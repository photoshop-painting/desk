#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون ماژول «آزمون ۱۰ دقیقه‌ای»: آیا کارنامه واقعاً شاهد می‌دهد یا فقط ادعا می‌کند؟"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GUI = Path(__file__).resolve().parent.parent
if str(GUI) not in sys.path:
    sys.path.insert(0, str(GUI))

import selftest as st  # noqa: E402


class SelftestRunTests(unittest.TestCase):
    def test_all_cases_green(self):
        result = st.run_all()
        reds = [c["id"] for c in result["cases"] if not c["ok"]]
        self.assertEqual([], reds, f"موردهای سرخ: {reds}")
        self.assertTrue(result["summary"]["ok"])
        self.assertGreaterEqual(result["summary"]["total"], 12)

    def test_engine_output_matches_independent_hand_calculation(self):
        """هر مورد باید هم عدد برنامه و هم حساب دستی را داشته باشد."""
        result = st.run_all()
        for c in result["cases"]:
            self.assertTrue(c["hand"], f"مورد {c['id']} راه چک دستی ندارد")
            for row in c["rows"]:
                self.assertIn("got", row)
                self.assertIn("expected", row)

    def test_case_ids_are_unique(self):
        ids = [c["id"] for c in st.run_all()["cases"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_engine_fingerprint_is_stable_and_short(self):
        fp = st.engine_fingerprint()
        self.assertEqual(16, len(fp["sha256"]))
        self.assertEqual(fp["sha256"], st.engine_fingerprint()["sha256"])
        self.assertTrue(fp["version"])

    def test_only_filter_selects_subset(self):
        result = st.run_all(only=["fees-kill-edge", "position-size"])
        ids = [c["id"] for c in result["cases"]]
        self.assertEqual(["fees-kill-edge", "position-size"], ids)

    def test_fee_case_really_flips_the_verdict(self):
        c = st.case_fees_kill_edge({})
        got = {r["key"]: r["got"] for r in c["rows"]}
        self.assertTrue(got["go_cheap"])
        self.assertFalse(got["go_dear"])
        self.assertGreater(got["annualized_cheap_pct"], got["annualized_dear_pct"])

    def test_tamper_case_detects_a_broken_chain(self):
        c = st.case_tamper_chain({})
        got = {r["key"]: r["got"] for r in c["rows"]}
        self.assertTrue(got["chain_ok_before"])
        self.assertFalse(got["chain_ok_after_tamper"])

    def test_look_ahead_case_changes_nothing(self):
        c = st.case_no_look_ahead({})
        got = {r["key"]: r["got"] for r in c["rows"]}
        self.assertTrue(got["decisions_identical"])

    def test_live_failure_case_is_honest_about_missing_data(self):
        c = st.case_live_failure_honest({})
        got = {r["key"]: r["got"] for r in c["rows"]}
        self.assertEqual("failed", got["status"])
        self.assertEqual("نامعلوم", got["freshness_unknown"])
        self.assertEqual(0, got["live_prices_empty"])

    def test_missing_expectation_marks_case_red(self):
        """اگر موتور از حساب دستی جدا شود، مورد باید سرخ شود (نه اینکه بی‌صدا رد شود)."""
        def broken(ctx):
            return st._case("broken-case", "مورد خراب", "برای آزمون", {"x": 1}, {"v": 5.0}, {"v": 7.0}, "دستی")

        result = st.run_all(cases=[broken])
        self.assertFalse(result["summary"]["ok"])
        self.assertFalse(result["cases"][0]["ok"])

    def test_result_is_json_serializable(self):
        text = json.dumps(st.run_all(only=["position-size"]), ensure_ascii=False)
        self.assertIn("position-size", text)


class SelftestReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.result = st.run_all(only=["fees-kill-edge", "tamper-chain"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_report_html_has_credit_and_rtl(self):
        path = st.build_report(self.result, self.dir / "report.html")
        html = path.read_text(encoding="utf-8")
        self.assertIn('dir="rtl"', html)
        self.assertIn("Masoud Mojarabian", html)
        self.assertIn("tel:+989126630554", html)
        self.assertIn("ت.me" if False else "t.me/Mojarabian", html)
        self.assertNotIn("http://cdn", html)          # خودبسنده و آفلاین

    def test_report_shows_hand_check_line(self):
        html = st.build_report(self.result, self.dir / "report.html").read_text(encoding="utf-8")
        self.assertIn("چک با ماشین‌حساب", html)
        self.assertIn("fees-kill-edge", html)

    def test_exam_sheet_hides_answers_after_questions(self):
        path = st.build_exam_sheet(self.result, self.dir / "exam.html")
        html = path.read_text(encoding="utf-8")
        self.assertIn("بخش یک: سؤال", html)
        self.assertIn("بخش دو: پاسخ", html)
        self.assertLess(html.index("بخش یک: سؤال"), html.index("بخش دو: پاسخ"))
        self.assertIn("حدس شما", html)

    def test_console_output_mentions_result(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            st.console(self.result)
        self.assertIn("سبز", buf.getvalue())


class SelftestCliTests(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run([sys.executable, str(GUI / "selftest.py"), *args],
                              capture_output=True, text=True, timeout=180, cwd=str(GUI))

    def test_cli_json_output_is_pure_json(self):
        r = self._run("--json")
        self.assertEqual(0, r.returncode)
        data = json.loads(r.stdout)          # پیام‌های موتور نباید خروجی را آلوده کنند
        self.assertTrue(data["summary"]["ok"])

    def test_cli_list_prints_cases(self):
        r = self._run("--list")
        self.assertEqual(0, r.returncode)
        self.assertIn("fees-kill-edge", r.stdout)

    def test_cli_writes_reports(self):
        r = self._run("--only", "position-size", "--no-report")
        self.assertEqual(0, r.returncode)
        self.assertIn("position-size", r.stdout)

    def test_cli_version(self):
        r = self._run("--version")
        self.assertEqual(0, r.returncode)
        self.assertEqual(st.VERSION, r.stdout.strip())


if __name__ == "__main__":
    unittest.main()
