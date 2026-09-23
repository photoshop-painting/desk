#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون «اجازه‌نامهٔ دسترسی» (license.py) — بی‌شبکه، سریع، با پوشهٔ موقت."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
GUI = HERE.parent
sys.path.insert(0, str(GUI))

import license as lic  # noqa: A004  (نام ماژول خودمان)


class TempLicense(unittest.TestCase):
    """آزمون‌ها به پروندهٔ اجازه‌نامهٔ واقعی دست نمی‌زنند."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = lic.LICENSE_FILE
        lic.LICENSE_FILE = Path(self._tmp.name) / "license.json"

    def tearDown(self):
        lic.LICENSE_FILE = self._orig
        self._tmp.cleanup()


class TestMake(TempLicense):
    def test_grant_fields_and_signature(self):
        row = lic.make_license("شرکت الف", months=6, contact="آقای ب", note="پیش‌فاکتور ۱۲")
        self.assertEqual("شرکت الف", row["client"])
        self.assertEqual(6, row["months"])
        self.assertEqual(16, len(row["signature"]))
        self.assertIn("اجازه‌نامهٔ دسترسی", row["kind"])

    def test_signature_is_reproducible(self):
        a = lic.make_license("شرکت الف", months=6, start=date(2026, 1, 1))
        b = lic.make_license("شرکت الف", months=6, start=date(2026, 1, 1))
        self.assertEqual(a["signature"], b["signature"])
        c = lic.make_license("شرکت ب", months=6, start=date(2026, 1, 1))
        self.assertNotEqual(a["signature"], c["signature"])

    def test_trial_is_short(self):
        row = lic.make_trial("آزمون شرکت الف")
        self.assertIn("آزمون", row["note"])
        span = (date.fromisoformat(row["end"]) - date.fromisoformat(row["start"])).days
        self.assertEqual(lic.TRIAL_DAYS, span)


class TestVerify(TempLicense):
    def test_no_license_is_fine(self):
        st = lic.verify(None)
        self.assertTrue(st["ok"])
        self.assertEqual("بدون اجازه‌نامه", st["state"])

    def test_valid_license_days_left(self):
        row = lic.make_license("شرکت الف", months=2, start=date.today() - timedelta(days=1))
        st = lic.verify(row)
        self.assertTrue(st["ok"])
        self.assertGreater(st["days_left"], 0)

    def test_expired_license_fails(self):
        row = lic.make_license("شرکت الف", months=1, start=date.today() - timedelta(days=90))
        st = lic.verify(row)
        self.assertFalse(st["ok"])
        self.assertEqual("منقضی", st["state"])

    def test_tampered_license_is_caught(self):
        row = lic.make_license("شرکت الف", months=12)
        row["months"] = 120                      # دست‌بردن در مفاد
        st = lic.verify(row)
        self.assertFalse(st["ok"])
        self.assertIn("امضا", st["state"])

    def test_read_and_write_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "license.json"
            row = lic.make_license("شرکت الف", months=3)
            lic.write_license(row, p)
            again = lic.read_license(p)
            self.assertEqual(row["client"], again["client"])
            self.assertTrue(lic.verify(again)["ok"])

    def test_broken_file_reads_as_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "license.json"
            p.write_text("{ شکسته", encoding="utf-8")
            self.assertIsNone(lic.read_license(p))


class TestLadder(TempLicense):
    def test_three_steps(self):
        rows = lic.ladder()
        self.assertEqual(3, len(rows))
        self.assertIn("پشتیبانی", rows[1]["step"])
        for row in rows:
            self.assertTrue(row["what"] and row["basis"] and row["why"])


class TestCli(TempLicense):
    def _run(self, *args):
        import os
        env = dict(os.environ, IRAN_DESK_CONFIG_DIR=self._tmp.name)   # پوشهٔ تنظیمات موقت
        return subprocess.run([sys.executable, str(GUI / "license.py"), *args],
                              capture_output=True, text=True, timeout=120, env=env)

    def test_status_without_license(self):
        r = self._run("--status", "--json")
        self.assertEqual(0, r.returncode)
        self.assertEqual("بدون اجازه‌نامه", json.loads(r.stdout)["status"]["state"])

    def test_grant_text_output(self):
        r = self._run("--grant", "شرکت نمونه", "--months", "12")
        self.assertEqual(0, r.returncode)
        self.assertIn("شرکت نمونه", r.stdout)
        self.assertIn("ذخیره نشد", r.stdout)

    def test_ladder_output(self):
        self.assertIn("پشتیبانی", self._run("--ladder").stdout)




class DocumentTests(unittest.TestCase):
    """سند چاپی اجازه‌نامه: باید نام مشتری، امضا و مرزهای صادقانه را داشته باشد."""

    def test_document_with_license(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            row = lic.make_license("شرکت نمونه", months=6, contact="آقای الف")
            hp, mp = lic.build_document(row, path=d / "doc.md", html_path=d / "doc.html")
            md = mp.read_text(encoding="utf-8")
            html = hp.read_text(encoding="utf-8")
            self.assertIn("شرکت نمونه", md)
            self.assertIn(row["signature"], md)
            self.assertIn("سود تضمینی", md)
            self.assertIn("sha256", md)
            self.assertIn("امضای ارائه‌دهنده", md)
            self.assertIn("اجازه‌نامهٔ دسترسی", html)
            self.assertIn("مهندس مسعود مجربیان", html)

    def test_document_without_license_says_so_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            hp, mp = lic.build_document({}, path=d / "doc.md", html_path=d / "doc.html")
            md = mp.read_text(encoding="utf-8")
            self.assertIn("صادر نشده است", md)
            self.assertIn("حالت آزاد", md)
            self.assertIn("--grant", md)
            self.assertTrue(hp.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
