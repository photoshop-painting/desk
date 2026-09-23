#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون «امکان‌سنجی مسیرهای داده»: آیا سنجش، راست می‌گوید یا فقط عدد نشان می‌دهد؟"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

GUI = Path(__file__).resolve().parent.parent
if str(GUI) not in sys.path:
    sys.path.insert(0, str(GUI))

import data_sources as ds  # noqa: E402


class FixtureProbeTests(unittest.TestCase):
    """سنجش روی سرور نمونهٔ محلی با همان ساختار نشانی‌های واقعی."""

    @classmethod
    def setUpClass(cls):
        cls.httpd, cls.host = ds.start_fixture()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_all_endpoints_detected_and_code_resolved(self):
        res = ds.probe_all(host=self.host, with_stability=False, timeout=5)
        self.assertEqual(len(ds.ENDPOINTS), res["summary"]["total"])
        self.assertEqual(res["summary"]["total"], res["summary"]["ok"], [i["reason"] for i in res["items"]])
        self.assertEqual("46348559193224090", res["code"])       # کد نماد از جست‌وجو درآمد
        self.assertTrue(res["summary"]["usable_for_engine"])

    def test_declared_paths_are_the_source_of_truth(self):
        ep = next(e for e in ds.ENDPOINTS if e["name"] == "price_info")
        item = ds.probe_endpoint(ep, code="46348559193224090", host=self.host, timeout=5)
        paths = [f["path"] for f in item["fields"]]
        self.assertIn("closingPriceInfo.pDrCotVal", paths)
        self.assertEqual(4, item["count"])

    def test_wrong_paths_make_endpoint_unusable(self):
        """اگر ساختار سرویس عوض شود، باید «سرخ» شود، نه اینکه بی‌صدا قبول شود."""
        ep = {"name": "broken", "label": "نشانی با ساختار عوض‌شده",
              "url": self.host + "/api/ClosingPrice/GetClosingPriceInfo/{code}",
              "needs": "code", "gives": "", "paths": ["nope.0.notHere"]}
        item = ds.probe_endpoint(ep, code="1", host=self.host, timeout=5)
        self.assertFalse(item["ok"])
        self.assertIn("ساختار", item["reason"])

    def test_stability_detects_a_moving_price(self):
        ep = next(e for e in ds.ENDPOINTS if e["name"] == "price_info")
        s = ds.stability_check(ep, code="46348559193224090", host=self.host, wait=0.3, timeout=5)
        self.assertTrue(s["checked"])
        self.assertEqual("تازه‌شونده", s["verdict"])

    def test_stability_skips_non_price_endpoints(self):
        ep = next(e for e in ds.ENDPOINTS if e["name"] == "symbol_search")
        s = ds.stability_check(ep, symbol="فولاد", host=self.host, wait=0.2, timeout=5)
        self.assertFalse(s["checked"])
        self.assertIn("قیمت نیست", s["reason"])

    def test_missing_code_is_reported_in_persian(self):
        ep = next(e for e in ds.ENDPOINTS if e["name"] == "closing_daily")
        item = ds.probe_endpoint(ep, code="", host=self.host, timeout=5)
        self.assertFalse(item["ok"])
        self.assertIn("insCode", item["reason"])

    def test_offline_flag_does_not_touch_network(self):
        ep = next(e for e in ds.ENDPOINTS if e["name"] == "market_watch")
        item = ds.probe_endpoint(ep, host="http://127.0.0.1:9", allow_network=False, timeout=1)
        self.assertFalse(item["ok"])
        self.assertIn("شبکه خاموش", item["reason"])

    def test_report_and_sheet_are_written(self):
        res = ds.probe_all(host=self.host, with_stability=False, timeout=5)
        with tempfile.TemporaryDirectory() as tmp:
            report = ds.build_report(res, ds.build_matrix(), path=Path(tmp) / "f.html")
            html = report.read_text(encoding="utf-8")
            self.assertIn('dir="rtl"', html)
            self.assertIn("Masoud Mojarabian", html)
            self.assertIn("وجه تضمین", html)
            self.assertNotIn("http://cdn", html)
            sheet = ds.requirement_sheet()
            self.assertIn("برگهٔ نیاز داده", sheet)
            self.assertIn("وجه تضمین", sheet)
            for q in ("قالب دسترسی", "احراز هویت", "پایداری", "پرداخت", "اجازهٔ استفاده"):
                self.assertIn(q, sheet)                    # پنج پرسش فنی از فروشنده

    def test_matrix_covers_three_routes_with_verdicts(self):
        m = ds.build_matrix()
        self.assertEqual(3, len(m))
        for row in m:
            for key in ("route", "gives", "misses", "cost", "verdict", "test"):
                self.assertTrue(row[key], key)
        self.assertIn("نیاز نداریم", m[2]["verdict"])       # پوش لحظه‌ای

    def test_ws_block_appears_only_when_probed(self):
        res = ds.probe_all(host=self.host, with_stability=False, timeout=5)
        with tempfile.TemporaryDirectory() as tmp:
            plain = ds.build_report(res, ds.build_matrix(), path=Path(tmp) / "a.html").read_text(encoding="utf-8")
            with_ws = ds.build_report(res, ds.build_matrix(),
                                      ws={"url": "wss://x/y", "tcp": True, "tls": True, "status": 401,
                                          "verdict": "سرویس هست ولی احراز هویت می‌خواهد", "note": "پاسخ 401"},
                                      path=Path(tmp) / "b.html").read_text(encoding="utf-8")
            self.assertNotIn("<h2>سنجش پوش لحظه‌ای</h2>", plain)
            self.assertIn("<h2>سنجش پوش لحظه‌ای</h2>", with_ws)
            self.assertIn("401", with_ws)


class FakeWsServer:
    """سرور خام برای آزمون دست‌دادن websocket (پاسخ ثابت، بدون کتابخانه)."""

    def __init__(self, response: bytes | None):
        self.response = response
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(2)
        self.port = self.sock.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        try:
            conn, _ = self.sock.accept()
        except OSError:
            return
        try:
            conn.recv(2048)
            if self.response:
                conn.sendall(self.response)
            else:
                time.sleep(1.0)              # سرور ساکت: پاسخ نمی‌دهد
        except OSError:
            pass
        finally:
            conn.close()
            self.sock.close()

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class WsProbeTests(unittest.TestCase):
    def test_upgrade_101_is_reachable(self):
        srv = FakeWsServer(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                           b"Connection: Upgrade\r\nSec-WebSocket-Accept: x\r\n\r\n")
        try:
            res = ds.probe_ws(f"ws://127.0.0.1:{srv.port}/market", timeout=3)
            self.assertTrue(res["tcp"])
            self.assertEqual(101, res["status"])
            self.assertTrue(res["ok"])
            self.assertIn("ارتقا", res["verdict"])
        finally:
            srv.close()

    def test_401_is_reachable_but_needs_auth(self):
        srv = FakeWsServer(b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\n\r\n")
        try:
            res = ds.probe_ws(f"ws://127.0.0.1:{srv.port}/market", timeout=3)
            self.assertEqual(401, res["status"])
            self.assertFalse(res["ok"])
            self.assertIn("احراز هویت", res["verdict"])
        finally:
            srv.close()

    def test_silent_server_reports_timeout_honestly(self):
        srv = FakeWsServer(None)
        try:
            res = ds.probe_ws(f"ws://127.0.0.1:{srv.port}/market", timeout=1)
            self.assertFalse(res["ok"])
            self.assertTrue(res["verdict"])
            self.assertNotIn("101", str(res.get("status")))
        finally:
            srv.close()

    def test_closed_port_is_unreachable(self):
        res = ds.probe_ws("ws://127.0.0.1:9/market", timeout=1)
        self.assertFalse(res["tcp"])
        self.assertEqual("دسترس نیست", res["verdict"])

    def test_invalid_url_is_rejected(self):
        res = ds.probe_ws("https://example.ir/market")
        self.assertEqual("نشانی نامعتبر", res["verdict"])

    def test_real_read_says_what_is_missing(self):
        res = ds.real_ws_read("ws://127.0.0.1:9/x", seconds=1)
        self.assertFalse(res["ok"])
        self.assertTrue(res.get("reason"))


class DataSourcesCliTests(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run([sys.executable, str(GUI / "data_sources.py"), *args],
                              capture_output=True, text=True, timeout=180, cwd=str(GUI))

    def test_sheet_command_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "sheet.md"
            code = ("import sys, pathlib; sys.path.insert(0, r'%s'); import data_sources as ds; "
                    "pathlib.Path(r'%s').write_text(ds.requirement_sheet(), encoding='utf-8')"
                    % (GUI, out))
            r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
            self.assertEqual(0, r.returncode, r.stderr)
            self.assertIn("وجه تضمین", out.read_text(encoding="utf-8"))

    def test_fixture_json_run_is_usable(self):
        r = self._run("--fixture", "--json", "--no-stability")
        self.assertEqual(0, r.returncode, r.stderr[:400])
        data = json.loads(r.stdout)
        self.assertTrue(data["result"]["fixture"])
        self.assertGreaterEqual(data["result"]["summary"]["ok"], 3)
        self.assertEqual(3, len(data["matrix"]))

    def test_ws_probe_cli_on_unreachable_host(self):
        r = self._run("--ws", "ws://127.0.0.1:9/x", "--symbol", "فولاد", "--timeout", "1",
                      "--host", "http://127.0.0.1:9")
        self.assertIn("پوش لحظه‌ای", r.stdout)
        self.assertIn("دسترس نیست", r.stdout)

    def test_version_flag(self):
        r = self._run("--version")
        self.assertEqual(0, r.returncode)
        self.assertEqual(ds.VERSION, r.stdout.strip())


if __name__ == "__main__":
    unittest.main()
