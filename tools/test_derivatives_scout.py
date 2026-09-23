#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون‌های واحد ابزار دیده‌بان مشتقه — فقط کتابخانهٔ استاندارد."""
from __future__ import annotations

import math
import unittest

from derivatives_scout import (
    FEE_FUND_ETF,
    Scenario,
    basis_opportunity,
    black_scholes,
    box_spread,
    covered_call,
    futures_fair,
    implied_rate,
    implied_vol,
    position_size,
    put_call_parity,
    run_scenario,
    score,
    tabei_min_yield,
    years,
)


class TestPricing(unittest.TestCase):
    def test_black_scholes_reference_value(self):
        # S=K=100، T=1 سال، r=0، σ=0.2 ⇒ C ≈ 7.9656
        self.assertAlmostEqual(black_scholes(100, 100, 365, 0.0, 0.20, "call"), 7.9656, places=3)

    def test_model_parity(self):
        c = black_scholes(100, 100, 365, 0.10, 0.25, "call")
        p = black_scholes(100, 100, 365, 0.10, 0.25, "put")
        self.assertAlmostEqual(c - p, 100 - 100 * math.exp(-0.10), places=8)

    def test_zero_vol_is_intrinsic(self):
        # با نوسان صفر: C = S − K·e^(−rT)
        expected = 110 - 100 * math.exp(-0.3 * 30 / 365)
        self.assertAlmostEqual(black_scholes(110, 100, 30, 0.3, 0.0, "call"), expected, places=6)

    def test_implied_vol_round_trip(self):
        price = black_scholes(100, 100, 365, 0.0, 0.20, "call")
        iv = implied_vol(price, 100, 100, 365, 0.0, "call")
        self.assertIsNotNone(iv)
        self.assertAlmostEqual(iv, 0.20, places=4)

    def test_implied_vol_rejects_below_intrinsic(self):
        self.assertIsNone(implied_vol(1.0, 100, 50, 30, 0.0, "call"))

    def test_days_must_be_positive(self):
        with self.assertRaises(ValueError):
            years(0)


class TestArbitrage(unittest.TestCase):
    def test_implied_rate_identity(self):
        self.assertAlmostEqual(implied_rate(100, 110, 365), math.log(1.1), places=10)

    def test_futures_fair_round_trip(self):
        f = futures_fair(1000, 180, 0.35)
        self.assertAlmostEqual(implied_rate(1000, f, 180), 0.35, places=10)

    def test_basis_go_when_above_hurdle(self):
        # ۲۰٪ بازده دوره‌ای در ۶۰ روز ⇒ سالانه بسیار بالاتر از سد ۳۵٪
        r = basis_opportunity(1000, 1220, 60, 0.35)
        self.assertTrue(r["go"])
        self.assertGreater(r["annualized_pct"], 35.0)

    def test_basis_no_go_when_below_hurdle(self):
        r = basis_opportunity(1000, 1005, 365, 0.35)
        self.assertFalse(r["go"])
        self.assertLess(r["annualized_pct"], 35.0)

    def test_box_payoff_is_strike_gap(self):
        r = box_spread(300, 420, 180, 560, 1200, 1500, 45)
        self.assertEqual(r["payoff"], 300)
        self.assertGreater(r["annualized_pct"], 0)

    def test_box_rejects_inverted_strikes(self):
        with self.assertRaises(ValueError):
            box_spread(300, 420, 180, 560, 1500, 1200, 45)

    def test_parity_gap_sign(self):
        # C − P بزرگ‌تر از S − PV(K) ⇒ فرصت conversion
        r = put_call_parity(500, 100, 1000, 1000, 30, 0.0)
        self.assertGreater(r["gap"], 0)
        self.assertEqual(r["direction"], "conversion")

    def test_tabei_min_yield_hand_computation(self):
        r = tabei_min_yield(50000, 0, 62500, 365)
        # بدون کارمزد: ۲۵٪ در یک سال (کمی کمتر با کارمزد خرید و فروش)
        self.assertLess(r["period_return_pct"], 25.0)
        self.assertGreater(r["period_return_pct"], 23.0)

    def test_covered_call_premium_annualized(self):
        r = covered_call(7000, 7400, 220, 30)
        self.assertGreater(r["premium_annualized_pct"], 30.0)
        self.assertIn("upside_capped_at_pct", r)


class TestSizing(unittest.TestCase):
    def test_position_size_respects_cap(self):
        r = position_size(1_000_000_000, 150_000_000, risk_pct=0.20)
        self.assertEqual(r["contracts"], 1)
        self.assertGreaterEqual(r["free_cash"], 0)
        self.assertEqual(r["min_cash_ratio"], 0.40)

    def test_score_penalizes_illiquidity(self):
        base = {"annualized_pct": 60.0, "liquidity_contracts_per_day": 500, "spread_pct": 0.005}
        illq = dict(base, liquidity_contracts_per_day=5)
        self.assertGreater(score(base), score(illq))


class TestRunner(unittest.TestCase):
    def test_runner_sorts_and_reports_errors(self):
        sc = Scenario(name="t", rows=[
            {"name": "bad", "kind": "nope"},
            {"name": "weak", "kind": "basis", "spot": 1000, "future": 1005, "days": 365},
            {"name": "strong", "kind": "basis", "spot": 1000, "future": 1220, "days": 60},
        ], hurdle=0.35)
        out = run_scenario(sc)
        self.assertEqual(out[0]["name"], "strong")
        self.assertIn("error", out[-1])

    def test_missing_key_is_error_not_crash(self):
        sc = Scenario(name="t", rows=[{"name": "x", "kind": "box", "call_low": 1}], hurdle=0.35)
        out = run_scenario(sc)
        self.assertIn("error", out[0])

    def test_fee_constant_is_expected_value(self):
        self.assertAlmostEqual(FEE_FUND_ETF, 0.0012, places=10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
