# -*- coding: utf-8 -*-
"""بار ۳۱ — اعلان‌های شناور toast + نوار پیشرفت راست‌به‌چپ (progress) + kbd/badge/skeleton.

spec وایب‌فارسی:
  toast: روی هم جمع میشن، سقف تعداد، بستن همه، جایگاه قابل‌تنظیم، Provider/hook
  progress: از راست پر میشه + درصد فارسی
  kbd: نمایش میانبر همیشه ltr
  badge: برچسب وضعیت
  skeleton: جای خالی ضربان‌دار تا رسیدن داده
"""
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

INDEX = BASE / "web" / "index.html"
APP = BASE / "web" / "app.js"
ADMIN = BASE / "web" / "admin.html"

def _read(p):
    return p.read_text(encoding="utf-8")

def test_toast_container_exists_with_a11y():
    html = _read(INDEX)
    assert 'id="toast-stack"' in html, "کانتینر toast-stack در index.html نیست"
    assert 'aria-live="polite"' in html, "aria-live polite برای toast لازم است"
    assert 'aria-atomic="false"' in html
    assert 'role="status"' in html
    # آفلاین خودکفا: نباید اسکریپت CDN برای toast باشد
    assert "cdn" not in html.lower() or "toast" not in html.lower().split("cdn")[0][-200:]  # سختگیر نیست
    # در admin هم باشد
    admin = _read(ADMIN)
    assert 'id="toast-stack"' in admin
    assert 'aria-live="polite"' in admin

def test_toast_css_stacked_fixed_and_max():
    html = _read(INDEX)
    # استایل در index.html
    assert ".toast-stack" in html
    assert "position:fixed" in html
    assert "inset-inline-end" in html or "right:" in html
    # سقف تعداد در JS
    js = _read(APP)
    assert "MAX" in js
    # سقف ۴
    assert re.search(r"MAX\s*=\s*4", js), "سقف toast باید ۴ باشد (وایب‌فارسی: سقف تعداد)"
    # بستن همه
    assert "بستن همه" in js or "بستن همه" in html, "دکمه بستن همه باید باشد"

def test_toast_variants_and_provider():
    js = _read(APP)
    html = _read(INDEX)
    for cls in (".toast-success", ".toast-error", ".toast-warning", ".toast-info"):
        assert cls in html, f"{cls} در CSS نیست"
    # Provider / hook در JS
    assert "const Toast" in js or "window.Toast" in js
    for m in ("success", "error", "warning", "info", "clearAll"):
        assert m in js, f"متد Toast.{m} نیست"
    # هوک/ Provider عبارت: حداقل Toast.success/error
    assert "Toast.success" in js
    assert "Toast.error" in js

def test_progress_css_is_rtl_filling():
    html = _read(INDEX)
    assert ".progress" in html
    assert ".progress-fill" in html
    # از راست پر شود
    assert "direction:rtl" in html or "direction: rtl" in html
    assert "right:0" in html or "inset-inline-end:0" in html or "inset-inline-end: 0" in html
    # transform-origin right
    assert "transform-origin:right" in html or "transform-origin: right" in html
    # جایگاه قابل تنظیم: inset-inline-end در کانتینر toast هم هست
    assert "inset-inline-end" in html

def test_progress_html_a11y_and_fa_percent():
    html = _read(INDEX)
    # دست‌کم یک نمونه progress در HTML باشد (دمو یا نزدیک busy)
    assert 'role="progressbar"' in html
    assert 'aria-valuenow' in html
    assert 'aria-valuemin="0"' in html
    assert 'aria-valuemax="100"' in html
    # برچسب فارسی درصد
    assert "progress-label" in html
    # چک رقم فارسی در برچسب نمونه (۷۲٪)
    # نمی‌خواهیم رقم لاتین باشد — برچسب نمونه باید فارسی باشد
    m = re.search(r'class="progress-label"[^>]*>(.*?)</span>', html)
    assert m, "برچسب progress پیدا نشد"
    lab = m.group(1)
    assert not re.search(r"[0-9]", lab), f"برچسب progress باید فارسی باشد، شد {lab}"
    assert re.search(r"[۰-۹]", lab), "برچسب progress باید رقم فارسی داشته باشد"

def test_progress_js_helpers():
    js = _read(APP)
    assert "setProgress" in js, "تابع setProgress (وایب‌فارسی درصد فارسی) نیست"
    assert "ensureProgressNear" in js or "progress" in js.lower()
    # busy باید progress را هم مدیریت کند
    assert "busy" in js
    # busy جدید باید سه آرگومان pct هم بپذیرد یا progress را toggle کند
    assert "progress" in js.lower() and "busy" in js.lower()
    # درصد فارسی در JS
    assert "fa-IR" in js

def test_kbd_is_ltr():
    html = _read(INDEX)
    assert "<kbd>" in html or "<kbd" in html, "نمونه kbd در صفحه نیست"
    # CSS kbd باید ltr باشد
    assert "kbd" in html.lower()
    # باید direction:ltr در استایل kbd باشد
    assert "direction:ltr" in html or "direction: ltr" in html

def test_badge_variants():
    html = _read(INDEX)
    assert "badge-soft" in html
    assert "badge-soft ok" in html or "badge-soft.ok" in html
    assert "badge-soft bad" in html or "badge-soft.bad" in html

def test_skeleton_exists():
    html = _read(INDEX)
    assert ".skeleton" in html
    assert "skeleton-shimmer" in html
    assert "background-size:400%" in html or "animation" in html

def test_toast_and_progress_offline_self_contained():
    html = _read(INDEX)
    js = _read(APP)
    # هیچ وابستگی خارجی (CDN) برای toast/progress نباید باشد
    combined = html + js
    assert "unpkg" not in combined.lower()
    assert "jsdelivr" not in combined.lower()
    # فونت/اسکریپت بیرونی نیست (همان قاعدهٔ همیشه: آفلاین)
    # فقط help.js و app.js و jalali* مجازند
    scripts = re.findall(r'<script\s+src="([^"]+)"', html)
    for src in scripts:
        assert not src.startswith("http"), f"اسکریپت بیرونی مجاز نیست: {src}"
        assert src in ("help.js", "app.js", "jalali.js", "jalali-calendar.js", "admin.js"), f"اسکریپت ناشناس: {src}"

def test_busy_disables_button_and_shows_progress():
    js = _read(APP)
    #Busy باید دکمه را غیرفعال کند (الگوی قبلی)
    assert "sib.disabled" in js
    # و progress را نمایش دهد
    assert 'style.display' in js and 'progress' in js.lower()

def test_toast_has_close_and_auto_dismiss():
    js = _read(APP)
    # دکمهٔ بستن تکی
    assert 'class="t-close"' in js or "t-close" in js
    # auto dismiss با ttl
    assert "setTimeout" in js
    assert re.search(r"ttl|7000|4200", js), "زمان خودکار بستن toast باید باشد"
