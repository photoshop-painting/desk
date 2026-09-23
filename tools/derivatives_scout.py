#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""دیده‌بان ریاضی بازار مشتقه ایران — ابزار محاسبهٔ بازده بدون‌شانس.

هیچ پیش‌بینی‌ای انجام نمی‌شود؛ فقط رابطه‌های ریاضی قیمت‌گذاری (ارزش منصفانه،
تساوی پوت‌کال، باکس اسپرد، مبنای آتی، بازده تضمینی اوراق تبعی) روی اعداد بازار
اجرا و با نرخ سد (benchmark) مقایسه می‌شود. خروجی: فهرست فرصت‌ها با بازده
سالانهٔ خالص و حاشیهٔ اطمینان.

اجرا:
    python3 derivatives_scout.py --demo
    python3 derivatives_scout.py --input scenario.json
    python3 derivatives_scout.py --self-test
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from typing import Iterable

# ---------------------------------------------------------------- هزینه‌های بازار ایران
# کارمزد معاملهٔ اختیار معامله: ۰٫۱۰۳٪ ارزش معامله (هر طرف)؛ کارمزد اعمال ۰٫۰۵٪ ارزش قرارداد
# بر پایهٔ قیمت اعمال؛ مالیات واگذاری در تسویهٔ فیزیکی ۰٫۵٪.
FEE_OPTION_TRADE = 0.00103
FEE_OPTION_EXERCISE = 0.0005
TAX_PHYSICAL_SETTLE = 0.005
# سهام: کارمزد خرید ۰٫۴۶۴٪ و کسورات فروش ۰٫۹۶۴٪ (شامل ۰٫۵٪ مالیات).
FEE_STOCK_BUY = 0.00464
FEE_STOCK_SELL = 0.00964
# صندوق کالایی/زعفران: ۰٫۱۲٪ هر طرف.
FEE_FUND_ETF = 0.0012

DAYS = 365.0


# ---------------------------------------------------------------- ابزارهای پایه
def years(days: float) -> float:
    if days <= 0:
        raise ValueError("روز تا سررسید باید مثبت باشد")
    return days / DAYS


def exp(x: float) -> float:
    return math.exp(x)


def _npdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes(spot: float, strike: float, days: float, rate: float,
                  vol: float, kind: str = "call") -> float:
    """قیمت نظری اروپایی؛ rate و vol سالانه‌اند و اعشاری وارد می‌شوند."""
    if spot <= 0 or strike <= 0 or vol < 0:
        raise ValueError("ورودی نامعتبر")
    t = years(max(days, 1e-9))
    disc = exp(-rate * t)
    if vol == 0:
        intrinsic = max(spot - strike * disc, 0.0) if kind == "call" else max(strike * disc - spot, 0.0)
        return intrinsic
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    if kind == "call":
        return spot * _ncdf(d1) - strike * disc * _ncdf(d2)
    return strike * disc * _ncdf(-d2) - spot * _ncdf(-d1)


def implied_vol(price: float, spot: float, strike: float, days: float,
                rate: float, kind: str = "call",
                lo: float = 1e-4, hi: float = 5.0, tol: float = 1e-6) -> float | None:
    """نوسان ضمنی با روش نصف‌کردن بازه؛ اگر قیمت بیرون از بازهٔ معتبر باشد None."""
    t = years(max(days, 1e-9))
    intrinsic = max(spot - strike * exp(-rate * t), 0.0) if kind == "call" else \
        max(strike * exp(-rate * t) - spot, 0.0)
    if price < intrinsic - 1e-9:
        return None
    if black_scholes(spot, strike, days, rate, hi, kind) < price:
        return None
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if black_scholes(spot, strike, days, rate, mid, kind) < price:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------- رابطه‌های آربیتراژ
def futures_fair(spot: float, days: float, rate: float,
                 storage: float = 0.0, convenience: float = 0.0) -> float:
    """F = S · e^((r + انبارداری − راحتی)·T)"""
    t = years(days)
    return spot * exp((rate + storage - convenience) * t)


def implied_rate(spot: float, future: float, days: float) -> float:
    """نرخ تلویحی (سالانه) از مبنای آتی: ln(F/S)/T"""
    t = years(days)
    return math.log(future / spot) / t


def basis_opportunity(spot: float, future: float, days: float,
                      hurdle: float, fee_buy: float = FEE_FUND_ETF,
                      fee_sell: float = FEE_FUND_ETF,
                      storage_annual: float = 0.0) -> dict:
    """خرید نقدی + فروش آتی: بازده سالانهٔ خالص در برابر نرخ سد."""
    t = years(days)
    cost_buy = spot * (1 + fee_buy)
    proceeds = future * (1 - fee_sell)
    storage = spot * storage_annual * t
    net_gain = proceeds - cost_buy - storage
    ret_period = net_gain / cost_buy
    annual = (1 + ret_period) ** (1 / t) - 1
    return {
        "strategy": "basis_cash_and_carry",
        "net_gain_per_unit": round(net_gain, 2),
        "period_return_pct": round(ret_period * 100, 3),
        "annualized_pct": round(annual * 100, 3),
        "hurdle_pct": round(hurdle * 100, 3),
        "edge_pp": round((annual - hurdle) * 100, 3),
        "go": annual - hurdle >= 0.03,
    }


def put_call_parity(call: float, put: float, spot: float, strike: float,
                    days: float, rate: float,
                    fee: float = FEE_OPTION_TRADE) -> dict:
    """انحراف از تساوی C − P = S − K·e^(−rT)."""
    t = years(days)
    left = call - put
    right = spot - strike * exp(-rate * t)
    gap = left - right
    costs = (call + put + spot) * fee
    conversion_edge = gap - costs           # خرید سهم + خرید پوت + فروش کال
    basis = spot + put - call
    annual = None
    if basis > 0 and conversion_edge > 0:
        annual = (1 + conversion_edge / basis) ** (1 / t) - 1
    return {
        "strategy": "put_call_parity",
        "lhs_call_minus_put": round(left, 2),
        "rhs_spot_minus_pv_strike": round(right, 2),
        "gap": round(gap, 2),
        "costs_estimate": round(costs, 2),
        "conversion_edge_per_unit": round(conversion_edge, 2),
        "annualized_pct": round(annual * 100, 3) if annual is not None else None,
        "direction": "conversion" if conversion_edge > 0 else "reverse (نیازمند فروش استقراضی: در ایران ممکن نیست)",
        "go": conversion_edge > 0,
    }


def box_spread(call_low: float, put_low: float, call_high: float, put_high: float,
               strike_low: float, strike_high: float, days: float,
               fee: float = FEE_OPTION_TRADE) -> dict:
    """باکس اسپرد: بدهی اولیه در برابر دریافتی قطعی (K₂−K₁).

    خرید کال با اعمال پایین + فروش پوت با اعمال پایین +
    فروش کال با اعمال بالا + خرید پوت با اعمال بالا.
    """
    t = years(days)
    if strike_high <= strike_low:
        raise ValueError("قیمت اعمال بالا باید بزرگ‌تر باشد")
    debit = (call_low + put_high) - (put_low + call_high)
    payoff = strike_high - strike_low
    fees = (call_low + put_low + call_high + put_high) * fee + payoff * FEE_OPTION_EXERCISE * 0
    net = payoff - debit - fees
    if debit <= 0:
        return {"strategy": "box_spread", "debit": round(debit, 2), "note": "بدهی غیرمثبت: داده را بررسی کنید", "go": False}
    period = net / debit
    annual = (1 + period) ** (1 / t) - 1
    return {
        "strategy": "box_spread",
        "debit": round(debit, 2),
        "payoff": round(payoff, 2),
        "fees_estimate": round(fees, 2),
        "net_profit": round(net, 2),
        "period_return_pct": round(period * 100, 3),
        "annualized_pct": round(annual * 100, 3),
        "go": annual > 0,
    }


def tabei_min_yield(stock_price: float, put_price: float, strike: float, days: float,
                    fee_stock_buy: float = FEE_STOCK_BUY,
                    fee_stock_sell: float = FEE_STOCK_SELL) -> dict:
    """اوراق اختیار فروش تبعی: کمینهٔ بازده در صورت نگه‌داشتن تا سررسید."""
    t = years(days)
    buy_total = stock_price * (1 + fee_stock_buy) + put_price
    sell_net = strike * (1 - fee_stock_sell)
    period = (sell_net - buy_total) / buy_total
    annual = (1 + period) ** (1 / t) - 1
    return {
        "strategy": "tabei_put_min_yield",
        "cost_basis": round(buy_total, 2),
        "guaranteed_proceeds": round(sell_net, 2),
        "period_return_pct": round(period * 100, 3),
        "annualized_pct": round(annual * 100, 3),
        "go": annual > 0,
    }


def covered_call(spot: float, strike: float, premium: float, days: float,
                 fee_stock_buy: float = FEE_STOCK_BUY,
                 fee_stock_sell: float = FEE_STOCK_SELL,
                 fee_option: float = FEE_OPTION_TRADE) -> dict:
    """فروش اختیار خرید پوشش‌داده‌شده روی سهم موجود."""
    t = years(days)
    basis = spot * (1 + fee_stock_buy)
    proceeds = strike * (1 - fee_stock_sell) + premium * (1 - fee_option)
    period = (proceeds - basis) / basis
    annual = (1 + period) ** (1 / t) - 1
    capped_upside = round((strike - spot) / spot * 100, 2)
    prem_period = (premium * (1 - fee_option)) / basis
    prem_annual = (1 + prem_period) ** (1 / t) - 1
    return {
        "strategy": "covered_call",
        "period_return_if_exercised_pct": round(period * 100, 3),
        "annualized_if_exercised_pct": round(annual * 100, 3),
        "premium_yield_pct": round(premium / spot * 100, 3),
        "premium_annualized_pct": round(prem_annual * 100, 3),
        # معیار تصمیم: فقط درآمد پرمیوم (بخش بازار-ریسک جدا شمرده می‌شود)
        "annualized_pct": round(prem_annual * 100, 3),
        "upside_capped_at_pct": capped_upside,
        "go": prem_annual > 0.03,
    }


def position_size(capital: float, margin_per_contract: float,
                  risk_pct: float = 0.20, concurrent: int = 1) -> dict:
    """چند قرارداد می‌توان باز کرد تا وجه تضمین از سقف ریسک رد نشود."""
    budget = capital * risk_pct * concurrent
    n = int(budget // margin_per_contract) if margin_per_contract > 0 else 0
    return {
        "contracts": n,
        "margin_locked": round(n * margin_per_contract, 2),
        "free_cash": round(capital - n * margin_per_contract, 2),
        "min_cash_ratio": 0.40,
    }


def score(opportunity: dict, hurdle: float = 0.35) -> float:
    """امتیازدهی: بازده سالانه منهای نرخ سد، با جریمهٔ نقدشوندگی و اهرم."""
    annual = opportunity.get("annualized_pct")
    if annual is None:
        return -999.0
    edge = annual / 100.0 - hurdle
    penalty = 0.0
    if opportunity.get("liquidity_contracts_per_day", 99) < 20:
        penalty += 0.05
    if opportunity.get("spread_pct", 0) > 0.03:
        penalty += 0.05
    if opportunity.get("leverage_used", 0) > 2:
        penalty += 0.03
    return round((edge - penalty) * 100, 3)


# ---------------------------------------------------------------- گزارش
@dataclass
class Scenario:
    name: str
    rows: list[dict] = field(default_factory=list)
    hurdle: float = 0.35


def run_scenario(sc: Scenario) -> list[dict]:
    out: list[dict] = []
    for r in sc.rows:
        kind = r.get("kind")
        try:
            if kind == "basis":
                res = basis_opportunity(r["spot"], r["future"], r["days"], sc.hurdle,
                                        r.get("fee_buy", FEE_FUND_ETF),
                                        r.get("fee_sell", FEE_FUND_ETF),
                                        r.get("storage_annual", 0.0))
            elif kind == "parity":
                res = put_call_parity(r["call"], r["put"], r["spot"], r["strike"],
                                      r["days"], r.get("rate", 0.35))
            elif kind == "box":
                res = box_spread(r["call_low"], r["put_low"], r["call_high"], r["put_high"],
                                 r["strike_low"], r["strike_high"], r["days"])
            elif kind == "tabei":
                res = tabei_min_yield(r["stock_price"], r["put_price"], r["strike"], r["days"])
            elif kind == "covered_call":
                res = covered_call(r["spot"], r["strike"], r["premium"], r["days"])
            else:
                out.append({"name": r.get("name", "?"), "error": f"نوع ناشناخته: {kind}"})
                continue
        except (KeyError, ValueError, ZeroDivisionError) as e:
            out.append({"name": r.get("name", "?"), "error": str(e)})
            continue
        res["name"] = r.get("name", kind)
        res["liquidity_contracts_per_day"] = r.get("liquidity_contracts_per_day", 99)
        res["spread_pct"] = r.get("spread_pct", 0.0)
        res["leverage_used"] = r.get("leverage_used", 0)
        res["score_pp"] = score(res, sc.hurdle)
        out.append(res)
    return sorted(out, key=lambda x: x.get("score_pp", -999), reverse=True)


def print_report(items: Iterable[dict], hurdle: float, caveat: bool = True) -> None:
    print(f"نرخ سد (بازده بدون ریسک فرضی): {hurdle * 100:.1f}٪ سالانه")
    if caveat:
        print("یادآوری: خروجی فقط تفاوت ریاضی قیمت‌ها با نرخ سد است؛ ریسک اجرا، نقدشوندگی،")
        print("         وجه تضمین و نکول ناشر در آن لحاظ نشده. اعداد نمونه، واقعی بازار نیستند.")
    print("-" * 72)
    for it in items:
        if "error" in it:
            print(f"× {it['name']}: {it['error']}")
            continue
        annual = it.get("annualized_pct")
        tag = "✅" if it.get("go") else ("✖" if "go" in it else "◻")
        annual_txt = f"{annual:.2f}٪" if isinstance(annual, (int, float)) else "—"
        print(f"{tag} {it['name']:<28} بازده سالانهٔ خالص: {annual_txt:<10} امتیاز: {it['score_pp']}")
        for k, v in it.items():
            if k in {"name", "strategy", "go", "score_pp", "annualized_pct"}:
                continue
            print(f"     · {k}: {v}")
        print()


DEMO = {
    "hurdle": 0.35,
    "rows": [
        {"name": "آتی صندوق طلا (۶۰ روز)", "kind": "basis", "spot": 20000, "future": 22800,
         "days": 60, "storage_annual": 0.0, "liquidity_contracts_per_day": 900, "spread_pct": 0.005},
        {"name": "باکس اسپرد خساپا (۴۵ روز)", "kind": "box", "call_low": 300, "put_low": 420,
         "call_high": 180, "put_high": 560, "strike_low": 1200, "strike_high": 1500, "days": 45},
        {"name": "تبعی نمونه (۹۰ روز، ۲۵٪ تضمین)", "kind": "tabei", "stock_price": 50000,
         "put_price": 200, "strike": 62500, "days": 90},
        {"name": "پوشش‌داده‌شده فولاد (۳۰ روز)", "kind": "covered_call", "spot": 7000,
         "strike": 7400, "premium": 220, "days": 30},
        {"name": "تساوی پوت‌کال شپنا (۳۰ روز)", "kind": "parity", "call": 420, "put": 380,
         "spot": 9000, "strike": 9000, "days": 30, "rate": 0.35},
    ],
}


def self_test() -> int:
    ok = 0
    # ارزش نظری بلک‌شولز با مقدار مرجع
    c = black_scholes(100, 100, 365, 0.0, 0.20, "call")
    assert abs(c - 7.9656) < 0.01, c
    ok += 1
    # تقارن پوت‌کال در مدل
    p = black_scholes(100, 100, 365, 0.0, 0.20, "put")
    assert abs((c - p) - 0.0) < 1e-9, (c, p)  # r=0 ⇒ C=P
    ok += 1
    # نرخ تلویحی
    assert abs(implied_rate(100, 110, 365) - math.log(1.1)) < 1e-9
    ok += 1
    # نوسان ضمنی رفت‌وبرگشت
    iv = implied_vol(c, 100, 100, 365, 0.0, "call")
    assert iv is not None and abs(iv - 0.20) < 1e-4, iv
    ok += 1
    # باکس اسپرد: بازده قطعی مثبت و سالانه‌سازی درست
    b = box_spread(300, 420, 180, 560, 1200, 1500, 45)
    assert b["payoff"] == 300
    assert b["annualized_pct"] > 0
    ok += 1
    # تبعی: بازده تضمینی مثبت
    t = tabei_min_yield(50000, 0, 62500, 90)
    assert t["annualized_pct"] > 0.25 * 100
    ok += 1
    print(f"خودآزمون: {ok} بررسی موفق")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="دیده‌بان ریاضی بازار مشتقه ایران")
    ap.add_argument("--demo", action="store_true", help="اجرای سناریوی نمونه")
    ap.add_argument("--input", help="پروندهٔ JSON سناریو")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    data = DEMO if args.demo else (json.load(open(args.input, encoding="utf-8")) if args.input else None)
    if data is None:
        ap.print_help()
        return 0
    sc = Scenario(name=data.get("name", "سناریو"), rows=data["rows"], hurdle=data.get("hurdle", 0.35))
    print_report(run_scenario(sc), sc.hurdle, caveat=bool(args.demo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
