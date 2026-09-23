#!/usr/bin/env python3
"""ساخت «کوله‌پشتی دمو» — بسته‌ای که بدون اینترنت هم کار می‌کند.

چرا: اینترنت ایران در ۲۰۲۶ به‌شدت محدود است (خاموشی سراسری، وایت‌لیست، و بسته‌شدن مکرر
سرویس‌های خارجی). پس ستون فقرات دمو نباید هیچ لینک خارجی باشد. این بسته سه راه دارد:

  ۱) **نمونهٔ ثابت** (`demo/`): با دوبار کلیک روی `شروع-از-اینجا.html` باز می‌شود؛ **بدون اینترنت**.
  ۲) **دمو روی شبکهٔ محلی** (`RUN-DEMO-LAN.*`): همان نمونه از روی خود لپ‌تاپ سرو می‌شود و کارفرما
     با گوشی/لپ‌تاپ خودش، در همان اتاق، باز می‌کند. باز هم بدون اینترنت.
  ۳) **برنامهٔ زنده** (`RUN-LIVE-*`): ایستگاه واقعی (دروازهٔ ورود، ورود اعداد، موتور ریاضی) روی
     لپ‌تاپ اجرا می‌شود و در شبکهٔ محلی در دسترس است. اگر پایتون روی ویندوز نصب نیست،
     `python/` (نسخهٔ قابل‌حمل، بدون نصب) را کنارش می‌گذارد.

اجرا:
  python3 make_backpack.py                 # بستهٔ سبک (نمونه + برنامه + اسکریپت‌ها)
  python3 make_backpack.py --with-python   # به‌همراه پایتون قابل‌حمل ویندوز (برای RUN-LIVE روی ویندوز)
  python3 make_backpack.py --zip
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent                     # .../money/gui
MONEY = BASE.parent
HERE_DELIVERY = MONEY / "delivery"
NAME = "iran-desk-backpack"
DEMO_SRC = HERE_DELIVERY / "iran-desk-demo"                # ساختهٔ make_demo_site.py
PY_EMBED = Path("/tmp/py-embed.zip")                       # اگر باشد، در بسته می‌رود

sys.path.insert(0, str(BASE))
import make_kit                                            # noqa: E402

START_HTML = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>کوله‌پشتی دمو — ایستگاه تصمیم مشتقه</title>
<style>
  :root { --green:#0b3d2e; --ink:#1d1d1f; --muted:#6b7280; --line:#e3e6ea; --bg:#f6f7f9; --gold:#f0c674; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink); font-family:Tahoma,"Segoe UI",Vazirmatn,"Noto Naskh Arabic",sans-serif; line-height:2; }
  header { background:var(--green); color:#fff; padding:26px 22px; }
  header h1 { margin:0 0 8px; font-size:24px; }
  header p { margin:0; opacity:.9; font-size:14px; }
  .wrap { max-width:940px; margin:0 auto; padding:20px 22px 70px; }
  .step { background:#fff; border:1px solid var(--line); border-radius:14px; padding:18px 20px; margin:16px 0; }
  .step h2 { margin:0 0 6px; font-size:19px; color:var(--green); }
  .step .tag { display:inline-block; background:#d7e6df; color:#0b3d2e; border-radius:20px; padding:2px 12px; font-size:12.5px; margin-bottom:8px; }
  .cta { display:inline-block; background:var(--green); color:#fff; text-decoration:none; padding:12px 22px; border-radius:10px; font-weight:bold; margin:8px 0 2px; }
  .cta.alt { background:#0a7d33; }
  .hint { color:var(--muted); font-size:13.5px; }
  table { width:100%; border-collapse:collapse; margin:10px 0; font-size:13.5px; }
  td, th { border-bottom:1px solid var(--line); padding:8px; text-align:right; vertical-align:top; }
  th { color:var(--muted); font-weight:normal; }
  .warn { background:#fff8e1; border:1px solid #f0e0a8; border-radius:12px; padding:14px 16px; font-size:13.5px; margin:14px 0; }
  code { background:#f0f2f4; border-radius:6px; padding:1px 6px; direction:ltr; display:inline-block; }
  .credit { text-align:center; background:var(--green); color:#fff; border-radius:12px; padding:14px; margin-top:26px; font-size:13.5px; }
  .credit a { color:var(--gold); }
</style>
</head>
<body>
<header>
  <h1>کوله‌پشتی دمو — ایستگاه تصمیم مشتقه</h1>
  <p>سه راه، از بی‌خطرترین به کامل‌ترین. همه‌شان بدون اینترنت کار می‌کنند.</p>
</header>
<div class="wrap">

  <div class="warn">
    <b>اینترنت لازم نیست.</b> کارفرما در اینترنت ایران ممکن است به سرویس‌های خارجی دسترسی نداشته باشد؛
    برای همین هیچ‌کدام از این سه راه به اینترنت بیرونی وابسته نیست. همه‌چیز از روی همین لپ‌تاپ اجرا می‌شود.
  </div>

  <div class="step">
    <div class="tag">راه ۱ · بدون هیچ نصب</div>
    <h2>نمونهٔ ثابت را نشان بده</h2>
    <p class="hint">خودِ رابط برنامه با اعداد یک اجرای واقعی. روی فایل زیر دوبار کلیک کن (یا این دکمه را بزن):</p>
    <p><a class="cta" href="demo/index.html">بازکردن نمونهٔ ثابت →</a></p>
    <table>
      <tr><th>می‌بینی</th><th>یعنی چه</th></tr>
      <tr><td>۱۱ گام برنامه</td><td>همان چیزی که کارفرما با آن کار می‌کند</td></tr>
      <tr><td>خروجی‌های واقعی</td><td>برگهٔ پیشنهاد، جلسهٔ بازبینی، روز اول مشتری، مراسم فروش و…</td></tr>
    </table>
    <p class="hint">در این نسخه اعداد با ورودی تغییر نمی‌کنند (روی فایل ذخیره شده‌اند). برای «زنده» راه ۳ را ببین.</p>
  </div>

  <div class="step">
    <div class="tag">راه ۲ · بدون اینترنت، روی گوشی کارفرما</div>
    <h2>نمونه را روی شبکهٔ محلی باز کن</h2>
    <p class="hint">کارفرما با گوشی یا لپ‌تاپ خودش، در همان اتاق، آدرس را باز می‌کند. فقط باید هر دو روی یک وای‌فای باشید.</p>
    <table>
      <tr><th>سیستم</th><th>چه فایلی را اجرا کن</th></tr>
      <tr><td>ویندوز</td><td><code>RUN-DEMO-LAN-WINDOWS.bat</code> (دوبار کلیک)</td></tr>
      <tr><td>لینوکس/مک</td><td><code>bash RUN-DEMO-LAN-LINUX.sh</code></td></tr>
    </table>
    <p class="hint">اسکریپت خودش آدرس شبکهٔ محلی را چاپ می‌کند (مثل <code>http://192.168.1.5:8080</code>). همان را روی گوشی کارفرما بزن.</p>
  </div>

  <div class="step">
    <div class="tag">راه ۳ · کامل (زنده)</div>
    <h2>برنامهٔ واقعی را اجرا کن</h2>
    <p class="hint">ایستگاه واقعی: دروازهٔ ورود، پنل مدیر، ورود اعداد، موتور ریاضی، دفتر زنجیره‌هش‌دار.
      کارفرما با حساب مهمان وارد می‌شود و پنل مدیریت برایش بسته است.</p>
    <table>
      <tr><th>سیستم</th><th>چه فایلی</th><th>شرط</th></tr>
      <tr><td>ویندوز</td><td><code>RUN-LIVE-WINDOWS.bat</code></td><td>پوشهٔ <code>python</code> کنار بسته باشد (نسخهٔ قابل‌حمل) یا خود ویندوز پایتون داشته باشد</td></tr>
      <tr><td>لینوکس/مک</td><td><code>bash RUN-LIVE-LINUX.sh</code></td><td>پایتون ۳.۱۱+</td></tr>
    </table>
    <p><a class="cta alt" href="LIVE-DEMO-FA.md">راهنمای دقیق دموی زنده (چک‌لیست ۱۰ دقیقه‌ای) →</a></p>
    <p class="hint">اگر مرورگر خودش باز نشد، آدرس چاپ‌شده در پنجرهٔ سیاه را دستی بزن.</p>
  </div>

  <div class="step">
    <div class="tag">آزمون سلامت</div>
    <h2>قبل از جلسه، یک بار آزمون کن</h2>
    <p class="hint">این اسکریپت‌ها چک می‌کنند همه‌چیز سر جایش باشد (فایل‌ها، پایتون، دروازه):</p>
    <table>
      <tr><td>ویندوز</td><td><code>CHECK-WINDOWS.bat</code></td></tr>
      <tr><td>لینوکس/مک</td><td><code>bash CHECK-LINUX.sh</code></td></tr>
    </table>
  </div>

  <div class="warn">
    <b>رمزها خودشان ساخته می‌شوند.</b> اولین بار که <code>RUN-LIVE</code> را اجرا کنی، دو رمز تصادفی ساخته می‌شود و
    در <code>station/config/CREDENTIALS-FIRST-LOGIN.txt</code> نوشته می‌شود: یکی برای پنل مدیر (خودت) و یکی برای
    کارفرما (حساب مهمان؛ پنل مدیریت برایش بسته است). آن پرونده را جدا کن و به کسی نده.
    اگر رمزها را گم کردی یا خواستی عوض کنی: <code>python3 MAKE-PASSWORDS.py --force</code>
    (ویندوز: <code>python MAKE-PASSWORDS.py --force</code>). روش کار در <code>docs/17-remote-access-fa.md</code>.
  </div>

  <div class="step">
    <div class="tag">چرا این‌طور؟</div>
    <h2>تصمیم «نمایش آفلاین»</h2>
    <p class="hint">چرا ستون فقرات نمایش به هیچ لینک اینترنتی گره نخورده، هر راه چه شرایطی دارد، و
      «راه زندهٔ کامل» چه زمانی می‌آید:</p>
    <p><a class="cta" href="docs/19-demo-offline-decision-fa.md">خواندن سند تصمیم →</a></p>
  </div>

  <div class="credit">
    <b>تهیه‌کنندهٔ جزوات: Masoud Mojarabian</b> ·
    <a href="tel:+989126630554">📱 __PHONE__</a> ·
    <a href="https://t.me/Mojarabian" target="_blank">✈️ Telegram: Mojarabian</a> ·
    <a href="https://instagram.com/Mojarabian.Art" target="_blank">📸 Instagram: Mojarabian.Art</a>
  </div>
</div>
</body>
</html>
"""

LIVE_GUIDE = """# دموی زنده در ۱۰ دقیقه (روی لپ‌تاپ خودت، بدون اینترنت)

## پیش از جلسه (۵ دقیقه)

۱. `CHECK-WINDOWS.bat` (ویندوز) یا `bash CHECK-LINUX.sh` (لینوکس/مک) را بزن و ببین «همه‌چیز آماده» می‌دهد.
۲. رمزها را تازه کن (یک بار برای همیشه):

```bash
cd station
python3 adminauth.py --set-id mafhoom --set-pass "<رمز-قوی-خودت>"
python3 gate.py --sync-admin
python3 gate.py --guest-id masoud --guest-pass "<رمز-کارفرما>"
python3 gate.py --on
python3 gate.py --status
```

۳. `RUN-LIVE-WINDOWS.bat` را بزن. پنجرهٔ سیاه آدرس شبکهٔ محلی را چاپ می‌کند؛ همان را یادداشت کن.

## سر جلسه (۱۰ دقیقه)

| دقیقه | چه کار کن | چه چیزی نشان می‌دهد |
| --- | --- | --- |
| ۰-۱ | گوشی/لپ‌تاپ کارفرما را به همان وای‌فای وصل کن و آدرس را باز کن | وارد صفحهٔ ورود می‌شود؛ بدون رمز هیچ صفحه‌ای باز نیست |
| ۱-۲ | خودش با حساب مهمان وارد شود (شناسه: masoud) | «حس مهمان‌بودن»: پنل مدیریت برایش ۴۰۳ است |
| ۲-۴ | گام ۴: «داوری سیگنال» را بزن | یک سیگنال می‌ماند یا می‌افتد، با دلیل دروازه‌ها |
| ۴-۶ | گام ۵: شوک‌آزمون با کارمزد سه‌برابر | با بدترین فرض‌ها هم جواب می‌دهد |
| ۶-۷ | گام ۶: ریاضیِ کِلی و احتمال نیم‌شدن حساب | عدد، نه وعده |
| ۷-۸ | گام ۷: برگهٔ پیشنهاد و جلسهٔ بازبینی | خروجی آمادهٔ دست‌دادن به شرکت |
| ۸-۹ | گام ۹: آزمون کور سرمایه‌گذار | خودشان امتحان می‌کنند؛ ۶ پرسش با پاسخ محاسبه‌شده |
| ۹-۱۰ | سند `docs/18-client-value-fa.md` و «سه پرسش سخت» | پاسخ آماده برای سخت‌ترین سؤال‌ها |

## اگر کارفرما خواست خودش بعداً نگاه کند

- **بدون اینترنت:** پوشهٔ `demo` را در فلش مموری بده؛ روی هر رایانه‌ای با دوبار کلیک روی
  `demo/index.html` باز می‌شود.
- **با اینترنت (اگر باز بود):** لینک نمونهٔ ثابت را بفرست (فایل `LINK-FA.txt`).
- **حساب مهمان:** با `gate.py --guest-off` هر وقت خواستی قطعش کن؛ با `--guest-on` برگردان.

## مرزهای صادقانه که خودت بگو (پیش از آنکه بپرسند)

- برنامه **سفارش خودکار نمی‌دهد** و **سود تضمینی** وعده نمی‌دهد؛ تصمیم نهایی با کاربر است.
- درصدها با بدترین حالت‌ها (کارمزد، لغزش، حرکت مخالف) هم سنجیده شده‌اند.
- این نسخه برای تصمیم واقعی، با دادهٔ بازار واقعی کار می‌کند؛ دادهٔ نمایشی برای تمرین است.
"""

RUN_LIVE_WIN = r"""@echo off
chcp 65001 >nul
title ایستگاه تصمیم مشتقه — اجرای زنده
cd /d "%~dp0"

if exist "python\python.exe" (
  set "PY=python\python.exe"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo.
    echo [!] پایتون پیدا نشد.
    echo     یا پوشهٔ "python" را از بستهٔ قابل‌حمل کنار همین فایل بگذار،
    echo     یا پایتون ۳.۱۱+ را نصب کن: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
  )
  set "PY=python"
)

if not exist "station\config\gate.json" (
  echo ── اولین اجرا: ساخت رمزها ──
  "%PY%" MAKE-PASSWORDS.py
  echo.
)
echo ── ایستگاه تصمیم مشتقه: اجرای زنده روی شبکهٔ محلی ──
echo.
echo   حساب مدیر (پنل):      mafhoom
echo   حساب کارفرما (مهمان): masoud
echo   (رمزها در پروندهٔ station\config\CREDENTIALS-FIRST-LOGIN.txt هم هست)
echo.
echo   آدرس‌هایی که کارفرما می‌تواند باز کند:
echo     http://127.0.0.1:8765          (روی همین لپ‌تاپ)
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address"') do (
  for /f "tokens=* delims= " %%b in ("%%a") do echo     http://%%b:%STATION_PORT%          (روی گوشی/لپ‌تاپ کارفرما در همان وای‌فای)
)
echo.
echo   برای بستن: همین پنجره را ببند یا Ctrl+C بزن.
echo.
"%PY%" station\web_server.py --port %STATION_PORT% --host 0.0.0.0
pause
"""

RUN_LIVE_SH = """#!/usr/bin/env bash
# اجرای زنده روی شبکهٔ محلی (لینوکس/مک). پیش‌نیاز: پایتون ۳.۱۱+
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f station/config/gate.json ]; then
  echo "── اولین اجرا: ساخت رمزها ──"
  python3 MAKE-PASSWORDS.py
  echo
fi
echo "── ایستگاه تصمیم مشتقه: اجرای زنده روی شبکهٔ محلی ──"
echo "  حساب مدیر (پنل):      mafhoom"
echo "  حساب کارفرما (مهمان): masoud"
echo "  (رمزها در پروندهٔ station/config/CREDENTIALS-FIRST-LOGIN.txt هم هست)"
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
PORT="${STATION_PORT:-8765}"
echo "  آدرس‌ها:"
echo "    http://127.0.0.1:$PORT    (روی همین دستگاه)"
[ -n "$IP" ] && echo "    http://$IP:$PORT    (روی گوشی/لپ‌تاپ کارفرما در همان شبکه)"
echo "  برای بستن: Ctrl+C"
exec python3 station/web_server.py --port "${STATION_PORT:-8765}" --host 0.0.0.0
"""

RUN_DEMO_WIN = r"""@echo off
chcp 65001 >nul
title نمونهٔ ثابت — روی شبکهٔ محلی
cd /d "%~dp0"
if "%STATION_PORT%"=="" set "STATION_PORT=8765"
if exist "python\python.exe" ( set "PY=python\python.exe" ) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo [!] برای این راه به پایتون نیاز است. راه ساده‌تر: خودِ فایل demo\index.html را دوبار کلیک کن.
    echo     (یا پوشهٔ "python" قابل‌حمل را کنار این فایل بگذار.)
    pause
    exit /b 1
  )
  set "PY=python"
)
echo ── نمونهٔ ثابت روی شبکهٔ محلی ──
echo   آدرس‌ها:
echo     http://127.0.0.1:8080       (روی همین لپ‌تاپ)
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address"') do (
  for /f "tokens=* delims= " %%b in ("%%a") do echo     http://%%b:8080       (روی گوشی کارفرما در همان وای‌فای)
)
echo   برای بستن: Ctrl+C
echo.
"%PY%" -m http.server 8080 --bind 0.0.0.0 --directory demo
pause
"""

RUN_DEMO_SH = """#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "── نمونهٔ ثابت روی شبکهٔ محلی ──"
echo "    http://127.0.0.1:8080"
[ -n "$IP" ] && echo "    http://$IP:8080   (گوشی کارفرما در همان وای‌فای)"
echo "  برای بستن: Ctrl+C"
exec python3 -m http.server 8080 --bind 0.0.0.0 --directory demo
"""

CHECK_WIN = r"""@echo off
chcp 65001 >nul
title آزمون سلامت کوله‌پشتی
cd /d "%~dp0"
setlocal enabledelayedexpansion
set OK=0
set BAD=0

echo ── آزمون سلامت کوله‌پشتی دمو ──
echo.

if exist "demo\index.html" ( echo   [OK] نمونهٔ ثابت هست & set /a OK+=1 ) else ( echo   [--] نمونهٔ ثابت نیست & set /a BAD+=1 )
if exist "station\web_server.py" ( echo   [OK] برنامهٔ زنده هست & set /a OK+=1 ) else ( echo   [--] برنامهٔ زنده نیست & set /a BAD+=1 )
if exist "station\gate.py" ( echo   [OK] دروازهٔ ورود هست & set /a OK+=1 ) else ( echo   [--] دروازه نیست & set /a BAD+=1 )
if exist "docs\18-client-value-fa.md" ( echo   [OK] سندهای تحویلی هست & set /a OK+=1 ) else ( echo   [--] سندها نیستند & set /a BAD+=1 )

if exist "python\python.exe" (
  echo   [OK] پایتون قابل‌حمل هست ^& set /a OK+=1
  set /a OK+=1
  "python\python.exe" -c "import json,http.server,sqlite3,hashlib,secrets" ^& if errorlevel 1 ( echo   [--] ماژول‌های پایتون ناقص‌اند ^& set /a BAD+=1 ) else ( echo   [OK] ماژول‌های لازم پایتون سالم‌اند ^& set /a OK+=1 )
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo   [!!] پایتون نیست: برای «برنامهٔ زنده» به آن نیاز داری ^(راه ۱ و ۲ بدون پایتون هم کار می‌کنند^)
  ) else (
    echo   [OK] پایتون روی سیستم هست ^& set /a OK+=1
    python -c "import json,http.server,sqlite3,hashlib,secrets" ^& if errorlevel 1 ( echo   [--] ماژول‌های پایتون ناقص‌اند ^& set /a BAD+=1 ) else ( echo   [OK] ماژول‌های لازم پایتون سالم‌اند ^& set /a OK+=1 )
  )
)

if exist "station\config\gate.json" (
  echo   [OK] رمزها ساخته شده‌اند ^(پروندهٔ station\config\CREDENTIALS-FIRST-LOGIN.txt^)
) else (
  echo   [..] رمزها هنوز ساخته نشده: با اجرای RUN-LIVE دوباره خودش می‌سازد
)

echo.
echo ── نتیجه: %OK% درست · %BAD% ناقص ──
echo.
echo برای دیدن نمونهٔ ثابت: روی demo\index.html دوبار کلیک کن (بدون اینترنت هم کار می‌کند).
pause
"""

CHECK_SH = """#!/usr/bin/env bash
# آزمون سلامت کوله‌پشتی (لینوکس/مک)
set -uo pipefail
cd "$(dirname "$0")"
OK=0; BAD=0
say() { printf '  %s %s\\n' "$1" "$2"; }
chk() { local path="$1" desc="$2"; if [ -e "$path" ]; then say "[OK]" "$desc"; OK=$((OK+1)); else say "[--]" "$desc"; BAD=$((BAD+1)); fi; }

echo "── آزمون سلامت کوله‌پشتی دمو ──"
chk demo/index.html "نمونهٔ ثابت هست"
chk station/web_server.py "برنامهٔ زنده هست"
chk station/gate.py "دروازهٔ ورود هست"
chk docs/18-client-value-fa.md "سندهای تحویلی هست"
if command -v python3 >/dev/null 2>&1; then
  say "[OK]" "پایتون $(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"; OK=$((OK+1))
  if python3 -c 'import json,http.server,sqlite3,hashlib,secrets' 2>/dev/null; then
    say "[OK]" "ماژول‌های لازم پایتون سالم‌اند"; OK=$((OK+1))
  else
    say "[--]" "ماژول‌های پایتون ناقص‌اند (json/sqlite3/hashlib/secrets)"; BAD=$((BAD+1))
  fi
else
  say "[!!]" "پایتون نیست (راه ۱ و ۲ بدون پایتون هم کار می‌کنند)"
fi
echo "── نتیجه: $OK درست · $BAD ناقص ──"
"""

README = """# کوله‌پشتی دمو — چطور استفاده کنم؟

**یک قاعده:** برای هیچ‌کدام از این راه‌ها به اینترنت نیاز نداری. همه‌چیز از روی همین لپ‌تاپ اجرا می‌شود.

| می‌خواهم… | فایل | پیش‌نیاز |
| --- | --- | --- |
| فقط نشان بدهم | `demo/index.html` را دوبار کلیک کن | هیچ |
| کارفرما با گوشی خودش ببیند | `RUN-DEMO-LAN-WINDOWS.bat` | پایتون (یا پوشهٔ `python` کنار بسته) |
| برنامهٔ زنده را نشان بدهم | `RUN-LIVE-WINDOWS.bat` | همان بالا |
| مطمئن شوم همه‌چیز سالم است | `CHECK-WINDOWS.bat` | هیچ |

روی لینوکس/مک، همان فایل‌های `.sh` را با `bash` اجرا کن.

**اول این را بخوان:** `شروع-از-اینجا.html` (با دوبار کلیک باز می‌شود؛ همه‌چیز را گام‌به‌گام می‌گوید).
**برای دموی زنده:** `LIVE-DEMO-FA.md`.
**چرا بدون اینترنت؟** چون اینترنت ایران محدود است و نمی‌خواهیم نمایش کارفرما به یک لینک خارجی گره بخورد.

✍️ تهیه‌کنندهٔ جزوات: Masoud Mojarabian · 📱 09126630554 · ✈️ Telegram: Mojarabian · 📸 Instagram: Mojarabian.Art
"""


def sha16(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def demo_ready() -> bool:
    """آیا نمونهٔ ثابت دمو (که کوله‌پشتی از آن ساخته می‌شود) آماده است؟

    در بستهٔ تحویلی ممکن است این پوشه نباشد؛ در آن حالت آزمون‌ها «رد» می‌شوند نه «خطا».
    """
    # شرط باید دقیقاً همان باشد که ساخت می‌سنجد، وگرنه یک پوشهٔ نیمه‌ساخته می‌تواند
    # «آماده» گزارش شود و ساخت وسط کار بترکد.
    need = (DEMO_SRC / "index.html", DEMO_SRC / "app" / "index.html",
            DEMO_SRC / "DEMO-MANIFEST.json")
    return all(x.exists() for x in need)


def build(out: Path, *, with_python: bool, link_note: str = "") -> dict:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    stats = {"copied": 0, "skipped": 0}

    # ۱) خودِ برنامه (station + desk + kodal-alert + tools + strategies) — همان چیدمانی که برنامه می‌خواهد
    make_kit.copy_tree(BASE, out / "station", data_allow=make_kit.DATA_ALLOW,
                       config_allow=make_kit.CONFIG_ALLOW, stats=stats)
    (out / "desk").mkdir(exist_ok=True)
    make_kit.copy_tree(MONEY / "desk", out / "desk", data_allow=set(), config_allow=None, stats=stats)
    make_kit.copy_tree(MONEY / "kodal-alert", out / "kodal-alert",
                       data_allow=make_kit.KODAL_DATA_ALLOW, stats=stats)
    for extra in ("tools", "strategies"):
        src = MONEY / extra
        if src.exists():
            make_kit.copy_tree(src, out / extra, stats=stats)

    # ۲) نمونهٔ ثابت (باید از قبل با make_demo_site.py ساخته شده باشد)
    if not (DEMO_SRC / "index.html").exists():
        raise SystemExit("⛔ نمونهٔ ثابت ساخته نشده. اول: python3 deploy/huggingface/make_demo_site.py")
    shutil.copytree(DEMO_SRC, out / "demo", dirs_exist_ok=True)

    # ۳) سندهای تحلیلی
    (out / "docs").mkdir(exist_ok=True)
    for doc in sorted(MONEY.glob("*.md")):
        shutil.copy2(doc, out / "docs" / doc.name)

    # ۳.۵) کمکیِ اولین اجرا (ساخت رمزها بدون هیچ فرمانی)
    shutil.copy2(BASE / "MAKE-PASSWORDS.py", out / "MAKE-PASSWORDS.py")

    # ۴) اسکریپت‌ها و راهنماها
    (out / "شروع-از-اینجا.html").write_text(START_HTML.replace("__PHONE__", "09126630554"), encoding="utf-8")
    (out / "LIVE-DEMO-FA.md").write_text(LIVE_GUIDE, encoding="utf-8")
    (out / "README-FA.md").write_text(README, encoding="utf-8")
    (out / "LINK-FA.txt").write_text(link_note or
        "لینک نمونهٔ ثابت (فقط اگر اینترنت کارفرما باز بود): در بستهٔ تحویلی، بخش «نمونهٔ ثابت» را ببین.\n"
        "یادت باشد: اینترنت ایران محدود است؛ ستون فقرات دمو، همین پوشهٔ آفلاین است.\n", encoding="utf-8")
    files = {"RUN-LIVE-WINDOWS.bat": RUN_LIVE_WIN, "RUN-DEMO-LAN-WINDOWS.bat": RUN_DEMO_WIN,
             "CHECK-WINDOWS.bat": CHECK_WIN, "RUN-LIVE-LINUX.sh": RUN_LIVE_SH,
             "RUN-DEMO-LAN-LINUX.sh": RUN_DEMO_SH, "CHECK-LINUX.sh": CHECK_SH}
    for name, body in files.items():
        p = out / name
        p.write_text(body, encoding="utf-8", newline="\r\n" if name.endswith(".bat") else "\n")
        if name.endswith(".sh"):
            p.chmod(0o755)

    # ۵) پایتون قابل‌حمل (اختیاری، برای ویندوز): بدون نصب، بدون اینترنت
    if with_python:
        if not PY_EMBED.exists():
            raise SystemExit(f"⛔ نسخهٔ قابل‌حمل پایتون نیست: {PY_EMBED}\n"
                             "   دانلود: https://www.python.org/ftp/python/3.13.7/python-3.13.7-embed-amd64.zip")
        (out / "python").mkdir(exist_ok=True)
        with zipfile.ZipFile(PY_EMBED) as z:
            z.extractall(out / "python")
        # اجازهٔ واردکردن پوشه‌های کنار بسته (پیش‌فرض embed فقط کتابخانهٔ خودش را می‌بیند)
        (out / "python" / "python313._pth").write_text(
            "python313.zip\n.\n..\\station\n", encoding="utf-8")

    # ۶) اسکن راز و مانیفست
    sys.path.insert(0, str(BASE / "deploy"))
    from security_scan import find_secret_literals             # noqa: E402
    leaked = [x for f in sorted(out.rglob("*")) if f.is_file() for x in find_secret_literals(f)]
    if leaked:
        raise SystemExit("⛔ مقدار شبیه رمز در کوله‌پشتی: \n  " + "\n  ".join(leaked))
    for banned in ("station/config/gate.json", "station/config/admin.json"):
        if (out / banned).exists():
            raise SystemExit(f"⛔ پروندهٔ راز در کوله‌پشتی: {banned}")

    all_files = sorted(f for f in out.rglob("*") if f.is_file())
    manifest = {
        "name": NAME, "files": len(all_files),
        "size_kb": sum(f.stat().st_size for f in all_files) // 1024,
        "has_python": bool(with_python and (out / "python" / "python.exe").exists()),
        "offline_demo": True,
        "key_files": {n: sha16(out / n) for n in
                      ("شروع-از-اینجا.html", "LIVE-DEMO-FA.md", "RUN-LIVE-WINDOWS.bat",
                       "RUN-LIVE-LINUX.sh", "CHECK-WINDOWS.bat", "demo/index.html")
                      if (out / n).exists()},
        "note": "کوله‌پشتی دمو: آفلاین کار می‌کند · نمونهٔ ثابت + برنامهٔ زنده روی شبکهٔ محلی + آزمون سلامت",
    }
    (out / "BACKPACK-MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="ساخت کوله‌پشتی دمو (آفلاین)")
    ap.add_argument("--out", default=str(HERE_DELIVERY / NAME))
    ap.add_argument("--with-python", action="store_true", help="پایتون قابل‌حمل ویندوز را هم بگذار")
    ap.add_argument("--link-note", default="", help="متن لینک نمونهٔ ثابت برای فایل LINK-FA.txt")
    ap.add_argument("--zip", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    m = build(out, with_python=a.with_python, link_note=a.link_note)
    print(f"کوله‌پشتی ساخته شد: {out}")
    print(f"  پرونده: {m['files']} · حجم: {m['size_kb']} کیلوبایت · "
          f"پایتون قابل‌حمل: {'هست' if m['has_python'] else 'نیست'} · اسکن راز: پاکیزه ✅")
    if a.zip:
        arch = shutil.make_archive(str(out), "zip", out.parent, out.name)
        print(f"  zip: {arch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
