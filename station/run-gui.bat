@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ایستگاه تصمیم مشتقه در حال روشن شدن است...
python web_server.py --port 8765
pause
