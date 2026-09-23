#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون‌های پنل مدیریت: هش رمز، توکن، انقضا، محدودیت تلاش، و متغیر محیطی.

هیچ آزمونی پروندهٔ واقعی `config/admin.json` را دست نمی‌زند؛ همه در پوشهٔ موقتی کار می‌کنند.
"""

import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

BASE = pathlib.Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import adminauth as aa  # noqa: E402

# رمز آزمونی: از محیط می‌آید یا هر بار ساخته می‌شود. هیچ رمز واقعی در این پرونده نیست،
# چون این پرونده در بسته‌های تحویلی هم می‌رود و نمی‌شود رمز واقعی کسی را با خودش برد.
ADMIN_PASS = os.environ.get("STATION_TEST_ADMIN_PASS") or "Test-Admin-" + __import__("secrets").token_hex(4)


class Credentials(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = pathlib.Path(self.tmp.name) / "admin.json"
        os.environ.pop("STATION_ADMIN_ID", None)
        os.environ.pop("STATION_ADMIN_PASS", None)

    def tearDown(self):
        self.tmp.cleanup()

    def test_password_is_never_stored_in_plain_text(self):
        aa.set_credentials("mafhoom", ADMIN_PASS, path=self.cfg)
        raw = self.cfg.read_text(encoding="utf-8")
        self.assertNotIn(ADMIN_PASS, raw)
        self.assertIn("hash", json.loads(raw))

    def test_correct_pair_passes_and_wrong_pair_fails(self):
        aa.set_credentials("mafhoom", ADMIN_PASS, path=self.cfg)
        self.assertTrue(aa.verify_credentials("mafhoom", ADMIN_PASS, path=self.cfg))
        self.assertFalse(aa.verify_credentials("mafhoom", "غلط", path=self.cfg))
        self.assertFalse(aa.verify_credentials("دیگری", ADMIN_PASS, path=self.cfg))

    def test_short_password_is_refused(self):
        with self.assertRaises(ValueError):
            aa.set_credentials("mafhoom", "123", path=self.cfg)
        self.assertFalse(self.cfg.exists())

    def test_env_pair_overrides_file(self):
        aa.set_credentials("mafhoom", ADMIN_PASS, path=self.cfg)
        with mock.patch.dict(os.environ, {"STATION_ADMIN_ID": "بهرام",
                                          "STATION_ADMIN_PASS": "P@ssw0rdX"}):
            self.assertTrue(aa.verify_credentials("بهرام", "P@ssw0rdX", path=self.cfg))
            self.assertFalse(aa.verify_credentials("mafhoom", ADMIN_PASS, path=self.cfg))

    def test_missing_config_is_not_configured(self):
        self.assertFalse(aa.is_configured(self.cfg))
        self.assertFalse(aa.verify_credentials("mafhoom", ADMIN_PASS, path=self.cfg))
        out = aa.login("mafhoom", ADMIN_PASS, path=self.cfg)
        self.assertFalse(out["ok"])
        self.assertIn("شناسه و رمز پنل", out["error"])


class Tokens(unittest.TestCase):
    def setUp(self):
        aa.SESSIONS.clear()
        aa.FAILS.clear()

    def test_token_lifecycle_and_sliding_expiry(self):
        tok = aa.issue_token("mafhoom", now=1000.0)
        self.assertTrue(aa.check_token(tok, now=1000.0))
        self.assertTrue(aa.check_token(tok, now=1000.0 + aa.TOKEN_TTL_SECONDS - 1))
        self.assertFalse(aa.check_token(tok, now=1000.0 + 2 * aa.TOKEN_TTL_SECONDS))
        self.assertFalse(aa.check_token("چیزنامعتبر"))
        self.assertFalse(aa.check_token(None))

    def test_revoke_and_unknown_token(self):
        tok = aa.issue_token("mafhoom")
        self.assertTrue(aa.revoke_token(tok))
        self.assertFalse(aa.check_token(tok))
        self.assertFalse(aa.revoke_token("نبود"))


class RateLimit(unittest.TestCase):
    def setUp(self):
        aa.SESSIONS.clear()
        aa.FAILS.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = pathlib.Path(self.tmp.name) / "admin.json"
        aa.set_credentials("mafhoom", ADMIN_PASS, path=self.cfg)

    def tearDown(self):
        self.tmp.cleanup()

    def test_five_wrong_tries_lock_the_window(self):
        for i in range(aa.FAIL_LIMIT):
            out = aa.login("mafhoom", "غلط", ip="1.2.3.4", path=self.cfg, now=1000.0)
            self.assertFalse(out["ok"])
        locked = aa.login("mafhoom", ADMIN_PASS, ip="1.2.3.4", path=self.cfg, now=1000.0)
        self.assertTrue(locked.get("rate_limited"))
        later = aa.login("mafhoom", ADMIN_PASS, ip="1.2.3.4", path=self.cfg,
                         now=1000.0 + aa.FAIL_WINDOW_SECONDS + 1)
        self.assertTrue(later["ok"], "بعد از پنجرهٔ قفل باید دوباره باز شود")
        self.assertTrue(later["token"])

    def test_successful_login_clears_failures(self):
        aa.login("mafhoom", "غلط", ip="9.9.9.9", path=self.cfg)
        aa.login("mafhoom", ADMIN_PASS, ip="9.9.9.9", path=self.cfg)
        self.assertFalse(aa.rate_limited("9.9.9.9"))

    def test_session_counter(self):
        aa.login("mafhoom", ADMIN_PASS, ip="7.7.7.7", path=self.cfg)
        self.assertEqual(aa.active_tokens(), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
