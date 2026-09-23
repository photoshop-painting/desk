#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون‌های edge_stress — «شوک‌آزمون» باید با موتور سازگار و یکنوا باشد.

قفل‌های اصلی:
  ۱) حالت خنثی (بدون شوک) **دقیقاً** همان عدد موتور است (neutral_matches_engine).
  ۲) شوک‌ها بدتر می‌کنند: لغزش اجرا و کارمزد بیشتر ⇒ بازده کمتر، هرگز بیشتر.
  ۳) تحمل کارمزد درست است: روی عدد برگشتی سالم می‌ماند و کمی بالاتر می‌افتد.
  ۴) سقف نرخ سد درست است.
  ۵) فاصله تا مارجین‌کال با واحدهای ناهمخوان، عدد عجیب چاپ نمی‌کند.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

GUI = Path(__file__).resolve().parents[1]
if str(GUI) not in sys.path:
    sys.path.insert(0, str(GUI))

import edge_stress as es  # noqa: E402
import investor_test as inv  # noqa: E402


class TestNeutralMatchesEngine(unittest.TestCase):
    def test_every_row_neutral_equals_engine(self):
        doc = es.stress()
        self.assertTrue(doc["rows"], "باید حداقل یک ردیف راهبرد باشد")
        for r in doc["rows"]:
            self.assertTrue(r["neutral_matches_engine"],
                            f"حالت خنثی با موتور یکی نیست: {r['title']}")

    def test_parity_neutral_is_boolean_verdict(self):
        row = inv._pick("parity", inv.fallback_rows())
        got = es.survives(row)
        self.assertIsInstance(got["survives"], bool)
        self.assertIn("go", got)


class TestMonotoneShocks(unittest.TestCase):
    def test_slip_reduces_return(self):
        row = inv._pick("basis", inv.fallback_rows())
        base = es.survives(row)["annualized_pct"]
        slipped = es.survives(row, slip_pct=es.SLIP_PCT)["annualized_pct"]
        self.assertLess(slipped, base)

    def test_more_fees_reduce_return(self):
        row = inv._pick("covered_call", inv.fallback_rows())
        base = es.survives(row)["annualized_pct"]
        two = es.survives(row, fee_mult=2.0)["annualized_pct"]
        three = es.survives(row, fee_mult=3.0)["annualized_pct"]
        self.assertLess(two, base)
        self.assertLess(three, two)

    def test_higher_hurdle_never_helps(self):
        row = inv._pick("tabei", inv.fallback_rows())
        low = es.survives(row, hurdle=0.30)
        high = es.survives(row, hurdle=0.90)
        self.assertTrue(low["survives"])
        self.assertFalse(high["survives"])


class TestFeeTolerance(unittest.TestCase):
    def test_tolerance_is_a_real_breakeven(self):
        row = inv._pick("basis", inv.fallback_rows())
        tol = es.fee_tolerance(row)
        if tol["multiple"] is None:
            self.skipTest("این راهبرد تا ۱۲ برابر کارمزد هم می‌ماند")
        m = tol["multiple"]
        self.assertTrue(es.survives(row, fee_mult=max(0.0, m * 0.9))["survives"])
        self.assertFalse(es.survives(row, fee_mult=m * 1.1)["survives"])

    def test_box_neutral_equals_engine_after_bug_fix(self):
        """باگ باکس (کم‌کردن دوبارهٔ پرداخت خالص) نباید برگردد."""
        row = inv._pick("box", inv.fallback_rows())
        self.assertAlmostEqual(es.annualized(row)["annualized_pct"],
                               inv.ladder_for(row)["annualized_pct"], places=2)

    def test_parity_reports_no_multiple(self):
        row = inv._pick("parity", inv.fallback_rows())
        tol = es.fee_tolerance(row)
        self.assertIsNone(tol["multiple"])
        self.assertIn("کارمزد", tol["detail"])


class TestHurdleCeiling(unittest.TestCase):
    def test_ceiling_is_the_todays_return(self):
        row = inv._pick("basis", inv.fallback_rows())
        ceil = es.hurdle_ceiling(row)
        annual = inv.ladder_for(row)["annualized_pct"]
        self.assertAlmostEqual(ceil["annualized_pct"], annual, places=2)
        self.assertAlmostEqual(ceil["ceiling_pct"], annual, places=3)


class TestMarginDistance(unittest.TestCase):
    def test_basis_margin_is_sane(self):
        row = inv._pick("basis", inv.fallback_rows())
        got = es.margin_distance(row)
        self.assertTrue(got["ok"], got.get("detail"))
        self.assertGreater(got["move_pct"], 0)
        self.assertLess(got["move_pct"], 100)
        self.assertGreater(got["money_at_risk"], 0)
        self.assertIn("حد نگهداری", got["source"])

    def test_unit_mismatch_is_refused_not_reported(self):
        row = dict(inv._pick("basis", inv.fallback_rows()))
        row["notional_per_contract"] = 20_000            # تومان
        row["margin_per_contract"] = 20_000_000          # ریال — ناهمخوان
        got = es.margin_distance(row)
        self.assertFalse(got["ok"])
        self.assertTrue(got.get("unit_mismatch"))
        self.assertIn("واحد", got["detail"])

    def test_contract_size_makes_notional(self):
        row = dict(inv._pick("basis", inv.fallback_rows()))
        row.pop("notional_per_contract", None)
        row["contract_size"] = 500
        row["margin_per_contract"] = 2_280_000
        got = es.margin_distance(row)
        self.assertTrue(got["ok"], got.get("detail"))
        self.assertAlmostEqual(got["notional_per_contract"], 500 * float(row["future"]), places=2)


class TestBuild(unittest.TestCase):
    def test_report_without_writing(self):
        doc = es.build(write=False)
        self.assertIn("honesty", doc)
        self.assertIn("تاب‌آوری", doc["honesty"])
        self.assertIn("احتمال سود نیست", doc["honesty"])
        self.assertIn("## ۱.", doc["md_text"])
        self.assertGreaterEqual(len(doc["rows"]), 5)

    def test_every_row_has_shocks_and_feasibility(self):
        doc = es.stress()
        for r in doc["rows"]:
            self.assertGreaterEqual(len(r["shocks"]), 5)
            self.assertIn("resilience_pct", r)
            self.assertIsNotNone(r.get("feasibility"))

    def test_resilience_is_not_a_probability_of_profit(self):
        doc = es.stress()
        for r in doc["rows"]:
            self.assertGreaterEqual(r["resilience_pct"], 0)
            self.assertLessEqual(r["resilience_pct"], 100)
            self.assertIsInstance(r["shocks_passed"], int)


if __name__ == "__main__":
    unittest.main(verbosity=2)
