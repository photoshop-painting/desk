@echo off
chcp 65001 >nul
REM آزمون کور سرمایه‌گذار: پرسش‌ها، پاسخ‌های برنامه با فرمول، و برگهٔ امضادار
cd /d "%~dp0"
echo ============================================================
echo   آزمون کور سرمایه‌گذار — اول حدس، بعد عدد
echo ============================================================
echo.
echo 1) شش پرسش بدون پاسخ (لپ‌تاپ را به سرمایه‌گذار بدهید):
echo    python investor_test.py --cases
echo.
echo 2) پاسخ‌ها با فرمول و روش دوم:
echo    python investor_test.py --reveal
echo.
echo 3) آستانهٔ ریزش راهبردها و اندازهٔ موقعیت:
echo    python investor_test.py --ladder
echo.
echo 4) حساب‌رسی یک معاملهٔ واقعی گذشته (نمونه):
echo    python investor_test.py --reconcile --symbol فولاد --entry 7000 --exit 7400 --days 30
echo.
echo 5) برگهٔ چاپی و بررسی زنجیره:
echo    python investor_test.py --sheet
echo    python investor_test.py --verify
echo.
dir /b investor_test.py >nul 2>&1
if errorlevel 1 (
  echo [خطا] investor_test.py در همین پوشه پیدا نشد.
  pause
  exit /b 1
)
python investor_test.py --cases
echo.
echo برای برگهٔ چاپی، این دستور را بزنید:  python investor_test.py --sheet
pause
