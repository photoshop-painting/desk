#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون «گزارش عیب‌یابی» (diagnose.py) — سبک، بدون اجرای آزمون‌های واحد درونی."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GUI = HERE.parent
sys.path.insert(0, str(GUI))

import diagnose as dg  # noqa: E402


class TestCollect(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rep = dg.collect(run_tests=False)

    def test_core_sections_present(self):
        for key in ("ts", "python", "platform", "health", "license", "engine", "files",
                    "connections", "tests"):
            self.assertIn(key, self.rep)

    def test_health_has_items(self):
        items = self.rep["health"]["items"]
        self.assertGreaterEqual(len(items), 5)
        self.assertTrue(all({"name", "ok", "note"} <= set(i) for i in items))

    def test_engine_fingerprint_recorded(self):
        self.assertEqual(16, len(self.rep["engine"]["sha256_16"]))

    def test_files_section_marks_existence(self):
        names = [f["name"] for f in self.rep["files"]]
        self.assertIn("دفتر اتصال", names)
        self.assertTrue(all(isinstance(f["exists"], bool) for f in self.rep["files"]))

    def test_quick_mode_skips_tests_but_stays_ok(self):
        self.assertTrue(self.rep["tests"]["ok"])
        self.assertIn("سریع", self.rep["tests"]["tail"])

    def test_summary_line_mentions_key_facts(self):
        line = dg.summary_line(self.rep)
        self.assertIn("سلامت", line)
        self.assertIn("مجوز", line)


class TestReport(unittest.TestCase):
    def test_report_files_written(self):
        rep = dg.collect(run_tests=False)
        with tempfile.TemporaryDirectory() as tmp:
            h, t = dg.build_report(rep, Path(tmp) / "d.html")
            html = h.read_text(encoding="utf-8")
            txt = t.read_text(encoding="utf-8")
        for needle in ("گزارش عیب‌یابی", "سلامت اجزا", "پرونده‌های مهم",
                       "Masoud Mojarabian", rep["engine"]["sha256_16"]):
            self.assertIn(needle, html)
        self.assertIn("سلامت", txt)
        self.assertIn("engine", txt)

    def test_report_does_not_leak_account_data(self):
        """گزارش فقط وضعیت فنی است؛ نباید حاوی راز یا کلید باشد."""
        rep = dg.collect(run_tests=False)
        with tempfile.TemporaryDirectory() as tmp:
            h, _ = dg.build_report(rep, Path(tmp) / "d.html")
            body = h.read_text(encoding="utf-8")
        for bad in ("api_key", "apiKey", "token=", "password"):
            self.assertNotIn(bad, body)


class TestCli(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run([sys.executable, str(GUI / "diagnose.py"), *args],
                              capture_output=True, text=True, timeout=300)

    def test_json_quick(self):
        r = self._run("--json", "--quick")
        self.assertIn(r.returncode, (0, 1))
        data = json.loads(r.stdout)
        self.assertIn("health", data)
        self.assertIn("engine", data)

    def test_tail_prefers_summary_and_hides_warnings(self):
        """خط «نتیجه» باید گویا باشد، نه هشدار بی‌ربط پایان کار پایتون."""
        noisy = ("..\n"
                 "Ran 691 tests in 32.044s\n"
                 "OK (skipped=107)\n"
                 "sys:1: ResourceWarning: unclosed file <_io.TextIOWrapper name=9 encoding='UTF-8'>\n")
        self.assertEqual(dg.pick_test_tail(noisy), "OK (skipped=107)")
        red = "FAILED (errors=2)\nERROR: test_x (test_y.TestZ.test_x)\nFAIL: test_w (test_v.T.test_w)\n"
        tail = dg.pick_test_tail(red)
        self.assertTrue(tail.startswith("FAILED (errors=2)"))
        self.assertIn("test_x", tail)
        self.assertEqual(dg.pick_test_tail("").strip(), "بی‌پاسخ")

    def test_text_quick(self):
        r = self._run("--text", "--quick")
        self.assertIn("گزارش عیب‌یابی", r.stdout)
        self.assertIn("سلامت", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
