#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون دفتر آزمون زنده (ثبت، بازسنجی، زنجیرهٔ هش، گزارش)."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import live_trial as lt  # noqa: E402


class FakeSignal:
    def __init__(self, symbol, kind, expected, status="pending", score=8.0, detail=None):
        self.symbol, self.kind, self.annualized_pct = symbol, kind, expected
        self.status, self.score_pp = status, score
        self.detail = detail or {"spot": 20000, "future": 22800, "days": 90}
        self.sid, self.gate_note = f"sig-{symbol}", ""


class TrialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "trial.sqlite3"
        self.t = lt.Trial(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    # ---------- ثبت
    def test_record_and_count(self):
        saved = self.t.record([{"symbol": "اهرم", "kind": "basis", "expected": 29.48,
                                "decision": "approved", "note": "جلسهٔ اول", "legs": {"spot": 20000}}])
        self.assertEqual(len(saved), 1)
        self.assertEqual(self.t.count(), 1)
        row = self.t.all()[0]
        self.assertEqual(row["symbol"], "اهرم")
        self.assertEqual(row["legs"]["spot"], 20000)

    def test_record_skips_rows_without_symbol(self):
        self.assertEqual(self.t.record([{"kind": "basis", "expected": 5}]), [])
        self.assertEqual(self.t.count(), 0)

    def test_dedupe_blocks_same_signal_within_window(self):
        item = {"symbol": "فولاد", "kind": "covered_call", "expected": 17.5, "decision": "pending"}
        self.assertEqual(len(self.t.record([item])), 1)
        self.assertEqual(len(self.t.record([item])), 0)
        self.assertEqual(self.t.count(), 1)

    def test_dedupe_can_be_disabled(self):
        item = {"symbol": "فولاد", "kind": "covered_call", "expected": 17.5}
        self.t.record([item], dedupe_hours=0)
        self.t.record([item], dedupe_hours=0)
        self.assertEqual(self.t.count(), 2)

    def test_record_from_signals_builds_legs(self):
        saved = self.t.record_from_signals([FakeSignal("کگل", "tabei", 3.36)], source_label="دادهٔ نمونه", mode="sim")
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["legs"]["future"], 22800)
        self.assertEqual(saved[0]["source_label"], "دادهٔ نمونه")

    def test_conservative_span_lowers_expected(self):
        saved = self.t.record_from_signals([FakeSignal("کگل", "tabei", 3.36)], add_span=-2)
        self.assertAlmostEqual(saved[0]["expected"], 1.36, places=3)

    # ---------- زنجیرهٔ هش
    def test_chain_verifies_after_many_records(self):
        for i, sym in enumerate(["اهرم", "فولاد", "کگل", "شپنا"]):
            self.t.record([{"symbol": sym, "kind": "basis", "expected": 10 + i}])
        ok, msg = self.t.verify_chain()
        self.assertTrue(ok, msg)
        self.assertIn("سالم", msg)

    def test_tampering_breaks_chain(self):
        self.t.record([{"symbol": "اهرم", "kind": "basis", "expected": 29.48}])
        self.t.record([{"symbol": "فولاد", "kind": "covered_call", "expected": 17.5}])
        c = sqlite3.connect(self.db)
        c.execute("UPDATE entries SET expected = 99.9 WHERE symbol = 'اهرم'")
        c.commit()
        c.close()
        ok, msg = self.t.verify_chain()
        self.assertFalse(ok)
        self.assertIn("شکسته", msg)

    def test_deleting_a_row_breaks_chain(self):
        self.t.record([{"symbol": "اهرم", "kind": "basis", "expected": 29.48}])
        self.t.record([{"symbol": "فولاد", "kind": "covered_call", "expected": 17.5}])
        c = sqlite3.connect(self.db)
        c.execute("DELETE FROM entries WHERE symbol = 'اهرم'")
        c.commit()
        c.close()
        ok, _ = self.t.verify_chain()
        self.assertFalse(ok)

    # ---------- بازسنجی
    def test_mark_computes_delta_and_status(self):
        self.t.record([{"symbol": "اهرم", "kind": "basis", "expected": 29.48}])
        out = self.t.mark({"اهرم": {"expected_now": 12.0, "floor": 3.0, "spot_now": 21000}})
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out[0]["delta_pp"], -17.48, places=2)
        self.assertEqual(out[0]["status_now"], "کم شد")

    def test_mark_flags_under_floor(self):
        self.t.record([{"symbol": "کگل", "kind": "tabei", "expected": 8.0}])
        out = self.t.mark({"کگل": {"expected_now": 1.5, "floor": 5.0}})
        self.assertEqual(out[0]["status_now"], "زیر کف رفت")

    def test_mark_marks_wider_opportunity(self):
        self.t.record([{"symbol": "شپنا", "kind": "box", "expected": 3.0}])
        out = self.t.mark({"شپنا": {"expected_now": 6.5, "floor": 3.0}})
        self.assertEqual(out[0]["status_now"], "بازتر شد")

    def test_mark_handles_missing_data_gracefully(self):
        self.t.record([{"symbol": "خساپا", "kind": "basis", "expected": -14.3}])
        out = self.t.mark({"خساپا": {"expected_now": None, "floor": 3.0}})
        self.assertEqual(out[0]["status_now"], "دادهٔ تازه نبود")
        self.assertIsNone(out[0]["delta_pp"])

    def test_mark_ignores_symbols_without_entry(self):
        self.t.record([{"symbol": "اهرم", "kind": "basis", "expected": 29.48}])
        out = self.t.mark({"وبملت": {"expected_now": 5.0, "floor": 3.0}})
        self.assertEqual(out, [])

    def test_latest_mark_wins(self):
        self.t.record([{"symbol": "اهرم", "kind": "basis", "expected": 20.0}])
        self.t.mark({"اهرم": {"expected_now": 15.0, "floor": 3.0}})
        self.t.mark({"اهرم": {"expected_now": 9.0, "floor": 3.0}})
        marks = self.t.latest_marks()
        self.assertEqual(len(marks), 1)
        self.assertAlmostEqual(list(marks.values())[0]["expected_now"], 9.0, places=2)

    # ---------- خلاصه و گزارش
    def test_summary_counts_and_averages(self):
        self.t.record([{"symbol": "اهرم", "kind": "basis", "expected": 30.0}])
        self.t.record([{"symbol": "فولاد", "kind": "covered_call", "expected": 10.0}])
        self.t.mark({"اهرم": {"expected_now": 20.0, "floor": 3.0}})
        s = self.t.summary()
        self.assertEqual(s["entries"], 2)
        self.assertEqual(s["marked"], 1)
        self.assertEqual(s["unmarked"], 1)
        self.assertAlmostEqual(s["avg_expected"], 20.0, places=2)
        self.assertAlmostEqual(s["avg_delta_pp"], -10.0, places=2)
        self.assertTrue(s["chain_ok"])

    def test_summary_on_empty_trial(self):
        s = self.t.summary()
        self.assertEqual(s["entries"], 0)
        self.assertIsNone(s["avg_delta_pp"])
        self.assertTrue(s["chain_ok"])

    def test_report_html_contains_tables_and_credit(self):
        self.t.record([{"symbol": "اهرم", "kind": "basis", "expected": 29.48, "decision": "approved"}])
        self.t.mark({"اهرم": {"expected_now": 12.0, "floor": 3.0}})
        path = self.t.write_report(Path(self.tmp.name) / "report.html")
        html = path.read_text(encoding="utf-8")
        for needle in ("دفتر آزمون زنده", "اهرم", "زنجیرهٔ ثبت", "Masoud Mojarabian",
                       "سود تحقق‌یافته"):
            self.assertIn(needle, html)

    def test_csv_has_header_and_row(self):
        self.t.record([{"symbol": "اهرم", "kind": "basis", "expected": 29.48}])
        path = self.t.write_csv(Path(self.tmp.name) / "entries.csv")
        text = path.read_text(encoding="utf-8-sig")
        self.assertIn("انتظار در ثبت (٪)", text)
        self.assertIn("اهرم", text)

    def test_reopening_db_keeps_entries_and_chain(self):
        self.t.record([{"symbol": "اهرم", "kind": "basis", "expected": 29.48}])
        again = lt.Trial(self.db)
        self.assertEqual(again.count(), 1)
        ok, _ = again.verify_chain()
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
