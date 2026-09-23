#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""دفترِ اتصال‌ها — «هر وقت سرویس را گرفتم، همین‌جا وصلش کنم و استفاده کنم».

چه چیزی ذخیره می‌شود:
  • `config/connections.json`  : مشخصات اتصال (قالب نشانی، مسیر JSON، نام هدر کلید، …) — بدون کلید.
  • `config/keys.local.json`   : کلیدها، فقط اگر خودتان صریحاً «ذخیرهٔ کلید» را بزنید.

چرا کلید جدا و اختیاری؟ چون کلید پول است. پیش‌فرض این است که کلید در هیچ پرونده‌ای نوشته نشود
و فقط تا بسته‌شدن برنامه در حافظه بماند. اگر ذخیره کنید، پرونده فقط روی همین رایانه است،
ولی هر کسی که به این پوشه دسترسی داشته باشد می‌تواند آن را ببیند — پس به‌جز رایانهٔ خودتان،
آن را جای دیگری نگه ندارید و در گیت/تلگرام نفرستید.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.1.0"
BASE = Path(__file__).resolve().parent
CONFIG_DIR = BASE / "config"
PROFILES_FILE = CONFIG_DIR / "connections.json"
KEYS_FILE = CONFIG_DIR / "keys.local.json"

FREE = "رایگان"
PAID = "خریدنی"
# با هر تغییر در پروفایل‌های آماده، این شماره را بالا ببرید تا روی نسخه‌های قبلی هم به‌روز شود.
PRESET_VERSION = 3

# نگه‌داشته‌شده‌ها «نقطهٔ شروع» هستند، نه وعده: هر کدام را با دکمهٔ «آزمایش اتصال» بررس کنید.
PRESET_PROFILES: list[dict] = [
    {
        "name": "mock-local",
        "label": "خوراک آزمایشی محلی (بدون اینترنت، بدون هزینه)",
        "cost": FREE,
        "url_template": "http://127.0.0.1:8788/quote?symbol={symbol}",
        "json_path": "data.0.pl",
        "key_header": "", "key_query_name": "", "env_key": "",
        "tested": True,
        "note": "برای آزمایش کامل برنامه و نشان‌دادن کارکردِ اتصال زنده به سرمایه‌گذار. دادهٔ این خوراک ساختگی است و روی آن هیچ ادعای درآمدی نمی‌شود.",
        "gives": "قیمت یک لنگه (قیمت پایه) برای همهٔ نمادها، با نوسان ساختگی و یک رخداد برنامه‌ریزی‌شده برای دیدن سیگنال",
        "after": "ستون تازگی داده سبز می‌شود و قیمت‌ها هر چند ثانیه عوض می‌شوند؛ یعنی کل مسیر فنی «زنده» کار می‌کند.",
        "steps": "۱) در پوشهٔ ایستگاه دستور `python mock_feed.py` را اجرا کنید (یا خوراک همراه کارساز خودکار بالا می‌آید). ۲) همین پروفایل را انتخاب و آزمایش کنید.",
    },
    {
        "name": "tgju-usd",
        "label": "tgju — دلار، طلا، سکه (رایگان، آزمون‌شده)",
        "cost": FREE,
        "url_template": "https://api.tgju.org/v1/market/indicator/summary-table-data/{symbol}",
        "json_path": "data.0.3",
        "key_header": "", "key_query_name": "", "env_key": "",
        "tested": True,
        "note": ("آزمون‌شده در ۲۲ سپتامبر ۲۰۲۶: پاسخ ۲۰۰ در ۰٫۳ تا ۱٫۸ ثانیه. ستون چهارم سطر اول = "
                 "قیمت پایانی. پنج شاخص (دلار، گرم طلای ۱۸، سکهٔ امامی، نیم، ربع) با یک نقطهٔ "
                 "پایانی مستقل (call1.tgju.org/ajax.json) مقایسه شد و هر پنج عدد یکی درآمد؛ پس "
                 "مسیر «data.0.3» درست است. اگر روزی ساختار عوض شد، با «کاوش پاسخ سرویس» مسیر "
                 "تازه را پیدا کنید."),
        "gives": ("قیمت زندهٔ دلار، طلا و سکه. نماد ردیف را نام شاخص tgju بگذارید: price_dollar_rl "
                  "(دلار) · geram18 (گرم طلای ۱۸) · sekeb (سکهٔ امامی) · sekee (سکهٔ بهار) · "
                  "nim (نیم) · rob (ربع)."),
        "after": ("تازگی داده سبز می‌شود و برای ردیف‌های دلار/طلا/سکه قیمت واقعی می‌آید. این "
                  "خوراک برای سهام، آتی و اختیار چیزی نمی‌دهد؛ برای آزمون «قیمت زنده» و برای "
                  "نرخ طلا/ارز پایهٔ محاسبهٔ آتی طلا کافی است."),
        "steps": ("۱) ردیف اسنپ‌شات بسازید و در ستون نماد همان نام انگلیسی شاخص را بگذارید "
                  "(مثل price_dollar_rl). ۲) همین پروفایل را انتخاب و «آزمایش اتصال» را بزنید."),
    },
    {
        "name": "tsetmc-cdn",
        "label": "tsetmc — قیمت پایانی سهام و آپشن (رایگان، آزمون‌نشده)",
        "cost": FREE,
        "url_template": "https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceDailyList/{symbol}/0",
        "json_path": "closingPriceDaily.0.pClosing",
        "key_header": "", "key_query_name": "", "env_key": "",
        "tested": False,
        "note": "منبع رسمی و رایگان است ولی بی‌تعهد. در نشانی، {symbol} باید «کد نماد» (insCode) باشد نه نام نماد؛ کد را در فیلد feed_symbol هر ردیف اسنپ‌شات بگذارید.",
        "gives": "قیمت پایانی روز برای سهم و آپشن، بر پایهٔ کد نماد",
        "after": "قیمت پایه از منبع رسمی می‌آید؛ ولی نرخ به‌روزرسانی روزانه است، نه لحظه‌ای.",
        "steps": "۱) کد نماد هر سهم را از سایت tsetmc بردارید. ۲) در اسنپ‌شات، فیلد feed_symbol هر ردیف را با آن کد پر کنید. ۳) آزمون اتصال.",
    },
    {
        "name": "exchange-irt",
        "label": "صرافی ایرانی — نرخ ریالی (رایگان، آزمون‌نشده)",
        "cost": FREE,
        "url_template": "https://api.exir.io/v2/ticker?symbol={symbol}",
        "json_path": "last",
        "key_header": "", "key_query_name": "", "env_key": "",
        "tested": True,
        "note": ("این سرویس در آزمون واقعی پاسخ سالم داد (شهریور ۱۴۰۵). برای هر ردیف، در ستون «کد نماد» "
                 "نام بازار را بنویسید: usdt-irt · btc-irt · eth-irt و مانند این‌ها. کاربردش اثبات اتصال زندهٔ "
                 "واقعی بدون کلید است، نه ساختن سیگنال سهام."),
        "gives": "نرخ لحظه‌ای ریالی از یک بازار واقعی، بدون کلید و بدون هزینه",
        "after": "تازگی داده سبز می‌شود و می‌بینید قیمت واقعی همان لحظه خوانده می‌شود.",
        "steps": "۱) پروفایل را انتخاب کنید. ۲) در گام ۲ جدول «وارد کردن اعداد کارگزاری»، در ستون کد نماد نام بازار را بنویسید. ۳) آزمون اتصال.",
    },
    {
        "name": "broker-service",
        "label": "سرویس دادهٔ خریدنی (کلیددار) — قالب نمونه",
        "cost": PAID,
        "url_template": "https://api.example.ir/Quote.php?key={key}&l18={symbol}",
        "json_path": "data.0.pl",
        "key_header": "", "key_query_name": "key", "env_key": "MARKET_API_KEY",
        "tested": False,
        "note": "این قالب نمونهٔ عمومی است؛ قالب واقعی را از مستندات فروشنده کپی کنید. معمولاً ۴ چیز می‌دهند: قیمت پایه، ریزمعاملات، زنجیرهٔ آپشن، دادهٔ تاریخی.",
        "gives": "قیمت زندهٔ همهٔ نمادها + دادهٔ تاریخی برای پس‌آزمایی",
        "after": "قیمت پایه هر ۳۰ ثانیه خودکار تازه می‌شود، تازگی داده سبز می‌ماند، و پس‌آزمایی روی دادهٔ واقعی ممکن می‌شود. وجه تضمین همچنان دستی از کارگزاری می‌آید.",
        "steps": "۱) کلید را از فروشنده بگیرید. ۲) قالب نشانی و مسیر JSON را از مستنداتش کپی کنید. ۳) کلید را همین‌جا بگذارید. ۴) آزمون اتصال. ۵) اگر درست بود، «ذخیره» بزنید تا هر بار خودکار وصل شود.",
    },
    {
        "name": "custom",
        "label": "اتصال دلخواه (خودم پرش می‌کنم)",
        "cost": FREE,
        "url_template": "", "json_path": "", "key_header": "", "key_query_name": "key", "env_key": "",
        "tested": False,
        "note": "هر سرویسی که خواستید. دو چیز لازم است: نشانی‌ای که {symbol} در آن باشد، و مسیر رسیدن به عدد قیمت در پاسخ JSON.",
        "gives": "هر چیزی که سرویس بدهد",
        "after": "همان لحظه‌ای که نشانی درست شود، قیمت زنده در همهٔ گام‌ها جاری می‌شود.",
        "steps": "۱) «کاوش پاسخ سرویس» را بزنید و نشانی را آزمایش کنید. ۲) از فهرست، مسیر عدد قیمت را انتخاب کنید. ۳) ذخیره.",
    },
]

PROFILE_FIELDS = ("name", "label", "cost", "url_template", "json_path", "key_header",
                  "key_query_name", "env_key", "note", "gives", "after", "steps", "tested", "custom")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean(profile: dict) -> dict:
    out = {k: profile.get(k, "") for k in PROFILE_FIELDS}
    out["name"] = str(out["name"] or "").strip() or "custom"
    out["label"] = str(out["label"] or out["name"]).strip()
    out["tested"] = bool(out.get("tested"))
    out["custom"] = bool(profile.get("custom"))   # دست‌کاری کاربر: در به‌روزرسانی‌ها دست نمی‌زنیم
    for k in ("url_template", "json_path", "key_header", "key_query_name", "env_key"):
        out[k] = str(out[k] or "").strip()
    return out


def default_store() -> dict:
    return {"version": 1, "preset_version": PRESET_VERSION, "selected": "mock-local",
            "updated_at": _now(), "profiles": [_clean(p) for p in PRESET_PROFILES]}


def _refresh_presets(data: dict) -> tuple[dict, bool]:
    """پروفایل‌های آماده را به نسخهٔ تازهٔ برنامه به‌روز می‌کند.

    پروفایل‌هایی که خودِ کاربر ساخته یا دست‌کاری کرده (custom) دست‌نخورده می‌مانند؛
    بدون این کار، کاربر نسخهٔ قدیمی برنامه را نگه می‌داشت و نشانی‌های اصلاح‌شده را نمی‌دید.
    """
    changed = False
    if int(data.get("preset_version", 1)) >= PRESET_VERSION:
        return data, changed
    by_name = {p["name"]: _clean(p) for p in PRESET_PROFILES}
    out = []
    for prof in data.get("profiles", []):
        name = prof.get("name")
        if name in by_name and not prof.get("custom"):
            out.append(dict(by_name[name], custom=False))
            changed = True
        else:
            out.append(prof)
    data["profiles"] = out
    data["preset_version"] = PRESET_VERSION
    return data, True


def load_store() -> dict:
    """دفتر اتصال‌ها را می‌خواند؛ اگر نبود، نسخهٔ پیش‌فرض را می‌سازد."""
    if PROFILES_FILE.exists():
        try:
            data = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
        except Exception:
            return default_store()
        if not isinstance(data, dict) or not isinstance(data.get("profiles"), list):
            return default_store()
        seen = {p["name"] for p in data["profiles"] if isinstance(p, dict)}
        for preset in PRESET_PROFILES:          # پروفایل‌های تازهٔ نسخهٔ جدید هم اضافه می‌شوند
            if preset["name"] not in seen:
                data["profiles"].append(_clean(preset))
        data["profiles"] = [_clean(p) for p in data["profiles"] if isinstance(p, dict)]
        data.setdefault("selected", "mock-local")
        data, changed = _refresh_presets(data)
        if changed:
            save_store(data)
        return data
    return default_store()


def save_store(store: dict) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    store = dict(store)
    store["version"] = 1
    store["updated_at"] = _now()
    store["profiles"] = [_clean(p) for p in store.get("profiles", [])]
    PROFILES_FILE.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    return PROFILES_FILE


def find_profile(store: dict, name: str) -> dict | None:
    for p in store.get("profiles", []):
        if p.get("name") == name:
            return p
    return None


def upsert_profile(store: dict, profile: dict) -> dict:
    prof = _clean(profile)
    prof["custom"] = True if profile.get("custom") is None else bool(profile.get("custom"))
    existing = find_profile(store, prof["name"])
    if existing:
        existing.update(prof)
        prof = existing
    else:
        store.setdefault("profiles", []).append(prof)
    return prof


def select_profile(store: dict, name: str) -> dict | None:
    prof = find_profile(store, name)
    if prof is None:
        return None
    store["selected"] = name
    return prof


def delete_profile(store: dict, name: str) -> bool:
    before = len(store.get("profiles", []))
    store["profiles"] = [p for p in store.get("profiles", []) if p.get("name") != name]
    if store.get("selected") == name:
        store["selected"] = (store["profiles"][0]["name"] if store["profiles"] else "custom")
    return len(store["profiles"]) != before


# ---------------------------------------------------------------- کلیدها
def load_keys() -> dict:
    if KEYS_FILE.exists():
        try:
            data = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def save_key(name: str, key: str) -> Path:
    """کلید را روی رایانهٔ خودتان ذخیره می‌کند (فقط با درخواست صریح شما)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = load_keys()
    if key:
        data[name] = {"key": key, "saved_at": _now()}
    else:
        data.pop(name, None)
    KEYS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(KEYS_FILE, 0o600)
    except OSError:                      # ویندوز این را نادیده می‌گیرد؛ اشکالی ندارد
        pass
    return KEYS_FILE


def stored_key(name: str) -> str:
    rec = load_keys().get(name) or {}
    return str(rec.get("key", "")) if isinstance(rec, dict) else ""


def resolve_key(profile: dict, *, inline_key: str = "") -> tuple[str, str]:
    """کلید را به ترتیب اولویت پیدا می‌کند و می‌گوید از کجا آمد.

    ترتیب: کلیدی که همین حالا در کادر گذاشته‌اید ← کلید ذخیره‌شده ← متغیر محیطی.
    هیچ‌وقت کلید را در لاگ یا گزارش چاپ نمی‌کند.
    """
    if inline_key:
        return inline_key, "کادر همین لحظه"
    saved = stored_key(str(profile.get("name", "")))
    if saved:
        return saved, "ذخیره‌شده روی همین رایانه"
    env_name = str(profile.get("env_key", "") or "").strip()
    if env_name:
        env_val = os.environ.get(env_name, "")
        if env_val:
            return env_val, f"متغیر محیطی {env_name}"
    return "", "بدون کلید"


def key_status(name: str) -> dict:
    store = load_store()
    prof = find_profile(store, name) or {}
    key, where = resolve_key(prof)
    env_name = str(prof.get("env_key", "") or "")
    return {"stored": bool(stored_key(name)), "where": where, "has_key": bool(key),
            "env_key": env_name, "env_set": bool(env_name and os.environ.get(env_name))}


def live_config(profile: dict) -> dict:
    """پروفایل را به قالب تنظیمات زندهٔ datafeed تبدیل می‌کند."""
    import datafeed                       # واردکردن تنبل: این ماژول باید مستقل هم کار کند
    cfg = dict(datafeed.DEFAULT_LIVE_CONFIG)
    cfg["url_template"] = str(profile.get("url_template", "") or "")
    cfg["json_path"] = str(profile.get("json_path", "") or "")
    cfg["key_header"] = str(profile.get("key_header", "") or "")
    cfg["key_query_name"] = str(profile.get("key_query_name", "") or "")
    return cfg


def apply_profile(store: dict, name: str, *, inline_key: str = "") -> dict:
    """پروفایل انتخابی را «فعال» می‌کند: تنظیمات زنده + کلید + یادداشت منبع."""
    prof = select_profile(store, name)
    if prof is None:
        raise KeyError(f"پروفایل پیدا نشد: {name}")
    key, where = resolve_key(prof, inline_key=inline_key)
    return {"name": prof["name"], "profile": prof, "live_cfg": live_config(prof),
            "key": key, "key_where": where, "is_mock": prof["name"] == "mock-local"}


def active_or_none() -> dict | None:
    """پروفایل فعالِ ذخیره‌شده را برمی‌گرداند (برای راه‌اندازی خودکار برنامه)."""
    store = load_store()
    name = store.get("selected") or ""
    if not name or find_profile(store, name) is None:
        return None
    try:
        return apply_profile(store, name)
    except KeyError:
        return None


def summary_rows() -> list[list[str]]:
    """ردیف‌های خلاصه برای جدول رابط گرافیکی."""
    store = load_store()
    rows = []
    for p in store.get("profiles", []):
        status = "آزمون‌شده" if p.get("tested") else "آزمون‌نشده"
        mark = "★" if p.get("name") == store.get("selected") else ""
        rows.append([mark, p.get("label", p["name"]), p.get("cost", ""), status,
                     p.get("url_template", "") or "—"])
    return rows


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="دفتر اتصال‌های ایستگاه")
    ap.add_argument("--list", action="store_true", help="نمایش پروفایل‌ها")
    ap.add_argument("--select", help="انتخاب پروفایل با نام")
    args = ap.parse_args(argv)
    store = load_store()
    if args.select:
        prof = select_profile(store, args.select)
        if prof is None:
            print("پروفایل پیدا نشد.")
            return 2
        save_store(store)
        print(f"پروفایل فعال شد: {prof['label']}")
    if args.list or not args.select:
        active = store.get("selected")
        for row in summary_rows():
            print(" | ".join(str(c) for c in row))
        print(f"فعال: {active}")
        print(f"پروندهٔ مشخصات: {PROFILES_FILE}")
        print(f"کلیدهای ذخیره‌شده: {'دارد' if load_keys() else 'ندارد'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
