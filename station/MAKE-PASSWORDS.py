"""اولین اجرا: اگر رمزها ساخته نشده‌اند، همین حالا ساخته می‌شوند و چاپ می‌شوند.

این پرونده بخشی از «کوله‌پشتی دمو» است (نه بستهٔ تحویلی). کارش فقط این است که کاربر تازه‌کار
بدون هیچ فرمانی، رمز مدیر و کارفرما داشته باشد. رمزها را در پروندهٔ زیر هم می‌نویسد:
`station/config/CREDENTIALS-FIRST-LOGIN.txt` (دسترسی ۶۰۰) تا گم نشوند.
"""
from __future__ import annotations

import json
import pathlib
import secrets
import sys

HERE = pathlib.Path(__file__).resolve().parent
STATION = HERE / "station"
sys.path.insert(0, str(STATION))

import adminauth                                    # noqa: E402
import gate                                         # noqa: E402

CRED = STATION / "config" / "CREDENTIALS-FIRST-LOGIN.txt"
ADMIN_ID, GUEST_ID = "mafhoom", "masoud"


def make(force: bool = False) -> int:
    cfg = STATION / "config" / "gate.json"
    if cfg.exists() and not force:
        st = gate.status()
        print("رمزها از قبل ساخته شده‌اند (چیزی عوض نشد).")
        acc = st.get("accounts", {})
        print("  دروازه: " + ("روشن" if st.get("enabled") else "خاموش"))
        print("  مدیر: " + (acc.get("admin", {}).get("id") or "—") +
              " · کارفرما: " + (acc.get("guest", {}).get("id") or "—") +
              (" (فعال)" if acc.get("guest", {}).get("enabled") else " (قطع)"))
        print("  اگر رمزها را گم کرده‌ای: این فایل را با --force اجرا کن (رمز تازه می‌سازد).")
        if CRED.exists():
            print(f"  پروندهٔ رمز: {CRED}")
        return 0

    admin_pass = "Desk-" + secrets.token_hex(4)
    guest_pass = "Desk-" + secrets.token_hex(4)

    adminauth.set_credentials(ADMIN_ID, admin_pass)
    gate.sync_admin_from_panel()
    gate.set_account("guest", GUEST_ID, guest_pass)
    gate.set_enabled_account("guest", True)
    gate.set_enabled(True)

    CRED.parent.mkdir(parents=True, exist_ok=True)
    CRED.write_text(
        f"""ایستگاه تصمیم مشتقه — رمزهای اولین ورود (ساختهٔ MAKE-PASSWORDS.py)
این پرونده را جایی نگه دار که فقط خودت ببینی. هر وقت خواستی رمز تازه بسازی:
    python MAKE-PASSWORDS.py --force

مدیر (پنل مدیریت): {ADMIN_ID}
رمز مدیر        : {admin_pass}
کارفرما (مهمان)  : {GUEST_ID}
رمز کارفرما     : {guest_pass}

قطع کارفرما همین حالا:  python station/gate.py --guest-off
روشن‌کردن دوباره       :  python station/gate.py --guest-on
""", encoding="utf-8")
    CRED.chmod(0o600)

    print("┌───────────────────────────────────────────────┐")
    print("│  رمزهای تازه ساخته شد — همین حالا یادداشت کن   │")
    print("└───────────────────────────────────────────────┘")
    print(f"  پنل مدیر  : {ADMIN_ID} / {admin_pass}")
    print(f"  کارفرما   : {GUEST_ID} / {guest_pass}")
    print(f"  (همین‌ها در این پرونده هم نوشته شد: {CRED})")
    print("  دروازه روشن است: بدون رمز، هیچ صفحه‌ای باز نمی‌شود.")
    return 0


if __name__ == "__main__":
    raise SystemExit(make(force="--force" in sys.argv))
