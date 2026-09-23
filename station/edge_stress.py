#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون تاب‌آوری — «مطمئن شو ایده‌های قبلی واقعاً جواب می‌دهند».

ایدهٔ خوب، ایده‌ای نیست که فقط در بهترین حالت سود نشان بدهد؛ ایده‌ای است که وقتی شرایط
بدتر شد هم بدانی کجا می‌افتد. این پرونده همین کار را می‌کند:

  • هر راهبرد را با شرایط بدتر (لغزش اجرا، حرکت مخالف قیمت، کارمزد بیشتر، نرخ سد بالاتر،
    وجه تضمین گران‌تر، نقدشوندگی کمتر) دوباره حل می‌کند — با همان موتور خودِ برنامه.
  • «نقطهٔ مرگ» هر راهبرد را با جست‌وجوی دودویی پیدا می‌کند: کارمزد تا چند برابر بالا برود
    که سود از بین برود؟ نرخ سد تا کجا بالا برود که سیگنال بیفتد؟
  • فاصله تا اخطاریهٔ مارجین‌کال را حساب می‌کند (مهم‌ترین عدد برای سرمایهٔ کوچک).
  • «نرخ تاب‌آوری» می‌دهد: چند درصدِ شوک‌ها را سالم رد کرده. این **احتمال سود نیست**؛
    فقط می‌گوید در بدترین حالت‌ها چقدر مقاوم است. هیچ‌جا ادعای تضمین سود نمی‌شود.

هر عددی که این‌جا ساخته می‌شود، بازتولیدپذیر است: با حالت خنثی (بدون شوک) دقیقاً همان عدد
موتور بیرون می‌آید — آزمون‌ها همین را قفل کرده‌اند.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import investor_test as inv  # noqa: E402
import signal_judge as sj  # noqa: E402
import reportkit as rk  # noqa: E402

VERSION = "0.1.0"
DATA = BASE / "data"
REPORT_HTML = DATA / "edge-stress.html"
REPORT_MD = DATA / "edge-stress.md"
REPORT_JSON = DATA / "edge-stress.json"

HURDLE_STRESS = 0.45          # نرخ سد بالاتر: بازده مؤثر صندوق‌ها بالا می‌رود
SLIP_PCT = 0.5                # لغزش اجرا: خرید گران‌تر، فروش ارزان‌تر
PRICE_SHOCK_PCT = 1.0         # ۱٪ حرکت مخالف قیمت پایه
MARGIN_STRESS = 1.2           # کارگزاری وجه تضمین را ۲۰٪ بالا می‌برد

# کدام عدد در هر راهبرد «خرید» است و کدام «فروش» → لغزش کدام‌طرف را بدتر می‌کند
BUY_FIELDS = {"basis": ("spot",), "tabei": ("stock_price", "put_price"),
              "covered_call": ("spot",), "box": ("call_low", "put_high"),
              "parity": ("spot_like",)}
SELL_FIELDS = {"basis": ("future",), "covered_call": ("premium",), "box": ("put_low", "call_high")}


def engine():
    return inv.engine()


def _scale(row: dict, fields: tuple, factor: float) -> dict:
    out = dict(row)
    for f in fields:
        if isinstance(out.get(f), (int, float)):
            out[f] = float(out[f]) * factor
    return out


def shocked_row(row: dict, *, slip_pct: float = 0.0, price_shock_pct: float = 0.0) -> dict:
    """قیمت‌ها را بدتر می‌کند: پایه‌های خرید گران‌تر، پایه‌های فروش ارزان‌تر (بدون دست‌زدن به مشخصات قرارداد)."""
    kind = row.get("kind")
    out = dict(row)
    if slip_pct:
        out = _scale(out, BUY_FIELDS.get(kind, ()), 1 + slip_pct / 100)
        out = _scale(out, SELL_FIELDS.get(kind, ()), 1 - slip_pct / 100)
    if price_shock_pct:
        # حرکت مخالف قیمت پایه: در «مبنا» و «پوشش‌داده‌شده» و «تبعی» دارایی گران‌تر می‌شود
        if kind == "basis":
            out = _scale(out, ("spot",), 1 + price_shock_pct / 100)
        elif kind == "covered_call":
            out = _scale(out, ("spot",), 1 + price_shock_pct / 100)
        elif kind == "tabei":
            out = _scale(out, ("stock_price",), 1 + price_shock_pct / 100)
        # باکس اسپرد و تساوی، نسبت به حرکت قیمت پایه حساس نیستند (جهت‌شان خنثی است)
    return out


def annualized(row: dict, *, fee_mult: float = 1.0, hurdle: float | None = None) -> dict:
    """بازده سالانه را با کارمزد ضرب‌شده و نرخ سد دلخواه دوباره حساب می‌کند.

    برای راهبردهایی که موتور کارمزد را ورودی می‌گیرد (مبنا، تبعی، پوشش‌داده‌شده) حساب دقیق
    است. برای «باکس اسپرد» کارمزد داخل موتور ثابت است؛ آن‌جا همان فرمول دستی‌ای که آزمون
    دو-روشی تأییدش کرده به کار می‌رود و در خروجی هم برچسب «مسیر دستی» می‌گیرد.
    """
    E = engine()
    kind = row.get("kind")
    fb, fs, fo = inv._fees(row, kind)
    h = float(row.get("hurdle") or (hurdle if hurdle is not None else inv.HURDLE_DEFAULT))
    if hurdle is not None:
        h = float(hurdle)

    if kind == "basis":
        res = E.basis_opportunity(row["spot"], row["future"], row["days"], h, fb * fee_mult,
                                  fs * fee_mult, row.get("storage_annual", 0.0))
        return {"annualized_pct": res["annualized_pct"], "path": "موتور", "hurdle": h}
    if kind == "tabei":
        res = E.tabei_min_yield(row["stock_price"], row["put_price"], row["strike"], row["days"],
                                fb * fee_mult, fs * fee_mult)
        # موتور نرخ سد را در خروجی نمی‌آورد؛ خودمان مقایسه می‌کنیم
        return {"annualized_pct": res["annualized_pct"], "path": "موتور", "hurdle": h}
    if kind == "covered_call":
        res = E.covered_call(row["spot"], row["strike"], row["premium"], row["days"], fb * fee_mult,
                             fs * fee_mult, fo * fee_mult)
        return {"annualized_pct": res["premium_annualized_pct"], "path": "موتور", "hurdle": h}
    if kind == "box":
        res = E.box_spread(row["call_low"], row["put_low"], row["call_high"], row["put_high"],
                           row["strike_low"], row["strike_high"], row["days"])
        debit = (row["call_low"] + row["put_high"]) - (row["put_low"] + row["call_high"])
        payoff = row["strike_high"] - row["strike_low"]
        legs = row["call_low"] + row["put_low"] + row["call_high"] + row["put_high"]
        fees = legs * fo * fee_mult
        if debit <= 0:
            return {"annualized_pct": None, "path": "مسیر دستی (فرمول تأییدشده)",
                    "engine_pct": res.get("annualized_pct"), "hurdle": h,
                    "note": "پرداخت خالص باکس صفر یا منفی است؛ بازده سالانه معنا ندارد."}
        # نکتهٔ مهم: پرداخت خالص (debit) یک‌بار می‌آید؛ فرمول سالانه‌کردن روی خودِ نسبت است.
        annual = ((payoff - fees) / debit) ** (365.0 / row["days"]) - 1
        return {"annualized_pct": round(annual * 100, 3), "path": "مسیر دستی (فرمول تأییدشده)",
                "engine_pct": res.get("annualized_pct"), "hurdle": h}
    if kind == "parity":
        res = E.put_call_parity(row["call"], row["put"], row["spot"], row["strike"], row["days"],
                                row.get("rate", h))
        return {"annualized_pct": None, "go": bool(res.get("go")), "path": "موتور",
                "edge": res.get("conversion_edge_per_unit"), "hurdle": h}
    raise ValueError(f"نوع ناشناخته: {kind}")


def survives(row: dict, *, fee_mult: float = 1.0, hurdle: float | None = None,
             slip_pct: float = 0.0, price_shock_pct: float = 0.0) -> dict:
    """پس از شوک، سیگنال می‌ماند یا می‌افتد؟ (بر پایهٔ همان قاعدهٔ نرخ سد)"""
    r = shocked_row(row, slip_pct=slip_pct, price_shock_pct=price_shock_pct)
    out = annualized(r, fee_mult=fee_mult, hurdle=hurdle)
    if row.get("kind") == "parity":
        return {**out, "survives": bool(out.get("go"))}
    annual = out["annualized_pct"]
    return {**out, "survives": bool(annual is not None and annual > out["hurdle"] * 100)}


def fee_tolerance(row: dict, *, hi: float = 12.0) -> dict:
    """کارمزد تا چند برابر بالاتر برود که سیگنال بیفتد (جست‌وجوی دودویی)."""
    if row.get("kind") == "parity":
        base = survives(row)
        return {"multiple": None, "detail": "تساوی به کارمزد به‌شدت حساس است؛ کارمزد سه پایه "
                                            "همیشه اول کسر می‌شود و «نه» فعلی هم از همین است.",
                "survives_now": base["survives"]}
    if not survives(row)["survives"]:
        return {"multiple": None, "survives_now": False,
                "detail": "این ردیف همین امروز هم زیر نرخ سد است؛ «تحمل کارمزد» معنا ندارد — "
                          "اول باید خودِ سیگنال زنده شود."}
    lo, mid = 0.0, 1.0
    if survives(row, fee_mult=hi)["survives"]:
        return {"multiple": None, "detail": f"با کارمزد {hi:g} برابر هم می‌ماند؛ کارمزد قاتل این "
                                            f"راهبرد نیست.", "survives_now": True}
    for _ in range(50):
        mid = (lo + hi) / 2
        if survives(row, fee_mult=mid)["survives"]:
            lo = mid
        else:
            hi = mid
    return {"multiple": round((lo + hi) / 2, 3),
            "detail": f"اگر کارمزد کل از {round((lo + hi) / 2, 2)} برابر امروز بگذرد، این راهبرد "
                      f"از نرخ سد می‌افتد.", "survives_now": survives(row)["survives"]}


def hurdle_ceiling(row: dict) -> dict:
    """نرخ سد تا کجا بالا برود که سیگنال بماند؛ بالاتر از آن می‌افتد."""
    base = annualized(row)
    if row.get("kind") == "parity" or base["annualized_pct"] is None:
        return {"ceiling_pct": None, "detail": "این ردیف بازده سالانه ندارد (بله/نه است)."}
    ceiling = float(base["annualized_pct"])
    survives_now = bool(survives(row)["survives"])
    if not survives_now:
        detail = (f"سقف نرخ سد این ردیف {ceiling:.3f}٪ است، ولی همین امروز نرخ سد فعلی از آن "
                  f"بالاتر است؛ یعنی این سیگنال حالا نمی‌گذرد و این سقف بی‌فایده است.")
    else:
        detail = (f"تا وقتی بازده مؤثر جایگزین (نرخ سد) زیر {ceiling:.3f}٪ بماند، این ردیف "
                  f"می‌ماند؛ از آن بالاتر می‌افتد.")
    return {"ceiling_pct": round(ceiling, 3), "annualized_pct": round(ceiling, 3),
            "survives_now": survives_now, "detail": detail}


def margin_distance(row: dict) -> dict:
    """چند درصد حرکت مخالف، حساب را به اخطاریهٔ مارجین‌کال می‌رساند.

    واحدها باید یکی باشند (تومان با تومان یا ریال با ریال). اگر وجه تضمین و ارزش قرارداد در دو
    واحد متفاوت وارد شده باشند، عدد بی‌معنا می‌شود؛ پس این‌جا سازگاری هم سنجیده می‌شود و در صورت
    ناهم‌خوانی، صریح گفته می‌شود — نه اینکه عدد عجیب چاپ شود.
    """
    if row.get("kind") == "sizing":
        return {"ok": False, "detail": "ردیف اندازهٔ موقعیت، معامله نیست."}

    def num(x) -> float:
        try:
            return float(x or 0.0)
        except (TypeError, ValueError):
            return 0.0

    margin = num(row.get("margin_per_contract"))
    price = num(row.get("strike") or row.get("future") or row.get("spot")
                or row.get("stock_price"))
    size = num(row.get("contract_size"))
    notional = num(row.get("notional_per_contract"))
    src: list[str] = []
    estimated = False

    if not notional and size and price:
        notional = size * price
        src.append(f"ارزش قرارداد = اندازهٔ قرارداد ({size:,.0f}) × قیمت ({price:,.0f})")
    if not notional and margin:
        notional = margin / sj.INITIAL_RATIO_DEFAULT
        estimated = True
        src.append(f"ارزش قرارداد از وجه تضمین ثبت‌شده ÷ نسبت اولیهٔ "
                   f"{int(sj.INITIAL_RATIO_DEFAULT * 100)}٪ برآورد شد")
    if not notional and price:
        notional = price
        estimated = True
        src.append("فقط قیمت واحد در دست بود؛ ارزش قرارداد تقریبی است")
    if not margin:
        margin = notional * sj.INITIAL_RATIO_DEFAULT
        estimated = True
        src.append(f"وجه تضمین با نسبت اولیهٔ {int(sj.INITIAL_RATIO_DEFAULT * 100)}٪ برآورد شد")
    if not notional or not margin:
        return {"ok": False, "detail": "بدون وجه تضمین و ارزش قرارداد، فاصله تا مارجین‌کال "
                                       "حساب نمی‌شود. این دو عدد را از کارگزاری بگیرید."}

    out = sj.margin_call(contracts=1, margin_per_contract=margin, notional_per_contract=notional)
    if not out.get("ok"):
        return out
    if out["move_pct"] >= 100:
        return {"ok": False, "unit_mismatch": True,
                "margin_per_contract": margin, "notional_per_contract": notional,
                "detail": (f"عدد به‌دست‌آمده ({out['move_pct']:.0f}٪ حرکت مخالف) نامعقول است؛ "
                           f"معمولاً یعنی وجه تضمین ({margin:,.0f}) و ارزش قرارداد "
                           f"({notional:,.0f}) در دو واحد متفاوت (تومان/ریال) نوشته شده‌اند. "
                           f"هر دو را به یک واحد برگردانید.")}
    out["estimated"] = estimated
    out["source"] = ("حد نگهداری ۷۰٪ وجه تضمین اولیه (رویهٔ بورس) و تسویهٔ روزانه؛ عدد برای "
                     "لحظهٔ ورود است." + ((" · " + " · ".join(src)) if src else ""))
    return out


def sizing_stress(row: dict, *, capital: float = 20_000_000_000.0, risk_pct: float = 0.20) -> dict:
    """اگر کارگزاری وجه تضمین را گران کند، چند قرارداد کم می‌شود؟"""
    E = engine()
    margin = float(row.get("margin_per_contract") or 0.0)
    if not margin:
        return {"ok": False, "detail": "وجه تضمین این ردیف در اسنپ‌شات نیست."}
    base = E.position_size(capital, margin, risk_pct)
    worse = E.position_size(capital, margin * MARGIN_STRESS, risk_pct)
    return {"ok": True, "contracts_now": base["contracts"], "contracts_if_margin_up": worse["contracts"],
            "margin_now": margin, "margin_if_up": margin * MARGIN_STRESS,
            "lost_pct": (round((base["contracts"] - worse["contracts"]) / base["contracts"] * 100, 1)
                         if base["contracts"] else 0.0)}


def feasibility(row: dict, *, min_liquidity: int = 20, max_spread_pct: float = 0.03) -> dict:
    """اجرا شدنی است یا نه: نقدشوندگی و اسپرد. شوک این‌جا روی «بازده» اثر ندارد، روی «شدن/نشدن» دارد."""
    liq = row.get("liquidity_contracts_per_day")
    spread = row.get("spread_pct")
    half = (liq / 2) if isinstance(liq, (int, float)) else None
    triple = (spread * 3) if isinstance(spread, (int, float)) else None
    return {
        "liquidity": liq, "liquidity_half": half,
        "liquidity_ok_now": (liq is None or liq >= min_liquidity),
        "liquidity_ok_if_half": (half is None or half >= min_liquidity),
        "spread_pct": (round(spread * 100, 4) if isinstance(spread, (int, float)) else None),
        "spread_x3_pct": (round(triple * 100, 4) if isinstance(triple, (int, float)) else None),
        "spread_ok_now": (spread is None or spread <= max_spread_pct),
        "spread_ok_if_x3": (triple is None or triple <= max_spread_pct),
        "rules": f"حداقل حجم روز {min_liquidity} قرارداد · حداکثر اسپرد {max_spread_pct * 100:.1f}٪",
    }


SHOCKS = (
    ("لغزش اجرا ۰٫۵٪", {"slip_pct": SLIP_PCT}),
    (f"حرکت مخالف {PRICE_SHOCK_PCT:g}٪ قیمت پایه", {"price_shock_pct": PRICE_SHOCK_PCT}),
    ("کارمزد دو برابر", {"fee_mult": 2.0}),
    ("کارمزد سه برابر", {"fee_mult": 3.0}),
    (f"نرخ سد {HURDLE_STRESS * 100:.0f}٪", {"hurdle": HURDLE_STRESS}),
)


def row_label(row: dict, title: str) -> str:
    """عنوان ردیف + نماد، تا دو ردیف هم‌نام (مثلاً دو «مبنا») با هم قاطی نشوند."""
    sym = str(row.get("symbol") or "").strip()
    return f"{title} · {sym}" if sym and sym not in title else title


def stress_row(row: dict) -> dict:
    """یک راهبرد را زیر همهٔ شوک‌ها می‌گذارد و خلاصهٔ تاب‌آوری‌اش را می‌دهد."""
    base = inv.ladder_for(row)
    neutral = survives(row)
    # سنجهٔ صداقت: حالت خنثی باید عیناً همان عدد موتور باشد
    neutral_matches = (row.get("kind") == "parity"
                       or (base.get("annualized_pct") is not None
                           and abs(float(neutral["annualized_pct"]) - float(base["annualized_pct"])) < 0.01))
    results = []
    for label, kw in SHOCKS:
        got = survives(row, **kw)
        annual = got.get("annualized_pct")
        if row.get("kind") == "parity":
            ok = bool(got.get("survives"))
            value = "صرفه دارد" if ok else "صرفه ندارد"
        else:
            ok = bool(got.get("survives"))
            value = "—" if annual is None else f"{annual:.3f}٪"
        results.append({"shock": label, "value": value, "survives": ok,
                        "value_raw": (None if row.get("kind") == "parity" else annual)})
    passed = sum(1 for r in results if r["survives"])
    fate = next((r["shock"] for r in results if not r["survives"]), "")
    if not base["survives"]:
        # ردیفی که امروز هم زیر نرخ سد است، «شکستِ شوک» ندارد؛ از قبل افتاده.
        fate = "از قبل زیر نرخ سد است"
    # کم‌ترین حاشیهٔ پس از شوک: «رد کرد ولی لبِ مرز» با «راحت رد کرد» یکی نیست.
    margins = [float(r["value_raw"]) - base["hurdle_pct"] for r in results
               if isinstance(r.get("value_raw"), (int, float))]
    min_margin = round(min(margins), 3) if margins else None
    dist = margin_distance(row)
    return {
        "kind": row.get("kind"), "title": row_label(row, base["title"]), "given": base["given"],
        "annualized_pct": base["annualized_pct"], "hurdle_pct": base["hurdle_pct"],
        "margin_pp": base["margin_pp"], "survives_today": base["survives"],
        "neutral_matches_engine": neutral_matches,
        "shocks": results, "shocks_total": len(results), "shocks_passed": passed,
        "resilience_pct": round(passed / len(results) * 100, 1),
        "first_failure": fate, "min_margin_pp": min_margin,
        "fee_tolerance": fee_tolerance(row), "hurdle_ceiling": hurdle_ceiling(row),
        "margin": dist, "sizing": sizing_stress(row) if row.get("kind") == "basis" else None,
        "feasibility": feasibility(row),
        "fees_pct": base.get("fees_pct"),
        "verdict_today": base.get("verdict"),
    }


def stress(rows: list[dict] | None = None) -> dict:
    """همهٔ راهبردهای دارای «نوع» را می‌سنجد (بدون ردیف اندازهٔ موقعیت)."""
    rows = rows if rows is not None else inv.fallback_rows()
    out_rows = []
    for row in rows:
        if not row.get("kind") or row.get("kind") == "sizing":
            continue
        out_rows.append(stress_row(row))
    out_rows.sort(key=lambda r: (-(r["survives_today"] or False), -r["resilience_pct"]))
    solid = [r for r in out_rows if r["survives_today"] and r["resilience_pct"] >= 80
             and (r["min_margin_pp"] is None or r["min_margin_pp"] >= 5)]
    weak = [r for r in out_rows if r["survives_today"] and r["resilience_pct"] < 80]
    marginal = [r for r in out_rows if r["survives_today"] and r["resilience_pct"] >= 80
                and r["min_margin_pp"] is not None and r["min_margin_pp"] < 5]
    dead = [r for r in out_rows if not r["survives_today"]]
    return {
        "version": VERSION,
        "rows": out_rows,
        "counts": {"checked": len(out_rows), "solid": len(solid), "weak": len(weak),
                   "marginal": len(marginal), "dead": len(dead)},
        "solid": [r["title"] for r in solid],
        "weak": [r["title"] for r in weak],
        "marginal": [r["title"] for r in marginal],
        "dead": [r["title"] for r in dead],
        "shocks": [s[0] for s in SHOCKS],
        "honesty": ("«نرخ تاب‌آوری» یعنی سهم شوک‌هایی که راهبرد از آن‌ها سالم بیرون آمده است؛ "
                    "این عدد احتمال سود نیست و هیچ‌جا به‌عنوان احتمال سود به کار نمی‌رود."),
    }


def to_md(doc: dict) -> str:
    L = [f"# آزمون تاب‌آوری راهبردها — نسخهٔ {VERSION}", "",
         f"سنجیده‌شده: {doc['counts']['checked']} راهبرد · شوک‌های آزمون: {'، '.join(doc['shocks'])}", "",
         f"> {doc['honesty']}", ""]
    L += ["## ۱. خلاصهٔ یک‌نگاهی", "",
          "| راهبرد | بازده امروز | نرخ سد | می‌ماند؟ | تاب‌آوری | اولین شوکی که می‌اندازد |",
          "| --- | --- | --- | --- | --- | --- |"]
    for r in doc["rows"]:
        annual = "—" if r["annualized_pct"] is None else f"{r['annualized_pct']:.3f}٪"
        L.append(f"| {r['title']} | {annual} | {r['hurdle_pct']:.1f}٪ | "
                 f"{'بله' if r['survives_today'] else 'نه'} | {r['resilience_pct']:.0f}٪ | "
                 f"{r['first_failure'] or '— سخت‌جان'} |")
    L += ["", "## ۲. زیر هر شوک، چه اتفاقی می‌افتد", ""]
    for r in doc["rows"]:
        L += [f"### {r['title']}", "",
              f"- بازده امروز: {r['annualized_pct'] if r['annualized_pct'] is not None else '—'} · "
              f"حاشیهٔ روی سد: {r['margin_pp']} واحد درصد · کارمزد لحاظ‌شده: {r['fees_pct']}٪", "",
              "| شوک | نتیجه | می‌ماند؟ |", "| --- | --- | --- |"]
        for s in r["shocks"]:
            L.append(f"| {s['shock']} | {s['value']} | {'بله' if s['survives'] else 'نه'} |")
        if r["kind"] != "parity":
            ft = r["fee_tolerance"]
            hc = r["hurdle_ceiling"]
            L += ["", f"- **کارمزد چه‌قدر قابل تحمل است:** {ft['detail']}"]
            L += [f"- **سقف نرخ سد:** {hc['detail']}"]
        mg = r["margin"]
        if mg.get("ok"):
            L += [f"- **فاصله تا اخطاریهٔ مارجین‌کال:** {mg['move_pct']:.2f}٪ حرکت مخالف "
                  f"(بر پایهٔ {mg['maintenance_pct']}٪ حد نگهداری). {mg['source']}"]
            if mg.get("price_level"):
                L += [f"  - {mg['price_note']}"]
        else:
            L += [f"- **مارجین‌کال:** {mg.get('detail')}"]
        if r.get("sizing") and r["sizing"].get("ok"):
            s = r["sizing"]
            L += [f"- **اگر وجه تضمین ۲۰٪ گران شود:** از {s['contracts_now']} قرارداد به "
                  f"{s['contracts_if_margin_up']} قرارداد می‌رسد ({s['lost_pct']}٪ کوچک‌تر)."]
        f = r["feasibility"]
        L += [f"- **اجرا شدنی بودن:** {f['rules']} — نقدشوندگی فعلی {f['liquidity']} قرارداد "
              f"(نصف شود: {'می‌شود' if f['liquidity_ok_if_half'] else 'نمی‌شود'}) · اسپرد فعلی "
              f"{f['spread_pct']}٪ (سه برابر شود: {'می‌شود' if f['spread_ok_if_x3'] else 'نمی‌شود'})", ""]
    L += ["## ۳. نتیجه‌گیری صادقانه", "",
          f"- سخت‌جان‌ها (همهٔ شوک‌ها را رد کردند): {'، '.join(doc['solid']) or '—'}",
          f"- لرزان‌ها (با شوک کوچک می‌افتند): {'، '.join(doc['weak']) or '—'}",
          f"- لبِ مرز (رد کردند، ولی حاشیهٔ پس از شوک کمتر از ۵ واحد درصد): "
          f"{'، '.join(doc.get('marginal') or []) or '—'}",
          f"- امروز افتاده‌ها: {'، '.join(doc['dead']) or '—'}", "",
          "هرچه نرخ تاب‌آوری پایین‌تر باشد، آن ردیف بیشتر به «حالت خوبِ بازار» وابسته است؛ با "
          "سرمایهٔ کوچک، فقط ردیف‌های سخت‌جان ارزش بررسی دارند.", ""]
    return "\n".join(L)


def build(rows: list[dict] | None = None, *, write: bool = True,
          html: Path | str | None = None, md: Path | str | None = None,
          jsonf: Path | str | None = None) -> dict:
    doc = stress(rows)
    doc["md_text"] = to_md(doc)
    if write:
        body = ['<div class="honest"><b>این پرونده شوک‌آزمون است، نه تبلیغ.</b> هر راهبرد را با '
                'شرایطی که واقعاً پیش می‌آید دوباره حساب می‌کنیم و می‌گوییم کجا می‌افتد. '
                '«نرخ تاب‌آوری» احتمال سود نیست: فقط نشان می‌دهد راهبرد با بدترشدن شرایط چقدر '
                'دوام می‌آورد.</div>',
                f"<p class=\"sub\">{rk.esc(doc['honesty'])}</p>",
                "<h2>۱. خلاصهٔ یک‌نگاهی</h2>",
                '<table><thead><tr><th>راهبرد</th><th class="num">بازده امروز</th>'
                '<th class="num">نرخ سد</th><th>می‌ماند؟</th><th class="num">تاب‌آوری</th>'
                '<th>اولین شوکی که می‌اندازد</th></tr></thead><tbody>']
        for r in doc["rows"]:
            annual = "—" if r["annualized_pct"] is None else f"{r['annualized_pct']:.3f}٪"
            body.append(f"<tr><td>{rk.esc(r['title'])}</td><td class=\"num\">{annual}</td>"
                        f"<td class=\"num\">{r['hurdle_pct']:.1f}٪</td>"
                        f"<td>{'بله ✅' if r['survives_today'] else 'نه ❌'}</td>"
                        f"<td class=\"num\">{r['resilience_pct']:.0f}٪</td>"
                        f"<td>{rk.esc(r['first_failure'] or '— سخت‌جان')}</td></tr>")
        body.append("</tbody></table><h2>۲. زیر هر شوک</h2>")
        for r in doc["rows"]:
            body.append(f"<h3>{rk.esc(r['title'])}</h3>")
            if r["kind"] != "parity":
                body.append(f"<p class=\"sub\">بازده امروز {annual_of(r)} · حاشیه روی سد "
                            f"{r['margin_pp']} واحد درصد · کارمزد {r['fees_pct']}٪</p>")
            body.append('<table><thead><tr><th>شوک</th><th class="num">نتیجه</th><th>می‌ماند؟</th>'
                        '</tr></thead><tbody>')
            for s in r["shocks"]:
                body.append(f"<tr><td>{rk.esc(s['shock'])}</td><td class=\"num\">{rk.esc(s['value'])}</td>"
                            f"<td>{'بله ✅' if s['survives'] else 'نه ❌'}</td></tr>")
            body.append("</tbody></table>")
            ft, hc = r["fee_tolerance"], r["hurdle_ceiling"]
            if r["kind"] != "parity":
                body.append(f"<p class=\"note\"><b>کارمزد:</b> {rk.esc(ft['detail'])}<br>"
                            f"<b>سقف نرخ سد:</b> {rk.esc(hc['detail'])}</p>")
            mg = r["margin"]
            if mg.get("ok"):
                body.append(f"<p class=\"note\"><b>مارجین‌کال:</b> {mg['move_pct']:.2f}٪ حرکت مخالف. "
                            f"{rk.esc(mg.get('source', ''))}</p>")
            f = r["feasibility"]
            body.append(f"<p class=\"hint\">اجرا شدنی بودن — {rk.esc(f['rules'])}: نقدشوندگی "
                        f"{f['liquidity']} (نصف: {'می‌شود' if f['liquidity_ok_if_half'] else 'نمی‌شود'}) · "
                        f"اسپرد {f['spread_pct']}٪ (سه‌برابر: "
                        f"{'می‌شود' if f['spread_ok_if_x3'] else 'نمی‌شود'})</p>")
        body += ["<h2>۳. نتیجه‌گیری</h2><ul>",
                 f"<li><b>سخت‌جان‌ها:</b> {rk.esc('، '.join(doc['solid']) or '—')}</li>",
                 f"<li><b>لرزان‌ها:</b> {rk.esc('، '.join(doc['weak']) or '—')}</li>",
                 f"<li><b>لبِ مرز:</b> {rk.esc('، '.join(doc.get('marginal') or []) or '—')}</li>",
                 f"<li><b>امروز افتاده‌ها:</b> {rk.esc('، '.join(doc['dead']) or '—')}</li></ul>",
                 '<p class="sub">✍️ تهیه‌کنندهٔ جزوات: <b>Masoud Mojarabian</b> · 📱 +989126630554 · '
                 '✈️ <a href="https://t.me/Mojarabian">Telegram: Mojarabian</a> · '
                 '📸 <a href="https://instagram.com/Mojarabian.Art">Instagram: Mojarabian.Art</a></p>']
        hp = Path(html or REPORT_HTML)
        hp.parent.mkdir(parents=True, exist_ok=True)
        hp.write_text(rk.page("آزمون تاب‌آوری راهبردها", "".join(body),
                              subtitle=f"{doc['counts']['checked']} راهبرد × "
                                       f"{len(doc['shocks'])} شوک"), encoding="utf-8")
        Path(md or REPORT_MD).write_text(doc["md_text"], encoding="utf-8")
        Path(jsonf or REPORT_JSON).write_text(json.dumps(doc, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
        doc.update({"html": str(hp), "md": str(md or REPORT_MD), "json": str(jsonf or REPORT_JSON)})
    return doc


def annual_of(r: dict) -> str:
    return "—" if r["annualized_pct"] is None else f"{r['annualized_pct']:.3f}٪"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="آزمون تاب‌آوری راهبردها زیر شوک‌های واقعی")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    doc = build(write=not a.no_write)
    if a.json:
        print(json.dumps(doc, ensure_ascii=False, indent=1))
        return 0
    print(f"آزمون تاب‌آوری — {doc['counts']['checked']} راهبرد · شوک‌ها: {'، '.join(doc['shocks'])}")
    for r in doc["rows"]:
        print(f"  · {r['title']}: بازده {annual_of(r)} · می‌ماند: "
              f"{'بله' if r['survives_today'] else 'نه'} · تاب‌آوری {r['resilience_pct']:.0f}٪"
              + (f" · اولین باخت: {r['first_failure']}" if r["first_failure"] else ""))
    print(f"  سخت‌جان: {'، '.join(doc['solid']) or '—'}")
    print(f"  لرزان: {'، '.join(doc['weak']) or '—'}")
    print(f"  لبِ مرز: {'، '.join(doc.get('marginal') or []) or '—'}")
    print(f"  افتاده: {'، '.join(doc['dead']) or '—'}")
    if doc.get("html"):
        print("  برگه:", doc["html"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
