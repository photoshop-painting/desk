#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون‌های واحد دیده‌بان کدال — فقط کتابخانهٔ استاندارد (unittest)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import kodal_alert as ka  # noqa: E402


class TestClassify(unittest.TestCase):
    def test_capital_increase_rule(self):
        cat, direction, score, why = ka.classify("افزایش سرمایه از محل تجدید ارزیابی دارایی‌ها", "")
        self.assertEqual(cat, "افزایش سرمایه")
        self.assertEqual(direction, "مثبت")
        self.assertGreaterEqual(score, 80)
        self.assertIn("قرارداد مشتقه", why)

    def test_halt_symbol_is_negative(self):
        cat, direction, score, _ = ka.classify("توقف نماد به دلیل ابهام در اطلاعات", "")
        self.assertEqual(cat, "توقف و بازگشایی نماد")
        self.assertEqual(direction, "منفی")

    def test_legal_risk_rule(self):
        cat, direction, _, _ = ka.classify("دعوی حقوقی و جریمهٔ مالیاتی", "")
        self.assertEqual(cat, "دعاوی و ریسک حقوقی")
        self.assertEqual(direction, "منفی")

    def test_lexicon_when_no_rule_matches(self):
        cat, direction, score, _ = ka.classify("اطلاعیهٔ شمارهٔ ۱۲۳", "شرکت از رشد درآمد خبر داد")
        self.assertEqual(cat, "سایر")
        self.assertEqual(direction, "مثبت")
        self.assertGreater(score, 0)

    def test_numeric_bonus_increases_score(self):
        _, _, s_plain, _ = ka.classify("انعقاد قرارداد جدید", "")
        _, _, s_number, _ = ka.classify("انعقاد قرارداد جدید به ارزش ۱۲ میلیون یورو", "")
        self.assertGreater(s_number, s_plain)

    def test_recency_bonus_and_penalty(self):
        now = datetime.now(timezone.utc)
        _, _, fresh, _ = ka.classify("انعقاد قرارداد جدید", "", 1.0, now - timedelta(hours=2))
        _, _, old, _ = ka.classify("انعقاد قرارداد جدید", "", 1.0, now - timedelta(days=6))
        self.assertGreater(fresh, old)

    def test_score_bounds(self):
        for title in ["توقف نماد", "افزایش سرمایه", "", "خبر بی‌ربط"]:
            _, _, score, _ = ka.classify(title, title * 3)
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 100)

    def test_source_weight(self):
        _, _, s_norm, _ = ka.classify("توقف نماد", "", 1.0)
        _, _, s_codal, _ = ka.classify("توقف نماد", "", 1.15)
        self.assertGreaterEqual(s_codal, s_norm)


class TestDates(unittest.TestCase):
    def test_jalali_known_dates(self):
        self.assertEqual(ka.g2j(2026, 9, 22), (1405, 6, 31))
        self.assertEqual(ka.g2j(2024, 1, 1), (1402, 10, 11))

    def test_jalali_string_shape(self):
        s = ka.jalali_str(datetime(2026, 9, 22, 8, 5))
        self.assertTrue(s.startswith("1405/06/31"))


class TestStore(unittest.TestCase):
    def test_insert_and_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ka.Store(Path(tmp) / "t.sqlite3")
            item = ka.Item(title="افزایش سرمایه", symbol="خساپا", score=80)
            self.assertTrue(store.add(item))
            self.assertFalse(store.add(item))  # همان کلید، بار دوم رد می‌شود
            store.commit()
            self.assertEqual(store.count(), 1)
            rows = store.recent(10)
            self.assertEqual(rows[0].title, "افزایش سرمایه")

    def test_min_score_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ka.Store(Path(tmp) / "t.sqlite3")
            store.add(ka.Item(title="کم‌اهمیت", score=10))
            store.add(ka.Item(title="مهم", score=90))
            store.commit()
            self.assertEqual(len(store.recent(10, min_score=50)), 1)

    def test_run_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ka.Store(Path(tmp) / "t.sqlite3")
            store.log_run("demo", 7)
            n = store.conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            self.assertEqual(n, 1)


class TestFeeds(unittest.TestCase):
    def test_parse_demo_rss(self):
        text = (Path(__file__).resolve().parents[1] / "demo" / "news.rss").read_text(encoding="utf-8")
        items = ka.parse_feed(text, "خبر نمونه", ka.DEFAULT_CONFIG)
        self.assertGreaterEqual(len(items), 4)
        self.assertTrue(all(i.title for i in items))
        self.assertTrue(any("توقف" in i.title or "بازگشایی" in i.title for i in items))

    def test_bad_xml_returns_empty(self):
        self.assertEqual(ka.parse_feed("<rss><channel>", "خراب", ka.DEFAULT_CONFIG), [])


class TestSources(unittest.TestCase):
    def test_load_json_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.json"
            p.write_text(json.dumps([{"title": "افزایش سرمایه", "symbol": "فولاد"}], ensure_ascii=False), encoding="utf-8")
            items = ka.load_file_source(str(p), ka.DEFAULT_CONFIG)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].category, "افزایش سرمایه")

    def test_load_csv_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.csv"
            p.write_text("title,symbol\nتوقف نماد,وبملت\n", encoding="utf-8")
            items = ka.load_file_source(str(p), ka.DEFAULT_CONFIG)
            self.assertEqual(items[0].direction, "منفی")

    def test_missing_file_is_safe(self):
        self.assertEqual(ka.load_file_source("/no/such/file.json", ka.DEFAULT_CONFIG), [])

    def test_http_file_scheme(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.txt"
            p.write_text("سلام", encoding="utf-8")
            self.assertEqual(ka.http_get(f"file:{p}", ka.DEFAULT_CONFIG), "سلام")


class TestPipeline(unittest.TestCase):
    def test_demo_pipeline_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = json.loads(json.dumps(ka.DEFAULT_CONFIG, ensure_ascii=False))
            cfg["db_path"] = str(Path(tmp) / "demo.sqlite3")
            cfg["report_path"] = str(Path(tmp) / "report.html")
            cfg["min_score_to_alert"] = 40
            store = ka.Store(cfg["db_path"])
            items = ka.run_pipeline(cfg, store, ["demo"])
            self.assertGreaterEqual(len(items), 5)
            scores = [i.score for i in items]
            self.assertEqual(scores, sorted(scores, reverse=True))
            path = ka.build_report(store.recent(100), cfg, cfg["report_path"])
            body = path.read_text(encoding="utf-8")
            self.assertIn('dir="rtl"', body)
            self.assertIn("دیده‌بان", body)
            self.assertIn(items[0].title[:20], body)

    def test_report_has_no_external_assets(self):
        cfg = ka.DEFAULT_CONFIG
        with tempfile.TemporaryDirectory() as tmp:
            path = ka.build_report([ka.Item(title="نمونه", score=50)], cfg, Path(tmp) / "r.html")
            body = path.read_text(encoding="utf-8")
            self.assertNotIn("http://cdn", body)
            self.assertNotIn("<script", body)
            self.assertNotIn("fonts.googleapis", body)

class TestTitlePriority(unittest.TestCase):
    def test_title_beats_body_noise(self):
        cat, _, _, _ = ka.classify("شفاف‌سازی در خصوص نوسان قیمت سهم",
                                   "شرکت اعلام کرد برنامهٔ افزایش سرمایه در دست بررسی است", 1.0)
        self.assertEqual(cat, "شفاف‌سازی")

    def test_reopening_is_positive(self):
        cat, direction, _, _ = ka.classify("بازگشایی نماد پس از شفاف‌سازی", "")
        self.assertEqual(cat, "توقف و بازگشایی نماد")
        self.assertEqual(direction, "مثبت")

    def test_dividend_not_misread_as_halt(self):
        cat, _, _, _ = ka.classify("تقسیم سود نقدی هر سهم و زمان برگزاری مجمع",
                                   "تاریخ توقف نماد پیش از مجمع اعلام خواهد شد", 1.0)
        self.assertEqual(cat, "تقسیم سود")


class TestCli(unittest.TestCase):
    def test_selftest_command(self):
        self.assertEqual(ka.main(["selftest"]), 0)

    def test_version_command(self):
        self.assertEqual(ka.main(["version"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
