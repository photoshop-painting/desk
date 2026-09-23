"""آزمون برگهٔ «روز اول مشتری» — همان چیزی که بعد از «بله» دست طرف مقابل می‌افتد.

قواعدی که نباید بشکنند: هیچ وعدهٔ سود (کلمهٔ «تضمین» فقط در جملهٔ نفی‌شده) · تاریخ بازبینی از
خودِ `license.TRIAL_DAYS` بیاید · شرط‌های کارنامه از پیش‌فرض‌های `daily_trial.scorecard` بیاید
(عدد دست‌نویس ممنوع) · قیمت خودساخته نشود · عدد بسته از مانیفست خوانده شود · برگه خودبسنده باشد.
"""
from __future__ import annotations

import inspect
import json
import re
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import daily_trial as dailytrial  # noqa: E402
import license as licmod  # noqa: E402
import onboarding as onb  # noqa: E402


class TestOnboarding(unittest.TestCase):
    def _build(self, client="کارگزاری نمونه", **kw):
        d = Path(tempfile.mkdtemp())
        kw.setdefault("start", "2026-09-22")
        return onb.build_onboarding(client, html_path=d / "n.html", md_path=d / "n.md", **kw)

    def test_both_versions_are_built(self):
        hp, mp = self._build()
        self.assertTrue(hp.exists() and mp.exists())
        self.assertGreater(hp.stat().st_size, 2000)
        self.assertGreater(mp.stat().st_size, 1500)

    def test_client_name_and_honest_lines(self):
        _, mp = self._build(client="کارگزاری نمونه")
        md = mp.read_text(encoding="utf-8")
        self.assertIn("کارگزاری نمونه", md)
        self.assertIn("هیچ سود تضمینی", md)
        self.assertIn("هیچ سفارشی", md)
        self.assertIn("ابلاغیهٔ مهر ۱۳۹۹", md)
        self.assertIn("درصدی از سود گرفته نمی‌شود", md)

    def test_invented_claims_are_refused(self):
        """«تضمین» فقط جایی می‌آید که همان جمله نفی‌اش می‌کند."""
        _, mp = self._build()
        md = mp.read_text(encoding="utf-8")
        for m in re.finditer("تضمین", md):
            if md[max(0, m.start() - 6):m.start()].endswith("وجه "):
                continue                     # «وجه تضمین» اصطلاح بازار است، نه وعده
            window = md[max(0, m.start() - 20):m.start()]
            self.assertIn("هیچ", window, f"«تضمین» بدون نفی: …{md[max(0, m.start() - 40):m.start() + 20]}…")
        for bad in ("سود قطعی", "بازده تضمین", "درصد از سود می‌گیرم", "پولدار"):
            self.assertNotIn(bad, md)

    def test_review_date_comes_from_license_module(self):
        hp, mp = self._build(start="2026-09-22")
        want = (date(2026, 9, 22) + timedelta(days=licmod.TRIAL_DAYS)).isoformat()
        fa_want = onb.fa(want)
        md = mp.read_text(encoding="utf-8")
        html = hp.read_text(encoding="utf-8")
        self.assertIn(fa_want, md)
        self.assertIn(fa_want, html)
        self.assertIn(onb.fa(licmod.TRIAL_DAYS), md)

    def test_gate_numbers_come_from_daily_trial(self):
        """اگر کسی شرط‌های کارنامه را عوض کند، برگه باید همان را نشان بدهد."""
        p = inspect.signature(dailytrial.scorecard).parameters
        md = self._build()[1].read_text(encoding="utf-8")
        self.assertIn(onb.fa(int(p["target_days"].default)), md)
        self.assertIn(onb.fa(int(p["target_real_days"].default)), md)
        self.assertIn(onb.fa(int(round(float(p["min_marked_ratio"].default) * 100))), md)
        self.assertIn(onb.fa(int(p["min_moves"].default)), md)
        self.assertIn("زنجیرهٔ هش", md)

    def test_first_day_steps_have_the_license_command(self):
        _, mp = self._build(client="شرکت الف")
        md = mp.read_text(encoding="utf-8")
        self.assertIn('license.py --grant "شرکت الف" --trial --save', md)
        self.assertIn("license.py --document", md)
        self.assertIn("selftest.py", md)
        for s in onb.first_day_steps("شرکت الف"):
            self.assertIn(s["title"], md)

    def test_no_purchase_gate_is_written(self):
        _, mp = self._build()
        md = mp.read_text(encoding="utf-8")
        self.assertIn("هیچ دادهٔ خریدنی", md)
        self.assertIn("هیچ سرمایه‌ای", md)
        self.assertIn("هیچ پرداخت ماهانه‌ای", md)

    def test_ladder_and_payment_rule_come_from_license(self):
        _, mp = self._build()
        md = mp.read_text(encoding="utf-8")
        for row in licmod.ladder():
            self.assertIn(row["step"], md)
            self.assertIn(row["basis"], md)
        self.assertIn("پرداخت در برابر **شاهد**", md)

    def test_price_is_not_invented(self):
        _, mp = self._build()
        self.assertIn("توافقی", mp.read_text(encoding="utf-8"))
        _, mp2 = self._build(monthly_rial=40_000_000)
        self.assertIn("۴۰٬۰۰۰٬۰۰۰ ریال", mp2.read_text(encoding="utf-8"))

    def test_html_is_self_contained_and_printable(self):
        hp, _ = self._build()
        html = hp.read_text(encoding="utf-8")
        self.assertNotIn("<script", html)
        self.assertNotIn("<link", html)
        self.assertNotIn("localhost", html)
        self.assertIn('dir="rtl"', html)
        self.assertIn("مهندس مسعود مجربیان", html)
        self.assertIn("روز اول", html)

    def test_bad_date_is_refused_loudly(self):
        with self.assertRaises(ValueError):
            onb.build_onboarding("شرکت", start="۱۴۰۵/۰۷/۰۱")

    def test_kit_facts_are_read_not_guessed(self):
        facts = onb.kit_facts()
        if facts:                                   # اگر بستهٔ تحویل ساخته شده باشد
            md = self._build()[1].read_text(encoding="utf-8")
            self.assertIsInstance(facts.get("files"), int)
            self.assertGreater(facts["files"], 10)
            self.assertIn(onb.fa(facts["files"]), md)


class TestCli(unittest.TestCase):
    def test_cli_json(self):
        import subprocess
        r = subprocess.run([sys.executable, str(BASE / "onboarding.py"), "--client", "نمونهٔ نمایشی",
                            "--start", "2026-09-22", "--json"], capture_output=True, text=True, timeout=120)
        self.assertEqual(0, r.returncode, r.stderr)
        data = json.loads(r.stdout)
        self.assertIn("html", data)
        self.assertFalse(data["price_given"])
        self.assertEqual("2026-10-06", data["review"])
        self.assertEqual(len(onb.gate_conditions()), len(data["gates"]))

    def test_cli_bad_date_fails(self):
        import subprocess
        r = subprocess.run([sys.executable, str(BASE / "onboarding.py"), "--client", "شرکت",
                            "--start", "دیروز", "--json"], capture_output=True, text=True, timeout=120)
        self.assertEqual(2, r.returncode)
        self.assertIn("خطا", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
