"""آزمون «کوله‌پشتی دمو» — بسته‌ای که بدون اینترنت کار می‌کند.

چرا این آزمون‌ها مهم‌اند: در اینترنت محدود ایران، نمایش کارفرما نباید به هیچ لینک بیرونی گره بخورد.
پس سه چیز را می‌سنجیم: (۱) ساختار بسته درست است؛ (۲) **نمونهٔ ثابت روی فایل محلی** (بدون شبکه)
در jsdom بالا می‌آید و همهٔ گام‌ها باز می‌شوند؛ (۳) برنامهٔ زنده روی شبکهٔ محلی بالا می‌آید و
دروازه‌اش کار می‌کند و رمزهای اولین اجرا خودشان ساخته می‌شوند.

همه‌چیز در پوشهٔ موقت ساخته و آزموده می‌شود؛ چیزی از بستهٔ اصلی (delivery) دست‌کاری نمی‌شود.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]                 # .../money/gui
TOOLING_NEEDED = ("make_backpack.py", "deploy/huggingface/make_demo_site.py")


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

sys.path.insert(0, str(BASE))                              # خودِ سازندهٔ کوله‌پشتی
sys.path.insert(0, str(BASE / "deploy"))
try:                                                       # بستهٔ تحویلی: ابزار ساخت نیست
    from security_scan import find_secret_literals
    import make_backpack as BP
except Exception as _e:                                     # noqa: BLE001
    find_secret_literals = None
    BP = None
    _IMPORT_ERROR = f"{type(_e).__name__}: {_e}" 

DEMO_READY = bool(BP) and BP.demo_ready()          # در بستهٔ تحویلی نمونهٔ ثابت نیست → آزمون «رد» می‌شود
WHY_SKIP = "نمونهٔ ثابت دمو در این بسته نیست (اول make_demo_site.py)"

def build_or_skip(out, **kw):
    """ساخت کوله‌پشتی؛ اگر پیش‌نیازش در این بسته نبود «رد» می‌شویم، نه «خطا»."""
    try:
        return BP.build(out, **kw)
    except SystemExit as e:
        raise unittest.SkipTest(str(e))

def jsdom_available() -> bool:
    """jsdom از افزوده‌های بیرونی است و در پیمان‌های کاری (snapshot) نگه داشته نمی‌شود."""
    for base in (Path("/home/user"), Path(__file__).resolve().parents[1]):
        if (base / "node_modules" / "jsdom").exists():
            return True
    return False


WHY_NO_JSDOM = "jsdom نصب نیست (برای آزمون‌های مرورگری لازم است؛ در بستهٔ تحویلی نصب می‌شود)"


OFFLINE_CHECK = Path("/home/user/offline-check.mjs")       # آزمون آفلاین (jsdom از روی فایل)


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def code(url: str, *, cookie: str | None = None, data: bytes | None = None) -> int:
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"} if data else {})
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


@unittest.skipUnless(DEMO_READY, WHY_SKIP)
@unittest.skipUnless(TOOLING_OK, WHY_NO_TOOLING)
class TestBackpackBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        B = BP
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "backpack"
        cls.manifest = build_or_skip(cls.out, with_python=False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_structure(self):
        for rel in ("شروع-از-اینجا.html", "README-FA.md", "LIVE-DEMO-FA.md", "LINK-FA.txt",
                    "MAKE-PASSWORDS.py", "demo/index.html", "demo/app/app.js",
                    "station/web_server.py", "station/gate.py", "desk/desk.py",
                    "kodal-alert/kodal_alert.py", "docs/18-client-value-fa.md",
                    "RUN-LIVE-WINDOWS.bat", "RUN-LIVE-LINUX.sh", "RUN-DEMO-LAN-WINDOWS.bat",
                    "RUN-DEMO-LAN-LINUX.sh", "CHECK-WINDOWS.bat", "CHECK-LINUX.sh"):
            self.assertTrue((self.out / rel).exists(), rel)

    def test_scripts_are_valid_and_mention_the_essentials(self):
        for name in ("RUN-LIVE-LINUX.sh", "RUN-DEMO-LAN-LINUX.sh", "CHECK-LINUX.sh"):
            r = subprocess.run(["bash", "-n", str(self.out / name)], capture_output=True, text=True)
            self.assertEqual(0, r.returncode, f"{name}: {r.stderr}")
        win = (self.out / "RUN-LIVE-WINDOWS.bat").read_text(encoding="utf-8")
        for needle in ("chcp 65001", "python\\python.exe", "station\\web_server.py",
                       "0.0.0.0", "MAKE-PASSWORDS.py", "ipconfig"):
            self.assertIn(needle, win)
        lan = (self.out / "RUN-DEMO-LAN-WINDOWS.bat").read_text(encoding="utf-8")
        self.assertIn("http.server 8080", lan)
        self.assertIn("--directory demo", lan)

    def test_start_page_links_all_exist(self):
        t = (self.out / "شروع-از-اینجا.html").read_text(encoding="utf-8")
        for needle in ("demo/index.html", "LIVE-DEMO-FA.md", "RUN-LIVE-WINDOWS.bat",
                       "RUN-LIVE-LINUX.sh", "RUN-DEMO-LAN-WINDOWS.bat",
                       "RUN-DEMO-LAN-LINUX.sh", "CHECK-WINDOWS.bat", "CHECK-LINUX.sh"):
            self.assertIn(needle, t)
        # هر پیوند نسبی باید پرونده‌اش موجود باشد
        for href in re.findall(r'href="([^"#]+)"', t):
            if href.startswith(("http", "tel:", "mailto:")):
                continue
            self.assertTrue((self.out / href).exists(), f"پیوند شکسته: {href}")

    def test_no_secrets_and_no_outputs(self):
        for f in self.out.rglob("*"):
            if f.is_file():
                self.assertEqual([], find_secret_literals(f), f"{f} مشکوک است")
        self.assertFalse((self.out / "station" / "config" / "gate.json").exists())
        self.assertFalse((self.out / "station" / "config" / "admin.json").exists())
        self.assertEqual([], list((self.out / "station" / "export").glob("*")))
        self.assertEqual([], [p for p in self.out.rglob("__pycache__")])

    def test_manifest(self):
        m = json.loads((self.out / "BACKPACK-MANIFEST.json").read_text(encoding="utf-8"))
        self.assertTrue(m["offline_demo"])
        self.assertFalse(m["has_python"])
        self.assertIn("demo/index.html", m["key_files"])
        self.assertGreater(m["files"], 100)


@unittest.skipUnless(DEMO_READY, WHY_SKIP)
@unittest.skipUnless(TOOLING_OK, WHY_NO_TOOLING)
class TestOfflineDemo(unittest.TestCase):
    """نمونهٔ ثابت باید **بدون شبکه** کار کند؛ همین را با jsdom از روی فایل می‌سنجیم."""

    @classmethod
    def setUpClass(cls):
        B = BP
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "backpack"
        build_or_skip(cls.out, with_python=False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @unittest.skipUnless(OFFLINE_CHECK.exists(), "آزمون‌گر آفلاین نیست")
    @unittest.skipUnless(jsdom_available(), WHY_NO_JSDOM)
    def test_demo_index_opens_from_file_without_network(self):
        # نکته: صفحهٔ برنامه «demo/app/index.html» است؛ «demo/index.html» فقط صفحهٔ راهنماست
        r = subprocess.run(["node", str(OFFLINE_CHECK), str(self.out / "demo" / "app" / "index.html")],
                           capture_output=True, text=True, timeout=600)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("بازشده: 11", r.stdout)

    def test_demo_launcher_points_to_app(self):
        t = (self.out / "demo" / "index.html").read_text(encoding="utf-8")
        self.assertIn("app/index.html", t)

    def test_demo_pages_have_no_external_assets(self):
        for f in (self.out / "demo").rglob("*.html"):
            text = f.read_text(encoding="utf-8", errors="ignore")
            for bad in ("http://cdn", "https://cdn", "https://fonts.", "src=\"http"):
                self.assertNotIn(bad, text, f"{f} منبع بیرونی دارد")


@unittest.skipUnless(DEMO_READY, WHY_SKIP)
@unittest.skipUnless(TOOLING_OK, WHY_NO_TOOLING)
class TestBackpackLive(unittest.TestCase):
    """اولین اجرا: رمز ساخته می‌شود، دروازه روشن است، مهمان وارد می‌شود و پنل برایش بسته است."""

    @classmethod
    def setUpClass(cls):
        B = BP
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "backpack"
        build_or_skip(cls.out, with_python=False)
        cls.port = free_port()
        env = {**os.environ, "STATION_PORT": str(cls.port), "PYTHONDONTWRITEBYTECODE": "1"}
        cls.proc = subprocess.Popen(["bash", "RUN-LIVE-LINUX.sh"], cwd=str(cls.out), env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        base = f"http://127.0.0.1:{cls.port}"
        for _ in range(40):
            try:
                if code(f"{base}/login") == 200:
                    break
            except Exception:
                pass
            time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
        cls.tmp.cleanup()

    def test_first_run_made_credentials_and_gate_is_on(self):
        cred = self.out / "station" / "config" / "CREDENTIALS-FIRST-LOGIN.txt"
        self.assertTrue(cred.exists(), "پروندهٔ رمزهای اولین اجرا ساخته نشد")
        self.assertEqual(0o600, cred.stat().st_mode & 0o777)
        text = cred.read_text(encoding="utf-8")
        guest_pass = re.search(r"رمز کارفرما\s*:\s*(\S+)", text).group(1)
        operator_pass = re.search(r"رمز مدیر\s*:\s*(\S+)", text).group(1)
        self.assertNotEqual(guest_pass, operator_pass)
        self.assertGreaterEqual(len(guest_pass), 12)

        base = f"http://127.0.0.1:{self.port}"
        self.assertEqual(401, code(f"{base}/files/offer"))                 # بدون ورود
        body = json.dumps({"id": "masoud", "pass": guest_pass}).encode()
        req = urllib.request.Request(f"{base}/api/login", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            self.assertEqual(200, r.status)
            cookie = r.headers.get("Set-Cookie", "").split(";")[0]
        self.assertEqual(200, code(f"{base}/", cookie=cookie))
        self.assertEqual(403, code(f"{base}/admin", cookie=cookie))        # پنل برای کارفرما بسته است


@unittest.skipUnless(TOOLING_OK, WHY_NO_TOOLING)
class TestBackpackSkills(unittest.TestCase):
    def test_make_passwords_is_idempotent(self):
        t = (BASE / "MAKE-PASSWORDS.py").read_text(encoding="utf-8")
        self.assertIn("--force", t)
        self.assertIn("gate.set_account", t)
        self.assertIn("gate.sync_admin_from_panel", t)
        self.assertIn("chmod(0o600)", t)
        self.assertIn("CREDENTIALS-FIRST-LOGIN.txt", t)

    def test_builder_requires_the_demo_first(self):
        t = (BASE / "make_backpack.py").read_text(encoding="utf-8")
        self.assertIn("نمونهٔ ثابت ساخته نشده", t)
        self.assertIn("--with-python", t)
        self.assertIn("BACKPACK-MANIFEST.json", t)

    def test_demo_ready_helper_matches_reality(self):
        demo = BP.DEMO_SRC / "app" / "index.html"
        self.assertEqual(BP.demo_ready(), demo.exists())

    def test_offline_checker_exists_for_future_runs(self):
        self.assertTrue(OFFLINE_CHECK.exists())
        t = OFFLINE_CHECK.read_text(encoding="utf-8")
        self.assertIn("JSDOM.fromFile", t)
        self.assertIn("/api/state", t)


if __name__ == "__main__":
    unittest.main(verbosity=2)
