#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون‌های math-pool (bankroll) — ریاضیِ بقا و رشد باید بازتولیدپذیر و صادق باشد.

قفل‌های اصلی:
  ۱) کسر کِلی با کسرِ دستی می‌خواند: f = (p·b − q) ÷ b.
  ۲) نرخ برد سر‌به‌سر با کسر دستی می‌خواند.
  ۳) شبیه‌سازی با دانهٔ ثابت، نتیجهٔ یکسان می‌دهد (بازتولیدپذیری).
  ۴) کارمزد بیشتر ⇒ میانهٔ پایان کمتر (یکنوا)، و ریسک درشت ⇒ ورشکستگی بیشتر.
  ۵) مسیر رشد با لگاریتم می‌خواند، و بازده خالص منفی ⇒ «هیچ‌وقت».
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

GUI = Path(__file__).resolve().parents[1]
if str(GUI) not in sys.path:
    sys.path.insert(0, str(GUI))

import bankroll as bk  # noqa: E402


class TestKelly(unittest.TestCase):
    def test_kelly_hand_math(self):
        k = bk.kelly(0.55, 8.0, 5.0)          # b = 1.6 · f = (0.88−0.45)÷1.6
        self.assertTrue(k["ok"])
        self.assertAlmostEqual(k["kelly_fraction"], 0.2688, places=4)
        self.assertAlmostEqual(k["half_kelly_fraction"], 0.1344, places=4)
        self.assertAlmostEqual(k["edge_pct_per_trade"], 2.15, places=2)

    def test_negative_edge_is_refused(self):
        k = bk.kelly(0.30, 8.0, 5.0)
        self.assertFalse(k["positive_edge"])
        self.assertEqual(k["kelly_fraction"], 0.0)
        self.assertIn("پول‌سوزی", k["detail"])

    def test_breakeven_hand_math(self):
        be = bk.breakeven_win_rate(win_pct=8.0, loss_pct=5.0, fee_pct=1.428)
        self.assertAlmostEqual(be["breakeven_win_prob"], (5 + 1.428) / 13.0, places=4)
        self.assertAlmostEqual(be["breakeven_win_pct"], 49.45, places=2)


class TestSimulation(unittest.TestCase):
    def test_same_seed_same_result(self):
        a = bk.simulate(trials=500, seed=3)
        b = bk.simulate(trials=500, seed=3)
        self.assertEqual(a["median_final"], b["median_final"])
        self.assertEqual(a["ruin_prob"], b["ruin_prob"])

    def test_fee_drag_reduces_median(self):
        cheap = bk.simulate(trials=800, fee_pct=0.0)
        dear = bk.simulate(trials=800, fee_pct=4.0)
        self.assertLess(dear["median_final"], cheap["median_final"])

    def test_bigger_size_means_more_ruin(self):
        small = bk.simulate(risk_fraction=0.05, trials=800, win_prob=0.45)
        big = bk.simulate(risk_fraction=0.40, trials=800, win_prob=0.45)
        self.assertGreaterEqual(big["ruin_prob"], small["ruin_prob"])
        self.assertGreaterEqual(big["ruin_prob"], 0.0)

    def test_probabilities_are_in_range(self):
        s = bk.simulate(trials=300)
        for key in ("ruin_prob", "double_prob", "profit_prob"):
            self.assertGreaterEqual(s[key], 0.0)
            self.assertLessEqual(s[key], 1.0)
        self.assertLessEqual(s["p10_final"], s["median_final"])
        self.assertLessEqual(s["median_final"], s["p90_final"])


class TestPath(unittest.TestCase):
    def test_months_hand_math(self):
        p = bk.path(capital=100_000_000.0, monthly_return_pct=10.0, target=400_000_000.0)
        expected = math.log(4) / math.log(1.10)
        self.assertAlmostEqual(p["months"], expected, places=1)

    def test_zero_growth_never_reaches(self):
        p = bk.path(capital=100_000_000.0, monthly_return_pct=1.0, target=400_000_000.0,
                    fee_drag_pct_month=1.0)
        self.assertIsNone(p["months"])
        self.assertIn("هیچ زمانی", p["detail"])

    def test_strategy_path_subtracts_churn_fees(self):
        sp = bk.strategy_path(capital=100_000_000.0, annualized_pct=68.482,
                              target=400_000_000.0, churn_per_year=1.0)
        self.assertAlmostEqual(sp["net_annual_pct"], 68.482 - 1.428, places=2)
        self.assertGreater(sp["months"], 24)
        self.assertLess(sp["months"], 42)

    def test_strategy_path_negative_when_churn_eats_edge(self):
        sp = bk.strategy_path(capital=100_000_000.0, annualized_pct=1.0,
                              target=400_000_000.0, churn_per_year=1.0)
        self.assertIsNone(sp["months"])
        self.assertIn("منفی", sp["detail"])


class TestBuild(unittest.TestCase):
    def test_build_without_writing(self):
        doc = bk.build(write=False)
        self.assertEqual(len(doc["checks"]), 3)
        self.assertIn("وعدهٔ سود نیست", doc["honesty"])
        self.assertIn("## ۳.", doc["md_text"])
        self.assertIn("نیم‌شدن حساب", doc["md_text"])

    def test_used_fraction_is_conservative(self):
        doc = bk.build(write=False)
        k = doc["kelly"]
        self.assertLessEqual(doc["used_risk_fraction"], k["kelly_fraction"] + 1e-9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
