"""آزمون برگهٔ «جلسهٔ بازبینی دو هفته‌ای» — همان جایی که آزمون تمام می‌شود و باید تصمیم گرفته شود.

قواعدی که نباید بشکنند: هیچ وعدهٔ سود و هیچ «تضمین» بی‌مرز · هیچ فوریت ساختگی · پنج شرط کارنامه
از خودِ `daily_trial.scorecard` بیاید (نه دست‌نویس) · سه پله از `license.ladder` · قیمت خودساخته
نداشته باشد («توافقی» اگر عددی داده نشود) · روز بازبینی = شروع + `license.TRIAL_DAYS` · هر شاهد
بگوید چه چیزی را نشان نمی‌دهد · برگه خودبسنده باشد (بدون اسکریپت و بدون فایل بیرونی) · تاریخ خراب
= خطای روشن، نه سکوت.
"""
from __future__ import annotations

import inspect
import json
import re
import subprocess
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
import review_meeting as rm  # noqa: E402
from offer import fa, price_line  # noqa: E402

BANNED = ("فرصت محدود", "فقط امروز", "فوری اقدام", "تخفیف", "از دست ندهید", "پولدار",
          "تضمین بازده", "سود قطعی", "بازده تضمینی", "ثروتمند")


class TestReviewMeeting(unittest.TestCase):
    def _build(self, client="شرکت آزمون", **kw):
        d = Path(tempfile.mkdtemp())
        return rm.build_review(client, html_path=d / "r.html", md_path=d / "r.md", **kw)

    def test_both_versions_are_built(self):
        hp, mp = self._build()
        self.assertTrue(hp.exists() and mp.exists())
        self.assertGreater(hp.stat().st_size, 2000)
        self.assertGreater(mp.stat().st_size, 1500)

    def test_client_name_and_review_date_from_code(self):
        _, mp = self._build(client="کارگزاری نمونه", start="2026-09-22")
        md = mp.read_text(encoding="utf-8")
        self.assertIn("کارگزاری نمونه", md)
        review = (date.fromisoformat("2026-09-22") + timedelta(days=rm.trial_days())).isoformat()
        self.assertIn(fa(review), md)
        self.assertIn(fa(rm.trial_days()), md)
        self.assertEqual(rm.trial_days(), int(licmod.TRIAL_DAYS))

    def test_days_left_has_three_states(self):
        self.assertEqual(3, rm.days_left("2026-09-22", "2026-10-03"))
        self.assertEqual(0, rm.days_left("2026-09-22", "2026-10-06"))
        self.assertEqual(-5, rm.days_left("2026-09-22", "2026-10-11"))
        _, mp = self._build(start="2026-09-22", on="2026-10-03")
        self.assertIn("روز تا روز بازبینی مانده", mp.read_text(encoding="utf-8"))
        _, mp2 = self._build(start="2026-09-22", on="2026-10-06")
        self.assertIn("امروز روز بازبینی است", mp2.read_text(encoding="utf-8"))
        _, mp3 = self._build(start="2026-09-22", on="2026-10-11")
        self.assertIn("از روز بازبینی گذشته است", mp3.read_text(encoding="utf-8"))

    def test_gate_numbers_are_read_from_code_not_written(self):
        """عددهای پنج شرط از پیش‌فرض‌های `daily_trial.scorecard` می‌آید؛ اگر کسی عوض کرد، برگه هم عوض شود."""
        p = inspect.signature(dailytrial.scorecard).parameters
        md = self._build(start="2026-09-22")[1].read_text(encoding="utf-8")
        self.assertIn(f"{fa(int(p['target_days'].default))} روز ثبت‌شده", md)
        self.assertIn(f"{fa(int(p['target_real_days'].default))} روز واقعی", md)
        self.assertIn(f"{fa(int(round(float(p['min_marked_ratio'].default) * 100)))}٪", md)
        self.assertIn(f"{fa(int(p['min_moves'].default))} حرکت معنادار", md)

    def test_gates_are_the_same_source_as_onboarding_sheet(self):
        self.assertEqual(onb.gate_conditions(), rm.gate_conditions())

    def test_ladder_and_price_are_not_invented(self):
        md = self._build()[1].read_text(encoding="utf-8")
        self.assertIn("توافقی", md)                                  # عددی نداده‌ایم
        for row in licmod.ladder():
            self.assertIn(row["step"], md)
        md2 = self._build(monthly_rial=40_000_000)[1].read_text(encoding="utf-8")
        self.assertIn(price_line(40_000_000, 0)["text"], md2)
        # «توافقی» به‌عنوان مفهوم جای خودش را دارد، ولی جملهٔ قیمتِ توافقی نباید بیاید:
        # وقتی عدد داده شده، عدد روی برگه می‌نشیند.
        self.assertNotIn(price_line(0, 0)["text"], md2)

    def test_no_claim_is_left_without_its_border(self):
        """«تضمین» و «درصد» فقط در جملهٔ نفی یا در شرط کارنامه مجاز است، نه به‌عنوان وعده."""
        md = self._build(start="2026-09-22")[1].read_text(encoding="utf-8")
        for word in ("تضمین", "درصد"):
            for m in re.finditer(word, md):
                ctx = md[max(0, m.start() - 34):m.start() + len(word) + 6]
                ok = ("هیچ" in ctx) or ("بازسنجی" in ctx) or ("۶۰٪" in ctx) or ("ادعا" in ctx)
                self.assertTrue(ok, f"«{word}» بی‌مرز مانده: …{ctx}…")
        for bad in BANNED:
            self.assertNotIn(bad, md)

    def test_every_witness_says_what_it_does_not_show(self):
        md = self._build()[1].read_text(encoding="utf-8")
        for w in rm.witness_rows():
            self.assertIn(w["name"], md)
            self.assertIn(f"نشان نمی‌دهد: {w['not_shows']}", md)
            if w.get("cmd"):
                self.assertIn(w["cmd"], md)

    def test_two_outcomes_and_the_payment_rule(self):
        md = self._build(monthly_rial=40_000_000)[1].read_text(encoding="utf-8")
        self.assertIn("خروجی یک — ادامه با پرداخت", md)
        self.assertIn("خروجی دو — توقف، بی‌گلایه‌مندی", md)
        self.assertIn("پرداخت در برابر", md)
        self.assertIn("هیچ درصدی از سود", md)
        self.assertIn("اجازه‌نامه در همان تاریخ", md)

    def test_follow_up_is_dated_and_short(self):
        after = rm.follow_up(on="2026-10-06")
        self.assertEqual("2026-11-05", after["next_on"])            # پیش‌فرض: +۳۰ روز
        self.assertEqual("2026-11-01", rm.follow_up(on="2026-10-06", follow_on="2026-11-01")["next_on"])
        self.assertEqual(2, len(after["messages"]))
        for msg in after["messages"]:
            self.assertLess(len(msg["text"]), 230)
            self.assertNotIn("٪", msg["text"])
            self.assertNotIn("درصد", msg["text"])
            self.assertNotIn("سود", msg["text"])
        md = self._build(on="2026-10-06")[1].read_text(encoding="utf-8")
        self.assertIn("2026-11-05", md)
        self.assertIn("prospects.py --outcome", md)

    def test_renewal_is_free_and_ruled(self):
        md = self._build()[1].read_text(encoding="utf-8")
        self.assertIn("تمدید", md)
        self.assertIn("بی‌هزینه", md)

    def test_html_is_self_contained_and_printable(self):
        html = self._build()[0].read_text(encoding="utf-8")
        self.assertNotIn("<script", html)
        self.assertNotIn("<link", html)
        self.assertNotIn("localhost", html)
        self.assertIn('dir="rtl"', html)
        self.assertIn("مهندس مسعود مجربیان", html)

    def test_kit_facts_are_read_not_guessed(self):
        facts = rm.kit_facts()
        if not facts.get("files"):
            self.skipTest("بستهٔ تحویل ساخته نشده است؛ عددی هم برای سنجیدن نیست.")
        md = self._build()[1].read_text(encoding="utf-8")
        self.assertIn(facts["kit"], md)

    def test_bad_date_raises_clear_error(self):
        with self.assertRaises(ValueError) as ctx:
            self._build(start="۱۴۰۵/۰۷/۰۱")
        self.assertIn("YYYY-MM-DD", str(ctx.exception))


class TestCli(unittest.TestCase):
    def test_cli_json_and_bad_date(self):
        d = Path(tempfile.mkdtemp())
        r = subprocess.run([sys.executable, str(BASE / "review_meeting.py"),
                            "--client", "نمونهٔ نمایشی", "--start", "2026-09-22",
                            "--on", "2026-10-06", "--json",
                            "--html", str(d / "r.html"), "--md", str(d / "r.md")],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(0, r.returncode, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual("2026-10-06", data["review"])
        self.assertEqual(0, data["days_left"])
        self.assertFalse(data["price_given"])
        self.assertEqual(["continue", "stop"], data["outcomes"])
        self.assertTrue(d.joinpath("r.html").exists())

        bad = subprocess.run([sys.executable, str(BASE / "review_meeting.py"),
                              "--start", "۱۴۰۵/۰۷/۰۱",
                              "--html", str(d / "b.html"), "--md", str(d / "b.md")],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(2, bad.returncode)
        self.assertIn("YYYY-MM-DD", bad.stderr)
        self.assertFalse(d.joinpath("b.html").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
