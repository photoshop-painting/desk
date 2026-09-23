"""آزمون دروازهٔ ورود برنامه (`gate.py`) — مدیر برای صاحب برنامه، مهمان برای کارفرما.

قواعدی که نباید بشکنند: رمز فقط هش می‌شود · مهمان هیچ‌وقت مدیر نمی‌شود · قطع‌کردن مهمان، نشست
باز او را هم می‌بندد · دروازهٔ خاموش = اعتماد محلی (مدیر) · پنج تلاش خطا = قفل کوتاه · عمر نشست
محدود است · وضعیت هیچ رمز و هشی را بیرون نمی‌دهد.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import adminauth as panel  # noqa: E402
import gate as g  # noqa: E402

ADMIN = ("mafhoom", os.environ.get("STATION_TEST_ADMIN_PASS")
         or "Test-Admin-" + __import__("secrets").token_hex(4))   # رمز آزمونی، نه رمز واقعی
GUEST = ("masoud", "09126630554")


class GateBase(unittest.TestCase):
    def setUp(self):
        g.SESSIONS.clear()
        panel.FAILS.clear()
        self.tmp = Path(tempfile.mkdtemp()) / "gate.json"

    def _open_gate(self):
        g.set_account("admin", *ADMIN, path=self.tmp)
        g.set_account("guest", *GUEST, path=self.tmp)
        g.set_enabled(True, path=self.tmp)


class TestGate(GateBase):
    def test_gate_off_by_default_is_local_trust(self):
        self.assertFalse(g.enabled(self.tmp))
        self.assertEqual("admin", g.role_of(None, path=self.tmp))
        s = g.status(self.tmp)
        self.assertFalse(s["enabled"])
        self.assertIn("خاموش", s["rule"])

    def test_admin_login_works(self):
        self._open_gate()
        out = g.login(*ADMIN, ip="1.1.1.1", path=self.tmp)
        self.assertTrue(out["ok"], out)
        self.assertEqual("admin", out["role"])
        self.assertEqual("admin", g.role_of(out["token"], path=self.tmp))

    def test_guest_login_gets_guest_role(self):
        self._open_gate()
        out = g.login(*GUEST, ip="1.1.1.2", path=self.tmp)
        self.assertTrue(out["ok"], out)
        self.assertEqual("guest", out["role"])
        self.assertEqual("guest", g.role_of(out["token"], path=self.tmp))

    def test_guest_password_does_not_open_admin(self):
        self._open_gate()
        wrong = g.login("mafhoom", GUEST[1], ip="1.1.1.3", path=self.tmp)
        self.assertFalse(wrong["ok"])
        wrong2 = g.login("masoud", ADMIN[1], ip="1.1.1.4", path=self.tmp)
        self.assertFalse(wrong2["ok"])

    def test_password_is_hashed_not_stored(self):
        self._open_gate()
        raw = self.tmp.read_text(encoding="utf-8")
        self.assertNotIn(GUEST[1], raw)
        self.assertNotIn(ADMIN[1], raw)
        cfg = json.loads(raw)
        self.assertTrue(cfg["guest"]["hash"] and cfg["guest"]["salt"])

    def test_short_guest_password_rejected(self):
        with self.assertRaises(ValueError):
            g.set_account("guest", "karfarma", "123", path=self.tmp)

    def test_disabled_guest_cannot_login_and_open_session_dies(self):
        self._open_gate()
        tok = g.login(*GUEST, ip="1.1.1.5", path=self.tmp)["token"]
        self.assertEqual("guest", g.role_of(tok, path=self.tmp))
        g.set_enabled_account("guest", False, path=self.tmp)
        self.assertFalse(g.login(*GUEST, ip="1.1.1.6", path=self.tmp)["ok"])
        self.assertIsNone(g.role_of(tok, path=self.tmp))       # نشست باز هم بسته شد

    def test_logout_closes_session(self):
        self._open_gate()
        tok = g.login(*ADMIN, ip="1.1.1.7", path=self.tmp)["token"]
        self.assertTrue(g.logout(tok))
        self.assertIsNone(g.role_of(tok, path=self.tmp))

    def test_token_expires_after_ttl_and_refreshes_on_use(self):
        self._open_gate()
        now = time.time()
        idle = g.login(*GUEST, ip="1.1.1.8", path=self.tmp, now=now)["token"]
        self.assertIsNone(g.role_of(idle, path=self.tmp, now=now + g.TTL_SECONDS + 1))
        busy = g.login(*GUEST, ip="1.1.1.8", path=self.tmp, now=now)["token"]
        self.assertEqual("guest", g.role_of(busy, path=self.tmp, now=now + 60))
        # هر بررسی، عمر نشست را تازه می‌کند: از لحظهٔ آخرین کار می‌شماریم، نه از لحظهٔ ورود
        self.assertIsNone(g.role_of(busy, path=self.tmp, now=now + 60 + g.TTL_SECONDS + 1))

    def test_five_failures_lock_the_ip(self):
        self._open_gate()
        for i in range(panel.FAIL_LIMIT):
            g.login("masoud", f"غلط-{i}", ip="9.9.9.9", path=self.tmp)
        locked = g.login(*GUEST, ip="9.9.9.9", path=self.tmp)
        self.assertFalse(locked["ok"])
        self.assertTrue(locked.get("rate_limited"))
        self.assertTrue(g.login(*GUEST, ip="8.8.8.8", path=self.tmp)["ok"])   # نشانی دیگر باز است

    def test_sync_admin_takes_panel_credentials(self):
        panel_file = Path(tempfile.mkdtemp()) / "admin.json"
        panel.set_credentials("mafhoom", ADMIN[1], path=panel_file)
        acc = g.sync_admin_from_panel(panel_file, path=self.tmp)
        self.assertEqual("mafhoom", acc["id"])
        g.set_enabled(True, path=self.tmp)
        self.assertTrue(g.login("mafhoom", ADMIN[1], ip="1.1.1.9", path=self.tmp)["ok"])

    def test_status_has_no_secrets(self):
        self._open_gate()
        blob = json.dumps(g.status(self.tmp), ensure_ascii=False)
        for secret in (GUEST[1], ADMIN[1], "hash", "salt"):
            self.assertNotIn(secret, blob)
        self.assertIn("masoud", blob)                          # شناسه اشکالی ندارد
        self.assertTrue(g.status(self.tmp)["accounts"]["guest"]["enabled"])

    def test_gate_toggle_on_off(self):
        self._open_gate()
        self.assertTrue(g.enabled(self.tmp))
        g.set_enabled(False, path=self.tmp)
        self.assertFalse(g.enabled(self.tmp))
        self.assertEqual("admin", g.role_of(None, path=self.tmp))   # بازگشت به اعتماد محلی
        out = g.login(*GUEST, ip="1.1.2.1", path=self.tmp)
        self.assertFalse(out["ok"])
        self.assertTrue(out.get("gate_off"))


class TestGateCli(GateBase):
    def _run(self, *args):
        return subprocess.run([sys.executable, str(BASE / "gate.py"), "--config", str(self.tmp),
                               *args], capture_output=True, text=True, timeout=120)

    def test_cli_full_cycle(self):
        self.assertEqual(0, self._run("--admin-id", ADMIN[0], "--admin-pass", ADMIN[1]).returncode)
        r = self._run("--guest-id", GUEST[0], "--guest-pass", GUEST[1])
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("مهمان", r.stdout)
        self.assertEqual(0, self._run("--on").returncode)
        self.assertEqual(0, self._run("--check", *GUEST).returncode)
        self.assertEqual(1, self._run("--check", "masoud", "غلط").returncode)
        self.assertEqual(0, self._run("--guest-off").returncode)
        self.assertEqual(1, self._run("--check", *GUEST).returncode)
        r2 = self._run("--status")
        self.assertIn("قطع‌شده", r2.stdout)
        self.assertEqual(0, self._run("--off").returncode)
        self.assertFalse(g.enabled(self.tmp))

    def test_cli_rejects_short_password(self):
        r = self._run("--guest-id", "masoud", "--guest-pass", "123")
        self.assertEqual(2, r.returncode)
        self.assertIn("خطا", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestGuestGuard(unittest.TestCase):
    """نگهبانی مسیرها: مهمان/کارفرما برنامه را می‌بیند، ولی کلیدهای خطرناک دستش نیست."""

    BLOCKED = ("/admin", "/admin/", "/api/admin/health", "/api/license", "/api/shutdown",
               "/api/gate/update")
    OPEN = ("/", "/index.html", "/login", "/api/gate/status", "/api/signals", "/files/offer",
            "/api/health", "/api/diagnose", "/api/usage", "/files/usage")

    def test_importable(self):
        import web_server  # noqa: F401
        self.assertTrue(hasattr(web_server.Handler, "_guest_blocked"))

    def test_guest_is_blocked_from_the_dangerous_doors(self):
        import web_server
        for path in self.BLOCKED:
            self.assertTrue(web_server.Handler._guest_blocked(path), path)

    def test_guest_can_see_the_program(self):
        import web_server
        for path in self.OPEN:
            self.assertFalse(web_server.Handler._guest_blocked(path), path)

    def test_shutdown_needs_the_word_confirm(self):
        """مسیر خاموشی، بدون «confirm» فقط دست مدیر را می‌خواند (بدون تأیید، خطا می‌دهد)."""
        import inspect
        import web_server
        # مسیرها در `_do_post` هستند و `do_POST` فقط نگهبان خطاست؛ هر دو را می‌خوانیم.
        src = inspect.getsource(web_server.Handler._do_post)
        self.assertIn('u.path == "/api/shutdown"', src)
        self.assertIn('self._role() != "admin"', src)
        self.assertIn('"confirm"', src)
        self.assertIn('"dry"', src)
