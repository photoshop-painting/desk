#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""نگهبان «تمرکز روی کارفرما»: صفحهٔ کارفرما فقط جریانِ واجب را جلو می‌دهد و
«خرید و فروش اوراق مشتقه» سرلوحهٔ بولد است؛ گام‌های اثباتی (۷ تا ۱) می‌مانند
ولی به‌عنوان اختیاری مشخص‌اند."""
from __future__ import annotations

import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

INDEX = (BASE / "web" / "index.html").read_text(encoding="utf-8")
APP = (BASE / "web" / "app.js").read_text(encoding="utf-8")
GUIDE = (BASE / "web" / "guide.html").read_text(encoding="utf-8")

import unittest


class ClientFocusTests(unittest.TestCase):
    def test_hero_states_buy_sell_as_the_purpose(self):
        """بندِ نخستِ صفحه «خرید و فروش اوراق مشتقه» را سرلوحهٔ بولد می‌کند.»"""
        self.assertIn("hero-card", INDEX)
        m = re.search(r'<div class="card" id="hero-card".*?</div>\s*</div>', INDEX, re.S)
        self.assertIsNotNone(m, "کارتِ سرلوحه پیدا نشد")
        hero = m.group(0)
        self.assertIn("خرید و فروش", hero)
        self.assertIn("اوراق مشتقه", hero)
        self.assertIn("تصمیم", hero)
        # دکمهٔ میان‌بر به تصمیم
        self.assertIn("showStep(5)", hero)

    def test_header_meta_leads_with_buy_sell(self):
        """متنِ سرتیتر، «خرید و فروش اوراق مشتقه» را بولد و در اول می‌گذارد.»"""
        m = re.search(r'<div class="meta">(.*?)</div>', INDEX, re.S)
        self.assertIsNotNone(m)
        meta = m.group(1)
        self.assertIn("<b>خرید و فروش اوراق مشتقه</b>", meta)
        self.assertIn("تصمیمِ خرید و فروش", meta)

    def test_guest_keeps_the_no_auto_order_statement(self):
        """بیانیهٔ «سفارش را خودتان» (که آزمون‌های تعاملی هم می‌سنجند) دست‌نخورده می‌ماند.»"""
        sec = re.search(r'<section id="s-health">.*?(?=<section id="s-data")', INDEX, re.S)
        self.assertIsNotNone(sec)
        self.assertIn("سفارش را خودتان", sec.group(0))

    def test_decide_step_is_bold_buy_sell(self):
        """گامِ تصمیم با عنوانِ بولدِ «تصمیمِ خرید و فروش» دیده می‌شود.»"""
        sec = re.search(r'<section id="s-decide">.*?</section>', INDEX, re.S)
        self.assertIsNotNone(sec)
        self.assertIn("تصمیمِ خرید و فروش", sec.group(0))
        self.assertIn("سیگنال‌های اوراق مشتقه", sec.group(0))

    def test_proof_steps_are_marked_optional(self):
        """گام‌های ۷ تا ۱۱ برچسبِ «اختیاری/اثبات» می‌گیرند ولی حذف نمی‌شوند.»"""
        for sec_id in ("s-backtest", "s-bundle", "s-trial", "s-blind", "s-math"):
            sec = re.search(rf'<section id="{sec_id}">.*?</section>', INDEX, re.S)
            self.assertIsNotNone(sec, sec_id)
            self.assertIn("اختیاری", sec.group(0), sec_id)
        # و هنوز ۱۱ بخش کامل در HTML هست (آزمون‌های تعاملی به ۱۱ تکیه دارند)
        self.assertEqual(INDEX.count("<section id=\"s-"), 11)

    def test_nav_stays_eleven_and_adds_proof_group(self):
        """فهرست هنوز ۱۱ گام دارد (ترتیب و برچسب‌ها دست‌نخورده) + گروهِ «اثبات»."""
        steps = re.search(r"const STEPS = \[(.*?)\];", APP, re.S)
        self.assertIsNotNone(steps)
        labels = re.findall(r'\["([a-z]+)",\s*"([^"]+)"\]', steps.group(1))
        self.assertEqual(len(labels), 11)
        self.assertEqual(labels[6][0], "backtest")
        self.assertEqual(labels[8][0], "trial")
        self.assertIn("دفتر سرمایه‌گذار", labels[8][1])
        self.assertIn("آزمون کور", labels[9][1])
        self.assertIn("راهبردها و ریاضی", labels[10][1])
        # جداکنندهٔ گروهِ اثبات در کدِ ناوبری
        self.assertIn("اثباتِ برنامه (اختیاری)", APP)

    def test_guide_opens_with_buy_sell_purpose(self):
        """راهنمای کارفرما با بندِ «کارِ اصلی: خرید و فروش اوراق مشتقه» شروع می‌شود.»"""
        self.assertIn("کارِ اصلی: خرید و فروشِ اوراق مشتقه", GUIDE)
        self.assertIn("اثباتِ برنامه به سرمایه‌گر", GUIDE)
        # و تعهدِ قدیمی دست‌نخورده است
        self.assertIn("سفارش نمی‌فرستد", GUIDE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
