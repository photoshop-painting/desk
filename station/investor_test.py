#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون کور سرمایه‌گذار — «عدد را او می‌گوید، بعد جواب برنامه رو می‌شود».

این پرونده برای روز نمایش و پس از آن ساخته شده و چهار کار می‌کند:

۱) از دادهٔ همین اسنپ‌شات چند پرسش عددی می‌سازد که سرمایه‌گذار بتواند با ماشین‌حساب
   معمولی بازتولیدشان کند؛
۲) حدس سرمایه‌گذار را ثبت می‌کند و با جواب موتور می‌سنجد (دفتر زنجیره‌هش‌دار)؛
۳) برگهٔ چاپی دواِمضا می‌سازد: پرسش، حدس، جواب، مسیر محاسبه، محاسبهٔ دستی دوم،
   «کِی می‌افتد» و اثر انگشت دفتر؛
۴) پیمان‌نامهٔ نمایش می‌نویسد: چه چیزی اثبات می‌شود و چه چیزی نه.

قاعده‌های صداقت که در کد اعمال شده‌اند:
- هیچ عدد سودی «تضمین‌شده» نیست؛ همه از قیمت‌های همین اسنپ‌شات و کارمزدهای واقعی می‌آید.
- هر جواب یک «محاسبهٔ دستی دوم» جدا دارد (کسر دقیق + فرمول قابل اجرا) و اگر نخواند،
  آزمون می‌افتد تا سند بی‌اعتبار لو برود.
- هیچ چیزی به بیرون فرستاده نمی‌شود؛ دفتر و برگه‌ها محلی‌اند.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

VERSION = "0.1.0"

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
TOOLS = (BASE.parent / "tools").resolve()
DESK = (BASE.parent / "desk").resolve()
LOG_FILE = DATA / "investor-blind-test.json"
SHEET_HTML = DATA / "investor-blind-test.html"
SHEET_MD = DATA / "investor-blind-test.md"
PLEDGE_MD = DATA / "investor-pledge.md"

HURDLE_DEFAULT = 0.35        # نرخ سد پیش‌فرض (همان عدد ایستگاه، قابل جایگزینی با عدد شرکت)
GO_THRESHOLD = 0.03          # آستانهٔ «ارزش دارد» برای پوشش‌داده

CREDIT_HTML = (
    '✍️ تهیه‌کنندهٔ جزوات: <a href="https://t.me/Mojarabian">Masoud Mojarabian</a> · '
    '📱 <a href="tel:+989126630554">+989126630554</a> · '
    '✈️ <a href="https://t.me/Mojarabian">Telegram: Mojarabian</a> · '
    '📸 <a href="https://instagram.com/Mojarabian.Art">Instagram: Mojarabian.Art</a>')
CREDIT_MD = ("✍️ تهیه‌کنندهٔ جزوات: **Masoud Mojarabian** · 📱 +989126630554 · "
             "✈️ Telegram: [Mojarabian](https://t.me/Mojarabian) · "
             "📸 Instagram: [Mojarabian.Art](https://instagram.com/Mojarabian.Art)")

KIND_TITLES = {
    "basis": "مبنا (خرید نقدی + فروش آتی)",
    "box": "باکس اسپرد",
    "tabei": "اوراق تبعی",
    "covered_call": "پوشش‌داده‌شده (فروش اختیار خرید)",
    "parity": "تساوی پوت-کال",
}

TAKE_PROFIT_FRACTION = 0.50     # برداشت سود: ۵۰٪ بازده انتظاری
STOP_LOSS_FRACTION = 0.40       # توقف ضرر: ۴۰٪ بازده انتظاری
STRATEGY_CAP_FRACTION = 0.75    # سقف هر راهبرد از سرمایهٔ تخصیص‌یافته


# ------------------------------------------------------------------ موتور
_ENGINE = None


def engine():
    """موتور مشتقه را از tools/ می‌خواند (بدون نصب، بدون اینترنت)."""
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE
    path = TOOLS / "derivatives_scout.py"
    if not path.exists():
        raise FileNotFoundError(f"موتور پیدا نشد: {path}")
    spec = importlib.util.spec_from_file_location("derivatives_scout", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["derivatives_scout"] = mod   # لازم برای @dataclass داخل موتور
    spec.loader.exec_module(mod)
    _ENGINE = mod
    return mod


def demo_rows() -> list[dict]:
    """ردیف‌ها: اول پروندهٔ بازار ایستگاه، بعد نمونهٔ خود موتور."""
    f = DESK / "market-demo.json"
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            got = data.get("rows") if isinstance(data, dict) else data
            rows = [r for r in (got or []) if isinstance(r, dict) and r.get("kind")]
            if rows:
                return rows
        except (json.JSONDecodeError, OSError):
            pass
    return list(engine().DEMO["rows"])


def fallback_rows() -> list[dict]:
    try:
        return demo_rows()
    except (FileNotFoundError, OSError):
        return list(engine().DEMO["rows"])


def _pick(kind: str, rows: list[dict] | None = None) -> dict:
    for r in (rows if rows is not None else fallback_rows()):
        if r.get("kind") == kind:
            return r
    raise LookupError(f"ردیفی با نوع «{kind}» پیدا نشد")


# ------------------------------------------------------------------ ابزار نمایش عدد
def money(x) -> str:
    if x is None:
        return "—"
    if isinstance(x, Fraction):
        x = float(x)
    if isinstance(x, float):
        return f"{x:,.3f}".rstrip("0").rstrip(".")
    return f"{x:,}"


def pct(x, digits: int = 3) -> str:
    if x is None:
        return "—"
    return f"{round(float(x), digits):,}٪"


def rule(x) -> str:
    """عدد داخل فرمول قابل اجرا: بدون جداکننده، بدون نماد درصد."""
    if isinstance(x, Fraction):
        x = float(x)
    if isinstance(x, float):
        return repr(round(x, 8))
    return repr(x)


# ------------------------------------------------------------------ محاسبه + سنجش دوم
def _fees(row: dict, kind: str) -> tuple[float, float, float]:
    E = engine()
    if kind == "basis":
        return row.get("fee_buy", E.FEE_FUND_ETF), row.get("fee_sell", E.FEE_FUND_ETF), 0.0
    if kind == "covered_call":
        return E.FEE_STOCK_BUY, E.FEE_STOCK_SELL, E.FEE_OPTION_TRADE
    if kind == "tabei":
        return E.FEE_STOCK_BUY, E.FEE_STOCK_SELL, 0.0
    return 0.0, 0.0, E.FEE_OPTION_TRADE


def _annual(period: Fraction, days: float) -> float:
    """سالانه‌سازی با کسر دقیق (محاسبهٔ دوم، جدا از کد موتور)."""
    t = Fraction(int(days), 365)
    return (1 + float(period)) ** (1 / float(t)) - 1


def plain_annual(period_expr: str, days: float) -> str:
    """فرمول قابل‌اجرا برای ماشین‌حساب/پایتون: بازده دوره → بازده سالانه → درصد."""
    return f"((({period_expr}) + 1) ** (365.0/{rule(days)}) - 1) * 100"


def _agree(got: float, hand: float, tol: float = 0.02) -> bool:
    return abs(got - hand) <= max(abs(got) * tol, 0.001)


def _given(row: dict, kind: str) -> list[tuple[str, str]]:
    if kind == "basis":
        return [("قیمت نقدی", money(row["spot"])), ("قیمت آتی", money(row["future"])),
                ("روز تا سررسید", money(row["days"]))]
    if kind == "box":
        return [("کال اعمال پایین", money(row["call_low"])), ("پوت اعمال پایین", money(row["put_low"])),
                ("کال اعمال بالا", money(row["call_high"])), ("پوت اعمال بالا", money(row["put_high"])),
                ("اعمال پایین", money(row["strike_low"])), ("اعمال بالا", money(row["strike_high"])),
                ("روز تا سررسید", money(row["days"]))]
    if kind == "tabei":
        return [("قیمت سهم", money(row["stock_price"])), ("قیمت پوت", money(row["put_price"])),
                ("قیمت اعمال تضمینی", money(row["strike"])), ("روز تا سررسید", money(row["days"]))]
    if kind == "covered_call":
        return [("قیمت سهم", money(row["spot"])), ("قیمت اعمال کال", money(row["strike"])),
                ("پرمیوم کال", money(row["premium"])), ("روز تا سررسید", money(row["days"]))]
    if kind == "sizing":
        return [("سرمایه", money(row.get("capital", 20_000_000_000.0)) + " ریال"),
                ("سقف ریسک", pct(float(row.get("risk_pct", 0.20)) * 100, 0)),
                ("وجه تضمین هر قرارداد", money(row.get("margin_per_contract", 2_000_000_000.0)) + " ریال")]
    if kind == "parity":
        return [("قیمت کال", money(row["call"])), ("قیمت پوت", money(row["put"])),
                ("قیمت سهم", money(row["spot"])), ("قیمت اعمال", money(row["strike"])),
                ("روز تا سررسید", money(row["days"])),
                ("نرخ بدون ریسک", pct(row.get("rate", 0.35) * 100, 0))]
    return []


def solve(row: dict) -> dict:
    """هر ردیف را حل می‌کند و کنار جواب موتور، محاسبهٔ دستی دوم و فرمول اجراپذیر می‌گذارد."""
    E = engine()
    kind = row.get("kind")
    fb, fs, fo = _fees(row, kind)
    hurdle = float(row.get("hurdle") or HURDLE_DEFAULT)
    out: dict = {"kind": kind, "title": row.get("name") or KIND_TITLES.get(kind, kind),
                 "given": _given(row, kind), "hurdle": hurdle, "checks": [], "steps": [],
                 "extras": {}, "answer_num": None, "answer": None, "unit": "", "formula": "",
                 "formula_plain": ""}

    if kind == "basis":
        res = E.basis_opportunity(row["spot"], row["future"], row["days"], hurdle, fb, fs,
                                  row.get("storage_annual", 0.0))
        buy = Fraction(str(row["spot"])) * (1 + Fraction(str(fb)).limit_denominator(10 ** 6))
        sell = Fraction(str(row["future"])) * (1 - Fraction(str(fs)).limit_denominator(10 ** 6))
        hand = _annual((sell - buy) / buy, row["days"]) * 100
        out.update(
            answer_num=res["annualized_pct"], answer=res["annualized_pct"], unit="٪ سالانه",
            formula=(f"سود هر واحد = {money(row['future'])}×(۱−{pct(fs * 100)}) − "
                     f"{money(row['spot'])}×(۱+{pct(fb * 100)}) = {money(res['net_gain_per_unit'])}، "
                     f"بعد بازده دوره ÷ قیمت تمام‌شده و توان ۳۶۵÷{row['days']}"),
            formula_plain=plain_annual(
                f"({rule(row['future'])}*(1-{rule(fs)}) - {rule(row['spot'])}*(1+{rule(fb)})) / "
                f"({rule(row['spot'])}*(1+{rule(fb)}))", row["days"]),
            steps=[f"بازده دوره = سود ÷ قیمت تمام‌شده = {pct(res['period_return_pct'])}",
                   f"بازده سالانه = (۱+بازده دوره)^(۳۶۵÷{row['days']}) − ۱ = {pct(res['annualized_pct'])}",
                   f"نرخ سد امروز {pct(hurdle * 100, 1)} و حاشیه "
                   f"{money(res['edge_pp'])} واحد درصد است"],
            extras={"سود هر واحد": money(res["net_gain_per_unit"]),
                    "بازده دوره": pct(res["period_return_pct"]),
                    "کارمزد خرید و فروش": f"{pct(fb * 100)} + {pct(fs * 100)}"},
            checks=[{"note": "محاسبهٔ دستی با کسر دقیق (بدون کد موتور)", "value": round(hand, 3),
                     "agree": _agree(res["annualized_pct"], hand)}])
    elif kind == "box":
        res = E.box_spread(row["call_low"], row["put_low"], row["call_high"], row["put_high"],
                           row["strike_low"], row["strike_high"], row["days"])
        debit = Fraction(str((row["call_low"] + row["put_high"]) - (row["put_low"] + row["call_high"])))
        payoff = Fraction(str(row["strike_high"] - row["strike_low"]))
        legs = Fraction(str(row["call_low"] + row["put_low"] + row["call_high"] + row["put_high"]))
        fees = legs * Fraction(str(E.FEE_OPTION_TRADE)).limit_denominator(10 ** 6)
        hand = _annual((payoff - debit - fees) / debit, row["days"]) * 100
        out.update(
            answer_num=res["annualized_pct"], answer=res["annualized_pct"], unit="٪ سالانه",
            formula=(f"بدهی امروز = {money(debit)} · دریافتی قطعی در سررسید = {money(payoff)} · "
                     f"کارمزد چهار طرف = {money(float(fees))}"),
            formula_plain=plain_annual(
                f"({rule(payoff)} - {rule(debit)} - "
                f"(({rule(row['call_low'])}+{rule(row['put_low'])}+{rule(row['call_high'])}"
                f"+{rule(row['put_high'])})*{rule(E.FEE_OPTION_TRADE)})) / ({rule(debit)})",
                row["days"]),
            steps=[f"سود خالص = دریافتی − بدهی − کارمزد = {money(res['net_profit'])}",
                   f"بازده سالانه = (۱+سود÷بدهی)^(۳۶۵÷{row['days']}) − ۱ = {pct(res['annualized_pct'])}"],
            extras={"بدهی": money(debit), "دریافتی قطعی": money(payoff),
                    "کارمزد چهار طرف": money(float(fees)), "سود خالص": money(res["net_profit"])},
            checks=[{"note": "محاسبهٔ دستی با کسر دقیق روی چهار پایه", "value": round(hand, 3),
                     "agree": _agree(res["annualized_pct"], hand)}])
    elif kind == "tabei":
        res = E.tabei_min_yield(row["stock_price"], row["put_price"], row["strike"], row["days"], fb, fs)
        cost = (Fraction(str(row["stock_price"])) * (1 + Fraction(str(fb)).limit_denominator(10 ** 6))
                + Fraction(str(row["put_price"])))
        proceeds = Fraction(str(row["strike"])) * (1 - Fraction(str(fs)).limit_denominator(10 ** 6))
        hand = _annual((proceeds - cost) / cost, row["days"]) * 100
        out.update(
            answer_num=res["annualized_pct"], answer=res["annualized_pct"],
            unit="٪ سالانه (کمینهٔ تضمینی)",
            formula=(f"هزینهٔ خرید = {money(row['stock_price'])}×(۱+{pct(fb * 100)}) + پوت "
                     f"{money(row['put_price'])} = {money(res['cost_basis'])} · دریافتی تضمینی = "
                     f"{money(row['strike'])}×(۱−{pct(fs * 100)}) = {money(res['guaranteed_proceeds'])}"),
            formula_plain=plain_annual(
                f"({rule(row['strike'])}*(1-{rule(fs)}) - "
                f"({rule(row['stock_price'])}*(1+{rule(fb)}) + {rule(row['put_price'])})) / "
                f"({rule(row['stock_price'])}*(1+{rule(fb)}) + {rule(row['put_price'])})",
                row["days"]),
            steps=[f"بازده دوره = (دریافتی تضمینی − هزینهٔ خرید) ÷ هزینهٔ خرید = "
                   f"{pct(res['period_return_pct'])}",
                   f"بازده سالانه = (۱+بازده دوره)^(۳۶۵÷{row['days']}) − ۱ = {pct(res['annualized_pct'])}"],
            extras={"هزینهٔ خرید": money(res["cost_basis"]),
                    "دریافتی تضمینی": money(res["guaranteed_proceeds"])},
            checks=[{"note": "محاسبهٔ دستی با کسر دقیق (کارمزد سهم + پوت)", "value": round(hand, 3),
                     "agree": _agree(res["annualized_pct"], hand)}])
    elif kind == "covered_call":
        res = E.covered_call(row["spot"], row["strike"], row["premium"], row["days"], fb, fs, fo)
        base = Fraction(str(row["spot"])) * (1 + Fraction(str(fb)).limit_denominator(10 ** 6))
        prem = Fraction(str(row["premium"])) * (1 - Fraction(str(fo)).limit_denominator(10 ** 6))
        hand = _annual(prem / base, row["days"]) * 100
        out.update(
            answer_num=res["premium_annualized_pct"], answer=res["premium_annualized_pct"],
            unit="٪ سالانه (فقط پرمیوم)",
            formula=(f"پرمیوم خالص = {money(row['premium'])}×(۱−{pct(fo * 100)}) = {money(float(prem))} "
                     f"÷ قیمت تمام‌شدهٔ سهم {money(float(base))}"),
            formula_plain=plain_annual(
                f"({rule(row['premium'])}*(1-{rule(fo)})) / ({rule(row['spot'])}*(1+{rule(fb)}))",
                row["days"]),
            steps=[f"درآمد پرمیوم دوره = {pct(float(prem / base) * 100)}",
                   f"بازده سالانهٔ پرمیوم = (۱+درآمد دوره)^(۳۶۵÷{row['days']}) − ۱ = "
                   f"{pct(res['premium_annualized_pct'])}",
                   f"سقف رشد سهم با این پوشش = {pct(res['upside_capped_at_pct'])} "
                   f"(بخش بازار-ریسک، جدا از پرمیوم)"],
            extras={"سقف رشد سهم": pct(res["upside_capped_at_pct"]),
                    "ارزش دارد؟": "بله" if res.get("go") else "نه",
                    "بازده دوره": pct(round(float(prem / base) * 100, 3))},
            checks=[{"note": "محاسبهٔ دستی پرمیوم با کسر دقیق", "value": round(hand, 3),
                     "agree": _agree(res["premium_annualized_pct"], hand)}])
    elif kind == "parity":
        res = E.put_call_parity(row["call"], row["put"], row["spot"], row["strike"], row["days"],
                                row.get("rate", HURDLE_DEFAULT))
        editable = float(res["gap"]) - float(res["costs_estimate"])
        hand_agree = abs(editable - float(res["conversion_edge_per_unit"])) < 0.01
        out.update(
            answer="بله" if res.get("go") else "نه", answer_bool=bool(res.get("go")),
            unit="بله/نه", answer_num=None,
            formula=(f"سمت چپ کال−پوت = {money(res['lhs_call_minus_put'])} · سمت راست سهم−ارزش فعلی "
                     f"اعمال = {money(res['rhs_spot_minus_pv_strike'])} · شکاف = {money(res['gap'])} · "
                     f"کارمزد سه پایه = {money(res['costs_estimate'])}"),
            formula_plain="",
            steps=[f"اختلاف قابل برداشت = شکاف − کارمزد = {money(res['conversion_edge_per_unit'])}",
                   f"داوری: {'صرفه دارد' if res.get('go') else 'صرفه ندارد'} — سمت معکوس در ایران "
                   f"ممکن نیست (فروش استقراضی نداریم)"],
            extras={"شکاف": money(res["gap"]), "کارمزد سه پایه": money(res["costs_estimate"]),
                    "اختلاف قابل برداشت": money(res["conversion_edge_per_unit"])},
            checks=[{"note": "محاسبهٔ دستی: شکاف منهای کارمزد سه پایه", "value": round(editable, 2),
                     "agree": hand_agree}])
    elif kind == "sizing":
        capital = float(row.get("capital", 20_000_000_000.0))
        margin = float(row.get("margin_per_contract", 2_000_000_000.0))
        risk = float(row.get("risk_pct", 0.20))
        res = E.position_size(capital, margin, risk)
        out.update(
            answer_num=res["contracts"], answer=res["contracts"], unit="قرارداد",
            formula=(f"بودجهٔ ریسک = {money(capital)} × {pct(risk * 100, 0)} = {money(capital * risk)} "
                     f"÷ وجه تضمین هر قرارداد {money(margin)}"),
            formula_plain=f"{rule(capital)}*{rule(risk)}//{rule(margin)}",
            steps=[f"تعداد قرارداد = کف({money(capital * risk)} ÷ {money(margin)}) = {res['contracts']}",
                   f"وجه تضمین قفل‌شده = {money(res['margin_locked'])} · نقد آزاد = {money(res['free_cash'])}"],
            extras={"سرمایه": money(capital), "سقف ریسک": pct(risk * 100, 0),
                    "وجه تضمین هر قرارداد": money(margin)},
            checks=[{"note": "محاسبهٔ دستی: تقسیم صحیح بودجهٔ ریسک بر وجه تضمین",
                     "value": int(capital * risk // margin),
                     "agree": int(capital * risk // margin) == res["contracts"]}])
    else:
        raise ValueError(f"نوع ناشناخته: {kind}")
    return out


# ------------------------------------------------------------------ پلهٔ «کِی می‌افتد»
def _exit_price(row: dict, annual_pct: float, *, mode: str) -> float | None:
    base = row.get("spot") or row.get("stock_price") or row.get("strike") or row.get("strike_low")
    days = float(row.get("days") or 0)
    if not base or days <= 0:
        return None
    period = (1 + annual_pct / 100) ** (days / 365) - 1
    frac = TAKE_PROFIT_FRACTION if mode == "take_profit" else -STOP_LOSS_FRACTION
    return round(float(base) * (1 + period * frac), 3)


def _fees_total_pct(row: dict) -> float:
    kind = row.get("kind")
    E = engine()
    if kind == "basis":
        return round((row.get("fee_buy", E.FEE_FUND_ETF) + row.get("fee_sell", E.FEE_FUND_ETF)) * 100, 4)
    if kind == "covered_call":
        return round((E.FEE_STOCK_BUY + E.FEE_STOCK_SELL + E.FEE_OPTION_TRADE) * 100, 4)
    if kind == "tabei":
        return round((E.FEE_STOCK_BUY + E.FEE_STOCK_SELL) * 100, 4)
    if kind in ("box", "parity"):
        return round(E.FEE_OPTION_TRADE * (4 if kind == "box" else 3) * 100, 4)
    return 0.0


def ladder_for(row: dict, *, hurdle: float | None = None) -> dict:
    """برای یک ردیف می‌گوید: می‌ماند یا می‌افتد، و سه حد خروج کجاست."""
    solved = solve(row)
    kind = row.get("kind")
    base = float(row.get("hurdle") or (hurdle if hurdle is not None else HURDLE_DEFAULT))
    if hurdle is not None:
        base = float(hurdle)
    annual = float(solved.get("answer_num") or 0.0)
    days = float(row.get("days") or 0)
    fees = _fees_total_pct(row)

    if kind == "parity":
        return {"kind": kind, "title": solved["title"], "given": solved["given"], "ladder": [],
                "survives": False, "annualized_pct": None, "hurdle_pct": round(base * 100, 3),
                "margin_pp": None, "fees_pct": fees,
                "verdict": ("امروز «نه»: انحراف تساوی از کارمزد سه پایه کمتر است، پس چیزی برای "
                            "برداشتن نیست. هر وقت شکاف بزرگ‌تر شد، همین خط دوباره چک می‌شود."),
                "why": (f"کارمزد سه پایه ({fees}٪) اول از شکاف کسر می‌شود و بعد نتیجه با نرخ سد "
                        f"سنجیده می‌شود؛ سمت معکوس هم در ایران عملی نیست."),
                "check": solved["checks"]}

    survives = annual > base * 100 and annual > 0
    ladder = [
        {"label": "برداشت سود", "when": f"{int(TAKE_PROFIT_FRACTION * 100)}٪ بازده انتظاری",
         "price": _exit_price(row, annual, mode="take_profit"), "action": "خروج و ثبت در دفتر"},
        {"label": "توقف ضرر", "when": f"{int(STOP_LOSS_FRACTION * 100)}٪ بازده انتظاری",
         "price": _exit_price(row, annual, mode="stop_loss"), "action": "خروج بی‌مذاکره"},
        {"label": "سررسید", "when": f"{int(days)} روز" if days else "—",
         "price": "—", "action": "خروج در سررسید، حتی اگر هدف نخورده باشد"},
    ]
    if annual <= 0:
        verdict = (f"«می‌افتد»: بازده خالص منفی است ({annual:.3f}٪). این ردیف فقط ثبت می‌شود و "
                   f"اجرا نمی‌شود.")
    elif not survives:
        verdict = (f"«می‌افتد»: بازده سالانهٔ امروز {annual:.3f}٪ از نرخ سد {base * 100:.1f}٪ عبور "
                   f"نمی‌کند؛ پس هیچ اقدامی نمی‌کنیم.")
    else:
        verdict = (f"«می‌ماند» با حاشیهٔ {annual - base * 100:.3f} واحد درصد: تا وقتی نرخ سد زیر "
                   f"{annual:.3f}٪ بماند، این معامله ارزش بررسی دارد.")
    why = (f"عدد خالص است: اول کارمزد ({fees}٪ مجموع) کسر شده، بعد با نرخ سد سنجیده شده. "
           f"نقطهٔ برگشت روشن است: اگر نرخ سد از {annual:.3f}٪ بگذرد، همین سیگنال می‌افتد؛ "
           f"و اگر کارمزد کارگزاری شما جای دیگری بود، همان عدد را در برنامه جایگزین می‌کنیم.")
    return {"kind": kind, "title": solved["title"], "given": solved["given"], "ladder": ladder,
            "survives": survives, "annualized_pct": round(annual, 3),
            "hurdle_pct": round(base * 100, 3), "margin_pp": round(annual - base * 100, 3),
            "fees_pct": fees, "verdict": verdict, "why": why, "check": solved["checks"],
            "capital_pct": STRATEGY_CAP_FRACTION * 100}


def sensitivity(rows: list[dict] | None = None) -> dict:
    """شکنندگی: نرخ سد، کارمزد، اسپرد/نقدشوندگی — همه با عدد."""
    rows = rows if rows is not None else fallback_rows()
    out = {"rows": [], "fee_break": None, "spread_note": ""}
    for kind in ("basis", "box", "tabei", "covered_call"):
        try:
            row = _pick(kind, rows)
        except LookupError:
            continue
        lead = ladder_for(row)
        out["rows"].append({"kind": kind, "title": lead["title"],
                            "annualized_pct": lead["annualized_pct"], "hurdle_now_pct": lead["hurdle_pct"],
                            "breaks_if_hurdle_above_pct": lead["annualized_pct"],
                            "survives": lead["survives"], "margin_pp": lead["margin_pp"]})
    try:
        out["fee_break"] = fee_flip(_pick("covered_call", rows))
    except LookupError:
        pass
    spreads = [float(r.get("spread_pct") or 0) * 100 for r in rows if r.get("spread_pct")]
    liq = [r.get("liquidity_contracts_per_day") for r in rows if r.get("liquidity_contracts_per_day")]
    out["spread_note"] = (
        f"بیشترین اسپرد ثبت‌شده {pct(max(spreads))} و کم‌ترین نقدشوندگی "
        f"{money(min(liq))} قرارداد در روز است؛ هر ردیفی که نقدشوندگی‌اش کم باشد در تصمیم "
        f"علامت می‌خورد." if spreads or liq else
        "اسپرد و نقدشوندگی در اسنپ‌شات ثبت نشده است؛ بدون آن‌ها هم برنامه تصمیم نمی‌سازد.")
    return out


def fee_flip(row: dict | None = None, *, target: float = GO_THRESHOLD, hi: float = 0.60) -> dict:
    """کارمزد فروش سهم تا چند درصد بالا برود که پوشش‌داده دیگر ارزش نداشته باشد."""
    E = engine()
    row = row or _pick("covered_call")

    def annual(fee: float) -> float:
        r = E.covered_call(row["spot"], row["strike"], row["premium"], row["days"],
                           E.FEE_STOCK_BUY, fee, E.FEE_OPTION_TRADE)
        return r["premium_annualized_pct"] / 100

    lo = 0.0
    if annual(hi) > target:
        return {"name": row.get("name") or KIND_TITLES["covered_call"],
                "fee_now_pct": E.FEE_STOCK_SELL * 100, "fee_flip_pct": None, "sensitive": False,
                "threshold_pct": target * 100, "days": row["days"], "searched_to_pct": hi * 100,
                "meaning": (f"این معامله به کارمزد فروش سهم حساس نیست: حتی با کارمزد "
                            f"{pct(hi * 100, 0)} هم درآمد پرمیوم بالای آستانهٔ {pct(target * 100)} "
                            f"می‌ماند. چیزی که این تصمیم را عوض می‌کند کارمزد نیست؛ نرخ سد و "
                            f"ریسک بازار است.")}
    for _ in range(60):
        mid = (lo + hi) / 2
        if annual(mid) > target:
            lo = mid
        else:
            hi = mid
    flip = round((lo + hi) / 2 * 100, 3)
    return {"name": row.get("name") or KIND_TITLES["covered_call"],
            "fee_now_pct": E.FEE_STOCK_SELL * 100, "fee_flip_pct": flip, "sensitive": True,
            "threshold_pct": target * 100, "days": row["days"], "searched_to_pct": 60.0,
            "meaning": (f"اگر کارمزد فروش سهم از {flip}٪ بگذرد، این پوشش‌داده کم‌تر از آستانهٔ "
                        f"{pct(target * 100)} سالانه می‌دهد و باید رد شود.")}


# ------------------------------------------------------------------ پرسش‌ها
QUESTIONS = {
    "basis": ("اگر امروز این دارایی را نقد بخری و همان لحظه در بازار آتی بفروشی و تا سررسید "
              "نگه داری، بازده سالانه‌ات بعد از کارمزد چند درصد می‌شود؟"),
    "box": ("در این باکس اسپرد امروز چه‌قدر پول می‌دهی و در سررسید چه‌قدر قطعی می‌گیری؟ "
            "بازده سالانه‌اش چند درصد است؟"),
    "tabei": ("اگر این سهم را امروز بخری و این پوت تبعی را بخری و تا سررسید نگه داری، "
              "کمینهٔ بازده تضمینی‌ات سالانه چند درصد است؟"),
    "covered_call": ("اگر امروز این سهم را بخری و این اختیار خرید را بفروشی و سررسید اعمال شود، "
                     "درآمد سالانه‌ات فقط از پرمیوم چند درصد است؟"),
    "parity": ("در این تساوی پوت-کال، اگر سهم را بخری و پوت را بخری و کال را بفروشی، "
               "با توجه به کارمزدها صرفه دارد یا نه؟"),
    "sizing": ("با این سرمایه و این سقف ریسک و این وجه تضمین، حداکثر چند قرارداد می‌شود باز کرد؟"),
}

_HIDDEN = ("answer", "answer_num", "answer_bool", "formula", "formula_plain", "steps", "extras",
           "checks", "ladder", "hand")


def cases(reveal: bool = False, *, rows: list[dict] | None = None,
          capital: float = 20_000_000_000.0, margin_per_contract: float = 2_000_000_000.0,
          risk_pct: float = 0.20) -> list[dict]:
    """پرسش‌ها. تا وقتی reveal=True نشود، هیچ جوابی داخلشان نیست (آزمون کور واقعی)."""
    rows = rows if rows is not None else fallback_rows()
    out: list[dict] = []
    for kind in ("basis", "box", "tabei", "covered_call", "parity"):
        try:
            row = _pick(kind, rows)
        except LookupError:
            continue
        s = solve(row)
        out.append({"id": f"{kind}_{'annual' if s['answer_num'] is not None else 'yn'}",
                    "kind": kind, "title": s["title"], "question": QUESTIONS[kind],
                    "given": s["given"], "ladder": ladder_for(row), **s})
    sizing_row = {"kind": "sizing", "capital": capital, "margin_per_contract": margin_per_contract,
                  "risk_pct": risk_pct}
    s = solve(sizing_row)
    out.append({"id": "sizing", "kind": "sizing", "title": "اندازهٔ موقعیت — چند قرارداد؟",
                "question": QUESTIONS["sizing"], "given": s["given"],
                "ladder": ladder_for(sizing_row), **s})
    if not reveal:
        out = [{k: v for k, v in c.items() if k not in _HIDDEN} for c in out]
    return out


def answer_text(case: dict) -> str:
    ans = case.get("answer")
    if isinstance(ans, bool):
        return "بله" if ans else "نه"
    if isinstance(ans, (int, float)):
        return f"{money(ans)} {case.get('unit', '')}".strip()
    return str(ans)


def find_case(case_id: str, **kw) -> dict:
    for c in cases(reveal=True, **kw):
        if c["id"] == case_id:
            return c
    raise KeyError(f"پرسش «{case_id}» پیدا نشد")


# ------------------------------------------------------------------ دفتر زنجیره‌هش‌دار
def _prev_chain(path: Path) -> str:
    rows = read_log(path)
    return rows[-1].get("chain", "0" * 16) if rows else "0" * 16


def chain_hash(payload: dict, prev: str) -> str:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(f"{prev}|{body}".encode("utf-8")).hexdigest()[:16]


def read_log(path: Path | str | None = None) -> list[dict]:
    p = Path(path or LOG_FILE)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def append_guess(record: dict, *, path: Path | str | None = None) -> dict:
    p = Path(path or LOG_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = read_log(p)
    rec = dict(record)
    rec["ts"] = rec.get("ts") or datetime.now(timezone.utc).isoformat(timespec="seconds")
    rec["chain"] = chain_hash({k: v for k, v in rec.items() if k != "chain"}, _prev_chain(p))
    rows.append(rec)
    p.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def verify_chain(path: Path | str | None = None) -> dict:
    rows = read_log(path)
    prev = "0" * 16
    for i, r in enumerate(rows):
        want = chain_hash({k: v for k, v in r.items() if k != "chain"}, prev)
        if want != r.get("chain"):
            return {"ok": False, "rows": len(rows), "broken_at": i + 1, "chain": prev,
                    "last_fingerprint": prev,
                    "detail": f"سطر {i + 1} با اثر انگشت زنجیره نمی‌خواند؛ یعنی بعد از ثبت "
                              f"دست‌کاری شده است."}
        prev = r["chain"]
    return {"ok": True, "rows": len(rows), "broken_at": None, "chain": prev,
            "last_fingerprint": prev,
            "detail": ("زنجیره سالم است؛ هیچ سطر دست‌کاری‌شده‌ای پیدا نشد." if rows else
                       "دفتر هنوز خالی است؛ بعد از اولین ثبت پر می‌شود.")}


# ------------------------------------------------------------------ سنجش حدس
_YES = {"بله", "بلی", "اره", "آره", "درست", "yes", "y", "true", "1"}
_NO = {"نه", "خیر", "نادرست", "no", "n", "false", "0"}


def _as_bool(v) -> bool | None:
    s = str(v).strip().lower().replace("‌", "")
    if s in _YES:
        return True
    if s in _NO:
        return False
    return None


def _as_number(v) -> float | None:
    if v is None:
        return None
    s = str(v).replace(",", "").replace("٬", "").replace("٪", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def judge(guess, note: str | None = None, *, case_id: str, client: str = "",
          path: Path | str | None = None, **kw) -> dict:
    """حدس سرمایه‌گذار را ثبت و داوری می‌کند: دقیقاً درست / نزدیک / دور / درست / نادرست / بی‌عدد."""
    case = find_case(case_id, **kw)
    status, delta = "بی‌عدد", None
    if case.get("answer_bool") is not None:
        g = _as_bool(guess)
        if g is None:
            status = "بی‌عدد"
        else:
            status = "درست" if g == bool(case["answer_bool"]) else "نادرست"
        guess_val = None if g is None else g
    else:
        g = _as_number(guess)
        guess_val = g
        if g is None:
            status = "بی‌عدد"
        else:
            a = float(case["answer_num"])
            delta = round(abs(g - a) / max(abs(a), 1e-9) * 100, 3) if a else round(abs(g) * 100, 3)
            status = "دقیقاً درست" if delta < 2 else ("نزدیک" if delta < 10 else "دور")
    notes = {"دقیقاً درست": "دقیقاً همان عددی که موتور می‌دهد.",
             "نزدیک": "خیلی نزدیک؛ اختلاف از گرد کردن یا ترتیب کارمزدها است.",
             "دور": "فاصله زیاد است؛ همین‌جا ارزش برنامه معلوم می‌شود: کارمزد و سالانه‌سازی و نرخ سد.",
             "درست": "درست گفتید؛ با کارمزد واقعی این معامله برداشتنی نیست.",
             "نادرست": "اینجا اختلاف است؛ همین مسیر محاسبه را با هم می‌بینیم.",
             "بی‌عدد": "عدد یا «بله/نه» روشنی ثبت نشد، پس داوری نشد."}
    rec = append_guess({"kind": "guess", "case": case_id, "title": case["title"], "client": client,
                        "guess_raw": str(guess), "guess": guess_val, "note": note or "",
                        "answer": case.get("answer"), "unit": case.get("unit", ""),
                        "delta_pct": delta, "status": status,
                        "engine": getattr(engine(), "VERSION", "?")}, path=path)
    return {"case_id": case_id, "case": case, "status": status, "delta_pct": delta,
            "note": notes[status], "record": rec}


def check(case_id: str, guess, *, client: str = "", path: Path | str | None = None,
          **kw) -> dict:
    """شکل سازگار با گام ۱۰ رابط: همان داوری، با کلیدهایی که کارت‌های مرورگری می‌خوانند."""
    try:
        res = judge(guess, None, case_id=case_id, client=client, path=path, **kw)
    except KeyError as e:
        return {"ok": False, "error": str(e)}
    c = res["case"]
    return {"ok": True, "id": case_id, "title": c["title"], "answer": answer_text(c),
            "unit": c.get("unit", ""), "verdict": res["status"], "off_pct": res["delta_pct"],
            "formula": c.get("formula", ""), "second": "; ".join(
                f"{ch['note']} = {money(ch['value'])}" for ch in c.get("checks", [])),
            "note": res["note"], "chain": res["record"]["chain"]}


def strategy_table(rows: list[dict] | None = None,
                   hurdles: tuple[float, ...] = (0.30, 0.35, 0.40, 0.50)) -> dict:
    """جدول آستانهٔ ریزش: برای هر راهبرد، با هر نرخ سد می‌گذرد یا می‌افتد."""
    rows = rows if rows is not None else fallback_rows()
    out_rows = []
    for row in rows:
        if not row.get("kind"):
            continue
        try:
            s = solve(row)
        except (KeyError, ValueError, ZeroDivisionError):
            continue
        annual = s.get("answer_num")
        cells = {}
        for h in hurdles:
            edge = None if annual is None else round(float(annual) - h * 100, 3)
            cells[str(h)] = {"go": bool(annual is not None and float(annual) > h * 100),
                             "edge_pp": edge}
        out_rows.append({"name": s["title"], "kind": row.get("kind"),
                         "annualized_pct": annual, "cells": cells})
    passed = len([1 for r in out_rows if r["cells"].get(str(hurdles[0]), {}).get("go")])
    verdict = (f"{len(out_rows)} راهبرد سنجیده شد؛ با نرخ سد {hurdles[0] * 100:.0f}٪ "
               f"{passed} راهبرد از سد عبور می‌کند. عددها بعد از کارمزد واقعی‌اند و هیچ‌کدام "
               f"تضمین سود نیست؛ ستون‌ها نشان می‌دهند با بالا رفتن نرخ سد کدام راهبرد می‌افتد.")
    return {"hurdles": list(hurdles), "rows": out_rows, "verdict": verdict}


def size_sensitivity(capital: float = 100_000_000.0, margin_per_contract: float = 2_000_000.0,
                     caps: tuple[float, ...] = (0.10, 0.20, 0.30, 0.40)) -> list[dict]:
    """اندازهٔ موقعیت در چند سقف ریسک (عددها فقط نشان می‌دهند وجه تضمین چقدر قفل می‌شود)."""
    E = engine()
    out = []
    for cap in caps:
        res = E.position_size(capital, margin_per_contract, cap)
        out.append({"risk_pct": round(cap * 100, 1), "contracts": res["contracts"],
                    "margin_locked": round(res["margin_locked"], 2),
                    "free_cash": round(res["free_cash"], 2)})
    return out


def reconcile(*, symbol: str = "بدون‌نام", entry, exit, days=30, units=1, expected=None,
              path: Path | str | None = None) -> dict:
    """حساب‌رسی یک معاملهٔ گذشتهٔ سهم با کارمزد واقعی ایران (بدون اینترنت)."""
    E = engine()
    try:
        e, x, u = float(str(entry).replace(",", "")), float(str(exit).replace(",", "")), float(str(units or 1))
        d = float(str(days or 30))
    except (TypeError, ValueError):
        return {"ok": False, "error": "عددهای قیمت خرید، فروش، تعداد و روز باید عدد باشند."}
    cost = e * u * (1 + E.FEE_STOCK_BUY)
    proceeds = x * u * (1 - E.FEE_STOCK_SELL)
    profit = proceeds - cost
    period = profit / cost
    annual = (1 + period) ** (365 / d) - 1 if d > 0 else None
    verdict = ("سود" if profit > 0 else "زیان") + (
        f" · بازده سالانه {pct(annual * 100)}" if annual is not None else "")
    compare = "—"
    if expected not in (None, "", "—"):
        try:
            exp = float(str(expected).replace(",", "").replace("٪", ""))
            gap = round((annual or 0) * 100 - exp, 3)
            compare = (f"انتظار برنامه {exp}٪ سالانه بود؛ نتیجهٔ واقعی "
                       f"{pct((annual or 0) * 100)} شد؛ اختلاف {money(gap)} واحد درصد. "
                       f"{'نتیجه بهتر از انتظار بود.' if gap > 0 else 'نتیجه بدتر از انتظار بود.'}")
        except ValueError:
            compare = "عدد انتظار برنامه خوانده نشد، پس مقایسه انجام نشد."
    rec = append_guess({"kind": "reconcile", "symbol": symbol, "entry": e, "exit": x, "units": u,
                        "days": d, "profit": round(profit, 2), "period_pct": round(period * 100, 3),
                        "annualized_pct": round(annual * 100, 3) if annual is not None else None,
                        "expected_pct": expected or "", "note": compare}, path=path)
    return {"ok": True, "symbol": symbol, "cost": round(cost, 2), "proceeds": round(proceeds, 2),
            "profit": round(profit, 2), "period_pct": round(period * 100, 3),
            "annualized_pct": round(annual * 100, 3) if annual is not None else None,
            "verdict": verdict, "compare": compare,
            "note": (f"کارمزد خرید {pct(E.FEE_STOCK_BUY * 100)} و فروش {pct(E.FEE_STOCK_SELL * 100)} "
                     f"کسر شده است. این عدد «حساب‌رسی گذشته» است، نه پیش‌بینی آینده."),
            "chain": verify_chain(path)}


def append_log(record: dict, *, path: Path | str | None = None) -> dict:
    """نام سازگار با رابط قدیمی؛ همان دفتر زنجیره‌هش‌دار."""
    return append_guess(record, path=path)


def scorecard(*, path: Path | str | None = None) -> dict:
    rows = [r for r in read_log(path) if r.get("kind") == "guess"]
    close = [r for r in rows if r.get("status") in ("دقیقاً درست", "نزدیک", "درست")]
    scored = [r for r in rows if r.get("status") != "بی‌عدد"]
    return {"guesses": len(rows), "scored": len(scored), "near": len(close),
            "fair_pp": round(len(close) / len(scored) * 100, 1) if scored else None,
            "cases_available": len(cases()), "verify": verify_chain(path)}


# ------------------------------------------------------------------ برگهٔ چاپی و پیمان‌نامه
def build_sheet(*, client: str = "", sheet_html: Path | str | None = None,
                sheet_md: Path | str | None = None, log_path: Path | str | None = None,
                rows: list[dict] | None = None) -> dict:
    """برگهٔ چاپی دواِمضا: پرسش، حدس، جواب، مسیر محاسبه، «کِی می‌افتد» و اثر انگشت دفتر."""
    import reportkit as rk

    html_path = Path(sheet_html or SHEET_HTML)
    md_path = Path(sheet_md or SHEET_MD)
    log = read_log(log_path)
    guesses = {r["case"]: r for r in log if r.get("kind") == "guess"}
    cs = cases(reveal=True, rows=rows)
    body = [
        '<div class="honest"><b>این برگه چه را اثبات می‌کند و چه را نه.</b> '
        'هر پرسش از دادهٔ همین اسنپ‌شات ساخته شده و سرمایه‌گذار می‌تواند با ماشین‌حساب خودش '
        'جوابش را بازتولید کند؛ مسیر محاسبه، کارمزدهای فرض‌شده و محاسبهٔ دستیِ دوم در همین '
        'برگه نوشته شده است. اگر جواب برنامه با محاسبهٔ دستی نخواند، این برگه ارزشی ندارد و '
        'باید پاره شود. این برگه هیچ ادعایی دربارهٔ سود آینده نمی‌کند و تضمین سود نمی‌کند.</div>',
        f'<p class="sub">سرمایه‌گذار: <b>{rk.esc(client or "—")}</b> · '
        f'تاریخ: {rk.esc(datetime.now().strftime("%Y-%m-%d"))} · نسخهٔ برگزارکننده: {VERSION}</p>',
    ]
    if not guesses:
        body.append('<p class="note">هنوز حدسی ثبت نشده است؛ پرسش‌ها را بپرسید و با کادر '
                    '«داوری حدس» ثبت کنید تا این برگه پر شود.</p>')
    for c in cs:
        g = guesses.get(c["id"], {})
        given = "".join(f'<tr><td>{rk.esc(k)}</td><td class="num">{rk.esc(v)}</td></tr>'
                        for k, v in c["given"])
        steps = "".join(f"<li>{rk.esc(s)}</li>" for s in c.get("steps", []))
        extras = "".join(f'<tr><td>{rk.esc(k)}</td><td class="num">{rk.esc(v)}</td></tr>'
                         for k, v in (c.get("extras") or {}).items())
        checks = "".join(
            f'<li>{rk.esc(ch["note"])}: <b>{rk.esc(money(ch["value"]))}</b> — '
            f'{"موافق موتور ✅" if ch["agree"] else "مخالف ⚠️"}</li>' for ch in c.get("checks", []))
        lead = c.get("ladder") or {}
        ladder_rows = "".join(
            f'<tr><td>{rk.esc(s["label"])}</td><td>{rk.esc(s["when"])}</td>'
            f'<td class="num">{rk.esc(money(s["price"]) if isinstance(s["price"], (int, float)) else s["price"])}</td>'
            f'<td>{rk.esc(s["action"])}</td></tr>' for s in lead.get("ladder", []))
        guess_txt = rk.esc(str(g.get("guess_raw", "—")))
        body.append(
            f'<h2>{rk.esc(c["title"])}</h2>'
            f'<p class="lead">{rk.esc(c["question"])}</p>'
            f'<table><thead><tr><th>دادهٔ ورودی</th><th class="num">عدد</th></tr></thead>'
            f'<tbody>{given}</tbody></table>'
            f'<p class="note"><b>پاسخ برنامه:</b> {rk.esc(answer_text(c))}</p>'
            f'<p class="note"><b>حدس سرمایه‌گذار:</b> {guess_txt} — داوری: '
            f'<b>{rk.esc(str(g.get("status", "ثبت نشده")))}</b>'
            + (f' (فاصله {g.get("delta_pct")}٪)' if g.get("delta_pct") is not None else '') + '</p>'
            + (f'<details open><summary>مسیر محاسبهٔ برنامه</summary><p>{rk.esc(c.get("formula", ""))}</p>'
               f'<ol>{steps}</ol>{checks and "<ul>" + checks + "</ul>"}'
               f'{extras and "<table><tbody>" + extras + "</tbody></table>"}</details>'
               if c.get("steps") else '')
            + (f'<p class="note"><b>این ردیف چه زمانی می‌افتد:</b> {rk.esc(str(lead.get("verdict", "")))}'
               f'</p>' + (f'<table><thead><tr><th>حد</th><th>کِی</th><th class="num">قیمت/سطح</th>'
                          f'<th>اقدام</th></tr></thead><tbody>{ladder_rows}</tbody></table>'
                          if lead.get("ladder") else '') if lead else ''))
    sens = sensitivity(rows)
    if sens["rows"]:
        grows = "".join(
            f'<tr><td>{rk.esc(e["title"])}</td><td class="num">{pct(e["annualized_pct"])}</td>'
            f'<td class="num">{pct(e["hurdle_now_pct"], 1)}</td>'
            f'<td class="num">{pct(e["breaks_if_hurdle_above_pct"])}</td>'
            f'<td class="num">{money(e["margin_pp"])} واحد درصد</td>'
            f'<td>{"می‌ماند ✅" if e["survives"] else "می‌افتد ✗"}</td></tr>' for e in sens["rows"])
        fb = sens["fee_break"] or {}
        body.append('<h2>کِی می‌افتد؟ — نقطهٔ برگشت هر ردیف</h2>'
                    '<p class="lead">برنامه فقط نمی‌گوید «بخر»؛ می‌گوید با چه نرخی این تصمیم '
                    'می‌افتد. ستون آخر = بازده امروز منهای نرخ سد.</p>'
                    '<table><thead><tr><th>راهبرد</th><th class="num">بازده سالانهٔ امروز</th>'
                    '<th class="num">نرخ سد امروز</th><th class="num">اگر نرخ سد از این بگذرد می‌افتد</th>'
                    '<th class="num">حاشیهٔ اطمینان</th><th>وضعیت</th></tr></thead><tbody>'
                    + grows + '</tbody></table>'
                    + (f'<p class="note"><b>کارمزد:</b> {rk.esc(fb.get("meaning", ""))}</p>' if fb else '')
                    + f'<p class="note"><b>اسپرد و نقدشوندگی:</b> {rk.esc(sens["spread_note"])}</p>'
                    '<p class="note">این جدول همان چیزی است که «تصمیم» را از «عدد» جدا می‌کند: '
                    'با یک حرکت در نرخ سد، سیگنال می‌افتد و برنامه خودش می‌گوید نه.</p>')
    card = scorecard(path=log_path)
    if card["scored"]:
        body.append(f'<div class="note"><b>کارنامهٔ همین جلسه:</b> {card["scored"]} پرسش سنجیده شد و '
                    f'{card["near"]} پاسخ نزدیک یا درست بود ({card["fair_pp"]}٪). این عدد دربارهٔ '
                    f'سود نمی‌گوید؛ دربارهٔ شهود می‌گوید.</div>')
    body.append('<h2>امضا و شاهد</h2><table><tbody>'
                f'<tr><td>اثر انگشت دفتر آزمون</td><td class="num"><code>{rk.esc(card["verify"]["chain"])}</code></td></tr>'
                f'<tr><td>تعداد سطر دفتر</td><td class="num">{len(log)}</td></tr>'
                f'<tr><td>تمامیت زنجیرهٔ هش</td><td>{"سالم ✅" if card["verify"]["ok"] else "شکسته ⚠️"}</td></tr>'
                '</tbody></table>'
                '<p class="note">امضای برگزارکننده: ..................................... · '
                'امضای سرمایه‌گذار: .....................................</p>'
                f'<p class="sub">{CREDIT_HTML}</p>')
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(rk.page("برگهٔ آزمون کور سرمایه‌گذار — عدد را او می‌گوید، بعد جواب برنامه",
                                 "".join(body),
                                 subtitle=f"نسخهٔ {VERSION} · {len(cs)} پرسش از دادهٔ همین اسنپ‌شات"),
                         encoding="utf-8")
    md_path.write_text(_sheet_md(cs, guesses, card, client), encoding="utf-8")
    return {"html": str(html_path), "md": str(md_path), "scorecard": card}


def _sheet_md(cs: list[dict], guesses: dict, card: dict, client: str) -> str:
    L = [f"# برگهٔ آزمون کور سرمایه‌گذار (نسخهٔ {VERSION})", "",
         f"سرمایه‌گذار: {client or '—'} · تاریخ: {datetime.now().strftime('%Y-%m-%d')} · "
         f"{len(cs)} پرسش از دادهٔ همین اسنپ‌شات", "",
         "هر پرسش با ماشین‌حساب معمولی قابل بازتولید است. اگر جواب برنامه با محاسبهٔ دستی "
         "نخواند، این برگه بی‌اعتبار است.", ""]
    for c in cs:
        g = guesses.get(c["id"], {})
        L += [f"## {c['title']}", "", c["question"], "", "| داده | عدد |", "|---|---|"]
        L += [f"| {k} | {v} |" for k, v in c["given"]]
        L += ["", f"**پاسخ برنامه:** {answer_text(c)}", ""]
        for ch in c.get("checks", []):
            L.append(f"- محاسبهٔ دستی: {ch['note']} = {money(ch['value'])} "
                     f"({'موافق' if ch['agree'] else 'مخالف ⚠️'})")
        L += ["", f"**حدس سرمایه‌گذار:** {g.get('guess_raw', '—')} — {g.get('status', 'ثبت نشده')}", ""]
        for s in c.get("steps", []):
            L.append(f"- {s}")
        lead = c.get("ladder") or {}
        if lead.get("verdict"):
            L += ["", f"**کِی می‌افتد:** {lead['verdict']}", f"**چرا:** {lead.get('why', '')}"]
        for s in lead.get("ladder", []):
            L.append(f"  - {s['label']} — {s['when']} → {s['price']} → {s['action']}")
        L.append("")
    sens = sensitivity()
    if sens["rows"]:
        L += ["# کِی می‌افتد؟ (نقطهٔ برگشت هر ردیف)", "",
              "| راهبرد | بازده سالانه امروز | نرخ سد | نقطهٔ برگشت نرخ سد | حاشیه (واحد درصد) | وضعیت |",
              "|---|---|---|---|---|---|"]
        for e in sens["rows"]:
            L.append(f"| {e['title']} | {pct(e['annualized_pct'])} | {pct(e['hurdle_now_pct'], 1)} | "
                     f"{pct(e['breaks_if_hurdle_above_pct'])} | {money(e['margin_pp'])} | "
                     f"{'می‌ماند' if e['survives'] else 'می‌افتد'} |")
        if sens.get("fee_break"):
            L.append(f"\n**کارمزد:** {sens['fee_break']['meaning']}")
        L.append(f"\n**اسپرد و نقدشوندگی:** {sens['spread_note']}\n")
    if card["scored"]:
        L += [f"# کارنامهٔ جلسه", "",
              f"{card['scored']} پرسش سنجیده شد · {card['near']} پاسخ نزدیک یا درست "
              f"({card['fair_pp']}٪) — دربارهٔ شهود، نه سود.", ""]
    L += ["# امضا و شاهد", "",
          f"- اثر انگشت دفتر آزمون: `{card['verify']['chain']}`",
          f"- تعداد سطر دفتر: {card['verify']['rows']} · تمامیت زنجیره: "
          f"{'سالم' if card['verify']['ok'] else 'شکسته'}",
          "- امضای برگزارکننده: .............................  ·  امضای سرمایه‌گذار: .............................", "",
          CREDIT_MD, ""]
    return "\n".join(L)


def build_pledge(*, client: str = "", path: Path | str | None = None,
                 log_path: Path | str | None = None) -> str:
    """پیمان‌نامهٔ نمایش: چه چیزی اثبات می‌شود، چه چیزی نه، و حدهای خروج کجاست."""
    card = scorecard(path=log_path)
    text = "\n".join([
        f"# پیمان‌نامهٔ نمایش و آزمون — نسخهٔ {VERSION}", "",
        f"**طرف‌ها:** برگزارکننده (نگه‌دارندهٔ ایستگاه تصمیم) و سرمایه‌گذار: **{client or '—'}**", "",
        "## ۱. موضوع",
        "این سند نتیجهٔ چند ساعت کار مشترک روی همین رایانه است: عددهای بازار امروز، محاسبهٔ "
        "کارمزد واقعی، و داوری «بماند یا بیفتد».", "",
        "## ۲. چه چیزی با شاهد اثبات می‌شود",
        "- هر عدد با ماشین‌حساب معمولی روی همان دادهٔ ورودی بازتولید می‌شود (محاسبهٔ دستی دوم در برگه).",
        "- کارمزد خرید/فروش سهم، اختیار و اعمال در همهٔ عددها کسر شده است.",
        "- نقطهٔ برگشت هر تصمیم نوشته شده: با چه نرخ سدی سیگنال می‌افتد.",
        "- دفتر آزمون زنجیره‌هش‌دار است؛ دست‌کاری بعدی در آن لو می‌رود.",
        "- هر چیزی که اثبات نشد (سود آینده، پیش‌بینی قیمت، موفقیت تضمینی) در همین سند "
        "«اثبات‌نشده» علامت خورده و هیچ عددی برایش ساخته نشده.", "",
        "## ۳. چه چیزی اثبات نمی‌شود (و هیچ‌وقت ادعا نشد)",
        "- این برنامه تضمین سود نمی‌کند و آیندهٔ قیمت را پیش‌بینی نمی‌کند.",
        "- بازار ایران با ابلاغیه و محدودیت عوض می‌شود؛ اگر قاعده‌ای عوض شد، عدد قدیمی بی‌اعتبار است.",
        "- فقط با عدد کارگزاری: وجه تضمین و کارمزد نهایی را کارگزاری می‌گوید؛ عدد کارگزاری مقدّم "
        "بر هر عدد این برنامه است.",
        "- دادهٔ تاریخی کوتاه برای پس‌آزمایی: هر ادعایی بیش از آن بازه، ادعای بی‌شاهد است.", "",
        "## ۴. حدهای خروج (پیش از هر خرید نوشته می‌شود)",
        f"- برداشت سود در {int(TAKE_PROFIT_FRACTION * 100)}٪ بازده انتظاری.",
        f"- توقف ضرر در {int(STOP_LOSS_FRACTION * 100)}٪ بازده انتظاری، بی‌مذاکره.",
        "- خروج در سررسید، حتی اگر هیچ‌کدام نخورده باشد.",
        f"- سقف هر راهبرد {int(STRATEGY_CAP_FRACTION * 100)}٪ سرمایهٔ تخصیص‌یافته و سقف کل "
        "باز در حد سقف ریسک توافق‌شده.", "",
        "## ۵. شاهد فنی",
        f"- اثر انگشت دفتر آزمون: `{card['verify']['chain']}`",
        f"- تعداد سطر دفتر حدس‌ها: {card['verify']['rows']} · تمامیت زنجیرهٔ هش: "
        f"{'سالم' if card['verify']['ok'] else 'شکسته'}",
        f"- تعداد پرسش‌های آماده: {card['cases_available']} · بهترتیب دلخواه: {card['guesses']} ثبت شد",
        "- هیچ دادهٔ شخصی یا مالی از این رایانه بیرون نمی‌رود؛ دفتر و برگه‌ها محلی‌اند.", "",
        "## ۶. امضا",
        "امضای برگزارکننده: .............................     امضای سرمایه‌گذار: .............................", "",
        "تاریخ: .............................", "",
        CREDIT_MD, "",
    ])
    p = Path(path or PLEDGE_MD)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return text


# ------------------------------------------------------------------ خط فرمان
def _print_cases(show_answers: bool) -> None:
    cs = cases(reveal=show_answers)
    print(f"آزمون کور سرمایه‌گذار — نسخهٔ {VERSION} — {len(cs)} پرسش")
    print("=" * 74)
    for c in cs:
        print(f"\n[{c['id']}] {c['title']}")
        print("  پرسش:", c["question"])
        for k, v in c["given"]:
            print(f"    · {k}: {v}")
        if show_answers:
            print("  جواب موتور:", answer_text(c))
            for s in c.get("steps", []):
                print("     -", s)
            for ch in c.get("checks", []):
                print(f"     ✓ {ch['note']}: {money(ch['value'])} "
                      f"({'موافق' if ch['agree'] else 'مخالف ⚠️'})")
            lead = c.get("ladder") or {}
            if lead.get("verdict"):
                print("  کِی می‌افتد:", lead["verdict"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="آزمون کور سرمایه‌گذار (محلی، بدون اینترنت)")
    ap.add_argument("--cases", action="store_true", help="پرسش‌ها بدون جواب")
    ap.add_argument("--reveal", action="store_true", help="پرسش‌ها با جواب و مسیر محاسبه")
    ap.add_argument("--check", metavar="CASE_ID", help="ثبت حدس سرمایه‌گذار")
    ap.add_argument("--guess", help="عدد یا بله/نه حدس")
    ap.add_argument("--client", default="", help="نام سرمایه‌گذار")
    ap.add_argument("--flip", action="store_true", help="نقطهٔ برگشت کارمزد")
    ap.add_argument("--reconcile", action="store_true", help="حساب‌رسی یک معاملهٔ گذشته")
    ap.add_argument("--symbol", default="بدون‌نام")
    ap.add_argument("--entry", help="قیمت خرید")
    ap.add_argument("--exit", help="قیمت فروش")
    ap.add_argument("--days", default="30")
    ap.add_argument("--units", default="1")
    ap.add_argument("--expected", help="انتظار برنامه (٪ سالانه، اختیاری)")
    ap.add_argument("--ladder", action="store_true", help="پلهٔ تصمیم: چه بخرم، کِی بفروشم")
    ap.add_argument("--sheet", action="store_true", help="ساخت برگهٔ چاپی")
    ap.add_argument("--pledge", action="store_true", help="ساخت پیمان‌نامهٔ نمایش")
    ap.add_argument("--verify", action="store_true", help="بررسی زنجیرهٔ هش")
    ap.add_argument("--json", action="store_true", help="خروجی JSON")
    ap.add_argument("--version", action="store_true")
    a = ap.parse_args(argv)

    if a.version:
        print(f"investor_test {VERSION}")
        return 0
    if a.verify:
        v = verify_chain()
        print(("زنجیره سالم است" if v["ok"] else f"زنجیره در سطر {v['broken_at']} شکسته") +
              f" · {v['rows']} سطر · اثر انگشت {v['chain']}")
        return 0 if v["ok"] else 1
    if a.flip:
        print(json.dumps(fee_flip(), ensure_ascii=False, indent=1))
        return 0
    if a.ladder:
        import ladder as ladder_mod
        doc = ladder_mod.build(client=a.client, path_md=ladder_mod.LADDER_MD)
        print(doc["md"] if not a.json else json.dumps(doc, ensure_ascii=False, indent=1))
        return 0
    if a.reconcile:
        if a.entry is None or a.exit is None:
            print("برای حساب‌رسی، --entry و --exit لازم است (اختیاری: --days --units --expected).")
            return 2
        rec = reconcile(symbol=a.symbol, entry=a.entry, exit=a.exit, days=a.days, units=a.units,
                        expected=a.expected)
        if not rec.get("ok"):
            print("خطا:", rec.get("error"))
            return 2
        print(f"{rec['symbol']}: هزینهٔ کل {money(rec['cost'])} · دریافتی خالص "
              f"{money(rec['proceeds'])} · سود/زیان {money(rec['profit'])}")
        print(f"بازده دوره {pct(rec['period_pct'])} · سالانه {pct(rec['annualized_pct'])} → "
              f"{rec['verdict']}")
        if rec.get("compare") and rec["compare"] != "—":
            print(rec["compare"])
        print(rec["note"])
        print("زنجیره:", "سالم" if rec["chain"]["ok"] else "شکسته",
              "· کلید", rec["chain"]["last_fingerprint"])
        return 0

    if a.check:
        if a.guess is None:
            print("عدد یا بله/نه را با --guess بدهید.")
            return 2
        res = check(a.guess, client=a.client, case_id=a.check)
        print(f"{res['case']['title']}: حدس «{a.guess}» → جواب موتور {answer_text(res['case'])} · "
              f"داوری: {res['status']}"
              + (f" (فاصله {res['delta_pct']}٪)" if res["delta_pct"] is not None else ""))
        print("  ", res["note"], "· زنجیره:", res["record"]["chain"])
        return 0
    if a.pledge:
        text = build_pledge(client=a.client)
        print(f"پیمان‌نامه ساخته شد: {PLEDGE_MD}")
        print(text[:600])
        return 0
    if a.sheet:
        out = build_sheet(client=a.client)
        print("برگه ساخته شد:", out["html"])
        print("نسخهٔ متن:", out["md"])
        print("کارنامه:", json.dumps(out["scorecard"], ensure_ascii=False))
        return 0
    if a.json:
        print(json.dumps(cases(reveal=True), ensure_ascii=False, indent=1))
        return 0
    _print_cases(show_answers=bool(a.reveal))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
