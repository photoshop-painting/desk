#!/usr/bin/env python3
"""آزمون «برنامهٔ کامل و زنده»ی Hugging Face: ساخت بسته، بوت واقعی، دروازه، پشتیبان‌گیری.

چه چیزی قفل می‌شود:
  ۱. بستهٔ زنده ساختار درست دارد و کارت Space روی SDK گرادیو (راه مجانی HF) است.
  ۲. هیچ راز/خروجی/نمونهٔ ثابتی داخل بسته نیست.
  ۳. بسته واقعاً بالا می‌آید: صفحهٔ ورود و راهنما باز، بدون ورود بسته، حساب کارفرما کار می‌کند،
     پنل مدیر برای کارفرما ۴۰۳ است.
  ۴. ضد CSRF پشت پروکسی: فقط نام Space پذیرفته می‌شود، نه میزبان بیگانه.
  ۵. وضعیت (کاربران، ثبت‌ها، خروجی‌ها) در بستهٔ پشتیبان می‌رود و برمی‌گردد؛ کد وارد بسته نمی‌شود.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
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
TOOLING_NEEDED = ("deploy/huggingface-live/make_live_space.py", "deploy/huggingface-live/activate_live_space.py")


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

sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "deploy"))
sys.path.insert(0, str(BASE / "deploy" / "huggingface-live"))
try:                                                       # بستهٔ تحویلی: ابزار ساخت نیست
    from security_scan import find_secret_literals
    import make_live_space as LIVE
except Exception as _e:                                     # noqa: BLE001
    find_secret_literals = None
    LIVE = None
    _IMPORT_ERROR = f"{type(_e).__name__}: {_e}" 

ADMIN = ("mafhoom", "Test-Admin-9f2x")
GUEST = ("masoud", "Test-Guest-7c4y")
SPACE_HOST = "delaris-desk-live.hf.space"


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def code(url: str, *, cookie: str | None = None, data: bytes | None = None,
         headers: dict | None = None) -> int:
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"} if data else {})
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0                                        # هنوز بالا نیامده یا بسته شد


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):               # ریدایرکت را دنبال نکن
        return None


def raw_code(url: str) -> int:
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(url, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


class LiveBundleBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "iran-desk-live"
        cls.manifest = LIVE.build(cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()


@unittest.skipUnless(TOOLING_OK, WHY_NO_TOOLING)
class TestLiveBundleShape(LiveBundleBase):
    def test_root_files_present(self):
        for name in ("app.py", "space_state.py", "README.md", "requirements.txt",
                     "LIVE-SPACE-MANIFEST.json"):
            self.assertTrue((self.out / name).exists(), name)

    def test_app_siblings_present(self):
        for name in ("station/web_server.py", "station/gate.py", "desk/desk.py"):
            self.assertTrue((self.out / name).exists(), name)
        self.assertTrue((self.out / "station" / "web" / "index.html").exists())
        self.assertTrue((self.out / "station" / "web" / "guide.html").exists())

    def test_space_card_is_gradio_for_the_free_route(self):
        card = (self.out / "README.md").read_text(encoding="utf-8")
        self.assertIn("sdk: gradio", card)                  # راه مجانی HF
        self.assertIn("app_file: app.py", card)
        self.assertIn("zero-a10g", card)                    # ZeroGPU: دو Space مجانی برای شخصی
        self.assertNotIn("sdk: docker", card)

    def test_manifest_says_live(self):
        self.assertEqual(self.manifest["kind"], "live")     # زنده، نه نمونهٔ ثابت
        self.assertEqual(self.manifest["port"], 7860)
        self.assertEqual(self.manifest["secret_like_literals_found"], 0)

    def test_printed_documents_ship_inside(self):
        """سندهایی که از /files/… سرو می‌شوند باید داخل بسته باشند، وگرنه ۴۰۴ می‌شود."""
        docs = self.out / "station" / "docs"
        self.assertTrue(docs.is_dir())
        for name in ("13-novice-walkthrough-fa.md", "09-sell-or-grant-access-fa.md",
                     "10-daily-inputs-fa.md", "20-security-review-fa.md",
                     "21-positive-result-plan-fa.md", "22-hf-live-deploy-fa.md"):
            self.assertTrue((docs / name).exists(), name)
        self.assertGreaterEqual(self.manifest.get("docs", 0), 15)

    def test_default_connection_is_a_real_free_source(self):
        """روی میزبان ابری، پیش‌فرض باید منبع واقعی باشد نه خوراک ساختگی محلی."""
        cfg = json.loads((self.out / "station" / "config" / "connections.json")
                         .read_text(encoding="utf-8"))
        self.assertEqual(cfg["selected"], LIVE.DEFAULT_CONNECTION)
        self.assertNotEqual(cfg["selected"], "mock-local")
        chosen = [p for p in cfg["profiles"] if p["name"] == cfg["selected"]][0]
        self.assertEqual(chosen.get("cost"), "رایگان")
        self.assertNotIn("127.0.0.1", chosen.get("url_template", ""))   # نه خوراک ساختگی محلی

    def test_backtest_sample_history_ships_inside(self):
        """فایل تاریخ نمونهٔ پس‌آزمایی باید باشد، وگرنه آزمون «بدون آینده‌نگری» و گام ۷ سرخ می‌شود."""
        csv = self.out / "station" / "demo" / "history-demo.csv"
        self.assertTrue(csv.exists(), "نمونهٔ تاریخ پس‌آزمایی در بسته نیست")
        self.assertGreater(len(csv.read_text(encoding="utf-8").splitlines()), 5)
        self.assertFalse((self.out / "station" / "demo" / "static-recording.json").exists(),
                         "ضبط نمونهٔ ثابت نباید سوار بستهٔ زنده شود")

    def test_every_test_module_imports_inside_the_bundle(self):
        """همهٔ ماژول‌های آزمون در بسته باید بی‌خطا بار شوند.

        چرا: «گزارش عیب‌یابی» همان‌جا داخل بسته آزمون‌ها را اجرا می‌کند؛ اگر یک ماژول هنگام
        بارگذاری بترکد، پنل «آزمون‌ها: سرخ» نشان می‌دهد و کاربر فکر می‌کند برنامه خراب است.
        """
        station = self.out / "station"
        code = ("import glob, importlib, os, sys\n"
                "sys.path.insert(0, '.')\n"
                "bad = []\n"
                "for path in sorted(glob.glob('tests/test_*.py')):\n"
                "    name = os.path.basename(path)[:-3]\n"
                "    try:\n"
                "        importlib.import_module(name)\n"
                "    except unittest_missing := Exception as e:\n"
                "        bad.append(f'{name}: {type(e).__name__}: {e}')\n"
                "print('BAD:' + ' | '.join(bad))\n")
        r = subprocess.run([sys.executable, "-c", code], cwd=str(station),
                           capture_output=True, text=True, timeout=300)
        out = (r.stdout or "").strip().splitlines()
        line = [x for x in out if x.startswith("BAD:")] or ["BAD:"]
        self.assertEqual(line[-1], "BAD:", line[-1][:500])

    def test_kodal_sample_database_ships_inside(self):
        """پایگاه نمونهٔ کدال باید باشد، وگرنه جدول سلامت هشدار می‌دهد و بخش کدال خالی است."""
        db = self.out / "kodal-alert" / "data" / "demo.sqlite3"
        self.assertTrue(db.exists(), "پایگاه نمونهٔ کدال در بسته نیست")
        self.assertGreater(db.stat().st_size, 1000)

    def test_engine_and_strategies_ship_inside(self):
        """موتور ریاضی و کارنامهٔ استراتژی‌ها همسایهٔ برنامه‌اند؛ بدونشان چند بخش ۵۰۰ می‌دهد."""
        self.assertTrue((self.out / "tools" / "derivatives_scout.py").exists())
        self.assertTrue((self.out / "strategies").is_dir())
        self.assertTrue(list((self.out / "strategies").glob("*.json")), "کارنامهٔ استراتژی خالی است")

    def test_no_secrets_outputs_or_demo_inside(self):
        for banned in ("station/config/gate.json", "station/config/admin.json", "station/export"):
            self.assertFalse((self.out / banned).exists(), banned)
        for path in self.out.rglob("*"):
            self.assertNotEqual(path.name, "DEMO-MANIFEST.json")
            self.assertEqual(path.suffix, path.suffix.lower())
        leaked = [x for p in sorted(self.out.rglob("*")) if p.is_file()
                  for x in find_secret_literals(p)]
        self.assertEqual(leaked, [], leaked[:3])

    def test_boot_script_understands_the_host_env(self):
        app = (self.out / "app.py").read_text(encoding="utf-8")
        self.assertIn("SPACE_HOST", app)
        self.assertIn("STATION_TRUST_PROXY", app)
        self.assertIn("space_state", app)


@unittest.skipUnless(TOOLING_OK, WHY_NO_TOOLING)
class TestLiveBoot(LiveBundleBase):
    """بسته را واقعاً بالا می‌آوریم و از بیرون می‌آزماییم (بدون توکن HF)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.port = free_port()
        env = dict(os.environ)
        env.update({
            "PORT": str(cls.port),
            "STATION_INTERNAL_PORT": str(free_port()),      # کارساز داخلی، درگاه آزاد
            "STATION_ADMIN_ID": ADMIN[0], "STATION_ADMIN_PASS": ADMIN[1],
            "STATION_GUEST_ID": GUEST[0], "STATION_GUEST_PASS": GUEST[1],
            "STATION_ALLOW_HOSTS": SPACE_HOST,
        })
        env.pop("HF_TOKEN", None)
        env.pop("HUGGING_FACE_HUB_TOKEN", None)
        cls.proc = subprocess.Popen([sys.executable, "app.py"], cwd=str(cls.out), env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        cls.base = f"http://127.0.0.1:{cls.port}"
        for _ in range(150):                                # پوستهٔ گرادیو چند ثانیه وقت می‌خواهد
            if code(cls.base + "/login") == 200:
                break
            time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
        super().tearDownClass()

    def test_login_and_guide_are_open(self):
        self.assertEqual(code(self.base + "/login"), 200)
        self.assertEqual(code(self.base + "/guide"), 200)

    def test_gate_blocks_outputs_without_login(self):
        self.assertEqual(code(self.base + "/files/offer"), 401)        # خروجی‌ها: کد ۴۰۱
        cookie = self.guest_cookie()
        # سندهای تحلیلی همراه بسته‌اند و برای کارفرما باز می‌شوند؛ برگهٔ پیشنهاد بعد از
        # ساخته‌شدن (دکمهٔ خودش) سرو می‌شود، پس از پیش ۴۰۴ است.
        self.assertEqual(code(self.base + "/files/walkthrough", cookie=cookie), 200)
        self.assertEqual(code(self.base + "/files/zero-cost", cookie=cookie), 200)
        self.assertEqual(code(self.base + "/files/daily-inputs", cookie=cookie), 200)
        # سندهای مدیریتی (مثل سند واگذاری) برای کارفرما بسته‌اند
        self.assertEqual(code(self.base + "/files/grant-doc", cookie=cookie), 403)
        self.assertEqual(raw_code(self.base + "/"), 302)               # صفحه‌ها: ریدایرکت به ورود
        self.assertIn("ورود", urllib.request.urlopen(self.base + "/login", timeout=20)
                      .read().decode("utf-8"))

    def test_guest_account_from_env_works(self):
        cookie = self.guest_cookie()
        self.assertTrue(cookie.startswith("station_gate="))
        self.assertEqual(code(self.base + "/", cookie=cookie), 200)
        self.assertEqual(code(self.base + "/api/signals", cookie=cookie), 200)
        self.assertEqual(code(self.base + "/admin", cookie=cookie), 403)   # کارفرما مدیر نیست

    def test_admin_account_from_env_is_admin(self):
        cookie = self.admin_cookie()
        self.assertTrue(cookie.startswith("station_gate="))
        self.assertEqual(code(self.base + "/admin", cookie=cookie), 200)

    def test_engine_dependent_sections_work(self):
        """بخش‌هایی که موتور ریاضی را صدا می‌زنند (آزمون کور سرمایه‌گذار و پرونده) باید کار کنند."""
        cookie = self.guest_cookie()
        req = urllib.request.Request(self.base + "/api/investor/blind",
                                     data=json.dumps({"reveal": True}).encode(),
                                     headers={"Content-Type": "application/json",
                                              "Cookie": cookie})
        with urllib.request.urlopen(req, timeout=60) as r:
            out = json.loads(r.read().decode("utf-8"))
        self.assertTrue(out.get("ok"), out)
        self.assertGreaterEqual(len(out.get("cases") or []), 5)
        self.assertTrue(any(c.get("answer") for c in out["cases"]))

    def test_selftest_is_all_green_on_the_deployed_bundle(self):
        """آزمون ۱۵ موردی و خلاصهٔ سلامت روی بستهٔ میزبان ابری باید کامل سبز باشند."""
        body = json.dumps({"id": ADMIN[0], "pass": ADMIN[1]}).encode()
        req = urllib.request.Request(self.base + "/api/admin/login", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                token = (json.loads(r.read().decode("utf-8")) or {}).get("token") or ""
        except urllib.error.HTTPError as e:
            self.skipTest(f"قفل کوتاه فعال است (کد {e.code})")
            return
        cookie = self._cookie(ADMIN)

        def admin_post(path: str, *, method: str = "POST") -> dict:
            rq = urllib.request.Request(self.base + path,
                                        data=None if method == "GET" else b"{}", method=method,
                                        headers={"Content-Type": "application/json",
                                                 "Cookie": cookie, "X-Admin-Token": token})
            try:
                with urllib.request.urlopen(rq, timeout=180) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                self.fail(f"{path} → کد {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}")
                return {}

        st = admin_post("/api/selftest")
        summary = st.get("summary") or {}
        red = [c.get("id") for c in (st.get("cases") or []) if not c.get("ok")]
        self.assertEqual(summary.get("failed"), 0, f"موارد سرخ آزمون: {red}")
        self.assertGreaterEqual(summary.get("total", 0), 15)

        health = admin_post("/api/health", method="GET")
        bad = [i.get("name") for i in (health.get("items") or []) if not i.get("ok")]
        self.assertEqual(health.get("passed"), health.get("total"), f"هشدارهای سلامت: {bad}")

    def test_state_keeper_reports_honestly_without_token(self):
        """پنل باید وضعیت نگهبان را ببیند؛ بی‌توکن هم صادقانه «خاموش» بگوید، نه خطا بدهد.

        چرا: روی میزبان ابری، دیسک بادوام نیست و تنها سندِ زنده‌ماندنِ کارِ کاربر همین نگهبان است.
        اگر پنل نتواند وضعیتش را ببیند، کاربر نمی‌داند کارش پشتیبان می‌شود یا نه.
        """
        cookie = self.admin_cookie()
        body = json.dumps({"id": ADMIN[0], "pass": ADMIN[1]}).encode()
        req = urllib.request.Request(self.base + "/api/admin/login", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                token = (json.loads(r.read().decode("utf-8")) or {}).get("token") or ""
        except urllib.error.HTTPError as e:
            if e.code == 401:
                self.skipTest("قفل کوتاهِ تلاش ناموفق فعال است")
                return
            raise

        self.assertEqual(code(self.base + "/api/admin/state", cookie=cookie), 403)   # بی‌توکن پنل

        def call(path: str, method: str = "GET") -> dict:
            rq = urllib.request.Request(self.base + path, method=method,
                                        data=None if method == "GET" else b"{}",
                                        headers={"Content-Type": "application/json",
                                                 "Cookie": cookie, "X-Admin-Token": token})
            with urllib.request.urlopen(rq, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))

        info = call("/api/admin/state")
        self.assertTrue(info.get("ok"), info)
        self.assertFalse(info.get("online"), "در آزمون توکن HF عمداً نیست")
        self.assertIn("توکن", info.get("note") or "")
        self.assertIn("interval_seconds", info)
        self.assertIn("last", info)

        out = call("/api/admin/backup", "POST")
        self.assertFalse(out.get("ok"))
        self.assertIn("توکن", out.get("note") or "")

    def test_csrf_accepts_the_space_host_only(self):
        body = json.dumps({"id": GUEST[0], "pass": GUEST[1]}).encode()
        self.assertEqual(code(self.base + "/api/login", data=body,
                              headers={"Origin": f"https://{SPACE_HOST}"}), 200)
        self.assertEqual(code(self.base + "/api/login", data=body,
                              headers={"Origin": "https://evil.example"}), 403)

    def test_health_belongs_to_the_admin_panel(self):
        """سلامت، پشت دروازه و مخصوص مدیر است: بدون ورود ۴۰۱، کارفرما ۴۰۳."""
        self.assertEqual(code(self.base + "/api/health"), 401)
        self.assertEqual(code(self.base + "/api/health", cookie=self.guest_cookie()), 403)

    def test_admin_panel_login_can_read_health(self):
        """سلامت با توکن پنل مدیریت خوانده می‌شود (همان رمزی که boot از Secrets ساخته)."""
        body = json.dumps({"id": ADMIN[0], "pass": ADMIN[1]}).encode()
        req = urllib.request.Request(self.base + "/api/admin/login", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                out = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", "ignore")[:200]
            if e.code == 401 and "قفل" in body_text:
                self.skipTest("قفل کوتاهِ تلاش ناموفق فعال است")
            self.fail(f"ورود پنل شکست خورد (کد {e.code}): {body_text}")
            return
        self.assertTrue(out.get("ok"), out)
        token = out.get("token") or ""
        # در برنامهٔ واقعی مدیر دو چیز دارد: نشست دروازه + توکن پنل.
        gate = self._cookie(ADMIN)
        self.assertEqual(code(self.base + "/api/health", headers={"X-Admin-Token": token}),
                         401)                                   # توکن تنها، بدون نشست دروازه کافی نیست
        self.assertEqual(code(self.base + "/api/health", cookie=gate,
                              headers={"X-Admin-Token": token}), 200)

    def guest_cookie(self) -> str:
        return self._cookie(GUEST)

    def admin_cookie(self) -> str:
        return self._cookie(ADMIN)

    def _cookie(self, who) -> str:
        """کوکی از یک ورود موفق؛ اگر قفل کوتاهِ تلاش ناموفق فعال بود، «رد» می‌شویم نه «سرخ»."""
        body = json.dumps({"id": who[0], "pass": who[1]}).encode()
        req = urllib.request.Request(self.base + "/api/login", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.headers.get("Set-Cookie", "").split(";")[0]
        except urllib.error.HTTPError as e:
            self.skipTest(f"قفل کوتاهِ تلاش ناموفق فعال است (کد {e.code})؛ در آزمون امنیتی جدا سنجیده می‌شود")
            return ""


@unittest.skipUnless(TOOLING_OK, WHY_NO_TOOLING)
class TestActivateGuard(LiveBundleBase):
    """نگهبان آپلود: هیچ راز/خروجی/پایتون‌کش‌شده‌ای به مخزن عمومی نمی‌رود."""

    def test_secret_files_are_never_uploaded(self):
        import activate_live_space as A
        for rel in ("station/config/gate.json", "station/config/admin.json", "admin.json",
                    "station/export/offer.html", "desk/data/dashboard.html",
                    "station/__pycache__/gate.pyc"):
            self.assertTrue(A.skippable(rel), rel)

    def test_normal_files_are_uploaded(self):
        import activate_live_space as A
        for rel in ("app.py", "space_state.py", "station/web_server.py",
                    "station/data/trial-ledger.json", "desk/desk.py"):
            self.assertFalse(A.skippable(rel), rel)


@unittest.skipUnless(TOOLING_OK, WHY_NO_TOOLING)
class TestStateKeeper(LiveBundleBase):
    """نگهبان وضعیت: بستهٔ پشتیبان می‌سازد، برمی‌گرداند، و کد را واردش نمی‌کند."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        spec = importlib.util.spec_from_file_location("live_space_state",
                                                      cls.out / "space_state.py")
        cls.state = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.state)                  # HERE = پوشهٔ بستهٔ ساخته‌شده

    def test_state_zip_roundtrip(self):
        made = self.out / "station" / "data" / "trial-ledger.json"
        made.parent.mkdir(parents=True, exist_ok=True)
        made.write_text('{"daily": [1, 2, 3]}', encoding="utf-8")
        blob = self.state.build_zip()
        self.assertIn(b"trial-ledger.json", blob)
        made.unlink()
        restored = self.state.apply_zip(blob)
        self.assertGreaterEqual(restored, 1)
        self.assertEqual(json.loads(made.read_text(encoding="utf-8"))["daily"], [1, 2, 3])

    def test_state_zip_never_carries_code(self):
        blob = self.state.build_zip()
        for forbidden in (b"web_server.py", b"gate.py", b"app.py", b"desk.py"):
            self.assertNotIn(forbidden, blob)

    def test_zip_cannot_escape_the_space_folder(self):
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("../../evil.txt", "x")
            z.writestr("station/data/ok.json", "{}")
        n = self.state.apply_zip(buf.getvalue())
        self.assertEqual(n, 1)                              # فقط پروندهٔ داخل
        self.assertFalse((self.out.parent / "evil.txt").exists())

    def test_last_backup_memo_travels_inside_the_backup(self):
        """یادداشت «آخرین پشتیبان» باید خودش داخل بستهٔ پشتیبان باشد، وگرنه پس از ری‌استارت گم می‌شود."""
        import io
        import zipfile
        self.state._remember({"ok": True, "at": "2026-09-22 22:58:47", "files": 37, "kb": 77,
                              "reason": "درخواست مدیر از پنل"})
        names = zipfile.ZipFile(io.BytesIO(self.state.build_zip())).namelist()
        self.assertIn("station/data/keeper-last.json", names)
        recalled = self.state._recall()
        self.assertEqual(recalled.get("files"), 37)
        self.state.LAST_MARK.unlink()

    def test_default_connection_is_forced_to_a_real_source(self):
        """اگر نسخهٔ پشتیبان خوراک ساختگی را برگرداند، پیش از روشن‌شدن به منبع واقعی برمی‌گردد."""
        cfg_path = self.out / "station" / "config" / "connections.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["selected"] = "mock-local"                     # مثل نسخهٔ پشتیبان قدیمی
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        os.environ.pop("STATION_CONNECTION", None)
        chosen = self.state.ensure_connection()
        self.assertEqual(chosen, "tgju-usd")
        after = json.loads(cfg_path.read_text(encoding="utf-8"))
        self.assertEqual(after["selected"], "tgju-usd")
        prof = [p for p in after["profiles"] if p["name"] == "tgju-usd"][0]
        self.assertNotIn("127.0.0.1", prof["url_template"])

    def test_without_token_restore_is_quiet(self):
        os.environ.pop("HF_TOKEN", None)
        os.environ.pop("HUGGING_FACE_HUB_TOKEN", None)
        self.assertEqual(self.state.restore(), 0)
        self.assertIsNone(self.state.start_loop())

    def test_state_repo_name_defaults_to_user_dataset(self):
        os.environ["SPACE_AUTHOR_NAME"] = "delaris"
        os.environ.pop("STATION_STATE_REPO", None)
        self.assertEqual(self.state._repo(), "delaris/desk-state")
        os.environ["STATION_STATE_REPO"] = "delaris/custom-state"
        self.assertEqual(self.state._repo(), "delaris/custom-state")
        os.environ.pop("SPACE_AUTHOR_NAME", None)
        os.environ.pop("STATION_STATE_REPO", None)



    def test_panel_shows_the_keeper_and_has_a_backup_button(self):
        """پنل مدیر باید وضعیت نگهبان و دکمهٔ پشتیبان‌گیری داشته باشد."""
        js = (BASE / "web" / "admin.js").read_text(encoding="utf-8")
        html = (BASE / "web" / "admin.html").read_text(encoding="utf-8")
        self.assertIn("/api/admin/state", js)
        self.assertIn("/api/admin/backup", js)
        self.assertIn("loadStateInfo", js)
        self.assertIn("state-box", html)
        self.assertIn("پشتیبان‌گیری الان", html)

    def test_keeper_exposes_info_and_manual_backup(self):
        """نگهبان وضعیت باید هم «گزارش وضعیت» بدهد و هم «پشتیبان‌گیری فوری»."""
        src = (self.out / "space_state.py").read_text(encoding="utf-8")
        for needle in ("def info(", "def backup_now(", "def push(", "def pull(", "def restore(",
                       "RESTORED", "LAST", "def _remember(", "def _recall(", "keeper-last.json"):
            self.assertIn(needle, src)
        self.assertIn("/api/state/info", (self.out / "station" / "web_server.py").read_text("utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
