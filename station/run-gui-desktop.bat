@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo نسخهٔ دسکتاپ (اگر مرورگر را نمی‌خواهید)
python station.py
pause
