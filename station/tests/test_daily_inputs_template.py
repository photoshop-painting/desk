#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون «ورودی روزانه»: قالب اسنپ‌شات و راهنمای آن.

هدف دو چیز است:
  ۱. قالب هیچ‌وقت ناقص نماند (هر پنج نوع معامله با فیلدهای درست).
  ۲. همان قالب هرگز به‌اشتباه یک «روز واقعی» در کارنامه ثبت نکند.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GUI = HERE.parent
sys.path.insert(0, str(GUI))

import datafeed as df  # noqa: E402
import daily_trial as dt  # noqa: E402

def _doc(name: str) -> Path:
    for cand in (GUI.parent / name, GUI.parent / "docs" / name, GUI / "docs" / name):
        if cand.exists():
            return cand
    return GUI.parent / name


DOC = _doc("10-daily-inputs-fa.md")
NEEDED = {
    "basis": ("spot", "future", "days"),
    "covered_call": ("spot", "strike", "premium", "days"),
    "tabei": ("stock_price", "put_price", "strike", "days"),
    "box": ("call_low", "put_low", "call_high", "put_high", "strike_low", "strike_high", "days"),
    "parity": ("call", "put", "spot", "strike", "days"),
}


class TestTemplate(unittest.TestCase):
    def setUp(self):
        self.raw = json.loads(json.dumps(df.SNAPSHOT_TEMPLATE, ensure_ascii=False))

    def test_template_names_all_five_kinds(self):
        kinds = {r["kind"] for r in self.raw["rows"]}
        self.assertEqual(set(NEEDED), kinds)

    def test_every_kind_has_its_numbers(self):
        for row in self.raw["rows"]:
            for field in NEEDED[row["kind"]]:
                self.assertIn(field, row, f"{row['symbol']}: «{field}» نیست")
                self.assertGreater(float(row[field]), 0, f"{row['symbol']}: «{field}» باید مثبت باشد")

    def test_common_fields_present(self):
        for row in self.raw["rows"]:
            for field in ("symbol", "margin_per_contract", "liquidity_contracts_per_day", "spread_pct"):
                self.assertIn(field, row, f"{row['symbol']}: «{field}» نیست")

    def test_rules_and_help_blocks_present(self):
        self.assertIn("hurdle", self.raw)
        self.assertIn("capital", self.raw)
        self.assertIn("قالب", self.raw["note"])
        for kind in NEEDED:
            self.assertIn(kind, self.raw["_fields_per_kind"])

    def test_written_template_loads_as_snapshot(self):
        """قالبِ نوشته‌شده روی دیسک باید بدون خطا خوانده شود (پنج ردیف)."""
        with tempfile.TemporaryDirectory() as tmp:
            p = df.write_snapshot_template(Path(tmp) / "snapshot-template.json")
            snap = df.build_snapshot("file", file_path=p)
            self.assertEqual("ok", snap.status, snap.messages)
            self.assertEqual(5, len(snap.rows))
            self.assertIn("دستی", snap.source_label)


class TestHonesty(unittest.TestCase):
    def test_template_name_is_synthetic(self):
        """نام قالب هرگز روز «واقعی» حساب نمی‌شود."""
        self.assertTrue(dt.path_is_synthetic("data/snapshot-template.json"))

    def test_renamed_copy_is_real(self):
        """اگر کاربر عددهای واقعی خودش را با نام خودش ذخیره کند، روز واقعی است."""
        self.assertFalse(dt.path_is_synthetic("data/daily-input.json"))

    def test_note_field_says_it_is_a_template(self):
        self.assertIn("واقعی", df.SNAPSHOT_TEMPLATE["note"])


class TestDoc(unittest.TestCase):
    def test_doc_exists_and_names_the_free_sources(self):
        text = DOC.read_text(encoding="utf-8")
        for needle in ("tsetmc", "کدال", "کارگزاری", "مجانی", "snapshot-template.json"):
            self.assertIn(needle, text)

    def test_doc_lists_field_names_of_every_kind(self):
        text = DOC.read_text(encoding="utf-8")
        for field in ("spot", "future", "strike", "premium", "put_price",
                      "call_low", "put_high", "margin_per_contract", "liquidity_contracts_per_day"):
            self.assertIn(field, text)

    def test_doc_says_what_not_to_enter(self):
        text = DOC.read_text(encoding="utf-8")
        for needle in ("رمز", "سفارش"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
