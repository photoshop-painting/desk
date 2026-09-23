"""کاربران مهمان (چند نفر) — «شناسه/رمز را خودم می‌سازم و هر وقت خواستم حذف می‌کنم».

چرا این آزمون‌ها هست: کاربر می‌خواهد برای کارفرما و همکارانش خودش شناسه/رمز بسازد و هر لحظه
پس بگیرد. پس باید ثابت شود که:

  ۱. ساخت/حذف/قطع کاربر با کد کار می‌کند و رمز فقط هش می‌شود.
  ۲. حذف کاربر، **همان لحظه** نشست بازش را می‌بندد (نه با ری‌استارت).
  ۳. کاربرِ مهمان به کارهای مدیر (پنل، مجوز، خاموشی، مدیریت کاربران) نمی‌رسد.
  ۴. بیرون از ورود، هیچ شناسه‌ای از سامانه درز نمی‌کند (وضعیتِ کم‌اطلاع).

بخش دوم آزمون، یک سرور **واقعی** روی پیکربندی موقت بالا می‌آورد و همین چرخه را از HTTP می‌سنجد.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]      # .../money/gui
sys.path.insert(0, str(BASE))

import gate as g                                 # noqa: E402

ADMIN = ("mafhoom", "Smm@1101001")
GUEST = ("masoud", "Guest-Test-9931")
USER = ("ali", "Ramz-Ali-9931")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """برای دیدن خودِ ۳۰۲ (وگرنه urllib خودش دنبال ریدایرکت می‌رود و ۲۰۰ می‌دهد)."""

    def redirect_request(self, *args, **kwargs):
        return None


NO_REDIRECT = urllib.request.build_opener(_NoRedirect())


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class UsersBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gate-users-")) / "gate.json"
        g.SESSIONS.clear()
        g.set_account("admin", *ADMIN, path=self.tmp)
        self._open_gate()

    def tearDown(self):
        g.SESSIONS.clear()

    def _open_gate(self):
        g.set_enabled(True, path=self.tmp)


class TestUserCrud(UsersBase):
    def test_add_user_and_login(self):
        u = g.add_user(*USER, note="کارشناس شرکت", path=self.tmp)
        self.assertEqual("ali", u["id"])
        out = g.login(*USER, ip="10.0.0.1", path=self.tmp)
        self.assertTrue(out["ok"], out)
        self.assertEqual("guest", out["role"])
        self.assertEqual("ali", out["id"])

    def test_password_is_hashed_only(self):
        g.add_user(*USER, path=self.tmp)
        blob = self.tmp.read_text(encoding="utf-8")
        self.assertNotIn(USER[1], blob)
        self.assertIn("hash", blob)
        self.assertTrue(g.status(self.tmp)["users"][0]["id"] == "ali")
        self.assertNotIn("hash", json.dumps(g.status(self.tmp), ensure_ascii=False))

    def test_short_password_rejected(self):
        with self.assertRaises(ValueError):
            g.add_user("ali", "123", path=self.tmp)

    def test_admin_id_cannot_be_used_as_a_user(self):
        with self.assertRaises(ValueError):
            g.add_user(ADMIN[0], "Ramz-Khaili-9911", path=self.tmp)

    def test_duplicate_user_rejected(self):
        g.add_user(*USER, path=self.tmp)
        with self.assertRaises(ValueError):
            g.add_user(*USER, path=self.tmp)

    def test_delete_user_also_closes_his_live_session(self):
        g.add_user(*USER, path=self.tmp)
        out = g.login(*USER, ip="10.0.0.2", path=self.tmp)
        self.assertEqual("guest", g.role_of(out["token"], path=self.tmp))
        res = g.delete_user("ali", path=self.tmp)
        self.assertEqual(1, res["closed"])
        self.assertIsNone(g.role_of(out["token"], path=self.tmp))       # همان لحظه بیرون
        self.assertFalse(g.login(*USER, ip="10.0.0.3", path=self.tmp)["ok"])
        self.assertEqual([], g.users(self.tmp))

    def test_disable_then_enable(self):
        g.add_user(*USER, path=self.tmp)
        out = g.login(*USER, ip="10.0.0.4", path=self.tmp)
        g.set_user_enabled("ali", False, path=self.tmp)
        self.assertIsNone(g.role_of(out["token"], path=self.tmp))       # قطع = بستن نشست
        self.assertFalse(g.login(*USER, ip="10.0.0.5", path=self.tmp)["ok"])
        g.set_user_enabled("ali", True, path=self.tmp)
        self.assertTrue(g.login(*USER, ip="10.0.0.6", path=self.tmp)["ok"])

    def test_delete_unknown_user_is_a_clear_error(self):
        with self.assertRaises(ValueError):
            g.delete_user("nadarim", path=self.tmp)

    def test_legacy_guest_account_still_works(self):
        g.set_account("guest", *GUEST, path=self.tmp)
        out = g.login(*GUEST, ip="10.0.0.7", path=self.tmp)
        self.assertTrue(out["ok"])
        self.assertEqual("guest", out["role"])

    def test_users_do_not_see_each_other(self):
        g.add_user(*USER, path=self.tmp)
        g.add_user("reza", "Ramz-Reza-9932", path=self.tmp)
        self.assertEqual({"ali", "reza"}, {u["id"] for u in g.users(self.tmp)})
        g.delete_user("ali", path=self.tmp)
        self.assertEqual(["reza"], [u["id"] for u in g.users(self.tmp)])


class TestUserCli(UsersBase):
    def _run(self, *args):
        return subprocess.run([sys.executable, str(BASE / "gate.py"), "--config", str(self.tmp), *args],
                              capture_output=True, text=True, timeout=120)

    def test_cli_add_list_del(self):
        r = self._run("--user-add", *USER, "--user-note", "کارشناس شرکت")
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("ali", r.stdout)
        r2 = self._run("--users")
        self.assertIn("ali", r2.stdout)
        self.assertIn("کارشناس شرکت", r2.stdout)
        self.assertEqual(0, self._run("--user-off", "ali").returncode)
        self.assertEqual(1, self._run("--check", *USER).returncode)     # قطع‌شده = ورود نه
        self.assertEqual(0, self._run("--user-on", "ali").returncode)
        self.assertEqual(0, self._run("--check", *USER).returncode)
        r3 = self._run("--user-del", "ali")
        self.assertEqual(0, r3.returncode, r3.stderr)
        self.assertIn("حذف", r3.stdout)
        self.assertEqual([], g.users(self.tmp))

    def test_cli_status_shows_users(self):
        self._run("--user-add", *USER)
        r = self._run("--status")
        self.assertIn("کاربران مهمان", r.stdout)
        self.assertIn("ali", r.stdout)


class TestUsersOverHttp(unittest.TestCase):
    """چرخهٔ کامل از HTTP: بیرون از ورود حداقل اطلاعات، مدیر کاربر می‌سازد، کاربر وارد می‌شود، حذف می‌شود."""

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="gate-http-"))
        cls.cfg = cls.dir / "gate.json"
        g.SESSIONS.clear()
        g.set_account("admin", *ADMIN, path=cls.cfg)
        g.set_enabled(True, path=cls.cfg)
        cls.port = free_port()
        env = {**dict(__import__("os").environ), "STATION_GATE_CONFIG": str(cls.cfg),
               "PYTHONDONTWRITEBYTECODE": "1"}
        cls.proc = subprocess.Popen(
            [sys.executable, "-m", "web_server", "--port", str(cls.port),
             "--host", "127.0.0.1", "--no-browser"],
            cwd=str(BASE), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        cls.base = f"http://127.0.0.1:{cls.port}"
        for _ in range(60):
            try:
                if cls._get("/api/gate/status")[0] == 200:
                    break
            except Exception:
                pass
            time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
        g.SESSIONS.clear()

    # ---------- ابزارها
    @classmethod
    def _get(cls, path, cookie=None, *, follow=False):
        req = urllib.request.Request(cls.base + path)
        if cookie:
            req.add_header("Cookie", cookie)
        opener = urllib.request.urlopen if follow else NO_REDIRECT.open
        try:
            with opener(req, timeout=20) as r:
                return r.status, r.read().decode("utf-8", "replace"), r.headers.get("Set-Cookie", "")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), e.headers.get("Set-Cookie", "")

    @classmethod
    def _post(cls, path, body, cookie=None):
        req = urllib.request.Request(cls.base + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        if cookie:
            req.add_header("Cookie", cookie)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read().decode("utf-8") or "{}"), r.headers.get("Set-Cookie", "")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                return e.code, json.loads(raw or "{}"), ""
            except json.JSONDecodeError:
                return e.code, {"raw": raw}, ""

    def _login(self, user_id, password):
        code, body, setcookie = self._post("/api/login", {"id": user_id, "pass": password})
        cookie = setcookie.split(";")[0] if setcookie else ""
        return code, body, cookie

    # ---------- آزمون‌ها
    def test_01_logged_out_status_hides_every_identity(self):
        code, raw, _ = self._get("/api/gate/status")
        self.assertEqual(200, code)
        self.assertNotIn(ADMIN[0], raw)          # شناسهٔ مدیر درز نمی‌کند
        self.assertNotIn("users", raw)
        payload = json.loads(raw)
        self.assertTrue(payload["enabled"])
        self.assertFalse(payload["logged_in"])

    def test_02_admin_login_then_sees_the_user_list(self):
        code, body, cookie = self._login(*ADMIN)
        self.assertEqual(200, code, body)
        self.assertEqual("admin", body["role"])
        code2, raw, _ = self._get("/api/gate/status", cookie=cookie)
        self.assertEqual(200, code2)
        self.assertIn("users", json.loads(raw))
        self.__class__.admin_cookie = cookie

    def test_03_admin_creates_a_user_and_that_user_logs_in(self):
        code, body, _ = self._post("/api/gate/update",
                                   {"action": "user-add", "id": USER[0], "pass": USER[1],
                                    "note": "کارشناس شرکت"}, cookie=self.admin_cookie)
        self.assertEqual(200, code, body)
        self.assertEqual([USER[0]], [u["id"] for u in body["users"]])
        code2, login, ucookie = self._login(*USER)
        self.assertEqual(200, code2, login)
        self.assertEqual("guest", login["role"])
        self.__class__.user_cookie = ucookie
        self.assertEqual(200, self._get("/", cookie=ucookie)[0])

    def test_04_guest_cannot_touch_admin_doors(self):
        code, _, _ = self._get("/admin", cookie=self.user_cookie)
        self.assertEqual(403, code)
        code2, _, _ = self._post("/api/gate/update", {"action": "user-add", "id": "hack",
                                                      "pass": "Hack-Hack-9911"},
                                 cookie=self.user_cookie)
        self.assertEqual(403, code2)
        code3, _, _ = self._post("/api/shutdown", {"confirm": True}, cookie=self.user_cookie)
        self.assertEqual(403, code3)

    def test_05_delete_kills_the_live_session_at_once(self):
        code, body, _ = self._post("/api/gate/update", {"action": "user-del", "id": USER[0]},
                                   cookie=self.admin_cookie)
        self.assertEqual(200, code, body)
        self.assertEqual([], body["users"])
        self.assertIn("حذف", body["note"])
        code2, _, _ = self._get("/", cookie=self.user_cookie)      # نشستش مرده است
        self.assertEqual(302, code2)
        self.assertEqual(401, self._get("/api/state", cookie=self.user_cookie)[0])
        code3, login, _ = self._login(*USER)
        self.assertEqual(401, code3, login)

    def test_06_admin_password_can_be_changed_from_the_panel_path(self):
        code, body, _ = self._post("/api/gate/update",
                                   {"action": "set-admin", "id": "masoud2", "pass": "Ramz-Modir-9955"},
                                   cookie=self.admin_cookie)
        self.assertEqual(200, code, body)
        self.assertEqual("masoud2", body["admin"]["id"])
        code2, login, _ = self._login("masoud2", "Ramz-Modir-9955")
        self.assertEqual(200, code2, login)
        self.assertEqual("admin", login["role"])
        self.assertEqual(302, self._get("/")[0])          # بدون کوکی، هیچ صفحه‌ای نمی‌آید
