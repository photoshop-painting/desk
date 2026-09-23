#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون اسنپ‌شات دستی: پاکیزه‌سازی فرم، ذخیرهٔ تاریخ‌دار، و شرط «روز واقعی»."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import datafeed  # noqa: E402
import daily_trial as dt  # noqa: E402

ROWS_FORM = [
    {"symbol": "اهرم", "kind": "basis", "spot": "21,500", "future": "24,900", "days": "88",
     "margin_per_contract": "20000000", "liquidity_contracts_per_day": "900", "spread_pct": "0.005"},
    {"symbol": "فولاد", "kind": "covered_call", "spot": "7050", "strike": "7600",
     "premium": "410", "days": "45", "margin_per_contract": "7050", "feed_symbol": "46348559193224090"},
]


class CleanRowsTests(unittest.TestCase):
    def test_numbers_are_parsed_and_commas_removed(self):
        rows, problems = datafeed.clean_rows(ROWS_FORM)
        self.assertEqual(rows[0]["spot"], 21500.0)
        self.assertEqual(rows[0]["margin_per_contract"], 20_000_000.0)
        self.assertEqual(problems, [])

    def test_empty_text_fields_are_dropped(self):
        rows, _ = datafeed.clean_rows([{"symbol": "اهرم", "kind": "basis", "spot": "20000",
                                        "future": "", "strike": "  "}])
        self.assertNotIn("future", rows[0])
        self.assertNotIn("strike", rows[0])

    def test_blank_symbol_rows_are_skipped_silently(self):
        rows, problems = datafeed.clean_rows(ROWS_FORM + [{"symbol": "  ", "kind": "basis"}])
        self.assertEqual(len(rows), 2)
        self.assertEqual(problems, [])

    def test_bad_number_is_reported_and_dropped(self):
        rows, problems = datafeed.clean_rows([{"symbol": "اهرم", "kind": "basis", "spot": "۲۰ هزار"}])
        self.assertNotIn("spot", rows[0])
        self.assertTrue(any("عدد نبود" in p for p in problems))

    def test_unknown_kind_falls_back_to_basis(self):
        rows, problems = datafeed.clean_rows([{"symbol": "اهرم", "kind": "چیز-عجیب", "spot": 10}])
        self.assertEqual(rows[0]["kind"], "basis")
        self.assertTrue(any("شناخته نشد" in p for p in problems))

    def test_row_without_any_price_is_reported(self):
        _, problems = datafeed.clean_rows([{"symbol": "اهرم", "kind": "basis", "days": 90}])
        self.assertTrue(any("هیچ قیمتی" in p for p in problems))

    def test_nothing_valid_is_an_error(self):
        rows, problems = datafeed.clean_rows([])
        self.assertEqual(rows, [])
        self.assertTrue(any("هیچ ردیف" in p for p in problems))

    def test_feed_symbol_is_kept(self):
        rows, _ = datafeed.clean_rows(ROWS_FORM)
        self.assertEqual(rows[1]["feed_symbol"], "46348559193224090")


class SaveDatedSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_dated_file_with_manual_source(self):
        path = datafeed.save_dated_snapshot(ROWS_FORM, out_dir=self.dir, day="2026-09-22",
                                            note="جلسهٔ اول")
        self.assertEqual(path.name, "snapshot-2026-09-22.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["source"], "manual-broker")
        self.assertEqual(data["note"], "جلسهٔ اول")
        self.assertEqual(len(data["rows"]), 2)
        self.assertTrue(datafeed.snapshot_confirmed(path))

    def test_dated_files_do_not_overwrite_each_other(self):
        a = datafeed.save_dated_snapshot(ROWS_FORM, out_dir=self.dir, day="2026-09-22")
        b = datafeed.save_dated_snapshot(ROWS_FORM, out_dir=self.dir, day="2026-09-23")
        self.assertNotEqual(a.name, b.name)
        self.assertEqual(len(list(self.dir.glob("snapshot-*.json"))), 2)

    def test_empty_rows_raise(self):
        with self.assertRaises(ValueError):
            datafeed.save_dated_snapshot([], out_dir=self.dir)

    def test_load_rows_returns_meta(self):
        path = datafeed.save_dated_snapshot(ROWS_FORM, out_dir=self.dir, day="2026-09-22")
        got = datafeed.load_snapshot_rows(path)
        self.assertTrue(got["exists"])
        self.assertTrue(got["confirmed"])
        self.assertEqual(len(got["rows"]), 2)
        self.assertEqual(got["path"], str(path))

    def test_hand_written_file_is_not_confirmed(self):
        path = self.dir / "my-own.json"
        path.write_text(json.dumps({"as_of": "2026-09-22", "rows": ROWS_FORM}, ensure_ascii=False),
                        encoding="utf-8")
        self.assertFalse(datafeed.snapshot_confirmed(path))
        self.assertFalse(datafeed.load_snapshot_rows(path)["confirmed"])

    def test_quoted_numbers_are_coerced_on_load(self):
        path = self.dir / "quoted.json"
        path.write_text(json.dumps({"as_of": "x", "rows": [
            {"symbol": "اهرم", "kind": "basis", "spot": "21,500", "future": "24,900", "days": "88",
             "margin_per_contract": "20000000", "unit": "قرارداد",
             "liquidity_contracts_per_day": "900", "spread_pct": "0.005"}]}, ensure_ascii=False),
            encoding="utf-8")
        snap = datafeed.load_snapshot_file(path)
        self.assertEqual(snap.rows[0]["spot"], 21500.0)
        self.assertEqual(snap.rows[0]["unit"], "قرارداد")      # متن دست‌نخورده می‌ماند
        self.assertEqual(snap.rows[0]["feed_symbol"] if "feed_symbol" in snap.rows[0] else "", "")

    def test_missing_or_broken_file_is_not_confirmed(self):
        self.assertFalse(datafeed.snapshot_confirmed(self.dir / "nope.json"))
        bad = self.dir / "broken.json"
        bad.write_text("{oops", encoding="utf-8")
        self.assertFalse(datafeed.snapshot_confirmed(bad))


class SyntheticRuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_trial_counts_unconfirmed_file_as_not_real(self):
        path = self.dir / "broker-numbers.json"
        path.write_text(json.dumps({"as_of": "x", "rows": ROWS_FORM}, ensure_ascii=False), encoding="utf-8")
        res = dt.run_daily(mode="file", file_path=path, db=self.dir / "t.sqlite3",
                           report=self.dir / "r.html", use_kodal=False, log_path=self.dir / "daily.log",
                           desk_db=self.dir / "d.sqlite3")
        self.assertTrue(res["ok"])
        self.assertTrue(res["record"]["synthetic"])            # بی تأیید کاربر، روز واقعی نیست
        self.assertFalse(res["record"]["confirmed_file"])
        self.assertGreater(res["record"]["signals"], 0)        # عددهای رشته‌ای هم محاسبه می‌شوند

    def test_trial_counts_confirmed_file_as_real(self):
        path = datafeed.save_dated_snapshot(ROWS_FORM, out_dir=self.dir, day="2026-09-22")
        res = dt.run_daily(mode="file", file_path=path, db=self.dir / "t.sqlite3",
                           report=self.dir / "r.html", use_kodal=False, log_path=self.dir / "daily.log",
                           desk_db=self.dir / "d.sqlite3")
        self.assertTrue(res["record"]["confirmed_file"])
        self.assertFalse(res["record"]["synthetic"])           # پروندهٔ تأییدشده، روز واقعی است


if __name__ == "__main__":
    unittest.main()
