"""آزمون بستهٔ پیام‌های معرفی — همان چیزی که بیرون از این پوشه خوانده می‌شود.

قواعد سخت: هیچ وعدهٔ سود · هیچ بازدهی و هیچ درصدی در متن پیام‌ها · هیچ فوریت ساختگی · خطاب
درست (شرکت: سرد و رسمی · آدم: با نام) · پاسخ چهار مخالفت وجود دارد · برگه خودبسنده است.
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import outreach as out  # noqa: E402

BANNED = ("سود تضمین", "تضمین بازده", "درصد سود", "بازدهی ٪", "تخفیف", "فرصت محدود",
          "فقط امروز", "فوری اقدام", "پولدار")


class TestMessages(unittest.TestCase):
    def _m(self, client="شرکت نمونه", kind="company"):
        return out.messages(client, kind=kind, sender="مسعود")

    def test_no_promises_and_no_numbers(self):
        m = self._m()
        joined = " ".join([m["first_message"], m["second_message"], m["confirm_message"],
                           m["followup_message"], m["call_script"]] +
                          [o["objection"] + " " + o["answer"] for o in m["objections"]])
        for bad in BANNED:
            self.assertNotIn(bad, joined, f"عبارت ممنوع در پیام‌ها: {bad}")
        self.assertNotIn("٪", joined)                       # هیچ درصدی در پیام‌ها نیست
        self.assertNotIn("درصد", joined)

    def test_first_message_asks_for_time_only(self):
        m = self._m()
        first = m["first_message"]
        self.assertIn("نیم‌ساعت", first)
        self.assertIn("داوری سیگنال", first)
        self.assertIn("می‌مانَد یا می‌افتد", first)
        self.assertLess(len(first), 700)                    # پیام اول کوتاه است
        self.assertTrue(first.rstrip().endswith("یا نه."))  # با دعوت تمام می‌شود، نه با ادعا

    def test_greeting_depends_on_addressee(self):
        self.assertIn("سلام، وقتتان بخیر.", self._m("شرکت نمونه", "brokerage")["first_message"])
        self.assertIn("سلام آقای رضایی", self._m("آقای رضایی", "known")["first_message"])

    def test_four_objections_with_honest_answers(self):
        m = self._m()
        self.assertEqual(4, len(m["objections"]))
        text = " ".join(o["answer"] for o in m["objections"])
        self.assertIn("هیچ سفارشی نمی‌فرستم", text)
        self.assertIn("دو روش", text)
        self.assertIn("هیچ سایتی نمی‌دهد", text)

    def test_rules_and_followup_limit(self):
        m = self._m()
        rules = " ".join(m["rules"])
        self.assertIn("سه بار", rules)
        self.assertIn("اسپم", rules)
        self.assertIn("هیچ عدد سودی", rules)

    def test_pack_files_and_selfcontained_html(self):
        d = Path(tempfile.mkdtemp())
        hp, mp = out.build_pack("کارگزاری نمونه", html_path=d / "p.html", md_path=d / "p.md")
        html = hp.read_text(encoding="utf-8")
        md = mp.read_text(encoding="utf-8")
        self.assertNotIn("<script", html)
        self.assertNotIn("<link", html)
        self.assertIn("dir=\"rtl\"", html)
        self.assertIn("مهندس مسعود مجربیان", html)
        self.assertIn("کارگزاری نمونه", md)
        for section in ("۱. پیام اول", "۲. پیام بعد از جواب", "۳. تأیید وقت", "۴. پیگیری",
                        "۵. اسکریپت تماس", "۶. چهار مخالفت", "۷. پنج قاعده", "۸. جاهایی"):
            self.assertIn(section, md)

    def test_checklist_has_reasons(self):
        rows = out.checklist()
        self.assertGreaterEqual(len(rows), 5)
        self.assertTrue(all(r["task"] and r["why"] for r in rows))


class TestCli(unittest.TestCase):
    def test_cli_json(self):
        import json
        import subprocess
        r = subprocess.run([sys.executable, str(BASE / "outreach.py"), "--client", "نمونهٔ نمایشی",
                            "--kind", "teacher", "--json"], capture_output=True, text=True, timeout=120)
        self.assertEqual(0, r.returncode, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual("teacher", data["kind"])
        self.assertTrue(Path(data["md"]).exists())

    def test_cli_checklist_runs(self):
        import subprocess
        r = subprocess.run([sys.executable, str(BASE / "outreach.py"), "--checklist"],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("چرا:", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
