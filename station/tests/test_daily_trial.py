#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون مراسم روزانه و کارنامهٔ آزمون دو هفته‌ای."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE.parent / "desk"))

import daily_trial as dt  # noqa: E402
import live_trial as lt  # noqa: E402


class LabelTests(unittest.TestCase):
    def test_synthetic_labels_are_detected(self):
        for label in ("خوراک آزمایشی محلی (ساختگی)", "دادهٔ نمونهٔ همراه برنامه",
                      "دادهٔ نمونهٔ همراه برنامه (بدون هزینه)"):
            self.assertTrue(dt.is_synthetic(label), label)

    def test_demo_and_template_files_are_synthetic(self):
        for path in ("desk/market-demo.json", "data/snapshot-template.json",
                     "/tmp/نمونهٔ-تاریخ.csv", "demo/history.csv"):
            self.assertTrue(dt.path_is_synthetic(path), path)

    def test_user_files_are_not_synthetic(self):
        for path in ("/home/me/broker-1405-06-31.json", "C:/market/daily.json", None, ""):
            self.assertFalse(dt.path_is_synthetic(path), str(path))

    def test_real_labels_are_not_synthetic(self):
        for label in ("دادهٔ زندهٔ وب‌سرویس", "پروندهٔ دستی کاربر", ""):
            self.assertFalse(dt.is_synthetic(label), label)


class ScorecardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = self.dir / "trial.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def _logs(self, days, synthetic=False):
        return [{"date": d, "synthetic": synthetic, "chain_ok": True, "ts": f"{d}T10:00:00+00:00"}
                for d in days]

    def test_empty_journal_is_not_ready(self):
        score = dt.scorecard(lt.Trial(self.db), log_records=[])
        self.assertFalse(score["ready"])
        self.assertEqual(score["days"], 0)
        self.assertIn("هنوز نه", score["verdict"])

    def test_five_criteria_always_present(self):
        score = dt.scorecard(lt.Trial(self.db), log_records=[])
        self.assertEqual(len(score["criteria"]), 5)
        keys = {c["key"] for c in score["criteria"]}
        self.assertEqual(keys, {"days", "real_days", "marked", "moves", "chain"})

    def test_synthetic_days_do_not_count_as_real(self):
        score = dt.scorecard(lt.Trial(self.db), log_records=self._logs(
            [f"2026-09-{d:02d}" for d in range(1, 13)], synthetic=True))
        self.assertEqual(score["days"], 12)
        self.assertEqual(score["real_days"], 0)
        real = [c for c in score["criteria"] if c["key"] == "real_days"][0]
        self.assertFalse(real["ok"])

    def test_becoming_ready_when_everything_is_there(self):
        t = lt.Trial(self.db)
        # یازده روز واقعی، دفتر پر و بازسنجی‌شده
        logs = self._logs([f"2026-09-{d:02d}" for d in range(1, 12)])
        for i in range(6):
            t.record([{"symbol": f"نماد{i}", "kind": "basis", "expected": 20.0}], dedupe_hours=0)
        t.mark({f"نماد{i}": {"expected_now": 20.0 + (3 - i), "floor": 3.0} for i in range(6)})
        score = dt.scorecard(t, log_records=logs)
        self.assertGreaterEqual(score["days"], 10)
        self.assertEqual(score["real_days"], 11)
        self.assertGreaterEqual(score["up"], 1)
        self.assertGreaterEqual(score["down"], 1)
        self.assertTrue(score["ready"], score["verdict"])
        self.assertIn("آماده", score["verdict"])

    def test_verdict_names_what_is_missing(self):
        t = lt.Trial(self.db)
        t.record([{"symbol": "اهرم", "kind": "basis", "expected": 20.0}])
        score = dt.scorecard(t, log_records=self._logs(["2026-09-01"]))
        self.assertFalse(score["ready"])
        self.assertIn("تداوم", score["verdict"])

    def test_chain_break_blocks_readiness(self):
        t = lt.Trial(self.db)
        t.record([{"symbol": "اهرم", "kind": "basis", "expected": 20.0}])
        import sqlite3
        c = sqlite3.connect(self.db)
        c.execute("UPDATE entries SET expected = 1.0")
        c.commit()
        c.close()
        score = dt.scorecard(t, log_records=self._logs([f"2026-09-{d:02d}" for d in range(1, 12)]))
        self.assertFalse(score["ready"])
        chain = [x for x in score["criteria"] if x["key"] == "chain"][0]
        self.assertFalse(chain["ok"])

    def test_status_text_lists_every_criterion(self):
        text = dt.status_text(dt.scorecard(lt.Trial(self.db), log_records=[]))
        for name in ("تداوم", "روزهای با دادهٔ واقعی", "بازسنجی", "حرکت واقعی", "زنجیرهٔ هش"):
            self.assertIn(name, text)


class LogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "trial-daily.log"

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_and_read(self):
        dt.append_log({"date": "2026-09-22", "recorded": 3}, self.path)
        dt.append_log({"date": "2026-09-23", "recorded": 1}, self.path)
        rows = dt.read_log(self.path)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["recorded"], 1)

    def test_broken_line_is_skipped(self):
        self.path.write_text('{"date":"x"}\nnot json\n{"date":"y"}\n', encoding="utf-8")
        self.assertEqual(len(dt.read_log(self.path)), 2)

    def test_missing_file_reads_empty(self):
        self.assertEqual(dt.read_log(Path(self.tmp.name) / "nope.log"), [])


class SourcePickTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.snap_path = self.dir / "snap.json"
        self.snap_path.write_text(json.dumps({
            "as_of": "2026-09-22", "hurdle": 0.39, "capital": 20_000_000_000,
            "rows": [{"symbol": "اهرم", "kind": "basis", "spot": 20000, "future": 22800,
                      "days": 90, "margin_per_contract": 20_000_000, "unit": "قرارداد",
                      "liquidity_contracts_per_day": 900, "spread_pct": 0.005}]},
            ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_auto_without_url_uses_file(self):
        snap, used, notes = dt.pick_source(mode="auto", file_path=self.snap_path, live_cfg={})
        self.assertEqual(used, "file")
        self.assertEqual(len(snap.rows), 1)
        self.assertTrue(any("پرونده" in n for n in notes))

    def test_auto_without_anything_falls_back_to_demo(self):
        snap, used, notes = dt.pick_source(mode="auto", live_cfg={})
        self.assertEqual(used, "sim")
        self.assertTrue(dt.is_synthetic(snap.source_label))

    def test_live_mode_without_url_falls_back(self):
        snap, used, notes = dt.pick_source(mode="live", file_path=self.snap_path, live_cfg={"url_template": ""})
        self.assertEqual(used, "file")

    def test_network_can_be_blocked(self):
        snap, used, notes = dt.pick_source(
            mode="live", file_path=self.snap_path, allow_network=False,
            live_cfg={"url_template": "http://127.0.0.1:9/quote?symbol={symbol}"})
        self.assertEqual(used, "file")

    def test_write_running_snapshot_makes_market_file(self):
        snap, _, _ = dt.pick_source(mode="file", file_path=self.snap_path)
        out = dt.write_running_snapshot(snap, dt.DEFAULT_RULES, self.dir / "market.json")
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(data["rows"][0]["symbol"], "اهرم")
        self.assertIn("hurdle", data)


class RunDailyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = self.dir / "trial.sqlite3"
        self.report = self.dir / "report.html"
        self.market = self.dir / "market.json"
        self.log = self.dir / "daily.log"
        self._old = (dt.LOG_FILE, dt.RUNNING_SNAPSHOT, dt.REPORT_FILE, dt.DATA)
        dt.LOG_FILE = self.log
        dt.RUNNING_SNAPSHOT = self.market
        dt.REPORT_FILE = self.report
        # دفتر آزمون در همین پوشهٔ موقت ساخته شود
        self._old_desk_db = None

    def tearDown(self):
        dt.LOG_FILE, dt.RUNNING_SNAPSHOT, dt.REPORT_FILE, dt.DATA = self._old
        self.tmp.cleanup()

    def test_run_daily_with_demo_data_records_and_reports(self):
        res = dt.run_daily(mode="sim", rules=dt.DEFAULT_RULES, db=self.db, report=self.report,
                           log_path=self.log,
                           use_kodal=False, desk_db=self.dir / "desk.sqlite3")
        self.assertTrue(res["ok"], res.get("errors"))
        self.assertEqual(res["record"]["mode"], "sim")
        self.assertTrue(res["record"]["synthetic"])
        self.assertGreater(res["record"]["signals"], 0)
        self.assertTrue(res["report"].endswith("report.html"))
        self.assertTrue(Path(res["report"]).exists())
        self.assertTrue(self.log.exists())
        self.assertTrue(res["scorecard"]["criteria"])
        self.assertFalse(res["scorecard"]["ready"])       # یک روز کافی نیست

    def test_run_daily_is_idempotent_for_the_same_signals(self):
        first = dt.run_daily(mode="sim", db=self.db, report=self.report, use_kodal=False, log_path=self.log,
                             desk_db=self.dir / "desk.sqlite3")
        second = dt.run_daily(mode="sim", db=self.db, report=self.report, use_kodal=False, log_path=self.log,
                              desk_db=self.dir / "desk.sqlite3")
        self.assertGreater(first["record"]["recorded"], 0)
        self.assertEqual(second["record"]["recorded"], 0)   # تکراری‌ها ثبت نمی‌شوند
        self.assertGreaterEqual(second["summary"]["marked"], 1)

    def test_demo_file_does_not_count_as_real_day(self):
        demo = self.dir / "market-demo.json"
        demo.write_text(json.dumps({
            "as_of": "2026-09-22", "hurdle": 0.39, "capital": 20_000_000_000,
            "rows": [{"symbol": "اهرم", "kind": "basis", "spot": 20000, "future": 22800, "days": 90,
                      "margin_per_contract": 20_000_000, "unit": "قرارداد",
                      "liquidity_contracts_per_day": 900, "spread_pct": 0.005}]},
            ensure_ascii=False), encoding="utf-8")
        res = dt.run_daily(mode="file", file_path=demo, db=self.db, report=self.report, log_path=self.log,
                           use_kodal=False, desk_db=self.dir / "desk.sqlite3")
        self.assertTrue(res["ok"])
        self.assertEqual(res["record"]["mode"], "file")
        self.assertTrue(res["record"]["synthetic"])            # پروندهٔ نمونه، روز واقعی نیست
        self.assertEqual(res["scorecard"]["real_days"], 0)

    def test_failed_source_does_not_crash(self):
        res = dt.run_daily(mode="file", file_path=self.dir / "missing.json", db=self.db,
                           report=self.report, use_kodal=False, log_path=self.log,
                           desk_db=self.dir / "desk.sqlite3")
        self.assertTrue(res["ok"])                          # به دادهٔ نمونه برمی‌گردد
        self.assertEqual(res["record"]["mode"], "sim")

    def test_log_records_one_line_per_run(self):
        dt.run_daily(mode="sim", db=self.db, report=self.report, use_kodal=False,
                     desk_db=self.dir / "desk.sqlite3", log_path=self.log, note="جلسهٔ اول")
        rows = dt.read_log(self.log)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["note"], "جلسهٔ اول")
        self.assertIn("source", rows[0])


if __name__ == "__main__":
    unittest.main()
