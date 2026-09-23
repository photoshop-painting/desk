@echo off
chcp 65001 >nul
cd /d "%~dp0"
python kodal_alert.py run --source codal --source rss:https://www.farsnews.ir/rss
echo.
echo گزارش ساخته شد در data\report.html
timeout /t 5 >nul
