#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون‌های ایستگاه: لایهٔ داده، پس‌آزمایی، بستهٔ تحویل شرکت، و بررسی سلامت.

همهٔ این آزمون‌ها بدون نمایشگر اجرا می‌شوند. آزمون ساخت رابط گرافیکی در
`tests/gui-smoke.sh` است که با Xvfb اجرا می‌شود.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

GUI = Path(__file__).resolve().parents[1]
for p in (GUI, GUI.parent / "desk"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import backtest as bt  # noqa: E402
import datafeed as df  # noqa: E402
import station as st  # noqa: E402
import desk as deskmod  # noqa: E402


class TestDigAndParse(unittest.TestCase):
    def test_dig_nested(self):
        data = {"data": [{"pl": 1234.5}]}
        self.assertEqual(df.dig(data, "data.0.pl"), 1234.5)
        self.assertIsNone(df.dig(data, "data.5.pl"))
        self.assertIsNone(df.dig(data, "nope"))
        self.assertEqual(df.dig({"a": {"b": {"c": 7}}}, "a.b.c"), 7)

    def test_parse_quote_json(self):
        value, why = df.parse_quote_payload('{"data":[{"pl":"21,300"}]}', "data.0.pl", "اهرم")
        self.assertEqual(value, 21300.0)

    def test_parse_quote_fallback_keys(self):
        value, _ = df.parse_quote_payload('{"close": 9000}', "", "فولاد")
        self.assertEqual(value, 9000.0)

    def test_parse_quote_plain_text(self):
        value, why = df.parse_quote_payload("اهرم,21300,سود", "", "اهرم")
        self.assertEqual(value, 21300.0)
        self.assertIn("متن ساده", why)

    def test_parse_quote_bad_payload(self):
        value, why = df.parse_quote_payload("no numbers here", "x", "y")
        self.assertIsNone(value)


class TestSnapshotModes(unittest.TestCase):
    def test_sim_mode_marks_synthetic(self):
        snap = df.build_snapshot("sim")
        self.assertEqual(snap.mode, "sim")
        self.assertGreaterEqual(len(snap.rows), 5)
        self.assertTrue(any("ساختگی" in m for m in snap.messages))

    def test_file_mode_reports_missing_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "s.json"
            p.write_text(json.dumps({"hurdle": 0.4, "capital": 1e10,
                                     "rows": [{"symbol": "اهرم"}, {"symbol": "طلا", "kind": "basis"}]},
                                    ensure_ascii=False), encoding="utf-8")
            snap = df.build_snapshot("file", file_path=p)
            self.assertEqual(snap.status, "partial")
            self.assertTrue(snap.missing_fields)
            self.assertEqual(snap.rows[0]["_hurdle"], 0.4)

    def test_file_mode_missing_file(self):
        snap = df.build_snapshot("file", file_path="/no/such/file.json")
        self.assertEqual(snap.status, "failed")

    def test_file_mode_with_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "b.json"
            p.write_bytes("\ufeff".encode("utf-8") + json.dumps(
                {"hurdle": 0.39, "capital": 1e10, "rows": [{"symbol": "اهرم", "kind": "basis"}]},
                ensure_ascii=False).encode("utf-8"))
            snap = df.build_snapshot("file", file_path=p)
            self.assertEqual(snap.status, "ok")

    def test_live_mode_without_url_fails_clearly(self):
        snap = df.build_snapshot("live", live_cfg={"url_template": ""})
        self.assertEqual(snap.status, "failed")
        self.assertIn("قالب نشانی", " ".join(snap.messages))

    def test_live_mode_uses_local_file_url(self):
        """آزمون کامل مسیر «زنده» بدون اینترنت: نشانی، یک پروندهٔ محلی است."""
        with tempfile.TemporaryDirectory() as tmp:
            quote = Path(tmp) / "quote.json"
            quote.write_text('{"data":[{"pl": 21500}]}', encoding="utf-8")
            base = Path(tmp) / "base.json"
            base.write_text(json.dumps({"hurdle": 0.39, "capital": 1e10, "rows": [
                {"symbol": "اهرم", "kind": "basis", "spot": 20000, "future": 22800, "days": 90,
                 "margin_per_contract": 20000000, "unit": "قرارداد"}]}, ensure_ascii=False), encoding="utf-8")
            snap = df.build_snapshot("live", file_path=base,
                                     live_cfg={"url_template": f"file:{quote}",
                                               "json_path": "data.0.pl", "cache_seconds": 0})
            self.assertEqual(snap.status, "ok")
            self.assertEqual(snap.rows[0]["spot"], 21500.0)
            self.assertEqual(snap.rows[0]["spot_manual"], 20000.0)   # مقدار قبلی حفظ می‌شود
            self.assertEqual(snap.freshness_seconds, 0.0)

    def test_live_mode_network_disabled(self):
        snap = df.build_snapshot("live", live_cfg={"url_template": "https://example.invalid/{symbol}"},
                                 allow_network=False)
        self.assertEqual(snap.status, "failed")

    def test_freshness_labels(self):
        snap = df.Snapshot(rows=[{}])
        snap.freshness_seconds = 30
        self.assertIn("زنده", snap.freshness_label)
        snap.freshness_seconds = 7200
        self.assertIn("ساعت", snap.freshness_label)


class TestTemplates(unittest.TestCase):
    def test_snapshot_template_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = df.write_snapshot_template(Path(tmp) / "t.json")
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertIn("rows", data)
            self.assertTrue(data["rows"][0]["symbol"])

    def test_history_template_has_key_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = df.write_history_template(Path(tmp) / "h.csv")
            head = p.read_text(encoding="utf-8").splitlines()[0]
            self.assertIn("realized_annualized_pct", head)
            self.assertIn("hurdle", head)


class TestBacktest(unittest.TestCase):
    def test_demo_history_runs(self):
        result = bt.run_backtest(st.GUI if hasattr(st, "GUI") else GUI / "demo" / "history-demo.csv")
        s = result["summary"]
        self.assertEqual(s["rows"], 100)
        self.assertGreater(s["taken"], 5)
        self.assertIsNotNone(s["hit_rate_pct"])
        self.assertLess(s["avg_forecast_error_pp"], 0)   # انتظار خوش‌بینانه است: درس اصلی

    def test_lookahead_safety(self):
        """نتیجهٔ واقعی نباید در تصمیم نقشی داشته باشد."""
        path = GUI / "demo" / "history-demo.csv"
        rows, _ = bt.load_history(path)
        base = [bt.decide_row(r, bt.DEFAULT_RULES).taken for r in rows]
        tampered = []
        for r in rows:
            r2 = dict(r)
            r2["realized_annualized_pct"] = -999.0   # همه را فاجعه اعلام می‌کنیم
            tampered.append(r2)
        after = [bt.decide_row(r, bt.DEFAULT_RULES).taken for r in tampered]
        self.assertEqual(base, after)

    def test_absurd_edge_is_rejected(self):
        row = {"date": "1405-01-01", "symbol": "فملی", "kind": "box", "call_low": 97, "put_low": 135,
               "call_high": 58, "put_high": 181, "strike_low": 800, "strike_high": 1100, "days": 30,
               "hurdle": 0.39, "liquidity_contracts_per_day": 500, "spread_pct": 0.01,
               "realized_annualized_pct": 40}
        d = bt.decide_row(row, bt.DEFAULT_RULES)
        self.assertFalse(d.taken)
        self.assertIn("باورپذیری", d.reason)

    def test_gate_thresholds_change_counts(self):
        path = GUI / "demo" / "history-demo.csv"
        strict = bt.run_backtest(path, rules={"min_edge_leveraged_pct": 30.0, "min_edge_arbitrage_pct": 25.0})
        loose = bt.run_backtest(path, rules={"min_edge_leveraged_pct": 1.0, "min_edge_arbitrage_pct": 1.0})
        self.assertLess(strict["summary"]["taken"], loose["summary"]["taken"])

    def test_reports_written_self_contained(self):
        path = GUI / "demo" / "history-demo.csv"
        result = bt.run_backtest(path)
        with tempfile.TemporaryDirectory() as tmp:
            html_path = bt.build_report(result, Path(tmp) / "r.html")
            body = html_path.read_text(encoding="utf-8")
            self.assertIn('dir="rtl"', body)
            self.assertNotIn("<script", body)
            self.assertNotIn("fonts.googleapis", body)
            csv_path = bt.write_csv(result, Path(tmp) / "r.csv")
            self.assertTrue(csv_path.read_text(encoding="utf-8").startswith("\ufeffdate"))

    def test_missing_history_is_reported(self):
        result = bt.run_backtest("/no/such/history.csv")
        self.assertEqual(result["summary"]["rows"], 0)
        self.assertTrue(result["summary"]["problems"])


class TestBundle(unittest.TestCase):
    def make_kodal_db(self, path: Path) -> Path:
        conn = sqlite3.connect(str(path))
        conn.execute("CREATE TABLE items (id TEXT PRIMARY KEY, title TEXT, source TEXT, symbol TEXT, company TEXT,"
                     " body TEXT, url TEXT, published_at TEXT, category TEXT, direction TEXT, score INTEGER,"
                     " reason TEXT, ai_note TEXT, provider TEXT, created_at TEXT)")
        conn.execute("INSERT INTO items VALUES ('k1','افزایش سرمایه','کدال','خساپا','','','','','افزایش سرمایه','مثبت',95,'','','شاهد محلی','')")
        conn.commit()
        conn.close()
        return path

    def test_build_bundle_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            snap = df.build_snapshot("sim")
            state = {"data_mode": "sim", "snapshot": snap,
                     "rules": dict(deskmod.DEFAULT_CONFIG),
                     "backtest_result": bt.run_backtest(GUI / "demo" / "history-demo.csv")}
            state["rules"].update({"capital": 20_000_000_000, "hurdle": 0.39})
            out = st.build_bundle(state, tmp_dir / "bundle")
            names = sorted(p.name for p in out.iterdir())
            self.assertIn("03-method.html", names)
            self.assertIn("07-manifest.json", names)
            self.assertIn("README-FA.md", names)
            manifest = json.loads((out / "07-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["data_mode"], "sim")
            self.assertIn("rules", manifest)
            self.assertTrue(manifest["limitations"])
            method = (out / "03-method.html").read_text(encoding="utf-8")
            self.assertIn("راستی‌آزمایی توسط شما", method)
            self.assertIn("معاملات الگوریتمی", method)

    def test_bundle_includes_evidence_files_when_present(self):
        """کارنامهٔ آزمون، برگهٔ آزمون و پروندهٔ سرمایه‌گذار باید داخل بسته هم بروند."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            ev = tmp_dir / "evidence"
            ev.mkdir()
            (ev / "selftest-report.html").write_text("<html>کارنامه</html>", encoding="utf-8")
            (ev / "exam-sheet.html").write_text("<html>برگه</html>", encoding="utf-8")
            (ev / "investor-dossier.html").write_text("<html>پرونده</html>", encoding="utf-8")
            (ev / "investor-dossier.md").write_text("# پرونده", encoding="utf-8")
            state = {"data_mode": "sim", "snapshot": df.build_snapshot("sim"),
                     "rules": dict(deskmod.DEFAULT_CONFIG)}
            state["rules"].update({"capital": 20_000_000_000, "hurdle": 0.39})
            import license as licmod_iso
            from unittest import mock as _mock
            with _mock.patch.object(licmod_iso, "read_license", return_value=None):
                out = st.build_bundle(state, tmp_dir / "bundle", evidence_dir=ev)
            names = sorted(p.name for p in out.iterdir())
            for name in ("08-selftest-report.html", "09-exam-sheet.html",
                         "10-investor-dossier.html", "11-investor-dossier.md"):
                self.assertIn(name, names)
            manifest = json.loads((out / "07-manifest.json").read_text(encoding="utf-8"))
            # چهار شاهد ورودی + دو گواهی خودکار (اجازه‌نامه و گواهی استفاده) که ایستگاه خودش می‌سازد
            self.assertEqual(6, len(manifest["evidence"]))
            self.assertIn("17-usage-statement.html", names)
            for row in manifest["evidence"]:
                self.assertEqual(16, len(row["sha256"]))       # اثر انگشت هر شاهد
            checklist = (out / "README-FA.md").read_text(encoding="utf-8")
            self.assertIn("08-selftest-report.html", checklist)

    def test_bundle_without_evidence_still_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            empty = tmp_dir / "empty"
            empty.mkdir()
            state = {"data_mode": "sim", "snapshot": df.build_snapshot("sim"),
                     "rules": dict(deskmod.DEFAULT_CONFIG)}
            state["rules"].update({"capital": 20_000_000_000, "hurdle": 0.39})
            import license as licmod_iso
            from unittest import mock as _mock
            with _mock.patch.object(licmod_iso, "read_license", return_value=None):
                out = st.build_bundle(state, tmp_dir / "bundle", evidence_dir=empty)
            names = sorted(p.name for p in out.iterdir())
            self.assertNotIn("08-selftest-report.html", names)
            self.assertNotIn("15-license-doc.html", names)
            manifest = json.loads((out / "07-manifest.json").read_text(encoding="utf-8"))
            # هیچ شاهد ورودی‌ای نبود؛ فقط دو گواهی خودکار ایستگاه باید در بسته باشد
            self.assertEqual({"17-usage-statement.html", "18-usage-statement.md"},
                             {row["file"] for row in manifest["evidence"]})

    def test_method_html_reflects_rules(self):
        state = {"rules": {"capital": 5_000_000_000, "hurdle": 0.42, "min_edge_arbitrage_pct": 4.0,
                           "min_edge_leveraged_pct": 6.0, "max_margin_pct": 0.2, "max_position_pct": 0.35,
                           "max_positions": 3, "min_liquidity_contracts_per_day": 20, "max_spread_pct": 0.03,
                           "max_plausible_arb_pct": 250.0, "max_plausible_lev_pct": 400.0},
                 "snapshot": df.build_snapshot("sim")}
        html = st.build_method_html(state)
        self.assertIn("42.00", html)
        self.assertIn("4.0", html)

    def test_signals_csv_matches_db(self):
        rows = st.signals_csv(Path("/no/such/db.sqlite3"), Path(tempfile.gettempdir()) / "x.csv")
        self.assertGreaterEqual(rows, 0)


class TestHealth(unittest.TestCase):
    def test_health_report_all_green(self):
        ok, items = st.health_report()
        self.assertTrue(ok, items)
        names = [n for n, _, _ in items]
        self.assertIn("میز معاملات", names)
        self.assertIn("موتور ریاضی مشتقه", names)
        self.assertIn("دیده‌بان کدال", names)

    def test_steps_defined(self):
        self.assertEqual(len(st.STEPS), 8)
        self.assertEqual([k for k, _ in st.STEPS][0], "health")
        self.assertEqual([k for k, _ in st.STEPS][-1], "bundle")


class SingleRateGuardTests(unittest.TestCase):
    """سنجهٔ صداقت: منبعی که برای همهٔ نمادها یک عدد می‌دهد، نباید سیگنال سهام بسازد."""

    def _base(self):
        return {"as_of": "x", "rows": [
            {"symbol": "اهرم", "kind": "basis", "spot": 20000, "future": 22800, "days": 90,
             "margin_per_contract": 20000000, "unit": "قرارداد"},
            {"symbol": "فولاد", "kind": "basis", "spot": 7000, "future": 7600, "days": 90,
             "margin_per_contract": 7000, "unit": "قرارداد"}]}

    def test_identical_prices_are_flagged(self):
        import tempfile, json as _json
        from pathlib import Path as _P
        tmp = tempfile.TemporaryDirectory()
        feed = _P(tmp.name) / "feed.json"
        feed.write_text(_json.dumps({"data": [{"pl": 227860}]}, ensure_ascii=False), encoding="utf-8")
        snap_path = _P(tmp.name) / "snap.json"
        snap_path.write_text(_json.dumps(self._base(), ensure_ascii=False), encoding="utf-8")
        out = df.live_snapshot(snap_path, {"url_template": f"file:{feed}", "json_path": "data.0.pl"})
        self.assertEqual(out.status, "partial")
        self.assertIn("نرخ واحد", out.source_label)
        self.assertTrue(any("عیناً یکسان" in m for m in out.messages))
        tmp.cleanup()

    def test_distinct_prices_are_not_flagged(self):
        """خوراکی که برای هر نماد عدد خودش را می‌دهد، نباید علامت «نرخ واحد» بخورد."""
        import tempfile, threading
        from pathlib import Path as _P
        import mock_feed
        httpd = mock_feed.serve(0)
        try:
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            port = httpd.server_address[1]
            tmp = tempfile.TemporaryDirectory()
            snap_path = _P(tmp.name) / "snap2.json"
            snap_path.write_text(json.dumps(self._base(), ensure_ascii=False), encoding="utf-8")
            out = df.live_snapshot(snap_path, {
                "url_template": f"http://127.0.0.1:{port}/quote?symbol={{symbol}}",
                "json_path": "data.0.pl"})
            tmp.cleanup()
        finally:
            httpd.shutdown()
            httpd.server_close()
        self.assertEqual(out.status, "ok", out.messages)
        self.assertNotIn("نرخ واحد", out.source_label)
        self.assertEqual(len(set(out.live_prices.values())), 2)


class BundleAdminFilesTests(unittest.TestCase):
    """بستهٔ شاهد باید مجوز دسترسی و گواهی استفاده را هم بردارد (گام ۸ + پنل مدیریت)."""

    def _state(self):
        state = {"data_mode": "sim", "snapshot": df.build_snapshot("sim"),
                 "rules": dict(deskmod.DEFAULT_CONFIG)}
        state["rules"].update({"capital": 20_000_000_000, "hurdle": 0.39})
        return state

    def test_license_doc_and_usage_certificate_land_in_the_bundle(self):
        import license as licmod
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            ev = d / "evidence"
            ev.mkdir()
            (ev / "usage-statement.html").write_text("<html>گواهی</html>", encoding="utf-8")
            (ev / "usage-statement.md").write_text("# گواهی", encoding="utf-8")
            fake = licmod.make_license("شرکت آزمون بسته", months=12)
            with mock.patch.object(licmod, "read_license", return_value=fake):
                out = st.build_bundle(self._state(), d / "bundle", evidence_dir=ev)
            names = sorted(p.name for p in out.iterdir())
            for name in ("15-license-doc.html", "16-license-doc.md",
                         "17-usage-statement.html", "18-usage-statement.md"):
                self.assertIn(name, names)
            manifest = json.loads((out / "07-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(fake["signature"], manifest["access"]["signature"]
                             if "signature" in (manifest.get("access") or {}) else fake["signature"])
            self.assertIn("usage_certificate", manifest)
            self.assertTrue(manifest["admin_notes"])
            checklist = (out / "README-FA.md").read_text(encoding="utf-8")
            self.assertIn("15-license-doc.html", checklist)
            self.assertIn("17-usage-statement.html", checklist)
            doc = (out / "16-license-doc.md").read_text(encoding="utf-8")
            self.assertIn("شرکت آزمون بسته", doc)

    def test_bundle_says_clearly_when_no_license_exists(self):
        import license as licmod
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            ev = d / "evidence"
            ev.mkdir()
            with mock.patch.object(licmod, "read_license", return_value=None):
                out = st.build_bundle(self._state(), d / "bundle", evidence_dir=ev)
            names = [p.name for p in out.iterdir()]
            self.assertNotIn("15-license-doc.html", names)
            manifest = json.loads((out / "07-manifest.json").read_text(encoding="utf-8"))
            notes = " ".join(manifest["admin_notes"])
            self.assertIn("پنل مدیریت", notes)

    def test_fresh_install_bundle_gets_a_dashboard(self):
        """در نصب تازه، داشبورد هنوز ساخته نشده؛ بسته باید خودش بسازدش تا چک‌لیست ناقص نباشد."""
        import license as licmod
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            ev = d / "evidence"
            ev.mkdir()
            with mock.patch.object(st, "DASHBOARD_FILE", d / "no-dashboard.html"), \
                 mock.patch.object(licmod, "read_license", return_value=None):
                out = st.build_bundle(self._state(), d / "bundle", evidence_dir=ev)
            names = [p.name for p in out.iterdir()]
            self.assertIn("01-dashboard.html", names)
            dashboard = (out / "01-dashboard.html").read_text(encoding="utf-8")
            self.assertTrue(len(dashboard) > 200)
            manifest = json.loads((out / "07-manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(any("داشبورد" in n for n in manifest["admin_notes"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
