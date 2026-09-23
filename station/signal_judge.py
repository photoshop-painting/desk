#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""داوری سیگنال بیرونی — «سیگنال نرم‌افزار فعلی‌تان را بیاورید؛ این‌جا می‌سنجیمش».

مسئله: ابزارهای فارسی بازار (دیده‌بان‌ها، ماشین‌حساب‌های بلک‌شولز، فیلترها) سیگنال می‌سازند؛
ولی هیچ‌کدام نمی‌گویند آن سیگنال **با کارمزد واقعی، نقدشوندگی، نرخ سد و وجه تضمین** می‌مانَد یا
می‌افتد. این ابزار همان یک کار را با عدد و دلیل انجام می‌دهد و در پایان، «فاصله تا مارجین‌کال»
هر موقعیت را هم می‌گوید.

نمونه:
    python signal_judge.py --kind basis --params '{"spot":20000,"future":22800,"days":50}' --json
    python signal_judge.py --file my-signal.json --hurdle 0.39 --capital 100000000
    python signal_judge.py --kind covered --params '{"spot":7000,"strike":7400,"premium":220,"days":30}'
    python signal_judge.py --kind basis --params '{"spot":20000,"future":22800,"days":50}' --sheet

مفروضات مارجین (اعلامی، نه حدسی): حد نگهداری = ۷۰٪ وجه تضمین اولیه (رویهٔ بورس ایران) و
وجه تضمین اولیهٔ اختیار فروش ≈ ۲۰٪ ارزش قرارداد. هر دو را می‌توانید با عدد کارگزاری خودتان
عوض کنید؛ اگر کارگزاری عدد دیگری بدهد، همان را بگذارید.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.1.0"
BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
TOOLS_DIR = (BASE.parent / "tools").resolve()
SHEET_HTML = DATA / "signal-verdict.html"
SHEET_MD = DATA / "signal-verdict.md"
CREDIT = ("تهیه‌کننده: Masoud Mojarabian · https://www.instagram.com/Mojarabian.Art/ · "
          "tel:+989126630554 · https://t.me/Mojarabian")
HURDLE_DEFAULT = 0.39          # نرخ سد پیش‌فرض (بازده مؤثر صندوق درآمد ثابت، شهریور ۱۴۰۵)
MAINTENANCE_DEFAULT = 0.70     # حد نگهداری وجه تضمین (رویهٔ بورس ایران)
INITIAL_RATIO_DEFAULT = 0.20   # وجه تضمین اولیهٔ اختیار فروش ≈ ۲۰٪ ارزش قرارداد
LIQUIDITY_FLOOR = 20           # کف قرارداد معامله‌شده در روز
SPREAD_CAP = 0.03              # سقف اسپرد نسبی
PLAUSIBLE_CAP = 5.0            # بیش از ۵۰۰٪ سالانه = مشکوک به دادهٔ اشتباه

for p in (str(TOOLS_DIR), str((BASE.parent / "desk").resolve())):
    if p not in sys.path:
        sys.path.insert(0, p)

KINDS = {
    "basis": "خرید نقدی و فروش آتی (کری) ، نرخ‌های لازم: spot, future, days[, storage_annual, spread_pct, liquidity_contracts_per_day]",
    "box": "باکس اسپرد ، call_low, put_low, call_high, put_high, strike_low, strike_high, days",
    "tabei": "تبعی (تضمین فروش) ، stock_price, put_price, strike, days",
    "covered": "پوشش‌داده‌شده ، spot, strike, premium, days",
    "parity": "تساوی پوت‌کال ، call, put, spot, strike, days[, rate]",
}

# کلیدی که برای «نقطهٔ برگشت» جابه‌جا می‌شود: تا کجا بشود و معامله همچنان بماند
KIND_LABELS = {"basis": "خرید نقدی و فروش آتی (کری)", "box": "باکس اسپرد",
               "tabei": "تبعی (تضمین فروش)", "covered": "پوشش‌داده‌شده (کاورد کال)",
               "parity": "تساوی پوت‌کال"}

FLIP_KEY = {"basis": "future", "covered": "premium", "tabei": "strike", "box": "call_low",
            "parity": "spot"}
FLIP_LABEL = {"basis": "کم‌ترین قیمت آتی که معامله بماند", "covered": "کم‌ترین پرمیوم که معامله بماند",
              "tabei": "کم‌ترین قیمت اعمال که معامله بماند", "box": "کم‌ترین قیمت پاها که معامله بماند",
              "parity": "قیمتی که فاصله را از هزینه رد می‌کند"}


def load_engine():
    import derivatives_scout as scout  # noqa: WPS433
    return scout


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fa_num(x, digits: int = 2) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        out = f"{x:,.{digits}f}"
        if digits > 0 and "." in out:
            out = out.rstrip("0").rstrip(".")
        return out
    return f"{x:,}"


def fingerprint(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- هستهٔ داوری
ENGINE_KIND = {"covered": "covered_call"}


def _row(kind: str, params: dict) -> dict:
    row = dict(params)
    row["kind"] = ENGINE_KIND.get(kind, kind)
    row.setdefault("liquidity_contracts_per_day", 99)
    row.setdefault("spread_pct", 0.0)
    row.setdefault("storage_annual", 0.0)
    row.setdefault("rate", HURDLE_DEFAULT)
    return row


def _run(kind: str, params: dict, hurdle: float) -> dict:
    scout = load_engine()
    res = scout.run_scenario(scout.Scenario(name=KINDS.get(kind, kind), rows=[_row(kind, params)],
                                           hurdle=hurdle))[0]
    if "error" in res:
        raise ValueError(res["error"])
    return res


def hand_annualized(kind: str, params: dict, res: dict) -> dict:
    """حساب دستی مستقل از موتور، برای همان عدد تصمیم (روش دوم، قابل بازبینی با ماشین‌حساب)."""
    if kind == "basis":
        spot, future, days = float(params["spot"]), float(params["future"]), float(params["days"])
        net = future - spot - (spot + future) * 0.0012          # کارمزد صندوق دو طرف
        period = net / spot
    elif kind == "tabei":
        stock, put, strike, days = (float(params["stock_price"]), float(params["put_price"]),
                                    float(params["strike"]), float(params["days"]))
        cost = stock * 1.00464 + put * 1.00103
        proceeds = strike * (1 - 0.00964)
        period = (proceeds - cost) / cost
    elif kind == "covered":
        spot, premium, days = float(params["spot"]), float(params["premium"]), float(params["days"])
        period = (premium * (1 - 0.00103)) / (spot * 1.00464)
    elif kind == "box":
        diff = float(params["strike_high"]) - float(params["strike_low"])
        debit = float(res.get("debit") or 0)
        period = (diff - debit - float(res.get("fees_estimate") or 0)) / debit if debit else 0.0
        days = float(params["days"])
    else:
        return {"method": "حساب دستی برای این راهبرد تعریف نشده", "period_pct": None,
                "annualized_pct": res.get("annualized_pct")}
    annual = ((1 + period) ** (365 / days) - 1) * 100 if days else None
    return {"method": "سود دوره ÷ سرمایه، بعد (۱+بازده)^(۳۶۵÷روز) − ۱",
            "period_pct": round(period * 100, 3),
            "annualized_pct": round(annual, 2) if annual is not None else None}


def break_even(kind: str, params: dict, hurdle: float, *, lo: float | None = None,
               hi: float | None = None, tol: float = 1e-4) -> dict | None:
    """نقطهٔ برگشت: مقدار آن ورودی که معامله دقیقاً به نرخ سد می‌رسد."""
    key = FLIP_KEY.get(kind)
    if key is None or key not in params:
        return None
    base = float(params[key])
    if base == 0:
        return None
    try:
        if _run(kind, params, hurdle).get("annualized_pct") is None:
            return {"key": key, "label": FLIP_LABEL[kind], "value": None,
                    "note": ("این ساختار بازده سالانهٔ سد‌محور ندارد؛ تصمیمش ساختاری است "
                             "(تساوی پوت‌کال با هزینهٔ اجرا سنجیده می‌شود)، پس «نقطهٔ برگشت سد» "
                             "برای آن معنا ندارد.")}
    except (ValueError, KeyError, ZeroDivisionError):
        return None
    lo = base * 0.2 if lo is None else lo
    hi = base * 3.0 if hi is None else hi

    def edge(value: float) -> float:
        p = dict(params)
        p[key] = value
        try:
            res = _run(kind, p, hurdle)
        except (ValueError, ZeroDivisionError):
            return -999.0
        annual = res.get("annualized_pct")
        if annual is None:
            return -999.0
        return float(annual) - hurdle * 100

    e_lo, e_hi = edge(lo), edge(hi)
    increasing = e_hi > e_lo
    if (e_lo > 0) == (e_hi > 0):
        return {"key": key, "label": FLIP_LABEL[kind], "value": None,
                "note": "در این بازه نقطهٔ برگشت پیدا نشد؛ یعنی با این ورودی‌ها تصمیم عوض نمی‌شود."}
    for _ in range(90):
        mid = (lo + hi) / 2
        e_mid = edge(mid)
        if e_mid == 0:
            lo = hi = mid
            break
        if (e_mid > 0) == increasing:      # ریشه بین lo و mid است
            hi, e_hi = mid, e_mid
        else:
            lo, e_lo = mid, e_mid
        if abs(hi - lo) <= tol * max(1.0, abs(base)):
            break
    value = (lo + hi) / 2
    return {"key": key, "label": FLIP_LABEL[kind], "value": round(value, 3),
            "note": ("اگر این ورودی از این عدد بدتر شود، معامله از دروازه می‌افتد؛ "
                     "این همان «نقطهٔ بی‌تفاوتی» است که در ابزارهای نمایش‌دادهٔ بازار پیدا نمی‌شود.")}


def margin_call(*, contracts: float, margin_per_contract: float, notional_per_contract: float,
                maintenance: float = MAINTENANCE_DEFAULT, current_price: float | None = None,
                direction: str = "long") -> dict:
    """فاصله تا اخطاریهٔ مارجین‌کال: چند درصد حرکت مخالف، حساب را به حد نگهداری می‌رساند.

    مبنا: حد نگهداری = ۷۰٪ وجه تضمین اولیه (رویهٔ بورس ایران). تسویهٔ روزانه است، پس هر روز
    دوباره محاسبه می‌شود؛ عدد این‌جا برای همان لحظهٔ ورود است.
    """
    if contracts <= 0 or margin_per_contract <= 0 or notional_per_contract <= 0:
        return {"ok": False, "detail": "برای محاسبهٔ مارجین‌کال، تعداد قرارداد، وجه تضمین و ارزش قرارداد لازم است."}
    buffer_per_contract = margin_per_contract * (1 - maintenance)
    loss_pct_notional = buffer_per_contract / notional_per_contract * 100
    money_at_risk = buffer_per_contract * contracts
    out = {
        "ok": True, "contracts": contracts, "margin_per_contract": margin_per_contract,
        "notional_per_contract": notional_per_contract, "maintenance": maintenance,
        "maintenance_pct": round(maintenance * 100, 1),
        "buffer_per_contract": round(buffer_per_contract, 2),
        "move_pct": round(loss_pct_notional, 3),
        "money_at_risk": round(money_at_risk, 2),
        "margin_locked": round(margin_per_contract * contracts, 2),
        "formula": ("فاصله = وجه تضمین × (۱ − حد نگهداری) ÷ ارزش قرارداد. "
                    f"اینجا: {fa_num(margin_per_contract)} × {1 - maintenance:.2f} ÷ "
                    f"{fa_num(notional_per_contract)} = {loss_pct_notional:.2f}٪ حرکت مخالف."),
        "note": (" حرکت مخالف به همین اندازه، حساب را به حد نگهداری می‌رساند و اخطاریه می‌آید؛ "
                 "پس حد ضرر منطقی باید نزدیک‌تر از این عدد باشد، نه دورتر."),
    }
    if current_price:
        level = (current_price * (1 - loss_pct_notional / 100) if direction != "short"
                 else current_price * (1 + loss_pct_notional / 100))
        out["price_level"] = round(level, 2)
        out["price_note"] = (f"با قیمت فعلی {fa_num(current_price)}، سطح اخطاریه حدود "
                             f"{fa_num(level)} است.")
    return out


def judge(kind: str, params: dict, *, hurdle: float = HURDLE_DEFAULT, capital: float = 100_000_000,
          margin_per_contract: float = 0.0, contracts: float = 0.0,
          notional_per_contract: float | None = None, maintenance: float = MAINTENANCE_DEFAULT,
          initial_ratio: float = INITIAL_RATIO_DEFAULT, current_price: float | None = None,
          claimed_return_pct: float | None = None, direction: str = "long") -> dict:
    """داوری کامل یک سیگنال بیرونی: می‌ماند یا می‌افتد، چرا، تا کجا، و فاصله تا مارجین‌کال."""
    if kind not in KINDS:
        return {"ok": False, "detail": f"نوع راهبرد «{kind}» شناخته نشد. گزینه‌ها: "
                                       + "، ".join(KINDS)}
    try:
        res = _run(kind, params, hurdle)
    except (ValueError, KeyError, ZeroDivisionError) as e:
        return {"ok": False, "detail": f"عددهای ورودی کامل یا درست نیست: {e}"}

    annual = res.get("annualized_pct")
    annual_f = float(annual) if isinstance(annual, (int, float)) else None
    edge_pp = (annual_f - hurdle * 100) if annual_f is not None else None
    reasons: list[str] = []
    gates: list[dict] = []

    def gate(name: str, ok: bool, detail: str):
        gates.append({"gate": name, "ok": bool(ok), "detail": detail})
        if not ok:
            reasons.append(detail)

    gate("موتور ریاضی", bool(res.get("go")), "موتور خودش این معامله را پذیرفت."
         if res.get("go") else "موتور ریاضی این ساختار را از پایه رد می‌کند (مثلاً جهت لازم ممکن نیست).")
    if annual_f is None:
        structural = kind == "parity"
        gate("بازده قابل محاسبه", structural,
             "این ساختار بازده سالانهٔ ساده ندارد؛ تصمیمش با تساوی پوت‌کال گرفته می‌شود."
             if structural else "بازده سالانه از این عددها درنمی‌آید؛ ورودی‌ها را کامل کنید.")
    else:
        ok_hurdle = edge_pp is not None and edge_pp > 0
        gate("نرخ سد", ok_hurdle,
             f"بازده سالانه {annual_f:.1f}٪ در برابر نرخ سد {hurdle * 100:.0f}٪ → "
             f"{'مثبت' if ok_hurdle else 'منفی'} ({edge_pp:+.1f} واحد درصد).")
        gate("معقول‌بودن عدد", not (annual_f is not None and annual_f / 100 > PLAUSIBLE_CAP),
             "بازده سالانه معقول است." if annual_f / 100 <= PLAUSIBLE_CAP else
             f"بازده سالانه {annual_f:.0f}٪ غیرواقعی است؛ احتمالاً قیمت جابه‌جا وارد شده.")
    liq = res.get("liquidity_contracts_per_day", 99)
    gate("نقدشوندگی", liq >= LIQUIDITY_FLOOR,
         f"نقدشوندگی {liq} قرارداد در روز " + ("کافی است." if liq >= LIQUIDITY_FLOOR
                                                else f"کمتر از کف {LIQUIDITY_FLOOR} است؛ خروج از موقعیت ممکن است گران تمام شود."))
    spread = float(res.get("spread_pct") or 0.0)
    gate("اسپرد", spread <= SPREAD_CAP,
         f"اسپرد {spread * 100:.1f}٪ " + ("قابل قبول است." if spread <= SPREAD_CAP
                                          else f"از سقف {SPREAD_CAP * 100:.0f}٪ بیشتر است؛ سود کاغذی است."))
    if kind == "parity":
        d = str(res.get("direction") or "")
        gate("قابل اجرا بودن جهت", not d.startswith("reverse"),
             "جهت معامله در ایران قابل اجرا است." if not d.startswith("reverse")
             else f"جهت لازم «{d}» است؛ فروش استقراضی در ایران ممکن نیست.")

    verdict = "می‌ماند" if not reasons else "می‌افتد"
    if contracts and margin_per_contract and notional_per_contract is None:
        notional_per_contract = margin_per_contract / max(initial_ratio, 1e-9)
    mc = (margin_call(contracts=contracts or 1, margin_per_contract=margin_per_contract,
                      notional_per_contract=notional_per_contract or 0.0,
                      maintenance=maintenance, current_price=current_price, direction=direction)
          if (margin_per_contract and notional_per_contract) else
          {"ok": False, "detail": "برای فاصلهٔ مارجین‌کال، وجه تضمین هر قرارداد و ارزش قرارداد را بدهید."})

    hand = hand_annualized(kind, params, res)
    diff = (None if (hand.get("annualized_pct") is None or annual_f is None)
            else round(float(hand["annualized_pct"]) - annual_f, 3))

    size = None
    if capital and margin_per_contract:
        engine = load_engine()
        size = engine.position_size(capital=capital, margin_per_contract=margin_per_contract,
                                    risk_pct=0.20, concurrent=1)

    payload = {
        "ok": True, "ts": now_iso(), "kind": kind,
        "kind_label": KIND_LABELS.get(kind, kind), "params": params,
        "hurdle": hurdle, "capital": capital, "annualized_pct": annual_f, "edge_pp": edge_pp,
        "engine_go": bool(res.get("go")), "score_pp": res.get("score_pp"),
        "verdict": verdict, "reasons": reasons, "gates": gates,
        "break_even": break_even(kind, params, hurdle), "margin": mc, "size": size,
        "hand": hand, "hand_diff_pp": diff,
        "claimed_return_pct": claimed_return_pct,
        "claim_note": (None if claimed_return_pct is None else
                       f"ابزار شما {claimed_return_pct:.1f}٪ سالانه گفته؛ محاسبهٔ خالص این‌جا "
                       f"{annual_f:.1f}٪ است ({annual_f - claimed_return_pct:+.1f} واحد درصد). "
                       "اختلاف معمولاً از کارمزد، اسپرد و مالیات می‌آید که در آن عدد لحاظ نشده."),
        "res": res,
    }
    payload["fingerprint"] = fingerprint({k: v for k, v in payload.items() if k != "fingerprint"})
    return payload


# ---------------------------------------------------------------- برگهٔ داوری
def _html(j: dict) -> str:
    if not j.get("ok"):
        return f"<html lang='fa' dir='rtl'><meta charset='utf-8'><p>{j.get('detail')}</p></html>"
    ok = j["verdict"] == "می‌ماند"
    color = "#0a7f4f" if ok else "#b32020"
    rows = "\n".join(
        f"<tr><td>{g['gate']}</td><td>{'✅' if g['ok'] else '❌'}</td>"
        f"<td class='hint'>{g['detail']}</td></tr>" for g in j["gates"])
    be = j.get("break_even") or {}
    mc = j.get("margin") or {}
    sz = j.get("size") or {}
    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8"><title>داوری سیگنال — {j['kind_label']}</title>
<style>
 body{{font-family:Tahoma,system-ui,sans-serif;background:#f6f7fb;color:#151a26;margin:0;padding:28px}}
 .wrap{{max-width:900px;margin:auto;background:#fff;border:1px solid #e3e6ef;border-radius:14px;padding:26px}}
 h1{{font-size:20px;margin:0 0 4px}} h2{{font-size:15px;margin:20px 0 8px}}
 .verdict{{font-size:22px;font-weight:700;color:{color};margin:10px 0}}
 table{{width:100%;border-collapse:collapse;margin-top:6px}}
 th,td{{border:1px solid #e3e6ef;padding:7px 9px;font-size:13px;text-align:right}}
 th{{background:#f2f4fa}} .hint{{color:#5b6478;font-size:12.5px}}
 .kpi{{display:inline-block;border:1px solid #e3e6ef;border-radius:10px;padding:8px 12px;margin:4px 6px 0 0}}
 .kpi b{{display:block;font-size:16px}}
 .foot{{margin-top:18px;border-top:1px solid #e3e6ef;padding-top:10px;color:#5b6478;font-size:12px}}
</style></head><body><div class="wrap">
<h1>داوری سیگنال بیرونی</h1>
<p class="hint">{j['ts']} · نسخهٔ {VERSION} · اثر انگشت: <b>{j['fingerprint']}</b></p>
<p class="hint">سیگنال: {j['kind_label']}</p>
<div class="verdict">داوری: {j['verdict']}</div>
<div>
 <span class="kpi">بازده سالانهٔ خالص<b>{fa_num(j['annualized_pct'])}٪</b></span>
 <span class="kpi">نرخ سد<b>{j['hurdle'] * 100:.0f}٪</b></span>
 <span class="kpi">حاشیه بر سد<b>{fa_num(j['edge_pp'])} واحد</b></span>
</div>
{"<p class='hint'>⚠️ " + " · ".join(j["reasons"]) + "</p>" if j["reasons"] else ""}
<h2>دروازه‌ها</h2>
<table><thead><tr><th>دروازه</th><th>نتیجه</th><th>توضیح</th></tr></thead><tbody>{rows}</tbody></table>
<h2>نقطهٔ برگشت (تا کجا می‌مانَد)</h2>
<p>{('در «' + be.get('label', '') + '»: ' + str(be.get('value')) + ' — ' + be.get('note', '')
     if be and be.get('value') is not None else (be or {}).get('note', '—'))}</p>
<h2>فاصله تا مارجین‌کال</h2>
{("<p>" + mc.get("formula", "") + "</p><p class='hint'>حد نگهداری " + str(mc.get("maintenance_pct")) +
  "٪ · پول در معرض خطر: " + fa_num(mc.get("money_at_risk"), 0) + " · " + mc.get("note", "") +
  (" " + mc.get("price_note", "") if mc.get("price_note") else "") + "</p>")
 if mc.get("ok") else "<p class='hint'>" + mc.get("detail", "—") + "</p>"}
<h2>اندازهٔ موقعیت و دو روش حساب</h2>
{("<p class='hint'>با سرمایهٔ " + fa_num(j["capital"], 0) + " و وجه تضمین " +
  fa_num(mc.get("margin_per_contract") or 0, 0) + " در هر قرارداد: " + str(sz.get("contracts")) +
  " قرارداد (درگیر " + fa_num(sz.get("margin_locked"), 0) + "، آزاد " + fa_num(sz.get("free_cash"), 0) + ").</p>")
 if sz else ""}
<p class="hint">محاسبهٔ دوم (مستقل از موتور): {j['hand']['method']} → {j['hand']['annualized_pct']}٪ سالانه
 (اختلاف با موتور: {j['hand_diff_pp']} واحد درصد). عددها را با ماشین‌حساب جیبی هم می‌توان بازبینی کرد.</p>
{j.get("claim_note") or ""}
<div class="foot">{CREDIT}<br>هیچ سفارشی از این برنامه ارسال نمی‌شود؛ اجرا در سامانهٔ کارگزاری با انسان است.
عددها روی ورودی‌های همین برگه بسته شده‌اند و اثر انگشت بالا تغییرشان را لو می‌دهد.</div>
</div></body></html>
"""


def _md(j: dict) -> str:
    if not j.get("ok"):
        return f"# داوری سیگنال\n\n{j.get('detail')}\n"
    L = [f"# داوری سیگنال بیرونی — {j['kind_label']}\n",
         f"تاریخ: {j['ts']} · اثر انگشت: {j['fingerprint']}\n", f"## داوری: {j['verdict']}\n",
         f"- بازده سالانهٔ خالص: {j['annualized_pct']}٪ (نرخ سد {j['hurdle'] * 100:.0f}٪، "
         f"حاشیه {j['edge_pp']} واحد)", "\n## دروازه‌ها\n", "| دروازه | نتیجه | توضیح |", "| --- | --- | --- |"]
    for g in j["gates"]:
        L.append(f"| {g['gate']} | {'✅' if g['ok'] else '❌'} | {g['detail']} |")
    be = j.get("break_even") or {}
    mc = j.get("margin") or {}
    L += ["\n## نقطهٔ برگشت\n", (f"{be.get('label')}: {be.get('value')} — {be.get('note')}"
                                if be.get("value") is not None else be.get("note", "—"))]
    L += ["\n## فاصله تا مارجین‌کال\n", mc.get("formula", mc.get("detail", "—")),
          (f"حد نگهداری {mc.get('maintenance_pct')}٪ · پول در معرض خطر {mc.get('money_at_risk')}"
           if mc.get("ok") else "")]
    L += [f"\n## دو روش حساب\n", f"موتور: {j['annualized_pct']}٪ · دستی: {j['hand']['annualized_pct']}٪ "
          f"(اختلاف {j['hand_diff_pp']} واحد)", f"\n{j.get('claim_note') or ''}", f"\n{CREDIT}"]
    return "\n".join(L) + "\n"


def build_sheet(j: dict, path_html: Path | str = SHEET_HTML,
                path_md: Path | str = SHEET_MD) -> tuple[Path, Path]:
    h, m = Path(path_html), Path(path_md)
    h.parent.mkdir(parents=True, exist_ok=True)
    h.write_text(_html(j), encoding="utf-8")
    m.write_text(_md(j), encoding="utf-8")
    return h, m


# ---------------------------------------------------------------- خط فرمان
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="داوری سیگنال ابزارهای دیگر با کارمزد و ریسک واقعی")
    ap.add_argument("--kind", choices=sorted(KINDS), help="نوع راهبرد")
    ap.add_argument("--params", default="", help="عددهای ورودی به شکل JSON")
    ap.add_argument("--file", default="", help="پروندهٔ JSON با کلیدهای kind و params")
    ap.add_argument("--hurdle", type=float, default=HURDLE_DEFAULT, help="نرخ سد سالانه (۰٫۳۹ = ۳۹٪)")
    ap.add_argument("--capital", type=float, default=100_000_000, help="سرمایه (ریال/تومان)")
    ap.add_argument("--margin", type=float, default=0.0, help="وجه تضمین اولیهٔ هر قرارداد")
    ap.add_argument("--contracts", type=float, default=0.0, help="تعداد قرارداد")
    ap.add_argument("--notional", type=float, default=None, help="ارزش هر قرارداد")
    ap.add_argument("--maintenance", type=float, default=MAINTENANCE_DEFAULT, help="حد نگهداری (۰٫۷)")
    ap.add_argument("--price", type=float, default=None, help="قیمت فعلی دارایی پایه")
    ap.add_argument("--claimed", type=float, default=None, help="بازدهی که ابزار فعلی شما گفته (٪)")
    ap.add_argument("--sheet", action="store_true", help="ساخت برگهٔ چاپی داوری")
    ap.add_argument("--json", action="store_true", help="خروجی ماشین‌خوان")
    ap.add_argument("--version", action="version", version=f"signal_judge {VERSION}")
    args = ap.parse_args(argv)

    if args.file:
        blob = json.loads(Path(args.file).read_text(encoding="utf-8"))
        kind = blob.get("kind") or args.kind
        params = blob.get("params") or {}
        args.hurdle = blob.get("hurdle", args.hurdle)
        for k in ("capital", "margin", "contracts", "notional", "maintenance", "price", "claimed"):
            if k in blob:
                setattr(args, k, blob[k])
    else:
        kind = args.kind
        params = json.loads(args.params) if args.params else {}
    if not kind:
        print("نوع راهبرد را بدهید: " + "، ".join(sorted(KINDS)), file=sys.stderr)
        return 2

    j = judge(kind, params, hurdle=args.hurdle, capital=args.capital,
              margin_per_contract=args.margin, contracts=args.contracts,
              notional_per_contract=args.notional, maintenance=args.maintenance,
              current_price=args.price, claimed_return_pct=args.claimed)
    if args.sheet and j.get("ok"):
        h, m = build_sheet(j)
        j["sheet_html"], j["sheet_md"] = str(h), str(m)
    if args.json:
        print(json.dumps(j, ensure_ascii=False, indent=1))
        return 0 if j.get("ok") else 2
    if not j.get("ok"):
        print(j.get("detail"))
        return 2
    ann = "قابل محاسبه نیست" if j["annualized_pct"] is None else f"{j['annualized_pct']}٪"
    print(f"داوری: {j['verdict']}  (بازده سالانهٔ خالص {ann} در برابر سد {j['hurdle'] * 100:.0f}٪)")
    for g in j["gates"]:
        print(f"  {'✓' if g['ok'] else '✗'} {g['gate']}: {g['detail']}")
    be = j.get("break_even") or {}
    if be.get("value") is not None:
        print(f"نقطهٔ برگشت — {be['label']}: {be['value']}")
    mc = j.get("margin") or {}
    if mc.get("ok"):
        print(f"مارجین‌کال: {mc['move_pct']}٪ حرکت مخالف · پول در معرض خطر {fa_num(mc['money_at_risk'], 0)}"
              + (f" · سطح اخطاریه {mc.get('price_level')}" if mc.get("price_level") else ""))
    print(f"دو روش: موتور {j['annualized_pct']}٪ · دستی {j['hand']['annualized_pct']}٪ "
          f"(اختلاف {j['hand_diff_pp']} واحد) · اثر انگشت {j['fingerprint']}")
    if j.get("sheet_html"):
        print("برگهٔ داوری: " + j["sheet_html"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
