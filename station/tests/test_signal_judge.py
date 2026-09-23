#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون «داوری سیگنال بیرونی» (signal_judge.py).

بی‌اینترنت و سریع: همهٔ عددها از موتور محلی درمی‌آید و برگه در پوشهٔ موقت نوشته می‌شود.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GUI = HERE.parent
sys.path.insert(0, str(GUI))

import signal_judge as sj  # noqa: E402

BASIS = {"spot": 20000, "future": 22800, "days": 50}
WEAK_BASIS = {"spot": 20000, "future": 21000, "days": 50}
COVERED = {"spot": 7000, "strike": 7400, "premium": 220, "days": 30}
WEAK_COVERED = {"spot": 7000, "strike": 7400, "premium": 120, "days": 30}
PARITY = {"call": 420, "put": 380, "spot": 9000, "strike": 9000, "days": 30}


class TestJudge(unittest.TestCase):
    def test_good_signal_survives(self):
        j = sj.judge("basis", BASIS, hurdle=0.39)
        self.assertTrue(j["ok"])
        self.assertEqual("می‌ماند", j["verdict"])
        self.assertGreater(j["edge_pp"], 0)

    def test_weak_signal_dies_with_reason(self):
        j = sj.judge("covered", WEAK_COVERED, hurdle=0.39)
        self.assertEqual("می‌افتد", j["verdict"])
        self.assertTrue(any("نرخ سد" in r for r in j["reasons"]))

    def test_high_hurdle_kills_basis(self):
        self.assertEqual("می‌افتد", sj.judge("basis", BASIS, hurdle=2.0)["verdict"])

    def test_parity_rejected_structurally(self):
        j = sj.judge("parity", PARITY)
        self.assertEqual("می‌افتد", j["verdict"])
        self.assertTrue(any("استقراضی" in r for r in j["reasons"]))
        self.assertIsNone(j["annualized_pct"])

    def test_liquidity_gate_and_spread_gate(self):
        j = sj.judge("basis", {**BASIS, "liquidity_contracts_per_day": 5, "spread_pct": 0.08})
        self.assertEqual("می‌افتد", j["verdict"])
        joined = " ".join(j["reasons"])
        self.assertIn("نقدشوندگی", joined)
        self.assertIn("اسپرد", joined)

    def test_implausible_number_caught(self):
        j = sj.judge("basis", {"spot": 20000, "future": 320000, "days": 50})
        self.assertTrue(any("غیرواقعی" in r or "جابه‌جا" in r for r in j["reasons"]))

    def test_unknown_kind(self):
        self.assertFalse(sj.judge("چیزی", {})["ok"])

    def test_missing_input_is_reported(self):
        j = sj.judge("basis", {"spot": 20000})
        self.assertFalse(j["ok"])
        self.assertIn("ورودی", j["detail"])

    def test_claim_comparison(self):
        j = sj.judge("covered", COVERED, hurdle=0.39, claimed_return_pct=100)
        self.assertIn("ابزار شما", j["claim_note"])
        self.assertLess(j["annualized_pct"], 100)

    def test_fingerprint_stable_and_sensitive(self):
        a = sj.judge("basis", BASIS, hurdle=0.39)
        b = sj.judge("basis", BASIS, hurdle=0.39)
        c = sj.judge("basis", BASIS, hurdle=0.40)
        self.assertEqual(a["fingerprint"], b["fingerprint"])
        self.assertNotEqual(a["fingerprint"], c["fingerprint"])


class TestBreakEven(unittest.TestCase):
    def test_break_even_is_the_flip_point(self):
        j = sj.judge("basis", BASIS, hurdle=0.39)
        be = j["break_even"]["value"]
        self.assertIsNotNone(be)
        below = sj.judge("basis", {**BASIS, "future": be * 0.98}, hurdle=0.39)
        above = sj.judge("basis", {**BASIS, "future": be * 1.02}, hurdle=0.39)
        self.assertEqual("می‌افتد", below["verdict"])
        self.assertEqual("می‌ماند", above["verdict"])

    def test_break_even_for_covered_premium(self):
        j = sj.judge("covered", WEAK_COVERED, hurdle=0.39)
        be = j["break_even"]["value"]
        self.assertGreater(be, WEAK_COVERED["premium"])
        self.assertEqual("می‌ماند", sj.judge("covered", {**WEAK_COVERED, "premium": be * 1.05},
                                             hurdle=0.39)["verdict"])

    def test_no_break_even_when_decision_cannot_flip(self):
        j = sj.judge("parity", PARITY)
        self.assertIsNone((j["break_even"] or {}).get("value"))


class TestMarginCall(unittest.TestCase):
    def test_margin_call_matches_hand_calc(self):
        mc = sj.margin_call(contracts=10, margin_per_contract=2_000_000,
                            notional_per_contract=10_000_000, maintenance=0.70)
        self.assertTrue(mc["ok"])
        # ۲٬۰۰۰٬۰۰۰ × ۰٫۳۰ ÷ ۱۰٬۰۰۰٬۰۰۰ = ۶٪
        self.assertAlmostEqual(6.0, mc["move_pct"], places=3)
        self.assertAlmostEqual(6_000_000.0, mc["money_at_risk"], places=2)

    def test_more_contracts_scale_the_money_not_the_percent(self):
        a = sj.margin_call(contracts=1, margin_per_contract=2_000_000, notional_per_contract=10_000_000)
        b = sj.margin_call(contracts=5, margin_per_contract=2_000_000, notional_per_contract=10_000_000)
        self.assertAlmostEqual(a["move_pct"], b["move_pct"], places=6)
        self.assertAlmostEqual(a["money_at_risk"] * 5, b["money_at_risk"], places=2)

    def test_price_level_in_direction(self):
        up = sj.margin_call(contracts=1, margin_per_contract=2_000_000, notional_per_contract=10_000_000,
                            current_price=20000, direction="long")
        down = sj.margin_call(contracts=1, margin_per_contract=2_000_000, notional_per_contract=10_000_000,
                              current_price=20000, direction="short")
        self.assertLess(up["price_level"], 20000)
        self.assertGreater(down["price_level"], 20000)

    def test_maintenance_ratio_shifts_distance(self):
        loose = sj.margin_call(contracts=1, margin_per_contract=2_000_000,
                               notional_per_contract=10_000_000, maintenance=0.50)
        tight = sj.margin_call(contracts=1, margin_per_contract=2_000_000,
                               notional_per_contract=10_000_000, maintenance=0.90)
        self.assertGreater(loose["move_pct"], tight["move_pct"])

    def test_notional_derived_from_initial_ratio(self):
        j = sj.judge("basis", BASIS, hurdle=0.39, margin_per_contract=2_000_000, contracts=2)
        # ارزش قرارداد = وجه تضمین ÷ ۲۰٪ → ۱۰٬۰۰۰٬۰۰۰ ؛ فاصله = ۰٫۳ × ۲٬۰۰۰٬۰۰۰ ÷ ۱۰٬۰۰۰٬۰۰۰
        self.assertAlmostEqual(6.0, j["margin"]["move_pct"], places=3)


class TestTwoMethodsAndSize(unittest.TestCase):
    def test_hand_method_close_to_engine(self):
        for kind, params in (("basis", BASIS), ("covered", COVERED), ("tabei", {
                "stock_price": 50000, "put_price": 200, "strike": 62500, "days": 90})):
            j = sj.judge(kind, params, hurdle=0.39)
            self.assertIsNotNone(j["hand"]["annualized_pct"], kind)
            self.assertLess(abs(j["hand_diff_pp"]), 5.0, f"اختلاف دو روش در {kind} زیاد است")

    def test_size_uses_risk_cap(self):
        j = sj.judge("basis", BASIS, hurdle=0.39, capital=100_000_000, margin_per_contract=2_000_000)
        self.assertEqual(10, j["size"]["contracts"])


class TestSheet(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_sheet_files_written(self):
        j = sj.judge("basis", BASIS, hurdle=0.39, margin_per_contract=2_000_000, contracts=2,
                     current_price=20000, claimed_return_pct=190)
        h, m = sj.build_sheet(j, self.tmp / "v.html", self.tmp / "v.md")
        html = h.read_text(encoding="utf-8")
        for needle in ("داوری", "می‌ماند", "نقطهٔ برگشت", "مارجین‌کال", j["fingerprint"],
                       "Masoud Mojarabian", "ابزار شما"):
            self.assertIn(needle, html)
        self.assertIn("مارجین‌کال", m.read_text(encoding="utf-8"))

    def test_sheet_of_rejected_signal(self):
        j = sj.judge("parity", PARITY)
        h, _ = sj.build_sheet(j, self.tmp / "r.html", self.tmp / "r.md")
        self.assertIn("می‌افتد", h.read_text(encoding="utf-8"))


class TestCli(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run([sys.executable, str(GUI / "signal_judge.py"), *args],
                              capture_output=True, text=True, timeout=180)

    def test_json_output(self):
        r = self._run("--kind", "basis", "--params", json.dumps(BASIS), "--json")
        self.assertEqual(0, r.returncode, r.stderr[-400:])
        d = json.loads(r.stdout)
        self.assertEqual("می‌ماند", d["verdict"])

    def test_missing_kind_exits_2(self):
        self.assertEqual(2, self._run("--json").returncode)

    def test_unknown_kind_reports(self):
        r = self._run("--kind", "basis", "--params", '{"spot":1}', "--json")
        self.assertEqual(2, r.returncode)

    def test_file_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sig.json"
            p.write_text(json.dumps({"kind": "covered", "params": COVERED, "hurdle": 0.39}),
                         encoding="utf-8")
            r = self._run("--file", str(p), "--json")
            self.assertEqual(0, r.returncode, r.stderr[-400:])
            self.assertIn("verdict", json.loads(r.stdout))

    def test_version(self):
        self.assertIn("signal_judge", self._run("--version").stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
