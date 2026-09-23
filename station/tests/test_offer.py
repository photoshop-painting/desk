"""آزمون برگهٔ «پیشنهاد یک‌صفحه‌ای» — همان چیزی که دست شرکت داده می‌شود.

قواعدی که نباید بشکنند: هیچ وعدهٔ سود · هیچ سفارش خودکار · هیچ قیمتِ خودساخته (اگر عدد ندهیم،
«توافقی») · سه پلهٔ ارائه از خود `license.ladder` بیاید · هر دو نسخه (چاپی و متنی) ساخته شود ·
برگه خودبسنده باشد (بدون اسکریپت و بدون فایل بیرونی) تا آفلاین هم چاپ شود.
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import license as licmod  # noqa: E402
import offer as off  # noqa: E402


class TestOffer(unittest.TestCase):
    def _build(self, client="شرکت آزمون", **kw):
        d = Path(tempfile.mkdtemp())
        return off.build_offer(client, html_path=d / "o.html", md_path=d / "o.md", **kw)

    def test_both_versions_are_built(self):
        hp, mp = self._build()
        self.assertTrue(hp.exists() and mp.exists())
        self.assertGreater(hp.stat().st_size, 1500)
        self.assertGreater(mp.stat().st_size, 800)

    def test_client_name_and_honest_lines(self):
        _, mp = self._build(client="کارگزاری نمونه")
        md = mp.read_text(encoding="utf-8")
        self.assertIn("کارگزاری نمونه", md)
        self.assertIn("هیچ سود تضمینی", md)
        self.assertIn("هیچ سفارشی به کارگزاری فرستاده نمی‌شود", md)
        self.assertIn("درصد از سود نمی‌گیرم", md)
        self.assertIn("ابلاغیهٔ مهر ۱۳۹۹", md)
        self.assertNotIn("تضمین بازده", md)

    def test_ladder_comes_from_license_module(self):
        _, mp = self._build()
        md = mp.read_text(encoding="utf-8")
        for row in licmod.ladder():
            self.assertIn(row["step"], md)
            self.assertIn(row["basis"], md)

    def test_price_is_not_invented(self):
        _, mp = self._build()
        self.assertIn("توافقی", mp.read_text(encoding="utf-8"))
        _, mp2 = self._build(monthly_rial=40_000_000)
        self.assertIn("۴۰٬۰۰۰٬۰۰۰ ریال", mp2.read_text(encoding="utf-8"))

    def test_verification_commands_are_written(self):
        _, mp = self._build()
        md = mp.read_text(encoding="utf-8")
        self.assertIn("unittest discover -s tests", md)
        self.assertIn("selftest.py", md)

    def test_html_is_self_contained_and_printable(self):
        hp, _ = self._build()
        html = hp.read_text(encoding="utf-8")
        self.assertNotIn("<script", html)
        self.assertNotIn("<link", html)                 # بدون CSS بیرونی
        self.assertNotIn("localhost", html)
        self.assertIn("dir=\"rtl\"", html)
        self.assertIn("مهندس مسعود مجربیان", html)      # امضای دولوپر
        self.assertIn("پیشنهاد", html)

    def test_persian_digits_are_used_for_numbers(self):
        _, mp = self._build(monthly_rial=1_500_000)
        md = mp.read_text(encoding="utf-8")
        self.assertRegex(md, r"[۰-۹]")
        self.assertTrue(re.search(r"۱٬۵۰۰٬۰۰۰", md))

    def test_kit_facts_are_read_not_guessed(self):
        facts = off._kit_facts()
        if facts:                                       # اگر بستهٔ تحویل ساخته شده باشد
            self.assertIsInstance(facts.get("files"), int)
            self.assertGreater(facts["files"], 10)


    def test_docs_count_is_read_not_written(self):
        """شمار سندهای تحلیلی از خودِ پوشهٔ بسته خوانده می‌شود، نه دست‌نویس."""
        facts = off._kit_facts()
        if not facts.get("docs"):
            self.skipTest("بستهٔ تحویل ساخته نشده است؛ عددی هم برای سنجیدن نیست.")
        md = self._build()[1].read_text(encoding="utf-8")
        self.assertIn(off.fa(facts["docs"]), md)
        self.assertNotIn("سیزده سند تحلیلی", md)          # عدد کهنه نماند


class TestCli(unittest.TestCase):
    def test_cli_json(self):
        import json
        import subprocess
        r = subprocess.run([sys.executable, str(BASE / "offer.py"), "--client", "نمونهٔ نمایشی",
                            "--json"], capture_output=True, text=True, timeout=120)
        self.assertEqual(0, r.returncode, r.stderr)
        data = json.loads(r.stdout)
        self.assertIn("html", data)
        self.assertFalse(data["price_given"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
