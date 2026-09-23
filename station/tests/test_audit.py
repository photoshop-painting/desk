#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""لاگِ ممیزی: کارِ هر کاربر با جزئیات + خطاها، قابل دیدن/کپی/پاک/ریست برای مدیر.

قاعده‌های قرمز:
  - رمز و کلید هرگز به‌صورت خوانا در لاگ نمی‌نشینند (redact).
  - لاگ بدون توکنِ پنل دست‌نیافتنی است.
  - «پاک کردن» حذف است؛ «ریست» آرشیو می‌کند و بعد خالی می‌کند.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import audit  # noqa: E402
import gate as g  # noqa: E402


class AuditModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="audit-"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_and_read_roundtrip_newest_first(self):
        audit.write(self.tmp, user="ali", role="guest", method="POST", path="/api/run",
                    action="شروع محاسبه", status=200, ms=12)
        audit.write(self.tmp, user="ali", role="guest", method="GET", path="/api/audit",
                    action="خواندن", status=200, ms=2)
        rows = audit.read(self.tmp)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["path"], "/api/audit")      # تازه‌تر اول
        self.assertEqual(rows[0]["user"], "ali")
        self.assertEqual(rows[1]["action"], "شروع محاسبه")

    def test_sensitive_fields_are_masked(self):
        audit.write(self.tmp, user="mafhoom", role="admin", method="POST", path="/api/connections",
                    details={"name": "p1", "pass": "Smm@1101001", "live-key": "abc123",
                             "label": "سرویس من"})
        raw = (self.tmp / "audit" / "audit.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("Smm@1101001", raw)
        self.assertNotIn("abc123", raw)
        self.assertIn("•••", raw)
        self.assertIn("سرویس من", raw)                        # فیلد غیرحساس دست‌نخورده

    def test_filters(self):
        audit.write(self.tmp, user="ali", role="guest", method="GET", path="/", status=200)
        audit.write(self.tmp, user="mafhoom", role="admin", method="POST", path="/api/health",
                    status=500, level="error", error="Traceback ... KeyError")
        self.assertEqual(len(audit.read(self.tmp, user="ali")), 1)
        self.assertEqual(len(audit.read(self.tmp, level="error")), 1)
        self.assertEqual(len(audit.read(self.tmp, q="Traceback")), 1)
        self.assertEqual(len(audit.read(self.tmp, q="وجودندارد")), 0)

    def test_clear_deletes(self):
        audit.write(self.tmp, user="ali", method="GET", path="/", status=200)
        self.assertEqual(audit.clear(self.tmp), 1)
        self.assertEqual(audit.read(self.tmp), [])
        self.assertEqual(audit.clear(self.tmp), 0)

    def test_reset_archives_then_clears(self):
        audit.write(self.tmp, user="ali", method="GET", path="/", status=200)
        name = audit.reset(self.tmp)
        self.assertTrue(name.startswith("audit-") and name.endswith(".jsonl"))
        self.assertTrue((self.tmp / "audit" / "archived" / name).exists())
        self.assertEqual(audit.read(self.tmp), [])
        self.assertEqual(audit.reset(self.tmp), "")           # پروندهٔ خالی: آرشیوی نمی‌سازد
        self.assertEqual(audit.stats(self.tmp)["archived"], 1)

    def test_stats_counts(self):
        audit.write(self.tmp, user="ali", method="GET", path="/", status=200)
        audit.write(self.tmp, user="mafhoom", role="admin", method="POST", path="/api/x",
                    status=500, level="error", error="boom")
        s = audit.stats(self.tmp)
        self.assertEqual(s["entries"], 2)
        self.assertEqual(s["errors"], 1)
        self.assertEqual(s["users"], 2)

    def test_error_text_is_capped(self):
        audit.write(self.tmp, method="POST", path="/api/x", level="error",
                    error="X" * 99999)
        rows = audit.read(self.tmp)
        self.assertLessEqual(len(rows[0]["error"]), audit.MAX_ERROR_LEN)

    def test_text_output_is_copyable(self):
        audit.write(self.tmp, user="ali", role="guest", method="POST", path="/api/run",
                    action="شروع محاسبه", status=200, ms=9)
        t = audit.text(self.tmp)
        self.assertIn("شروع محاسبه", t)
        self.assertIn("ali", t)
        audit.clear(self.tmp)
        self.assertIn("لاگ خالی", audit.text(self.tmp))


class AuditEndpointTests(unittest.TestCase):
    """رویهٔ کامل: سرور واقعی + توکن پنل؛ بی‌توکن رد می‌شود."""

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="audit-srv-"))
        cfg = cls.dir / "gate.json"
        g.SESSIONS.clear()
        g.set_account("admin", "mafhoom", "Smm@1101001", path=cfg)
        g.set_enabled(True, path=cfg)
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        cls.port = s.getsockname()[1]
        s.close()
        env = {**os.environ, "STATION_GATE_CONFIG": str(cfg), "PYTHONDONTWRITEBYTECODE": "1"}
        cls.proc = subprocess.Popen([sys.executable, "-m", "web_server", "--port", str(cls.port),
                                     "--host", "127.0.0.1", "--no-browser"],
                                    cwd=str(BASE), env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
        cls.base = f"http://127.0.0.1:{cls.port}"
        for _ in range(60):
            try:
                with urllib.request.urlopen(cls.base + "/api/gate/status", timeout=10):
                    break
            except Exception:
                time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.proc.kill()

    def _login_admin(self) -> tuple[str, str]:
        """توکنِ پنل + کوکیٔ نشستِ دروازه (پنل هم پشت دروازه است)."""
        req = urllib.request.Request(self.base + "/api/login",
                                     data=json.dumps({"id": "mafhoom",
                                                      "pass": "Smm@1101001"}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            cookie = r.headers.get("Set-Cookie", "").split(";")[0]
        req2 = urllib.request.Request(self.base + "/api/admin/login",
                                      data=json.dumps({"id": "mafhoom",
                                                       "pass": "Smm@1101001"}).encode(),
                                      headers={"Content-Type": "application/json",
                                               "Cookie": cookie})
        with urllib.request.urlopen(req2, timeout=20) as r:
            return json.loads(r.read())["token"], cookie

    def _get(self, path, token=None, cookie=None):
        headers = {}
        if token:
            headers["X-Admin-Token"] = token
        if cookie:
            headers["Cookie"] = cookie
        try:
            with urllib.request.urlopen(urllib.request.Request(self.base + path,
                                                               headers=headers), timeout=20) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}")

    def _post(self, path, payload, token=None, cookie=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Admin-Token"] = token
        if cookie:
            headers["Cookie"] = cookie
        try:
            with urllib.request.urlopen(urllib.request.Request(
                    self.base + path, data=json.dumps(payload).encode(), headers=headers),
                    timeout=20) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}")

    def test_read_requires_token(self):
        cookie = self._login_admin()[1]
        code, _ = self._get("/api/admin/audit", cookie=cookie)
        self.assertIn(code, (401, 403))

    def test_full_cycle_with_token(self):
        tok, cookie = self._login_admin()
        # یک کار واقعی ثبت شود (خودِ ورود، در لاگ می‌نشیند)
        code, d = self._get("/api/admin/audit?limit=100", tok, cookie)
        self.assertEqual(code, 200)
        self.assertGreaterEqual(d["count"], 1)
        self.assertTrue(any("ورود" in (e.get("action") or "") or
                            e.get("path", "").startswith("/api/") for e in d["entries"]))
        # کپی
        code, d = self._post("/api/admin/audit", {"action": "copy"}, tok, cookie)
        self.assertEqual(code, 200)
        self.assertIn("·", d["text"])
        # ریست (آرشیو + خالی)
        code, d = self._post("/api/admin/audit", {"action": "reset"}, tok, cookie)
        self.assertEqual(code, 200)
        self.assertTrue(d["archived"].startswith("audit-"))
        code, d = self._get("/api/admin/audit?limit=100", tok, cookie)
        self.assertEqual(code, 200)
        # پاک کردن
        code, d = self._post("/api/admin/audit", {"action": "clear"}, tok, cookie)
        self.assertEqual(code, 200)
        self.assertIsInstance(d["cleared"], int)
        # کار ناشناس
        code, d = self._post("/api/admin/audit", {"action": "hacking"}, tok, cookie)
        self.assertEqual(code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
