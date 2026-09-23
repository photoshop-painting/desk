#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون‌های برگهٔ شاهد زنده — همه آفلاین: سرور نمونهٔ محلی جای سرویس واقعی می‌نشیند.

هیچ آزمونی به اینترنت نمی‌رود و هیچ آزمونی پرونده‌های اصلی `data/witness-live.*` را دست نمی‌زند.
"""

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE = pathlib.Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import demo_day  # noqa: E402
import datafeed  # noqa: E402

DESK_FILE = BASE.parent / "desk" / "market-demo.json"      # نسبی: روی هر رایانهٔ دیگری هم کار می‌کند


class QuoteHandler(BaseHTTPRequestHandler):
    """سرور نمونهٔ محلی: برای هر نماد یک قیمت متفاوت می‌دهد (تا سنجهٔ «نرخ واحد» گیر نکند)."""

    protocol_version = "HTTP/1.1"
    same_for_all = False
    hits = 0

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        symbol = (parse_qs(u.query).get("symbol") or [""])[0]
        type(self).hits += 1
        table = {"اهرم": 19_500.0, "فولاد": 6_980.0, "کگل": 9_810.0, "خساپا": 2_090.0,
                 "طلا": 45_700_000.0, "شپنا": 12_450.0, "وبملت": 5_380.0}
        if type(self).same_for_all:
            price = 7_000.0                            # عیناً یک نرخ برای همه (آزمون سنجهٔ صداقت)
        else:
            price = table.get(symbol, 5_000.0) + (type(self).hits % 7) * 0.5
        body = json.dumps({"data": [{"pl": price, "symbol": symbol}]},
                          ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class Fixture(unittest.TestCase):
    """یک سرور محلی برای همهٔ آزمون‌های این پرونده."""

    same_for_all = False

    @classmethod
    def setUpClass(cls):
        QuoteHandler.same_for_all = cls.same_for_all
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), QuoteHandler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.profile = {"name": "test-local", "label": "سرور نمونهٔ آزمون", "cost": "رایگان",
                       "url_template": cls.base + "/quote?symbol={symbol}",
                       "json_path": "data.0.pl", "key_header": "", "key_query_name": "",
                       "env_key": ""}

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def tmpdir(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return pathlib.Path(d.name)


class ProbeTests(Fixture):
    def test_probe_reads_price_with_hash_and_latency(self):
        probes = demo_day.probe(self.profile, ["اهرم", "فولاد"], timeout=4)
        self.assertEqual([p["ok"] for p in probes], [True, True])
        for p in probes:
            self.assertEqual(len(p["sha256"]), 64)
            self.assertGreater(p["bytes"], 10)
            self.assertGreaterEqual(p["latency_ms"], 0)
            self.assertIn("آزمایشی محلی", p["source"])
            self.assertIn("data", p["snippet"])
        self.assertNotEqual(probes[0]["price"], probes[1]["price"])

    def test_probe_reports_dead_endpoint_honestly(self):
        dead = dict(self.profile, url_template="http://127.0.0.1:9/quote?symbol={symbol}")
        probes = demo_day.probe(dead, ["اهرم"], timeout=2)
        self.assertFalse(probes[0]["ok"])
        self.assertEqual(probes[0]["sha256"], "")
        self.assertTrue(probes[0]["error"])

    def test_empty_url_template_is_a_clear_error(self):
        probes = demo_day.probe(dict(self.profile, url_template=""), ["اهرم"], timeout=2)
        self.assertFalse(probes[0]["ok"])
        self.assertIn("قالب نشانی", probes[0]["error"])

    def test_key_is_not_leaked_into_the_sheet(self):
        prof = dict(self.profile, url_template=self.base + "/quote?key={key}&symbol={symbol}")
        probes = demo_day.probe(prof, ["اهرم"], timeout=4, key="SECRETKEY123")
        blob = json.dumps(probes, ensure_ascii=False)
        self.assertIn("SECRETKEY123", probes[0]["url"])   # در نشانی هست (لازم است)
        self.assertNotIn("SECRETKEY123", blob.replace(probes[0]["url"], ""))  # ولی جای دیگری نه


class DecisionTests(Fixture):
    def test_decision_uses_app_path_and_labels_sources(self):
        probes = demo_day.probe(self.profile, ["اهرم", "فولاد"], timeout=4)
        d = demo_day.decide(probes, path=DESK_FILE)
        self.assertTrue(d["ready"], d.get("reason"))
        chosen = d["chosen"]
        self.assertIn("answer_num", chosen)
        self.assertEqual(len(chosen["ladder"]), 3)
        self.assertTrue(any(c.get("agree") for c in chosen["checks"]))
        prov = {p["field"]: p for p in chosen["provenance"]}
        if "spot" in prov:
            self.assertEqual(prov["spot"]["source"], "زنده از سرویس")
        if "future" in prov:
            self.assertEqual(prov["future"]["source"], "از پروندهٔ پایه")
        note = demo_day.mixed_sources_note(chosen)
        self.assertIn("فرصت معاملاتی امروز", note)

    def test_decision_without_any_price_is_not_ready(self):
        d = demo_day.decide([], path=DESK_FILE)
        self.assertFalse(d["ready"])
        self.assertTrue(d["reason"])

    def test_missing_base_file_is_reported(self):
        d = demo_day.decide([], path="/tmp/definitely-not-here.json")
        self.assertFalse(d["ready"])
        self.assertIn("خوانده نشد", d["reason"])


class SingleRateGuard(Fixture):
    """اگر سرویس برای همهٔ نمادها یک نرخ بدهد، باید صریح گفته شود نه اینکه عدد ساخته شود."""

    same_for_all = True

    def test_identical_prices_are_flagged(self):
        probes = demo_day.probe(self.profile, ["اهرم", "فولاد", "کگل"], timeout=4)
        d = demo_day.decide(probes, path=DESK_FILE)
        messages = " ".join(d["snapshot"]["messages"])
        self.assertIn("نرخ واحد", messages)
        self.assertEqual(d["snapshot"]["status"], "partial")


class SheetTests(Fixture):
    def test_sheet_files_and_honest_limits(self):
        out = self.tmpdir()
        doc = demo_day.build(profile=self.profile, symbols=["اهرم", "فولاد"], timeout=4,
                             path=DESK_FILE, page=out / "w.html", md=out / "w.md",
                             json_path=out / "w.json")
        html = (out / "w.html").read_text(encoding="utf-8")
        md = (out / "w.md").read_text(encoding="utf-8")
        stored = json.loads((out / "w.json").read_text(encoding="utf-8"))
        self.assertIn("Masoud Mojarabian", html)
        self.assertIn("اثبات نمی‌کند", html)
        self.assertIn("اثر انگشت", html)
        self.assertIn("خوراک آزمایشی محلی", html)
        self.assertIn("اثبات نمی‌کند", md)
        self.assertIn("هر عدد از کجا آمد", md)
        self.assertEqual(stored["page_hash"], doc["page_hash"])
        self.assertTrue(doc["limits"])

    def test_page_hash_is_reproducible_from_the_json(self):
        out = self.tmpdir()
        doc = demo_day.build(profile=self.profile, symbols=["اهرم"], timeout=4, path=DESK_FILE,
                             page=out / "w.html", md=out / "w.md", json_path=out / "w.json")
        core = json.dumps({"probes": doc["probes"], "decision": doc["decision"]},
                          sort_keys=True, ensure_ascii=False)
        self.assertEqual(doc["page_hash"], hashlib.sha256(core.encode("utf-8")).hexdigest()[:16])

    def test_no_price_still_builds_an_honest_sheet(self):
        out = self.tmpdir()
        dead = dict(self.profile, url_template="http://127.0.0.1:9/quote?symbol={symbol}")
        doc = demo_day.build(profile=dead, symbols=["اهرم"], timeout=2, path=DESK_FILE,
                             page=out / "w.html", md=out / "w.md", json_path=out / "w.json")
        self.assertFalse(doc["decision"]["ready"])
        md = (out / "w.md").read_text(encoding="utf-8")
        self.assertIn("تصمیم نمونه ساخته نشد", md)
        self.assertIn("اثبات نمی‌کند", md)


class Helpers(Fixture):
    def test_symbols_of_desk_file(self):
        names = demo_day.symbols_of(DESK_FILE)
        self.assertGreaterEqual(len(names), 3)
        self.assertEqual(len(names), len(set(names)))

    def test_build_url_quotes_symbol_and_hides_missing_key(self):
        cfg = {"url_template": "http://x/{symbol}?k={key}"}
        self.assertEqual(demo_day.build_url(cfg, "فولاد", ""), "http://x/%D9%81%D9%88%D9%84%D8%A7%D8%AF?k=")
        self.assertNotIn("{key}", demo_day.build_url(cfg, "فولاد", "abc"))


class CliTests(unittest.TestCase):
    """خط فرمان با --out، بدون دست‌زدن به پرونده‌های اصلی."""

    def test_cli_json_and_out_dir(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, "demo_day.py", "--json", "--out", d,
                                "--symbols", "اهرم", "--timeout", "2"],
                               cwd=str(BASE), capture_output=True, text=True, timeout=120)
            self.assertIn(r.returncode, (0, 1), r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            doc = json.loads(r.stdout)
            self.assertIn("probes", doc)
            self.assertTrue((pathlib.Path(d) / "witness-live.json").exists())
            self.assertTrue((pathlib.Path(d) / "witness-live.md").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
