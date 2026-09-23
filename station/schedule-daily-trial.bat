@echo off
REM ---------------------------------------------------------------------------
REM  زمان‌بندی خودکار مراسم روزانه در ویندوز (کارهای زمان‌بندی‌شده).
REM  پیش‌فرض: هر روز ساعت 13:15. برای تغییر ساعت، عدد را عوض کنید.
REM  برای حذف:  schtasks /delete /tn "Station-Daily-Trial" /f
REM ---------------------------------------------------------------------------
chcp 65001 >nul
cd /d "%~dp0"
set TASK=Station-Daily-Trial
set TIME=13:15
set PY=%~dp0daily_trial.py
schtasks /create /tn "%TASK%" /tr "python \"%PY%\"" /sc daily /st %TIME% /f
if errorlevel 1 (
  echo.
  echo  ساخت زمان‌بندی نشد. پنجرهٔ فرمان را با «اجرا به‌عنوان مدیر» باز کنید و دوباره امتحان کنید.
) else (
  echo.
  echo  زمان‌بندی ساخته شد: هر روز ساعت %TIME% مراسم روزانه خودش اجرا می‌شود.
  echo  کارنامه و لاگ هر روز در پوشهٔ data به‌روز می‌شود.
)
pause
