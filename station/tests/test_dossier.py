#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون «پروندهٔ سرمایه‌گذار»: آیا سند از شاهدهای واقعی ساخته می‌شود و ادعای اضافه نمی‌کند؟"""
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

import dossier as ds  # noqa: E402


class DossierEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.evidence = ds.collect(run_selftest=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_evidence_has_every_section_source(self):
        for key in ("rules", "connection", "snapshot", "trial", "scorecard", "self_test", "files"):
            self.assertIn(key, self.evidence)

    def test_rules_are_the_station_defaults(self):
        self.assertEqual(ds.DEFAULT_RULES["capital"], self.evidence["rules"]["capital"])
        self.assertEqual(0.39, self.evidence["rules"]["hurdle"])
        self.assertEqual(0.20, self.evidence["rules"]["max_margin_pct"])

    def test_no_secret_leaks_into_evidence(self):
        text = json.dumps(self.evidence, ensure_ascii=False).lower()
        for forbidden in ("api_key", "apikey", "token", "secret", "password"):
            self.assertNotIn(forbidden, text)

    def test_files_section_reports_digests_for_existing_files(self):
        existing = [f for f in self.evidence["files"] if f.get("exists")]
        self.assertGreater(len(existing), 3)
        for f in existing:
            self.assertEqual(16, len(f["sha256"]))

    def test_backtest_section_is_labelled_synthetic(self):
        bt = self.evidence["backtest"]
        self.assertIsNotNone(bt)
        self.assertTrue(bt["synthetic"])              # دادهٔ نمونه هرگز «واقعی» جا زده نمی‌شود
        self.assertIn("hit_rate_pct", bt["summary"])

    def test_rules_cover_every_documented_parameter(self):
        for key in self.evidence["rules"]:
            self.assertIn(key, ds.RULE_NOTES, f"برای {key} توضیح فارسی ننوشته‌ایم")


class DossierOutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.paths = ds.build(out=self.dir / "dossier.html", run_selftest=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_builds_html_md_and_json(self):
        for key in ("html", "md", "json"):
            self.assertTrue(Path(self.paths[key]).exists(), key)

    def test_html_is_self_contained_and_has_credit(self):
        html = Path(self.paths["html"]).read_text(encoding="utf-8")
        self.assertIn('dir="rtl"', html)
        self.assertIn("Masoud Mojarabian", html)
        self.assertIn("instagram.com/Mojarabian.Art", html)
        self.assertNotIn("<script src=", html)
        self.assertNotIn("http://cdn", html)

    def test_html_contains_all_nine_sections(self):
        html = Path(self.paths["html"]).read_text(encoding="utf-8")
        for heading in ("۱. مسئله", "۲. قواعد قفل‌شده", "۳. شاهد یک", "۴. شاهد دو", "۵. شاهد سه",
                        "۶. داده و اتصال", "۷. آنچه ادعا نمی‌کنیم", "۸. راستی‌آزمایی مستقل",
                        "۹. شناسنامهٔ پرونده‌ها"):
            self.assertIn(heading, html)

    def test_html_never_promises_profit(self):
        html = Path(self.paths["html"]).read_text(encoding="utf-8")
        self.assertIn("هیچ سود تضمینی وجود ندارد", html)
        self.assertIn("هیچ سفارشی به‌صورت خودکار ارسال نمی‌شود", html)
        self.assertNotIn("سود تضمین‌شده", html)

    def test_html_shows_selftest_ledger_and_fingerprint(self):
        html = Path(self.paths["html"]).read_text(encoding="utf-8")
        self.assertIn("آزمون ۱۰ دقیقه‌ای", html)
        self.assertIn("اثر انگشت", html)
        self.assertIn("fees-kill-edge", html)

    def test_summary_reports_chain_and_scorecard(self):
        s = self.paths["summary"]
        self.assertIn("chain_ok", s)
        self.assertIn("scorecard_ready", s)
        self.assertTrue(s["selftest"]["total"] >= 12)

    def test_json_sidecar_matches_html_evidence(self):
        data = json.loads(Path(self.paths["json"]).read_text(encoding="utf-8"))
        self.assertEqual(data["rules"], ds.DEFAULT_RULES | {k: v for k, v in ds.DEFAULT_RULES.items()})
        self.assertIn("cases", data["self_test"])

    def test_fingerprint_is_deterministic_for_same_evidence(self):
        evidence = ds.collect(run_selftest=False)
        self.assertEqual(ds.build_html(evidence), ds.build_html(evidence))

    def test_markdown_has_hand_check_lines(self):
        md = Path(self.paths["md"]).read_text(encoding="utf-8")
        self.assertIn("چک دستی", md)
        self.assertIn("## قواعد قفل‌شده", md)


class DossierCliTests(unittest.TestCase):
    def test_cli_builds_without_selftest(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "d.html"
            r = subprocess.run([sys.executable, str(GUI / "dossier.py"), "--out", str(out),
                                "--no-selftest", "--no-md"],
                               capture_output=True, text=True, timeout=180, cwd=str(GUI))
            self.assertEqual(0, r.returncode, r.stderr)
            self.assertTrue(out.exists())
            self.assertIn("پروندهٔ سرمایه‌گذار ساخته شد", r.stdout)

    def test_cli_json_dumps_evidence(self):
        r = subprocess.run([sys.executable, str(GUI / "dossier.py"), "--json", "--no-selftest"],
                           capture_output=True, text=True, timeout=180, cwd=str(GUI))
        self.assertEqual(0, r.returncode, r.stderr)
        data = json.loads(r.stdout)
        self.assertIn("scorecard", data)


if __name__ == "__main__":
    unittest.main()
