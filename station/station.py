#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ایستگاه — رابط گرافیکی گام‌به‌گام برای جذب، محاسبه، تصمیم و راستی‌آزمایی.

هشت گام، هر گام یک کار روشن:
  ۱) خوش‌آمد و بررسی سلامت
  ۲) منبع داده (نمونه / دستی / زندهٔ واقعی) + راهنمای خرید داده
  ۳) تنظیمات ریاضی و ریسک
  ۴) خبر و هشدار (اختیاری)
  ۵) اجرا و محاسبه
  ۶) نتیجه و تصمیم (تأیید یا رد انسانی)
  ۷) پس‌آزمایی روی دادهٔ تاریخ
  ۸) بستهٔ تحویل شرکت (برای راستی‌آزمایی آن‌ها)

قانون آهنین برنامه: هیچ سفارشی خودکار فرستاده نمی‌شود. تصمیم و مسئولیت با انسان است.
اجرای دستی برنامهٔ واقعی:  python station.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.1.0"
BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
EXPORT = BASE / "export"
DEMO_HISTORY = BASE / "demo" / "history-demo.csv"
SNAPSHOT_FILE = DATA / "current-snapshot.json"
DASHBOARD_FILE = DATA / "dashboard.html"
BACKTEST_HTML = DATA / "backtest.html"
BACKTEST_CSV = DATA / "backtest.csv"
DESK_DIR = (BASE.parent / "desk").resolve()
KODAL_DIR = (BASE.parent / "kodal-alert").resolve()
TOOLS_DIR = (BASE.parent / "tools").resolve()
CREDIT = ("تهیه‌کننده: Masoud Mojarabian · https://www.instagram.com/Mojarabian.Art/ · "
          "tel:+989126630554 · https://t.me/Mojarabian")

for p in (str(BASE), str(DESK_DIR), str(KODAL_DIR), str(TOOLS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import datafeed  # noqa: E402
import backtest as bt  # noqa: E402

try:
    import desk as deskmod  # noqa: E402
except Exception as e:  # pragma: no cover
    deskmod = None  # type: ignore
    _DESK_IMPORT_ERROR = e

try:
    import kodal_alert as kodal  # noqa: E402
except Exception as e:  # pragma: no cover
    kodal = None  # type: ignore
    _KODAL_IMPORT_ERROR = e

STEPS = [
    ("health", "خوش‌آمد و بررسی سلامت"),
    ("data", "منبع داده"),
    ("settings", "تنظیمات ریاضی و ریسک"),
    ("news", "خبر و هشدار"),
    ("run", "اجرا و محاسبه"),
    ("decide", "نتیجه و تصمیم"),
    ("backtest", "پس‌آزمایی روی تاریخ"),
    ("bundle", "بستهٔ تحویل شرکت"),
]

API_GUIDE_ROWS = [
    ("کدال (رسمی)", "اطلاعیه‌ها، صورت‌های مالی، افزایش سرمایه", "رایگان",
     "بدون کلید؛ همین حالا در گام خبر فعال است",
     "هیچ هزینه‌ای ندارد و همین امروز فعال می‌شود."),
    ("tsetmc / مدیریت فناوری", "قیمت پایانی و ریزمعاملات سهام و آپشن", "رایگان ولی بی‌تعهد",
     "بستهٔ پایتونی tsetmc-api یا خواندن مستقیم با قالب نشانی",
     "قیمت پایه به‌روز می‌شود؛ ولی بدون تضمین و بدون پشتیبانی."),
    ("سرویس دادهٔ خریدنی ایرانی", "قیمت زنده، ریزمعاملات، دادهٔ تاریخی",
     "تقریبی: از چند صد هزار تومان در ماه — در سایت فروشنده تأیید کنید",
     "کلید + قالب نشانی + مسیر JSON در همین گام",
     "قیمت پایه هر ۳۰ ثانیه تازه می‌شود، تازگی داده سبز می‌ماند، و پس‌آزمایی روی داد تاریخ واقعی ممکن می‌شود. وجه تضمین همچنان دستی است."),
    ("دادهٔ تاریخی برای پس‌آزمایی", "سری زمانی قیمت آپشن، آتی و گواهی سپرده", "معمولاً داخل همان بستهٔ خریدنی",
     "پروندهٔ CSV با ستون‌های قالب پس‌آزمایی",
     "می‌توانید نرخ برد و خطای پیش‌بینی موتور را با عدد واقعی به شرکت نشان دهید."),
]

CHECK_ITEMS = [
    ("پایتون", lambda: f"نسخهٔ {sys.version.split()[0]}"),
    ("موتور ریاضی", lambda: str(TOOLS_DIR / "derivatives_scout.py")),
    ("میز معاملات", lambda: str(DESK_DIR / "desk.py")),
    ("دیده‌بان کدال", lambda: str(KODAL_DIR / "kodal_alert.py")),
    ("اسنپ‌شات نمونه", lambda: str(DESK_DIR / "market-demo.json")),
    ("تاریخ نمونه", lambda: str(DEMO_HISTORY)),
]


def now_fa() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------- بررسی سلامت
def health_report() -> tuple[bool, list[tuple[str, bool, str]]]:
    items: list[tuple[str, bool, str]] = []
    items.append(("پایتون", True, f"نسخهٔ {sys.version.split()[0]}"))
    try:
        import tkinter  # noqa: F401
        items.append(("کتابخانهٔ گرافیکی tkinter", True, "نصب است"))
    except Exception as e:
        items.append(("کتابخانهٔ گرافیکی tkinter", False, f"نصب نیست: {e} — روی ویندوز پایتون را با گزینهٔ tcl/tk نصب کنید"))
    if deskmod is not None:
        items.append(("میز معاملات", True, f"بارگذاری شد · نسخهٔ {getattr(deskmod, 'VERSION', '?')}"))
        try:
            scout = deskmod.load_scout()
            items.append(("موتور ریاضی مشتقه", True,
                          f"بارگذاری شد · توابع: {', '.join(n for n in ('box_spread','tabei_min_yield','basis_opportunity') if hasattr(scout, n))}"))
        except Exception as e:
            items.append(("موتور ریاضی مشتقه", False, f"بارگذاری نشد: {e}"))
    else:
        items.append(("میز معاملات", False, f"بارگذاری نشد: {_DESK_IMPORT_ERROR}"))
    if kodal is not None:
        items.append(("دیده‌بان کدال", True, f"بارگذاری شد · نسخهٔ {getattr(kodal, 'VERSION', '?')}"))
    else:
        items.append(("دیده‌بان کدال", False, f"بارگذاری نشد: {_KODAL_IMPORT_ERROR}"))
    for name, path in (("اسنپ‌شات نمونه", DESK_DIR / "market-demo.json"),
                       ("تاریخ نمونهٔ پس‌آزمایی", DEMO_HISTORY),
                       ("پایگاه‌دادهٔ نمونهٔ کدال", KODAL_DIR / "data" / "demo.sqlite3")):
        items.append((name, Path(path).exists(), str(path)))
    ok = all(flag for _, flag, _ in items if "نمونهٔ کدال" not in _)
    return ok, items


# ---------------------------------------------------------------- بستهٔ تحویل شرکت
def build_method_html(state: dict) -> str:
    """سند روش کار؛ همان چیزی که شرکت برای راستی‌آزمایی می‌خواند."""
    snap = state.get("snapshot")
    rules = state.get("rules", {})
    src_label = getattr(snap, "source_label", "—")
    freshness = getattr(snap, "freshness_label", "—")
    rows = getattr(snap, "rows", [])
    messages = getattr(snap, "messages", [])
    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8"><title>سند روش کار — ایستگاه تصمیم مشتقه</title>
<style>
 body {{ font-family: Tahoma, "Segoe UI", sans-serif; background:#f6f7f9; color:#1d1d1f; margin:0; line-height:1.95; }}
 header {{ background:#0b3d2e; color:#fff; padding:16px 22px; }}
 main {{ padding:18px 22px 40px; max-width: 980px; }}
 h2 {{ font-size: 16px; margin-top: 24px; border-right: 4px solid #0b3d2e; padding-right: 8px; }}
 table {{ width:100%; border-collapse: collapse; background:#fff; font-size: 13px; }}
 th,td {{ border-bottom:1px solid #e6e8ec; padding:7px 9px; text-align:right; }}
 th {{ background:#eef2f7; }}
 code {{ background:#eef2f7; padding:1px 5px; border-radius:4px; font-family: Consolas, monospace; direction: ltr; display:inline-block; }}
 .box {{ background:#fff; border:1px solid #e3e6ea; border-radius:10px; padding:12px 14px; margin:10px 0; }}
 .warn {{ background:#fff8e1; border:1px solid #f0e0a8; }}
 footer {{ margin-top:24px; color:#6b7280; font-size:12px; }}
</style></head><body>
<header><h1>سند روش کار — ایستگاه تصمیم مشتقه</h1>
<div style="font-size:12.5px;opacity:.9">نسخهٔ {VERSION} · تاریخ ساخت سند: {now_fa()}</div></header>
<main>
<div class="box warn"><b>این سند چه چیزی را اثبات نمی‌کند:</b> هیچ سود تضمینی در این سیستم وجود ندارد.
خروجی برنامه «پیشنهاد و هشدار» است، نه دستور معامله. تصمیم و مسئولیت حقوقی آن با کاربر انسانی است.
دلیل فنی: طبق ابلاغیهٔ مهر ۱۳۹۹ سازمان بورس، معاملات الگوریتمی خودکار در بورس و فرابورس ایران «تا اطلاع ثانوی» مجاز نیست.</div>

<h2>۱. سیستم چه می‌کند</h2>
<ol>
<li>اسنپ‌شات بازار را می‌خواند (قیمت پایه، زنجیرهٔ آپشن، آتی، اوراق تبعی، وجه تضمین).</li>
<li>هر ردیف را روی موتور ریاضی می‌گذارد: ارزش منصفانه، نرخ تلویحی، تساوی پوت‌کال، باکس‌اسپرد، بازده تبعی، پوشش‌داده‌شده.</li>
<li>هزینه‌ها را کسر می‌کند: کارمزد معاملهٔ آپشن ۰٫۱۰۳٪ هر طرف، کارمزد اعمال ۰٫۰۵٪، مالیات تسویهٔ فیزیکی ۰٫۵٪، کارمزد سهام ۰٫۴۶۴٪ خرید و ۰٫۹۶۴٪ فروش، کارمزد صندوق کالایی ۰٫۱۲٪ هر طرف.</li>
<li>نتیجه را با «نرخ سد» مقایسه می‌کند (بازده مؤثر صندوق درآمد ثابت همان روز).</li>
<li>دروازه‌های ریسک را اعمال و اندازهٔ هر موقعیت را از بودجهٔ وجه تضمین درمی‌آورد.</li>
<li>هشدارهای کدال را به‌عنوان زمینه کنار سیگنال می‌گذارد (خبر به‌تنهایی سیگنال نیست).</li>
</ol>

<h2>۲. وضعیت داده در این بسته</h2>
<table><tr><th>منبع داده</th><td>{src_label}</td></tr>
<tr><th>تازگی داده</th><td>{freshness}</td></tr>
<tr><th>تعداد ردیف محاسبه‌شده</th><td>{len(rows)}</td></tr>
<tr><th>پیام‌های لایهٔ داده</th><td>{' · '.join(messages) if messages else '—'}</td></tr></table>

<h2>۳. قواعد ریسک فعال (همان‌ها که در محاسبه اجرا شد)</h2>
<table>
<tr><th>سرمایهٔ مبنا</th><td>{rules.get('capital', 0):,.0f}</td></tr>
<tr><th>نرخ سد (سالانه)</th><td>{rules.get('hurdle', 0) * 100:.2f} درصد</td></tr>
<tr><th>کف حاشیهٔ راهبردهای آربیتراژی</th><td>{rules.get('min_edge_arbitrage_pct')} واحد درصد</td></tr>
<tr><th>کف حاشیهٔ راهبردهای اهرمی</th><td>{rules.get('min_edge_leveraged_pct')} واحد درصد</td></tr>
<tr><th>سقف کل وجه تضمین</th><td>{rules.get('max_margin_pct', 0) * 100:.0f} درصد سرمایه</td></tr>
<tr><th>سقف هر موقعیت</th><td>{rules.get('max_position_pct', 0) * 100:.0f} درصد بودجهٔ وجه تضمین</td></tr>
<tr><th>سقف موقعیت‌های هم‌زمان</th><td>{rules.get('max_positions')}</td></tr>
<tr><th>کف نقدشوندگی</th><td>{rules.get('min_liquidity_contracts_per_day')} قرارداد در روز</td></tr>
<tr><th>سقف اسپرد خرید‌وفروش</th><td>{rules.get('max_spread_pct', 0) * 100:.1f} درصد</td></tr>
<tr><th>سقف باورپذیری بازده</th><td>{rules.get('max_plausible_arb_pct'):,.0f} درصد (آربیتراژ) و {rules.get('max_plausible_lev_pct'):,.0f} درصد (اهمی)</td></tr>
</table>

<h2>۴. راستی‌آزمایی توسط شما (هفت گام)</h2>
<ol>
<li>در همین رایانه، پوشهٔ میز معاملات را باز کنید و <code>python desk.py list</code> را اجرا کنید؛ باید همان سیگنال‌های فایل <code>02-signals.csv</code> را ببینید.</li>
<li><code>python desk.py packet &lt;شناسه&gt;</code> را اجرا کنید؛ باید همان متن <code>04-packets.txt</code> بیرون بیاید.</li>
<li>یک سیگنال را با ماشین‌حساب دستی بازبینی کنید: فرمول‌ها در بخش ۵ همین سند آمده است.</li>
<li>پروندهٔ <code>05-backtest.html</code> را باز کنید و ببینید موتور روی دادهٔ تاریخ چه نرخ برد و چه خطای پیش‌بینی‌ای داشته است.</li>
<li>یک روز را با اعداد واقعی کارگزاری خودتان عوض کنید و بگذارید سیستم دوباره محاسبه کند؛ خروجی باید با محاسبهٔ دستی شما بخواند.</li>
<li>نرخ سد را با بازده مؤثر صندوق درآمد ثابت همان روز عوض کنید؛ ببینید کدام سیگنال‌ها از دروازه رد می‌شوند.</li>
<li>هر اختلافی دیدید، همان عدد و همان ردیف را برگردانید؛ رفع آن، بخشی از تحویل است.</li>
</ol>

<h2>۵. فرمول‌های به‌کاررفته</h2>
<ul>
<li>ارزش منصفانهٔ آتی: F = S × exp((r + u − y) × T)</li>
<li>نرخ تلویحی: r = ln(F / S) / T</li>
<li>تساوی پوت‌کال: C − P = S − K × exp(−rT)</li>
<li>باکس‌اسپرد: دریافتی قطعی = K₂ − K₁ منهای بدهی اولیه و کارمزدها</li>
<li>اوراق تبعی: بازده = (قیمت اعمال پس از کارمزد فروش − (قیمت سهم پس از کارمزد خرید + قیمت پوت)) ÷ همان هزینهٔ کل</li>
<li>پوشش‌داده‌شده: بازده پرمیوم = پرمیوم پس از کارمزد ÷ بهای سهم پس از کارمزد</li>
<li>سالانه‌سازی: (۱ + بازده دوره)^(۳۶۵ ÷ روز) − ۱</li>
</ul>

<h2>۶. محدودیت‌هایی که باید بدانید</h2>
<ul>
<li>وجه تضمین و مشخصات قرارداد از سامانهٔ کارگزاری می‌آید؛ برنامه آن را حدس نمی‌زند.</li>
<li>در ایران فروش استقراضی وجود ندارد؛ پس نیمهٔ دوم بعضی آربیتراژها (reverse conversion) عملاً بسته است و برنامه آن را رد می‌کند.</li>
<li>ریسک اجرا (نگرفتن پاها هم‌زمان)، توقف نماد، و نکول ناشر در محاسبهٔ ریاضی نیست و فقط در دروازه‌ها هشدار داده شده است.</li>
<li>دادهٔ نمونه‌ای که همراه برنامه است ساختگی است؛ برای نمایش کارکرد است و برای ارائه به شرکت کافی نیست.</li>
</ul>

<footer>ساختهٔ ایستگاه نسخهٔ {VERSION} · {CREDIT}</footer>
</main></body></html>"""


def signals_csv(db_path: Path, path: Path) -> int:
    """همهٔ سیگنال‌های پایگاه‌داده را در CSV می‌ریزد؛ اگر پایگاه‌داده نبود، صفر."""
    if deskmod is None:
        return 0
    try:
        d = deskmod.Desk(db_path)
    except Exception:
        return 0
    sigs = d.all(limit=1000)
    cols = ["sid", "ts", "symbol", "kind", "name", "annualized_pct", "score_pp", "go",
            "status", "contracts", "unit", "margin_locked", "gate_note"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for s in sigs:
            w.writerow({"sid": s.sid, "ts": "", "symbol": s.symbol, "kind": s.kind,
                        "name": deskmod.KIND_LABELS.get(s.kind, s.kind),
                        "annualized_pct": s.annualized_pct, "score_pp": s.score_pp,
                        "go": int(s.go), "status": s.status, "contracts": s.contracts,
                        "unit": s.unit, "margin_locked": round(s.margin_locked, 0),
                        "gate_note": s.gate_note})
    return len(sigs)


def _count(db_path: Path, status: str) -> int:
    if deskmod is None:
        return 0
    try:
        return len(deskmod.Desk(db_path).all(status, 500))
    except Exception:
        return 0



def _usage_block() -> dict:
    """خلاصهٔ گواهی استفادهٔ موفق برای مانیفست بسته (بدون شمارهٔ حساب و بدون عدد مالی)."""
    try:
        import usage_meter as usagemod
        s = usagemod.summary()
        return {"success_total": s.get("success_total"), "active_days": s.get("active_days"),
                "today": s.get("today"), "chain_ok": s.get("chain_ok"),
                "broken_at": s.get("broken_at"), "kept_local": s.get("kept_local"),
                "detail": ("دفتر استفادهٔ موفق فقط روی همین رایانه است و هیچ عدد مالی در آن نیست؛ "
                           "برای ساخت گواهی دواِمضا: پنل مدیریت ← گواهی استفادهٔ موفق.")}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def build_bundle(state: dict, out_dir: Path | None = None, evidence_dir: Path | None = None) -> Path:
    """بستهٔ راستی‌آزمایی برای شرکت: گزارش، سیگنال‌ها، بسته‌های سفارش، روش کار، پس‌آزمایی، شاهدها و مانیفست.

    شاهدها = کارنامهٔ آزمون، برگهٔ آزمون سرمایه‌گذار و پروندهٔ سرمایه‌گذار (اگر ساخته شده باشند).
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out = Path(out_dir) if out_dir else EXPORT / f"bundle-{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    files: list[dict] = []
    admin_notes: list[str] = []
    if not DASHBOARD_FILE.exists() and deskmod is not None:
        # نصب تازه: داشبورد هنوز ساخته نشده. خودمان می‌سازیم تا چک‌لیست بسته به پروندهٔ نبوده
        # اشاره نکند (حتی اگر خالی باشد، صریح می‌گوید «هنوز تصمیمی ثبت نشده»).
        try:
            cfg = dict(getattr(deskmod, "DEFAULT_CONFIG", {}))
            cfg.update({k: v for k, v in (state.get("rules") or {}).items() if k in cfg} or {})
            deskmod.build_dashboard(deskmod.Desk(), cfg, DASHBOARD_FILE)
            admin_notes.append("داشبورد تازه ساخته شد (هنوز تصمیمی ثبت نشده بود) و در بسته آمد.")
        except Exception as e:
            admin_notes.append(f"داشبورد ساخته نشد ({type(e).__name__}: {e})؛ در گام ۵ "
                               "«نمایش داشبورد» را بزنید و بسته را دوباره بگیرید.")
    if DASHBOARD_FILE.exists():
        shutil.copy2(DASHBOARD_FILE, out / "01-dashboard.html")
        files.append({"file": "01-dashboard.html", "desc": "داشبورد تصمیم‌ها (تأیید، رد، انتظار تأیید)"})

    db_path = (DESK_DIR / "data" / "desk.sqlite3")
    n = signals_csv(db_path, out / "02-signals.csv")
    files.append({"file": "02-signals.csv", "desc": f"فهرست کامل {n} سیگنال با دلیل دروازه‌ها"})

    (out / "03-method.html").write_text(build_method_html(state), encoding="utf-8")
    files.append({"file": "03-method.html", "desc": "سند روش کار و چک‌لیست راستی‌آزمایی شرکت"})

    packets: list[str] = []
    if deskmod is not None:
        try:
            d = deskmod.Desk(db_path)
            for s in d.all("approved", 200) + d.all("pending", 200):
                packets.append(deskmod.order_packet(s))
        except Exception as e:
            packets.append(f"خواندن پایگاه‌داده ممکن نشد: {type(e).__name__}: {e}")
    (out / "04-packets.txt").write_text("\n\n" + "=" * 70 + "\n\n".join(packets) if packets
                                       else "بستهٔ سفارشی تأیید نشده است.", encoding="utf-8")
    files.append({"file": "04-packets.txt", "desc": "بستهٔ سفارش سیگنال‌های تأییدشده و منتظر تأیید"})

    if state.get("backtest_result"):
        if BACKTEST_HTML.exists():
            shutil.copy2(BACKTEST_HTML, out / "05-backtest.html")
            files.append({"file": "05-backtest.html", "desc": "گزارش پس‌آزمایی روی دادهٔ تاریخ"})
        if BACKTEST_CSV.exists():
            shutil.copy2(BACKTEST_CSV, out / "06-backtest-rows.csv")
            files.append({"file": "06-backtest-rows.csv", "desc": "سطر به سطر نتیجهٔ پس‌آزمایی"})

    # اجازه‌نامه و گواهی استفاده: اگر صادر شده‌اند، سند چاپی‌شان تازه ساخته می‌شود تا در بسته بیاید
    ev_for_doc = Path(evidence_dir) if evidence_dir else DATA
    client_name = "________________"
    try:
        import license as licmod
        if licmod.read_license():
            client_name = str((licmod.read_license() or {}).get("client") or client_name)
            licmod.build_document(path=ev_for_doc / "license-doc.md",
                                  html_path=ev_for_doc / "license-doc.html")
            admin_notes.append("سند چاپی اجازه‌نامه از پروندهٔ فعلی ساخته شد.")
        else:
            admin_notes.append("اجازه‌نامه‌ای صادر نشده؛ سند مجوز در بسته نیست. "
                               "از پنل مدیریت (بخش «مجوز دسترسی») بسازید و بسته را دوباره بگیرید.")
    except Exception as e:
        admin_notes.append(f"ساخت سند مجوز ممکن نشد: {type(e).__name__}: {e}")

    # گواهی استفاده هم تازه ساخته شود تا بسته، عددهای لحظهٔ ساخت را نشان دهد (نه فایل قدیمی)
    try:
        import usage_meter as usagemod
        h, m = usagemod.build_statement(usagemod.summary(), client=client_name,
                                        html_path=ev_for_doc / "usage-statement.html",
                                        md_path=ev_for_doc / "usage-statement.md")
        admin_notes.append("گواهی استفاده از دفتر همین رایانه ساخته شد.")
    except Exception as e:
        admin_notes.append(f"گواهی استفاده ساخته نشد ({type(e).__name__}: {e})؛ "
                           "در پنل مدیریت بخش «گواهی استفادهٔ موفق» بسازید.")

    # شاهدهای آزمون و پرونده: اگر ساخته شده‌اند، داخل بسته هم می‌روند تا شرکت خودش بازبینی کند
    evidence: list[dict] = []
    ev_dir = Path(evidence_dir) if evidence_dir else DATA
    for src_name, out_name, desc in (
            ("selftest-report.html", "08-selftest-report.html",
             "کارنامهٔ آزمون ۱۰ دقیقه‌ای: هر مورد دو بار حساب شده، موتور و حساب دستی مستقل"),
            ("exam-sheet.html", "09-exam-sheet.html",
             "برگهٔ آزمون سرمایه‌گذار: اول حدس خودش، بعد پاسخ و راه چک با ماشین‌حساب"),
            ("investor-dossier.html", "10-investor-dossier.html",
             "پروندهٔ سرمایه‌گذار: قواعد، سه شاهد، محدودیت‌ها، و اثر انگشت پرونده‌ها"),
            ("investor-dossier.md", "11-investor-dossier.md",
             "نسخهٔ متنی پروندهٔ سرمایه‌گذار برای ایمیل"),
            ("signal-verdict.html", "12-signal-verdict.html",
             "برگهٔ داوری سیگنال بیرونی: می‌ماند/می‌افتد، نقطهٔ برگشت و فاصله تا مارجین‌کال"),
            ("investor-blind-test.html", "13-blind-test-sheet.html",
             "برگهٔ آزمون کور سرمایه‌گذار با جای امضا و کلید زنجیره"),
            ("diagnostic-report.html", "14-diagnostic-report.html",
             "گزارش عیب‌یابی: نسخه‌ها، سلامت اجزا، وضعیت اتصال (برای پشتیبانی)"),
            ("license-doc.html", "15-license-doc.html",
             "سند چاپی اجازه‌نامهٔ دسترسی: نام مشتری، مدت، امضای چکسام و جای امضای دو طرف"),
            ("license-doc.md", "16-license-doc.md", "نسخهٔ متنی اجازه‌نامه برای ایمیل"),
            ("usage-statement.html", "17-usage-statement.html",
             "گواهی استفادهٔ موفق: چه کاری چند بار انجام شد، با اثر انگشت زنجیرهٔ دفتر"),
            ("usage-statement.md", "18-usage-statement.md", "نسخهٔ متنی گواهی استفاده برای ایمیل")):
        src = ev_dir / src_name
        if src.exists():
            shutil.copy2(src, out / out_name)
            data = src.read_bytes()
            files.append({"file": out_name, "desc": desc})
            evidence.append({"file": out_name, "bytes": len(data),
                             "sha256": hashlib.sha256(data).hexdigest()[:16],
                             "built_at": datetime.fromtimestamp(src.stat().st_mtime).strftime("%Y-%m-%d %H:%M")})

    access = None
    try:
        import license as licmod  # noqa: A004
        access = licmod.verify()
    except Exception as e:                                  # نبود اجازه‌نامه، خطا نیست
        access = {"state": "نامعلوم", "ok": True, "detail": f"{type(e).__name__}: {e}"}

    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "station_version": VERSION,
        "data_mode": state.get("data_mode"),
        "data_source_label": getattr(state.get("snapshot"), "source_label", "—"),
        "data_freshness": getattr(state.get("snapshot"), "freshness_label", "—"),
        "rows": len(getattr(state.get("snapshot"), "rows", [])),
        "rules": state.get("rules", {}),
        "signals": {"total": n, "pending": _count(db_path, "pending"), "approved": _count(db_path, "approved")},
        "backtest_summary": (state.get("backtest_result") or {}).get("summary"),
        "files": files,
        "evidence": evidence,
        "access": access,
        "usage_certificate": _usage_block(),
        "admin_notes": admin_notes,
        "limitations": ["هیچ سفارش خودکاری ارسال نمی‌شود",
                        "هیچ سود تضمینی وجود ندارد",
                        "وجه تضمین و مشخصات قرارداد باید از کارگزاری تأیید شود"],
        "credit": CREDIT,
    }
    (out / "07-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    files.append({"file": "07-manifest.json", "desc": "شناسنامهٔ فنی بسته (نسخه‌ها، پارامترها، شمارش‌ها)"})

    checklist = [
        "# چک‌لیست راستی‌آزمایی برای شرکت (پنج دقیقه)",
        "",
        "۱. `03-method.html` را باز کنید و بخش «راستی‌آزمایی توسط شما» را گام‌به‌گام اجرا کنید.",
        "۲. `02-signals.csv` را با خروجی `python desk.py list` در پوشهٔ میز معاملات مقایسه کنید؛ باید یکی باشد.",
        "۳. یک ردیف را با ماشین‌حساب دستی بازبینی کنید (فرمول‌ها در `03-method.html` بخش ۵).",
        "۴. `05-backtest.html` را ببینید: نرخ برد، خطای مثبت کاذب، و خطای پیش‌بینی.",
        "۵. `08-selftest-report.html` را ببینید و دو موردش را با ماشین‌حساب چک کنید؛ `09-exam-sheet.html` همین را برای پرسیدن از خودتان دارد.",
        "۶. یک روز را با اعداد واقعی کارگزاری خودتان جایگزین کنید و بگذارید سیستم دوباره محاسبه کند.",
        "۷. `07-manifest.json` را برای نسخه‌ها، پارامترها و اثر انگشت شاهدها ببینید.",
        "۸. `10-investor-dossier.html` خلاصهٔ همهٔ این‌ها را در یک صفحه آورده است.",
        "۹. `15-license-doc.html` و `17-usage-statement.html` را ببینید: مجوز دسترسی (با امضا) و "
        "گواهی استفادهٔ موفق؛ هر دو با یک فرمان بازتولیدشدنی‌اند.",
        "",
        "یادآوری: خروجی این بسته «پیشنهاد و هشدار» است؛ هیچ سفارشی خودکار ارسال نشده و هیچ سود تضمینی وجود ندارد.",
        "",
        *[f"- {n}" for n in admin_notes],
    ]
    (out / "README-FA.md").write_text("\n".join(checklist), encoding="utf-8")
    files.append({"file": "README-FA.md", "desc": "چک‌لیست راستی‌آزمایی"})

    state["bundle_dir"] = out
    return out


def open_path(path: Path) -> None:
    """باز کردن پوشه یا پرونده با برنامهٔ پیش‌فرض سیستم."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


# ---------------------------------------------------------------- رابط گرافیکی
def import_tk():
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
        return tk, ttk, filedialog, messagebox
    except Exception as e:  # pragma: no cover
        print("کتابخانهٔ گرافیکی tkinter نصب نیست:", e)
        print("روی ویندوز: پایتون را از سایت رسمی با گزینهٔ «tcl/tk and IDLE» نصب کنید.")
        print("روی لینوکس: sudo apt install python3-tk")
        raise SystemExit(2)


class Station:
    def __init__(self, root, tk, ttk, filedialog, messagebox):
        self.tk, self.ttk, self.filedialog, self.messagebox = tk, ttk, filedialog, messagebox
        self.root = root
        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.frames: dict[int, object] = {}
        self.index = 0
        self.state: dict = {
            "data_mode": "sim",
            "file_path": "",
            "live_cfg": dict(datafeed.DEFAULT_LIVE_CONFIG),
            "key": "",
            "snapshot": None,
            "rules": {
                "capital": 20_000_000_000, "hurdle": 0.39,
                "min_edge_arbitrage_pct": 3.0, "min_edge_leveraged_pct": 5.0,
                "max_margin_pct": 0.20, "max_position_pct": 0.35, "max_positions": 3,
                "min_liquidity_contracts_per_day": 20, "max_spread_pct": 0.03,
                "max_plausible_arb_pct": 250.0, "max_plausible_lev_pct": 400.0,
            },
            "use_kodal": True,
            "kodal_db": str(KODAL_DIR / "data" / "demo.sqlite3"),
            "backtest_result": None,
            "bundle_dir": None,
        }
        # اتصالی که در رابط مرورگری ذخیره کرده‌اید، در نسخهٔ دسکتاپ هم خودکار فعال می‌شود.
        try:
            import connections as _conn
            _active = _conn.active_or_none()
        except Exception:
            _active = None
        if _active:
            self.state["data_mode"] = "live"
            self.state["live_cfg"] = _active["live_cfg"]
            self.state["key"] = _active["key"]
        self.font = self.pick_font()
        self.build_window()
        self.show_step(0)
        self.root.after(150, self.drain_queue)

    # ---------- پایه‌ها
    def pick_font(self) -> tuple[str, int]:
        try:
            from tkinter import font as tkfont
            families = set(tkfont.families())
            for name in ("Tahoma", "Segoe UI", "Vazirmatn", "Noto Naskh Arabic", "DejaVu Sans"):
                if name in families:
                    return (name, 10)
        except Exception:
            pass
        return ("TkDefaultFont", 10)

    def f(self, size: int = 10, bold: bool = False) -> tuple:
        return (self.font[0], size, "bold") if bold else (self.font[0], size)

    def build_window(self) -> None:
        self.root.title(f"ایستگاه تصمیم مشتقه — نسخهٔ {VERSION}")
        self.root.geometry("1180x760")
        self.root.minsize(980, 640)

        head = self.tk.Frame(self.root, bg="#0b3d2e", height=64)
        head.pack(side="top", fill="x")
        self.tk.Label(head, text="ایستگاه تصمیم مشتقه", bg="#0b3d2e", fg="white",
                      font=self.f(15, True)).pack(anchor="e", padx=14, pady=(8, 0))
        self.tk.Label(head, text="محاسبه · هشدار · تأیید انسانی · بستهٔ راستی‌آزمایی برای شرکت",
                      bg="#0b3d2e", fg="#cfe6dd", font=self.f(9)).pack(anchor="e", padx=14)
        self.badge = self.tk.Label(head, text="منبع داده: تنظیم نشده", bg="#0b3d2e", fg="#ffe08a",
                                   font=self.f(9, True))
        self.badge.pack(anchor="w", padx=14, pady=(0, 8))

        body = self.tk.Frame(self.root)
        body.pack(side="top", fill="both", expand=True)

        side = self.tk.Frame(body, bg="#f0f2f5", width=250)
        side.pack(side="right", fill="y")
        self.tk.Label(side, text="گام‌ها", bg="#f0f2f5", font=self.f(11, True)).pack(anchor="e", padx=12, pady=(10, 6))
        self.step_labels: list = []
        for i, (_, title) in enumerate(STEPS):
            lbl = self.tk.Label(side, text=f"{i + 1}. {title}", bg="#f0f2f5", fg="#333",
                                font=self.f(10), anchor="e", justify="right", wraplength=225)
            lbl.pack(anchor="e", fill="x", padx=10, pady=2)
            lbl.bind("<Button-1>", lambda _e, idx=i: self.show_step(idx))
            self.step_labels.append(lbl)

        self.content = self.tk.Frame(body, bg="white")
        self.content.pack(side="left", fill="both", expand=True)

        foot = self.tk.Frame(self.root, bg="#eef2f7", height=46)
        foot.pack(side="bottom", fill="x")
        self.btn_next = self.ttk.Button(foot, text="گام بعد ▶", command=self.next_step)
        self.btn_next.pack(side="left", padx=10, pady=8)
        self.btn_back = self.ttk.Button(foot, text="◀ گام قبل", command=self.prev_step)
        self.btn_back.pack(side="left", padx=4, pady=8)
        self.status = self.tk.Label(foot, text="آماده", bg="#eef2f7", fg="#333", font=self.f(10, True))
        self.status.pack(side="right", padx=14)

    # ---------- ناوبری
    @property
    def key(self) -> str:
        return STEPS[self.index][0]

    def show_step(self, index: int) -> None:
        """گام‌ها یک بار ساخته و نگه داشته می‌شوند؛ برای نمایش، فقط جابه‌جا می‌شوند."""
        index = max(0, min(index, len(STEPS) - 1))
        self.index = index
        if index not in self.frames:
            builder = getattr(self, f"build_{STEPS[index][0]}")
            self.frames[index] = builder(self.content)
        for i, frame in self.frames.items():
            try:
                if i == index:
                    frame.pack(fill="both", expand=True)
                else:
                    frame.pack_forget()
            except Exception:
                pass
        for i, lbl in enumerate(self.step_labels):
            lbl.configure(bg="#d7e6df" if i == index else "#f0f2f5",
                          font=self.f(10, True) if i == index else self.f(10))
        self.btn_back.configure(state="normal" if index > 0 else "disabled")
        self.btn_next.configure(text="پایان" if index == len(STEPS) - 1 else "گام بعد ▶")
        self.status.configure(text=f"گام {index + 1} از {len(STEPS)}: {STEPS[index][1]}")

    def next_step(self) -> None:
        self.show_step(self.index + 1 if self.index < len(STEPS) - 1 else self.index)

    def prev_step(self) -> None:
        self.show_step(self.index - 1)

    # ---------- رشته و وظیفه‌های پس‌زمینه
    def log_box(self, parent, height: int = 12):
        frame = self.tk.Frame(parent, bg="white")
        text = self.tk.Text(frame, height=height, font=("Consolas", 9), bg="#0f172a", fg="#d7e6dd",
                            wrap="word", padx=8, pady=6)
        text.pack(side="left", fill="both", expand=True)
        sb = self.ttk.Scrollbar(frame, command=text.yview)
        sb.pack(side="right", fill="y")
        text.configure(yscrollcommand=sb.set, state="disabled")
        frame.pack(fill="both", expand=True, pady=6)
        return text

    def push(self, text: str) -> None:
        self.queue.put(("log", text))

    def drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    for box in self.frames.values():
                        for widget in getattr(box, "winfo_children", lambda: [])():
                            self.append_log_deep(widget, str(payload))
                    self.status.configure(text=str(payload)[:110])
                elif kind == "done":
                    callback = payload
                    if callable(callback):
                        callback()
        except queue.Empty:
            pass
        self.root.after(150, self.drain_queue)

    def append_log_deep(self, widget, text: str) -> None:
        try:
            if not widget.winfo_exists():
                return
            if isinstance(widget, self.tk.Text):
                widget.configure(state="normal")
                widget.insert("end", text + "\n")
                widget.see("end")
                widget.configure(state="disabled")
            for child in widget.winfo_children():
                self.append_log_deep(child, text)
        except Exception:
            return

    def run_async(self, func, on_done=None) -> None:
        def worker():
            try:
                result = func()
                self.queue.put(("done", (lambda r=result: on_done(r)) if on_done else None))
            except Exception as e:
                self.queue.put(("log", f"خطا: {type(e).__name__}: {e}"))
                self.queue.put(("log", traceback.format_exc(limit=3)))
                self.queue.put(("done", None))
        threading.Thread(target=worker, daemon=True).start()

    def card(self, parent, title: str, keys: list[tuple[str, str]]):
        box = self.ttk.LabelFrame(parent, text=title, padding=8)
        box.pack(fill="x", pady=6)
        box.columnconfigure(1, weight=1)
        entries = {}
        for i, (label, key) in enumerate(keys):
            self.tk.Label(box, text=label, font=self.f(10)).grid(row=i, column=0, sticky="e", padx=4, pady=3)
            var = self.tk.StringVar(value=str(self.state["rules"].get(key, "")))
            ent = self.ttk.Entry(box, textvariable=var, width=18)
            ent.grid(row=i, column=1, sticky="e", padx=4, pady=3)
            entries[key] = var
        return box, entries

    # ---------- گام ۱
    def build_health(self, parent):
        frame = self.tk.Frame(parent, bg="white")
        frame.pack(fill="both", expand=True)
        self.tk.Label(frame, text="۱. خوش‌آمد و بررسی سلامت", bg="white", font=self.f(14, True)).pack(anchor="e", padx=14, pady=(12, 4))
        intro = ("این ایستگاه به شما می‌گوید «کجا تفاوت ریاضی قیمت‌ها با نرخ سد از حاشیهٔ اطمینان عبور می‌کند»،\n"
                 "هشدارهای کدال را کنار همان سیگنال می‌گذارد، اندازهٔ هر موقعیت را از بودجهٔ وجه تضمین درمی‌آورد،\n"
                 "و در پایان یک بستهٔ راستی‌آزمایی برای شرکت می‌سازد.\n\n"
                 "قاعدهٔ خودِ ایستگاه: سفارشی خودکار به کارگزاری فرستاده نمی‌شود و هیچ سودی تضمین نمی‌شود؛\n"
                 "خروجی، «عدد و دلیل» است و تصمیم دستِ کاربر می‌ماند.\n\n"
                 "دولوپر: مهندس مسعود مجربیان · همراه: 09126630554 · Telegram: [Mojarabian](https://t.me/Mojarabian) · Instagram: [Mojarabian.Art](https://instagram.com/Mojarabian.Art)")
        self.tk.Label(frame, text=intro, bg="white", justify="right", font=self.f(10)).pack(anchor="e", padx=16)
        self.ttk.Button(frame, text="بررسی سلامت برنامه", command=self.do_health).pack(anchor="e", padx=16, pady=8)
        self.log_box(frame, height=14)
        return frame

    def do_health(self) -> None:
        self.push("در حال بررسی اجزای برنامه…")
        ok, items = health_report()
        for name, flag, note in items:
            self.push(("✓ " if flag else "✗ ") + f"{name}: {note}")
        passed = len([1 for _, flag, _ in items if flag])
        self.push(f"نتیجه: {passed} از {len(items)} بررسی موفق." + ("" if ok else " موارد ناقص را رفع کنید یا به من بگویید."))

    # ---------- گام ۲
    def build_data(self, parent):
        frame = self.tk.Frame(parent, bg="white")
        frame.pack(fill="both", expand=True)
        self.tk.Label(frame, text="۲. منبع داده", bg="white", font=self.f(14, True)).pack(anchor="e", padx=14, pady=(12, 4))
        self.tk.Label(frame, text="یکی از سه مسیر را انتخاب کنید. «زندهٔ واقعی» یعنی قیمت‌ها خودکار به‌روز می‌شوند؛\n"
                                  "اما تا کلید نخریده‌اید، با دادهٔ نمونه یا پروندهٔ دستی هم می‌توانید تمام گام‌ها را ببینید.\n"
                                  "برای همهٔ حالت‌ها، وجه تضمین و مشخصات قرارداد از سامانهٔ کارگزاری خودتان می‌آید.",
                      bg="white", justify="right", font=self.f(10)).pack(anchor="e", padx=16)

        self.mode_var = self.tk.StringVar(value=self.state["data_mode"])
        row = self.tk.Frame(frame, bg="white")
        row.pack(anchor="e", fill="x", padx=16, pady=4)
        for value, label in (("sim", "دادهٔ نمونهٔ همراه برنامه"), ("file", "پروندهٔ دستی JSON (بدون هزینه)"),
                             ("live", "دادهٔ زندهٔ واقعی (سرویس خریدنی)")):
            self.ttk.Radiobutton(row, text=label, value=value, variable=self.mode_var,
                                 command=self.on_mode_change).pack(side="right", padx=8)

        self.mode_text = self.tk.Text(frame, height=5, wrap="word", font=self.f(10), bg="#f8fafc", padx=8, pady=6)
        self.mode_text.pack(fill="x", padx=16, pady=6)
        self.mode_text.configure(state="disabled")

        self.file_card = self.ttk.LabelFrame(frame, text="پروندهٔ اسنپ‌شات (برای حالت دستی و پایهٔ حالت زنده)", padding=8)
        self.file_card.pack(fill="x", padx=16, pady=4)
        self.file_var = self.tk.StringVar(value=self.state.get("file_path", ""))
        self.ttk.Entry(self.file_card, textvariable=self.file_var, width=64).pack(side="right", padx=4)
        self.ttk.Button(self.file_card, text="انتخاب پرونده…", command=self.pick_file).pack(side="right", padx=4)
        self.ttk.Button(self.file_card, text="ساخت قالب نمونه", command=self.make_template).pack(side="right", padx=4)

        self.live_card = self.ttk.LabelFrame(frame, text="اتصال سرویس دادهٔ زنده (کلید و قالب نشانی)", padding=8)
        self.live_card.pack(fill="x", padx=16, pady=4)
        self.live_vars = {}
        rows = [("قالب نشانی سرویس", "url_template", 60, ""),
                ("مسیر قیمت در پاسخ JSON", "json_path", 24, ""),
                ("نام هدر کلید (اختیاری)", "key_header", 18, ""),
                ("نام پارامتر کلید در نشانی", "key_query_name", 18, ""),
                ("کلید سرویس (فقط در همین رایانه)", "key", 34, "*")]
        for label, key, width, mask in rows:
            line = self.tk.Frame(self.live_card, bg="white")
            line.pack(fill="x", pady=2)
            self.tk.Label(line, text=label, font=self.f(10), width=26, anchor="e").pack(side="right", padx=4)
            var = self.tk.StringVar(value=str(self.state["live_cfg"].get(key, "") or self.state.get("key", "")))
            ent = self.ttk.Entry(line, textvariable=var, width=width, show=mask)
            ent.pack(side="right", padx=4)
            self.live_vars[key] = var
        self.ttk.Button(self.live_card, text="آزمایش اتصال و خواندن قیمت زنده",
                        command=self.test_live).pack(anchor="e", padx=4, pady=6)

        self.api_tree = self.ttk.Treeview(frame, columns=("svc", "gives", "cost", "how"), show="headings", height=5)
        for col, title, width in (("svc", "گزینه", 180), ("gives", "چه می‌دهد", 250),
                                  ("cost", "هزینهٔ تقریبی (در سایت فروشنده تأیید کنید)", 300),
                                  ("how", "نحوهٔ اتصال", 320)):
            self.api_tree.heading(col, text=title)
            self.api_tree.column(col, width=width, anchor="e")
        for r in API_GUIDE_ROWS:
            self.api_tree.insert("", "end", values=r)
        self.api_tree.pack(fill="x", padx=16, pady=6)

        self.log_box(frame, height=8)
        self.on_mode_change()
        return frame

    def on_mode_change(self) -> None:
        mode = self.mode_var.get()
        self.state["data_mode"] = mode
        card = datafeed.SOURCE_CARDS[mode]
        text = (f"انتخاب شما: {card['label']}\n"
                f"هزینه: {card['cost']}\n"
                f"چه می‌دهد: {card['gives']}\n"
                f"پس از اتصال، چه تغییر می‌کند: {card['after']}\n"
                f"چگونه: {card['how']}")
        self.mode_text.configure(state="normal")
        self.mode_text.delete("1.0", "end")
        self.mode_text.insert("1.0", text)
        self.mode_text.configure(state="disabled")

    def pick_file(self) -> None:
        path = self.filedialog.askopenfilename(title="انتخاب پروندهٔ اسنپ‌شات JSON",
                                               filetypes=[("JSON", "*.json"), ("همه", "*.*")])
        if path:
            self.file_var.set(path)
            self.state["file_path"] = path

    def make_template(self) -> None:
        p = datafeed.write_snapshot_template(DATA / "snapshot-template.json")
        self.file_var.set(str(p))
        self.state["file_path"] = str(p)
        self.messagebox.showinfo("قالب ساخته شد", f"قالب اسنپ‌شات ساخته شد:\n{p}\n\n"
                                                 "این پرونده را با اعداد واقعی کارگزاری خود پر کنید و همین مسیر را نگه دارید.")

    def test_live(self) -> None:
        for key, var in self.live_vars.items():
            if key == "key":
                self.state["key"] = var.get().strip()
            else:
                self.state["live_cfg"][key] = var.get().strip()
        self.state["file_path"] = self.file_var.get().strip() or self.state.get("file_path", "")
        self.push("آزمایش اتصال…" + (" (کلید وارد نشده؛ بدون کلید هم تلاش می‌شود)" if not self.state["key"] else ""))

        def work():
            snap = datafeed.build_snapshot("live", file_path=self.state["file_path"] or None,
                                           live_cfg=self.state["live_cfg"], key=self.state["key"],
                                           progress=self.push)
            self.state["snapshot"] = snap
            return snap

        def done(snap):
            if snap is None:
                return
            self.push(f"وضعیت: {snap.status} · تازگی: {snap.freshness_label} · ردیف‌ها: {len(snap.rows)}")
            for m in snap.messages:
                self.push("· " + m)
            self.update_badge()
            if snap.status == "ok":
                self.push("از این پس: قیمت پایه هر ۳۰ ثانیه از سرویس خوانده می‌شود و در گزارش، تازگی داده سبز می‌ماند.")
            else:
                self.push("راهنمای رفع: قالب نشانی و مسیر JSON را از مستندات فروشنده بردارید؛ "
                          "اگر عدد در پاسخ تغییر کند، فقط همین دو خط را عوض کنید.")

        self.run_async(work, done)

    def update_badge(self) -> None:
        snap = self.state.get("snapshot")
        if snap is None:
            self.badge.configure(text="منبع داده: تنظیم نشده", fg="#ffe08a")
            return
        color = {"ok": "#9ae6b4", "partial": "#ffe08a", "failed": "#feb2b2"}.get(snap.status, "#ffe08a")
        self.badge.configure(text=f"منبع: {snap.source_label} · تازگی: {snap.freshness_label} · "
                                  f"ردیف: {len(snap.rows)}", fg=color)

    # ---------- گام ۳
    def build_settings(self, parent):
        frame = self.tk.Frame(parent, bg="white")
        frame.pack(fill="both", expand=True)
        self.tk.Label(frame, text="۳. تنظیمات ریاضی و ریسک", bg="white", font=self.f(14, True)).pack(anchor="e", padx=14, pady=(12, 4))
        self.tk.Label(frame, text="این اعداد، تصمیم را عوض می‌کنند. پیش‌فرض‌ها محافظه‌کارانه انتخاب شده‌اند؛\n"
                                  "هر عدد را بنا به شرایط خودتان عوض کنید و بعد دوباره محاسبه بگیرید.",
                      bg="white", justify="right", font=self.f(10)).pack(anchor="e", padx=16)

        box, self.rule_vars = self.card(frame, "پارامترهای اصلی", [
            ("سرمایه (ریال)", "capital"),
            ("نرخ سد سالانه (اعشار، مثلاً 0.39)", "hurdle"),
            ("کف حاشیهٔ آربیتراژ (واحد درصد)", "min_edge_arbitrage_pct"),
            ("کف حاشیهٔ اهرمی (واحد درصد)", "min_edge_leveraged_pct"),
        ])
        box2, self.rule_vars2 = self.card(frame, "دروازه‌های ریسک", [
            ("سقف کل وجه تضمین (اعشار، مثلاً 0.20)", "max_margin_pct"),
            ("سقف هر موقعیت از بودجه (اعشار)", "max_position_pct"),
            ("حداکثر موقعیت هم‌زمان", "max_positions"),
            ("کف نقدشوندگی (قرارداد در روز)", "min_liquidity_contracts_per_day"),
            ("سقف اسپرد (اعشار، مثلاً 0.03)", "max_spread_pct"),
            ("سقف باورپذیری بازدهٔ آربیتراژ", "max_plausible_arb_pct"),
            ("سقف باورپذیری بازدهٔ اهرمی", "max_plausible_lev_pct"),
        ])
        hint = ("نرخ سد را از کجا بیاورم؟ از «بازده مؤثر سالانه» صندوق درآمد ثابت همان روز.\n"
                "در شهریور ۱۴۰۵ این عدد حدود ۳۹ تا ۴۰ درصد بود. اگر نرخ سد را اشتباه بگذارید، همهٔ سیگنال‌ها اشتباه می‌شوند.")
        self.tk.Label(frame, text=hint, bg="#f8fafc", justify="right", font=self.f(10)).pack(anchor="e", padx=16, pady=8)

        def save():
            for source in (self.rule_vars, self.rule_vars2):
                for key, var in source.items():
                    raw = var.get().strip().replace("٬", "").replace(",", "")
                    try:
                        self.state["rules"][key] = float(raw) if "." in raw else int(raw)
                    except ValueError:
                        self.messagebox.showwarning("عدد نامعتبر", f"مقدار «{key}» عدد نیست: {raw}")
                        return
            self.push("تنظیمات ذخیره شد: " + json.dumps(self.state["rules"], ensure_ascii=False))
        self.ttk.Button(frame, text="ذخیرهٔ تنظیمات", command=save).pack(anchor="e", padx=16, pady=6)
        self.log_box(frame, height=8)
        return frame

    # ---------- گام ۴
    def build_news(self, parent):
        frame = self.tk.Frame(parent, bg="white")
        frame.pack(fill="both", expand=True)
        self.tk.Label(frame, text="۴. خبر و هشدار (اختیاری)", bg="white", font=self.f(14, True)).pack(anchor="e", padx=14, pady=(12, 4))
        self.tk.Label(frame, text="خبر به‌تنهایی سیگنال نیست. کارکردش سه چیز است: زمینه، اولویت‌بندی، و ساختن\n"
                                  "«کار بازبینی» برای نمادهایی که خبر مهم دارند ولی در اسنپ‌شات شما نیستند.",
                      bg="white", justify="right", font=self.f(10)).pack(anchor="e", padx=16)
        self.use_kodal = self.tk.BooleanVar(value=self.state["use_kodal"])
        self.ttk.Checkbutton(frame, text="از هشدارهای دیده‌بان کدال استفاده کن",
                             variable=self.use_kodal, command=self.toggle_kodal).pack(anchor="e", padx=16, pady=4)
        line = self.tk.Frame(frame, bg="white")
        line.pack(fill="x", padx=16)
        self.kodal_var = self.tk.StringVar(value=self.state["kodal_db"])
        self.ttk.Entry(line, textvariable=self.kodal_var, width=70).pack(side="right", padx=4)
        self.ttk.Button(line, text="انتخاب پایگاه‌داده…", command=self.pick_kodal).pack(side="right", padx=4)
        btns = self.tk.Frame(frame, bg="white")
        btns.pack(anchor="e", padx=16, pady=6)
        self.ttk.Button(btns, text="اجرای دیده‌بان روی دادهٔ نمونه", command=self.run_kodal_demo).pack(side="right", padx=4)
        self.ttk.Button(btns, text="وارد کردن پروندهٔ اطلاعیه‌ها…", command=self.import_announcements).pack(side="right", padx=4)
        self.ttk.Button(btns, text="نمایش هشدارهای فعلی", command=self.show_alerts).pack(side="right", padx=4)
        self.log_box(frame, height=14)
        return frame

    def toggle_kodal(self) -> None:
        self.state["use_kodal"] = bool(self.use_kodal.get())

    def pick_kodal(self) -> None:
        path = self.filedialog.askopenfilename(title="پایگاه‌دادهٔ دیده‌بان کدال",
                                              filetypes=[("SQLite", "*.sqlite3 *.db"), ("همه", "*.*")])
        if path:
            self.kodal_var.set(path)
            self.state["kodal_db"] = path

    def run_kodal_demo(self) -> None:
        if kodal is None:
            self.messagebox.showerror("دیده‌بان نیست", "پوشهٔ kodal-alert پیدا نشد.")
            return
        self.push("اجرای دیده‌بان روی دادهٔ نمونه…")

        def work():
            cfg = json.loads(json.dumps(kodal.DEFAULT_CONFIG, ensure_ascii=False))
            cfg["db_path"] = str(KODAL_DIR / "data" / "demo.sqlite3")
            cfg["report_path"] = str(KODAL_DIR / "data" / "demo-report.html")
            cfg["min_score_to_alert"] = 40
            store = kodal.Store(cfg["db_path"])
            items = kodal.run_pipeline(cfg, store, ["demo"])
            return items

        def done(items):
            if not items:
                self.push("خروجی نداشت؛ پوشهٔ نمونه را بررسی کنید.")
                return
            for it in items[:12]:
                self.push(f"[{it.score}] {it.direction} · {it.category} · {it.symbol or '-'} · {it.title[:70]}")
            self.state["kodal_db"] = str(KODAL_DIR / "data" / "demo.sqlite3")
            self.kodal_var.set(self.state["kodal_db"])
            self.push(f"{len(items)} هشدار ساخته شد و در پایگاه‌داده ثبت شد.")

        self.run_async(work, done)

    def import_announcements(self) -> None:
        path = self.filedialog.askopenfilename(title="پروندهٔ اطلاعیه‌ها (JSON یا CSV)",
                                              filetypes=[("JSON/CSV", "*.json *.csv"), ("همه", "*.*")])
        if not path or kodal is None:
            return
        self.push(f"وارد کردن اطلاعیه‌ها از {path} …")

        def work():
            cfg = json.loads(json.dumps(kodal.DEFAULT_CONFIG, ensure_ascii=False))
            cfg["db_path"] = self.state["kodal_db"]
            store = kodal.Store(cfg["db_path"])
            items = kodal.load_file_source(path, cfg)
            fresh = [i for i in items if store.add(i)]
            store.commit()
            return fresh

        def done(fresh):
            self.push(f"{len(fresh)} اطلاعیهٔ تازه ثبت شد.")
            self.show_alerts()

        self.run_async(work, done)

    def show_alerts(self) -> None:
        alerts = datafeed.read_alerts(self.state["kodal_db"], 55, 25)
        if not alerts:
            self.push("هشداری نیست (یا پایگاه‌داده خالی است).")
            return
        for a in alerts:
            self.push(f"[{a['score']}] {a['direction']} · {a['category']} · {a['symbol'] or '-'} · {a['title'][:70]}")

    # ---------- گام ۵
    def build_run(self, parent):
        frame = self.tk.Frame(parent, bg="white")
        frame.pack(fill="both", expand=True)
        self.tk.Label(frame, text="۵. اجرا و محاسبه", bg="white", font=self.f(14, True)).pack(anchor="e", padx=14, pady=(12, 4))
        self.tk.Label(frame, text="با یک دکمه: اسنپ‌شات خوانده می‌شود، موتور ریاضی هر ردیف را حساب می‌کند،\n"
                                  "دروازه‌های ریسک اعمال می‌شوند، و داشبورد تصمیم ساخته می‌شود.",
                      bg="white", justify="right", font=self.f(10)).pack(anchor="e", padx=16)
        self.progress = self.ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(fill="x", padx=16, pady=8)
        row = self.tk.Frame(frame, bg="white")
        row.pack(anchor="e", padx=16)
        self.ttk.Button(row, text="شروع محاسبه", command=self.do_run).pack(side="right", padx=4)
        self.ttk.Button(row, text="رفتن به گام نتیجه", command=lambda: self.show_step(5)).pack(side="right", padx=4)
        self.ttk.Button(row, text="بازکردن داشبورد در مرورگر",
                        command=lambda: open_path(DASHBOARD_FILE)).pack(side="right", padx=4)
        self.log_box(frame, height=16)
        return frame

    def materialize_snapshot(self, snap) -> Path:
        rows = []
        for r in snap.rows:
            clean = {k: v for k, v in r.items() if not k.startswith("_")}
            rows.append(clean)
        data = {"as_of": now_fa(), "hurdle": self.state["rules"]["hurdle"],
                "capital": self.state["rules"]["capital"], "rows": rows}
        SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return SNAPSHOT_FILE

    def do_run(self) -> None:
        if deskmod is None:
            self.messagebox.showerror("میز معاملات نیست", "پوشهٔ desk پیدا نشد؛ به من بگویید تا مسیرش را درست کنم.")
            return
        self.progress.start(12)
        self.push("شروع محاسبه…")

        def work():
            mode = self.state["data_mode"]
            if self.state.get("snapshot") is None or mode != "live":
                snap = datafeed.build_snapshot(mode, file_path=self.state.get("file_path") or None,
                                               live_cfg=self.state["live_cfg"], key=self.state.get("key"),
                                               progress=self.push)
                self.state["snapshot"] = snap
            snap = self.state["snapshot"]
            self.push(f"منبع: {snap.source_label} · تازگی: {snap.freshness_label} · ردیف: {len(snap.rows)}")
            for m in snap.messages:
                self.push("· " + m)
            if not snap.rows:
                self.push("هیچ ردیفی برای محاسبه نیست؛ پرونده یا منبع داده را بررسی کنید.")
                return None
            path = self.materialize_snapshot(snap)
            cfg = json.loads(json.dumps(deskmod.DEFAULT_CONFIG, ensure_ascii=False))
            cfg.update(self.state["rules"])
            cfg["capital"] = float(self.state["rules"]["capital"])
            cfg["hurdle"] = float(self.state["rules"]["hurdle"])
            desk = deskmod.Desk()
            kodal_db = self.state["kodal_db"] if self.state.get("use_kodal") else None
            sigs = deskmod.scan_market(path, cfg, desk, kodal_db)
            tasks = deskmod.recheck_tasks(cfg, desk, kodal_db, path) if kodal_db else []
            dash = deskmod.build_dashboard(desk, cfg, DASHBOARD_FILE, tasks)
            return sigs, tasks, dash

        def done(payload):
            self.progress.stop()
            if not payload:
                return
            sigs, tasks, dash = payload
            pending = [s for s in sigs if s.status == "pending"]
            approved = [s for s in sigs if s.status == "approved"]
            rejected = [s for s in sigs if s.status == "rejected"]
            self.push(f"خلاصه: {len(sigs)} سیگنال · {len(pending)} منتظر تأیید · "
                      f"{len(approved)} تأییدشده · {len(rejected)} رد")
            for s in sigs[:25]:
                mark = {"pending": "✅", "approved": "🟢", "rejected": "✖"}.get(s.status, "•")
                ann = f"{s.annualized_pct:.2f}٪" if isinstance(s.annualized_pct, (int, float)) else "—"
                self.push(f"{mark} {s.symbol} · {deskmod.KIND_LABELS.get(s.kind, s.kind)} · "
                          f"بازده {ann} · حاشیه {s.score_pp:,.2f} · {s.contracts:,} {s.unit}")
                if s.status == "rejected":
                    self.push(f"     دلیل رد: {s.gate_note}")
                for a in s.alerts[:2]:
                    self.push(f"     خبر: [{a['score']}] {a['title'][:70]}")
            if tasks:
                self.push("کار بازبینی (خبر مهم بدون دادهٔ بازار):")
                for t in tasks[:10]:
                    self.push(f"     · {t['symbol']}: {t['reason']}")
            self.push(f"داشبورد ساخته شد: {dash}")
            self.update_badge()
            self.show_step(5)

        self.run_async(work, done)

    # ---------- گام ۶
    def build_decide(self, parent):
        frame = self.tk.Frame(parent, bg="white")
        frame.pack(fill="both", expand=True)
        self.tk.Label(frame, text="۶. نتیجه و تصمیم", bg="white", font=self.f(14, True)).pack(anchor="e", padx=14, pady=(12, 4))
        self.tk.Label(frame, text="هر سیگنال را ببینید، دلیل دروازه‌ها را بخوانید، و اگر پذیرفتید تأیید کنید.\n"
                                  "تأیید شما در دفتر ثبت می‌شود و اجرای دوبارهٔ برنامه آن را بازنویسی نمی‌کند.",
                      bg="white", justify="right", font=self.f(10)).pack(anchor="e", padx=16, pady=(0, 6))

        cols = ("sid", "symbol", "kind", "annual", "edge", "size", "margin", "status", "note")
        heads = [("sid", "شناسه", 90), ("symbol", "نماد", 80), ("kind", "راهبرد", 140),
                 ("annual", "بازده سالانه٪", 90), ("edge", "حاشیه", 70), ("size", "اندازه", 110),
                 ("margin", "سرمایه (ریال)", 130), ("status", "وضعیت", 80), ("note", "دلیل / خبر", 360)]
        self.tree = self.ttk.Treeview(frame, columns=cols, show="headings", height=12)
        for c, title, width in heads:
            self.tree.heading(c, text=title)
            self.tree.column(c, width=width, anchor="e")
        self.tree.pack(fill="both", expand=True, padx=16)
        self.tree.bind("<<TreeviewSelect>>", self.on_select_signal)

        actions = self.tk.Frame(frame, bg="white")
        actions.pack(fill="x", padx=16, pady=6)
        self.note_var = self.tk.StringVar()
        self.tk.Label(actions, text="یادداشت تصمیم:", font=self.f(10)).pack(side="right", padx=4)
        self.ttk.Entry(actions, textvariable=self.note_var, width=58).pack(side="right", padx=4)
        self.ttk.Button(actions, text="رد با دلیل", command=lambda: self.decide("rejected")).pack(side="right", padx=4)
        self.ttk.Button(actions, text="تأیید و ساخت بستهٔ سفارش", command=lambda: self.decide("approved")).pack(side="right", padx=4)
        self.ttk.Button(actions, text="به‌روزرسانی فهرست", command=self.refresh_signals).pack(side="right", padx=4)

        self.log_box(frame, height=7)
        self.refresh_signals()
        return frame

    def refresh_signals(self) -> None:
        if deskmod is None:
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        desk = deskmod.Desk()
        self.state["_signals"] = desk.all(limit=300)
        for s in self.state["_signals"]:
            ann = f"{s.annualized_pct:,.2f}" if isinstance(s.annualized_pct, (int, float)) else "—"
            news = " | ".join(a["title"][:60] for a in s.alerts[:1])
            note = (s.gate_note or "") + (f" | خبر: {news}" if news else "")
            self.tree.insert("", "end", iid=s.sid, values=(s.sid, s.symbol,
                                                           deskmod.KIND_LABELS.get(s.kind, s.kind),
                                                           ann, f"{s.score_pp:,.2f}",
                                                           f"{s.contracts:,} {s.unit}",
                                                           f"{s.margin_locked:,.0f}", s.status, note))

    def on_select_signal(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        sid = sel[0]
        sig = next((s for s in self.state.get("_signals", []) if s.sid == sid), None)
        if sig:
            self.push(f"— {sig.symbol} · {sig.kind} · وضعیت {sig.status}")
            self.push("   " + json.dumps(sig.detail, ensure_ascii=False)[:400])
            if sig.alerts:
                for a in sig.alerts[:3]:
                    self.push(f"   خبر: [{a['score']}] {a['title']}")

    def decide(self, action: str) -> None:
        sel = self.tree.selection()
        if not sel:
            self.messagebox.showinfo("انتخاب نشده", "اول یک ردیف از جدول را انتخاب کنید.")
            return
        sid = sel[0]
        note = self.note_var.get().strip()
        desk = deskmod.Desk()
        sig = desk.get(sid)
        if sig is None:
            return
        if action == "approved":
            cap = (sig.detail.get("_policy") or {}).get("cap_total")
            used = desk.locked_margin(exclude_sid=sid) + sig.margin_locked
            count = len([s for s in desk.all("approved") if s.sid != sid])
            max_pos = (sig.detail.get("_policy") or {}).get("max_positions", self.state["rules"]["max_positions"])
            if (cap and used > cap) or count >= max_pos:
                ok = self.messagebox.askyesno(
                    "سقف ریسک",
                    f"تأیید این سیگنال سقف ریسک را رد می‌کند:\n"
                    f"سرمایهٔ درگیر {used:,.0f} از سقف {cap:,.0f} ریال\n"
                    f"موقعیت‌های تأییدشده {count} از {max_pos}\n\n"
                    "باز هم تأیید می‌کنید؟ (در دفتر با برچسب «رد سقف» ثبت می‌شود)")
                if not ok:
                    return
                note = (note + " | تأیید با رد سقف ریسک").strip(" |")
        desk.decide(sid, action, note)
        self.push(("تأیید شد: " if action == "approved" else "رد شد: ") + sid)
        if action == "approved":
            packet = deskmod.order_packet(desk.get(sid))
            self.show_packet(packet)
        self.refresh_signals()

    def show_packet(self, packet: str) -> None:
        win = self.tk.Toplevel(self.root)
        win.title("بستهٔ سفارش — اجرا فقط توسط انسان در سامانهٔ کارگزاری")
        win.geometry("820x600")
        txt = self.tk.Text(win, font=("Consolas", 10), wrap="word", padx=10, pady=10)
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", packet)
        self.ttk.Button(win, text="کپی در حافظه",
                        command=lambda: (self.root.clipboard_clear(), self.root.clipboard_append(packet))).pack(pady=6)
        self.ttk.Button(win, text="بستن", command=win.destroy).pack(pady=(0, 8))

    # ---------- گام ۷
    def build_backtest(self, parent):
        frame = self.tk.Frame(parent, bg="white")
        frame.pack(fill="both", expand=True)
        self.tk.Label(frame, text="۷. پس‌آزمایی روی دادهٔ تاریخ", bg="white", font=self.f(14, True)).pack(anchor="e", padx=14, pady=(12, 4))
        self.tk.Label(frame, text="همان موتوری که در تصمیم زنده کار می‌کند، روی دادهٔ گذشته اجرا می‌شود:\n"
                                  "نرخ برد، خطای مثبت کاذب، فرصت‌های از دست رفته، و خطای پیش‌بینی (انتظار منهای واقعیت) حساب می‌شود.",
                      bg="white", justify="right", font=self.f(10)).pack(anchor="e", padx=16)
        line = self.tk.Frame(frame, bg="white")
        line.pack(fill="x", padx=16, pady=6)
        self.hist_var = self.tk.StringVar(value=str(DEMO_HISTORY))
        self.ttk.Entry(line, textvariable=self.hist_var, width=70).pack(side="right", padx=4)
        self.ttk.Button(line, text="انتخاب پرونده…", command=self.pick_history).pack(side="right", padx=4)
        self.ttk.Button(line, text="ساخت قالب ستون‌ها", command=self.make_history_template).pack(side="right", padx=4)
        btns = self.tk.Frame(frame, bg="white")
        btns.pack(anchor="e", padx=16)
        self.ttk.Button(btns, text="اجرای پس‌آزمایی", command=self.do_backtest).pack(side="right", padx=4)
        self.ttk.Button(btns, text="بازکردن گزارش در مرورگر", command=lambda: open_path(BACKTEST_HTML)).pack(side="right", padx=4)
        self.summary = self.tk.Text(frame, height=6, wrap="word", bg="#f8fafc", font=self.f(10), padx=8, pady=6)
        self.summary.pack(fill="x", padx=16, pady=6)
        self.summary.configure(state="disabled")
        self.log_box(frame, height=10)
        return frame

    def pick_history(self) -> None:
        path = self.filedialog.askopenfilename(title="پروندهٔ تاریخ (CSV یا JSON)",
                                              filetypes=[("CSV", "*.csv"), ("JSON", "*.json"), ("همه", "*.*")])
        if path:
            self.hist_var.set(path)

    def make_history_template(self) -> None:
        p = datafeed.write_history_template(DATA / "history-template.csv")
        self.messagebox.showinfo("قالب ساخته شد", f"قالب ستون‌های پس‌آزمایی:\n{p}\n\n"
                                                 "ستون کلیدی: realized_annualized_pct یعنی «نتیجهٔ واقعی» آن معامله در گذشته. "
                                                 "این ستون در تصمیم هیچ نقشی ندارد و فقط برای سنجش است.")

    def do_backtest(self) -> None:
        path = self.hist_var.get().strip()
        self.push(f"اجرای پس‌آزمایی روی {path} …")

        def work():
            result = bt.run_backtest(path, rules={"min_edge_arbitrage_pct": self.state["rules"]["min_edge_arbitrage_pct"],
                                                  "min_edge_leveraged_pct": self.state["rules"]["min_edge_leveraged_pct"],
                                                  "min_liquidity_contracts_per_day": self.state["rules"]["min_liquidity_contracts_per_day"],
                                                  "max_spread_pct": self.state["rules"]["max_spread_pct"],
                                                  "max_plausible_arb_pct": self.state["rules"]["max_plausible_arb_pct"],
                                                  "max_plausible_lev_pct": self.state["rules"]["max_plausible_lev_pct"]},
                                capital=float(self.state["rules"]["capital"]))
            bt.build_report(result, BACKTEST_HTML)
            bt.write_csv(result, BACKTEST_CSV)
            self.state["backtest_result"] = result
            return result

        def done(result):
            if not result:
                return
            s = result["summary"]
            for p in s["problems"][:5]:
                self.push("· " + p)
            text = (f"سطرها: {s['rows']} · ورود: {s['taken']} · رد: {s['skipped']}\n"
                    f"نرخ برد: {s['hit_rate_pct']:.1f}٪ · خطای مثبت کاذب: {s['false_positive_rate_pct']:.1f}٪ · "
                    f"فرصت از دست رفته: {s['missed_opportunity_rate_pct']:.1f}٪\n"
                    f"میانگین بازده انتظاری ورودها: {s['avg_expected_annualized_pct']:.1f}٪ · "
                    f"میانگین بازده واقعی: {s['avg_realized_annualized_pct']:.1f}٪\n"
                    f"خطای پیش‌بینی (واقعی منهای انتظار): {s['avg_forecast_error_pp']:.1f} واحد درصد\n"
                    f"سرمایه: از {s['start_capital']:,.0f} به {s['final_equity']:,.0f} "
                    f"({s['equity_change_pct']:.1f}٪)\n"
                    + ("هشدار: این پرونده نمونهٔ ساختگی است؛ برای ارائه به شرکت، دادهٔ واقعی خودتان را بدهید."
                       if "history-demo" in str(s["file"]) else ""))
            self.summary.configure(state="normal")
            self.summary.delete("1.0", "end")
            self.summary.insert("1.0", text)
            self.summary.configure(state="disabled")
            self.push(f"گزارش پس‌آزمایی: {BACKTEST_HTML}")
            self.push("درسِ کلیدی: اگر میانگین واقعی از میانگین انتظاری کمتر است، انتظار موتور خوش‌بینانه است؛ "
                      "با دادهٔ خودتان این فاصله را اندازه بگیرید و کف حاشیه را بالا ببرید.")

        self.run_async(work, done)

    # ---------- گام ۸
    def build_bundle(self, parent):
        frame = self.tk.Frame(parent, bg="white")
        frame.pack(fill="both", expand=True)
        self.tk.Label(frame, text="۸. بستهٔ تحویل شرکت", bg="white", font=self.f(14, True)).pack(anchor="e", padx=14, pady=(12, 4))
        self.tk.Label(frame, text="این بسته، همه‌چیز را برای راستی‌آزمایی شرکت در یک پوشه می‌گذارد:\n"
                                  "گزارش تصمیم‌ها، فهرست سیگنال‌ها، سند روش کار، بسته‌های سفارش، نتیجهٔ پس‌آزمایی،\n"
                                  "و یک چک‌لیست که خودشان در پنج دقیقه راستی‌آزمایی کنند.",
                      bg="white", justify="right", font=self.f(10)).pack(anchor="e", padx=16)
        btns = self.tk.Frame(frame, bg="white")
        btns.pack(anchor="e", padx=16, pady=8)
        self.ttk.Button(btns, text="ساخت بستهٔ راستی‌آزمایی", command=self.do_bundle).pack(side="right", padx=4)
        self.ttk.Button(btns, text="بازکردن پوشهٔ بسته", command=self.open_bundle).pack(side="right", padx=4)
        self.ttk.Button(btns, text="نمایش سند روش کار", command=lambda: self.open_method()).pack(side="right", padx=4)
        self.log_box(frame, height=16)
        return frame

    def do_bundle(self) -> None:
        if self.state.get("snapshot") is None:
            self.messagebox.showinfo("داده‌ای نیست", "اول در گام ۲ یک منبع داده انتخاب کنید و در گام ۵ محاسبه بگیرید.")
            return
        try:
            out = build_bundle(self.state)
        except Exception as e:
            self.messagebox.showerror("ساخت بسته ناموفق", f"{type(e).__name__}: {e}")
            return
        self.push(f"بسته ساخته شد: {out}")
        for f in sorted(Path(out).iterdir()):
            self.push(f"  · {f.name}  ({f.stat().st_size:,} بایت)")
        self.push("پیشنهاد ارائه: فایل 03-method.html را بخوانند، بعد 01-dashboard.html را ببینند، "
                  "و بر اساس README-FA.md راستی‌آزمایی کنند.")

    def open_bundle(self) -> None:
        d = self.state.get("bundle_dir")
        if d:
            open_path(Path(d))
        else:
            self.messagebox.showinfo("بسته‌ای ساخته نشده", "اول دکمهٔ ساخت بسته را بزنید.")

    def open_method(self) -> None:
        p = DATA / "method-preview.html"
        p.write_text(build_method_html(self.state), encoding="utf-8")
        open_path(p)


# ---------------------------------------------------------------- اجرا
def demo_state(station: "Station") -> None:
    """حالت نمایش برای آزمون و تصویرسازی: دادهٔ نمونه + یک بار محاسبه."""
    station.state["data_mode"] = "sim"
    snap = datafeed.build_snapshot("sim")
    station.state["snapshot"] = snap
    station.update_badge()
    mode_var = getattr(station, "mode_var", None)
    if mode_var is not None:
        mode_var.set("sim")
        station.on_mode_change()


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="ایستگاه تصمیم مشتقه — رابط گرافیکی گام‌به‌گام")
    ap.add_argument("--smoke", action="store_true", help="آزمون ساخت همهٔ گام‌ها بدون تعامل")
    ap.add_argument("--step", type=int, default=0, help="با کدام گام باز شود (۱ تا ۸)")
    ap.add_argument("--demo-state", action="store_true", help="پر کردن وضعیت با دادهٔ نمونه")
    ap.add_argument("--autorun", action="store_true", help="اجرای خودکار محاسبه و پس‌آزمایی")
    ap.add_argument("--shot", help="گرفتن تصویر از پنجره در این مسیر و بستن برنامه")
    ap.add_argument("--shot-delay", type=float, default=2200, help="تأخیر تصویربرداری (میلی‌ثانیه)")
    ap.add_argument("--version", action="store_true")
    args = ap.parse_args(argv)

    if args.version:
        print(f"station {VERSION}")
        return 0

    tk, ttk, filedialog, messagebox = import_tk()
    root = tk.Tk()
    app = Station(root, tk, ttk, filedialog, messagebox)

    if args.demo_state and not args.smoke:
        demo_state(app)
    if args.step:
        app.show_step(max(0, args.step - 1))

    if args.smoke:
        errors = []
        for i in range(len(STEPS)):
            try:
                app.show_step(i)
                root.update()
            except Exception as e:
                errors.append(f"گام {i + 1}: {type(e).__name__}: {e}")
        try:
            demo_state(app)
            app.show_step(5)
            root.update()
            app.refresh_signals()
            root.update()
        except Exception as e:
            errors.append(f"حالت نمونه: {type(e).__name__}: {e}")
        ok, items = health_report()
        print("آزمون ساخت گام‌ها:")
        for i, (_, title) in enumerate(STEPS):
            print(f"  گام {i + 1} — {title}: ساخته شد")
        for e in errors:
            print("  خطا →", e)
        print(f"بررسی سلامت: {len([1 for _, f, _ in items if f])} از {len(items)} موفق")
        print("SMOKE " + ("OK" if not errors else "FAILED"))
        root.destroy()
        return 0 if not errors else 1

    if args.autorun:
        app.show_step(4)
        app.do_run()
        root.after(2500, app.do_backtest)

    if args.shot:
        def shoot():
            root.update()
            os.system(f'scrot -o "{args.shot}"')
            root.after(200, root.destroy)
        root.after(int(args.shot_delay), shoot)

    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
