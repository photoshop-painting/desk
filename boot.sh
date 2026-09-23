#!/usr/bin/env bash
# بالا آوردن ایستگاه روی میزبان ابری (Hugging Face Spaces یا Render).
#
# ترتیب کار: از محیط، شناسه و رمزها را می‌خواند → دروازه را روشن می‌کند → برنامه را اجرا می‌کند.
# اگر رمزی در محیط نبود، خودش رمز قوی می‌سازد و در گزارش چاپ می‌کند (برای آزمون سریع).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/station"        # برنامه، پوشهٔ «desk» و «kodal-alert» را همسایهٔ خودش می‌خواهد

# میزبان‌ها درگاه را خودشان می‌دهند: HF انتظار ۷۸۶۰ دارد، Render متغیر PORT می‌فرستد.
PORT="${PORT:-${STATION_PORT:-7860}}"
ADMIN_ID="${STATION_ADMIN_ID:-mafhoom}"
GUEST_ID="${STATION_GUEST_ID:-masoud}"
ADMIN_PASS="${STATION_ADMIN_PASS:-}"
GUEST_PASS="${STATION_GUEST_PASS:-}"

gen() { python3 -c "import secrets; print('Desk-' + secrets.token_hex(4))"; }

echo "── ایستگاه تصمیم مشتقه، نسخهٔ میزبان ابری ──"
echo "   درگاه: $PORT  ·  شناسهٔ مدیر: $ADMIN_ID  ·  شناسهٔ کارفرما: $GUEST_ID"

if [ -z "$ADMIN_PASS" ]; then
  ADMIN_PASS="$(gen)"
  echo "   ⚠️ STATION_ADMIN_PASS نبود؛ رمز مدیر ساخته شد: $ADMIN_PASS"
  echo "      این رمز را در Secrets بگذار (این پیام فقط برای خودت است، ولی در گزارش می‌ماند)."
fi
python3 adminauth.py --set-id "$ADMIN_ID" --set-pass "$ADMIN_PASS" >/dev/null

if [ -z "$GUEST_PASS" ]; then
  GUEST_PASS="$(gen)"
  echo "   ⚠️ STATION_GUEST_PASS نبود؛ رمز کارفرما ساخته شد: $GUEST_PASS"
fi
python3 gate.py --sync-admin >/dev/null
python3 gate.py --guest-id "$GUEST_ID" --guest-pass "$GUEST_PASS" >/dev/null
if [ "${STATION_GUEST_OFF:-0}" = "1" ]; then
  python3 gate.py --guest-off >/dev/null
  echo "   کارفرما فعلاً بسته است (STATION_GUEST_OFF=1)."
else
  python3 gate.py --guest-on >/dev/null
fi
python3 gate.py --on >/dev/null
echo "   دروازه روشن است: بدون شناسه و رمز، هیچ صفحه‌ای باز نمی‌شود."
python3 gate.py --status | sed 's/^/   /'

# روی میزبان ابری، اتصال پیش‌فرض باید «منبع واقعی رایگان» باشد (مثل نسخهٔ زندهٔ Hugging Face):
# اگر وضعیتِ برگردانده‌شدهٔ قدیمی «خوراک آزمایشی محلی» را برگردانده باشد — که در میزبان دیگر
# وجود ندارد و قیمت‌ها از کار می‌افتند — انتخاب را به منبع واقعی برمی‌گردانیم.
# برای منبع دلخواه، متغیر STATION_CONNECTION را در Environment بگذار (مثلاً tgju-usd).
python3 ensure_connection.py || echo "   (ensure_connection اجرا نشد؛ ادامه با همان انتخاب فعلی)"

echo "   آماده است. آدرس درگاه: 0.0.0.0:$PORT   (بدون ورود: 401)"
exec python3 -m web_server --port "$PORT" --host 0.0.0.0 --no-browser
