#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""پس‌آزمایی (Backtest) — همان موتوری که در تصمیم زنده به کار می‌رود، روی دادهٔ تاریخ.

چرا مهم است: هر عددی که روی کاغذ خوب به نظر می‌رسد، باید روی دادهٔ واقعی گذشته
آزمایش شود. این برنامه همان دروازه‌های ریسک زنده را روی تاریخ اجرا می‌کند،
«برنده» و «بازنده» را جدا می‌شمارد، و خطای پیش‌بینی را عدد می‌کند.

قاعدهٔ ضد خطای آینده‌نگری: تصمیم هر سطر فقط از فیلدهای همان سطر (و ستون نرخ سد همان تاریخ)
گرفته می‌شود. ستون `realized_annualized_pct` که «نتیجهٔ واقعی» است، فقط در سنجش
به کار می‌رود و در تصمیم هیچ نقشی ندارد؛ این نکته در آزمون‌ها هم بررسی می‌شود.
"""
from __future__ import annotations

import csv
import html
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.1.0"
BASE = Path(__file__).resolve().parent
DESK_DIR = (BASE.parent / "desk").resolve()

if str(DESK_DIR) not in sys.path:
    sys.path.insert(0, str(DESK_DIR))

try:  # موتور زنده؛ همین موتور در پس‌آزمایی هم اجرا می‌شود
    import desk as live_desk  # type: ignore
except Exception as e:  # pragma: no cover
    live_desk = None  # type: ignore
    _IMPORT_ERROR = e

CREDIT = ("تهیه‌کننده: Masoud Mojarabian · https://www.instagram.com/Mojarabian.Art/ · "
          "tel:+989126630554 · https://t.me/Mojarabian")

KIND_LABELS = {
    "basis": "پایهٔ نقدی‌آتی",
    "box": "باکس اسپرد",
    "tabei": "اوراق تبعی",
    "covered_call": "پوشش‌داده‌شده",
    "parity": "تساوی پوت‌کال",
}

DEFAULT_RULES = {
    "min_edge_arbitrage_pct": 3.0,
    "min_edge_leveraged_pct": 5.0,
    "min_liquidity_contracts_per_day": 20,
    "max_spread_pct": 0.03,
    "position_weight": 0.25,   # سهم هر معامله از سرمایه در شبیه‌سازی منحنی سرمایه
    "max_plausible_arb_pct": 250.0,
    "max_plausible_lev_pct": 400.0,
}

ARBITRAGE_KINDS = {"box", "parity", "tabei"}


# ---------------------------------------------------------------- ورودی
def load_history(path: str | Path) -> tuple[list[dict], list[str]]:
    """پروندهٔ تاریخی CSV را می‌خواند؛ سطرهای شروع‌شده با # و سطرهای خالی نادیده گرفته می‌شوند."""
    p = Path(path)
    problems: list[str] = []
    if not p.exists():
        return [], [f"پروندهٔ تاریخ پیدا نشد: {p}"]
    rows: list[dict] = []
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        raw = data if isinstance(data, list) else data.get("rows", [])
    else:
        raw_text = p.read_text(encoding="utf-8-sig").lstrip("\ufeff")
        text = "\n".join(line for line in raw_text.splitlines()
                         if line.strip() and not line.lstrip().startswith("#"))
        raw = list(csv.DictReader(text.splitlines()))
    for i, r in enumerate(raw, 1):
        if not r.get("kind") or not r.get("symbol"):
            problems.append(f"سطر {i}: نماد یا نوع راهبرد خالی است")
            continue
        row = {}
        for k, v in r.items():
            if k is None:
                continue
            if isinstance(v, str):
                v = v.strip()
                if v == "":
                    continue
                try:
                    row[k] = float(v) if any(c.isdigit() for c in v) and k not in ("date", "symbol", "kind", "unit") else v
                except ValueError:
                    row[k] = v
            else:
                row[k] = v
        rows.append(row)
    if not rows:
        problems.append("هیچ سطر معتبری در پروندهٔ تاریخ نبود")
    return rows, problems


# ---------------------------------------------------------------- تصمیم و نتیجه
@dataclass
class DecisionRow:
    date: str
    symbol: str
    kind: str
    taken: bool
    reason: str
    expected_annualized_pct: float | None
    edge_pp: float
    hurdle: float
    realized_annualized_pct: float | None
    days: float
    period_realized_pct: float | None

    def as_dict(self) -> dict:
        return {
            "date": self.date, "symbol": self.symbol, "kind": self.kind,
            "decision": "ورود" if self.taken else "رد",
            "reason": self.reason,
            "expected_annualized_pct": None if self.expected_annualized_pct is None else round(self.expected_annualized_pct, 3),
            "edge_pp": round(self.edge_pp, 3),
            "hurdle": self.hurdle,
            "realized_annualized_pct": None if self.realized_annualized_pct is None else round(self.realized_annualized_pct, 3),
            "period_realized_pct": None if self.period_realized_pct is None else round(self.period_realized_pct, 3),
        }


def period_return(annualized_pct: float | None, days: float) -> float | None:
    """بازده سالانه را به بازده همان دوره ترجمه می‌کند."""
    if annualized_pct is None or days <= 0:
        return None
    return ((1 + annualized_pct / 100.0) ** (days / 365.0) - 1) * 100.0


def decide_row(row: dict, rules: dict) -> DecisionRow:
    """دقیقاً همان دروازه‌های زنده، روی یک سطر تاریخ."""
    if live_desk is None:  # pragma: no cover
        raise RuntimeError(f"موتور زنده بارگذاری نشد: {_IMPORT_ERROR}")
    hurdle = float(row.get("hurdle", 0.39))
    kind = str(row.get("kind"))
    payload = {k: v for k, v in row.items() if not k.startswith("realized")}
    payload["margin_per_contract"] = float(row.get("margin_per_contract", 0) or 0)
    try:
        res = live_desk.math_for_row(payload, hurdle)
    except Exception as e:
        return DecisionRow(date=str(row.get("date", "")), symbol=str(row.get("symbol", "")), kind=kind,
                           taken=False, reason=f"محاسبه نشد: {type(e).__name__}: {e}",
                           expected_annualized_pct=None, edge_pp=-999.0, hurdle=hurdle,
                           realized_annualized_pct=_num(row.get("realized_annualized_pct")),
                           days=float(row.get("days", 0) or 0), period_realized_pct=None)

    edge = float(res.get("score_pp", -999.0))
    reasons: list[str] = []
    if not res.get("go"):
        reasons.append("موتور ریاضی تأیید نکرد")
    threshold = rules["min_edge_arbitrage_pct"] if kind in ARBITRAGE_KINDS else rules["min_edge_leveraged_pct"]
    if edge < threshold:
        reasons.append(f"حاشیهٔ {edge:.2f} کمتر از کف {threshold:.2f}")
    ceiling = (rules["max_plausible_arb_pct"] if kind in ARBITRAGE_KINDS else rules["max_plausible_lev_pct"])
    annual = res.get("annualized_pct")
    if isinstance(annual, (int, float)) and abs(annual) > ceiling:
        reasons.append(f"بازده محاسبه‌شده {annual:,.0f}٪ از سقف باورپذیری ({ceiling:,.0f}٪) بیشتر است؛ داده مشکوک")
    liq = row.get("liquidity_contracts_per_day")
    if isinstance(liq, (int, float)) and liq < rules["min_liquidity_contracts_per_day"]:
        reasons.append(f"نقدشوندگی {liq:.0f} کمتر از کف {rules['min_liquidity_contracts_per_day']}")
    spread = row.get("spread_pct")
    if isinstance(spread, (int, float)) and spread > rules["max_spread_pct"]:
        reasons.append(f"اسپرد {spread * 100:.2f}٪ بیش از سقف")

    realized = _num(row.get("realized_annualized_pct"))
    days = float(row.get("days", 0) or 0)
    return DecisionRow(date=str(row.get("date", "")), symbol=str(row.get("symbol", "")), kind=kind,
                       taken=not reasons, reason="؛ ".join(reasons) or "همهٔ دروازه‌ها باز بود",
                       expected_annualized_pct=res.get("annualized_pct"), edge_pp=edge, hurdle=hurdle,
                       realized_annualized_pct=realized, days=days,
                       period_realized_pct=period_return(realized, days))


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- اجرا و سنجه‌ها
def run_backtest(history_path: str | Path, rules: dict | None = None,
                 capital: float = 20_000_000_000) -> dict:
    rules = {**DEFAULT_RULES, **(rules or {})}
    rows, problems = load_history(history_path)
    decisions = [decide_row(r, rules) for r in rows]
    taken = [d for d in decisions if d.taken]
    skipped = [d for d in decisions if not d.taken]

    def avg(xs: list[float]) -> float | None:
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else None

    realized_taken = [d.realized_annualized_pct for d in taken if d.realized_annualized_pct is not None]
    realized_skipped = [d.realized_annualized_pct for d in skipped if d.realized_annualized_pct is not None]
    hits = [d for d in taken if d.realized_annualized_pct is not None and d.realized_annualized_pct > d.hurdle * 100]
    losses = [d for d in taken if d.realized_annualized_pct is not None and d.realized_annualized_pct < 0]
    missed = [d for d in skipped if d.realized_annualized_pct is not None and d.realized_annualized_pct > d.hurdle * 100]
    errors = [d.realized_annualized_pct - (d.expected_annualized_pct or 0) for d in taken
              if d.realized_annualized_pct is not None and d.expected_annualized_pct is not None]

    # منحنی سرمایه: معامله‌ها به ترتیب تاریخ و پشت‌سرهم، با وزن ثابت — فرض ساده و صریح
    ordered = sorted([d for d in taken if d.period_realized_pct is not None],
                     key=lambda d: str(d.date))
    equity = capital
    curve = [{"trade": 0, "date": "شروع", "equity": round(equity, 0)}]
    for i, d in enumerate(ordered, 1):
        equity *= (1 + rules["position_weight"] * d.period_realized_pct / 100.0)
        curve.append({"trade": i, "date": d.date, "equity": round(equity, 0)})

    by_kind: dict[str, dict] = {}
    for d in decisions:
        slot = by_kind.setdefault(d.kind, {"total": 0, "taken": 0, "hits": 0,
                                           "realized": [], "expected": []})
        slot["total"] += 1
        if d.taken:
            slot["taken"] += 1
            if d.realized_annualized_pct is not None:
                slot["realized"].append(d.realized_annualized_pct)
                if d.realized_annualized_pct > d.hurdle * 100:
                    slot["hits"] += 1
            if d.expected_annualized_pct is not None:
                slot["expected"].append(d.expected_annualized_pct)

    summary = {
        "file": str(history_path),
        "rows": len(decisions),
        "taken": len(taken),
        "skipped": len(skipped),
        "hit_rate_pct": (100.0 * len(hits) / len(realized_taken)) if realized_taken else None,
        "false_positive_rate_pct": (100.0 * len(losses) / len(realized_taken)) if realized_taken else None,
        "missed_opportunity_rate_pct": (100.0 * len(missed) / len(realized_skipped)) if realized_skipped else None,
        "avg_expected_annualized_pct": avg([d.expected_annualized_pct for d in taken]),
        "avg_realized_annualized_pct": avg(realized_taken),
        "avg_realized_skipped_pct": avg(realized_skipped),
        "avg_forecast_error_pp": avg(errors),
        "final_equity": round(equity, 0),
        "start_capital": capital,
        "equity_change_pct": round((equity / capital - 1) * 100, 2) if capital else None,
        "best_trade": max((d.realized_annualized_pct for d in taken if d.realized_annualized_pct is not None), default=None),
        "worst_trade": min((d.realized_annualized_pct for d in taken if d.realized_annualized_pct is not None), default=None),
        "rules": rules,
        "problems": problems,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return {"summary": summary, "decisions": decisions, "equity_curve": curve,
            "by_kind": by_kind, "best": sorted([d for d in taken if d.realized_annualized_pct is not None],
                                               key=lambda d: d.realized_annualized_pct, reverse=True)[:3],
            "worst": sorted([d for d in taken if d.realized_annualized_pct is not None],
                            key=lambda d: d.realized_annualized_pct)[:3],
            "missed": sorted(missed, key=lambda d: d.realized_annualized_pct, reverse=True)[:5]}


# ---------------------------------------------------------------- خروجی‌ها
def write_csv(result: dict, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(result["decisions"][0].as_dict().keys()) if result["decisions"] else
                           ["date", "symbol", "kind", "decision", "reason"])
        w.writeheader()
        for d in result["decisions"]:
            w.writerow(d.as_dict())
    return p


def _fmt(v, digits: int = 2, suffix: str = "") -> str:
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        return f"{v:,.{digits}f}{suffix}"
    return html.escape(str(v))


def build_report(result: dict, path: str | Path, title: str = "گزارش پس‌آزمایی") -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    s = result["summary"]
    rows = "".join(
        f"<tr><td>{html.escape(d.date)}</td><td>{html.escape(d.symbol)}</td>"
        f"<td>{html.escape(KIND_LABELS.get(d.kind, d.kind))}</td>"
        f"<td class='{'ok' if d.taken else 'no'}'>{'ورود' if d.taken else 'رد'}</td>"
        f"<td class='why'>{html.escape(d.reason)}</td>"
        f"<td class='num'>{_fmt(d.expected_annualized_pct)}</td>"
        f"<td class='num'>{_fmt(d.edge_pp)}</td>"
        f"<td class='num'>{_fmt(d.realized_annualized_pct)}</td>"
        f"<td class='num'>{_fmt(d.period_realized_pct)}</td></tr>"
        for d in result["decisions"][:400])

    kind_rows = "".join(
        f"<tr><td>{html.escape(KIND_LABELS.get(k, k))}</td><td class='num'>{v['total']}</td>"
        f"<td class='num'>{v['taken']}</td>"
        f"<td class='num'>{_fmt(sum(v['expected']) / len(v['expected']) if v['expected'] else None)}</td>"
        f"<td class='num'>{_fmt(sum(v['realized']) / len(v['realized']) if v['realized'] else None)}</td>"
        f"<td class='num'>{(100.0 * v['hits'] / len(v['realized'])) if v['realized'] else None}</td></tr>"
        for k, v in sorted(result["by_kind"].items(), key=lambda kv: -kv[1]["total"]))

    def small_table(items, label):
        if not items:
            return f"<p class='muted'>{label}: موردی نیست.</p>"
        return f"<p class='muted'>{label}</p><ul>" + "".join(
            f"<li>{html.escape(d.date)} · {html.escape(d.symbol)} · {html.escape(KIND_LABELS.get(d.kind, d.kind))}"
            f" — نتیجهٔ واقعی {_fmt(d.realized_annualized_pct, suffix='٪')} سالانه</li>" for d in items) + "</ul>"

    doc = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
 body {{ font-family: Tahoma, "Segoe UI", "Vazirmatn", sans-serif; margin: 0; background: #f6f7f9; color: #1d1d1f; }}
 header {{ background: #3b2f63; color: #fff; padding: 16px 22px; }}
 header h1 {{ margin: 0 0 6px; font-size: 19px; }}
 header .meta {{ font-size: 12px; opacity: .85; }}
 .cards {{ display: flex; gap: 10px; flex-wrap: wrap; padding: 14px 22px 0; }}
 .card {{ background: #fff; border: 1px solid #e3e6ea; border-radius: 10px; padding: 10px 12px; min-width: 165px; }}
 .card .k {{ font-size: 11.5px; color: #6b7280; }}
 .card .v {{ font-size: 17px; font-weight: bold; margin-top: 3px; }}
 main {{ padding: 12px 22px 40px; }}
 h2 {{ font-size: 15px; margin: 20px 0 8px; }}
 table {{ width: 100%; border-collapse: collapse; background: #fff; font-size: 12.5px; }}
 th, td {{ border-bottom: 1px solid #e6e8ec; padding: 6px 8px; text-align: right; vertical-align: top; }}
 th {{ background: #eef2f7; font-size: 12px; }}
 .num {{ font-variant-numeric: tabular-nums; }}
 .ok {{ color: #0a7d33; font-weight: bold; }}
 .no {{ color: #b3261e; }}
 .why {{ color: #444; max-width: 300px; }}
 .muted {{ color: #6b7280; font-size: 12.5px; }}
 .warn {{ background: #fff8e1; border: 1px solid #f0e0a8; border-radius: 8px; padding: 10px 12px; font-size: 12.5px; margin-bottom: 12px; }}
 footer {{ margin-top: 20px; font-size: 11.5px; color: #6b7280; }}
</style></head><body>
<header>
  <h1>{html.escape(title)}</h1>
  <div class="meta">پروندهٔ تاریخ: {html.escape(Path(s['file']).name)} · تاریخ اجرا: {html.escape(s['generated_at'])}
   · قواعد: کف آربیتراژ {s['rules']['min_edge_arbitrage_pct']} · کف اهرمی {s['rules']['min_edge_leveraged_pct']} · کف نقدشوندگی {s['rules']['min_liquidity_contracts_per_day']}</div>
</header>
<main>
  <div class="warn">این گزارش با «همان موتوری» ساخته شده که در تصمیم‌گیری زنده به کار می‌رود. هیچ عددی در آن وعدهٔ آینده نیست.
  نتیجهٔ هر معامله از ستون «نتیجهٔ واقعی» همان سطر می‌آید و در تصمیم هیچ نقشی نداشته است.</div>

  <div class="cards">
    <div class="card"><div class="k">کل سطرها</div><div class="v">{s['rows']}</div></div>
    <div class="card"><div class="k">ورود (تأییدشده)</div><div class="v">{s['taken']}</div></div>
    <div class="card"><div class="k">رد</div><div class="v">{s['skipped']}</div></div>
    <div class="card"><div class="k">نرخ برد</div><div class="v">{_fmt(s['hit_rate_pct'], 1, '٪')}</div></div>
    <div class="card"><div class="k">خطای مثبت کاذب</div><div class="v">{_fmt(s['false_positive_rate_pct'], 1, '٪')}</div></div>
    <div class="card"><div class="k">فرصت از دست رفته</div><div class="v">{_fmt(s['missed_opportunity_rate_pct'], 1, '٪')}</div></div>
    <div class="card"><div class="k">میانگین بازده انتظاری (ورودها)</div><div class="v">{_fmt(s['avg_expected_annualized_pct'], 1, '٪')}</div></div>
    <div class="card"><div class="k">میانگین بازده واقعی (ورودها)</div><div class="v">{_fmt(s['avg_realized_annualized_pct'], 1, '٪')}</div></div>
    <div class="card"><div class="k">خطای پیش‌بینی</div><div class="v">{_fmt(s['avg_forecast_error_pp'], 1, ' واحد')}</div></div>
    <div class="card"><div class="k">سرمایهٔ پایانی</div><div class="v">{_fmt(s['final_equity'], 0)}</div></div>
    <div class="card"><div class="k">تغییر سرمایه</div><div class="v">{_fmt(s['equity_change_pct'], 1, '٪')}</div></div>
  </div>

  <h2>تفکیک راهبردها</h2>
  <table><thead><tr><th>راهبرد</th><th>سطر</th><th>ورود</th><th>میانگین انتظاری</th><th>میانگین واقعی</th><th>نرخ برد</th></tr></thead>
  <tbody>{kind_rows}</tbody></table>

  <h2>سه معاملهٔ سودآورتر و سه معاملهٔ زیان‌ده‌تر (از میان ورودها)</h2>
  {small_table(result['best'], 'بهترین‌ها')}
  {small_table(result['worst'], 'بدترین‌ها')}

  <h2>فرصت‌هایی که با دروازه رد شدند ولی نتیجهٔ واقعی خوب داشتند</h2>
  {small_table(result['missed'], 'اگر دروازه‌ها را بازتر می‌کردیم')}

  <h2>سطر به سطر</h2>
  <table><thead><tr><th>تاریخ</th><th>نماد</th><th>راهبرد</th><th>تصمیم</th><th>دلیل</th>
  <th>بازده انتظاری (٪)</th><th>حاشیه (واحد)</th><th>نتیجهٔ واقعی (٪)</th><th>بازده دورهٔ واقعی (٪)</th></tr></thead>
  <tbody>{rows}</tbody></table>

  <footer>ساختهٔ پس‌آزمای ایستگاه نسخهٔ {VERSION} · {html.escape(CREDIT)}<br>
  فرض شبیه‌سازی سرمایه: هر معامله {s['rules']['position_weight'] * 100:.0f} درصد سرمایه، معامله‌ها پشت‌سرهم — ساده‌سازی عمدی و صریح.</footer>
</main></body></html>"""
    p.write_text(doc, encoding="utf-8")
    return p


def _cli(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="پس‌آزمایی موتور روی دادهٔ تاریخی")
    ap.add_argument("history")
    ap.add_argument("--out", default=str(BASE / "data" / "backtest.html"))
    ap.add_argument("--csv", default=str(BASE / "data" / "backtest.csv"))
    ap.add_argument("--capital", type=float, default=20_000_000_000)
    args = ap.parse_args(argv)
    result = run_backtest(args.history, capital=args.capital)
    s = result["summary"]
    print(f"سطرها: {s['rows']} · ورود: {s['taken']} · رد: {s['skipped']}")
    print(f"نرخ برد: {s['hit_rate_pct']}٪ · خطای مثبت کاذب: {s['false_positive_rate_pct']}٪ · "
          f"فرصت از دست رفته: {s['missed_opportunity_rate_pct']}٪")
    print(f"میانگین انتظاری: {s['avg_expected_annualized_pct']} · میانگین واقعی: {s['avg_realized_annualized_pct']}")
    print(f"گزارش: {build_report(result, args.out)}")
    print(f"CSV: {write_csv(result, args.csv)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
