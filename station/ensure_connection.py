#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""اتصال پیش‌فرضِ میزبان ابری را روی «منبع واقعی رایگان» می‌گذارد.

چرا لازم است: بستهٔ میزبانِ ابری ممکن است با انتخاب «خوراک آزمایشی محلی» (mock-local) برسد —
آن خوراک فقط روی رایانهٔ سازنده، در درگاه ۸۷۸۸، وجود دارد. روی میزبانِ ابری چنین درگاهی نیست
و همهٔ قیمت‌ها «نیامد» می‌مانند. این پرونده پیش از روشن‌شدن سرور، انتخاب را به منبع واقعی و
رایگان برمی‌گرداند (پیش‌فرض: tgju-usd؛ با متغیر STATION_CONNECTION عوض می‌شود).

اگر پروفایلِ خواسته‌شده در فهرست نبود، دست نمی‌زند (صادقانه: نمی‌داند).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import connections as conn  # noqa: E402


def main() -> int:
    name = (os.environ.get("STATION_CONNECTION") or "tgju-usd").strip()
    try:
        store = conn.load_store()
    except Exception as e:  # هر خطایی: صادقانه و بدون شکستن بوت
        print(f"   (دفتر اتصالات خوانده نشد: {e} — انتخاب دست‌نخورده می‌ماند.)")
        return 0
    if conn.find_profile(store, name) is None:
        print(f"   اتصال «{name}» در فهرست نیست؛ دست نمی‌زنم.")
        return 0
    if store.get("selected") != name:
        conn.select_profile(store, name)
        conn.save_store(store)
        print(f"   اتصال پیش‌فرض روی «{name}» گذاشته شد (منبع واقعی).")
    else:
        print(f"   اتصال فعال: «{name}» (منبع واقعی).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
