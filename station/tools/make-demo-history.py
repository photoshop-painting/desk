#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""سازندهٔ پروندهٔ تاریخ نمونه (سینتتیک) برای آزمون پس‌آزمای ایستگاه.

هشدار: اعداد این پرونده ساختگی‌اند و برای آموزش و آزمون کارکرد ساخته شده‌اند؛
هیچ‌کدام قیمت یا بازده واقعی بازار نیستند. برای پس‌آزمای واقعی، پروندهٔ خودتان را
با همان ستون‌ها بسازید (راهنما در README-FA.md پوشهٔ gui).
"""
from __future__ import annotations

import csv
import math
import random
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "demo" / "history-demo.csv"
random.seed(1405)

DATES = [f"1405-{m:02d}-{d:02d}" for m, d in
         [(1, 15), (2, 15), (3, 15), (4, 15), (5, 15), (6, 15), (7, 15), (8, 15), (9, 15), (10, 15)]]

# (نماد، نوع راهبرد، ساخت پایه‌ای فیلدهای ریاضی، وجه تضمین هر واحد، نقدشوندگی روزانه، اسپرد)
BOOK = [
    ("اهرم", "basis", {"spot": 20000, "future": 0, "days": 90}, 20_000_000, 900, 0.005),
    ("طلا", "basis", {"spot": 20000, "future": 0, "days": 60}, 20_000_000, 700, 0.006),
    ("فولاد", "covered_call", {"spot": 7000, "strike": 7600, "premium": 0, "days": 45}, 7000, 160, 0.018),
    ("شپنا", "covered_call", {"spot": 9000, "strike": 9600, "premium": 0, "days": 30}, 9000, 90, 0.02),
    ("کگل", "tabei", {"stock_price": 9800, "put_price": 40, "strike": 14210, "days": 365}, 9840, 240, 0.02),
    ("خساپا", "tabei", {"stock_price": 2500, "put_price": 12, "strike": 3000, "days": 270}, 2512, 320, 0.012),
    ("شستا", "tabei", {"stock_price": 1200, "put_price": 5, "strike": 1320, "days": 200}, 1205, 400, 0.015),
    ("وبملت", "parity", {"call": 420, "put": 380, "spot": 9000, "strike": 9000, "days": 30, "rate": 0.39}, 9000, 80, 0.02),
    ("شپدیس", "box", {"call_low": 300, "put_low": 430, "call_high": 175, "put_high": 585,
                      "strike_low": 1200, "strike_high": 1500, "days": 45}, 250_000, 60, 0.025),
    ("فملی", "box", {"call_low": 220, "put_low": 360, "call_high": 130, "put_high": 500,
                     "strike_low": 800, "strike_high": 1100, "days": 30}, 200_000, 45, 0.022),
]

HURDLES = [0.33, 0.34, 0.35, 0.36, 0.37, 0.38, 0.39, 0.40, 0.41, 0.42]
COLS = ["date", "symbol", "kind", "spot", "future", "strike", "premium", "put_price", "stock_price",
        "call", "put", "call_low", "put_low", "call_high", "put_high", "strike_low", "strike_high", "rate",
        "days", "margin_per_contract", "liquidity_contracts_per_day", "spread_pct", "hurdle",
        "realized_annualized_pct"]


def realized_for(expected_annual: float, days: float, luck: float) -> float:
    """نتیجهٔ واقعی: بخشی از انتظار محقق می‌شود، به‌همراه نویز، فرسایش، و گاهی شکست.

    عمداً «خوش‌بینانه» نیست: معاملهٔ حاشیه‌ای بیشتر شکست می‌خورد تا نتیجهٔ نمونه
    به واقعیت نزدیک بماند و شرکت را گمراه نکند.
    """
    keep = random.gauss(0.52, 0.24)               # چقدر از انتظار محقق می‌شود
    noise = random.gauss(0, 16)                   # نویز بازار
    accident = -65 if random.random() < 0.12 else 0.0   # شکست اجرا، توقف نماد، جهش خبری
    marginality = 0.0 if expected_annual > 60 else -0.35 * (60 - expected_annual)
    return round(expected_annual * keep + noise + accident + marginality, 1)


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for i, date in enumerate(DATES):
        hurdle = HURDLES[i % len(HURDLES)]
        for symbol, kind, params, margin, liq, spread in BOOK:
            base = dict(params)
            # نوسان روزانهٔ بازار: قیمت پایه و پرمیوم آرام تغییر می‌کنند
            drift = math.sin(i / 2.6 + hash(symbol) % 7) * 0.10 + random.gauss(0, 0.05)
            if kind == "basis":
                base["future"] = round(params["spot"] * (1 + (hurdle + 0.12 + drift) * params["days"] / 365))
            elif kind == "covered_call":
                base["premium"] = round(params["strike"] * (0.045 + 0.02 * drift))
            elif kind == "tabei":
                base["put_price"] = max(0.0, round(params["put_price"] * (1 + random.gauss(0, 0.25))))
            elif kind == "parity":
                base["call"] = round(params["put"] + params["spot"] * (hurdle * params["days"] / 365) * (1 + drift))
            elif kind == "box":
                payoff = params["strike_high"] - params["strike_low"]
                debit = payoff * (0.70 + 0.06 * drift)      # بدهی اولیهٔ باکس، نزدیک واقعیت
                base["call_low"] = round(debit * 0.42)
                base["put_low"] = round(debit * 0.58)
                base["call_high"] = round(payoff * 0.25)
                base["put_high"] = round(payoff * 0.30 + debit * 0.35)

            row = {c: "" for c in COLS}
            row.update({"date": date, "symbol": symbol, "kind": kind, "days": params["days"],
                        "margin_per_contract": margin, "liquidity_contracts_per_day": liq,
                        "spread_pct": spread, "hurdle": hurdle})
            for k, v in base.items():
                if k in row and isinstance(v, (int, float)):
                    row[k] = round(v, 2)
            # انتظار تقریبی برای تولید «نتیجهٔ واقعی» (خودِ موتور در پس‌آزمایی دوباره حساب می‌کند)
            rough_expected = 34 + 30 * (1.0 + drift) + random.gauss(0, 14)
            row["realized_annualized_pct"] = realized_for(max(rough_expected, 5.0), params["days"],
                                                          random.random())
            rows.append(row)

    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        f.write("# پروندهٔ تاریخ نمونه (سینتتیک) — اعداد واقعی بازار نیستند\n")
        f.write("# ستون‌ها: تاریخ · نماد · راهبرد · فیلدهای ریاضی · وجه تضمین · نقدشوندگی · اسپرد · نرخ سد · نتیجهٔ واقعی سالانه\n")
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"{len(rows)} سطر در {OUT} ساخته شد")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
