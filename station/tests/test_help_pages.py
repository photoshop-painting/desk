#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""نگهبان «راهنمای درون‌صفحه»: هر صفحه یک کلیدِ «راهنما» دارد که آن صفحه و
همهٔ پارامترهایش را تشریح می‌کند (چه کار می‌کند / چه استفاده‌ای دارد).

قاعده‌ها:
  ۱. هر ۱۱ گامِ صفحهٔ اصلی + پنل مدیریت + صفحهٔ ورود + راهنما، توضیحِ کامل دارند.
  ۲. پارامترهای کلیدیِ هر صفحه در توضیح‌ها نام برده می‌شوند.
  ۳. صداقت: هیچ وعدهٔ تضمینی در متنِ راهنما نیست و «سفارش را خودتان» دست‌نخورده است.
  ۴. همهٔ صفحات، پروندهٔ help.js را می‌خوانند (خودکفا و آفلاین).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

WEB = BASE / "web"
HELP = (WEB / "help.js").read_text(encoding="utf-8")
INDEX = (WEB / "index.html").read_text(encoding="utf-8")
ADMIN = (WEB / "admin.html").read_text(encoding="utf-8")
LOGIN = (WEB / "login.html").read_text(encoding="utf-8")
GUIDE = (WEB / "guide.html").read_text(encoding="utf-8")

import unittest

KEYS = [
    "s-health", "s-data", "s-settings", "s-news", "s-run", "s-decide",
    "s-backtest", "s-bundle", "s-trial", "s-blind", "s-math",
    "admin", "login", "guide",
]

BANNED = (
    "سود تضمین", "ثروت تضمین", "تضمین سود", "تضمین ثروت", "100٪", "صددرصدی",
    "سود تضمینی", "درآمد تضمینی", "پول حلال تضمین",
)


def entry_for(key: str) -> str:
    """متنِ کاملِ توضیحِ یک صفحه را از help.js برمی‌آورد."""
    m = re.search(rf'"{re.escape(key)}"\s*:\s*\{{(.*?)\n  \}},\n\n', HELP, re.S)
    if m is None:
        # آخرین کلیدها بدون فاصلهٔ خالیِ بعدی
        m = re.search(rf'"{re.escape(key)}"\s*:\s*\{{(.*?)\n  \}}', HELP, re.S)
    self = None
    if m is None:
        raise AssertionError(f"کلیدِ {key} در help.js پیدا نشد")
    return m.group(1)


class HelpContentTests(unittest.TestCase):
    def test_all_pages_have_help(self):
        for key in KEYS:
            entry_for(key)  # اگر نباشد، AssertionError می‌دهد

    def test_every_entry_has_about_and_items(self):
        for key in KEYS:
            body = entry_for(key)
            self.assertIn("about:", body, key)
            self.assertIn("items:", body, key)
            names = re.findall(r'name:\s*"', body)
            self.assertGreaterEqual(len(names), 3, f"{key}: کمترین پارامتر")

    def test_every_item_explains_does_and_use(self):
        """هر پارامتر، هر دو سؤالی که کاربر پرسید را جواب می‌دهد: چکار می‌کند و چه استفاده‌ای دارد."""
        for key in KEYS:
            body = entry_for(key)
            self.assertEqual(body.count("does:"), body.count("name:"), key)
            self.assertEqual(body.count("use:"), body.count("name:"), key)

    def test_key_parameters_are_named_per_page(self):
        """پارامترهای کلیدیِ هر صفحه در توضیحش نام برده می‌شوند."""
        expect = {
            "s-health": ["برو به تصمیم", "پنل مدیریت"],
            "s-data": ["مسیر JSON", "وجه تضمین", "پروفایل", "کاوش پاسخ"],
            "s-settings": ["نرخ سد", "نقدشوندگی", "اسپرد", "سقف کل وجه تضمین"],
            "s-news": ["کدال", "هشدار"],
            "s-run": ["شروع محاسبه", "دروازه"],
            "s-decide": ["بستهٔ سفارش", "داوری", "کارمزد", "خودتان"],
            "s-backtest": ["realized_annualized_pct", "خطای پیش‌بینی"],
            "s-bundle": ["بستهٔ راستی‌آزمایی", "پیشنهاد", "پیگیری"],
            "s-trial": ["مراسم امروز", "زنجیره", "بازسنجی", "سرمایه‌گر"],
            "s-blind": ["پرسش", "حساب‌رسی", "پیمان‌نامه"],
            "s-math": ["شوک", "ورشکستگی", "راهبرد"],
            "admin": ["سلامت", "مجوز", "پشتیبان", "کاربران", "گواهی"],
            "login": ["شناسه", "رمز", "ورود"],
            "guide": ["روز اول", "شصت ثانیه", "پرسش‌های پرتکرار"],
        }
        for key, words in expect.items():
            body = entry_for(key)
            for w in words:
                self.assertIn(w, body, f"{key} باید «{w}» را نام ببرد")

    def test_honesty_no_guarantee_words(self):
        for w in BANNED:
            self.assertNotIn(w, HELP, f"وعدهٔ ممنوعه: {w}")

    def test_no_auto_order_stated_in_help(self):
        self.assertIn("هیچ سفارشی", entry_for("s-trial"))
        self.assertIn("خودتان در سامانهٔ کارگزاری", entry_for("s-decide"))


class HelpWiringTests(unittest.TestCase):
    def test_main_page_loads_help_before_app(self):
        self.assertIn('<script src="help.js"></script>', INDEX)
        self.assertIn('<script src="app.js"></script>', INDEX)
        self.assertLess(INDEX.find("help.js"), INDEX.find("app.js"))
        # ۱۱ بخش دست‌نخورده
        self.assertEqual(INDEX.count('<section id="s-'), 11)

    def test_admin_login_guide_load_help_and_have_button(self):
        for html, key in ((ADMIN, "admin"), (LOGIN, "login"), (GUIDE, "guide")):
            self.assertIn('<script src="help.js"></script>', html, key)
            self.assertIn(f"openHelp('{key}')", html, key)
            self.assertIn("راهنمای این صفحه", html, key)


if __name__ == "__main__":
    unittest.main(verbosity=2)
