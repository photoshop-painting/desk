#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون دفتر اتصال‌ها و کاوشگر پاسخ سرویس."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import connections as conn  # noqa: E402
import datafeed  # noqa: E402


class ConnectionStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self._old_cfg, self._old_keys = conn.CONFIG_DIR, conn.KEYS_FILE
        self._old_profiles = conn.PROFILES_FILE
        conn.CONFIG_DIR = self.dir
        conn.PROFILES_FILE = self.dir / "connections.json"
        conn.KEYS_FILE = self.dir / "keys.local.json"

    def tearDown(self):
        conn.CONFIG_DIR, conn.KEYS_FILE = self._old_cfg, self._old_keys
        conn.PROFILES_FILE = self._old_profiles
        self.tmp.cleanup()

    def test_tgju_preset_is_verified_and_uses_symbol_template(self):
        """پروفایل رایگان tgju باید آزمون‌شده باشد و مسیر تأییدشده را داشته باشد."""
        store = conn.default_store()
        prof = conn.find_profile(store, "tgju-usd")
        self.assertIsNotNone(prof)
        self.assertTrue(prof["tested"])
        self.assertIn("{symbol}", prof["url_template"])
        self.assertEqual(prof["json_path"], "data.0.3")
        self.assertEqual(prof["cost"], conn.FREE)
        self.assertEqual(prof["env_key"], "")

    def test_default_store_has_presets_and_mock_selected(self):
        store = conn.load_store()
        names = {p["name"] for p in store["profiles"]}
        self.assertIn("mock-local", names)
        self.assertIn("custom", names)
        self.assertEqual(store["selected"], "mock-local")

    def test_default_store_has_free_profiles(self):
        store = conn.load_store()
        free = [p for p in store["profiles"] if p["cost"] == conn.FREE]
        self.assertGreaterEqual(len(free), 4)          # رایگان‌ها همیشه باید موجود باشند

    def test_upsert_save_and_reload(self):
        store = conn.load_store()
        conn.upsert_profile(store, {"name": "my-broker", "label": "سرویس من",
                                    "url_template": "https://x.ir/q?symbol={symbol}", "json_path": "a.b"})
        conn.select_profile(store, "my-broker")
        conn.save_store(store)
        again = conn.load_store()
        prof = conn.find_profile(again, "my-broker")
        self.assertIsNotNone(prof)
        self.assertEqual(prof["json_path"], "a.b")
        self.assertEqual(again["selected"], "my-broker")

    def test_store_file_never_contains_keys(self):
        store = conn.load_store()
        conn.upsert_profile(store, {"name": "k1", "url_template": "https://x/{key}"})
        conn.save_store(store)
        conn.save_key("k1", "SECRET-123")
        text = conn.PROFILES_FILE.read_text(encoding="utf-8")
        self.assertNotIn("SECRET-123", text)
        self.assertEqual(conn.stored_key("k1"), "SECRET-123")

    def test_delete_profile_removes_it(self):
        store = conn.load_store()
        conn.upsert_profile(store, {"name": "temp-prof"})
        conn.save_store(store)
        store = conn.load_store()
        self.assertTrue(conn.delete_profile(store, "temp-prof"))
        conn.save_store(store)
        self.assertIsNone(conn.find_profile(conn.load_store(), "temp-prof"))

    def test_new_presets_are_added_to_old_file(self):
        old = {"version": 1, "selected": "custom", "profiles": [dict(conn.PRESET_PROFILES[0])]}
        conn.PROFILES_FILE.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
        store = conn.load_store()
        self.assertGreater(len(store["profiles"]), 1)

    def test_presets_are_upgraded_but_user_profiles_untouched(self):
        # نسخهٔ قدیمی: پروفایل آمادهٔ «modified» با نشانی عوض‌شده توسط کاربر + پروفایل خودساخته
        old = {"version": 1, "selected": "my-own", "profiles": [
            {"name": "exchange-irt", "label": "صرافی (نسخهٔ قدیمی)", "url_template": "https://old/x",
             "custom": True},
            {"name": "my-own", "label": "سرویس خودم", "url_template": "https://mine/x", "custom": True},
            {"name": "tgju-usd", "label": "tgju (نسخهٔ قدیمی)", "url_template": "https://old/tgju"}]}
        conn.PROFILES_FILE.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
        store = conn.load_store()
        self.assertEqual(conn.find_profile(store, "exchange-irt")["url_template"], "https://old/x")
        self.assertEqual(conn.find_profile(store, "my-own")["url_template"], "https://mine/x")
        refreshed = conn.find_profile(store, "tgju-usd")
        self.assertNotEqual(refreshed["url_template"], "https://old/tgju")

    def test_preset_version_is_stored(self):
        store = conn.load_store()
        conn.save_store(store)
        again = json.loads(conn.PROFILES_FILE.read_text(encoding="utf-8"))
        self.assertEqual(again["preset_version"], conn.PRESET_VERSION)

    def test_corrupt_file_falls_back_to_defaults(self):
        conn.PROFILES_FILE.write_text("{ this is not json", encoding="utf-8")
        store = conn.load_store()
        self.assertEqual(store["selected"], "mock-local")


class KeyResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self._old_cfg, self._old_keys = conn.CONFIG_DIR, conn.KEYS_FILE
        conn.CONFIG_DIR = self.dir
        conn.KEYS_FILE = self.dir / "keys.local.json"
        self.prof = {"name": "p1", "env_key": "TEST_MARKET_KEY"}

    def tearDown(self):
        conn.CONFIG_DIR, conn.KEYS_FILE = self._old_cfg, self._old_keys
        os.environ.pop("TEST_MARKET_KEY", None)
        self.tmp.cleanup()

    def test_inline_key_wins(self):
        conn.save_key("p1", "SAVED")
        os.environ["TEST_MARKET_KEY"] = "FROM_ENV"
        key, where = conn.resolve_key(self.prof, inline_key="TYPED")
        self.assertEqual(key, "TYPED")
        self.assertIn("کادر", where)

    def test_saved_key_beats_env(self):
        conn.save_key("p1", "SAVED")
        os.environ["TEST_MARKET_KEY"] = "FROM_ENV"
        key, where = conn.resolve_key(self.prof)
        self.assertEqual(key, "SAVED")
        self.assertIn("ذخیره", where)

    def test_env_used_when_nothing_saved(self):
        os.environ["TEST_MARKET_KEY"] = "FROM_ENV"
        key, where = conn.resolve_key(self.prof)
        self.assertEqual(key, "FROM_ENV")
        self.assertIn("محیطی", where)

    def test_no_key_at_all(self):
        key, where = conn.resolve_key(self.prof)
        self.assertEqual(key, "")
        self.assertEqual(where, "بدون کلید")

    def test_clearing_saved_key(self):
        conn.save_key("p1", "SAVED")
        conn.save_key("p1", "")
        self.assertEqual(conn.stored_key("p1"), "")


class ProfileApplicationTests(unittest.TestCase):
    def test_mock_profile_maps_to_live_config(self):
        store = conn.load_store()
        active = conn.apply_profile(store, "mock-local")
        self.assertTrue(active["is_mock"])
        self.assertIn("{symbol}", active["live_cfg"]["url_template"])
        self.assertEqual(active["live_cfg"]["json_path"], "data.0.pl")

    def test_unknown_profile_raises(self):
        with self.assertRaises(KeyError):
            conn.apply_profile(conn.load_store(), "does-not-exist")

    def test_active_or_none_returns_dict_or_none(self):
        active = conn.active_or_none()
        self.assertTrue(active is None or "profile" in active)

    def test_summary_rows_mark_selected(self):
        rows = conn.summary_rows()
        self.assertTrue(any(r[0] == "★" for r in rows))


class PeekHelperTests(unittest.TestCase):
    def test_numeric_paths_finds_nested_numbers(self):
        payload = {"data": [{"pl": "20,150", "name": "اهرم"}], "meta": {"count": 3}, "ok": True}
        paths = dict(datafeed.numeric_paths(payload))
        self.assertEqual(paths["data.0.pl"], 20150.0)
        self.assertEqual(paths["meta.count"], 3.0)

    def test_numeric_paths_respects_limit(self):
        payload = {f"k{i}": i for i in range(100)}
        self.assertLessEqual(len(datafeed.numeric_paths(payload, max_items=10)), 10)

    def test_numeric_paths_ignores_text(self):
        self.assertEqual(datafeed.numeric_paths({"name": "اهرم", "null": None, "b": False}), [])


if __name__ == "__main__":
    unittest.main()
