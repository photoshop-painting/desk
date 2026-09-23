"""آزمون تابلوی پیگیری مخاطبان — سه قاعدهٔ سند ۱۴ که باید در کد قفل باشند.

۱. پیگیری فقط سه بار (روز ۰، ۳، ۱۰): بار سوم رد می‌شود.
۲. دفتر محلی و کم‌داده است: هیچ شماره/عدد در یادداشت‌ها نمی‌ماند.
۳. «کار امروز» درست حساب می‌شود: پیام اول، پیگیری، قرار جلسه، ثبت نتیجه، بستن.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import prospects as pr  # noqa: E402


class TestProspects(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "p.json"
        self.tmp.write_text("[]", encoding="utf-8")

    def _add(self, name, **kw):
        return pr.add(name, path=self.tmp, **kw)

    def test_add_and_no_duplicate(self):
        self.assertTrue(self._add("الف", when="2026-09-01")["ok"])
        again = self._add("الف")
        self.assertFalse(again["ok"])
        self.assertIn("از قبل", again["detail"])
        self.assertEqual(1, len(pr.load(self.tmp)))

    def test_empty_name_is_refused(self):
        with self.assertRaises(ValueError):
            pr.add("   ", path=self.tmp)

    def test_first_message_is_the_first_todo(self):
        self._add("الف", when="2026-09-18")
        items = pr.todo(path=self.tmp, on="2026-09-18")
        self.assertEqual("پیام اول را بفرست", items[0]["action"])
        self.assertFalse(items[0]["urgent"])

    def test_followup_days_three_and_ten(self):
        self._add("الف", when="2026-09-01")
        pr.mark("الف", "sent", when="2026-09-01", path=self.tmp)
        self.assertEqual([], pr.todo(path=self.tmp, on="2026-09-02"))          # روز ۱: کاری نیست
        due = pr.todo(path=self.tmp, on="2026-09-04")                          # روز ۳
        self.assertEqual("پیگیری ۱ (روز ۳)", due[0]["action"])
        pr.mark("الف", "followup", when="2026-09-04", path=self.tmp)
        self.assertEqual([], pr.todo(path=self.tmp, on="2026-09-08"))          # بین ۳ و ۱۰
        due2 = pr.todo(path=self.tmp, on="2026-09-11")                         # روز ۱۰
        self.assertEqual("پیگیری ۲ (روز ۱۰)", due2[0]["action"])

    def test_third_followup_is_refused(self):
        self._add("الف", when="2026-09-01")
        pr.mark("الف", "sent", when="2026-09-01", path=self.tmp)
        pr.mark("الف", "followup", when="2026-09-04", path=self.tmp)
        pr.mark("الف", "followup", when="2026-09-11", path=self.tmp)
        third = pr.mark("الف", "followup", when="2026-09-15", path=self.tmp)
        self.assertFalse(third["ok"])
        self.assertIn("دو پیگیری", third["detail"])
        self.assertEqual(2, len(pr.load(self.tmp)[0]["followup"]))

    def test_reply_then_meeting_then_outcome(self):
        self._add("ج", when="2026-09-01")
        pr.mark("ج", "sent", when="2026-09-02", path=self.tmp)
        pr.mark("ج", "reply", when="2026-09-05", note="پرسید داده از کجاست", path=self.tmp)
        self.assertEqual("قرار جلسه را بگذار", pr.todo(path=self.tmp, on="2026-09-06")[0]["action"])
        pr.mark("ج", "meeting", when="2026-09-09", path=self.tmp)
        self.assertEqual([], pr.todo(path=self.tmp, on="2026-09-08"))          # پیش از جلسه
        self.assertEqual("نتیجهٔ جلسه را ثبت کن",
                         pr.todo(path=self.tmp, on="2026-09-10")[0]["action"])
        bad = pr.mark("ج", "outcome", when="2026-09-10", result="شاید", path=self.tmp)
        self.assertFalse(bad["ok"])
        self.assertTrue(pr.mark("ج", "outcome", when="2026-09-10", result="بله",
                                note="پیگیری هفته آینده", path=self.tmp)["ok"])
        self.assertEqual([], pr.todo(path=self.tmp, on="2026-09-15"))          # بسته شده

    def test_close_removes_from_todo(self):
        self._add("د", when="2026-09-01")
        self.assertTrue(pr.close("د", path=self.tmp)["ok"])
        self.assertEqual([], pr.todo(path=self.tmp, on="2026-09-20"))

    def test_week_numbers(self):
        self._add("الف", channel="phone")
        self._add("ب")
        pr.mark("الف", "sent", when="2026-09-15", path=self.tmp)
        pr.mark("ب", "sent", when="2026-09-16", path=self.tmp)
        pr.mark("ب", "followup", when="2026-09-19", path=self.tmp)
        pr.mark("ب", "reply", when="2026-09-20", path=self.tmp)
        pr.mark("ب", "meeting", when="2026-09-21", path=self.tmp)
        wk = pr.week_numbers(path=self.tmp, on="2026-09-21")
        self.assertEqual(2, wk["messages"])
        self.assertEqual(1, wk["calls"])
        self.assertEqual(1, wk["followups"])
        self.assertEqual(1, wk["replies"])
        self.assertEqual(1, wk["meetings"])
        self.assertEqual(5, wk["targets"]["messages"])
        old = pr.week_numbers(path=self.tmp, on="2026-10-05")                   # هفتهٔ دیگر: صفر
        self.assertEqual(0, old["messages"])

    def test_notes_are_scrubbed_of_numbers(self):
        self._add("الف", note="شماره‌اش ۰۹۱۲۶۶۳۰۵۵۴ و مبلغ ۲٬۵۰۰٬۰۰۰ ریال")
        row = pr.load(self.tmp)[0]
        self.assertNotIn("۰۹۱۲۶۶۳۰۵۵۴", row["note"])
        self.assertNotIn("۲٬۵۰۰٬۰۰۰", row["note"])
        self.assertIn("‹عدد›", row["note"])

    def test_no_phone_field_is_stored(self):
        self._add("الف")
        row = pr.load(self.tmp)[0]
        for banned in ("phone", "mobile", "tel", "شماره", "account", "iban", "sheba"):
            self.assertNotIn(banned, row)

    def test_sheet_is_printable_and_selfcontained(self):
        self._add("الف", kind="brokerage", when="2026-09-01")
        pr.mark("الف", "sent", when="2026-09-02", path=self.tmp)
        d = self.tmp.parent
        hp, mp = pr.build_sheet(path=self.tmp, md_path=d / "b.md", html_path=d / "b.html",
                                on="2026-09-06")
        html = hp.read_text(encoding="utf-8")
        md = mp.read_text(encoding="utf-8")
        self.assertNotIn("<script", html)
        self.assertNotIn("<link", html)
        self.assertIn("مهندس مسعود مجربیان", html)
        self.assertIn("سه عدد این هفته", md)
        self.assertIn("پیگیری ۱ (روز ۳)", md)
        self.assertIn("روز ۰ (پیام اول)، روز ۳، روز ۱۰", md)


    def test_later_gets_a_return_date(self):
        """«بعداً» بی‌تاریخ یعنی فراموشی؛ پیش‌فرض سی روز بعد است."""
        self._add("ه", when="2026-09-01")
        pr.mark("ه", "meeting", when="2026-09-10", path=self.tmp)
        out = pr.mark("ه", "outcome", when="2026-09-10", result="بعداً",
                      note="گفتند بعد از بودجه‌بندی", path=self.tmp)
        self.assertTrue(out["ok"])
        row = pr.load(self.tmp)[0]
        self.assertEqual("2026-10-10", row["next_on"])            # ده مهر + ۳۰ روز
        custom = pr.mark("ه", "outcome", when="2026-09-12", result="بعداً",
                         next_on="2026-09-20", path=self.tmp)
        self.assertTrue(custom["ok"])
        self.assertEqual("2026-09-20", pr.load(self.tmp)[0]["next_on"])

    def test_later_row_comes_back_on_its_day(self):
        self._add("ه", when="2026-09-01")
        pr.mark("ه", "meeting", when="2026-09-10", path=self.tmp)
        pr.mark("ه", "outcome", when="2026-09-10", result="بعداً", next_on="2026-10-10",
                path=self.tmp)
        self.assertEqual([], pr.todo(path=self.tmp, on="2026-10-09"))          # پیش از موعد
        due = pr.todo(path=self.tmp, on="2026-10-10")
        self.assertEqual("روز موعود رسید — یک پیام صادقانه بفرست", due[0]["action"])
        self.assertFalse(due[0]["urgent"])
        late = pr.todo(path=self.tmp, on="2026-10-20")                         # ده روز دیرتر
        self.assertTrue(late[0]["urgent"])
        d = self.tmp.parent
        _, mp = pr.build_sheet(path=self.tmp, md_path=d / "l.md", html_path=d / "l.html",
                               on="2026-10-11")
        self.assertIn("سر زدن ۲۰۲۶-۱۰-۱۰", mp.read_text(encoding="utf-8"))

    def test_yes_and_no_do_not_come_back(self):
        for name, result in (("و", "بله"), ("ز", "نه")):
            self._add(name, when="2026-09-01")
            pr.mark(name, "meeting", when="2026-09-05", path=self.tmp)
            pr.mark(name, "outcome", when="2026-09-05", result=result, path=self.tmp)
        self.assertEqual([], pr.todo(path=self.tmp, on="2026-10-20"))
        self.assertNotIn("next_on", pr.load(self.tmp)[0])


class TestCli(unittest.TestCase):
    def _run(self, *args, env_path):
        import os
        import subprocess
        env = dict(os.environ, IRAN_DESK_PROSPECTS=str(env_path))
        return subprocess.run([sys.executable, str(BASE / "prospects.py"), *args],
                              capture_output=True, text=True, timeout=120, env=env)

    def test_cli_flow(self):
        p = Path(tempfile.mkdtemp()) / "cli.json"
        r = self._run("--add", "کارگزاری الف", "--kind", "brokerage", env_path=p)
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("ثبت شد", r.stdout)
        self.assertIn("✅", r.stdout)
        r2 = self._run("--sent", "کارگزاری الف", "--date", "2026-09-01", env_path=p)
        self.assertEqual(0, r2.returncode)
        r3 = self._run("--week", env_path=p)
        self.assertIn("هدف", r3.stdout)
        r4 = self._run("--json", env_path=p)
        data = json.loads(r4.stdout)
        self.assertEqual(1, len(data["prospects"]))
        r5 = self._run("--todo", env_path=p)
        self.assertIn("کارگزاری الف", r5.stdout)

    def test_cli_later_with_date(self):
        p = Path(tempfile.mkdtemp()) / "cli3.json"
        self._run("--add", "مخاطب بعدی", env_path=p)
        self._run("--meeting", "مخاطب بعدی", "--date", "2026-09-10", env_path=p)
        r = self._run("--outcome", "مخاطب بعدی", "--result", "بعداً",
                      "--next-on", "2026-09-01", "--date", "2026-08-20", env_path=p)
        self.assertEqual(0, r.returncode, r.stderr)
        data = json.loads(self._run("--json", env_path=p).stdout)
        self.assertEqual("2026-09-01", data["prospects"][0]["next_on"])
        todo = self._run("--todo", env_path=p)
        self.assertIn("روز موعود", todo.stdout)                  # موعدش (۲۰ شهریور) گذشته است

    def test_cli_unknown_name_fails(self):
        p = Path(tempfile.mkdtemp()) / "cli2.json"
        p.write_text("[]", encoding="utf-8")
        r = self._run("--sent", "ناشناس", env_path=p)
        self.assertEqual(1, r.returncode)
        self.assertIn("در تابلو نیست", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
