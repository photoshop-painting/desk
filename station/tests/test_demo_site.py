"""آزمون «نمونهٔ ثابت نمایشی» روی Hugging Face Static Space.

چه می‌سنجیم: (۱) بستهٔ نمایشی از ضبط واقعی درست ساخته می‌شود (رابط + خروجی‌ها + لایهٔ ثابت)؛
(۲) هیچ رمزی در آن نیست؛ (۳) **واقعاً کار می‌کند**: روی یک سرور محلی سرو می‌شود و آزمون‌گر
`tools/check_demo_site.mjs` (که خودش با jsdom گام‌ها را کلیک می‌کند) همهٔ ۲۲ بررسی را سبز می‌دهد؛
(۴) ابزارهای نشر (`activate_demo_site.py`/`activate_hf.py`) معناشان درست است.

این آزمون به شبکه بیرونی نیاز ندارد؛ سرور محلی روی درگاه آزاد خودش بالا می‌آید.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]                 # .../money/gui
TOOLING_NEEDED = ("deploy/huggingface/make_demo_site.py", "deploy/huggingface/activate_demo_site.py")


# ── نگهبان بستهٔ تحویلی ─────────────────────────────────────────────────────
# این آزمون به ابزارهای «ساخت بسته» در پوشهٔ deploy نیاز دارد. آن ابزارها عمداً داخل بستهٔ
# تحویلی شرکت نیستند؛ پس اگر نبودند، باید تمیز «رد» شود نه اینکه هنگام بارگذاری بترکد
# (وگرنه «گزارش عیب‌یابی» در خودِ بسته، آزمون‌ها را سرخ نشان می‌دهد).
def _tooling_ready() -> tuple[bool, str]:
    for rel in TOOLING_NEEDED:
        if not (BASE / rel).exists():
            return False, f"ابزار ساخت در این بسته نیست: {rel}"
    return True, ""


TOOLING_OK, WHY_NO_TOOLING = _tooling_ready()

sys.path.insert(0, str(BASE / "deploy"))
sys.path.insert(0, str(BASE / "deploy" / "huggingface"))
try:
    from security_scan import find_secret_literals
except Exception as _e:                                     # noqa: BLE001
    find_secret_literals = None
    _IMPORT_ERROR = f"{type(_e).__name__}: {_e}" 

HF = BASE / "deploy" / "huggingface"
RECORDING = BASE / "demo" / "static-recording.json"
def jsdom_available() -> bool:
    """jsdom از افزوده‌های بیرونی است و در پیمان‌های کاری (snapshot) نگه داشته نمی‌شود."""
    for base in (Path("/home/user"), Path(__file__).resolve().parents[1]):
        if (base / "node_modules" / "jsdom").exists():
            return True
    return False


WHY_NO_JSDOM = "jsdom نصب نیست (برای آزمون‌های مرورگری لازم است؛ در بستهٔ تحویلی نصب می‌شود)"


CHECKER = BASE / "tools" / "check_demo_site.mjs"


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@unittest.skipUnless(TOOLING_OK, WHY_NO_TOOLING)
class TestDemoBundle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import make_demo_site as M
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "iran-desk-demo"
        cls.manifest = M.build(RECORDING, cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_recording_is_checked_in_and_rich(self):
        rec = json.loads(RECORDING.read_text(encoding="utf-8"))
        self.assertGreater(len(rec), 30, "ضبط باید پاسخ‌های زیادی داشته باشد")
        self.assertTrue(any(k.startswith("GET /api/") for k in rec))
        self.assertTrue(any(k.startswith("POST /api/") for k in rec))
        import make_demo_site as M
        clean = M.sanitize(rec)
        self.assertTrue(all(v["status"] < 400 for v in clean.values()), "پاسخ خطا نباید در دمو بماند")
        self.assertLess(len(clean), len(rec) + 1)          # پاک‌سازی چیزی را خراب نمی‌کند

    def test_bundle_structure(self):
        for rel in ("README.md", "index.html", "app/index.html", "app/app.js", "app/recording.js",
                    "app/static-backend.js", "app/file-map.js", "DEMO-MANIFEST.json"):
            self.assertTrue((self.out / rel).exists(), rel)
        self.assertGreaterEqual(self.manifest["output_pages"], 8)
        self.assertGreaterEqual(self.manifest["responses"], 30)

    def test_employer_guide_ships_with_the_bundle(self):
        """راهنمای کارفرما باید داخل نمونه باشد و از صفحهٔ نخست پیوند بخورد."""
        g = self.out / "guide.html"
        self.assertTrue(g.exists(), "راهنمای کارفرما در نمونه نیست")
        body = g.read_text(encoding="utf-8")
        self.assertIn("راهنمای", body)
        self.assertNotIn('href="http://', body, "پیوند ناامن در راهنما")
        home = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="guide.html"', home)
        self.assertEqual(self.manifest.get("guide"), "guide.html")

    def test_space_card_is_static(self):
        t = (self.out / "README.md").read_text(encoding="utf-8")
        self.assertTrue(t.startswith("---\n"))
        for needle in ("sdk: static", "title:", "Masoud Mojarabian", "09126630554"):
            self.assertIn(needle, t)

    def test_shim_has_no_browser_only_globals(self):
        """لایهٔ ثابت باید در jsdom هم کار کند، پس Response/Headers مرورگر را لازم ندارد."""
        t = (self.out / "app" / "static-backend.js").read_text(encoding="utf-8")
        self.assertNotIn("new Response(", t)
        self.assertNotIn("new Headers(", t)
        for needle in ("window.fetch", "__DEMO_RECORDING__", "/api/gate/status", "نمونهٔ ثابت"):
            self.assertIn(needle, t)

    def test_no_secret_and_no_token_in_the_public_bundle(self):
        for f in self.out.rglob("*"):
            if f.is_file():
                self.assertEqual([], find_secret_literals(f), f"{f} مشکوک است")
                text = f.read_text(encoding="utf-8", errors="ignore")
                self.assertNotIn('"token"', text.replace(" ", ""), f"{f} توکن دارد")
                self.assertNotIn("station_gate", text, f"{f} کوکی نشست دارد")

    def test_files_links_are_rewritten_to_saved_pages(self):
        t = (self.out / "app" / "index.html").read_text(encoding="utf-8")
        self.assertIn("static-backend.js", t)
        self.assertIn("recording.js", t)
        fmap = json.loads((self.out / "DEMO-MANIFEST.json").read_text(encoding="utf-8"))["file_map"]
        self.assertIn("offer", fmap)
        self.assertEqual("offer.html", fmap["offer"])
        self.assertTrue((self.out / "files" / "offer.html").exists())
        self.assertTrue((self.out / "files" / "walkthrough.txt").exists())

    def test_home_page_says_the_honest_things(self):
        t = (self.out / "index.html").read_text(encoding="utf-8")
        for needle in ("نمونهٔ ثابت", "سود تضمینی", "سفارش خودکار", "Masoud Mojarabian", "app/index.html"):
            self.assertIn(needle, t)


@unittest.skipUnless(TOOLING_OK, WHY_NO_TOOLING)
class TestDemoServers(unittest.TestCase):
    """بسته را روی سرور محلی می‌گذاریم و همان آزمون‌گر زنده را می‌زنیم."""

    @classmethod
    def setUpClass(cls):
        import make_demo_site as M
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "demo"
        M.build(RECORDING, cls.out)
        cls.port = free_port()
        cls.srv = subprocess.Popen([sys.executable, "-m", "http.server", str(cls.port),
                                    "--bind", "127.0.0.1"], cwd=str(cls.out),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2.5)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        try:
            cls.srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.srv.kill()
        cls.tmp.cleanup()

    @unittest.skipUnless(jsdom_available(), WHY_NO_JSDOM)
    def test_checker_is_all_green_against_the_built_site(self):
        r = subprocess.run(["node", str(CHECKER), f"http://127.0.0.1:{self.port}"],
                           capture_output=True, text=True, cwd=str(BASE), timeout=600)
        last = [ln for ln in r.stdout.strip().splitlines() if ln.strip()][-1]
        self.assertEqual(0, r.returncode, r.stdout[-800:] + r.stderr[-400:])
        self.assertRegex(last, r"\d+ موفق · 0 ناموفق")
        self.assertGreaterEqual(int(last.split("موفق")[0].strip().split()[-1]), 20)


@unittest.skipUnless(TOOLING_OK, WHY_NO_TOOLING)
class TestPublishTools(unittest.TestCase):
    def test_tools_exist_and_parse(self):
        for name in ("activate_demo_site.py", "activate_demo_site.sh", "make_demo_site.py"):
            self.assertTrue((HF / name).exists(), name)
        r = subprocess.run(["bash", "-n", str(HF / "activate_demo_site.sh")],
                           capture_output=True, text=True)
        self.assertEqual(0, r.returncode, r.stderr)

    def test_static_space_url_comes_from_the_api(self):
        """ایستاها روی دامنهٔ static.hf.space سرو می‌شوند؛ آدرس نباید حدسی باشد."""
        t = (HF / "activate_demo_site.py").read_text(encoding="utf-8")
        for needle in ('.get("host")', "static.hf.space", "check_demo_site.mjs",
                       "desk-demo", "── تمام ──"):
            self.assertIn(needle, t)

    def test_pro_message_explains_the_free_route(self):
        t = (HF / "activate_hf.py").read_text(encoding="utf-8")
        self.assertIn("Space داکری را اجازه نمی‌دهد", t)
        self.assertIn("activate_demo_site.sh", t)          # راه مجانی را نشان می‌دهد
        self.assertIn("Render", t)

    def test_dry_run_of_demo_publisher_is_safe(self):
        r = subprocess.run([sys.executable, str(HF / "activate_demo_site.py"), "--dry-run",
                            "--bundle", str(Path(tempfile.mkdtemp()) / "d")],
                           capture_output=True, text=True, cwd=str(HF),
                           env={k: v for k, v in os.environ.items() if k != "HF_TOKEN"})
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("برای اجرای واقعی", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
