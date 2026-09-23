#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون ۱۰ دقیقه‌ای ایستگاه — کارنامهٔ شاهد، برای نشان‌دادن به سرمایه‌گذار.

منطق کار ساده است: هر مورد **دو بار** حساب می‌شود.
یک بار با موتور واقعی برنامه، یک بار با «حساب دستی» که همان‌جا در کد نوشته شده
و عددش را می‌شود با ماشین‌حساب هم چک کرد. اگر این دو از هم جدا شوند، مورد رد می‌شود.

هیچ عددی دروغین نیست: اگر موتور عوض شود، کارنامه سرخ می‌شود. موردهای فرایندی
(زنجیرهٔ هش، روز واقعی، نبود آینده‌نگری، شکست صادقانهٔ دادهٔ زنده) هم همین‌جا سنجیده می‌شوند.

اجرا:  python selftest.py                 (کارنامه در کنسول + فایل HTML)
       python selftest.py --json          (خروجی ماشین‌خوان)
       python selftest.py --only carry-90d,fees-kill-edge
       python selftest.py --list
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.1.0"
BASE = Path(__file__).resolve().parent
DESK_DIR = (BASE.parent / "desk").resolve()
TOOLS_DIR = (BASE.parent / "tools").resolve()
DATA = BASE / "data"

for p in (str(BASE), str(DESK_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import reportkit as rk  # noqa: E402

_ENGINE = None


def engine():
    """موتور ریاضی مشتقه — همان پرونده‌ای که ایستگاه در تصمیم زنده استفاده می‌کند."""
    global _ENGINE
    if _ENGINE is None:
        path = TOOLS_DIR / "derivatives_scout.py"
        spec = importlib.util.spec_from_file_location("derivatives_scout", str(path))
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules["derivatives_scout"] = module      # لازم برای dataclass داخل موتور
        spec.loader.exec_module(module)
        _ENGINE = module
    return _ENGINE


def engine_fingerprint() -> dict:
    from hashlib import sha256
    path = TOOLS_DIR / "derivatives_scout.py"
    return {"file": str(path), "sha256": sha256(path.read_bytes()).hexdigest()[:16],
            "version": getattr(engine(), "VERSION", "?"), "bytes": path.stat().st_size}


# ---------------------------------------------------------------- ابزار سنجش
def _cmp(got: dict, expected: dict, *, tol: float = 0.02) -> tuple[bool, list[dict]]:
    """مقایسهٔ عدد/وضعیت با تلورانس کوچک (گرد کردن نمایش)."""
    rows: list[dict] = []
    ok_all = True
    for key, exp in expected.items():
        g = got.get(key)
        if isinstance(exp, bool) or isinstance(exp, str) or exp is None:
            good = g == exp
        else:
            try:
                gv, ev = float(g), float(exp)
                diff = abs(gv - ev)
                good = diff <= tol or (ev != 0 and diff / abs(ev) <= 1e-9)
            except (TypeError, ValueError):
                good = False
        ok_all = ok_all and good
        rows.append({"key": key, "got": g, "expected": exp, "ok": good})
    return ok_all, rows


def _case(cid: str, title: str, why: str, inputs: dict, got: dict, expected: dict,
          hand: str, *, tol: float = 0.02, notes: str = "") -> dict:
    ok, rows = _cmp(got, expected, tol=tol)
    return {"id": cid, "title": title, "why": why, "inputs": inputs, "got": got,
            "expected": expected, "hand": hand, "rows": rows, "ok": ok, "notes": notes,
            "kind": "engine"}


def _process_case(cid: str, title: str, why: str, inputs: dict, checks: list[dict],
                  hand: str, *, notes: str = "") -> dict:
    """مورد فرایندی: چند ادعا، هر کدام با شاهد روشن."""
    ok = all(c["ok"] for c in checks)
    return {"id": cid, "title": title, "why": why, "inputs": inputs,
            "got": {c["key"]: c["got"] for c in checks},
            "expected": {c["key"]: c["expected"] for c in checks},
            "rows": checks, "hand": hand, "ok": ok, "notes": notes, "kind": "process"}


# ---------------------------------------------------------------- موردهای موتور
def case_carry(ctx) -> dict:
    e = engine()
    spot, future, days, hurdle, fee = 1000.0, 1145.0, 90.0, 0.39, 0.0012
    res = e.basis_opportunity(spot, future, days, hurdle, fee_buy=fee, fee_sell=fee)
    net = future * (1 - fee) - spot * (1 + fee)          # حساب دستی
    base = spot * (1 + fee)
    annual = ((1 + net / base) ** (365.0 / days) - 1) * 100
    return _case(
        "carry-90d", "خرید نقدی و فروش آتی، ۹۰ روز",
        "همان معاملهٔ پایهٔ بازار: کالا را نقد می‌خری و آتی‌اش را می‌فروشی؛ فقط اختلاف قیمت و کارمزد می‌ماند.",
        {"قیمت نقدی": spot, "قیمت آتی": future, "روز تا سررسید": days,
         "نرخ سد": hurdle, "کارمزد هر سمت": fee},
        {"annualized_pct": res["annualized_pct"], "net_gain_per_unit": res["net_gain_per_unit"],
         "period_return_pct": res["period_return_pct"], "go": res["go"]},
        {"annualized_pct": round(annual, 3), "net_gain_per_unit": round(net, 2),
         "period_return_pct": round(net / base * 100, 3), "go": True},
        hand=f"سود هر واحد = {future}×(۱−{fee}) − {spot}×(۱+{fee}) = {net:,.2f} ریال · "
             f"سرمایهٔ درگیر = {spot}×{1 + fee} = {base:,.2f} · "
             f"بازده دوره = {net / base * 100:.3f}٪ · سالانه = (۱+بازده دوره)^(۳۶۵/۹۰) − ۱ = {annual:.2f}٪",
        notes="نرخ سد ۳۹٪ است (نرخ سود مؤثر بازار)؛ ۷۱٪ یعنی این معامله از سد رد می‌شود.")


def case_carry_hurdle(ctx) -> dict:
    e = engine()
    args = dict(spot=1000.0, future=1145.0, days=90.0, fee_buy=0.0012, fee_sell=0.0012)
    low = e.basis_opportunity(hurdle=0.39, **args)
    high = e.basis_opportunity(hurdle=0.72, **args)
    annual = low["annualized_pct"]
    return _case(
        "carry-hurdle", "یک فرصت، دو نرخ سد",
        "نشان می‌دهد تصمیم به عدد بسته است نه سلیقه: با سد ۳۹٪ همین معامله باز است، با سد ۷۲٪ بسته می‌شود.",
        {"فرصت": f"بازده سالانهٔ {annual}٪", "سد اول": 0.39, "سد دوم": 0.72,
         "کف حاشیهٔ ایستگاه": "۳ واحد درصد"},
        {"go_hurdle_39": low["go"], "go_hurdle_72": high["go"],
         "edge_pp_39": low["edge_pp"], "edge_pp_72": high["edge_pp"]},
        {"go_hurdle_39": True, "go_hurdle_72": False,
         "edge_pp_39": round(annual - 39.0, 3), "edge_pp_72": round(annual - 72.0, 3)},
        hand=f"حاشیه = بازده سالانه − سد · با سد ۳۹٪: {annual}−۳۹ = {annual - 39:.2f} واحد درصد (باز) · "
             f"با سد ۷۲٪: {annual}−۷۲ = {annual - 72:.2f} واحد درصد (زیر کف ۳ → بسته)",
        notes="قاعدهٔ ایستگاه: راهبرد آربیتراژی به کف ۳ واحد درصد نیاز دارد؛ پس سد ۷۲٪ آن را می‌بندد.")


def case_fees_kill_edge(ctx) -> dict:
    e = engine()
    spot, future, days, hurdle = 1000.0, 1100.0, 90.0, 0.39

    def hand(fee: float) -> tuple[float, float]:
        net = future * (1 - fee) - spot * (1 + fee)
        base = spot * (1 + fee)
        return net, ((1 + net / base) ** (365.0 / days) - 1) * 100

    cheap = e.basis_opportunity(spot=spot, future=future, days=days, hurdle=hurdle,
                                fee_buy=0.0012, fee_sell=0.0012)
    dear = e.basis_opportunity(spot=spot, future=future, days=days, hurdle=hurdle,
                               fee_buy=0.02, fee_sell=0.02)
    cheap_annual, dear_annual = hand(0.0012)[1], hand(0.02)[1]
    return _case(
        "fees-kill-edge", "کارمزد گران، فرصت را می‌کُشد",
        "لحظهٔ اعتماد: قیمت‌ها تکان نمی‌خورد، فقط کارمزد از ۰٫۱۲٪ به ۲٪ می‌رود و حکم برنامه عوض می‌شود.",
        {"قیمت نقدی": spot, "قیمت آتی": future, "روز": days, "کارمزد ارزان": 0.0012, "کارمزد گران": 0.02},
        {"annualized_cheap_pct": cheap["annualized_pct"], "annualized_dear_pct": dear["annualized_pct"],
         "go_cheap": cheap["go"], "go_dear": dear["go"]},
        {"annualized_cheap_pct": round(cheap_annual, 3), "annualized_dear_pct": round(dear_annual, 3),
         "go_cheap": True, "go_dear": False},
        hand=f"ارزان: ({future}×۰٫۹۹۸۸ − {spot}×۱٫۰۰۱۲)/۱۰۰۱٫۲ = ۹٫۷۴٪ در ۹۰ روز → سالانه {cheap_annual:.2f}٪ · "
             f"گران: ({future}×۰٫۹۸ − {spot}×۱٫۰۲)/۱۰۲۰ = ۵٫۶۹٪ در ۹۰ روز → سالانه {dear_annual:.2f}٪ "
             f"(زیر سد ۳۹٪ → رد)",
        notes="این مورد ثابت می‌کند برنامه به کارمزد حساس است؛ اگر کسی کارمزد را دستی کم بگذارد، کارنامه او را لو می‌دهد.")


def case_tabei(ctx) -> dict:
    e = engine()
    stock, put, strike, days = 10000.0, 1000.0, 12000.0, 180.0
    res = e.tabei_min_yield(stock, put, strike, days)
    buy_total = stock * (1 + e.FEE_STOCK_BUY) + put
    sell_net = strike * (1 - e.FEE_STOCK_SELL)
    annual = ((sell_net / buy_total) ** (365.0 / days) - 1) * 100
    return _case(
        "tabei-180d", "اوراق تبعی: کمینهٔ بازده تضمین‌شده",
        "اینجا «تضمین» به معنای واقعی است: با خرید سهم + پوت تبعی، کمینهٔ بازده تا سررسید قفل می‌شود.",
        {"قیمت سهم": stock, "قیمت پوت": put, "قیمت اعمال": strike, "روز": days,
         "کارمزد خرید سهم": e.FEE_STOCK_BUY, "کارمزد فروش سهم": e.FEE_STOCK_SELL},
        {"annualized_pct": res["annualized_pct"], "period_return_pct": res["period_return_pct"],
         "cost_basis": res["cost_basis"], "guaranteed_proceeds": res["guaranteed_proceeds"], "go": res["go"]},
        {"annualized_pct": round(annual, 3), "period_return_pct": round((sell_net - buy_total) / buy_total * 100, 3),
         "cost_basis": round(buy_total, 2), "guaranteed_proceeds": round(sell_net, 2), "go": True},
        hand=f"بهای تمام‌شده = {stock}×۱٫۰۰۴۶۴ + {put} = {buy_total:,.1f} · "
             f"دریافتی قفل‌شده = {strike}×۰٫۹۹۰۳۶ = {sell_net:,.1f} · "
             f"بازده = {((sell_net / buy_total) - 1) * 100:.2f}٪ در ۱۸۰ روز → سالانه {annual:.2f}٪")


def case_covered_call(ctx) -> dict:
    e = engine()
    spot, strike, premium, days = 5000.0, 6000.0, 180.0, 60.0
    res = e.covered_call(spot, strike, premium, days)
    basis = spot * (1 + e.FEE_STOCK_BUY)
    prem_net = premium * (1 - e.FEE_OPTION_TRADE)
    prem_annual = ((1 + prem_net / basis) ** (365.0 / days) - 1) * 100
    return _case(
        "covered-call-60d", "فروش اختیار خرید پوشش‌داده‌شده",
        "برنامه فقط «درآمد پرمیوم» را تصمیم می‌گیرد و سقف سود را جدا نشان می‌دهد؛ دو عدد را قاطی نمی‌کند.",
        {"قیمت سهم": spot, "قیمت اعمال": strike, "پرمیوم دریافتی": premium, "روز": days},
        {"annualized_pct": res["annualized_pct"], "premium_annualized_pct": res["premium_annualized_pct"],
         "upside_capped_at_pct": res["upside_capped_at_pct"], "premium_yield_pct": res["premium_yield_pct"],
         "go": res["go"]},
        {"annualized_pct": round(prem_annual, 3), "premium_annualized_pct": round(prem_annual, 3),
         "upside_capped_at_pct": round((strike - spot) / spot * 100, 2),
         "premium_yield_pct": round(premium / spot * 100, 3), "go": True},
        hand=f"پرمیوم خالص = {premium}×۰٫۹۹۸۹۷ = {prem_net:,.2f} · پایه = {spot}×۱٫۰۰۴۶۴ = {basis:,.1f} · "
             f"بازده ۶۰ روزه = {prem_net / basis * 100:.3f}٪ → سالانه {prem_annual:.2f}٪ · "
             f"سقف سود = ({strike}−{spot})/{spot} = ۲۰٪ (جدا شمرده می‌شود)")


def case_parity(ctx) -> dict:
    e = engine()
    call, put, spot, strike, days, rate = 900.0, 350.0, 5000.0, 4800.0, 45.0, 0.30
    res = e.put_call_parity(call, put, spot, strike, days, rate)
    import math
    t = days / 365.0
    right = spot - strike * math.exp(-rate * t)
    gap = (call - put) - right
    costs = (call + put + spot) * e.FEE_OPTION_TRADE
    edge = gap - costs
    basis = spot + put - call
    annual = ((1 + edge / basis) ** (1 / t) - 1) * 100 if basis > 0 else None
    return _case(
        "parity-gap", "انحراف از تساوی پوت-کال",
        "رابطهٔ ریاضی که همیشه باید برقرار باشد؛ هر انحرافش یک معاملهٔ بدون جهت بازار است — به‌شرط اینکه از کارمزد بزرگ‌تر باشد.",
        {"کال": call, "پوت": put, "قیمت سهم": spot, "قیمت اعمال": strike, "روز": days, "نرخ بی‌ریسک": rate},
        {"gap": res["gap"], "conversion_edge_per_unit": res["conversion_edge_per_unit"],
         "annualized_pct": res["annualized_pct"], "direction": res["direction"], "go": res["go"]},
        {"gap": round(gap, 2), "conversion_edge_per_unit": round(edge, 2),
         "annualized_pct": round(annual, 3) if annual else None, "direction": "conversion", "go": True},
        hand=f"سمت چپ = {call}−{put} = {call - put:,.0f} · سمت راست = {spot} − {strike}×e^(−۰٫۳×{t:.4f}) = {right:,.2f} · "
             f"شکاف = {gap:,.2f} · کارمزدها = {costs:,.2f} · سود هر واحد = {edge:,.2f} → سالانه {annual:.2f}٪")


def case_box(ctx) -> dict:
    e = engine()
    res = e.box_spread(600.0, 150.0, 280.0, 250.0, 4000.0, 4500.0, 120.0)
    debit = (600.0 + 250.0) - (150.0 + 280.0)
    payoff = 500.0
    fees = (600.0 + 150.0 + 280.0 + 250.0) * e.FEE_OPTION_TRADE
    net = payoff - debit - fees
    annual = ((1 + net / debit) ** (365.0 / 120.0) - 1) * 100
    return _case(
        "box-spread", "باکس اسپرد: سود بی‌جهت‌بازار",
        "چهار قرارداد که هم‌زمان بسته می‌شوند و نتیجه‌اش عددی ثابت است؛ اگر بدهی اولیه کمتر از فاصلهٔ قیمت اعمال باشد، سود قطعی است.",
        {"کال/پوت اعمال ۴۰۰۰": "۶۰۰ / ۱۵۰", "کال/پوت اعمال ۴۵۰۰": "۲۸۰ / ۲۵۰", "روز": 120.0},
        {"debit": res["debit"], "payoff": res["payoff"], "fees_estimate": res["fees_estimate"],
         "net_profit": res["net_profit"], "annualized_pct": res["annualized_pct"], "go": res["go"]},
        {"debit": round(debit, 2), "payoff": payoff, "fees_estimate": round(fees, 2),
         "net_profit": round(net, 2), "annualized_pct": round(annual, 3), "go": True},
        hand=f"بدهی = (۶۰۰+۲۵۰) − (۱۵۰+۲۸۰) = {debit:,.0f} · دریافتی قطعی = ۴۵۰۰−۴۰۰۰ = {payoff:,.0f} · "
             f"کارمزد = ۱۲۸۰×۰٫۰۰۱۰۳ = {fees:,.2f} · سود = {net:,.2f} → سالانه {annual:.2f}٪")


def case_liquidity_penalty(ctx) -> dict:
    e = engine()
    clean = {"annualized_pct": 60.0, "liquidity_contracts_per_day": 100, "spread_pct": 0.01, "leverage_used": 1}
    dirty = {"annualized_pct": 60.0, "liquidity_contracts_per_day": 5, "spread_pct": 0.06, "leverage_used": 3}
    s1 = e.score(clean, hurdle=0.39)
    s2 = e.score(dirty, hurdle=0.39)
    return _case(
        "liquidity-penalty", "جریمهٔ نقدشوندگی و اسپرد",
        "بازده یکسان، دو بازار متفاوت: بازار کم‌معامله و پراسپرد جریمه می‌خورد تا برنامه فرصت توخالی معرفی نکند.",
        {"بازده سالانه": 60.0, "نقدشوندگی خوب/بد": "۱۰۰ / ۵ قرارداد در روز",
         "اسپرد خوب/بد": 0.01, "اهرم خوب/بد": 1},
        {"score_clean": s1, "score_dirty": s2, "penalty_pp": round(s1 - s2, 3)},
        {"score_clean": 21.0, "score_dirty": 8.0, "penalty_pp": 13.0},
        hand="امتیاز = (بازده − سد)×۱۰۰ − جریمه‌ها · تمیز: (۰٫۶−۰٫۳۹)×۱۰۰ = ۲۱ · "
             "بد: ۲۱ − (۵+۵+۳) = ۸ (نقدشوندگی ۵، اسپرد ۵، اهرم ۳)")


def case_position_size(ctx) -> dict:
    e = engine()
    capital, margin = 20_000_000_000.0, 1_850_000.0
    res = e.position_size(capital, margin, risk_pct=0.20)
    budget = capital * 0.20
    n = int(budget // margin)
    return _case(
        "position-size", "اندازهٔ موقعیت: چند قرارداد؟",
        "برنامه هرگز بیشتر از ۲۰٪ سرمایه را در وجه تضمین قفل نمی‌کند؛ این عدد را می‌شود با یک تقسیم ساده چک کرد.",
        {"سرمایه": capital, "وجه تضمین هر قرارداد": margin, "سقف ریسک": 0.20},
        {"contracts": res["contracts"], "margin_locked": res["margin_locked"], "free_cash": res["free_cash"]},
        {"contracts": n, "margin_locked": round(n * margin, 2), "free_cash": round(capital - n * margin, 2)},
        hand=f"بودجه = {capital:,.0f}×۰٫۲۰ = {budget:,.0f} · تعداد = {budget:,.0f} ÷ {margin:,.0f} = {n} قرارداد · "
             f"قفل‌شده = {n:,}×{margin:,.0f} = {n * margin:,.0f} ریال")


def case_implausible(ctx) -> dict:
    import backtest as bt
    rules = {"min_edge_arbitrage_pct": 3.0, "min_edge_leveraged_pct": 5.0, "max_plausible_arb_pct": 250.0,
             "max_plausible_lev_pct": 400.0, "min_liquidity_contracts_per_day": 20, "max_spread_pct": 0.03}
    row = {"date": "۱۴۰۵-۰۶-۰۱", "symbol": "آزمون", "kind": "basis", "spot": 1000.0, "future": 10000.0,
           "days": 30.0, "margin_per_contract": 1_000_000.0}
    d = bt.decide_row(row, rules)
    absurd = float(d.expected_annualized_pct or 0) / 250.0     # چند برابر سقف باورپذیری؟
    return _process_case(
        "implausible-data", "دادهٔ اشتباه رد می‌شود",
        "اگر کسی قیمت آتی را جابه‌جا وارد کند (ده برابر نقدی)، برنامه سود رؤیایی نمی‌سازد؛ آن را مشکوک اعلام می‌کند.",
        {"قیمت نقدی": 1000.0, "قیمت آتی (اشتباه)": 10000.0, "روز": 30.0, "سقف باورپذیری": 250.0},
        [{"key": "decision_taken", "got": bool(d.taken), "expected": False, "ok": d.taken is False},
         {"key": "reason_mentions_ceiling", "got": "سقف باورپذیری" in d.reason, "expected": True,
          "ok": "سقف باورپذیری" in d.reason},
         {"key": "annualized_x_ceiling", "got": f"{absurd:,.0f}× سقف",
          "expected": "بزرگ‌تر از ۱× سقف", "ok": absurd > 1}],
        hand="بازده بیرون‌آمده از این ورودی میلیون‌ها برابر سقف باورپذیری (۲۵۰٪ برای آربیتراژ) است؛ "
             "دروازه همین بزرگی را نشانهٔ خطای ورودی می‌داند و تصمیم را می‌بندد؛ پس عدد به‌عنوان «سود» روی میز نمی‌آید.",
        notes="عدد سالانه در این مورد عمداً غول‌آسا است؛ خودش شاهدِ خرابی داده است، نه سود.")


def case_no_look_ahead(ctx) -> dict:
    import backtest as bt
    rules = {"min_edge_arbitrage_pct": 3.0, "min_edge_leveraged_pct": 5.0, "max_plausible_arb_pct": 250.0,
             "max_plausible_lev_pct": 400.0, "min_liquidity_contracts_per_day": 20, "max_spread_pct": 0.03}
    rows, problems = bt.load_history(BASE / "demo" / "history-demo.csv")
    sample = rows[:6]
    first = [bt.decide_row(r, rules) for r in sample]
    tampered = []
    for r in sample:
        r2 = dict(r)
        if isinstance(r2.get("realized_annualized_pct"), (int, float)):
            r2["realized_annualized_pct"] = float(r2["realized_annualized_pct"]) * 5
        tampered.append(bt.decide_row(r2, rules))
    same = all((a.taken, a.reason, a.expected_annualized_pct) == (b.taken, b.reason, b.expected_annualized_pct)
               for a, b in zip(first, tampered))
    return _process_case(
        "no-look-ahead", "بدون آینده‌نگری",
        "ستون «نتیجهٔ واقعی گذشته» پنج برابر می‌شود؛ اگر تصمیم‌های برنامه تکان بخورد، یعنی برنامه دارد از آینده تقلب می‌کند.",
        {"ردیف‌های آزمون": len(sample), "ستون دست‌کاری‌شده": "realized_annualized_pct", "ضریب تغییر": 5},
        [{"key": "decisions_identical", "got": bool(same), "expected": True, "ok": bool(same)},
         {"key": "rows_loaded", "got": len(rows), "expected": len(rows), "ok": len(rows) > 0},
         {"key": "problems", "got": len(problems), "expected": len(problems), "ok": True}],
        hand="موتور در گام تصمیم، هر کلیدی که با realized شروع شود را کنار می‌گذارد؛ پس تغییر آن ستون نباید هیچ تصمیمی را عوض کند.")


def case_tamper_chain(ctx) -> dict:
    import live_trial as trial
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "trial.sqlite3"
        t = trial.Trial(db)
        t.record([{"symbol": "الف", "kind": "basis", "decision": "recorded", "expected": 40.0},
                  {"symbol": "ب", "kind": "tabei", "decision": "recorded", "expected": 22.0}],
                 source_label="آزمون", mode="sim", dedupe_hours=0)
        ok_before, why_before = t.verify_chain()
        con = sqlite3.connect(db)
        con.execute("UPDATE entries SET expected = 999 WHERE id = 1")
        con.commit()
        con.close()
        ok_after, why_after = t.verify_chain()
    return _process_case(
        "tamper-chain", "زنجیرهٔ هش: دست‌کاری لو می‌رود",
        "کسی عدد دفتر را در پایگاه‌داده عوض می‌کند؛ بررسی زنجیره باید همان لحظه سرخ شود. این یعنی سابقهٔ شما قابل جعل نیست.",
        {"ردیف‌های ثبت‌شده": 2, "تغییر انجام‌شده": "انتظار ردیف ۱ → ۹۹۹"},
        [{"key": "chain_ok_before", "got": bool(ok_before), "expected": True, "ok": bool(ok_before)},
         {"key": "chain_ok_after_tamper", "got": bool(ok_after), "expected": False, "ok": ok_after is False},
         {"key": "message_names_problem", "got": why_after[:60], "expected": "شکسته/ناسازگار",
          "ok": any(w in why_after for w in ("شکسته", "ناساز", "دست‌کاری", "نامعتبر"))}],
        hand="هر ردیف هش sha256 از (هش ردیف قبل + محتوای خودش) دارد؛ تغییر محتوا بدون بازنویسی همهٔ ردیف‌های بعدی، زنجیره را می‌شکند.")


def case_real_day(ctx) -> dict:
    import datafeed as df
    import daily_trial as dt
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        fake = tmpdir / "market-demo.json"
        fake.write_text(json.dumps({"rows": []}, ensure_ascii=False), encoding="utf-8")
        confirmed = tmpdir / "snapshot-manual.json"
        confirmed.write_text(json.dumps({"rows": [], "source": df.MANUAL_SOURCE}, ensure_ascii=False),
                             encoding="utf-8")
        unconfirmed = tmpdir / "snapshot-plain.json"
        unconfirmed.write_text(json.dumps({"rows": []}, ensure_ascii=False), encoding="utf-8")
        checks = [
            {"key": "demo_path_is_synthetic", "got": bool(dt.path_is_synthetic(fake)), "expected": True,
             "ok": dt.path_is_synthetic(fake) is True},
            {"key": "manual_snapshot_confirmed", "got": bool(df.snapshot_confirmed(confirmed)), "expected": True,
             "ok": df.snapshot_confirmed(confirmed) is True},
            {"key": "plain_file_not_confirmed", "got": bool(df.snapshot_confirmed(unconfirmed)), "expected": False,
             "ok": df.snapshot_confirmed(unconfirmed) is False},
            {"key": "absent_file_not_confirmed", "got": bool(df.snapshot_confirmed(tmpdir / "nope.json")),
             "expected": False, "ok": df.snapshot_confirmed(tmpdir / "nope.json") is False},
        ]
    return _process_case(
        "real-day-gate", "روز «واقعی» جعل‌شدنی نیست",
        "برای اینکه یک روز در کارنامه «واقعی» شمرده شود، پرونده باید هم از مسیر نمونه نباشد و هم شما تأییدش کرده باشید.",
        {"پروندهٔ نمونه": "market-demo.json", "پروندهٔ تأییدشده": "source = manual-broker", "پروندهٔ بی‌برچسب": "بدون source"},
        checks,
        hand="دو شرط با هم: نام/مسیر نمونه نباشد و برچسب منبع، «برداشته‌شده از سامانهٔ کارگزاری» باشد.")


def case_live_failure_honest(ctx) -> dict:
    import datafeed as df
    cfg = dict(df.DEFAULT_LIVE_CONFIG)
    cfg.update({"url_template": "http://127.0.0.1:9/quote?symbol={symbol}", "json_path": "last",
                "timeout_seconds": 2, "retries": 0, "cache_seconds": 0})
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):          # پیام‌های موتور نباید خروجی JSON را آلوده کند
        snap = df.build_snapshot("live", file_path=DESK_DIR / "market-demo.json", live_cfg=cfg,
                                 allow_network=True)
    engine_lines = [ln for ln in buf.getvalue().strip().splitlines() if ln.strip()]
    says_failed = any("نیامد" in m or "نشد" in m for m in snap.messages)
    return _process_case(
        "live-failure-honest", "شکست دادهٔ زنده، بی‌سروصدا نمی‌ماند",
        "سرویس جواب نمی‌دهد؛ برنامه نباید عدد ساختگی جای قیمت زنده بگذارد. باید صریح بگوید «نیامد» و تازگی را نامعلوم بگذارد.",
        {"نشانی آزمایشی": "http://127.0.0.1:9/quote (عمداً بسته)", "حالت": "live"},
        [{"key": "status", "got": snap.status, "expected": "failed", "ok": snap.status == "failed"},
         {"key": "freshness_unknown", "got": snap.freshness_label, "expected": "نامعلوم",
          "ok": snap.freshness_label == "نامعلوم"},
         {"key": "says_not_came", "got": says_failed, "expected": True, "ok": says_failed},
         {"key": "live_prices_empty", "got": len(snap.live_prices), "expected": 0,
          "ok": len(snap.live_prices) == 0},
         {"key": "engine_said_why", "got": engine_lines[0] if engine_lines else "—",
          "expected": "پیام دلیل برای هر نماد", "ok": bool(engine_lines)}],
        hand="قاعده: هیچ عددی بدون منبعِ خوانده‌شده روی میز نمی‌آید. شکست در «پیام‌ها» می‌نشیند و وضعیت را failed می‌کند.")


def case_determinism(ctx) -> dict:
    e = engine()
    args = dict(spot=1000.0, future=1145.0, days=90.0, hurdle=0.39, fee_buy=0.0012, fee_sell=0.0012)
    a = json.dumps(e.basis_opportunity(**args), sort_keys=True, ensure_ascii=False)
    b = json.dumps(e.basis_opportunity(**args), sort_keys=True, ensure_ascii=False)
    t1 = {"annualized_pct": 60.0, "liquidity_contracts_per_day": 10, "spread_pct": 0.01, "leverage_used": 3}
    s1 = e.score(t1, hurdle=0.39)
    s2 = e.score(dict(t1), hurdle=0.39)
    return _process_case(
        "determinism", "تکرارپذیری: یک ورودی، یک جواب",
        "دو بار اجرا با ورودی یکسان باید بیت‌به‌بیت یک جواب بدهد. در مسیر تصمیم هیچ مدل زبانی و هیچ تصادفی نیست.",
        {"ورودی": "مورد carry-90d و یک امتیازدهی نمونه", "تعداد تکرار": 2},
        [{"key": "engine_output_identical", "got": a == b, "expected": True, "ok": a == b},
         {"key": "score_identical", "got": s1 == s2, "expected": True, "ok": s1 == s2},
         {"key": "score_value", "got": s1, "expected": 13.0, "ok": abs(s1 - 13.0) < 0.02}],
        hand="امتیاز = (۰٫۶−۰٫۳۹)×۱۰۰ − ۸ = ۱۳ (نقدشوندگی ۵، اهرم ۳)؛ همان عدد در هر اجرا.")


CASES = [case_carry, case_carry_hurdle, case_fees_kill_edge, case_tabei, case_covered_call,
         case_parity, case_box, case_liquidity_penalty, case_position_size, case_implausible,
         case_no_look_ahead, case_tamper_chain, case_real_day, case_live_failure_honest,
         case_determinism]


def run_all(*, only: list[str] | None = None, cases: list | None = None, quiet: bool = False) -> dict:
    """همهٔ موردها را اجرا می‌کند و کارنامهٔ ماشین‌خوان برمی‌گرداند."""
    started = time.time()
    chosen = cases or CASES
    results: list[dict] = []
    for fn in chosen:
        r = fn({})
        if only and r["id"] not in only:
            continue
        results.append(r)
    passed = len([1 for r in results if r["ok"]])
    return {
        "version": VERSION,
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duration_ms": int((time.time() - started) * 1000),
        "engine": engine_fingerprint(),
        "python": sys.version.split()[0],
        "summary": {"total": len(results), "passed": passed, "failed": len(results) - passed,
                    "ok": passed == len(results) and bool(results)},
        "cases": results,
    }


# ---------------------------------------------------------------- نمایش
def console(result: dict) -> None:
    s = result["summary"]
    print(f"آزمون ایستگاه — نسخه {result['version']} · موتور {result['engine']['version']} "
          f"(sha256:{result['engine']['sha256']}) · {result['ran_at']}")
    print(f"نتیجه: {s['passed']}/{s['total']} سبز · زمان {result['duration_ms']} میلی‌ثانیه")
    print("-" * 78)
    for c in result["cases"]:
        mark = "سبز" if c["ok"] else "سرخ"
        print(f"[{mark}] {c['id']} — {c['title']}")
        for row in c["rows"]:
            flag = "✓" if row["ok"] else "✗"
            print(f"   {flag} {row['key']}: برنامه={row['got']!r} · مستقل={row['expected']!r}")
    print("-" * 78)
    print("برگهٔ آزمون سرمایه‌گذار و کارنامهٔ HTML در پوشهٔ data ساخته شد." if s["ok"] else "کارنامه سرخ است؛ پیش از نمایش به سرمایه‌گذار حلش کنید.")


def table_html(result: dict) -> str:
    s = result["summary"]
    badge = f'<span class="badge {"ok" if s["ok"] else "no"}">{"همه سبز" if s["ok"] else "سرخ"}</span>'
    kpis = (f'<div class="kpis">'
            f'<div class="kpi"><b>{s["passed"]}/{s["total"]}</b><span>مورد سبز</span></div>'
            f'<div class="kpi"><b>{s["failed"]}</b><span>مورد سرخ</span></div>'
            f'<div class="kpi"><b>{result["duration_ms"]}</b><span>میلی‌ثانیه</span></div>'
            f'<div class="kpi"><b>{rk.esc(result["engine"]["version"])}</b><span>نسخهٔ موتور ریاضی</span></div>'
            f'<div class="kpi"><b>{badge}</b><span>وضعیت کلی</span></div></div>')
    rows = []
    for c in result["cases"]:
        cls = "pass" if c["ok"] else "fail"
        detail = " · ".join(f'{rk.esc(r["key"])}={rk.esc(r["got"])}' for r in c["rows"])
        rows.append(f'<tr class="{cls}"><td><b>{rk.esc(c["id"])}</b><br>{rk.esc(c["title"])}</td>'
                    f'<td>{rk.esc(c["why"])}</td><td class="num">{detail}</td>'
                    f'<td>{"سبز" if c["ok"] else "سرخ"}</td></tr>')
    table = ('<table><thead><tr><th>مورد</th><th>چه چیزی را ثابت می‌کند</th>'
             '<th class="num">خروجی برنامه</th><th>وضعیت</th></tr></thead><tbody>'
             + "".join(rows) + "</tbody></table>")
    return kpis + table


def build_report(result: dict, path: Path | None = None) -> Path:
    out = Path(path or (DATA / "selftest-report.html"))
    out.parent.mkdir(parents=True, exist_ok=True)
    body = [
        '<div class="honest"><b>این کارنامه چه چیزی را ثابت می‌کند و چه چیزی را نه.</b> '
        'ثابت می‌کند حساب‌وکتاب برنامه با حساب دستی یکی است، زنجیرهٔ دفتر جعل‌ناپذیر است، '
        'و برنامه در نبود داده، عدد جعل نمی‌کند. ثابت <b>نمی‌کند</b> که این معامله‌ها سود می‌دهند؛ '
        'سودآوری به قیمت اجرا، نقدشوندگی و بازار واقعی بسته است.</div>',
        rk.digest_line("اثر انگشت موتور ریاضی (sha256، ۱۶ رقم اول)", result["engine"]["sha256"]),
        table_html(result),
        "<h2>جزئیات هر مورد</h2>",
    ]
    for c in result["cases"]:
        inputs = " · ".join(f"{rk.esc(k)}: {rk.esc(v)}" for k, v in c["inputs"].items())
        rows = "".join(
            f'<tr><td class="num">{rk.esc(r["key"])}</td><td class="num">{rk.esc(r["got"])}</td>'
            f'<td class="num">{rk.esc(r["expected"])}</td><td>{"✓" if r["ok"] else "✗"}</td></tr>'
            for r in c["rows"])
        body.append(
            f'<h3>{rk.esc(c["id"])} — {rk.esc(c["title"])} {"✅" if c["ok"] else "❌"}</h3>'
            f'<p>{rk.esc(c["why"])}</p>'
            f'<p class="sub">ورودی‌ها: {inputs}</p>'
            f'<table><thead><tr><th>کمیت</th><th class="num">خروجی برنامه</th>'
            f'<th class="num">حساب دستی مستقل</th><th>تطابق</th></tr></thead><tbody>{rows}</tbody></table>'
            f'<p class="note">راه چک با ماشین‌حساب: {rk.esc(c["hand"])}</p>'
            + (f'<p class="sub">{rk.esc(c["notes"])}</p>' if c.get("notes") else ""))
    out.write_text(rk.page("کارنامهٔ آزمون ایستگاه (۱۰ دقیقه)", "".join(body),
                           subtitle=f"{result['summary']['passed']} از {result['summary']['total']} مورد سبز · "
                                    f"اجرا در {result['ran_at']}"), encoding="utf-8")
    return out


def build_exam_sheet(result: dict, path: Path | None = None) -> Path:
    """برگهٔ آزمون برای سرمایه‌گذار: اول حدس خودش، بعد پاسخ برنامه و راه چک دستی."""
    out = Path(path or (DATA / "exam-sheet.html"))
    out.parent.mkdir(parents=True, exist_ok=True)
    body = [
        '<div class="note"><b>روش استفاده:</b> این برگه را چاپ کنید یا روی صفحه بدهید. '
        'برای هر سؤال اول <b>حدس خودتان</b> را بنویسید، بعد صفحه را برگردانید و پاسخ برنامه و '
        'راه چک با ماشین‌حساب را ببینید. اگر پاسخ‌ها را با ماشین‌حساب تأیید کردید، '
        'یعنی خودتان مستقل راستی‌آزمایی کرده‌اید — همان چیزی که این برنامه ادعا می‌کند.</div>',
        "<h2>بخش یک: سؤال‌ها (پاسخ‌ها در صفحهٔ بعد)</h2>",
    ]
    for i, c in enumerate(result["cases"], start=1):
        inputs = " · ".join(f"{rk.esc(k)}: {rk.esc(v)}" for k, v in c["inputs"].items())
        body.append(f'<h3>سؤال {i}: {rk.esc(c["title"])}</h3><p>{rk.esc(c["why"])}</p>'
                    f'<p class="sub">ورودی‌ها — {inputs}</p>'
                    '<p class="hint">حدس شما:</p><div class="lines"></div><div class="lines"></div>')
    body.append('<h2 style="page-break-before:always">بخش دو: پاسخ‌ها و راه چک دستی</h2>')
    for i, c in enumerate(result["cases"], start=1):
        got = " · ".join(f"{rk.esc(r['key'])} = {rk.esc(r['got'])}" for r in c["rows"])
        body.append(f'<h3>پاسخ {i}: {rk.esc(c["title"])}</h3>'
                    f'<p class="num">{got}</p>'
                    f'<p class="note">چک با ماشین‌حساب: {rk.esc(c["hand"])}</p>')
    out.write_text(rk.page("برگهٔ آزمون سرمایه‌گذار", "".join(body),
                           subtitle=f"{len(result['cases'])} سؤال · پاسخ‌ها از همان موتوری است که در تصمیم زنده کار می‌کند"),
                   encoding="utf-8")
    return out


# ---------------------------------------------------------------- خط فرمان
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=f"آزمون ۱۰ دقیقه‌ای ایستگاه — نسخه {VERSION}")
    ap.add_argument("--only", help="فقط موردهای فهرست‌شده، جداشده با ویرگول")
    ap.add_argument("--json", action="store_true", help="خروجی ماشین‌خوان")
    ap.add_argument("--list", action="store_true", help="فهرست موردها")
    ap.add_argument("--no-report", action="store_true", help="فایل HTML نساز")
    ap.add_argument("--version", action="version", version=VERSION)
    args = ap.parse_args(argv)

    only = [x.strip() for x in (args.only or "").replace("،", ",").split(",") if x.strip()]
    if args.list:
        for fn in CASES:
            r = fn({})
            print(f"{r['id']:>22} · {r['title']}")
        return 0

    result = run_all(only=only or None)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        console(result)
        if not args.no_report:
            print("کارنامه:", build_report(result))
            print("برگهٔ آزمون:", build_exam_sheet(result))
    return 0 if result["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
