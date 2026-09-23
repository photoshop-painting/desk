#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون‌های strategy_audit — کتابخانهٔ راهبردها و حسابرسی عددها.

قفل‌های اصلی:
  ۱) هر راهبرد قاعدهٔ بستن، ریسک و منبع دارد (چیزی بدون «کِی ببندم» منتشر نمی‌شود).
  ۲) فرمول‌های مالی با هویت‌های ریاضی خوانده می‌شوند: تساوی پوت-کال، رفت‌وبرگشت نوسان ضمنی،
     احتمال مدل‌محور در حالت «سرِ پول» ≈ نیم، و حرکت مورد انتظار.
  ۳) عدد راهبردهای عددی با موتور ایستگاه یکی است و محاسبهٔ دستی دوم تأییدش می‌کند.
  ۴) هیچ عددی بدون برچسب روش منتشر نمی‌شود.
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

GUI = Path(__file__).resolve().parents[1]
if str(GUI) not in sys.path:
    sys.path.insert(0, str(GUI))

import strategy_audit as sa  # noqa: E402
import investor_test as inv  # noqa: E402


class TestLibraryShape(unittest.TestCase):
    def test_every_strategy_is_complete(self):
        self.assertGreaterEqual(len(sa.STRATEGIES), 8)
        ids = [s["id"] for s in sa.STRATEGIES]
        self.assertEqual(len(ids), len(set(ids)), "شناسهٔ راهبردها تکراری است")
        for s in sa.STRATEGIES:
            for field in ("name", "en", "class", "idea", "when", "requires", "closing",
                          "risks", "refs"):
                self.assertTrue(s.get(field), f"{s['id']}: فیلد {field} خالی است")
            self.assertGreaterEqual(len(s["closing"]), 2, f"{s['id']}: قاعدهٔ بستن کم است")
            self.assertGreaterEqual(len(s["risks"]), 2, f"{s['id']}: ریسک‌ها کم است")

    def test_closing_rules_are_plenty_in_total(self):
        total = sum(len(s["closing"]) for s in sa.STRATEGIES)
        self.assertGreaterEqual(total, 25, "مجموع قواعد بستن کم است")

    def test_closing_rules_say_when_to_get_out(self):
        for s in sa.STRATEGIES:
            joined = " ".join(s["closing"])
            self.assertTrue(any(w in joined for w in ("بستن", "ببند", "بفروش", "برداشت سود",
                                                      "سررسید", "توقف")),
                            f"{s['id']}: قاعدهٔ خروج صریح ندارد")


class TestFinancialIdentities(unittest.TestCase):
    def test_put_call_parity_identity(self):
        s, k, days, r, sigma = 100.0, 110.0, 90.0, 0.30, 0.55
        t = days / 365.0
        lhs = sa.bs_call(s, k, days, r, sigma) - sa.bs_put(s, k, days, r, sigma)
        rhs = s - k * math.exp(-r * t)
        self.assertAlmostEqual(lhs, rhs, places=6)

    def test_implied_vol_round_trip(self):
        s, k, days, r, sigma = 7_000.0, 7_600.0, 45.0, 0.35, 0.50
        price = sa.bs_call(s, k, days, r, sigma)
        got = sa.implied_vol(price, s, k, days, r, "call")
        self.assertTrue(got["ok"], got.get("detail"))
        self.assertAlmostEqual(got["sigma"], sigma, places=3)
        self.assertLess(abs(got["gap_pct"]), 0.5)

    def test_implied_vol_out_of_range_is_refused(self):
        low = sa.implied_vol(1e-9, 100.0, 100.0, 30.0, 0.30, "call")
        high = sa.implied_vol(9e9, 100.0, 100.0, 30.0, 0.30, "call")
        self.assertFalse(low["ok"])
        self.assertFalse(high["ok"])
        self.assertIn("بازه", low["detail"])

    def test_prob_under_behaves_sensibly(self):
        """سرِ پول نزدیک نیم، با اعمال بالاتر بیشتر، با اعمال پایین‌تر کمتر."""
        atm = sa.prob_under(100.0, 100.0, 45.0, 0.0, 0.40)
        self.assertLess(abs(atm - 0.5), 0.05)          # اختلاف کوچک از جملهٔ دریفت
        self.assertGreater(sa.prob_under(100.0, 130.0, 45.0, 0.0, 0.40), atm)
        self.assertLess(sa.prob_under(100.0, 70.0, 45.0, 0.0, 0.40), atm)

    def test_expected_move_hand_math(self):
        self.assertAlmostEqual(sa.expected_move(100.0, 365.0, 0.50), 50.0, places=6)


class TestAudits(unittest.TestCase):
    def test_numeric_audits_agree_with_engine(self):
        for sid in ("basis", "covered_call", "tabei", "box", "parity"):
            a = sa.audit_strategy(sid)
            self.assertTrue(a["ok"], f"{sid}: حسابرسی انجام نشد")
            self.assertIsNotNone(a["engine_value"] if sid != "parity" else True)
            if sid != "parity":
                self.assertEqual(a["hand_agrees"], True,
                                 f"{sid}: محاسبهٔ دستی با موتور نمی‌خواند")

    def test_covered_call_has_model_probability(self):
        a = sa.audit_strategy("covered_call")
        mp = a["model_probability"]
        self.assertIsNotNone(mp)
        self.assertTrue(mp["iv"]["ok"], mp["iv"].get("detail"))
        self.assertGreater(mp["prob_under_strike_pct"], 0)
        self.assertLess(mp["prob_under_strike_pct"], 100)
        self.assertAlmostEqual(mp["prob_under_strike_pct"] + mp["prob_assigned_pct"],
                               100.0, places=1)
        self.assertIn("پیش‌بینی", mp["detail"])

    def test_basis_has_no_probability_claim(self):
        a = sa.audit_strategy("basis")
        self.assertIn("احتمال", a["model_probability"]["detail"])
        self.assertIn("قفل", a["model_probability"]["detail"])

    def test_non_numeric_strategy_is_flagged(self):
        a = sa.audit_strategy("income_no_capital")
        self.assertFalse(a["ok"])
        self.assertIn("عدد بازار", a["detail"])

    def test_audit_numbers_match_engine_directly(self):
        row = inv._pick("basis", inv.fallback_rows())
        eng = inv.ladder_for(row)["annualized_pct"]
        a = sa.audit_strategy("basis")
        self.assertAlmostEqual(a["engine_value"], eng, places=3)


class TestTables(unittest.TestCase):
    def test_table_rows_cover_all_strategies(self):
        doc = sa.build(write=False)
        self.assertEqual(len(doc["table"]), len(sa.STRATEGIES))

    def test_parity_shows_yes_no_not_a_percent(self):
        doc = sa.build(write=False)
        parity = [t for t in doc["table"] if t["id"] == "parity"][0]
        self.assertIn(parity["value"], ("بله", "نه"))

    def test_every_number_has_a_method_label(self):
        doc = sa.build(write=False)
        for t in doc["table"]:
            self.assertTrue(t["method"], f"{t['id']}: روش عدد خالی است")

    def test_markdown_contains_closing_and_references(self):
        doc = sa.build(write=False)
        self.assertIn("### قاعدهٔ بستن موقعیت", doc["md_text"])
        self.assertIn("مسیر مطالعهٔ پیشنهادی", sa.index_md(doc) or doc["index_md"])
        self.assertIn("محدودیت‌های صادقانه", doc["ref_md"])
        self.assertIn("Masoud Mojarabian", doc["ref_md"])   # امضای سازنده
        self.assertIn("هیچ درصد «برد تاریخی»", doc["ref_md"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
