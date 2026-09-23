"""آزمون «مراسم بیست‌دقیقه‌ای فروش» — برگهٔ اجراییِ هر روز.

قواعدی که نباید بشکنند: متن‌ها فقط از خودِ `outreach.messages` بیایند (به‌جز پیام «روز موعود» که
همین‌جا نوشته شده و همان قفل‌ها را دارد) · سقف پنج پیام در روز و بیست دقیقه بودجه · روز خالی،
پیام نمی‌سازد · هیچ عدد سود و هیچ فوریت ساختگی در هیچ متنی نیست · برگه خودبسنده و چاپی است.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import outreach as out  # noqa: E402
import prospects as pr  # noqa: E402
import sales_ritual as sr  # noqa: E402

BANNED = ("سود تضمین", "تضمین بازده", "درصد سود", "بازدهی ٪", "تخفیف", "فرصت محدود",
          "فقط امروز", "فوری اقدام", "پولدار", "ثروتمند")


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "p.json"
        self.tmp.write_text("[]", encoding="utf-8")

    def _add(self, name, **kw):
        kw.setdefault("when", "2026-09-01")
        return pr.add(name, path=self.tmp, **kw)

    def _plan(self, on="2026-09-22", sender="مسعود"):
        return sr.plan(path=self.tmp, on=on, sender=sender)

    def test_empty_board_sends_nothing(self):
        plan = self._plan()
        self.assertEqual([], plan["items"])
        self.assertEqual(0, plan["used_minutes"])
        self.assertEqual(0, plan["counts"]["messages"])
        self.assertIn("پنج نام", plan["note"])

    def test_first_message_text_comes_from_outreach(self):
        self._add("کارگزاری الف", kind="brokerage")
        plan = self._plan()
        card = plan["items"][0]
        self.assertEqual("message", card["kind"])
        self.assertEqual(out.messages("کارگزاری الف", kind="brokerage")["first_message"],
                         card["text"])

    def test_tone_follows_the_prospect_kind(self):
        self._add("آقای رضایی", kind="known")
        self._add("شرکت ب", kind="company")
        cards = {c["name"]: c for c in self._plan()["items"]}
        self.assertIn("سلام آقای رضایی", cards["آقای رضایی"]["text"])   # آدم: با نام
        self.assertIn("سلام، وقتتان بخیر.", cards["شرکت ب"]["text"])     # شرکت: سرد و رسمی
        self.assertNotIn("آقای رضایی", cards["شرکت ب"]["text"])

    def test_followups_use_the_followup_text(self):
        self._add("کارگزاری ب")
        pr.mark("کارگزاری ب", "sent", when="2026-09-15", path=self.tmp)
        first = self._plan(on="2026-09-19")["items"][0]                 # روز ۴: پیگیری ۱
        self.assertEqual(out.messages("کارگزاری ب")["followup_message"], first["text"])
        self.assertIn("روز ۳", first["note"])
        pr.mark("کارگزاری ب", "followup", when="2026-09-19", path=self.tmp)
        second = self._plan(on="2026-09-26")["items"][0]                # روز ۱۱: پیگیری ۲
        self.assertIn("آخرین پیگیری", second["note"])

    def test_reply_gets_the_confirm_message(self):
        self._add("شرکت ج")
        pr.mark("شرکت ج", "reply", when="2026-09-20", path=self.tmp)
        card = self._plan()["items"][0]
        self.assertEqual("message", card["kind"])
        self.assertEqual(out.messages("شرکت ج")["confirm_message"], card["text"])

    def test_meeting_result_is_desk_work_not_a_message(self):
        self._add("شرکت د")
        pr.mark("شرکت د", "meeting", when="2026-09-21", path=self.tmp)
        plan = self._plan()
        card = plan["items"][0]
        self.assertEqual("internal", card["kind"])
        self.assertIsNone(card["text"])
        self.assertEqual(len(sr.RESULT_QUESTIONS), len(card["checklist"]))
        self.assertEqual(0, plan["counts"]["messages"])
        self.assertEqual(1, plan["counts"]["internal"])

    def test_later_gets_one_gentle_message(self):
        self._add("شرکت ه")
        pr.mark("شرکت ه", "outcome", when="2026-09-01", result="بعداً", next_on="2026-09-20",
                path=self.tmp)
        card = self._plan()["items"][0]
        self.assertEqual(sr.LATER_MESSAGE, card["text"])
        self.assertIn("بی‌فشار", card["note"])

    def test_phone_channel_becomes_a_call(self):
        self._add("کارگزاری و", channel="phone")
        plan = self._plan()
        card = plan["items"][0]
        self.assertEqual("call", card["kind"])
        self.assertEqual(out.messages("کارگزاری و")["call_script"], card["text"])
        self.assertEqual(sr.COST["call"], card["minutes"])
        self.assertEqual(1, plan["counts"]["calls"])
        self.assertEqual(0, plan["counts"]["messages"])

    def test_five_messages_cap_and_budget(self):
        for i in range(8):
            self._add(f"مخاطب {i}", when="2026-09-15")
        plan = self._plan()
        self.assertLessEqual(plan["counts"]["messages"], sr.MAX_MESSAGES_PER_DAY)
        self.assertEqual(sr.MAX_MESSAGES_PER_DAY, plan["counts"]["messages"])
        self.assertLessEqual(plan["used_minutes"], sr.BUDGET_MIN)
        self.assertTrue(plan["deferred"])
        self.assertIn("سقف", plan["deferred"][0]["reason"])

    def test_budget_pushes_the_rest_to_tomorrow(self):
        for i in range(11):                                             # ۱۱ کار دفتری × ۲ دقیقه
            self._add(f"جلسه‌دار {i}", when="2026-09-01")
            pr.mark(f"جلسه‌دار {i}", "meeting", when="2026-09-20", path=self.tmp)
        plan = self._plan()
        self.assertLessEqual(plan["used_minutes"], sr.BUDGET_MIN)
        self.assertTrue(plan["deferred"])
        self.assertIn("بودجهٔ", plan["deferred"][0]["reason"])

    def test_hours_are_laid_out_in_order(self):
        for i in range(4):
            self._add(f"مخاطب {i}", when="2026-09-15")
        plan = self._plan()
        starts = [c["start_min"] for c in plan["items"]]
        self.assertEqual(sorted(starts), starts)                        # بدون پرش و بدون هم‌پوشانی
        self.assertEqual(0, starts[0])

    def test_no_promises_and_no_urgency_in_any_text(self):
        self._add("مخاطب ص")
        pr.mark("مخاطب ص", "sent", when="2026-09-15", path=self.tmp)
        texts = [sr.LATER_MESSAGE] + [c["text"] for c in self._plan()["items"] if c["text"]]
        for c in self._plan()["items"]:
            texts += list(c.get("checklist") or [])
        joined = " ".join(texts)
        for bad in BANNED:
            self.assertNotIn(bad, joined, f"عبارت ممنوع: {bad}")
        self.assertNotIn("٪", joined)
        self.assertNotIn("درصد", joined)
        for m in re.finditer("تضمین", joined):
            self.assertIn("هیچ", joined[max(0, m.start() - 20):m.start()])

    def test_sheet_is_printable_and_self_contained(self):
        self._add("شرکت م", kind="company")
        d = self.tmp.parent
        hp, mp = sr.build_sheet(path=self.tmp, on="2026-09-22",
                                md_path=d / "s.md", html_path=d / "s.html")
        html = hp.read_text(encoding="utf-8")
        md = mp.read_text(encoding="utf-8")
        self.assertNotIn("<script", html)
        self.assertNotIn("<link", html)
        self.assertIn("مهندس مسعود مجربیان", html)
        self.assertIn("فرستادم ☐", md)
        self.assertIn("سه عدد این هفته", md)
        self.assertIn("بیست‌دقیقه", md)
        self.assertIn(out.messages("شرکت م")["first_message"].split("\n")[0], md)


class TestCli(unittest.TestCase):
    def _run(self, *args, env_path):
        env = dict(os.environ, IRAN_DESK_PROSPECTS=str(env_path))
        return subprocess.run([sys.executable, str(BASE / "sales_ritual.py"), *args],
                              capture_output=True, text=True, timeout=120, env=env)

    def test_cli_json_and_sheet(self):
        p = Path(tempfile.mkdtemp()) / "cli.json"
        env = dict(os.environ, IRAN_DESK_PROSPECTS=str(p))
        subprocess.run([sys.executable, str(BASE / "prospects.py"), "--add", "شرکت ن",
                        "--date", "2026-09-15"], capture_output=True, text=True, timeout=120, env=env)
        r = self._run("--json", "--on", "2026-09-22", env_path=p)
        self.assertEqual(0, r.returncode, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(1, data["counts"]["messages"])
        self.assertEqual(3, data["used_minutes"])
        r2 = self._run("--sheet", "--on", "2026-09-22", env_path=p)
        self.assertEqual(0, r2.returncode, r2.stderr)
        self.assertIn("برگهٔ چاپی امروز", r2.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
