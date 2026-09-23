#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون «اتصال خودکار»: پیدا کردن منبع سالم، سنجش عدد، و ذخیرهٔ برنده.

سرویس‌های واقعی از این‌طرف مرزها در دسترس نیستند، پس اینجا سرویس‌های تقلبی محلی
با همان شکل پاسخ ساخته می‌شوند تا منطق تصمیم‌گیری برنامه آزموده شود.
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import autoconnect as ac  # noqa: E402
import connections as conn  # noqa: E402
import mock_feed  # noqa: E402


class FakeService(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, body: bytes, ctype="application/json; charset=utf-8", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/tgju-like":
            return self._send(json.dumps({"data": [{"p": "1,234,567"}]}).encode())
        if path == "/nested-like":
            return self._send(json.dumps({"response": {"quote": {"last": 92_500}}}).encode())
        if path == "/html-like":
            return self._send(b"<html><body>blocked</body></html>", "text/html; charset=utf-8")
        if path == "/empty-like":
            return self._send(json.dumps({"data": []}).encode())
        if path == "/timestamp-like":
            return self._send(json.dumps({"data": [{"p": 1_760_000_000_000}]}).encode())
        if path == "/search-ok":
            return self._send(json.dumps({"instrumentSearch": [{"insCode": "46348559193224090"}]}).encode())
        if path == "/search-empty":
            return self._send(json.dumps({"instrumentSearch": []}).encode())
        if path.startswith("/quote-ok/"):
            return self._send(json.dumps({"closingPriceDaily": [{"pClosing": 7_050}]}).encode())
        return self._send(b"{}", code=404)


def candidate(base: str, path: str, **kw) -> dict:
    cand = {"name": kw.pop("name", "c-1"), "label": kw.pop("label", "داوطلب"),
            "url_template": base + path, "paths": kw.pop("paths", ["data.0.p"]),
            "plausible": kw.pop("plausible", (10, 500_000_000))}
    cand.update(kw)
    return cand


class JudgeTests(unittest.TestCase):
    def test_plausible_price_passes(self):
        ok, why = ac.judge(1_234_567.0, (10_000, 500_000_000))
        self.assertTrue(ok, why)

    def test_zero_and_negative_rejected(self):
        self.assertFalse(ac.judge(0.0, (1, 10))[0])
        self.assertFalse(ac.judge(-5.0, (1, 10))[0])

    def test_timestamp_rejected(self):
        ok, why = ac.judge(1_760_000_000_000.0, (10, 500_000_000))
        self.assertFalse(ok)
        self.assertTrue("تاریخ" in why or "بیرون بازه" in why)

    def test_missing_value_rejected(self):
        self.assertFalse(ac.judge(None, (1, 10))[0])


class TryCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeService)
        cls.port = cls.httpd.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_finds_value_on_first_path(self):
        res = ac.try_candidate(candidate(self.base, "/tgju-like"))
        self.assertTrue(res["ok"], res["reason"])
        self.assertEqual(res["json_path"], "data.0.p")
        self.assertEqual(res["value"], 1_234_567.0)

    def test_falls_back_to_next_path(self):
        res = ac.try_candidate(candidate(self.base, "/nested-like",
                                         paths=["data.0.p", "response.quote.last"]))
        self.assertTrue(res["ok"], res["reason"])
        self.assertEqual(res["json_path"], "response.quote.last")

    def test_html_response_is_reported_as_json_problem(self):
        res = ac.try_candidate(candidate(self.base, "/html-like"))
        self.assertFalse(res["ok"])
        self.assertIn("JSON", res["reason"])

    def test_empty_list_is_reported(self):
        res = ac.try_candidate(candidate(self.base, "/empty-like"))
        self.assertFalse(res["ok"])
        self.assertIn("مسیر عدد سالم پیدا نشد", res["reason"])

    def test_timestamp_is_rejected_with_reason(self):
        res = ac.try_candidate(candidate(self.base, "/timestamp-like"))
        self.assertFalse(res["ok"])
        self.assertIn("بازهٔ باورپذیر", res["reason"])

    def test_symbol_code_is_resolved_then_used(self):
        cand = candidate(self.base, "/quote-ok/{symbol}", name="tsetmc-like",
                         paths=["closingPriceDaily.0.pClosing"], needs_code=True,
                         search_url=self.base + "/search-ok?q={symbol}",
                         search_paths=["instrumentSearch.0.insCode"])
        res = ac.try_candidate(cand)
        self.assertTrue(res["ok"], res["reason"])
        self.assertEqual(res["resolved_code"], "46348559193224090")
        self.assertIn("46348559193224090", res["url"])

    def test_missing_code_is_reported(self):
        cand = candidate(self.base, "/quote-ok/{symbol}", name="tsetmc-like",
                         needs_code=True, search_url=self.base + "/search-empty",
                         search_paths=["instrumentSearch.0.insCode"])
        res = ac.try_candidate(cand)
        self.assertFalse(res["ok"])
        self.assertIn("کد نماد", res["reason"])

    def test_network_can_be_disabled(self):
        res = ac.try_candidate(candidate(self.base, "/tgju-like"), allow_network=False)
        self.assertFalse(res["ok"])
        self.assertIn("شبکه", res["reason"])

    def test_works_against_the_local_demo_feed(self):
        """همان مسیری که کاربر با خوراک آزمایشی می‌رود هم باید سالم تشخیص داده شود."""
        httpd = mock_feed.serve(0)
        try:
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            port = httpd.server_address[1]
            res = ac.try_candidate(candidate(f"http://127.0.0.1:{port}", "/quote?symbol={symbol}",
                                             paths=["data.0.p", "data.0.pl"]))
        finally:
            httpd.shutdown()
            httpd.server_close()
        self.assertTrue(res["ok"], res["reason"])


class CodeEnrichmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeService)
        cls.port = cls.httpd.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _cand(self, search="/search-ok"):
        return {"name": "tsetmc-like", "label": "شبیه‌ساز tsetmc", "needs_code": True,
                "url_template": self.base + "/quote-ok/{symbol}",
                "search_url": self.base + search + "?q={symbol}",
                "search_paths": ["instrumentSearch.0.insCode"]}

    def test_codes_are_written_into_rows(self):
        rows = [{"symbol": "اهرم", "kind": "basis", "spot": 20000},
                {"symbol": "فولاد", "kind": "basis", "spot": 7000}]
        out, notes = ac.enrich_snapshot_with_codes(rows, self._cand())
        self.assertTrue(all(r.get("feed_symbol") == "46348559193224090" for r in out))
        self.assertEqual(len(notes), 2)

    def test_existing_code_is_not_overwritten(self):
        rows = [{"symbol": "اهرم", "kind": "basis", "feed_symbol": "999"}]
        out, notes = ac.enrich_snapshot_with_codes(rows, self._cand())
        self.assertEqual(out[0]["feed_symbol"], "999")
        self.assertEqual(notes, [])

    def test_missing_code_is_reported_not_invented(self):
        rows = [{"symbol": "اهرم", "kind": "basis"}]
        out, notes = ac.enrich_snapshot_with_codes(rows, self._cand(search="/search-empty"))
        self.assertNotIn("feed_symbol", out[0])
        self.assertTrue(any("دستی" in n for n in notes))

    def test_non_code_candidate_is_untouched(self):
        rows = [{"symbol": "اهرم", "kind": "basis"}]
        out, notes = ac.enrich_snapshot_with_codes(rows, {"name": "x", "label": "y"})
        self.assertEqual(out, rows)
        self.assertEqual(notes, [])


class AutoConnectFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeService)
        cls.port = cls.httpd.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self._old = (conn.CONFIG_DIR, conn.PROFILES_FILE, conn.KEYS_FILE)
        conn.CONFIG_DIR = self.dir
        conn.PROFILES_FILE = self.dir / "connections.json"
        conn.KEYS_FILE = self.dir / "keys.local.json"

    def tearDown(self):
        conn.CONFIG_DIR, conn.PROFILES_FILE, conn.KEYS_FILE = self._old
        self.tmp.cleanup()

    def test_first_working_candidate_wins(self):
        cands = [candidate(self.base, "/html-like", name="bad", label="خراب"),
                 candidate(self.base, "/tgju-like", name="good", label="سالم")]
        rep = ac.autoconnect(candidates=cands)
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["count_ok"], 1)
        self.assertEqual(rep["winner"]["name"], "good")
        self.assertIn("سالم", rep["summary"])

    def test_all_failing_is_reported_honestly(self):
        cands = [candidate(self.base, "/html-like", name="a"), candidate(self.base, "/empty-like", name="b")]
        rep = ac.autoconnect(candidates=cands)
        self.assertFalse(rep["ok"])
        self.assertIn("هیچ‌کدام", rep["summary"])
        self.assertEqual(len(rep["results"]), 2)

    def test_save_creates_and_selects_profile(self):
        cands = [candidate(self.base, "/tgju-like", name="winner-x", label="برنده",
                           profile_label="برندهٔ آزمون")]
        rep = ac.autoconnect(candidates=cands, save=True)
        self.assertTrue(rep["ok"])
        self.assertIsNotNone(rep["saved"])
        store = conn.load_store()
        self.assertEqual(store["selected"], "winner-x")
        prof = conn.find_profile(store, "winner-x")
        self.assertTrue(prof["tested"])
        self.assertEqual(prof["json_path"], "data.0.p")

    def test_report_text_mentions_each_candidate(self):
        cands = [candidate(self.base, "/tgju-like", name="ok1", label="اول"),
                 candidate(self.base, "/html-like", name="bad1", label="دوم")]
        rep = ac.autoconnect(candidates=cands)
        text = ac.format_report(rep)
        self.assertIn("اول", text)
        self.assertIn("دوم", text)
        self.assertIn("✓", text)
        self.assertIn("✗", text)


if __name__ == "__main__":
    unittest.main()
