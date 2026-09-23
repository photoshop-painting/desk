#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون «منبع واقعی روی میزبان ابری» — ensure_connection.py."""
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
import ensure_connection as ec  # noqa: E402


class EnsureConnectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self._old_cfg, self._old_profiles = conn.CONFIG_DIR, conn.PROFILES_FILE
        conn.CONFIG_DIR = self.dir
        conn.PROFILES_FILE = self.dir / "connections.json"
        self._old_env = os.environ.get("STATION_CONNECTION")

    def tearDown(self):
        conn.CONFIG_DIR, conn.PROFILES_FILE = self._old_cfg, self._old_profiles
        if self._old_env is None:
            os.environ.pop("STATION_CONNECTION", None)
        else:
            os.environ["STATION_CONNECTION"] = self._old_env
        self.tmp.cleanup()

    def _write_store(self, selected: str) -> None:
        store = conn.default_store()
        conn.select_profile(store, selected)
        conn.save_store(store)

    def test_flips_mock_local_to_real_source(self):
        """حالت بدِ اصلی: وضعیتِ برگردانده‌شده «خوراک آزمایشی محلی» را به منبع واقعی برمی‌گرداند.»"""
        self._write_store("mock-local")
        self.assertEqual(ec.main(), 0)
        self.assertEqual(conn.load_store()["selected"], "tgju-usd")

    def test_missing_file_creates_store_with_real_source(self):
        """اگر پرونده نبود، دفتر با همهٔ پروفایل‌ها ساخته و منبع واقعی انتخاب می‌شود.»"""
        self.assertFalse(conn.PROFILES_FILE.exists())
        self.assertEqual(ec.main(), 0)
        store = conn.load_store()
        self.assertEqual(store["selected"], "tgju-usd")
        self.assertTrue(any(p["name"] == "tgju-usd" for p in store["profiles"]))

    def test_respects_custom_station_connection_env(self):
        """متغیر STATION_CONNECTION می‌تواند منبع دیگر را پیش‌فرض کند.»"""
        self._write_store("mock-local")
        os.environ["STATION_CONNECTION"] = "exchange-irt"
        self.assertEqual(ec.main(), 0)
        self.assertEqual(conn.load_store()["selected"], "exchange-irt")

    def test_unknown_profile_leaves_selection_untouched(self):
        """اگر منبعِ خواسته‌شده در فهرست نبود، انتخاب دست‌نخورده می‌ماند.»"""
        self._write_store("mock-local")
        os.environ["STATION_CONNECTION"] = "چنین‌منبعی‌نیست"
        self.assertEqual(ec.main(), 0)
        self.assertEqual(conn.load_store()["selected"], "mock-local")

    def test_idempotent_when_already_real(self):
        """دومین اجرا هیچ تغییری نمی‌دهد (آیدی‌پوتنت).»"""
        self._write_store("mock-local")
        ec.main()
        first = json.loads(conn.PROFILES_FILE.read_text(encoding="utf-8"))
        ec.main()
        second = json.loads(conn.PROFILES_FILE.read_text(encoding="utf-8"))
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main(verbosity=2)
