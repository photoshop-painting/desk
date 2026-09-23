#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""نگهبان «لایهٔ مشترکِ UI» (web/help.js → uiStyle) و دیزاین‌سیستم (DESIGN.md).

منبعِ قواعد (همه در همین پروندهٔ تست ذکر شده‌اند):
  * مشخصهٔ حرکت: mathofdynamic/entrance-motion-skill
    (۱۰ms · cubic-bezier(.16,1,.3,1) · translate3d(0,20px,0) ← ۰ · فقط opacity/transform ·
     فاصلهٔ ۳۳ms · با prefers-reduced-motion خاموش).
  * اعدادِ هم‌تراز در جدول: اصلِ «tabular figures for money» از دیزاین‌سیستم‌های مالی
    (در مجموعهٔ VoltAgent/awesome-design-md، مثل design-md/stripe).
  * letter-spacingِ ممنوع روی فارسی: vibefarsi.ir (و هر دیزاین‌سیستمِ فارسی).
  * ساختارِ توکن‌ها: مفهوم DESIGN.md از Google Stitch / awesome-design-md.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

WEB = BASE / "web"
HELP = (WEB / "help.js").read_text(encoding="utf-8")
DESIGN = BASE / "DESIGN.md"


class TestDesignDoc(unittest.TestCase):
    def test_design_doc_exists_with_core_sections(self):
        self.assertTrue(DESIGN.is_file(), "DESIGN.md باید در ریشهٔ gui باشد")
        text = DESIGN.read_text(encoding="utf-8")
        for section in ("رنگ", "تایپوگرافی", "فاصله", "حرکت", "ممنوعیات", "امضا"):
            self.assertIn(section, text, f"بخشِ «{section}» در DESIGN.md نیست")

    def test_design_doc_states_fa_rules(self):
        text = DESIGN.read_text(encoding="utf-8")
        self.assertIn("letter-spacing", text, "قانونِ letter-spacingِ فارسی باید مکتوب باشد")
        self.assertIn("Vazirmatn", text, "استکِ فونتِ فارسی باید مکتوب باشد")
        self.assertIn("tabular-nums", text, "اعدادِ هم‌تراز باید مکتوب باشد")
        self.assertIn("jalali", text, "قاعدهٔ تاریخِ شمسی باید مکتوب باشد")

    def test_design_doc_credits_developer(self):
        text = DESIGN.read_text(encoding="utf-8")
        for part in ("مسعود مجربیان", "09126630554", "Mojarabian"):
            self.assertIn(part, text, "امضای تهیه‌کننده در DESIGN.md نیست")


class TestUiStyleInjection(unittest.TestCase):
    """help.js → uiStyle(): حرکتِ ورود، فوکوس و اعدادِ هم‌تراز روی همهٔ صفحات."""

    def test_uistyle_function_and_boot_call(self):
        self.assertIn("function uiStyle()", HELP)
        m = re.search(r"if \(typeof window !== \"undefined\".*?\}", HELP, re.S)
        self.assertTrue(m, "بخشِ بوتِ help.js پیدا نشد")
        self.assertIn("uiStyle()", m.group(0), "uiStyle باید در بوتِ help.js صدا زده شود")

    def test_motion_spec_exact(self):
        # مشخصهٔ entrance-motion: مدت، easing، جابجایی، فقط opacity/transform
        self.assertIn("@keyframes station-rise", HELP)
        self.assertIn("translate3d(0,20px,0)", HELP)
        self.assertIn("cubic-bezier(.16,1,.3,1)", HELP)
        self.assertIn("100ms", HELP)
        # فاصلهٔ پلک‌ها = 33ms (duration/3)
        self.assertIn("animation-delay:33ms", HELP)

    def test_motion_targets_cards_only(self):
        # جدول‌های داده حرکت نمی‌کنند: فقط .card و .kpi
        self.assertIn(".card,.kpi{animation:station-rise", HELP)
        self.assertNotIn(".row{animation", HELP)
        self.assertNotIn("tbody{animation", HELP)

    def test_reduced_motion_guard(self):
        self.assertIn("@media (prefers-reduced-motion: reduce)", HELP)
        seg = HELP.split("@media (prefers-reduced-motion: reduce)", 1)[1]
        self.assertIn("animation:none", seg[:400], "در حالتِ کاهشِ حرکت، انیمیشن باید خاموش شود")

    def test_focus_visible_ring(self):
        self.assertIn(":focus-visible{outline:2px solid #0b3d2e", HELP,
                      "حلقهٔ فوکوسِ کیبورد با رنگِ برند باید تعریف شود")

    def test_tabular_nums_for_data(self):
        self.assertIn("font-variant-numeric:tabular-nums", HELP,
                      "اعدادِ جدول‌ها باید هم‌تراز (tabular) باشند")

    def test_no_external_assets(self):
        # لایهٔ UI باید کاملاً آفلاین بماند
        for bad in ("@import url", "fonts.googleapis", "cdn.", "http://", "https://"):
            self.assertNotIn(bad, HELP.split("function uiStyle()")[1].split("/* خودکار")[0],
                             f"لایهٔ uiStyle نباید به منبعِ بیرونی اشاره کند: {bad}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
