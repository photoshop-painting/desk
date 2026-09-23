#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون‌های واحد میز معاملات — فقط کتابخانهٔ استاندارد."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE_MARKET = Path(__file__).resolve().parents[1] / "market-demo.json"

import desk as dk  # noqa: E402


def temp_cfg(tmp: str, **over) -> dict:
    cfg = json.loads(json.dumps(dk.DEFAULT_CONFIG, ensure_ascii=False))
    cfg["desk_db"] = str(Path(tmp) / "desk.sqlite3")
    cfg["report_path"] = str(Path(tmp) / "dash.html")
    cfg.update(over)
    return cfg


def make_kodal_db(tmp: str, rows: list[tuple]) -> Path:
    p = Path(tmp) / "kodal.sqlite3"
    conn = sqlite3.connect(str(p))
    conn.execute("CREATE TABLE items (id TEXT PRIMARY KEY, title TEXT, source TEXT, symbol TEXT, company TEXT,"
                 " body TEXT, url TEXT, published_at TEXT, category TEXT, direction TEXT, score INTEGER,"
                 " reason TEXT, ai_note TEXT, provider TEXT, created_at TEXT)")
    for i, (title, symbol, score) in enumerate(rows):
        conn.execute("INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (f"k{i}", title, "کدال", symbol, "", "", "https://codal.ir/x", "", "افزایش سرمایه",
                      "مثبت", score, "", "", "شاهد محلی", ""))
    conn.commit()
    conn.close()
    return p


class TestScoutBridge(unittest.TestCase):
    def test_scout_loads(self):
        scout = dk.load_scout()
        self.assertTrue(hasattr(scout, "box_spread"))

    def test_math_for_tabei_row(self):
        res = dk.math_for_row({"symbol": "خ", "kind": "tabei", "stock_price": 2500, "put_price": 12,
                               "strike": 3125, "days": 90}, 0.39)
        self.assertTrue(res["go"])
        self.assertGreater(res["annualized_pct"], 39.0)

    def test_math_for_bad_row_reports(self):
        with self.assertRaises(ValueError):
            dk.math_for_row({"symbol": "خ", "kind": "box", "call_low": 1}, 0.39)

    def test_math_unknown_kind_reports(self):
        with self.assertRaises(ValueError):
            dk.math_for_row({"symbol": "خ", "kind": "nope"}, 0.39)


class TestScan(unittest.TestCase):
    def test_scan_demo_market(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = temp_cfg(tmp)
            desk = dk.Desk(cfg["desk_db"])
            sigs = dk.scan_market(Path(dk.BASE) / "market-demo.json", cfg, desk)
            self.assertGreaterEqual(len(sigs), 6)
            scores = [s.score_pp for s in sigs]
            self.assertEqual(scores, sorted(scores, reverse=True))
            self.assertTrue(any(s.status == "pending" for s in sigs))
            self.assertTrue(any(s.status == "rejected" for s in sigs))

    def test_illiquid_row_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = temp_cfg(tmp)
            desk = dk.Desk(cfg["desk_db"])
            sig = dk.Signal(sid="x1", symbol="شپنا", kind="box", name="n", annualized_pct=200.0,
                            score_pp=100.0, go=True,
                            detail={"liquidity_contracts_per_day": 3, "spread_pct": 0.01},
                            margin_per_contract=1000)
            sig = dk.apply_risk_gates(sig, cfg, desk)
            self.assertEqual(sig.status, "rejected")
            self.assertIn("نقدشوندگی", sig.gate_note)

    def test_wide_spread_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = temp_cfg(tmp)
            desk = dk.Desk(cfg["desk_db"])
            sig = dk.Signal(sid="x2", symbol="الف", kind="box", name="n", annualized_pct=200.0,
                            score_pp=100.0, go=True,
                            detail={"liquidity_contracts_per_day": 200, "spread_pct": 0.09},
                            margin_per_contract=1000)
            sig = dk.apply_risk_gates(sig, cfg, desk)
            self.assertEqual(sig.status, "rejected")
            self.assertIn("اسپرد", sig.gate_note)

    def test_big_margin_blocks_position(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = temp_cfg(tmp)
            desk = dk.Desk(cfg["desk_db"])
            sig = dk.Signal(sid="x3", symbol="ب", kind="basis", name="n", annualized_pct=120.0,
                            score_pp=60.0, go=True,
                            detail={"liquidity_contracts_per_day": 200, "spread_pct": 0.01},
                            margin_per_contract=cfg["capital"])  # بیشتر از سقف ۲۰ درصد
            sig = dk.apply_risk_gates(sig, cfg, desk)
            self.assertEqual(sig.contracts, 0)
            self.assertEqual(sig.status, "rejected")

    def test_margin_math_respects_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = temp_cfg(tmp)
            desk = dk.Desk(cfg["desk_db"])
            sig = dk.Signal(sid="x4", symbol="ج", kind="basis", name="n", annualized_pct=120.0,
                            score_pp=60.0, go=True,
                            detail={"liquidity_contracts_per_day": 200, "spread_pct": 0.01},
                            margin_per_contract=100_000_000)
            sig = dk.apply_risk_gates(sig, cfg, desk)
            self.assertEqual(sig.contracts, 10)  # ۵ میلیارد × ۲۰٪ ÷ ۱۰۰ میلیون
            self.assertLessEqual(sig.margin_locked, cfg["capital"] * cfg["max_margin_pct"])

    def test_status_preserved_on_rescan(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = temp_cfg(tmp)
            desk = dk.Desk(cfg["desk_db"])
            market = Path(dk.BASE) / "market-demo.json"
            sigs = dk.scan_market(market, cfg, desk)
            target = next(s for s in sigs if s.status == "pending")
            desk.decide(target.sid, "approved", "تست")
            dk.scan_market(market, cfg, desk)
            self.assertEqual(desk.get(target.sid).status, "approved")


class TestAlertsBridge(unittest.TestCase):
    def test_read_and_match_alerts(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_kodal_db(tmp, [("افزایش سرمایه ۴۵۰ درصدی", "خساپا", 96),
                                    ("توقف نماد", "وبملت", 86)])
            alerts = dk.read_alerts(p, 60)
            self.assertEqual(len(alerts), 2)
            matched = dk.related_alerts("خساپا", alerts)
            self.assertEqual(len(matched), 1)
            self.assertIn("افزایش سرمایه", matched[0]["title"])

    def test_missing_db_is_safe(self):
        self.assertEqual(dk.read_alerts("/no/such.sqlite3", 60), [])

    def test_recheck_tasks_for_uncovered_symbol(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = temp_cfg(tmp)
            desk = dk.Desk(cfg["desk_db"])
            p = make_kodal_db(tmp, [("افزایش سرمایه", "شپدیس", 92)])
            tasks = dk.recheck_tasks(cfg, desk, p, Path(dk.BASE) / "market-demo.json")
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0]["symbol"], "شپدیس")

    def test_covered_symbol_not_in_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = temp_cfg(tmp)
            desk = dk.Desk(cfg["desk_db"])
            p = make_kodal_db(tmp, [("خبر مهم", "خساپا", 92)])
            self.assertEqual(dk.recheck_tasks(cfg, desk, p, Path(dk.BASE) / "market-demo.json"), [])


class TestWorkflow(unittest.TestCase):
    def test_approve_records_decision_and_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = temp_cfg(tmp)
            desk = dk.Desk(cfg["desk_db"])
            sigs = dk.scan_market(Path(dk.BASE) / "market-demo.json", cfg, desk)
            target = next(s for s in sigs if s.status == "pending")
            self.assertTrue(desk.decide(target.sid, "approved", "ریسک پذیرفته شد"))
            self.assertEqual(desk.get(target.sid).status, "approved")
            self.assertEqual(len(desk.decisions(10)), 1)
            packet = dk.order_packet(desk.get(target.sid))
            self.assertIn(target.symbol, packet)
            self.assertIn("انسان", packet)
            self.assertIn("سود تضمینی وجود ندارد", packet)

    def test_reject_unknown_id_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = temp_cfg(tmp)
            desk = dk.Desk(cfg["desk_db"])
            self.assertFalse(desk.decide("nope", "approved", ""))

    def test_locked_margin_tracks_approvals(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = temp_cfg(tmp)
            desk = dk.Desk(cfg["desk_db"])
            sigs = dk.scan_market(Path(dk.BASE) / "market-demo.json", cfg, desk)
            target = next(s for s in sigs if s.status == "pending")
            before = desk.locked_margin()
            desk.decide(target.sid, "approved", "")
            self.assertGreater(desk.locked_margin(), before)


class TestDashboard(unittest.TestCase):
    def test_dashboard_is_self_contained_and_rtl(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = temp_cfg(tmp)
            desk = dk.Desk(cfg["desk_db"])
            sigs = dk.scan_market(Path(dk.BASE) / "market-demo.json", cfg, desk)
            path = dk.build_dashboard(desk, cfg, cfg["report_path"], [{"symbol": "شپدیس", "reason": "بدون داده",
                                                                       "alert": {"title": "خبر"}}])
            body = path.read_text(encoding="utf-8")
            self.assertIn('dir="rtl"', body)
            self.assertIn(sigs[0].sid, body)
            self.assertNotIn("<script", body)
            self.assertNotIn("fonts.googleapis", body)
            self.assertIn("معاملات الگوریتمی خودکار", body)

    def test_credit_present(self):
        cfg = json.loads(json.dumps(dk.DEFAULT_CONFIG))
        with tempfile.TemporaryDirectory() as tmp:
            path = dk.build_dashboard(dk.Desk(Path(tmp) / "d.sqlite3"), cfg, Path(tmp) / "d.html", [])
            self.assertIn("Mojarabian", path.read_text(encoding="utf-8"))


class TestPortfolioSizing(unittest.TestCase):
    def test_units_follow_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = temp_cfg(tmp)
            desk = dk.Desk(cfg["desk_db"])
            sigs = dk.scan_market(Path(dk.BASE) / "market-demo.json", cfg, desk)
            units = {s.kind: s.unit for s in sigs}
            self.assertEqual(units["basis"], "قرارداد")
            self.assertEqual(units["tabei"], "سهم")
            self.assertEqual(units["covered_call"], "سهم")
            self.assertEqual(units["parity"], "سهم")
            self.assertEqual(units["box"], "قرارداد")

    def test_per_position_cap_is_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = temp_cfg(tmp)
            desk = dk.Desk(cfg["desk_db"])
            sigs = dk.scan_market(Path(dk.BASE) / "market-demo.json", cfg, desk)
            data = json.loads((Path(dk.BASE) / "market-demo.json").read_text(encoding="utf-8"))
            budget = data["capital"] * cfg["max_margin_pct"]
            for s in sigs:
                if s.status == "pending":
                    self.assertLessEqual(s.margin_locked, budget * cfg["max_position_pct"] + 1)

    def test_total_allocation_within_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = temp_cfg(tmp)
            desk = dk.Desk(cfg["desk_db"])
            sigs = dk.scan_market(Path(dk.BASE) / "market-demo.json", cfg, desk)
            data = json.loads((Path(dk.BASE) / "market-demo.json").read_text(encoding="utf-8"))
            cap = data["capital"] * cfg["max_margin_pct"]
            total = sum(s.margin_locked for s in sigs if s.status == "pending")
            self.assertLessEqual(total, cap + 1)
            self.assertGreaterEqual(len([s for s in sigs if s.status == "pending"]), 2)

    def test_budget_exhaustion_marks_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = temp_cfg(tmp, capital=1_000_000, max_margin_pct=0.2, max_position_pct=1.0)
            market = Path(tmp) / "m.json"
            row = {"symbol": "الف", "kind": "basis", "spot": 100, "future": 130, "days": 60,
                   "margin_per_contract": 60_000, "liquidity_contracts_per_day": 500, "spread_pct": 0.01}
            row2 = dict(row, symbol="ب")
            market.write_text(json.dumps({"hurdle": 0.39, "capital": 1_000_000, "rows": [row, row2]}),
                              encoding="utf-8")
            desk = dk.Desk(cfg["desk_db"])
            sigs = dk.scan_market(market, cfg, desk)
            statuses = sorted(s.status for s in sigs)
            self.assertIn("pending", statuses)
            self.assertIn("rejected", statuses)


class TestApprovalGuard(unittest.TestCase):
    def test_approve_blocks_beyond_max_positions(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = temp_cfg(tmp, max_positions=1)
            cfg_file = Path(tmp) / "config.json"
            cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
            market = Path(BASE_MARKET)
            args = type("A", (), {})()
            args.config = str(cfg_file)
            args.market = str(market)
            args.kodal_db = None
            self.assertEqual(dk.cmd_run(args), 0)
            desk = dk.Desk(cfg["desk_db"])
            pending = [s for s in desk.all("pending")]
            self.assertGreaterEqual(len(pending), 2)
            first, second = pending[0], pending[1]
            a1 = type("B", (), {"config": str(cfg_file), "sid": first.sid, "note": "", "force": False})()
            self.assertEqual(dk.cmd_decide(a1, "approved"), 0)
            a2 = type("B", (), {"config": str(cfg_file), "sid": second.sid, "note": "", "force": False})()
            self.assertEqual(dk.cmd_decide(a2, "approved"), 3)          # بدون --force رد می‌شود
            a3 = type("B", (), {"config": str(cfg_file), "sid": second.sid, "note": "آگاهانه", "force": True})()
            self.assertEqual(dk.cmd_decide(a3, "approved"), 0)


class TestCli(unittest.TestCase):
    def test_selftest(self):
        self.assertEqual(dk.main(["selftest"]), 0)

    def test_version(self):
        self.assertEqual(dk.main(["version"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
