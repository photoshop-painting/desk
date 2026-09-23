#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون «ورود اعداد از متن کپی‌شده» (snapshot_import.py).

هدف: کاربر نوآموز متن را از سامانهٔ کارگزاری کپی می‌کند و برنامه باید رقم فارسی، جداکنندهٔ
هزارگان، «تومان»، سرستون و خط‌های کج‌وکوله را بفهمد و هر چیز نفهمیده را صادقانه گزارش کند.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GUI = HERE.parent
sys.path.insert(0, str(GUI))

import datafeed as df  # noqa: E402
import snapshot_import as si  # noqa: E402


class TestNumbers(unittest.TestCase):
    def test_persian_digits(self):
        self.assertEqual(20000.0, si.to_number("۲۰٬۰۰۰ ریال"))

    def test_arabic_digits_and_thousand_separator(self):
        self.assertEqual(1234567.0, si.to_number("۱,۲۳۴,۵۶۷"))

    def test_toman_word_ignored(self):
        self.assertEqual(7050.0, si.to_number("7050 تومان"))

    def test_percent_word_ignored(self):
        self.assertEqual(1.8, si.to_number("1.8 %"))

    def test_non_number(self):
        self.assertIsNone(si.to_number("فولاد"))


class TestParsing(unittest.TestCase):
    def test_five_kinds_from_text(self):
        text = """
        # اعداد امروز از سامانهٔ کارگزاری
        اهرم , basis , 20000 , 22800 , 90 , 20000000 , 900 , 0.005
        فولاد , covered_call , 7000 , 7600 , 400 , 45 , 7000 , 160 , 1.8
        کگل , tabei , 9800 , 40 , 14210 , 365
        شپنا , box , 300 , 430 , 175 , 585 , 1200 , 1500 , 45
        وبملت , parity , 420 , 380 , 9000 , 9000 , 30
        """
        res = si.parse_paste(text)
        self.assertTrue(res["ok"], res["problems"])
        self.assertEqual(5, res["count"])
        by = {r["symbol"]: r for r in res["rows"]}
        self.assertEqual(22800, by["اهرم"]["future"])
        self.assertEqual(7600, by["فولاد"]["strike"])
        self.assertEqual(14210, by["کگل"]["strike"])
        self.assertEqual(1500, by["شپنا"]["strike_high"])
        self.assertEqual("parity", by["وبملت"]["kind"])

    def test_percent_spread_normalized(self):
        res = si.parse_paste("فولاد , covered , 7000 , 7600 , 400 , 45 , 7000 , 160 , 1.8")
        self.assertAlmostEqual(0.018, res["rows"][0]["spread_pct"], places=6)

    def test_kind_guessed_when_missing(self):
        res = si.parse_paste("اهرم 20000 22800 90")
        self.assertEqual("basis", res["rows"][0]["kind"])
        self.assertTrue(any("راهبرد" in h for h in res["hints"]))

    def test_default_kind_overrides_guess(self):
        res = si.parse_paste("اهرم , 9800 , 40 , 14210 , 365", default_kind="tabei")
        self.assertEqual("tabei", res["rows"][0]["kind"])
        self.assertEqual(9800, res["rows"][0]["stock_price"])

    def test_toman_scaling_only_prices(self):
        res = si.parse_paste("اهرم , basis , 2000 , 2280 , 90", toman_to_rial=True)
        row = res["rows"][0]
        self.assertEqual(20000, row["spot"])
        self.assertEqual(22800, row["future"])
        self.assertEqual(90, row["days"])              # روز هرگز ×۱۰ نمی‌شود

    def test_too_few_numbers_is_reported(self):
        res = si.parse_paste("فولاد , covered_call , 7000 , 7600")
        self.assertFalse(res["ok"])
        self.assertEqual(0, res["count"])
        self.assertTrue(any("به 4 عدد نیاز" in p or "به ۴ عدد نیاز" in p for p in res["problems"]))

    def test_header_names_decide_kind_for_covered_call(self):
        text = ("نماد , قیمت سهم , اعمال , پرمیوم , روز\n"
                "فولاد , ۷٬۰۰۰ , 7,600 , 400 , 45 , 7000 , 160 , 1.8")
        row = si.parse_paste(text)["rows"][0]
        self.assertEqual("covered_call", row["kind"])
        self.assertEqual(7000, row["spot"])
        self.assertEqual(7600, row["strike"])          # «7,600» یک عدد است، نه دو ستون
        self.assertEqual(400, row["premium"])
        self.assertEqual(45, row["days"])
        self.assertEqual(7000, row["margin_per_contract"])   # عددهای باقی‌مانده اختیاری‌اند
        self.assertAlmostEqual(0.018, row["spread_pct"], places=6)

    def test_header_with_put_word_means_tabei(self):
        text = ("نماد , قیمت سهم , پوت , اعمال , روز\n"
                "کگل , 9800 , 40 , 14210 , 365 , 9840 , 240 , 0.02")
        row = si.parse_paste(text)["rows"][0]
        self.assertEqual("tabei", row["kind"])
        self.assertEqual(40, row["put_price"])
        self.assertEqual(9840, row["margin_per_contract"])

    def test_box_row_is_not_flagged_for_missing_price(self):
        res = si.parse_paste("شپنا , box , 300 , 430 , 175 , 585 , 1200 , 1500 , 45")
        clean, problems = df.clean_rows(res["rows"])
        self.assertEqual(1, len(clean))
        self.assertEqual([], [p for p in problems if "هیچ قیمتی" in p])

    def test_label_words_inside_row_are_not_reported_as_junk(self):
        res = si.parse_paste("کگل , پوت , 9800 , 40 , 14210 , 365")
        self.assertEqual(1, res["count"])
        self.assertEqual([], [h for h in res["hints"] if "عدد نبودند" in h])

    def test_inline_labels_inside_row_define_tabei(self):
        res = si.parse_paste("کگل , قیمت سهم , پوت , اعمال , روز , 9800 , 40 , 14210 , 365 , 9840")
        row = res["rows"][0]
        self.assertEqual("tabei", row["kind"])
        self.assertEqual(9800, row["stock_price"])
        self.assertEqual(40, row["put_price"])
        self.assertEqual(14210, row["strike"])
        self.assertEqual(365, row["days"])

    def test_inline_labels_inside_row_define_parity(self):
        res = si.parse_paste("وبملت , کال , پوت , قیمت پایه , اعمال , روز , 420 , 380 , 9000 , 9000 , 30")
        row = res["rows"][0]
        self.assertEqual("parity", row["kind"])
        self.assertEqual(420, row["call"])
        self.assertEqual(380, row["put"])
        self.assertEqual(30, row["days"])

    def test_box_row_keeps_margin_and_spread(self):
        res = si.parse_paste("شپنا , باکس , 300 , 430 , 175 , 585 , 1200 , 1500 , 45 , 250000 , 12 , 4.5")
        row = res["rows"][0]
        self.assertEqual("box", row["kind"])
        self.assertEqual(250000, row["margin_per_contract"])
        self.assertEqual(12, row["liquidity_contracts_per_day"])
        self.assertAlmostEqual(0.045, row["spread_pct"], places=6)

    def test_header_line_is_read_and_not_turned_into_row(self):
        text = "نماد , قیمت سهم , اعمال , پرمیوم , روز\nفولاد , 7000 , 7600 , 400 , 45"
        res = si.parse_paste(text)
        self.assertEqual(1, res["count"])
        self.assertTrue(any("سرستون" in h for h in res["hints"]))

    def test_junk_words_are_reported_not_silent(self):
        res = si.parse_paste("فولاد , covered , 7000 , 7600 , 400 , 45 , 7000 , 160 , 0.018 , نامعلوم")
        self.assertTrue(any("عدد نبودند" in h for h in res["hints"]))

    def test_row_without_symbol_is_rejected(self):
        res = si.parse_paste("7000 , 7600 , 400 , 45")
        self.assertFalse(res["ok"])
        self.assertTrue(any("بی‌نماد" in p for p in res["problems"]))

    def test_empty_text_is_not_ok(self):
        self.assertFalse(si.parse_paste("")["ok"])

    def test_clean_rows_accepts_output(self):
        res = si.parse_paste("اهرم , basis , 20000 , 22800 , 90 , 20000000 , 900 , 0.005")
        clean, problems = df.clean_rows(res["rows"])
        self.assertEqual(1, len(clean))
        self.assertEqual([], [p for p in problems if "هیچ قیمتی" in p])


class TestCli(unittest.TestCase):
    def _run(self, *args, stdin: str = ""):
        return subprocess.run([sys.executable, str(GUI / "snapshot_import.py"), *args],
                              capture_output=True, text=True, timeout=120, input=stdin)

    def test_json_output(self):
        r = self._run("--json", "--text", "اهرم , basis , 20000 , 22800 , 90")
        self.assertEqual(0, r.returncode)
        self.assertEqual(1, json.loads(r.stdout)["count"])

    def test_bad_input_exit_code(self):
        r = self._run("--json", "--text", "فولاد")
        self.assertEqual(1, r.returncode)

    def test_text_output_explains_problems(self):
        r = self._run("--text", "فولاد , covered_call , 7000 , 7600")
        self.assertIn("ردیف خوانده شد", r.stdout)
        self.assertIn("نیاز", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

class SanityAndConflicts(unittest.TestCase):
    """بازبینی عقلی: عددهای محال و سرستون‌های ناهمخوان باید حرف بزنند."""

    def test_impossible_covered_call_is_reported(self):
        res = si.parse_paste("فولاد , covered_call , 7000 , 6000 , 400 , 45")
        self.assertTrue(any("اعمال" in p and "کمتر" in p for p in res["problems"]), res["problems"])

    def test_impossible_tabei_is_reported(self):
        res = si.parse_paste("کگل , tabei , 9800 , 40 , 7000 , 365")
        self.assertTrue(any("بیشتر باشد" in p for p in res["problems"]), res["problems"])

    def test_negative_basis_is_reported(self):
        res = si.parse_paste("صندوق , basis , 20000 , 18000 , 90")
        self.assertTrue(any("آتی" in p for p in res["problems"]), res["problems"])

    def test_oversized_premium_is_reported(self):
        res = si.parse_paste("فولاد , covered_call , 7000 , 7600 , 4000 , 45")
        self.assertTrue(any("پرمیوم" in p and "بزرگ" in p for p in res["problems"]), res["problems"])

    def test_header_and_order_conflict_is_hinted(self):
        # سرستون: اعمال، پرمیوم، قیمت سهم | عددها: 7000، 7600، 400 → خوانش سرستون با ترتیب نمی‌خواند
        res = si.parse_paste("نماد , اعمال , پرمیوم , قیمت سهم , روز\nفولاد , 7000 , 7600 , 400 , 45")
        joined = " ".join(res["hints"])
        self.assertIn("نمی‌خوانند", joined, res["hints"])

    def test_healthy_rows_have_no_problems(self):
        res = si.parse_paste("فولاد , covered_call , 7000 , 7600 , 400 , 45\n"
                             "کگل , tabei , 9800 , 40 , 14210 , 365")
        self.assertEqual(res["problems"], [], res["problems"])
        self.assertEqual(res["count"], 2)
