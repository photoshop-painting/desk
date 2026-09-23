#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون‌های گواهی استفادهٔ موفق: دفتر زنجیره‌هش‌دار، شمارش، حریم خصوصی و گواهی دو امضا.

هیچ آزمونی دفتر واقعی (data/usage-ledger.json) را دست نمی‌زند؛ همه در پوشهٔ موقتی کار می‌کنند.
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

import usage_meter as um  # noqa: E402


class LedgerChain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = pathlib.Path(self.tmp.name) / "usage.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_record_appends_and_chains(self):
        a = um.record("judge", "kind=box", path=self.log)
        b = um.record("ritual", "روز ۱", path=self.log)
        self.assertNotEqual(a["chain"], b["chain"])
        self.assertEqual(len(um.rows(self.log)), 2)
        self.assertTrue(um.verify(self.log)["ok"])

    def test_unknown_kind_is_refused(self):
        with self.assertRaises(KeyError):
            um.record("چیزعجیب", path=self.log)
        self.assertEqual(um.rows(self.log), [])

    def test_tamper_breaks_the_chain(self):
        um.record("judge", "الف", path=self.log)
        um.record("judge", "ب", path=self.log)
        data = json.loads(self.log.read_text(encoding="utf-8"))
        data[0]["label"] = "دست‌کاری‌شده"
        self.log.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        v = um.verify(self.log)
        self.assertFalse(v["ok"])
        self.assertEqual(v["broken_at"], 1)

    def test_label_is_cleaned_and_bounded(self):
        rec = um.record("run", "  چند   فاصله  " + "x" * 300, path=self.log)
        self.assertTrue(rec["label"].startswith("چند فاصله x"), rec["label"][:20])
        self.assertLessEqual(len(rec["label"]), 80)
        self.assertNotIn("  ", rec["label"])


class SummaryAndPrivacy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = pathlib.Path(self.tmp.name) / "usage.json"
        for kind in ("judge", "judge", "ritual", "bundle", "blind"):
            um.record(kind, "نمونه", path=self.log)

    def tearDown(self):
        self.tmp.cleanup()

    def test_summary_counts_and_days(self):
        s = um.summary(self.log)
        self.assertEqual(s["total"], 5)
        self.assertEqual(s["by_kind"]["judge"], 2)
        self.assertEqual(s["active_days"], 1)
        self.assertEqual(s["today"], 5)
        self.assertTrue(s["verify"]["ok"])
        self.assertTrue(s["kept_local"])

    def test_privacy_guard_flags_financial_keys(self):
        self.assertTrue(um.privacy_check(self.log)["clean"])
        data = json.loads(self.log.read_text(encoding="utf-8"))
        data[0]["profit"] = 1234
        self.log.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        res = um.privacy_check(self.log)
        self.assertFalse(res["clean"])
        self.assertIn("profit", res["offending_keys"])

    def test_ledger_never_contains_financial_field_names(self):
        raw = self.log.read_text(encoding="utf-8")
        for word in ("price", "spot", "strike", "premium", "balance", "account"):
            self.assertNotIn(f'"{word}"', raw)


class Statement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.log = self.dir / "usage.json"
        for kind in ("judge", "decision", "ritual", "exam", "judge"):
            um.record(kind, "نمونه", path=self.log)

    def tearDown(self):
        self.tmp.cleanup()

    def test_statement_files_and_content(self):
        s = um.summary(self.log, trial_days=3, real_days=2)
        hp, mp = um.build_statement(s, client="شرکت نمونه", period="مهر ۱۴۰۵",
                                    html_path=self.dir / "st.html", md_path=self.dir / "st.md")
        md = mp.read_text(encoding="utf-8")
        self.assertTrue(hp.exists() and mp.exists())
        self.assertIn("شرکت نمونه", md)
        self.assertIn("مهر ۱۴۰۵", md)
        self.assertIn("امضای ارائه‌دهنده", md)
        self.assertIn("امضای کاربر/شرکت", md)
        self.assertIn("اثبات نمی‌کند", md)
        self.assertIn("اثر انگشت زنجیرهٔ دفتر", md)
        self.assertIn("سالم ✅", md)
        self.assertIn("| داوری سیگنال (می‌ماند یا می‌افتد) | `judge` | 2 |", md)
        html = hp.read_text(encoding="utf-8")
        self.assertIn("این گواهی چه می‌گوید و چه نمی‌گوید", html)
        self.assertIn("Masoud Mojarabian", html)

    def test_empty_ledger_still_builds_honest_statement(self):
        empty = self.dir / "empty.json"
        s = um.summary(empty)
        hp, mp = um.build_statement(s, html_path=self.dir / "e.html", md_path=self.dir / "e.md")
        md = mp.read_text(encoding="utf-8")
        self.assertIn("مجموع کارهای ثبت‌شده: **0**", md)
        self.assertIn("اثبات نمی‌کند", md)
        self.assertEqual(s["active_days"], 0)

    def test_broken_chain_is_shown_on_the_statement(self):
        data = json.loads(self.log.read_text(encoding="utf-8"))
        data[0]["kind"] = "bundle"
        self.log.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        s = um.summary(self.log)
        _, mp = um.build_statement(s, html_path=self.dir / "b.html", md_path=self.dir / "b.md")
        self.assertIn("شکسته ⚠️", mp.read_text(encoding="utf-8"))


class Cli(unittest.TestCase):
    """فقط دستورهای خواندنی را از خط فرمان می‌آزماییم تا دفتر واقعی دست نخورد."""

    def _run(self, *args):
        return subprocess.run([sys.executable, "usage_meter.py", *args], cwd=str(BASE),
                              capture_output=True, text=True, timeout=120)

    def test_summary_cli(self):
        r = self._run("--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertIn("total", data)
        self.assertIn("kept_local", data)

    def test_verify_cli(self):
        r = self._run("--verify")
        self.assertIn(r.returncode, (0, 1))
        self.assertIn("دفتر", r.stdout)

    def test_unknown_kind_cli_fails_cleanly(self):
        r = self._run("--record", "چیزعجیب")
        self.assertEqual(r.returncode, 1)
        self.assertIn("خطا", r.stdout)


class CompatWithTheApp(unittest.TestCase):
    """کلیدها و نام‌هایی که کارساز/رابط گرافیکی انتظار دارند نباید بشکنند."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = pathlib.Path(self.tmp.name) / "u.json"
        for kind in ("run", "judge", "blind", "ladder", "pledge", "exam", "dossier",
                     "bundle", "snapshot", "import"):
            um.record_event(kind, label=um.KIND_LABELS[kind], path=self.log)

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_kind_the_server_uses_is_known(self):
        for kind in ("run", "judge", "blind", "ladder", "pledge", "exam", "dossier",
                     "bundle", "snapshot", "import"):
            self.assertIn(kind, um.KIND_LABELS)

    def test_summary_exposes_app_keys(self):
        s = um.summary(self.log)
        for key in ("success_total", "rows", "chain_ok", "broken_at", "by_kind", "active_days"):
            self.assertIn(key, s)
        self.assertEqual(s["success_total"], 10)
        self.assertEqual(s["rows"], 10)
        self.assertTrue(s["chain_ok"])

    def test_verify_chain_matches_verify(self):
        self.assertEqual(um.verify_chain(self.log), um.verify(self.log))

    def test_build_statement_returns_two_paths(self):
        hp, mp = um.build_statement(um.summary(self.log),
                                    html_path=pathlib.Path(self.tmp.name) / "a.html",
                                    md_path=pathlib.Path(self.tmp.name) / "a.md")
        self.assertTrue(pathlib.Path(hp).exists() and pathlib.Path(mp).exists())

    def test_record_event_never_raises_on_weird_label(self):
        rec = um.record_event("run", label="   ", note=None, path=self.log)
        self.assertEqual(rec["label"], "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
