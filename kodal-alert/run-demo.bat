@echo off
chcp 65001 >nul
cd /d "%~dp0"
python kodal_alert.py demo
start "" "data\demo-report.html"
