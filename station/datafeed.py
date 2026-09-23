#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""لایهٔ دادهٔ ایستگاه — سه حالت: نمونه، فایل دستی، و دادهٔ زندهٔ واقعی.

هدف: یک ساختار یکسان (اسنپ‌شات بازار) از سه مسیر مختلف، تا بقیهٔ برنامه
(موتور ریاضی، دروازه‌های ریسک، داشبورد) هیچ‌وقت نفهمد داده از کجا آمده است.

حالت‌ها:
  sim   → دادهٔ نمونهٔ همراهِ برنامه (برای آموزش و نمایش بدون هیچ هزینه)
  file  → پروندهٔ JSON که خودتان از سامانهٔ کارگزاری یا هر منبعی پر می‌کنید
  live  → قیمت زندهٔ واقعی از یک وب‌سرویس؛ با «قالب نشانی» و «مسیر JSON»
          که در همان صفحهٔ رابط گرافیکی تنظیم می‌شود (بدون نیاز به کدنویسی)

اصل طراحی: هیچ نشانی‌ای در کد ثابت نشده است. همهٔ نشانی‌ها قالب‌اند و در
`config.json` یا در رابط گرافیکی وارد می‌شوند؛ اگر سرویس‌دهنده نشانی‌اش را
عوض کند، فقط همان قالب را ویرایش می‌کنید.
"""
from __future__ import annotations

import csv
import errno
import json
import socket
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.1.0"
BASE = Path(__file__).resolve().parent
DESK_DIR = (BASE.parent / "desk").resolve()
KODAL_DIR = (BASE.parent / "kodal-alert").resolve()
CACHE_DIR = BASE / "data" / "cache"

def coerce_row_numbers(row: dict) -> dict:
    """عددهای رشته‌ای را به عدد تبدیل می‌کند (مثل «21,500» یا "21500").

    کاربر تازه‌کار معمولاً عدد را داخل گیومه می‌گذارد؛ بدون این کار، موتور ریاضی
    آن ردیف را با خطا رد می‌کند. این تابع پرونده‌های دستی را قابل‌استفاده می‌کند.
    """
    for k in SNAPSHOT_NUM_FIELDS:
        v = row.get(k)
        if isinstance(v, str):
            txt = v.strip().replace(",", "").replace("٬", "")
            if txt == "":
                continue
            try:
                row[k] = float(txt)
            except ValueError:
                pass
    return row


# ---------------------------------------------------------------- کارت راهنمای خرید داده
# هزینه‌ها «تقریبی و نیازمند تأیید در سایت فروشنده» هستند؛ هیچ عددی اینجا قطعی نیست.
SOURCE_CARDS: dict[str, dict] = {
    "sim": {
        "label": "دادهٔ نمونهٔ همراه برنامه (بدون هزینه)",
        "cost": "رایگان",
        "gives": "همهٔ فیلدها: قیمت پایه، آتی، زنجیرهٔ آپشن، تبعی، وجه تضمین",
        "after": "همهٔ فیلدها را دستی وارد می‌کنید؛ سیستم کار می‌کند ولی تصمیم روی دادهٔ ساختگی است و برای شرکت قابل ارائه نیست.",
        "how": "هیچ کاری لازم نیست؛ همین حالا با دکمهٔ بعد بروید.",
    },
    "file": {
        "label": "پروندهٔ دستی JSON (بدون هزینه)",
        "cost": "رایگان",
        "gives": "هر فیلدی که خودتان وارد کنید",
        "after": "داده به‌روز نمی‌شود؛ ستون تازگی داده زرد می‌ماند و باید هر روز پرونده را عوض کنید. برای شروع و برای راستی‌آزمایی شرکت کافی است.",
        "how": "یک پروندهٔ JSON با قالب نمونه بسازید (راهنما در گام ۲) و مسیرش را بدهید.",
    },
    "live": {
        "label": "وب‌سرویس داده (ابزار خریدنی؛ توصیهٔ من برای دادهٔ زندهٔ واقعی)",
        "cost": "بسته به سرویس‌دهنده؛ معمولاً از چند صد هزار تومان در ماه شروع می‌شود — قیمت را در سایت فروشنده تأیید کنید",
        "gives": "قیمت زندهٔ سهم و صندوق، ریزمعاملات، و در بعضی سرویس‌ها دادهٔ تاریخی",
        "after": "قیمت پایه هر ۲۰ تا ۶۰ ثانیه خودکار به‌روز می‌شود، ستون تازگی داده سبز می‌شود، و پس‌آزمایی روی دادهٔ واقعی تاریخ ممکن می‌شود. وجه تضمین و مشخصات قرارداد همچنان دستی می‌ماند چون از سامانهٔ کارگزاری می‌آید.",
        "how": "۱) از سرویس‌دهندهٔ ایرانی کلید بگیرید. ۲) در همین گام، کلید و «قالب نشانی» و «مسیر JSON» را پر کنید. ۳) دکمهٔ آزمایش اتصال.",
    },
}

SNAPSHOT_TEMPLATE: dict = {
    "note": ("این یک قالب است، نه دادهٔ واقعی. عددهای هر ردیف را با عدد امروزِ سامانهٔ کارگزاری "
             "خودتان عوض کنید و پرونده را با نام خودتان ذخیره کنید (مثلاً daily-input.json)."),
    "_units": ("hurdle و spread_pct کسری‌اند (0.39 یعنی ۳۹٪ و 0.005 یعنی ۰.۵٪) · capital به ریال · "
               "days = روزهای مانده تا سررسید · prices به ریال · margin_per_contract = وجه تضمین "
               "هر قرارداد (سهم در این قالب: ارزش یک سهم) · liquidity_contracts_per_day = حجم قرارداد روز"),
    "_fields_per_kind": {
        "basis": ["spot", "future", "days"],
        "covered_call": ["spot", "strike", "premium", "days"],
        "tabei": ["stock_price", "put_price", "strike", "days"],
        "box": ["call_low", "put_low", "call_high", "put_high", "strike_low", "strike_high", "days"],
        "parity": ["call", "put", "spot", "strike", "days"],
    },
    "as_of": "تاریخ امروز",
    "hurdle": 0.39,
    "capital": 20000000000,
    "rows": [
        {"symbol": "اهرم", "kind": "basis", "spot": 20000, "future": 22800, "days": 90,
         "storage_annual": 0.0, "margin_per_contract": 20000000, "unit": "قرارداد",
         "liquidity_contracts_per_day": 900, "spread_pct": 0.005},
        {"symbol": "فولاد", "kind": "covered_call", "spot": 7000, "strike": 7600, "premium": 400,
         "days": 45, "margin_per_contract": 7000, "unit": "سهم",
         "liquidity_contracts_per_day": 160, "spread_pct": 0.018},
        {"symbol": "کگل", "kind": "tabei", "stock_price": 9800, "put_price": 40, "strike": 14210,
         "days": 365, "margin_per_contract": 9840, "unit": "سهم",
         "liquidity_contracts_per_day": 240, "spread_pct": 0.02},
        {"symbol": "شپنا", "kind": "box", "call_low": 300, "put_low": 430, "call_high": 175,
         "put_high": 585, "strike_low": 1200, "strike_high": 1500, "days": 45,
         "margin_per_contract": 250000, "unit": "قرارداد",
         "liquidity_contracts_per_day": 12, "spread_pct": 0.045},
        {"symbol": "وبملت", "kind": "parity", "call": 420, "put": 380, "spot": 9000, "strike": 9000,
         "days": 30, "rate": 0.39, "margin_per_contract": 9000, "unit": "سهم",
         "liquidity_contracts_per_day": 80, "spread_pct": 0.02},
    ],
}

DEFAULT_LIVE_CONFIG: dict = {
    "url_template": "",          # مثال: https://api.example.ir/Quote.php?key={key}&l18={symbol}
    "json_path": "data.0.pl",    # مسیر رسیدن به «قیمت پایه» داخل پاسخ JSON
    "key_header": "",            # اگر کلید باید در هدر برود، نام هدر را بنویسید
    "key_query_name": "key",     # اگر کلید در نشانی می‌رود، نام پارامتر
    "timeout_seconds": 12,
    "retries": 1,
    "cache_seconds": 30,
    "field_map": {               # کدام کلید اسنپ‌شات از کدام فیلد بازار پر شود
        "spot": "spot",
        "stock_price": "stock_price",
        "future": "future",
    },
}


# ---------------------------------------------------------------- ابزارها
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg: str) -> None:
    print(msg)


def transient_error(exc: BaseException) -> bool:
    """آیا این خطای شبکه «گذرا» است (ارزش تلاش دوباره دارد) یا قطعی؟"""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code >= 500 or exc.code in (408, 429)
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, socket.gaierror):
        return False
    if isinstance(reason, ConnectionRefusedError):
        return False
    if getattr(reason, "errno", None) in (errno.ECONNREFUSED, errno.EHOSTUNREACH, errno.ENETUNREACH,
                                          errno.EADDRNOTAVAIL):
        return False
    return True


def fetch(url: str, *, timeout: float = 12, retries: int = 1,
          key_header: str = "", key: str = "", cache_name: str | None = None,
          cache_seconds: int = 30, use_cache: bool = True,
          stale_ok: bool = True) -> tuple[str | None, str]:
    """دریافت متن با تلاش مجدد و حافظهٔ نهان. خروجی: (متن یا None، پیام وضعیت).

    stale_ok=False یعنی «اگر شبکه جواب نداد، از حافظهٔ نهان نخوان»؛ این پرچم برای جاهایی
    است که خواندن از حافظهٔ کهنه، «موفقیت دروغین» می‌سازد (سنجش منبع، کاوش پاسخ سرویس).
    هر جا از حافظهٔ نهان خوانده شود، در پیام وضعیت صریح نوشته می‌شود.
    """
    url = ascii_safe_url(url)
    if url.startswith("file:"):
        try:
            return Path(url[5:]).read_text(encoding="utf-8-sig"), "از پروندهٔ محلی خوانده شد"
        except OSError as e:
            return None, f"خواندن پرونده ممکن نشد: {e}"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / (cache_name or "last.json")
    if use_cache and cache_file.exists() and cache_seconds > 0:
        age = time.time() - cache_file.stat().st_mtime
        if age < cache_seconds:
            return cache_file.read_text(encoding="utf-8"), f"از حافظهٔ نهان ({int(age)} ثانیه پیش)"
    headers = {"User-Agent": "IranDeskStation/0.1 (+local)"}
    if key_header and key:
        headers[key_header] = key
    req = urllib.request.Request(url, headers=headers)
    last_err = ""
    for attempt in range(1, retries + 2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            cache_file.write_text(body, encoding="utf-8")
            return body, f"دریافت تازه در تلاش {attempt}"
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last_err = f"{type(e).__name__}: {e}"
            # خطای گذرا: مکث و تلاش دوباره. خطای قطعی (سرویس خاموش، نام دامنهٔ نادرست،
            # ۴۰۴/۴۰۱) را نباید مکث کرد؛ وگرنه هر نماد ۱٫۵ ثانیه بی‌دلیل منتظر می‌ماند.
            if attempt > retries or not transient_error(e):
                break
            time.sleep(min(1.0 * attempt, 3.0))
    if stale_ok and cache_file.exists():
        age = int(time.time() - cache_file.stat().st_mtime)
        return (cache_file.read_text(encoding="utf-8"),
                f"از حافظهٔ نهان {age} ثانیه‌ای استفاده شد، نه از شبکه ({last_err})")
    return None, f"دریافت ناموفق: {last_err}"


def dig(data, path: str):
    """مسیر نقطه‌ای مثل data.0.pl را در ساختار JSON دنبال می‌کند."""
    cur = data
    for part in [p for p in path.split(".") if p != ""]:
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            if part not in cur:
                return None
            cur = cur[part]
        else:
            return None
    return cur


# ---------------------------------------------------------------- نتیجهٔ اسنپ‌شات
@dataclass
class Snapshot:
    rows: list[dict] = field(default_factory=list)
    mode: str = "sim"
    source_label: str = ""
    as_of: str = ""
    fetched_at: str = ""
    freshness_seconds: float | None = None
    status: str = "ok"          # ok | partial | failed
    messages: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    live_prices: dict[str, float] = field(default_factory=dict)

    @property
    def freshness_label(self) -> str:
        if self.freshness_seconds is None:
            return "نامعلوم"
        s = int(self.freshness_seconds)
        if s < 90:
            return f"زنده ({s} ثانیه پیش)"
        if s < 3600:
            return f"نسبتاً تازه ({s // 60} دقیقه پیش)"
        if s < 86400:
            return f"کهنه ({s // 3600} ساعت پیش)"
        return f"تاریخی ({s // 86400} روز پیش)"

    def to_dict(self) -> dict:
        return {"as_of": self.as_of, "hurdle": self.rows[0].get("_hurdle", 0.39),
                "capital": self.rows[0].get("_capital", 0), "rows": self.rows}


# ---------------------------------------------------------------- بارگذاری‌ها
def load_snapshot_file(path: str | Path) -> Snapshot:
    p = Path(path)
    if not p.exists():
        return Snapshot(status="failed", mode="file", source_label="پروندهٔ دستی",
                        messages=[f"پروندهٔ اسنپ‌شات پیدا نشد: {p}"])
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        return Snapshot(status="failed", mode="file", source_label="پروندهٔ دستی",
                        messages=[f"پروندهٔ JSON خوانده نشد: {e}"])
    rows = [coerce_row_numbers(r) for r in (data.get("rows") or []) if isinstance(r, dict)]
    missing: list[str] = []
    for i, r in enumerate(rows):
        for k in ("symbol", "kind"):
            if not r.get(k):
                missing.append(f"ردیف {i + 1}: «{k}» خالی است")
    hurdle = float(data.get("hurdle", 0.39))
    capital = float(data.get("capital", 0))
    for r in rows:
        r["_hurdle"] = hurdle
        r["_capital"] = capital
    return Snapshot(rows=rows, mode="file", source_label=f"پروندهٔ دستی: {p.name}",
                    as_of=str(data.get("as_of", "")), fetched_at=now_iso(),
                    freshness_seconds=time.time() - p.stat().st_mtime,
                    status="ok" if rows and not missing else ("partial" if rows else "failed"),
                    messages=[f"{len(rows)} ردیف خوانده شد"] + missing,
                    missing_fields=missing)


def demo_snapshot() -> Snapshot:
    snap = load_snapshot_file(DESK_DIR / "market-demo.json")
    snap.mode = "sim"
    snap.source_label = "دادهٔ نمونه (ساختگی)"
    snap.messages.append("هشدار: اعداد این اسنپ‌شات ساختگی‌اند و قیمت واقعی بازار نیستند.")
    snap.freshness_seconds = None
    return snap


def numeric_paths(payload, *, max_items: int = 40, max_depth: int = 6) -> list[tuple[str, float]]:
    """مسیرهای عددی داخل یک پاسخ JSON را پیدا می‌کند تا «مسیر JSON» را حدس نزنیم.

    خروجی: فهرست (مسیر، مقدار) مثل ("data.0.pl", 20150.0)
    """
    out: list[tuple[str, float]] = []

    def walk(node, prefix: str, depth: int) -> None:
        if len(out) >= max_items or depth > max_depth:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{prefix}.{k}" if prefix else str(k), depth + 1)
        elif isinstance(node, list):
            for i, v in enumerate(node[:8]):
                walk(v, f"{prefix}.{i}" if prefix else str(i), depth + 1)
        else:
            if isinstance(node, bool) or node is None:
                return
            if isinstance(node, (int, float)):
                out.append((prefix, float(node)))
            elif isinstance(node, str):
                txt = node.strip().replace(",", "")
                try:
                    out.append((prefix, float(txt)))
                except ValueError:
                    return

    walk(payload, "", 0)
    return out


def parse_quote_payload(text: str, json_path: str, symbol: str) -> tuple[float | None, str]:
    """قیمت را از پاسخ سرویس بیرون می‌کشد. برای هر سرویس، فقط مسیر JSON عوض می‌شود."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # بعضی سرویس‌ها متن ساده یا CSV برمی‌گردانند
        for token in reversed(text.replace(";", ",").replace("|", ",").split(",")):
            token = token.strip()
            if token and all(c.isdigit() or c in ".-" for c in token):
                try:
                    return float(token), "مقدار از متن ساده استخراج شد (مسیر JSON نادیده گرفته شد)"
                except ValueError:
                    continue
        return None, "پاسخ JSON نبود و عددی هم پیدا نشد"
    value = dig(data, json_path) if json_path else None
    if value is None and isinstance(data, dict):
        for k in ("pl", "plc", "price", "last", "close", "pDrCotVal", "lastPrice"):
            if k in data:
                value = data[k]
                break
    if value is None:
        return None, f"مسیر «{json_path}» در پاسخ پیدا نشد"
    try:
        return float(str(value).replace(",", "").strip()), "قیمت خوانده شد"
    except ValueError:
        return None, f"مقدار «{value}» عدد نبود"


def finish_live(snap: Snapshot, prices: dict, *, stale_count: int = 0, fail_count: int = 0) -> Snapshot:
    """قیمت‌های خوانده‌شده را روی اسنپ‌شات می‌نشاند، سنجهٔ صداقت را می‌گذارد و برچسب می‌زند.

    این تابع از مسیر زندهٔ خودِ برنامه و از «برگهٔ شاهد زنده» (demo_day) یکسان صدا زده می‌شود تا
    عددی که در برگهٔ شاهد چاپ می‌شود، دقیقاً همان عددی باشد که برنامه رویش تصمیم می‌گیرد.
    """
    ok_count = len(prices)
    for row in snap.rows:
        symbol = str(row.get("symbol", "")).strip()
        if symbol not in prices:
            continue
        for target in ("spot", "stock_price"):
            if isinstance(row.get(target), (int, float)):
                # قیمت پایه/سهم با قیمت زنده جابه‌جا می‌شود؛ آتی و مشخصات قرارداد دست‌نخورده می‌ماند.
                row[f"{target}_manual"] = row[target]
                row[target] = prices[symbol]
    snap.live_prices = prices
    snap.fetched_at = now_iso()
    # تازگی فقط وقتی معنا دارد که قیمت از «شبکه» آمده باشد؛ خواندن از حافظهٔ نهان
    # نباید «زندهٔ ۰ ثانیه پیش» جا بزند.
    snap.freshness_seconds = 0.0 if (prices and not stale_count) else None
    if stale_count:
        snap.messages.append(f"{stale_count} نماد از حافظهٔ نهان خوانده شد، نه از شبکه؛ "
                             f"این عددها قیمت زنده نیستند و برچسب «از حافظهٔ نهان» می‌گیرند.")
        snap.source_label = f"{snap.source_label} (از حافظهٔ نهان)"
        if snap.status == "ok":
            snap.status = "partial"
    # سنجهٔ صداقت: اگر قیمت چند نماد عیناً یکی باشد، یعنی این منبع «نرخ واحد» می‌دهد،
    # نه قیمت هر نماد. آن‌وقت محاسبهٔ سهام بی‌معنی است و باید بگوییم.
    if len(prices) >= 2 and len(set(prices.values())) == 1:
        snap.status = "partial"
        snap.messages.append("قیمت چند نماد عیناً یکسان آمد؛ یعنی این منبع یک «نرخ واحد» می‌دهد "
                             "(مثل نرخ ارز)، نه قیمت هر نماد. برای محاسبهٔ سهام، منبع نمادی "
                             "یا پروندهٔ دستی کارگزاری لازم است — به عددهای زیر استناد نکنید.")
        snap.source_label = f"{snap.source_label} (نرخ واحد، نه نماد)"
        return snap
    if ok_count and not fail_count:
        snap.status = "ok"
        snap.messages.append(f"قیمت زندهٔ {ok_count} نماد به‌روز شد.")
    elif ok_count:
        snap.status = "partial"
        snap.messages.append(f"قیمت {ok_count} نماد به‌روز شد و {fail_count} نماد نیامد.")
    else:
        snap.status = "failed"
        snap.messages.append("هیچ قیمتی از سرویس نیامد؛ قالب نشانی و مسیر JSON را بررسی کنید.")
    return snap


def live_snapshot(base: Snapshot | dict, live_cfg: dict, *, key: str = "",
                  allow_network: bool = True, progress=None) -> Snapshot:
    """قیمت‌های زنده را روی یک اسنپ‌شات پایه می‌نشاند.

    دادهٔ پایه (مشخصات قرارداد، وجه تضمین، تعداد روز) از پرونده می‌آید؛
    قیمت‌ها از سرویس. این تفکیک عمدی است: وجه تضمین فقط از کارگزاری می‌آید.
    """
    def say(m: str) -> None:
        if progress:
            progress(m)
        log(m)

    if isinstance(base, Snapshot):
        snap = base
    else:
        snap = load_snapshot_file(base)
    snap.mode = "live"
    url_tpl = (live_cfg.get("url_template") or "").strip()
    # صداقت برچسب: اگر نشانی روی همین رایانه باشد، داده ساختگی است، نه بازار واقعی.
    local_feed = any(h in url_tpl for h in ("127.0.0.1", "localhost", "0.0.0.0", "::1"))
    snap.source_label = "خوراک آزمایشی محلی (ساختگی)" if local_feed else "دادهٔ زندهٔ وب‌سرویس"
    if not url_tpl:
        snap.status = "failed"
        snap.messages.append("قالب نشانی خالی است؛ در همین صفحه نشانی سرویس را وارد کنید.")
        return snap
    if not allow_network:
        snap.status = "failed"
        snap.messages.append("دسترسی شبکه در این اجرا بسته است.")
        return snap

    prices: dict[str, float] = {}
    ok_count, fail_count, stale_count = 0, 0, 0
    for row in snap.rows:
        symbol = str(row.get("symbol", "")).strip()
        if not symbol:
            continue
        # feed_symbol اجازه می‌دهد در نشانی به‌جای نام نماد، «کد نماد» (insCode) برود
        url_symbol = str(row.get("feed_symbol") or symbol).strip()
        url = url_tpl.replace("{symbol}", urllib.parse.quote(url_symbol))
        if live_cfg.get("key_query_name"):
            url = url.replace("{key}", urllib.parse.quote(key)) if "{key}" in url_tpl else url
        if "{key}" in url:
            url = url.replace("{key}", urllib.parse.quote(key))
        text, status = fetch(url, timeout=float(live_cfg.get("timeout_seconds", 12)),
                             retries=int(live_cfg.get("retries", 1)),
                             key_header=live_cfg.get("key_header", ""), key=key,
                             cache_name=f"quote-{symbol}.json",
                             cache_seconds=int(live_cfg.get("cache_seconds", 30)))
        if not text:
            fail_count += 1
            say(f"قیمت {symbol} نیامد: {status}")
            continue
        if "حافظهٔ نهان" in status:
            stale_count += 1
            say(f"قیمت {symbol} از حافظهٔ نهان آمد، نه از شبکه")
        value, why = parse_quote_payload(text, live_cfg.get("json_path", ""), symbol)
        if value is None:
            fail_count += 1
            say(f"قیمت {symbol} خوانده نشد: {why}")
            continue
        prices[symbol] = value
        ok_count += 1
        say(f"قیمت زندهٔ {symbol}: {value:,.0f}")

    return finish_live(snap, prices, stale_count=stale_count, fail_count=fail_count)
    if ok_count and not fail_count:
        snap.status = "ok"
        snap.messages.append(f"قیمت زندهٔ {ok_count} نماد به‌روز شد.")
    elif ok_count:
        snap.status = "partial"
        snap.messages.append(f"قیمت {ok_count} نماد به‌روز شد و {fail_count} نماد نیامد.")
    else:
        snap.status = "failed"
        snap.messages.append("هیچ قیمتی از سرویس نیامد؛ قالب نشانی و مسیر JSON را بررسی کنید.")
    return snap


def build_snapshot(mode: str, *, file_path: str | Path | None = None, live_cfg: dict | None = None,
                   key: str = "", allow_network: bool = True, progress=None) -> Snapshot:
    """دروازهٔ یکسان برای همهٔ حالت‌ها (همان چیزی که رابط گرافیکی صدا می‌زند)."""
    if mode == "sim":
        return demo_snapshot()
    if mode == "file":
        if not file_path:
            return Snapshot(status="failed", mode="file", messages=["مسیر پرونده داده نشده است."])
        return load_snapshot_file(file_path)
    if mode == "live":
        base = load_snapshot_file(file_path) if file_path else demo_snapshot()
        return live_snapshot(base, live_cfg or DEFAULT_LIVE_CONFIG, key=key,
                             allow_network=allow_network, progress=progress)
    return Snapshot(status="failed", mode=mode, messages=[f"حالت دادهٔ ناشناخته: {mode}"])


# ---------------------------------------------------------------- خواندن هشدارهای کدال
def read_alerts(kodal_db: str | Path, min_score: int = 60, limit: int = 50) -> list[dict]:
    p = Path(kodal_db)
    if not p.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        rows = conn.execute(
            "SELECT title, symbol, category, direction, score, url FROM items "
            "WHERE score >= ? ORDER BY score DESC LIMIT ?", (min_score, limit)).fetchall()
        conn.close()
    except sqlite3.Error:
        return []
    return [{"title": t, "symbol": s, "category": c, "direction": d, "score": sc, "url": u}
            for t, s, c, d, sc, u in rows]


def write_snapshot_template(path: str | Path) -> Path:
    """قالب اسنپ‌شات برای کاربر تازه‌کار می‌سازد."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(SNAPSHOT_TEMPLATE, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


# ---------------------------------------------------------------- اسنپ‌شات دستی تاریخ‌دار
def ascii_safe_url(url: str) -> str:
    """نشانی‌هایی که حرف فارسی دارند (مثل نام نماد) را درصد‌کد می‌کند.

    بدون این کار، کتابخانهٔ شبکه با خطای UnicodeEncodeError می‌خوابد؛ این ایراد در آزمون
    «اتصال خودکار» با نام نماد فارسی پیدا شد.
    """
    try:
        str(url).encode("ascii")
        return str(url)
    except UnicodeEncodeError:
        import urllib.parse as _up
        return _up.quote(str(url), safe=":/?#[]@!$&'()*+,;=%")


SNAPSHOT_NUM_FIELDS = ("spot", "future", "strike", "premium", "stock_price", "put_price",
                       "days", "margin_per_contract", "liquidity_contracts_per_day", "spread_pct")
SNAPSHOT_KINDS = ("basis", "box", "tabei", "covered_call", "parity")


def load_snapshot_rows(path: str | Path) -> dict:
    """ردیف‌های یک اسنپ‌شات را برای ویرایش در رابط گرافیکی برمی‌گرداند."""
    p = Path(path)
    if not p.exists():
        return {"rows": [], "as_of": "", "hurdle": 0.39, "capital": 20_000_000_000,
                "note": "پرونده‌ای نیست", "path": str(p), "exists": False}
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        return {"rows": [], "as_of": "", "hurdle": 0.39, "capital": 20_000_000_000,
                "note": f"پرونده خوانده نشد: {e}", "path": str(p), "exists": True}
    rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in (data.get("rows") or [])]
    return {"rows": rows, "as_of": str(data.get("as_of", "")),
            "hurdle": float(data.get("hurdle", 0.39)),
            "capital": float(data.get("capital", 20_000_000_000)),
            "note": str(data.get("note", "")), "source": str(data.get("source", "")),
            "confirmed": snapshot_confirmed(p), "path": str(p), "exists": True}


def clean_rows(raw_rows: list[dict]) -> tuple[list[dict], list[str]]:
    """ردیف‌های فرم را پاکیزه می‌کند: فیلدهای خالی حذف، عددها عدد، ردیف بی‌نماد کنار گذاشته.

    خروجی: (ردیف‌های آماده، هشدارها)
    """
    out: list[dict] = []
    problems: list[str] = []
    for i, r in enumerate(raw_rows or []):
        if not isinstance(r, dict):
            problems.append(f"ردیف {i + 1}: ساختار نامعتبر")
            continue
        symbol = str(r.get("symbol", "") or "").strip()
        if not symbol:
            continue                              # ردیف خالی را بی‌صدا رد می‌کنیم
        kind = str(r.get("kind", "") or "basis").strip() or "basis"
        if kind not in SNAPSHOT_KINDS:
            problems.append(f"ردیف {i + 1} ({symbol}): نوع «{kind}» شناخته نشد؛ «basis» گذاشته شد.")
            kind = "basis"
        row: dict = {"symbol": symbol, "kind": kind}
        for k, v in r.items():
            if k in ("symbol", "kind"):
                continue
            if isinstance(v, str):
                v = v.strip().replace(",", "")
            if v in ("", None):
                continue
            if k in SNAPSHOT_NUM_FIELDS:
                try:
                    row[k] = float(v)
                except (TypeError, ValueError):
                    problems.append(f"ردیف {i + 1} ({symbol}): «{k}» عدد نبود و کنار گذاشته شد.")
                continue
            row[k] = v
        price_fields = ("spot", "stock_price", "future", "strike", "premium", "put_price",
                        "call", "put", "call_low", "call_high", "put_low", "put_high",
                        "strike_low", "strike_high")
        if not any(isinstance(row.get(k), (int, float)) and row[k] > 0 for k in price_fields):
            problems.append(f"ردیف {i + 1} ({symbol}): هیچ قیمتی وارد نشده؛ ردیف می‌ماند ولی سیگنالی نمی‌دهد.")
        unit = str(r.get("feed_symbol", "") or "").strip()
        if unit:
            row["feed_symbol"] = unit
        out.append(row)
    if not out:
        problems.append("هیچ ردیف درستی وارد نشد؛ حداقل یک نماد با قیمت لازم است.")
    return out, problems


MANUAL_SOURCE = "manual-broker"


def snapshot_confirmed(path: str | Path | None) -> bool:
    """آیا این پرونده را کاربر از سامانهٔ کارگزاری برداشته و تأیید کرده است؟

    بدون این تأیید، پرونده «واقعی» حساب نمی‌شود؛ وگرنه هر پرونده‌ای می‌توانست روز واقعی جعل کند.
    """
    if not path:
        return False
    p = Path(path)
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return False
    return str(data.get("source", "")) == MANUAL_SOURCE


def save_dated_snapshot(rows: list[dict], *, as_of: str | None = None, hurdle: float = 0.39,
                        capital: float = 20_000_000_000, note: str = "",
                        out_dir: str | Path | None = None, day: str | None = None,
                        source: str = MANUAL_SOURCE) -> Path:
    """اسنپ‌شات را با تاریخ می‌نویسد: `snapshots/snapshot-YYYY-MM-DD.json`.

    چرا تاریخ‌دار؟ چون هر روز پروندهٔ خودش را می‌خواهد: هم سابقهٔ قابل ممیزی می‌شود،
    هم اشتباه یک روز، روزهای دیگر را خراب نمی‌کند.
    """
    clean, _ = clean_rows(rows)
    if not clean:
        raise ValueError("هیچ ردیف درستی برای ذخیره نبود.")
    d = (Path(out_dir) if out_dir else (BASE / "data" / "snapshots"))
    d.mkdir(parents=True, exist_ok=True)
    stamp = day or datetime.now().strftime("%Y-%m-%d")
    path = d / f"snapshot-{stamp}.json"
    payload = {"as_of": as_of or datetime.now().strftime("%Y-%m-%d %H:%M"),
               "hurdle": float(hurdle), "capital": float(capital),
               "note": note, "source": source, "rows": clean}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def history_template_rows() -> list[dict]:
    """سطر نمونهٔ پروندهٔ پس‌آزمایی، برای اینکه کاربر بداند چه ستون‌هایی لازم است."""
    return [
        {"date": "1405-05-01", "symbol": "اهرم", "kind": "basis", "spot": 20000, "future": 22800,
         "days": 90, "margin_per_contract": 20000000, "liquidity_contracts_per_day": 900,
         "spread_pct": 0.005, "hurdle": 0.39, "realized_annualized_pct": 61.0},
    ]


def write_history_template(path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    cols = ["date", "symbol", "kind", "spot", "future", "strike", "premium", "put_price", "stock_price",
            "days", "margin_per_contract", "liquidity_contracts_per_day", "spread_pct", "hurdle",
            "realized_annualized_pct"]
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in history_template_rows():
            w.writerow({c: r.get(c, "") for c in cols})
    return p
