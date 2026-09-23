#!/usr/bin/env bash
# آزمون کامل ایستگاه: آزمون‌های واحد + آزمون ساخت رابط گرافیکی + اجرای پس‌آزمایی نمونه
set -e
cd "$(dirname "$0")"
echo "— آزمون‌های واحد —"
python3 -m unittest discover -s tests
echo "— آزمون ساخت رابط گرافیکی دسکتاپ (نیازمند Xvfb روی لینوکس) —"
if command -v xvfb-run >/dev/null 2>&1; then
  xvfb-run -a python3 station.py --smoke | tail -4
else
  python3 station.py --smoke | tail -4
fi
echo "— پس‌آزمایی روی دادهٔ نمونه —"
python3 backtest.py demo/history-demo.csv --out data/backtest.html --csv data/backtest.csv | tail -4
echo "همه سبز."
