"""ساخت «بستهٔ تحویل شرکت» از همین درخت کد — یک پوشهٔ تمیز و قابل کپی روی هر رایانه.

چه می‌کند: کد و قالب‌ها و اسناد را برمی‌دارد، ولی **آنچه با اجرا ساخته شده** (گزارش‌ها، دفترها،
بسته‌های شاهد، حافظهٔ نهان، خروجی آزمون‌ها) را با خودش نمی‌برد؛ چون شرکت باید از صفر خودش
بسازد و راستی‌آزمایی کند. اثر انگشت هر پرونده هم در `KIT-MANIFEST.json` می‌آید تا بشود بسته را
بعداً بازبینی کرد.

اجرا (از پوشهٔ همین پرونده):
    python3 make_kit.py                 # ساخت پوشه در ../delivery/iran-desk-kit
    python3 make_kit.py --zip           # + ساخت فایل zip برای تحویل
    python3 make_kit.py --out /مسیر/دلخواه
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"

BASE = Path(__file__).resolve().parent            # .../money/gui
MONEY = BASE.parent                               # .../money
DEFAULT_OUT = MONEY / "delivery"
KIT_NAME = "iran-desk-kit"

# پوشه‌ها/پسوندهایی که هرگز به بسته نمی‌روند
SKIP_DIRS = {"__pycache__", ".cache", ".pytest_cache", "export", ".git", "node_modules"}
SKIP_SUFFIX = {".pyc", ".pyo", ".log"}

# از پوشهٔ داده، فقط قالب‌ها می‌روند (نه گزارش و دفتر و حافظهٔ نهان)
DATA_ALLOW = {"snapshot-template.json", "history-template.csv", "history-demo.csv",
              "data-requirement-sheet.md"}
# از پوشهٔ تنظیمات: اتصال‌های آماده می‌روند، ولی رمز پنل نه (کاربر خودش می‌سازد)
CONFIG_ALLOW = {"connections.json"}
# از دادهٔ دیده‌بان: نمونهٔ همراه برنامه بماند
KODAL_DATA_ALLOW = {"demo.sqlite3"}

RUN_HINT = """
## اجرا

**ویندوز:** روی `station\\run-gui.bat` دوبار کلیک کنید.
**لینوکس/مک:**

```bash
cd station
python3 web_server.py --port 8765
```

بعد در مرورگر بروید به `http://localhost:8765`. (نسخهٔ دسکتاپ: `python3 station.py`.)
"""


def sha16(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def ignored(p: Path) -> bool:
    if p.name in SKIP_DIRS:
        return True
    return p.suffix in SKIP_SUFFIX


def copy_tree(src: Path, dst: Path, *, data_allow: set[str] | None = None,
              config_allow: set[str] | None = None, kodal_data_allow: set[str] | None = None,
              stats: dict | None = None) -> int:
    """کپی درخت با فیلترها. تعداد پروندهٔ کپی‌شده را برمی‌گرداند."""
    n = 0
    for item in sorted(src.rglob("*")):
        rel = item.relative_to(src)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if item.suffix in SKIP_SUFFIX:
            continue
        if item.is_dir():
            continue
        top = rel.parts[0] if len(rel.parts) > 1 else ""
        name = rel.name
        if top == "data" and data_allow is not None and name not in data_allow:
            if stats is not None:
                stats["skipped"] += 1
            continue
        if top == "config" and config_allow is not None and name not in config_allow:
            if stats is not None:
                stats["skipped"] += 1
            continue
        if src.name == "data" and kodal_data_allow is not None and name not in kodal_data_allow:
            if stats is not None:
                stats["skipped"] += 1
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        n += 1
    return n


def build(out_root: Path, *, zip_it: bool = False) -> dict:
    kit = out_root / KIT_NAME
    if kit.exists():
        shutil.rmtree(kit)
    (kit / "docs").mkdir(parents=True)
    stats = {"skipped": 0, "copied": 0}

    # ۱) خودِ ایستگاه (gui) — قالب‌های داده بمانند، ساخته‌شده‌ها نه
    stats["copied"] += copy_tree(BASE, kit / "station", data_allow=DATA_ALLOW,
                                 config_allow=CONFIG_ALLOW, stats=stats)

    # ۲) میز معاملات (desk) — بدون پایگاه داده و داشبورد اجراشده
    (kit / "desk").mkdir(exist_ok=True)
    stats["copied"] += copy_tree(MONEY / "desk", kit / "desk",
                                 data_allow=set(), config_allow=None, stats=stats)

    # ۳) دیده‌بان کدال — فقط نمونهٔ همراه
    stats["copied"] += copy_tree(MONEY / "kodal-alert", kit / "kodal-alert",
                                 data_allow=KODAL_DATA_ALLOW, stats=stats)

    # ۴) موتور ریاضی مشتقه و آزمونش
    stats["copied"] += copy_tree(MONEY / "tools", kit / "tools", stats=stats)

    # ۵) جزوهٔ راهبردها
    stats["copied"] += copy_tree(MONEY / "strategies", kit / "strategies", stats=stats)

    # ۶) سندهای تحلیلی
    for doc in sorted(MONEY.glob("*.md")):
        shutil.copy2(doc, kit / "docs" / doc.name)
        stats["copied"] += 1

    # ۶.۵) آزمون تعاملی مرورگری (شاهد آزمون‌پذیری؛ با node اجرا می‌شود)
    jsdom_test = None
    probe = BASE
    for _ in range(4):                      # آزمون تعاملی چند پله بالاتر است؛ تا چهار پله می‌جوییم
        cand = probe / "test-interactive.mjs"
        if cand.exists():
            jsdom_test = cand
            break
        probe = probe.parent
    if jsdom_test:
        shutil.copy2(jsdom_test, kit / "station" / "tools" / "test-interactive.mjs")
        stats["copied"] += 1

    # ۷) راهنمای شروع
    (kit / "START-HERE-FA.md").write_text(start_here(), encoding="utf-8")
    stats["copied"] += 1

    # ۸) فهرست و اثر انگشت هر پرونده
    files = []
    for p in sorted(kit.rglob("*")):
        if p.is_file() and p.name != "KIT-MANIFEST.json":
            files.append({"path": str(p.relative_to(kit)).replace("\\", "/"),
                          "bytes": p.stat().st_size, "sha256": sha16(p)})
    manifest = {
        "kit": KIT_NAME,
        "version": VERSION,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "files_count": len(files),
        "bytes": sum(f["bytes"] for f in files),
        "skipped_generated": stats["skipped"],
        "note": ("این بسته فقط کد و قالب و سند دارد؛ هر گزارش و دفتر و بستهٔ شاهد، روی رایانهٔ "
                 "خودتان از صفر ساخته می‌شود تا راستی‌آزمایی ممکن باشد. اثر انگشت هر پرونده "
                 "اینجا آمده تا بشود بازبینی کرد که چیزی بعداً عوض نشده."),
        "files": files,
    }
    (kit / "KIT-MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    out = {"kit": str(kit), "files": len(files) + 1,
           "bytes": manifest["bytes"], "skipped": stats["skipped"]}
    if zip_it:
        arch = shutil.make_archive(str(out_root / KIT_NAME), "zip", out_root, KIT_NAME)
        out["zip"] = arch
        out["zip_bytes"] = Path(arch).stat().st_size
    return out


def start_here() -> str:
    return f"""# از این‌جا شروع کنید — مجموعهٔ ابزار تصمیم‌گیری مشتقه (نسخهٔ بستهٔ {VERSION})

این پوشه، «بستهٔ تحویل» است: کد و قالب‌ها و سندها. **هیچ گزارش یا دفتر آماده‌ای داخلش نیست**؛
و همین نقطهٔ قوتش است: هر عددی که می‌بینید، روی همین رایانه از صفر ساخته می‌شود و خودتان
می‌توانید بازتولیدش کنید.

## چه چیزی داخل بسته است

| پوشه | چیست |
| --- | --- |
| `station/` | ایستگاه تصمیم مشتقه: یازده گام، رابط مرورگری و دسکتاپ، پنل مدیریت |
| `desk/` | میز معاملات: اسنپ‌شات بازار روی موتور ریاضی، دروازه‌های ریسک، بستهٔ سفارش برای اجرای انسانی |
| `kodal-alert/` | دیده‌بان خبر و هشدار کدال (نمونهٔ همراه برنامه برای دمو) |
| `tools/` | موتور ریاضی مشتقه (`derivatives_scout.py`) + آزمونش |
| `strategies/` | جزوهٔ راهبردها با درصد هرکدام، شوک‌آزمون، و منابع |
| `share/` | اسکریپت‌های «لینک دادن به کارفرما» (تونل امن + کلید خاموشی) و راهنمای تازه‌کار |
| `deploy/huggingface/` | میزبان مجانی: **نمونهٔ ثابت نمایشی روی HF Static Space** (رابط واقعی + پاسخ‌های ضبط‌شدهٔ یک اجرای واقعی + همهٔ خروجی‌ها؛ `activate_demo_site.sh` و `make_demo_site.py`) · برای Space داکری (نیازمند PRO): Dockerfile درگاه ۷۸۶۰، `boot.sh`، `render.yaml`، `activate_hf.sh` |
| `deploy/` | بردن روی سایت با یک فرمان: `deploy.sh` + `preflight.sh` + `setup-domain.sh` + Dockerfile/compose/Caddy/systemd + پشتیبان روزانه (`install-backup.sh`/`backup.sh`) و بازگردانی (`restore.sh`) + راهنمای فارسی (خاموش‌کردن، حذف، و تمرین بازیابی هم نوشته شده) |
| `docs/` | نوزده سند تحلیلی فارسی: از ایده‌های درآمدی تا ریاضیِ پول، راهنمای تازه‌کار، راهنمای گرفتن اولین جلسه، راهنمای بعد از جلسه (روز اول مشتری)، راهنمای جلسهٔ بازبینی دو هفته‌ای، راهنمای دسترسی از راه دور، و سند «خروجی‌ها برای کارفرما» |
| `START-HERE-FA.md` | همین پرونده |
| `KIT-MANIFEST.json` | فهرست همهٔ پرونده‌ها با اثر انگشت `sha256` (برای بازبینی) |

## نصب لازم نیست

فقط **پایتون ۳٫۱۰ یا بالاتر** لازم است؛ هیچ بستهٔ بیرونی، هیچ اینترنت اجباری، هیچ کلیدی، هیچ
هزینهٔ ماهانه. (کارت گرافیک، داکر، سرور هم لازم نیست.)
{RUN_HINT}
## ده دقیقهٔ اول (به همین ترتیب)

۱. **پنل مدیریت.** گام ۱ → «باز کردن پنل مدیریت» (یا نشانی `http://localhost:8765/admin`).
   بار اول می‌نویسد که شناسه و رمز ساخته نشده. در پوشهٔ `station` یک بار این را بزنید و
   رمز خودتان را بگذارید و جای دیگری نگه دارید:

```bash
python3 adminauth.py --set-id mafhoom --set-pass "رمز-خودتان"
```

۲. داخل پنل: «بررسی سلامت برنامه» باید **۸ از ۸ سالم** بدهد. اگر همه سالم بود، نصب درست است.

۳. **گام ۲:** «ساخت قالب نمونه» و بعد «آزمایش خواندن این پرونده» (برنامه داده می‌خواند).
   بعد یک پروفایل رایگان را «آزمایش اتصال این پروفایل» و اگر سبز شد «ذخیره و فعال کردن».

۴. **گام ۵:** «شروع محاسبه» — سیگنال‌ها با دلیل «می‌ماند یا می‌افتد» می‌آیند.

۵. **گام ۹:** «اجرای مراسم امروز» → «به‌روزرسانی جدول» → «بررسی زنجیرهٔ هش» (باید سالم باشد).

۶. **گام ۸:** «ساخت بستهٔ راستی‌آزمایی». پوشه‌ای می‌سازد با داشبورد، فهرست سیگنال‌ها، سند روش
   کار، کارنامه، پروندهٔ سرمایه‌گذار، و یک `README-FA.md` با چک‌لیست نه‌گامی برای خودتان.

۷. **گام ۸، دو دکمهٔ دیگر:** نام شرکت را بنویسید و «ساخت پیشنهاد یک‌صفحه‌ای» را بزنید — برگهٔ
   چاپی `data/offer-one-pager.html` و نسخهٔ متنی‌اش ساخته می‌شود. این همان برگه‌ای است که **پیش از**
   توافق دست شرکت می‌دهید: مسئله، سه چیزی که اضافه می‌شود، پله‌های ارائه، مرزهای صادقانه، و دو
   فرمان راستی‌آزمایی. اگر مبلغی ندهید، جای قیمت «توافقی» می‌ماند؛ برگه از خودش قیمت نمی‌سازد.

۸. **گام ۸، پیام‌های معرفی:** لحن مخاطب را از منو انتخاب کنید (شرکت، کارگزاری، مدرس، آشنای
   بازار) و «ساخت پیام‌های معرفی» را بزنید — چهار متن آماده می‌گیرید: پیام اول، پیام بعد از جواب،
   تأیید وقت، و پیگیری، به‌همراه اسکریپت تماس تلفنی و پاسخ چهار مخالفت رایج. هدف پیام اول فقط یک
   چیز است: نیم‌ساعت وقت. سند راهنمای همین کار: `docs/14-first-meeting-fa.md`.

   **تابلوی پیگیری مخاطبان** هم در همین کارت است: اسم مخاطب را بنویسید و «افزودن به تابلو» را
   بزنید؛ بعد از هر پیام «پیام اول رفت» و بعد از هر جواب «جواب داد» را بزنید.
   قاعده در خود برنامه قفل است: پیگیری فقط سه بار (روز ۰، ۳، ۱۰) و کار امروز خودش بالای کارت
   می‌آید. سه عدد هفته (پیام · تماس · جلسه) هدف را نشان می‌دهد، نه بازار را. برگهٔ چاپی هم دارد.
   نتیجهٔ «بعداً» را با یک تاریخ سر‌زدن ثبت کنید؛ همان روز خودش به «کار امروز» برمی‌گردد.

   و اگر خواستید بدانید امروز دقیقاً چه کاری و در چه دقیقه‌ای بکنید، «مراسم فروش امروز» را بزنید:
   بیست دقیقه، پنج پیام حداکثر، متن آمادهٔ هر مخاطب کنار کارش.

   روز چهاردهم که آزمون تمام شد، «ساخت برگهٔ جلسهٔ بازبینی» را بزنید: سه شاهد که خودشان اجرا
   می‌کنند، پنج شرط کارنامه، و دو خروجی روشن — ادامه با پرداخت، یا توقف بی‌گلایه‌مندی.

   وقتی جوابشان «بله» شد، «ساخت برگهٔ روز اول مشتری» را بزنید: پنج کار روز اول، دو هفته‌ای که
   در آن هیچ‌چیز خریده نمی‌شود، شرط‌های کارنامهٔ «آماده» با روز بازبینی، و قاعدهٔ پرداخت در برابر
   شاهد. سند راهنمایش: `docs/15-after-meeting-fa.md`.

راهنمای هر بخش، دکمه‌به‌دکمه و برای تازه‌کار: `docs/13-novice-walkthrough-fa.md` (در خود برنامه هم
از گام ۲ و گام ۹ باز می‌شود).

## سه کاری که فقط یک بار لازم است (و بعد فراموش کنید)

| کار | فرمان یا جای دکمه |
| --- | --- |
| گذاشتن رمز پنل (بار اول اجباری) | `python3 adminauth.py --set-id mafhoom --set-pass "رمز-خودتان"` — تا این کار را نکنید، ورود پنل انجام نمی‌شود و برنامه خودش همین فرمان را نشان می‌دهد |
| صدور اجازه‌نامهٔ نام‌دار + سند چاپی | پنل مدیریت ← بخش «مجوز دسترسی» (سند دوامضا) |
| ساخت بستهٔ شاهد برای شرکت یا سرمایه‌گذار | گام ۸ → «ساخت بستهٔ راستی‌آزمایی» |
| دسترسی از راه دور برای کارفرما (اختیاری) | `python3 gate.py --sync-admin` بعد `--guest-id masoud --guest-pass "رمز-کارفرما"` و در آخر `--on` (سند: `docs/17-remote-access-fa.md`) |

بستهٔ شاهد، سند مجوز و گواهی استفادهٔ موفق را **خودش** تازه می‌سازد و کنار شاهدها می‌گذارد
(`15-license-doc.html` · `17-usage-statement.html` و نسخه‌های متنی‌شان).

## چطور راستی‌آزمایی کنیم (عددها را خودتان بسازید)

```bash
cd station
python3 -m unittest discover -s tests        # انتظار: ۶۵۹ آزمون (۶۵۸ سبز + ۱ رد)
python3 selftest.py                          # آزمون ۱۰ دقیقه‌ای ایستگاه: ۱۵ سنجه، هر کدام دو بار
python3 usage_meter.py --summary --verify    # گواهی استفاده + سالم‌بودن زنجیرهٔ دفتر
python3 license.py --check                   # وضعیت اجازه‌نامه
```

آزمون تعاملی مرورگری (اختیاری، همان آزمونی که خودش دکمه‌ها را می‌زند): کارساز را بالا نگه دارید و
در ترمینال دیگر بزنید

```bash
cd station
npm i jsdom
python3 adminauth.py --set-id mafhoom --set-pass "رمز-پنل"     # اگر هنوز رمز نساخته‌اید
python3 gate.py --sync-admin                                  # دروازه: رمز مدیر = همین رمز پنل
python3 gate.py --guest-id masoud --guest-pass "رمز-کارفرما"  # حساب کارفرما برای آزمون گام ۱۵
python3 gate.py --on
STATION_ADMIN_PASS="رمز-پنل" STATION_GUEST_ID=masoud STATION_GUEST_PASS="رمز-کارفرما" \
  node tools/test-interactive.mjs          # انتظار: ۱۹۲ بررسی، صفر ناموفق
python3 gate.py --status                   # و در پایان، اگر خواستید: python3 gate.py --off
```

(اگر ایستگاه را روی درگاه دیگری بالا آورده‌اید، `STATION_URL` و `STATION_MOCK_URL` را هم بدهید.)
نتیجهٔ همین آزمون روی نسخهٔ بسته‌بندی‌شده، پیش از تحویل گرفته شده است: **۱۹۲ بررسی، صفر ناموفق**.

## مرزهای صادقانه (همین‌ها را در جلسه هم بگویید)

- **هیچ سفارشی به کارگزاری فرستاده نمی‌شود** و کدی هم برایش نوشته نشده؛ طبق ابلاغیهٔ مهر ۱۳۹۹
  سازمان بورس، معاملات الگوریتمی خودکار در بورس ایران «تا اطلاع ثانوی» مجاز نیست. اجرا در
  سامانهٔ کارگزاری کارِ کاربر است.
- **هیچ سود تضمینی و هیچ پیش‌بینی قیمت در کار نیست.** خروجی، «عدد و دلیل» است؛ تصمیم با کاربر.
- **دادهٔ خریدنی لازم نیست.** پروفایل‌های رایگان (دلار، طلا، سکه، صرافی) آزمون‌شده‌اند؛ اگر روزی
  سرویس خریدنی گرفتید، جای کلید و قالب نشانی در گام ۲ است.
- **دفترها محلی‌اند.** هیچ داده‌ای به بیرون فرستاده نمی‌شود؛ گواهی استفاده هم عمداً هیچ عدد مالی
  ندارد.
- **عدد بدون منبع، وارد نمی‌شود.** جای عدد نامعلوم (مثل وجه تضمین) هیچ عدد حدسی نمی‌نویسیم؛ عدد
  واقعی را از سامانهٔ کارگزاری بردارید.

## پشتیبانی و تماس

دولوپر: مهندس مسعود مجربیان · همراه: [09126630554](tel:+989126630554) ·
Telegram: [Mojarabian](https://t.me/Mojarabian) · Instagram: [Mojarabian.Art](https://instagram.com/Mojarabian.Art)

✍️ تهیه‌کنندهٔ جزوات: Masoud Mojarabian · 📱 [989126630554](tel:+989126630554) ·
✈️ [Telegram: Mojarabian](https://t.me/Mojarabian) · 📸 [Instagram: Mojarabian.Art](https://instagram.com/Mojarabian.Art)
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ساخت بستهٔ تحویل شرکت از درخت کد")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="پوشهٔ خروجی")
    ap.add_argument("--zip", action="store_true", help="ساخت فایل zip هم")
    a = ap.parse_args(argv)
    out_root = Path(a.out)
    out_root.mkdir(parents=True, exist_ok=True)
    out = build(out_root, zip_it=a.zip)
    print(f"بسته ساخته شد: {out['kit']}")
    print(f"  پرونده: {out['files']} · حجم: {out['bytes']/1024:.0f} کیلوبایت "
          f"· کنارگذاشته‌شده (ساخته‌شده‌ها): {out['skipped']}")
    if out.get("zip"):
        print(f"  zip: {out['zip']} ({out['zip_bytes']/1024:.0f} کیلوبایت)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
