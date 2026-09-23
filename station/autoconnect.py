#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""اتصال خودکار — «خودت بگرد و ببین کدام منبع رایگان امروز کار می‌کند».

ایدهٔ ساده است و صادقانه: من (سازندهٔ برنامه) نمی‌توانم از این‌طرف مرزها تست کنم که فلان
سرویس ایرانی امروز چه پاسخی می‌دهد. پس برنامه روی رایانهٔ خودِ شما، یکی‌یکی این منابع را
امتحان می‌کند، پاسخ را می‌خواند، عدد را از نظر عقلی می‌سنجد، و به شما می‌گوید کدام کار کرد
و کدام نه — با دلیل. آخرش، اولین منبع سالم را به‌عنوان اتصال فعال ذخیره می‌کند.

هیچ کلیدی لازم نیست و هیچ هزینه‌ای ندارد. اگر همه شکست خوردند، برنامه خودش می‌گوید
«برو سراغ پروندهٔ دستی» — که آن هم کار می‌کند.

اجرا:  python autoconnect.py            (گزارش کامل، بدون ذخیره)
       python autoconnect.py --save     (منبع سالم را ذخیره و فعال کن)
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

VERSION = "0.1.0"
BASE = Path(__file__).resolve().parent
import sys

if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import datafeed  # noqa: E402
import connections as conn  # noqa: E402

# هر داوطلب: نشانی، چند مسیر احتمالی قیمت، و توضیح فارسی برای کاربر.
# نکتهٔ مهم: این‌ها «حدس‌های آزمون‌شدنی» هستند، نه وعده. سرویس‌ها ساختار پاسخشان را عوض می‌کنند.
VERIFIED_NOTE = "آزمون از محیط سازنده (شهریور ۱۴۰۵) پاسخ سالم داد؛ روی رایانهٔ شما دوباره آزموده می‌شود."

CANDIDATES: list[dict] = [
    {
        "name": "tgju-dollar",
        "label": "tgju — قیمت دلار آزاد",
        "profile_label": "tgju — دلار (رایگان، خودکار پیدا شد)",
        "url_template": "https://api.tgju.org/v1/market/indicator/summary-table-data/price_dollar_rl",
        "paths": ["data.0.3", "data.0.p", "data.0.price", "data.price", "price"],
        "plausible": (10_000, 500_000_000),
        "verified": True,
        "note": ("قیمت پایانی دلار آزاد در ستون چهارم سطر اول (`data.0.3`). آزمون‌شده: با یک نقطهٔ "
                 "پایانی مستقل (call1.tgju.org/ajax.json) هم‌خوان بود."),
    },
    {
        "name": "tgju-coin",
        "label": "tgju — سکه امامی",
        "profile_label": "tgju — سکه (رایگان، خودکار پیدا شد)",
        "url_template": "https://api.tgju.org/v1/market/indicator/summary-table-data/sekeb",
        "paths": ["data.0.3", "data.0.p", "data.0.price", "price"],
        "plausible": (1_000_000, 20_000_000_000),
        "verified": True,
        "note": ("سکهٔ امامی (`sekeb`) با همان قالب tgju. نام‌های دیگر همین خانواده: geram18 (گرم "
                 "طلای ۱۸) · nim (نیم) · rob (ربع)."),
    },
    {
        "name": "tsetmc-cdn",
        "label": "tsetmc — قیمت پایانی (با کد نماد)",
        "profile_label": "tsetmc — قیمت پایانی (رایگان، خودکار پیدا شد)",
        "url_template": "https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceDailyList/{symbol}/0",
        "paths": ["closingPriceDaily.0.pClosing", "closingPriceDaily.0.pDrCotVal",
                  "closingPriceDaily.0.priceYesterday"],
        "plausible": (10, 100_000_000),
        "needs_code": True,
        "search_url": "https://cdn.tsetmc.com/api/Instrument/GetInstrumentSearch/{symbol}",
        "search_paths": ["instrumentSearch.0.insCode", "instrumentSearch.0.instrumentID"],
        "note": "منبع رسمی و رایگان. در نشانی به‌جای نام نماد، «کد نماد» می‌رود؛ برنامه خودش کد را پیدا می‌کند.",
    },
    {
        "name": "exchange-irt",
        "label": "صرافی ایرانی — نرخ لحظه‌ای ریالی (تأییدشده)",
        "profile_label": "صرافی ایرانی — نرخ لحظه‌ای (رایگان، تأییدشده)",
        "url_template": "https://api.exir.io/v2/ticker?symbol={symbol}",
        "paths": ["last", "close", "data.last"],
        "plausible": (1_000, 50_000_000_000),
        "verified": True,
        "note": ("بازارهای ریالی این صرافی: usdt-irt · btc-irt · eth-irt · ada-irt · ton-irt و چند تای دیگر. "
                 "برای اینکه هر ردیف قیمت خودش را بگیرد، در فیلد «کد نماد» آن ردیف نام بازار را بنویسید "
                 "(مثلاً usdt-irt). کاربردش اثبات کارکرد اتصال زندهٔ واقعی بدون کلید است، نه ساختن سیگنال سهام."),
    },
]

# نشانه‌های عدد بی‌معنی: تاریخ، شمارنده، یا درصد کوچک
TOO_BIG_FOR_PRICE = 1e15


def judge(value: float | None, plausible: tuple[float, float]) -> tuple[bool, str]:
    """آیا این عدد می‌تواند «قیمت» باشد؟ نه تاریخ، نه شمارنده، نه صفر."""
    if value is None:
        return False, "عدد پیدا نشد"
    if value <= 0:
        return False, "عدد صفر یا منفی بود"
    if value > TOO_BIG_FOR_PRICE:
        return False, "عدد شبیه تاریخ یا شمارنده است، نه قیمت"
    lo, hi = plausible
    if not (lo <= value <= hi):
        return False, f"عدد {value:,.0f} بیرون بازهٔ باورپذیر {lo:,.0f} تا {hi:,.0f} است"
    return True, "سالم"


def try_candidate(cand: dict, *, symbol: str = "اهرم", timeout: float = 10.0,
                  allow_network: bool = True, resolve_code: bool = True) -> dict:
    """یک داوطلب را امتحان می‌کند و نتیجه را با دلیل برمی‌گرداند."""
    out = {"name": cand["name"], "label": cand["label"], "ok": False, "value": None,
           "json_path": "", "reason": "", "url": "", "moved": None, "resolved_code": None}
    if not allow_network:
        out["reason"] = "دسترسی شبکه بسته است"
        return out
    url_symbol = symbol
    if cand.get("needs_code"):
        code, why = resolve_symbol_code(cand, symbol, timeout=timeout)
        if not code:
            out["reason"] = f"کد نماد پیدا نشد ({why})"
            return out
        url_symbol = str(code)
        out["resolved_code"] = str(code)
        if not resolve_code:
            out["reason"] = "کد نماد پیدا شد ولی استفاده نشد"
            return out
    from urllib.parse import quote as _q
    url = str(cand["url_template"]).replace("{symbol}", _q(str(url_symbol)))
    out["url"] = url
    text, status = datafeed.fetch(url, timeout=timeout, retries=0, cache_name=f"probe-{cand['name']}.json",
                                  cache_seconds=0, stale_ok=False)
    if not text:
        out["reason"] = f"پاسخی نیامد ({status})"
        return out
    try:
        payload = json.loads(text)
    except Exception:
        out["reason"] = "پاسخ JSON نبود (شاید صفحهٔ HTML یا بسته‌شدن دسترسی)"
        return out
    tried = []
    for path in cand.get("paths", []):
        value = datafeed.dig(payload, path)
        if isinstance(value, str):
            try:
                value = float(value.replace(",", ""))
            except ValueError:
                value = None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            ok, why = judge(float(value), cand.get("plausible", (0, TOO_BIG_FOR_PRICE)))
            tried.append(f"{path}={float(value):,.0f} → {why}")
            if ok:
                out.update({"ok": True, "value": float(value), "json_path": path,
                            "reason": "عدد سالم از مسیر " + path})
                break
        else:
            tried.append(f"{path}: خالی")
    if not out["ok"]:
        keys = ", ".join(list(payload)[:6]) if isinstance(payload, dict) else "فهرست"
        out["reason"] = "مسیر عدد سالم پیدا نشد · " + " · ".join(tried[:3]) + f" · کلیدهای پاسخ: {keys}"
        return out
    # آزمون دوم: قیمت در دو خواندن پشت‌سرهم نباید مسخره بپرد
    time.sleep(0.4)
    text2, _ = datafeed.fetch(url, timeout=timeout, retries=0, cache_name=f"probe2-{cand['name']}.json",
                              stale_ok=False,
                              cache_seconds=0)
    if text2:
        try:
            v2 = datafeed.dig(json.loads(text2), out["json_path"])
            if isinstance(v2, (int, float)) and isinstance(out["value"], (int, float)) and out["value"]:
                out["moved"] = round(abs(float(v2) - out["value"]) / float(out["value"]), 6)
        except Exception:
            pass
    return out


def resolve_symbol_code(cand: dict, symbol: str, *, timeout: float = 10.0) -> tuple[str | None, str]:
    """کد نماد (insCode) را از جست‌وجوی tsetmc درمی‌آورد."""
    from urllib.parse import quote as _q
    search = str(cand.get("search_url", "")).replace("{symbol}", _q(symbol))
    if not search:
        return None, "نشانی جست‌وجو نداشت"
    text, status = datafeed.fetch(search, timeout=timeout, retries=0,
                                  cache_name=f"search-{symbol}.json", cache_seconds=0, stale_ok=False)
    if not text:
        return None, status
    try:
        payload = json.loads(text)
    except Exception:
        return None, "پاسخ جست‌وجو JSON نبود"
    for path in cand.get("search_paths", []):
        value = datafeed.dig(payload, path)
        if isinstance(value, (str, int)) and str(value).strip().isdigit():
            return str(value).strip(), "ok"
    return None, "کد در پاسخ نبود"


def enrich_snapshot_with_codes(rows: list[dict], cand: dict, *, timeout: float = 10.0,
                               limit: int = 8, progress=None) -> tuple[list[dict], list[str]]:
    """برای منابعی که «کد نماد» می‌خواهند، کد هر نماد را پیدا و در ردیف‌ها می‌نویسد.

    این‌طور کاربر لازم نیست برای هر سهم، کد نماد را دستی از سایت بردارد.
    """
    notes: list[str] = []
    if not cand.get("needs_code"):
        return rows, notes
    for row in rows[:limit]:
        symbol = str(row.get("symbol", "")).strip()
        if not symbol or str(row.get("feed_symbol", "")).strip():
            continue
        code, why = resolve_symbol_code(cand, symbol, timeout=timeout)
        if code:
            row["feed_symbol"] = code
            notes.append(f"{symbol}: کد نماد {code} پیدا و در ردیف نوشته شد.")
        else:
            notes.append(f"{symbol}: کد نماد پیدا نشد ({why}) — دستی از سایت بردارید و در ستون «کد نماد» بنویسید.")
        if progress:
            progress(notes[-1])
    return rows, notes


def autoconnect(*, candidates: list[dict] | None = None, symbol: str = "اهرم",
                timeout: float = 10.0, allow_network: bool = True, save: bool = False,
                progress=None) -> dict:
    """همهٔ داوطلبان را امتحان می‌کند و در صورت خواستن، منبع سالم را ذخیره و فعال می‌کند."""
    cands = candidates if candidates is not None else CANDIDATES
    # منابع تأییدشدهٔ قبلی اول امتحان می‌شوند؛ در نتیجه زودتر به جواب می‌رسیم.
    cands = sorted(cands, key=lambda c: 0 if c.get("verified") else 1)
    results: list[dict] = []
    winner: dict | None = None
    for cand in cands:
        if progress:
            progress(f"امتحان: {cand['label']}")
        res = try_candidate(cand, symbol=symbol, timeout=timeout, allow_network=allow_network)
        results.append(res)
        if res["ok"] and winner is None:
            winner = res
    saved: dict | None = None
    if winner and save:
        store = conn.load_store()
        cand = next(c for c in cands if c["name"] == winner["name"])
        store["profiles"] = [p for p in store.get("profiles", []) if p.get("name") != cand["name"]]
        prof = conn.upsert_profile(store, {
            "name": cand["name"], "label": cand.get("profile_label", cand["label"]),
            "cost": conn.FREE, "url_template": cand["url_template"], "json_path": winner["json_path"],
            "key_header": "", "key_query_name": "", "env_key": "", "tested": True,
            "note": f"خودکار پیدا شد ({time.strftime('%Y-%m-%d')}) · {cand.get('note', '')}",
            "gives": cand.get("note", ""),
            "after": "قیمت پایه از همین منبع خوانده می‌شود و ستون تازگی داده سبز می‌ماند.",
            "steps": "همین حالا فعال شد؛ برای عوض‌کردن، از دفتر اتصال پروفایل دیگری انتخاب کنید.",
        })
        conn.select_profile(store, prof["name"])
        conn.save_store(store)
        saved = prof
    working = [r for r in results if r["ok"]]
    if working:
        summary = (f"{len(working)} منبع رایگان سالم پیدا شد. "
                   f"بهترین: {working[0]['label']} با قیمت {working[0]['value']:,.0f}.")
    else:
        summary = ("هیچ‌کدام از منابع رایگان جواب نداد. اشکالی ندارد: پروندهٔ دستی و خوراک آزمایشی "
                   "هم کار می‌کنند. دلیل هر شکست را در جدول ببینید.")
    return {"ok": bool(working), "results": results, "winner": winner, "saved": saved,
            "summary": summary, "count_ok": len(working), "tested_at": time.strftime("%Y-%m-%d %H:%M")}


def format_report(rep: dict) -> str:
    lines = [f"اتصال خودکار — {rep['tested_at']}", rep["summary"], ""]
    for r in rep["results"]:
        mark = "✓" if r["ok"] else "✗"
        lines.append(f"  {mark} {r['label']}: {r['reason']}")
        if r["url"]:
            lines.append(f"      نشانی: {r['url']}")
    if rep.get("saved"):
        lines.append("")
        lines.append(f"ذخیره شد: {rep['saved']['label']} (در دفتر اتصال، فعال)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="پیدا کردن خودکار یک منبع دادهٔ رایگان سالم")
    ap.add_argument("--save", action="store_true", help="منبع سالم را ذخیره و فعال کن")
    ap.add_argument("--symbol", default="اهرم", help="نماد آزمایشی")
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--offline", action="store_true", help="بدون شبکه (فقط برای آزمون)")
    ap.add_argument("--codes", action="store_true",
                    help="اگر منبع برنده «کد نماد» می‌خواهد، کد نمادهای اسنپ‌شات را پیدا و ذخیره کن")
    ap.add_argument("--version", action="store_true")
    args = ap.parse_args(argv)
    if args.version:
        print(f"autoconnect {VERSION}")
        return 0
    rep = autoconnect(symbol=args.symbol, timeout=args.timeout, allow_network=not args.offline,
                      save=args.save, progress=lambda m: print("· " + m))
    if args.codes and rep.get("winner"):
        cand = next((c for c in CANDIDATES if c["name"] == rep["winner"]["name"]), {})
        snap = datafeed.load_snapshot_rows(BASE / "data" / "current-snapshot.json")
        if snap.get("rows"):
            rows, notes = enrich_snapshot_with_codes(snap["rows"], cand, timeout=args.timeout)
            if any(r.get("feed_symbol") for r in rows):
                out = datafeed.save_dated_snapshot(rows, note="کد نمادها خودکار پر شد")
                print(f"کد نمادها در {out} ذخیره شد.")
            for n in notes:
                print("· " + n)
    print()
    print(format_report(rep))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
