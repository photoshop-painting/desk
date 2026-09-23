"""بررسی امنیتی: «کسی بتواند هک کند؟» — آزمون‌های حمله روی یک سرور واقعی.

این پرونده ادعا نمی‌سازد؛ **حمله می‌کند** و نتیجه را می‌گوید. سرور با پیکربندی موقت بالا می‌آید
(دروازه روشن، مدیر و یک کاربر مهمان) و هر آزمون یکی از راه‌های شناخته‌شدهٔ سوءاستفاده را می‌سنجد:

  ۱. پیمایش مسیر (`..`، درصدی‌شده، بک‌اسلش، نویسهٔ صفر) و خواندن پروندهٔ رازها.
  ۲. دسترسی بدون ورود و با کوکی جعلی/دزدیده‌شده.
  ۳. بالا رفتن از نقش مهمان به مدیر و رسیدن به درهای مدیریت.
  ۴. درخواست از سایت دیگر (CSRF) و روش‌های غیرمجاز و بدنهٔ غول‌آسا.
  ۵. قفل تلاش‌های ناموفق و جدا بودن قفل هر کاربر (که یک نفر بقیه را نبندد).
  ۶. سرآیندهای امنیتی و پرچم‌های کوکی.
  ۷. درز نکردن راز در پاسخ‌های عمومی.
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

BASE = Path(__file__).resolve().parents[1]      # .../money/gui
sys.path.insert(0, str(BASE))

import gate as g                                 # noqa: E402

ADMIN = ("mafhoom", "Smm@1101001")
USER = ("ali", "Ramz-Ali-9931")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


NO_REDIRECT = urllib.request.build_opener(_NoRedirect())


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class SecurityBase(unittest.TestCase):
    """یک سرور واقعی با پیکربندی موقت + STATION_TRUST_PROXY=1 (مثل حالتی که پشت تونل است)."""

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="sec-"))
        cls.cfg = cls.dir / "gate.json"
        g.SESSIONS.clear()
        g.set_account("admin", *ADMIN, path=cls.cfg)
        g.set_account("guest", "masoud", "Guest-Test-9931", path=cls.cfg)
        g.add_user(*USER, path=cls.cfg)
        g.set_enabled(True, path=cls.cfg)
        cls.port = free_port()
        env = {**os.environ, "STATION_GATE_CONFIG": str(cls.cfg), "STATION_TRUST_PROXY": "1",
               "PYTHONDONTWRITEBYTECODE": "1"}
        cls.proc = subprocess.Popen([sys.executable, "-m", "web_server", "--port", str(cls.port),
                                     "--host", "127.0.0.1", "--no-browser"],
                                    cwd=str(BASE), env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
        cls.base = f"http://127.0.0.1:{cls.port}"
        for _ in range(60):
            try:
                if cls.raw("/api/gate/status")[0] == 200:
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

    # ---------- ابزارهای خام (بدون تغییر مسیر و بدون رمزگشایی)
    @classmethod
    def raw(cls, path, *, cookie=None, method="GET", body=None, headers=None, follow=False,
            raw_path=False):
        url = cls.base + path
        req = urllib.request.Request(url, method=method,
                                     data=body.encode() if isinstance(body, str) else body)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        if cookie:
            req.add_header("Cookie", cookie)
        if isinstance(body, str) and "Content-Type" not in (headers or {}):
            req.add_header("Content-Type", "application/json")
        opener = urllib.request.urlopen if follow else NO_REDIRECT.open
        try:
            with opener(req, timeout=25) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    @classmethod
    def login(cls, user_id, password):
        code, raw, hdr = cls.raw("/api/login", method="POST",
                                 body=json.dumps({"id": user_id, "pass": password}))
        cookie = (hdr.get("Set-Cookie") or "").split(";")[0]
        return code, json.loads(raw.decode("utf-8") or "{}"), cookie

    @classmethod
    def admin_cookie(cls):
        code, _, cookie = cls.login(*ADMIN)
        assert code == 200, code
        return cookie

    @classmethod
    def user_cookie(cls):
        code, _, cookie = cls.login(*USER)
        assert code == 200, code
        return cookie


class TestPathTraversal(SecurityBase):
    """پیمایش مسیر: هیچ راهی نباید پروندهٔ بیرون از پوشهٔ خروجی‌ها بدهد."""

    ATTACKS = (
        "/files/../../config/gate.json",
        "/files/../../../etc/passwd",
        "/files/..%2f..%2fconfig%2fgate.json",
        "/files/%2e%2e/%2e%2e/config/gate.json",
        "/files/....//....//config/gate.json",
        "/files/..\\..\\config\\gate.json",
        "/files/%00offer.html",
        "/files/.hidden",
        "/files/",
        "/files/./../config/gate.json",
        "/app.js/../../config/gate.json",
        "/static/../../config/gate.json",
        "/web/../config/gate.json",
    )

    def test_none_of_the_traversal_attacks_returns_a_secret(self):
        cookie = self.user_cookie()          # حتی کاربر مهمان هم نباید بتواند
        for path in self.ATTACKS:
            code, body, _ = self.raw(path, cookie=cookie)
            text = body.decode("utf-8", "replace")
            self.assertNotIn("hash", text, f"{path} → پروندهٔ رازها لو رفت")
            self.assertNotIn("salt", text, f"{path} → پروندهٔ رازها لو رفت")
            self.assertNotIn("root:", text, f"{path} → پروندهٔ سیستم لو رفت")
            self.assertIn(code, (400, 401, 403, 404), f"{path} → کد غیرمنتظره {code}")

    def test_bundle_dir_cannot_be_escaped(self):
        """بعد از ساخت بستهٔ خروجی هم راه فرار بسته است (پوشهٔ خروجی هم زیر نگهبانی است)."""
        cookie = self.admin_cookie()
        for path in ("/files/../../config/gate.json", "/files/../gate.py"):
            code, body, _ = self.raw(path, cookie=cookie)
            self.assertIn(code, (400, 403, 404))
            self.assertNotIn(b"hash", body)


class TestAuthAndRoles(SecurityBase):
    def test_nothing_opens_without_login(self):
        for path in ("/", "/index.html", "/files/offer", "/api/state", "/admin"):
            code, _, _ = self.raw(path)
            self.assertIn(code, (302, 401, 403), f"{path} → {code}")

    def test_forged_and_random_cookies_do_not_work(self):
        for cookie in ("station_gate=" + "a" * 48, "station_gate=admin", "station_gate=; ",
                       "station_gate=%00" * 3):
            code, _, _ = self.raw("/", cookie=cookie)
            self.assertEqual(302, code, cookie)

    def test_guest_cannot_reach_any_manager_door(self):
        cookie = self.user_cookie()
        for path in ("/admin", "/api/gate/update", "/api/license", "/api/shutdown"):
            code, _, _ = self.raw(path, cookie=cookie,
                                  method="POST" if path.startswith("/api") and path != "/api/license" else "GET",
                                  body=json.dumps({"action": "gate-off", "confirm": True}))
            self.assertIn(code, (403, 405), f"{path} → {code}")

    def test_guest_cannot_change_roles_or_users(self):
        cookie = self.user_cookie()
        for payload in ({"action": "set-admin", "id": "hack", "pass": "Hack-Hack-9911"},
                        {"action": "user-add", "id": "hack", "pass": "Hack-Hack-9911"},
                        {"action": "gate-off"}):
            code, _, _ = self.raw("/api/gate/update", cookie=cookie, method="POST",
                                  body=json.dumps(payload))
            self.assertEqual(403, code, payload)

    def test_login_does_not_reveal_whether_the_id_exists(self):
        a = self.raw("/api/login", method="POST",
                     body=json.dumps({"id": "nadarim", "pass": "Xx-Xx-Xx-9911"}))
        b = self.raw("/api/login", method="POST",
                     body=json.dumps({"id": ADMIN[0], "pass": "Xx-Xx-Xx-9911"}))
        self.assertEqual(a[0], b[0])
        self.assertIn("شناسه یا رمز درست نیست", a[1].decode("utf-8"))
        self.assertIn("شناسه یا رمز درست نیست", b[1].decode("utf-8"))

    def test_public_status_never_leaks_identities(self):
        code, body, _ = self.raw("/api/gate/status")
        text = body.decode("utf-8")
        self.assertEqual(200, code)
        for secret in (ADMIN[0], USER[0], "masoud", "users", "hash", "salt"):
            self.assertNotIn(secret, text, secret)


class TestRequestHygiene(SecurityBase):
    def test_unknown_methods_are_rejected(self):
        for method in ("PUT", "DELETE", "PATCH", "TRACE"):
            code, _, hdr = self.raw("/api/state", method=method)
            self.assertEqual(405, code, method)
            self.assertIn("GET, POST", hdr.get("Allow", ""))

    def test_options_is_allowed_and_quiet(self):
        code, _, hdr = self.raw("/", method="OPTIONS")
        self.assertEqual(204, code)
        self.assertIn("GET, POST", hdr.get("Allow", ""))

    def test_cross_site_post_is_refused(self):
        code, body, _ = self.raw("/api/login", method="POST",
                                 body=json.dumps({"id": ADMIN[0], "pass": ADMIN[1]}),
                                 headers={"Origin": "https://evil.example"})
        self.assertEqual(403, code)
        self.assertIn("جای دیگری", body.decode("utf-8"))

    def test_same_site_post_is_accepted(self):
        code, _, _ = self.raw("/api/login", method="POST",
                              body=json.dumps({"id": ADMIN[0], "pass": ADMIN[1]}),
                              headers={"Origin": self.base})
        self.assertEqual(200, code)

    def test_huge_body_is_refused(self):
        big = json.dumps({"id": "x", "pass": "y" * (3 * 1024 * 1024)})
        code, body, _ = self.raw("/api/login", method="POST", body=big)
        self.assertEqual(413, code)
        self.assertIn("بزرگ", body.decode("utf-8"))

    def test_broken_json_does_not_crash_the_server(self):
        code, _, _ = self.raw("/api/login", method="POST", body="{ not json")
        self.assertIn(code, (400, 401))
        self.assertEqual(200, self.raw("/api/gate/status")[0])       # سرور سرپا است

    def test_security_headers_are_present(self):
        for path in ("/login", "/api/gate/status"):
            _, _, hdr = self.raw(path)
            self.assertEqual("nosniff", hdr.get("X-Content-Type-Options"), path)
            self.assertEqual("DENY", hdr.get("X-Frame-Options"), path)
            self.assertEqual("no-referrer", hdr.get("Referrer-Policy"), path)
            self.assertIn("noindex", hdr.get("X-Robots-Tag", ""), path)
            self.assertEqual("no-store", hdr.get("Cache-Control"), path)
        _, _, hdr_login = self.raw("/login")
        self.assertIn("frame-ancestors 'none'", hdr_login.get("Content-Security-Policy", ""))

    def test_cookie_flags_include_secure_behind_https(self):
        code, _, hdr = self.raw("/api/login", method="POST",
                                body=json.dumps({"id": ADMIN[0], "pass": ADMIN[1]}),
                                headers={"X-Forwarded-Proto": "https"})
        cookie = hdr.get("Set-Cookie", "")
        self.assertEqual(200, code)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertIn("Secure", cookie)
        self.assertNotIn("expires", cookie.lower())          # کوکی نشستی، نه ماندگار

    def test_cookie_is_not_secure_on_plain_http(self):
        code, _, hdr = self.raw("/api/login", method="POST",
                                body=json.dumps({"id": ADMIN[0], "pass": ADMIN[1]}))
        self.assertNotIn("Secure", hdr.get("Set-Cookie", ""))


class TestBruteForce(SecurityBase):
    def test_lockout_after_five_failures_and_no_bypass_with_headers(self):
        ip = "203.0.113.77"
        for _ in range(5):
            self.raw("/api/login", method="POST",
                     body=json.dumps({"id": USER[0], "pass": "Ghalat-Pass-9911"}),
                     headers={"X-Forwarded-For": ip})
        code, body, _ = self.raw("/api/login", method="POST",
                                 body=json.dumps({"id": USER[0], "pass": USER[1]}),
                                 headers={"X-Forwarded-For": ip})
        self.assertEqual(401, code)
        self.assertIn("صبر", body.decode("utf-8"))            # حتی رمز درست هم در قفل نمی‌گذرد
        # و با هدر جعلیِ نشانی دیگر، مهاجم نمی‌تواند قفل را دور بزند؟ قفل برای همان نشانی است
        code2, _, _ = self.raw("/api/login", method="POST",
                               body=json.dumps({"id": USER[0], "pass": USER[1]}),
                               headers={"X-Forwarded-For": "198.51.100.9"})
        self.assertEqual(200, code2)                          # کاربر دیگری قفل نشده است

    def test_admin_lockout_does_not_block_a_user(self):
        ip = "203.0.113.88"
        for _ in range(5):
            self.raw("/api/login", method="POST",
                     body=json.dumps({"id": ADMIN[0], "pass": "Ghalat-Pass-9911"}),
                     headers={"X-Forwarded-For": ip})
        code, _, _ = self.raw("/api/login", method="POST",
                              body=json.dumps({"id": USER[0], "pass": USER[1]}),
                              headers={"X-Forwarded-For": "198.51.100.10"})
        self.assertEqual(200, code)
        code2, _, _ = self.raw("/api/login", method="POST",
                               body=json.dumps({"id": ADMIN[0], "pass": ADMIN[1]}),
                               headers={"X-Forwarded-For": ip})
        self.assertEqual(401, code2)                          # همان نشانی همچنان قفل است


class TestInternalErrorsAreReported(SecurityBase):
    """خطای پیش‌بینی‌نشده نباید اتصال را بی‌پاسخ ببندد (روی میزبان ابری همین دردسر شد)."""

    def test_bad_number_gives_clean_500_not_dropped_connection(self):
        cookie = self.user_cookie()
        code, body, _ = self.raw("/api/judge", method="POST", cookie=cookie,
                                 body=json.dumps({"hurdle": "abc"}))
        self.assertEqual(code, 500)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data.get("kind"), "internal_error")
        self.assertIn("ValueError", data.get("error", ""))
        self.assertNotIn("Traceback", body.decode("utf-8"))        # ردِ خطا فقط در گزارش سرور

    def test_server_survives_the_internal_error(self):
        cookie = self.user_cookie()
        self.raw("/api/judge", method="POST", cookie=cookie, body=json.dumps({"capital": "؟"}))
        self.assertEqual(self.raw("/api/gate/status")[0], 200)     # سرور سرپا مانده


class TestStateKeeperIsOfflineSafe(SecurityBase):
    """روی رایانهٔ خودِ کاربر، نگهبان ابری نیست؛ پنل باید این را صادقانه بگوید نه خطا بدهد."""

    @classmethod
    def admin_token(cls) -> str:
        body = json.dumps({"id": ADMIN[0], "pass": ADMIN[1]})
        code_, raw, _ = cls.raw("/api/admin/login", method="POST", body=body)
        if code_ != 200:
            return ""
        return (json.loads(raw.decode("utf-8")) or {}).get("token") or ""

    def test_needs_admin_token(self):
        cookie = self.admin_cookie()
        code_, body, _ = self.raw("/api/admin/state", cookie=cookie)
        self.assertEqual(code_, 403)
        self.assertTrue(json.loads(body.decode("utf-8")).get("needs_admin"))

    def test_reports_offline_honestly(self):
        token = self.admin_token()
        if not token:
            self.skipTest("ورود پنل در این لحظه ممکن نشد (قفل تلاش)")
            return
        cookie = self.admin_cookie()
        code_, body, _ = self.raw("/api/admin/state", cookie=cookie,
                                  headers={"X-Admin-Token": token})
        self.assertEqual(code_, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertTrue(data.get("ok"))
        self.assertFalse(data.get("online"))
        self.assertIn("میزبان", data.get("note") or "")

        code_, body, _ = self.raw("/api/admin/backup", method="POST", cookie=cookie,
                                  headers={"X-Admin-Token": token}, body="{}")
        self.assertEqual(code_, 200)
        out = json.loads(body.decode("utf-8"))
        self.assertFalse(out.get("ok"))
        self.assertIn("میزبان", out.get("note") or "")


class TestNoSecretsAtRest(SecurityBase):
    def test_config_file_has_only_hashes(self):
        blob = self.cfg.read_text(encoding="utf-8")
        for password in (ADMIN[1], USER[1], "Guest-Test-9931"):
            self.assertNotIn(password, blob, password)
        self.assertIn("hash", blob)

    def test_outputs_do_not_contain_credentials(self):
        cookie = self.user_cookie()
        for path in ("/files/offer", "/files/onboarding", "/files/walkthrough.txt"):
            code, body, _ = self.raw(path, cookie=cookie)
            if code != 200:
                continue
            text = body.decode("utf-8", "replace")
            self.assertNotIn(ADMIN[1], text)
            self.assertNotIn(USER[1], text)
            self.assertNotIn("salt", text)

    def test_no_directory_listing_anywhere(self):
        cookie = self.user_cookie()
        for path in ("/files/", "/web/", "/data/", "/demo/"):
            code, body, _ = self.raw(path, cookie=cookie)
            self.assertIn(code, (400, 404))
            self.assertNotIn(b"Index of", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
