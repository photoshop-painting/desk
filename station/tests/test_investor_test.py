#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون‌های برگستره برای tools invest_test: پرسش‌ها، داوری حدس، دفتر زنجیره‌ای، برگهٔ چاپی، پلهٔ کارنامه.

همه آزمون‌ها محلی‌اند: هیچ درخواست شبکه‌ای زده نمی‌شود و هیچ پروندهٔ وضعیت واقعی
(gui/data/) دست‌کاری نمی‌شود؛ هر آزمون در پوشهٔ موقتی خودش کار می‌کند.
"""

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

BASE = pathlib.Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import investor_test as inv  # noqa: E402


class CasesShape(unittest.TestCase):
    """شکل پرسش‌ها و پنهان‌بودن جواب‌ها تا وقتی عمداً آشکار نشده‌اند."""

    def test_cases_without_answers_has_no_answer_key(self):
        cs = inv.cases(reveal=False)
        self.assertGreaterEqual(len(cs), 5)
        for c in cs:
            self.assertNotIn("answer", c, f"جواب پرسش {c['id']} نباید لو برود")
            self.assertIn("question", c)
            self.assertTrue(c["given"], "هر پرسش باید عددهای ورودی داشته باشد")

    def test_cases_with_answers_has_formula_and_second_method(self):
        cs = inv.cases(reveal=True)
        for c in cs:
            self.assertIn("answer", c)
            self.assertTrue(c.get("formula"), f"مسیر محاسبهٔ {c['id']} خالی است")
            self.assertIn("checks", c, "هر پرسش باید محاسبهٔ دستی دوم داشته باشد")
            self.assertIn("ladder", c)

    def test_case_ids_are_unique(self):
        ids = [c["id"] for c in inv.cases(reveal=True)]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_case_has_ladder_of_three_points(self):
        for c in inv.cases(reveal=True):
            if c.get("answer_num") is None:
                continue
            self.assertEqual(len(c["ladder"]["ladder"]), 3, c["id"])
            self.assertTrue(c["ladder"]["verdict"])

    def test_engine_agrees_with_manual_check(self):
        """محاسبهٔ دستی (کسر دقیق) باید با جواب موتور بخواند؛ اگر نخواند، آزمون می‌افتد."""
        for c in inv.cases(reveal=True):
            for chk in c.get("checks", []):
                self.assertTrue(chk["agree"], f"{c['id']}: {chk}")

    def test_manual_formula_is_evaluable_and_reproduces_answer(self):
        for c in inv.cases(reveal=True):
            if not c.get("formula_plain"):
                continue
            env = {"__builtins__": {}}
            value = eval(c["formula_plain"], env)  # noqa: S307 - فرمول تولیدی و بی‌خطر
            ans = c["answer_num"]
            if ans is None:
                continue
            self.assertAlmostEqual(value, ans, delta=abs(ans) * 0.02 + 0.5,
                                   msg=f"{c['id']}: فرمول دستی {value} ≠ جواب {ans}")


class Ladder(unittest.TestCase):
    """«کِی می‌افتد؟» — پله‌های نرخ سد برای هر ردیف."""

    def test_covered_call_drops_when_hurdle_passes_annualized(self):
        row = inv._pick("covered_call")
        annual = inv.solve(row)["answer"]
        low = inv.ladder_for(row, hurdle=annual / 100 - 0.02)
        high = inv.ladder_for(row, hurdle=annual / 100 + 0.02)
        self.assertTrue(low["survives"])
        self.assertFalse(high["survives"])

    def test_ladder_verdict_mentions_fee_and_hurdle(self):
        row = inv._pick("box")
        text = inv.ladder_for(row)["why"]
        self.assertIn("کارمزد", text)
        self.assertIn("نرخ سد", text)

    def test_ladder_never_promises_profit(self):
        for kind in ("basis", "box", "tabei", "covered_call", "parity"):
            text = inv.ladder_for(inv._pick(kind))["verdict"]
            self.assertNotIn("تضمین", text)


class Guessing(unittest.TestCase):
    """داوری حدس سرمایه‌گذار: عددی، بله/نه، و ورودی نامفهوم."""

    def test_close_guess_is_exact(self):
        c = inv.cases(reveal=True)[0]
        j = inv.judge(c["answer_num"], "فرضی", case_id=c["id"], client="نمونه")
        self.assertEqual(j["status"], "دقیقاً درست")

    def test_far_guess_is_flagged(self):
        c = next(c for c in inv.cases(reveal=True) if c["answer_num"])
        j = inv.judge(float(c["answer_num"]) * 3 + 10, "فرضی", case_id=c["id"], client="نمونه")
        self.assertEqual(j["status"], "دور")

    def test_boolean_guess_accepts_persian_and_english(self):
        c = next(c for c in inv.cases(reveal=True) if c["kind"] == "parity")
        for word in ("بله", "yes", "درست", "1"):
            j = inv.judge(word, None, case_id=c["id"], client="نمونه")
            self.assertIn(j["status"], ("درست", "نادرست"), word)

    def test_unknown_case_is_rejected(self):
        with self.assertRaises(KeyError):
            inv.judge("نه", None, case_id="چنین‌چیزی‌نیست", client="نمونه")

    def test_gibberish_guess_is_not_scored(self):
        c = next(c for c in inv.cases(reveal=True) if c["answer_num"])
        j = inv.judge("بلانمیدانم", None, case_id=c["id"], client="نمونه")
        self.assertEqual(j["status"], "بی‌عدد")


class LogChain(unittest.TestCase):
    """دفتر آزمون: زنجیرهٔ هش، کارنامه، و شناسایی دست‌کاری."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = pathlib.Path(self.tmp.name) / "blind.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_and_read_roundtrip(self):
        inv.append_guess({"case": "x", "guess": 1, "client": "c"}, path=self.log)
        rows = inv.read_log(self.log)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["chain"])
        inv.append_guess({"case": "y", "guess": 2, "client": "c"}, path=self.log)
        self.assertEqual(len(inv.read_log(self.log)), 2)
        self.assertTrue(inv.verify_chain(self.log)["ok"])

    def test_tamper_is_detected(self):
        inv.append_guess({"case": "x", "guess": 1, "client": "c"}, path=self.log)
        inv.append_guess({"case": "y", "guess": 2, "client": "c"}, path=self.log)
        data = json.loads(self.log.read_text(encoding="utf-8"))
        data[0]["guess"] = 999
        self.log.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        v = inv.verify_chain(self.log)
        self.assertFalse(v["ok"])
        self.assertEqual(v["broken_at"], 1)

    def test_scorecard_counts_and_accuracy(self):
        cs = inv.cases(reveal=True)
        c = next(x for x in cs if x["answer_num"])
        inv.judge(c["answer_num"], None, case_id=c["id"], client="س", path=self.log)
        inv.judge(0.0, None, case_id=c["id"], client="س", path=self.log)
        card = inv.scorecard(path=self.log)
        self.assertEqual(card["guesses"], 2)
        self.assertEqual(card["near"], 1)
        self.assertEqual(card["fair_pp"], 50.0)

    def test_verify_on_missing_file_is_ok(self):
        self.assertTrue(inv.verify_chain(self.log)["ok"])


class CompatWithGui(unittest.TestCase):
    """شکل خروجی‌هایی که گام ۱۰ رابط گرافیکی می‌خواند (قرارداد ثابت بماند)."""

    def setUp(self):
        # دفتر واقعی سرمایه‌گذار دست‌کاری نشود: هر آزمون دفتر موقتی خودش را دارد
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(inv, "LOG_FILE", pathlib.Path(self.tmp.name) / "blind.json")
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_check_shim_matches_gui_field_names(self):
        res = inv.check("box_annual", "62")
        for key in ("ok", "id", "title", "answer", "unit", "verdict", "off_pct", "formula",
                    "second", "note", "chain"):
            self.assertIn(key, res, f"کلید «{key}» رابط را می‌شکند")
        self.assertTrue(res["ok"])
        self.assertIn("نزدیک", res["verdict"])

    def test_check_shim_reports_unknown_case_without_crashing(self):
        res = inv.check("نیست", "1")
        self.assertFalse(res["ok"])
        self.assertIn("error", res)

    def test_strategy_table_has_hurdles_and_cells(self):
        table = inv.strategy_table()
        self.assertTrue(table["hurdles"])
        self.assertTrue(table["rows"])
        for row in table["rows"]:
            self.assertEqual(sorted(row["cells"].keys()),
                             sorted(str(h) for h in table["hurdles"]))
            self.assertIn("verdict", table)

    def test_strategy_table_parity_never_passes(self):
        table = inv.strategy_table()
        parity = [r for r in table["rows"] if r["kind"] == "parity"]
        self.assertTrue(parity)
        for cell in parity[0]["cells"].values():
            self.assertFalse(cell["go"])

    def test_size_sensitivity_is_monotonic(self):
        rows = inv.size_sensitivity(capital=100_000_000.0, margin_per_contract=2_000_000.0)
        counts = [r["contracts"] for r in rows]
        self.assertEqual(counts, sorted(counts))
        for r in rows:
            self.assertAlmostEqual(r["margin_locked"] + r["free_cash"], 100_000_000.0, places=2)

    def test_reconcile_charges_real_fees(self):
        rec = inv.reconcile(symbol="فولاد", entry=7000, exit=7000, days=30, units=1)
        self.assertLess(rec["profit"], 0)         # بی‌حرکت هم کارمزد می‌خورد
        self.assertIn("زیان", rec["verdict"])

    def test_reconcile_rejects_text(self):
        rec = inv.reconcile(symbol="فولاد", entry="عدد", exit=7000, days=30, units=1)
        self.assertFalse(rec["ok"])
        self.assertIn("error", rec)

    def test_verify_chain_has_gui_keys(self):
        v = inv.verify_chain()
        for key in ("ok", "rows", "last_fingerprint", "detail"):
            self.assertIn(key, v)


class Sheet(unittest.TestCase):
    """برگهٔ چاپی و پیمان‌نامه."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.html = self.dir / "sheet.html"
        self.md = self.dir / "sheet.md"
        self.log = self.dir / "log.json"
        self.patch = mock.patch.object(inv, "LOG_FILE", self.log)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_sheet_includes_questions_ladder_and_credit(self):
        inv.judge(inv.cases(reveal=True)[1]["answer_num"], None,
                  case_id=inv.cases(reveal=True)[1]["id"], client="آقای نمونه")
        out = inv.build_sheet(client="آقای نمونه", sheet_html=self.html, sheet_md=self.md,
                              log_path=self.log)
        text = self.html.read_text(encoding="utf-8")
        self.assertIn("آقای نمونه", text)
        self.assertIn("Masoud Mojarabian", text)
        self.assertIn("کِی می‌افتد", text)
        self.assertIn("چند قرارداد", text)
        self.assertTrue(out["md"])
        self.assertIn("|", self.md.read_text(encoding="utf-8"))

    def test_pledge_is_two_signature_and_honest(self):
        text = inv.build_pledge(client="آقای نمونه", path=self.dir / "pledge.md")
        self.assertIn("امضای سرمایه‌گذار", text)
        self.assertIn("امضای برگزارکننده", text)
        self.assertIn("تضمین سود نمی‌کند", text)
        self.assertIn("عدد کارگزاری مقدّم", text)
        self.assertIn("زنجیرهٔ هش", text)


class Cli(unittest.TestCase):
    """خط فرمان، همان‌طور که کاربر نوب اجرا می‌کند."""

    def test_cases_cli_has_no_answer_leak(self):
        r = subprocess.run([sys.executable, "investor_test.py", "--cases"], cwd=str(BASE),
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("آزمون کور سرمایه‌گذار", r.stdout)
        self.assertNotIn("جواب موتور", r.stdout)

    def test_reveal_cli_shows_answers(self):
        r = subprocess.run([sys.executable, "investor_test.py", "--reveal"], cwd=str(BASE),
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("جواب موتور", r.stdout)

    def test_flip_cli_returns_json(self):
        r = subprocess.run([sys.executable, "investor_test.py", "--flip"], cwd=str(BASE),
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertIn("meaning", data)

    def test_help_is_persian(self):
        r = subprocess.run([sys.executable, "investor_test.py", "--help"], cwd=str(BASE),
                           capture_output=True, text=True, timeout=120)
        self.assertIn("آزمون کور", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
