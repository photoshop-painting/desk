#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون خوراک آزمایشی محلی (بدون اینترنت، روی درگاه موقت)."""
from __future__ import annotations

import json
import sys
import threading
import unittest
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import datafeed  # noqa: E402
import mock_feed  # noqa: E402


class MarketTests(unittest.TestCase):
    def test_prices_are_plausible_and_positive(self):
        m = mock_feed.Market(seed=7, event_after=0)
        for sym in ("اهرم", "فولاد", "طلا"):
            for _ in range(50):
                p = m.tick(sym)
                self.assertGreater(p, 0)
                base = mock_feed.START_PRICES[sym]
                self.assertLess(abs(p - base) / base, 0.35)      # گشت آرام، نه انفجار

    def test_unknown_symbol_gets_stable_base(self):
        m = mock_feed.Market(seed=3)
        a, b = m.tick("نماد-ناشناس"), m.tick("نماد-ناشناس")
        self.assertLess(abs(a - b) / a, 0.05)                    # دو خواندن پشت‌سرهم نزدیک‌اند

    def test_event_biases_price_downwards(self):
        m = mock_feed.Market(seed=5, event_after=1)
        before = [m.tick("اهرم") for _ in range(5)]
        m.hit()                                                  # رخداد فعال شود
        after = [m.tick("اهرم") for _ in range(5)]
        self.assertLess(sum(after) / len(after), sum(before) / len(before))

    def test_event_fires_once_after_n_hits(self):
        m = mock_feed.Market(seed=1, event_after=3)
        flags = [m.hit() for _ in range(6)]
        self.assertEqual(flags.count(True), 1)
        self.assertTrue(m.event_on)
        self.assertEqual(flags.index(True), 2)

    def test_event_can_be_disabled(self):
        m = mock_feed.Market(seed=1, event_after=0)
        self.assertEqual([m.hit() for _ in range(5)].count(True), 0)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mock_feed.MARKET = mock_feed.Market(seed=11, event_after=2)
        cls.httpd = mock_feed.serve(0)                     # درگاه موقت
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def get(self, path: str) -> str:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as r:
            return r.read().decode("utf-8")

    def test_quote_endpoint_matches_default_json_path(self):
        payload = json.loads(self.get("/quote?symbol=%D8%A7%D9%87%D8%B1%D9%85"))
        self.assertTrue(payload["ok"])
        value = datafeed.dig(payload, "data.0.pl")
        self.assertIsInstance(value, float)
        value2, why = datafeed.parse_quote_payload(
            json.dumps(payload, ensure_ascii=False), "data.0.pl", "اهرم")
        self.assertIsNotNone(value2, why)

    def test_quote_without_symbol_is_400(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/quote")
        self.assertEqual(ctx.exception.code, 400)

    def test_symbols_endpoint(self):
        data = json.loads(self.get("/symbols"))
        self.assertIn("اهرم", data["symbols"])
        self.assertEqual(data["event_after"], 2)

    def test_history_csv_served_for_backtest(self):
        text = self.get("/history.csv")
        self.assertIn("realized_annualized_pct", text)

    def test_status_page_is_self_contained(self):
        html = self.get("/")
        self.assertIn("خوراک آزمایشی محلی", html)
        self.assertIn("ساختگی", html)
        self.assertNotIn("http://cdn", html)               # هیچ منبع بیرونی
        self.assertNotIn("https://cdn", html)
        self.assertNotIn("<script src", html)

    def test_unknown_path_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/nope")
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
