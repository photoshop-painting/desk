#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""دیده‌بان اطلاعیه‌های کدال و خبر بازار سرمایه — نسخهٔ ۰٫۱٫۰

بدون هیچ وابستگی بیرونی (فقط کتابخانهٔ استاندارد پایتون) تا روی هر ویندوز و
لینوکسی، بدون دسترسی به پی‌پی‌آی و بدون پرداخت ارزی، اجرا شود.

اصول طراحی (برای شرایط ایران):
  • آفلاین‌محور: اگر اینترنت یا سامانه در دسترس نبود، از دادهٔ نمونه یا دادهٔ ذخیره‌شده کار می‌کند.
  • بدون کلید و بدون هزینه: حالت پیش‌فرض «شاهد محلی» است؛ لایهٔ هوش مصنوعی اختیاری است.
  • قابل‌سرویس‌دهی از داخل ایران: همهٔ فراخوانی‌ها با timeout و retry، و پشتیبانی پروکسی.
  • هیچ توصیهٔ سوددهی تضمینی‌ای تولید نمی‌کند؛ خروجی «هشدار و زمینه» است، نه دستور معامله.

دستورها:
  python kodal_alert.py demo                 اجرای کامل روی دادهٔ نمونه (آفلاین)
  python kodal_alert.py import FILE          ورود اطلاعیه‌ها از فایل JSON/CSV
  python kodal_alert.py run --source rss:URL --source codal
  python kodal_alert.py watch --minutes 10   اجرای دوره‌ای
  python kodal_alert.py report               ساخت گزارش HTML از پایگاه‌داده
  python kodal_alert.py stats | version | selftest
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

VERSION = "0.1.0"
BASE = Path(__file__).resolve().parent
DEFAULT_DB = BASE / "data" / "kodal.sqlite3"
DEFAULT_REPORT = BASE / "data" / "report.html"
CACHE_DIR = BASE / "data" / "cache"
CREDIT = ("تهیه‌کننده: Masoud Mojarabian · "
          "https://www.instagram.com/Mojarabian.Art/ · "
          "tel:+989126630554 · https://t.me/Mojarabian")

# ---------------------------------------------------------------- تنظیمات پیش‌فرض
DEFAULT_CONFIG: dict = {
    "watchlist": ["خساپا", "شپنا", "فولاد", "وبملت", "شستا", "اهرم", "طلا", "زعفران"],
    "sources": [
        {"type": "rss", "name": "فارس", "url": "https://www.farsnews.ir/rss"},
        {"type": "rss", "name": "ایبنا", "url": "https://www.ibena.ir/rss"},
        {"type": "codal", "name": "کدال", "url": "https://search.codal.ir/api/search/v2/q"}
    ],
    "proxies": {"http": "", "https": ""},
    "timeout_seconds": 15,
    "retries": 2,
    "min_score_to_alert": 45,
    "llm": {"provider": "none", "model": "", "base_url": "", "api_key_env": "TYPESAFE_API_KEY"},
    "notifiers": {"console": True, "file": True,
                  "telegram": {"enabled": False, "token_env": "TELEGRAM_BOT_TOKEN", "chat_id": ""},
                  "bale": {"enabled": False, "token_env": "BALE_BOT_TOKEN", "chat_id": ""}},
    "credit": CREDIT,
    "report_title": "دیده‌بان کدال و خبر بازار",
}

# ---------------------------------------------------------------- دسته‌بندی رویدادها
# (دسته، کلیدواژه‌ها، امتیاز پایه، جهت، توضیح چرایی)
CATEGORY_RULES: list[tuple[str, list[str], int, str, str]] = [
    ("افزایش سرمایه", ["افزایش سرمایه", "تجدید ارزیابی", "آورده نقدی", "سهام جایزه"], 80, "مثبت",
     "افزایش سرمایه ساختار ترازنامه را عوض می‌کند و روی تعداد سهام، قیمت پایه و اندازهٔ قرارداد مشتقه اثر می‌گذارد."),
    ("تعدیل پیش‌بینی", ["تعدیل", "پیش‌بینی درآمد", "پیش‌بینی سود", "eps"], 78, "نامعلوم",
     "تعدیل پیش‌بینی، محرک اصلی انتظارات سود است؛ جهت تعدیل (مثبت یا منفی) را از متن بخوانید."),
    ("تقسیم سود", ["تقسیم سود", "مجمع عمومی", "سود نقدی", "dps"], 60, "نامعلوم",
     "مجمع و تقسیم سود، تاریخ توقف نماد و قیمت پایهٔ پس از مجمع را تغییر می‌دهد."),
    ("قرارداد و فروش", ["انعقاد قرارداد", "قرارداد جدید", "افزایش نرخ فروش", "صادرات", "سفارش خرید"], 62, "مثبت",
     "قرارداد یا افزایش نرخ فروش، جریان درآمد آینده را تغییر می‌دهد؛ به مبلغ و مدت قرارداد نگاه کنید."),
    ("تولید و فروش ماهانه", ["گزارش فعالیت ماهانه", "میزان تولید", "میزان فروش", "فروش ماهانه"], 48, "نامعلوم",
     "گزارش ماهانه بهترین نمای نزدیک از روند واقعی شرکت است؛ روند سه‌ماهه مهم‌تر از یک ماه است."),
    ("توقف و بازگشایی نماد", ["توقف نماد", "بازگشایی نماد", "شناور شدن"], 70, "منفی",
     "توقف و بازگشایی، نقدشوندگی را از بین می‌برد یا برمی‌گرداند؛ در زمان توقف، آپشن و آتی همان پایه پرریسک می‌شوند."),
    ("شفاف‌سازی", ["شفاف‌سازی", "توضیحات در خصوص", "پاسخ به استعلام"], 55, "نامعلوم",
     "شفاف‌سازی معمولاً واکنش به شایعه یا نوسان غیرعادی است؛ متن را کامل بخوانید."),
    ("دارایی و سرمایه‌گذاری", ["واگذاری دارایی", "خرید سهام", "سرمایه‌گذاری", "فروش زمین", "فروش ساختمان"], 58, "نامعلوم",
     "خرید یا فروش دارایی می‌تواند سود غیرعملیاتی بسازد؛ تکرارشدنی بودنش را بسنجید."),
    ("دعاوی و ریسک حقوقی", ["دعوی", "شکایت", "محکومیت", "جریمه", "مالیات معوق", "بدهی"], 66, "منفی",
     "ریسک حقوقی و بدهی، پیش‌بینی سود را بی‌اعتبار می‌کند؛ مبلغ ادعا را با سرمایهٔ شرکت مقایسه کنید."),
    ("مدیریت و مالکیت", ["تغییر مدیرعامل", "استعفا", "انتخاب اعضای هیئت مدیره", "سهامدار عمده"], 52, "نامعلوم",
     "تغییر مدیریت یا مالکیت، جهت راهبرد شرکت را عوض می‌کند؛ پیامدش دیرهنگام ظاهر می‌شود."),
    ("ابزار مشتقه و تبعی", ["اختیار فروش تبعی", "اوراق تبعی", "قرارداد آتی", "اختیار معامله", "صندوق طلا"], 75, "مثبت",
     "عرضهٔ تبعی، کفِ بازده را تضمین می‌کند؛ بازده تضمینی و شرط نگه‌داشتن سبد را دقیق حساب کنید."),
    ("پذیرش و عرضه", ["پذیرش در فرابورس", "عرضه اولیه", "پذیره‌نویسی"], 63, "نامعلوم",
     "پذیرش و عرضهٔ اولیه، عرضه و تقاضای سهم را جابه‌جا می‌کند."),
]

POSITIVE_WORDS = ["افزایش", "رشد", "سود", "مثبت", "توسعه", "بهبود", "رکورد", "قرارداد", "صادرات", "تعدیل مثبت"]
NEGATIVE_WORDS = ["کاهش", "زیان", "منفی", "توقف", "لغو", "شکایت", "دعوی", "محکومیت", "جریمه", "افت", "تعدیل منفی", "بدهی"]
NUMERIC_BONUS_PATTERNS = [r"\d[\d,\.]*\s*میلیارد", r"\d[\d,\.]*\s*میلیون", r"\d+\s*درصد", r"\d[\d,\.]*\s*ریال"]

# ---------------------------------------------------------------- ابزار پایه
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def g2j(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """تبدیل تاریخ میلادی به شمسی (الگوریتم استاندارد)."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def jalali_str(dt: datetime | None = None) -> str:
    dt = dt or now_utc()
    jy, jm, jd = g2j(dt.year, dt.month, dt.day)
    return f"{jy:04d}/{jm:02d}/{jd:02d} {dt.hour:02d}:{dt.minute:02d}"


def log(msg: str) -> None:
    print(f"[{jalali_str()}] {msg}")


def load_config(path: str | None) -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG, ensure_ascii=False))  # کپی عمیق
    p = Path(path) if path else BASE / "config.json"
    if p.exists():
        try:
            user = json.loads(p.read_text(encoding="utf-8"))
            for k, v in user.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
        except json.JSONDecodeError as e:
            log(f"پروندهٔ تنظیمات خوانده نشد ({e})؛ تنظیمات پیش‌فرض استفاده می‌شود.")
    return cfg


# ---------------------------------------------------------------- لایهٔ شبکه
def http_get(url: str, cfg: dict, cache_name: str | None = None) -> str | None:
    """دریافت متن با retry، timeout، پروکسی و حافظهٔ نهان روی دیسک."""
    if url.startswith("file:"):
        try:
            return Path(url[5:]).read_text(encoding="utf-8")
        except OSError as e:
            log(f"خواندن فایل ممکن نشد: {e}")
            return None
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / (cache_name or hashlib.sha1(url.encode()).hexdigest())
    handlers = []
    proxies = {k: v for k, v in (cfg.get("proxies") or {}).items() if v}
    if proxies:
        handlers.append(urllib.request.ProxyHandler(proxies))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (KodalAlert/0.1; +local)",
        "Accept": "application/json, text/xml, application/xml, text/html;q=0.9, */*;q=0.5",
    })
    for attempt in range(1, int(cfg.get("retries", 2)) + 2):
        try:
            with opener.open(req, timeout=float(cfg.get("timeout_seconds", 15))) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            cache_file.write_text(body, encoding="utf-8")
            return body
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            log(f"تلاش {attempt} برای {url} ناموفق: {e}")
            time.sleep(min(2.0 * attempt, 6.0))
    if cache_file.exists():
        log(f"از حافظهٔ نهان استفاده شد: {cache_file.name}")
        return cache_file.read_text(encoding="utf-8")
    return None


# ---------------------------------------------------------------- مدل داده
@dataclass
class Item:
    title: str
    source: str = "نامشخص"
    symbol: str = ""
    company: str = ""
    body: str = ""
    url: str = ""
    published_at: str = ""
    category: str = ""
    direction: str = "نامعلوم"
    score: int = 0
    reason: str = ""
    ai_note: str = ""
    provider: str = "شاهد محلی (قاعده‌محور)"

    def key(self) -> str:
        raw = f"{self.source}|{self.title}|{self.symbol}|{self.published_at}".encode("utf-8")
        return hashlib.sha1(raw).hexdigest()[:16]

    def to_row(self) -> tuple:
        d = asdict(self)
        return (self.key(), d["title"], d["source"], d["symbol"], d["company"], d["body"], d["url"],
                d["published_at"], d["category"], d["direction"], d["score"], d["reason"], d["ai_note"], d["provider"])


# ---------------------------------------------------------------- دسته‌بندی و امتیازدهی
def classify(title: str, body: str, source_weight: float = 1.0,
             published_at: datetime | None = None) -> tuple[str, str, int, str]:
    """عنوان بر متن مقدم است تا متن‌های حاشیه‌ای، دسته را از مسیر خارج نکنند."""
    title_l, body_l = title.lower(), body.lower()
    best: tuple[str, int, str, str] | None = None
    for cat, kws, base, direction, why in CATEGORY_RULES:
        t_hits = sum(1 for kw in kws if kw.lower() in title_l)
        b_hits = sum(1 for kw in kws if kw.lower() in body_l)
        if t_hits == 0 and b_hits < 2:
            continue
        effective = t_hits * 3 + b_hits
        score = base + min(max(effective - 1, 0), 3) * 4
        if t_hits == 0:
            score -= 12  # فقط از متن آمده: کمی محافظه‌کارتر
        if best is None or score > best[1]:
            best = (cat, score, direction, why)
    if best is None:
        best = ("سایر", 30, "نامعلوم", "دستهٔ مشخصی تشخیص داده نشد؛ عنوان را خودتان بخوانید.")

    cat, score, direction, why = best
    if cat == "توقف و بازگشایی نماد":
        direction = "مثبت" if ("بازگشایی" in title_l and "توقف نماد" not in title_l) else "منفی"
    text = f"{title_l} {body_l}"
    pos = sum(1 for w in POSITIVE_WORDS if w in text)
    neg = sum(1 for w in NEGATIVE_WORDS if w in text)
    if direction == "نامعلوم":
        direction = "مثبت" if pos > neg else ("منفی" if neg > pos else "خنثی")
    if any(re.search(p, text) for p in NUMERIC_BONUS_PATTERNS):
        score += 6
        why += " متن عدد کمّی دارد؛ نسبت آن عدد به اندازهٔ شرکت را حساب کنید."
    if published_at is not None:
        pa = published_at if published_at.tzinfo else published_at.replace(tzinfo=timezone.utc)
        age_h = (now_utc() - pa).total_seconds() / 3600.0
        if age_h <= 6:
            score += 8
        elif age_h > 72:
            score -= 10
    score = int(max(0, min(100, round(score * source_weight))))
    return cat, direction, score, why


def symbol_in_watchlist(item: Item, watchlist: list[str]) -> bool:
    blob = f"{item.symbol} {item.title} {item.company}"
    return any(w and w in blob for w in watchlist)


# ---------------------------------------------------------------- انبار داده
SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY, title TEXT, source TEXT, symbol TEXT, company TEXT,
    body TEXT, url TEXT, published_at TEXT, category TEXT, direction TEXT,
    score INTEGER, reason TEXT, ai_note TEXT, provider TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT, items INTEGER, source TEXT);
"""


class Store:
    def __init__(self, path: Path | str = DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ── بستن تمیز (پایان کار / پرونده‌های موقت)
    def close(self) -> None:
        """پیوند پایگاه‌داده را می‌بندد. چند بار صدا زدنش بی‌خطر است."""
        try:
            self.conn.close()
        except Exception:      # noqa: BLE001 — بستن نباید برنامه را بیندازد
            pass

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()


    def add(self, item: Item) -> bool:
        try:
            self.conn.execute(
                "INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                item.to_row() + (now_utc().isoformat(timespec="seconds"),))
            return True
        except sqlite3.IntegrityError:
            return False

    def commit(self) -> None:
        self.conn.commit()

    def recent(self, limit: int = 100, min_score: int = 0) -> list[Item]:
        cur = self.conn.execute(
            "SELECT title,source,symbol,company,body,url,published_at,category,direction,score,reason,ai_note,provider "
            "FROM items WHERE score >= ? ORDER BY score DESC, published_at DESC LIMIT ?", (min_score, limit))
        return [Item(*row) for row in cur.fetchall()]

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0])

    def log_run(self, source: str, n: int) -> None:
        self.conn.execute("INSERT INTO runs (started_at, items, source) VALUES (?,?,?)",
                          (now_utc().isoformat(timespec="seconds"), n, source))
        self.conn.commit()


# ---------------------------------------------------------------- منابع داده
def item_from_dict(d: dict, source_name: str = "", cfg: dict | None = None) -> Item:
    cfg = cfg or {}
    published = None
    raw_date = str(d.get("published_at") or d.get("date") or "").strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            published = datetime.strptime(raw_date[:19], fmt).replace(tzinfo=timezone.utc)
            break
        except ValueError:
            continue
    sw = 1.15 if source_name in ("کدال", "codal") else 1.0
    cat, direction, score, why = classify(str(d.get("title", "")), str(d.get("body", "")), sw, published)
    return Item(title=str(d.get("title", "")).strip(), source=source_name or str(d.get("source", "نامشخص")),
                symbol=str(d.get("symbol", "")).strip(), company=str(d.get("company", "")).strip(),
                body=str(d.get("body", ""))[:2000], url=str(d.get("url", "")), published_at=raw_date,
                category=cat, direction=direction, score=score, reason=why)


def load_file_source(path: str, cfg: dict) -> list[Item]:
    p = Path(path)
    if not p.exists():
        log(f"پروندهٔ منبع پیدا نشد: {path}")
        return []
    text = p.read_text(encoding="utf-8")
    items: list[Item] = []
    if p.suffix.lower() == ".csv":
        for row in csv.DictReader(text.splitlines()):
            items.append(item_from_dict(row, cfg=cfg))
    else:
        data = json.loads(text)
        rows = data if isinstance(data, list) else data.get("items", [])
        for row in rows:
            items.append(item_from_dict(row, cfg=cfg))
    return items


def parse_feed(xml_text: str, source_name: str, cfg: dict) -> list[Item]:
    items: list[Item] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        log(f"فید خوانده نشد: {e}")
        return items
    nodes = root.iter("item") if root.findall(".//item") else root.iter("{http://www.w3.org/2005/Atom}entry")
    for node in nodes:
        def txt(tag: str) -> str:
            el = node.find(tag) if node.find(tag) is not None else node.find("{http://www.w3.org/2005/Atom}" + tag)
            return (el.text or "").strip() if el is not None and el.text else ""
        link = txt("link") or ""
        if not link:
            el = node.find("{http://www.w3.org/2005/Atom}link")
            link = el.get("href", "") if el is not None else ""
        title, desc = txt("title"), (txt("description") or txt("summary"))
        desc = re.sub(r"<[^>]+>", " ", desc)[:1500]
        if title:
            items.append(item_from_dict({"title": title, "body": desc, "url": link,
                                         "published_at": txt("pubDate") or txt("updated")},
                                        source_name=source_name, cfg=cfg))
    return items


def fetch_codal(cfg: dict) -> list[Item]:
    """تلاش برای خواندن اطلاعیه‌های کدال. اگر سامانه پاسخ ندهد، رشتهٔ خالی برمی‌گردد."""
    src = next((s for s in cfg.get("sources", []) if s.get("type") == "codal"), None)
    if not src:
        return []
    params = {"PageNumber": "1", "Length": "-1", "Audited": "true", "NotAudited": "true",
              "Mains": "true", "Childs": "true", "Publisher": "false", "search": "true", "LetterType": "-1", "Category": "-1"}
    url = f"{src.get('url')}?{urllib.parse.urlencode(params)}"
    body = http_get(url, cfg, cache_name="codal.json")
    if not body:
        log("کدال پاسخ نداد؛ از منبع فایلی یا خبری استفاده کنید.")
        return []
    out: list[Item] = []
    try:
        data = json.loads(body)
        for row in data.get("Letters", []) or data.get("letters", []) or []:
            title = str(row.get("Title") or row.get("title") or "").strip()
            if not title:
                continue
            out.append(item_from_dict({
                "title": title,
                "symbol": str(row.get("Symbol") or row.get("symbol") or ""),
                "company": str(row.get("CompanyName") or row.get("companyName") or ""),
                "url": "https://codal.ir" + str(row.get("Url") or row.get("url") or ""),
                "published_at": str(row.get("PublishDateTime") or row.get("publishDateTime") or ""),
            }, source_name="کدال", cfg=cfg))
    except (json.JSONDecodeError, AttributeError, TypeError) as e:
        log(f"ساختار پاسخ کدال ناشناخته بود: {e}")
    return out


def fetch_rss(cfg: dict) -> list[Item]:
    out: list[Item] = []
    for src in cfg.get("sources", []):
        if src.get("type") != "rss":
            continue
        xml_text = http_get(src.get("url", ""), cfg, cache_name=f"rss-{src.get('name','feed')}.xml")
        if not xml_text:
            continue
        out.extend(parse_feed(xml_text, src.get("name", "خبر"), cfg))
    return out


# ---------------------------------------------------------------- لایهٔ هوش مصنوعی (اختیاری)
LLM_PROMPT = """تو دستیار تحلیل اطلاعیه‌های کدال و خبر بازار سرمایه ایران هستی.
فقط از متن زیر استفاده کن و چیزی از خودت اضافه نکن. خروجی را فقط JSON بده با این کلیدها:
{"رویداد": "...", "جهت": "مثبت|منفی|خنثی", "بزرگی": "کم|متوسط|زیاد", "افق": "کوتاه|میان|بلند",
 "اقدام": "یک اقدام بررسی‌محور و نه توصیهٔ خرید و فروش", "اطمینان": 0 تا 100}
هیچ وعدهٔ سود و هیچ دستور معامله‌ای نده.
عنوان: {title}
متن: {body}
"""


def llm_enrich(item: Item, cfg: dict) -> None:
    """غنی‌سازی با مدل زبانی. اگر کلید یا سرویس نبود، برچسب «شاهد محلی» باقی می‌ماند."""
    conf = cfg.get("llm", {})
    provider = conf.get("provider", "none")
    if provider in ("", "none", None):
        return
    prompt = LLM_PROMPT.replace("{title}", item.title).replace("{body}", item.body or item.title)
    text = None
    try:
        if provider == "ollama":
            payload = {"model": conf.get("model") or "qwen2.5:7b", "prompt": prompt, "stream": False, "format": "json"}
            req = urllib.request.Request(conf.get("base_url") or "http://127.0.0.1:11434/api/generate",
                                         data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                text = json.loads(r.read().decode()).get("response", "")
            item.provider = "Ollama محلی"
        elif provider in ("typesafe", "jev"):
            key = os.environ.get(conf.get("api_key_env", "TYPESAFE_API_KEY"), "")
            if not key:
                item.provider = "شاهد محلی (کلید هوش مصنوعی تنظیم نشده)"
                return
            url = conf.get("base_url") or "https://api.typesafe.ai/v1/chat/completions"
            payload = {"model": conf.get("model") or "jev-latest",
                       "messages": [{"role": "user", "content": prompt}]}
            req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={
                "Content-Type": "application/json", "Authorization": f"Bearer {key}"})
            with urllib.request.urlopen(req, timeout=60) as r:
                text = json.loads(r.read().decode())["choices"][0]["message"]["content"]
            item.provider = "Jev/TypeSafe"
        elif provider == "openrouter":
            key = os.environ.get(conf.get("api_key_env", "OPENROUTER_API_KEY"), "")
            if not key:
                item.provider = "شاهد محلی (کلید هوش مصنوعی تنظیم نشده)"
                return
            url = conf.get("base_url") or "https://openrouter.ai/api/v1/chat/completions"
            payload = {"model": conf.get("model") or "meta-llama/llama-3.1-8b-instruct",
                       "messages": [{"role": "user", "content": prompt}]}
            req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={
                "Content-Type": "application/json", "Authorization": f"Bearer {key}"})
            with urllib.request.urlopen(req, timeout=60) as r:
                text = json.loads(r.read().decode())["choices"][0]["message"]["content"]
            item.provider = "OpenRouter"
    except Exception as e:  # شبکه، کلید، ساختار پاسخ
        item.provider = f"شاهد محلی (خطای سرویس: {type(e).__name__})"
        return
    if not text:
        return
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return
    try:
        data = json.loads(m.group(0))
        item.ai_note = (f"رویداد: {data.get('رویداد','')} | جهت: {data.get('جهت','')} | "
                        f"بزرگی: {data.get('بزرگی','')} | افق: {data.get('افق','')} | "
                        f"اقدام: {data.get('اقدام','')} | اطمینان: {data.get('اطمینان','')}")
    except json.JSONDecodeError:
        item.ai_note = text[:300]


# ---------------------------------------------------------------- اعلان‌ها
def notify(items: list[Item], cfg: dict) -> None:
    hot = [i for i in items if i.score >= int(cfg.get("min_score_to_alert", 45))]
    if cfg.get("notifiers", {}).get("console", True):
        print("\n" + "=" * 78)
        print(f"هشدارهای مهم امروز: {len(hot)} مورد از {len(items)} مورد پردازش‌شده")
        print("=" * 78)
        for it in hot[:25]:
            print(f"[{it.score:>3}] {it.direction:<6} {it.category:<22} {it.symbol or '-':<10} {it.title[:70]}")
            print(f"      چرا مهم است: {it.reason}")
            if it.ai_note:
                print(f"      {it.provider}: {it.ai_note}")
            if it.url:
                print(f"      {it.url}")
    if cfg.get("notifiers", {}).get("file", True):
        logfile = BASE / "data" / "alerts.log"
        logfile.parent.mkdir(parents=True, exist_ok=True)
        with logfile.open("a", encoding="utf-8") as f:
            for it in hot:
                f.write(f"{jalali_str()} | {it.score} | {it.direction} | {it.title} | {it.url}\n")
    for name, url_tpl in (("telegram", "https://api.telegram.org/bot{token}/sendMessage"),
                          ("bale", "https://tapi.bale.ai/bot{token}/sendMessage")):
        conf = cfg.get("notifiers", {}).get(name, {})
        if not conf.get("enabled"):
            continue
        token = os.environ.get(conf.get("token_env", ""), "")
        chat_id = conf.get("chat_id", "")
        if not token or not chat_id:
            continue
        text = "هشدار کدال:\n" + "\n".join(f"• [{i.score}] {i.title[:120]}" for i in hot[:10])
        try:
            payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
            req = urllib.request.Request(url_tpl.format(token=token), data=payload)
            urllib.request.urlopen(req, timeout=20).read()
            log(f"اعلان {name} ارسال شد.")
        except Exception as e:
            log(f"ارسال اعلان {name} ناموفق: {e}")


# ---------------------------------------------------------------- گزارش HTML
def build_report(items: list[Item], cfg: dict, path: Path | str = DEFAULT_REPORT) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for it in items:
        color = {"مثبت": "#0a7d33", "منفی": "#b3261e", "خنثی": "#5f6368", "نامعلوم": "#8a6d00"}.get(it.direction, "#5f6368")
        rows.append(f"""<tr>
  <td class="score">{it.score}</td>
  <td><span class="badge" style="background:{color}">{html.escape(it.direction)}</span></td>
  <td>{html.escape(it.category)}</td>
  <td>{html.escape(it.symbol or '-')}</td>
  <td class="title">{html.escape(it.title)}{f'<div class="ai">{html.escape(it.provider)}: {html.escape(it.ai_note)}</div>' if it.ai_note else ''}</td>
  <td class="why">{html.escape(it.reason)}</td>
  <td>{f'<a href="{html.escape(it.url)}">منبع</a>' if it.url else '—'}</td>
  <td class="src">{html.escape(it.source)}</td>
</tr>""")
    doc = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<title>{html.escape(cfg.get('report_title','دیده‌بان'))} — {jalali_str()}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ font-family: Tahoma, "Segoe UI", "Vazirmatn", sans-serif; margin: 0; background: #f7f7f9; color: #1d1d1f; }}
  header {{ background: #102a43; color: #fff; padding: 18px 22px; }}
  header h1 {{ margin: 0 0 6px; font-size: 20px; }}
  header .meta {{ font-size: 12px; opacity: .85; }}
  main {{ padding: 18px 22px 40px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; font-size: 13px; }}
  th, td {{ border-bottom: 1px solid #e5e7eb; padding: 8px 10px; text-align: right; vertical-align: top; }}
  th {{ background: #eef2f7; font-size: 12.5px; }}
  .score {{ font-weight: bold; font-variant-numeric: tabular-nums; }}
  .badge {{ color: #fff; border-radius: 10px; padding: 2px 8px; font-size: 11.5px; }}
  .title {{ min-width: 260px; }}
  .why {{ color: #444; max-width: 320px; }}
  .src, .meta {{ color: #6b7280; font-size: 12px; }}
  .ai {{ margin-top: 4px; color: #0b5394; font-size: 12px; }}
  footer {{ margin-top: 18px; font-size: 11.5px; color: #6b7280; line-height: 1.9; }}
  .note {{ background: #fff8e1; border: 1px solid #f0e0a8; padding: 10px 12px; border-radius: 8px; font-size: 12.5px; margin-bottom: 14px; }}
  @media print {{ body {{ background: #fff; }} }}
</style></head>
<body>
<header>
  <h1>{html.escape(cfg.get('report_title','دیده‌بان'))}</h1>
  <div class="meta">زمان گزارش: {jalali_str()} · تعداد رکورد: {len(items)}</div>
</header>
<main>
  <div class="note">این گزارش «دستیار تصمیم» است، نه توصیهٔ معامله. هیچ سود تضمینی در آن نیست.
  امتیاز، ترکیبی از نوع رویداد، تازگی خبر و وجود عدد کمّی است. تصمیم نهایی و مسئولیت آن بر عهدهٔ کاربر است.</div>
  <table>
    <thead><tr><th>امتیاز</th><th>جهت</th><th>دسته</th><th>نماد</th><th>عنوان</th><th>چرا مهم است</th><th>منبع</th><th>مأخذ</th></tr></thead>
    <tbody>{''.join(rows) or '<tr><td colspan="8">رکوردی نیست.</td></tr>'}</tbody>
  </table>
  <footer>
    ساختهٔ دیده‌بان کدال نسخهٔ {VERSION} · {html.escape(cfg.get('credit', CREDIT))}<br>
    برای اجرای روزانه: <code>python kodal_alert.py watch --minutes 15</code>
  </footer>
</main></body></html>"""
    path.write_text(doc, encoding="utf-8")
    return path


# ---------------------------------------------------------------- خط لوله
def run_pipeline(cfg: dict, store: Store, sources: list[str] | None = None) -> list[Item]:
    collected: list[Item] = []
    srcs = sources or [f"rss:{s.get('url')}" if s.get("type") == "rss" else s.get("type", "")
                       for s in cfg.get("sources", [])]
    for spec in srcs:
        kind, _, value = spec.partition(":")
        if kind == "file":
            collected.extend(load_file_source(value, cfg))
        elif kind == "rss":
            local = dict(cfg)
            local["sources"] = [{"type": "rss", "name": "خبر", "url": value}]
            collected.extend(fetch_rss(local))
        elif kind == "codal":
            collected.extend(fetch_codal(cfg))
        elif kind == "demo":
            collected.extend(load_file_source(str(BASE / "demo" / "announcements.json"), cfg))
            collected.extend(parse_feed((BASE / "demo" / "news.rss").read_text(encoding="utf-8"), "خبر نمونه", cfg))
        else:
            log(f"منبع ناشناخته: {spec}")

    fresh: list[Item] = []
    for it in collected:
        if it.score >= int(cfg.get("min_score_to_alert", 45)) or symbol_in_watchlist(it, cfg.get("watchlist", [])):
            llm_enrich(it, cfg)
            if store.add(it):
                fresh.append(it)
    store.commit()
    store.log_run(",".join(srcs), len(fresh))
    return sorted(fresh, key=lambda i: i.score, reverse=True)


def cmd_run(args) -> int:
    cfg = load_config(args.config)
    store = Store(cfg.get("db_path") or DEFAULT_DB)
    items = run_pipeline(cfg, store, args.source)
    notify(items, cfg)
    path = build_report(store.recent(200), cfg, cfg.get("report_path") or DEFAULT_REPORT)
    log(f"گزارش ساخته شد: {path}")
    return 0


def cmd_watch(args) -> int:
    cfg = load_config(args.config)
    while True:
        cmd_run(args)
        log(f"خواب {args.minutes} دقیقه‌ای…")
        try:
            time.sleep(max(1, args.minutes) * 60)
        except KeyboardInterrupt:
            log("خارج شد.")
            return 0


def cmd_report(args) -> int:
    cfg = load_config(args.config)
    store = Store(cfg.get("db_path") or DEFAULT_DB)
    path = build_report(store.recent(args.limit), cfg, cfg.get("report_path") or DEFAULT_REPORT)
    log(f"گزارش از پایگاه‌داده: {path} ({store.count()} رکورد)")
    return 0


def cmd_import(args) -> int:
    cfg = load_config(args.config)
    store = Store(cfg.get("db_path") or DEFAULT_DB)
    items = load_file_source(args.file, cfg)
    fresh = [i for i in items if store.add(i)]
    store.commit()
    log(f"{len(fresh)} رکورد تازه از {len(items)} رکورد ورودی ثبت شد.")
    notify(fresh, cfg)
    return 0


def cmd_stats(args) -> int:
    cfg = load_config(args.config)
    store = Store(cfg.get("db_path") or DEFAULT_DB)
    rows = store.conn.execute(
        "SELECT category, COUNT(*), AVG(score) FROM items GROUP BY category ORDER BY COUNT(*) DESC").fetchall()
    print(f"کل رکوردها: {store.count()}")
    print(f"{'دسته':<24}{'تعداد':>8}{'میانگین امتیاز':>16}")
    for cat, n, avg in rows:
        print(f"{cat:<24}{n:>8}{avg:>16.1f}")
    return 0


def cmd_selftest(args) -> int:
    """آزمون سریع درون‌برنامه‌ای (بدون نیاز به unittest)."""
    checks = 0
    cat, direction, score, why = classify("افزایش سرمایه از محل تجدید ارزیابی دارایی‌ها", "")
    assert cat == "افزایش سرمایه" and direction == "مثبت" and score >= 80, (cat, direction, score)
    checks += 1
    cat2, dir2, s2, _ = classify("اعلام توقف نماد به دلیل ابهام در اطلاعات", "")
    assert cat2 == "توقف و بازگشایی نماد" and dir2 == "منفی", (cat2, dir2)
    checks += 1
    j = g2j(2026, 9, 22)
    assert j == (1405, 6, 31), j
    checks += 1
    it = Item(title="تست")
    assert len(it.key()) == 16
    checks += 1
    print(f"خودآزمون: {checks} بررسی موفق")
    return 0


def cmd_demo(args) -> int:
    args.source = ["demo"]
    cfg = load_config(args.config)
    cfg["db_path"] = str(BASE / "data" / "demo.sqlite3")
    cfg["report_path"] = str(BASE / "data" / "demo-report.html")
    store = Store(cfg["db_path"])
    items = run_pipeline(cfg, store, ["demo"])
    notify(items, cfg)
    path = build_report(store.recent(200), cfg, cfg["report_path"])
    log(f"گزارش نمونه ساخته شد: {path}")
    return 0


# ---------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="دیده‌بان اطلاعیه‌های کدال و خبر بازار سرمایه (بدون وابستگی بیرونی)")
    ap.add_argument("--config", help="مسیر پروندهٔ تنظیمات JSON")
    ap.add_argument("--db", help="مسیر پایگاه‌دادهٔ SQLite (پیش‌فرض: data/kodal.sqlite3)")
    sub = ap.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="یک بار اجرا")
    p_run.add_argument("--source", action="append", help="منبع: demo | file:PATH | rss:URL | codal")
    p_run.set_defaults(func=cmd_run)

    p_watch = sub.add_parser("watch", help="اجرای دوره‌ای")
    p_watch.add_argument("--minutes", type=int, default=15)
    p_watch.add_argument("--source", action="append")
    p_watch.set_defaults(func=cmd_watch)

    p_rep = sub.add_parser("report", help="ساخت گزارش از پایگاه‌داده")
    p_rep.add_argument("--limit", type=int, default=200)
    p_rep.set_defaults(func=cmd_report)

    p_imp = sub.add_parser("import", help="ورود اطلاعیه‌ها از پروندهٔ JSON یا CSV")
    p_imp.add_argument("file")
    p_imp.set_defaults(func=cmd_import)

    sub.add_parser("stats", help="آمار دسته‌ها").set_defaults(func=cmd_stats)
    sub.add_parser("demo", help="اجرای کامل روی دادهٔ نمونه").set_defaults(func=cmd_demo)
    sub.add_parser("selftest", help="آزمون سریع").set_defaults(func=cmd_selftest)
    sub.add_parser("version", help="نسخه").set_defaults(func=lambda a: (print(f"kodal-alert {VERSION}"), 0)[1])

    args = ap.parse_args(argv)
    if not getattr(args, "cmd", None):
        ap.print_help()
        return 0
    if getattr(args, "db", None):
        args.config = args.config
        cfg_override = {"db_path": args.db}
        original = load_config

        def patched(path):  # اعمال --db روی هر زیرفرمان
            cfg = original(path)
            cfg.update(cfg_override)
            return cfg

        globals()["load_config"] = patched
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
