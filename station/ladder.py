#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""پلهٔ تصمیم — سند «چه چیزی بخرم، چه زمانی بفروشم، چه زمانی می‌افتد».

این پرونده یک سند می‌سازد؛ محاسبه‌ها در `investor_test.py` هستند (یک موتور، نه دو تا).
خروجی: سه بخش روشن.

۱) بخش «چه چیزی بخرم»: ردیف‌هایی که امروز از نرخ سد عبور می‌کنند (به‌ترتیب بازده).
۲) بخش «چه چیزی نخر»: ردیف‌هایی که می‌افتند، با دلیل عددی — نه حذف‌شده و نه بی‌توضیح.
۳) برای هر ردیف: سه حد خروج (برداشت سود، توقف ضرر، سررسید) و نقطهٔ برگشت نرخ سد.

هیچ‌جا نمی‌گوییم «بخر»؛ می‌گوییم «اگر بخری، این سه حد این‌جاست و با این نرخ می‌افتد».
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import investor_test as inv

VERSION = "0.1.0"

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
LADDER_MD = DATA / "investor-ladder.md"
LADDER_JSON = DATA / "investor-ladder.json"


def build(rows: list[dict] | None = None, *, capital: float = 20_000_000_000.0,
          risk_pct: float = 0.20, margin_per_contract: float = 2_000_000_000.0,
          client: str = "", path_md: Path | str | None = None,
          path_json: Path | str | None = None) -> dict:
    """سند کامل را می‌سازد و (اختیاری) می‌نویسد."""
    rows = rows if rows is not None else inv.fallback_rows()
    entries = []
    for row in rows:
        if not row.get("kind"):
            continue
        try:
            entries.append(inv.ladder_for(row))
        except (KeyError, ValueError, ZeroDivisionError) as e:
            entries.append({"kind": row.get("kind"), "title": inv.KIND_TITLES.get(row.get("kind"), "?"),
                            "given": [], "ladder": [], "survives": False, "annualized_pct": None,
                            "hurdle_pct": None, "margin_pp": None, "fees_pct": 0.0,
                            "verdict": f"دادهٔ این ردیف کامل نیست، پس بررسی نشد ({e}).",
                            "why": "ردیف ناقص را حذف نمی‌کنیم؛ همان‌طور که هست گزارش می‌شود.",
                            "check": []})
    live = sorted([e for e in entries if e.get("survives") and (e.get("annualized_pct") or 0) > 0],
                  key=lambda e: e.get("annualized_pct") or -999, reverse=True)
    dead = [e for e in entries if e not in live]
    sizing = inv.engine().position_size(capital, margin_per_contract, risk_pct) if margin_per_contract else {}
    doc = {
        "version": VERSION,
        "client": client,
        "buy": live,
        "no_buy": dead,
        "counts": {"checked": len(entries), "actionable": len(live), "no_action": len(dead)},
        "sizing": {"capital": capital, "risk_pct": risk_pct,
                   "margin_per_contract": margin_per_contract, **sizing},
        "caps_note": (f"سقف هر راهبرد: {int(inv.STRATEGY_CAP_FRACTION * 100)}٪ سرمایهٔ تخصیص‌یافته؛ "
                      f"سقف کل باز: {int(risk_pct * 100)}٪ سرمایهٔ موجود برای وجه تضمین."),
        "fees_note": "همهٔ عددها بعد از کسر کارمزد واقعی (خرید سهم ۰.۴۶۴٪، فروش سهم ۰.۹۶۴٪، "
                     "اختیار ۰.۱۰۳٪ هر طرف) و در برابر نرخ سد سنجیده شده‌اند.",
        "honest": ("این فهرست پیشنهاد خرید نیست؛ خروجی محاسبه است. اگر کارگزاری شما عدد دیگری "
                   "برای کارمزد یا وجه تضمین می‌دهد، همان عدد مقدم است و در برنامه جایگزین می‌شود. "
                   "هیچ سودی تضمین نمی‌شود."),
        "verify": inv.verify_chain(),
    }
    doc["md"] = to_md(doc)
    if path_md:
        Path(path_md).write_text(doc["md"], encoding="utf-8")
        doc["path_md"] = str(path_md)
    if path_json:
        Path(path_json).write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        doc["path_json"] = str(path_json)
    return doc


def _block(e: dict) -> list[str]:
    out = [f"## {e['title']}", ""]
    if e.get("annualized_pct") is not None:
        out.append(f"- بازده سالانهٔ امروز (بعد از کارمزد {e['fees_pct']}٪): "
                   f"**{e['annualized_pct']}٪** · نرخ سد: {e['hurdle_pct']}٪ · "
                   f"حاشیه: {e['margin_pp']} واحد درصد")
    out += [f"- **داوری:** {e['verdict']}", f"- **چرا:** {e['why']}"]
    for step in e.get("ladder", []):
        out.append(f"  - {step['label']} — {step['when']} → حد: **{step['price']}** → "
                   f"اقدام: {step['action']}")
    for ch in e.get("check", []):
        out.append(f"  - محاسبهٔ دستی: {ch['note']} = {ch['value']} "
                   f"({'موافق' if ch['agree'] else 'مخالف ⚠️'})")
    out.append("")
    return out


def to_md(doc: dict) -> str:
    L = [f"# پلهٔ تصمیم — چه بخرم، چه زمانی بفروشم، چه زمانی می‌افتد (نسخهٔ {doc['version']})", ""]
    if doc.get("client"):
        L += [f"سرمایه‌گذار: **{doc['client']}**", ""]
    L += [doc["fees_note"], "",
          f"- ردیف بررسی‌شده: {doc['counts']['checked']} · قابل اجرا: {doc['counts']['actionable']} · "
          f"بدون اقدام: {doc['counts']['no_action']}",
          f"- {doc['caps_note']}", "", "# بخش ۱ — چه چیزی بخرم", ""]
    if doc["buy"]:
        for e in doc["buy"]:
            L += _block(e)
    else:
        L += ["امروز هیچ ردیفی از نرخ سد عبور نمی‌کند. این هم یک جواب است و بهترین جواب: نخر.", ""]
    L += ["# بخش ۲ — چه چیزی نخر (و چرا)", ""]
    for e in doc["no_buy"]:
        L += _block(e)
    s = doc.get("sizing") or {}
    if s.get("contracts") is not None:
        L += ["# بخش ۳ — اندازه: چند تا؟", "",
              f"- سرمایه: {s['capital']:,.0f} ریال · سقف ریسک: {int(s['risk_pct'] * 100)}٪ · "
              f"وجه تضمین هر قرارداد: {s['margin_per_contract']:,.0f} ریال",
              f"- حداکثر قرارداد: **{s['contracts']}** · وجه تضمین قفل‌شده: {s['margin_locked']:,.0f} "
              f"· نقد آزاد: {s['free_cash']:,.0f}", ""]
    L += [doc["honest"], "",
          f"اثر انگشت دفتر: `{doc['verify']['chain']}` · تمامیت زنجیره: "
          f"{'سالم' if doc['verify']['ok'] else 'شکسته'}", "", inv.CREDIT_MD, ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="پلهٔ تصمیم: چه بخرم، کِی بفروشم، کِی می‌افتد")
    ap.add_argument("--client", default="")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    doc = build(client=a.client, path_md=LADDER_MD, path_json=LADDER_JSON)
    print(json.dumps(doc, ensure_ascii=False, indent=1) if a.json else doc["md"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
