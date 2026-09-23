@echo off
chcp 65001 >nul
cd /d "%~dp0"
python desk.py run --market market-demo.json --kodal-db ..\kodal-alert\data\demo.sqlite3
start "" "data\dashboard.html"
