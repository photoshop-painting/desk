#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون‌های صداقت لایهٔ داده — «موفقیت دروغین» نباید ساخته شود.

این پرونده یک اشکال واقعی را قفل می‌کند: اگر شبکه جواب ندهد، خواندنِ خودکار از حافظهٔ
نهان (فایل last.json یا probe-*.json) باعث می‌شد سنجش سرویس‌ها بگوید «۶ از ۶ جواب داد»
در حالی که هیچ پاسخ تازه‌ای نیامده بود. حالا هر خواندن از حافظهٔ نهان یا ممنوع است
(stale_ok=False) یا صریح اعلام می‌شود.

همهٔ آزمون‌ها محلی‌اند: هیچ درخواست شبکه‌ای زده نمی‌شود (نشانی‌های درگاه بسته/نامعتبر).
"""

import json
import os
import pathlib
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

BASE = pathlib.Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import datafeed  # noqa: E402
import data_sources  # noqa: E402

DEAD_URL = "http://127.0.0.1:9/quote"      # درگاه ۹: همیشه بسته، بدون تماس شبکه‌ای واقعی


class StaleCacheIsHonest(unittest.TestCase):
    """حافظهٔ نهان: ممنوع یا برچسب‌دار، هرگز بی‌سروصدا."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = pathlib.Path(self.tmp.name)
        self.patch = mock.patch.object(datafeed, "CACHE_DIR", self.cache)
        self.patch.start()
        self.file = self.cache / "probe-x.json"
        self.file.write_text(json.dumps({"last": 227860}), encoding="utf-8")
        old = time.time() - 3600
        import os
        os.utime(self.file, (old, old))

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_stale_not_used_when_disallowed(self):
        text, status = datafeed.fetch(DEAD_URL, timeout=2, retries=0,
                                      cache_name="probe-x.json", cache_seconds=0,
                                      stale_ok=False)
        self.assertIsNone(text, "خواندن از حافظهٔ کهنه نباید «پاسخ» حساب شود")
        self.assertIn("ناموفق", status)

    def test_stale_is_labeled_when_allowed(self):
        text, status = datafeed.fetch(DEAD_URL, timeout=2, retries=0,
                                      cache_name="probe-x.json", cache_seconds=0,
                                      stale_ok=True)
        self.assertIsNotNone(text)
        self.assertIn("حافظهٔ نهان", status, "باید صریح بگوید از شبکه نیامده")
        self.assertIn("نه از شبکه", status)

    def test_probe_endpoint_reports_failure(self):
        res = data_sources.probe_endpoint(
            {"name": "نمونه", "label": "نمونه", "url": DEAD_URL, "needs": "",
             "gives": "هیچ", "paths": ["last"]},
            timeout=2)
        self.assertFalse(res["ok"], "نشانی بی‌پاسخ نباید سالم اعلام شود")
        self.assertIn("پاسخی نیامد", res["reason"])

    def test_probe_all_verdict_asks_user_to_run_locally(self):
        result = data_sources.probe_all(symbol="فولاد", host="http://127.0.0.1:9",
                                        timeout=2, with_stability=False)
        self.assertEqual(result["summary"]["ok"], 0)
        self.assertIn("دسترسی نبود", result["verdict"])
        self.assertFalse(result["summary"]["usable_for_engine"])


class LiveSnapshotFreshness(unittest.TestCase):
    """قیمتِ حافظهٔ نهان نباید برچسب «زندهٔ ۰ ثانیه پیش» بگیرد."""

    def _snap(self):
        return datafeed.Snapshot(
            rows=[{"name": "الف", "kind": "basis", "symbol": "فولاد", "spot": 7000, "future": 7600,
                   "days": 30},
                  {"name": "ب", "kind": "covered_call", "symbol": "خساپا", "spot": 1200,
                   "strike": 1300, "premium": 40, "days": 30}],
            as_of="2026-09-22", source_label="پروندهٔ دستی")

    def test_stale_prices_are_marked_and_freshness_unknown(self):
        def fake_fetch(url, **kw):
            return json.dumps({"last": 7000}), "از حافظهٔ نهان ۴۰۰ ثانیه‌ای استفاده شد، نه از شبکه"

        with mock.patch.object(datafeed, "fetch", fake_fetch):
            snap = datafeed.live_snapshot(self._snap(),
                                          {"url_template": "http://example.ir/q?s={symbol}",
                                           "json_path": "last", "cache_seconds": 0},
                                          allow_network=True)
        self.assertIsNone(snap.freshness_seconds, "تازگی ناشناخته باید None باشد، نه صفر")
        self.assertIn("حافظهٔ نهان", snap.source_label)
        self.assertTrue(any("حافظهٔ نهان" in m for m in snap.messages))
        self.assertEqual(snap.status, "partial")

    def test_fresh_prices_keep_zero_freshness(self):
        calls = {"n": 0}

        def fake_fetch(url, **kw):
            calls["n"] += 1
            return json.dumps({"last": 7000 + calls["n"]}), "دریافت تازه در تلاش ۱"

        with mock.patch.object(datafeed, "fetch", fake_fetch):
            snap = datafeed.live_snapshot(self._snap(),
                                          {"url_template": "http://example.ir/q?s={symbol}",
                                           "json_path": "last", "cache_seconds": 0},
                                          allow_network=True)
        self.assertEqual(snap.freshness_seconds, 0.0)
        self.assertIn("زندهٔ وب‌سرویس", snap.source_label)
        self.assertNotIn("حافظهٔ نهان", snap.source_label)


class FixturePath(unittest.TestCase):
    """مسیر نمایشی (سرور نمونهٔ محلی) باید همچنان کار کند: همان شکل، برچسب ساختگی."""

    def test_fixture_still_serves_six_endpoints(self):
        httpd, host = data_sources.start_fixture()
        try:
            result = data_sources.probe_all(symbol="فولاد", host=host, timeout=5,
                                            with_stability=False)
        finally:
            httpd.shutdown()
        self.assertGreaterEqual(result["summary"]["ok"], 5, result["verdict"])
        self.assertTrue(all(i["bytes"] >= 0 for i in result["items"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestStaleCacheHonesty(unittest.TestCase):
    """قفل صداقت: جایزه‌ای که از حافظهٔ کهنه می‌آید نباید «موفقیت تازه» جا بزند."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._old = datafeed.CACHE_DIR
        datafeed.CACHE_DIR = Path(self.tmp)

    def tearDown(self):
        datafeed.CACHE_DIR = self._old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_stale(self, name, body):
        f = Path(self.tmp) / name
        f.write_text(body, encoding="utf-8")
        old = time.time() - 3600
        os.utime(f, (old, old))

    def test_stale_ok_false_never_returns_cached_body(self):
        self._write_stale("probe.json", '{"cached": 12345}')
        text, status = datafeed.fetch("http://127.0.0.1:9/none", timeout=1, retries=0,
                                      cache_name="probe.json", cache_seconds=0, stale_ok=False)
        self.assertIsNone(text)
        self.assertNotIn("12345", status)
        self.assertIn("دریافت ناموفق", status)

    def test_stale_ok_true_marks_the_number_as_cached(self):
        self._write_stale("probe.json", '{"cached": 12345}')
        text, status = datafeed.fetch("http://127.0.0.1:9/none", timeout=1, retries=0,
                                      cache_name="probe.json", cache_seconds=0, stale_ok=True)
        self.assertIsNotNone(text)
        self.assertIn("حافظهٔ نهان", status)
