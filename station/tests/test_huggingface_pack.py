"""آزمون بستهٔ میزبان ابری (Hugging Face Spaces و Render).

چه می‌سنجیم: (۱) پرونده‌های لازم هست و جای درستی نشانده شده‌اند؛ (۲) بستهٔ ساخته‌شده هیچ رمزی
با خودش نمی‌برد و پوشهٔ راز/خروجی ندارد؛ (۳) **واقعاً** بالا می‌آید: `boot.sh` را اجرا می‌کنیم،
از متغیرهای محیطی دو حساب می‌سازد و همان چهار عدد دروازه را می‌گیریم (۴۰۱/۲۰۰/۲۰۰/۴۰۳).
"""
from __future__ import annotations

import json
import os
import re
import secrets
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
TOOLING_NEEDED = ("deploy/make_hf.py", "deploy/huggingface/Dockerfile")


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
try:
    from security_scan import find_secret_literals, looks_like_real_secret
except Exception as _e:                                     # noqa: BLE001
    find_secret_literals = None
    looks_like_real_secret = None
    _IMPORT_ERROR = f"{type(_e).__name__}: {_e}" 

DEPLOY = BASE / "deploy"
HF = DEPLOY / "huggingface"
RENDER = DEPLOY / "render"
MAKE = DEPLOY / "make_hf.py"
def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def http(url: str, *, cookie: str | None = None, data: bytes | None = None,
         headers: dict | None = None) -> int:
    req = urllib.request.Request(url, data=data, headers=headers or {})
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


@unittest.skipUnless(TOOLING_OK, WHY_NO_TOOLING)
class TestPackFiles(unittest.TestCase):
    def test_pack_files_exist(self):
        for f in (HF / "Dockerfile", HF / "README.md", HF / "boot.sh", HF / "README-HF-FA.md",
                  RENDER / "render.yaml", MAKE):
            self.assertTrue(f.exists(), str(f))

    def test_space_card_has_front_matter(self):
        t = (HF / "README.md").read_text(encoding="utf-8")
        self.assertTrue(t.startswith("---\n"), "کارت Space باید با سرصفحهٔ HF شروع شود")
        for needle in ("sdk: docker", "app_port: 7860", "title:"):
            self.assertIn(needle, t)

    def test_dockerfile_serves_the_space_port(self):
        t = (HF / "Dockerfile").read_text(encoding="utf-8")
        for needle in ("EXPOSE 7860", 'CMD ["bash", "boot.sh"]', "USER desk", "STATION_PORT=7860"):
            self.assertIn(needle, t)

    def test_boot_builds_accounts_from_environment(self):
        t = (HF / "boot.sh").read_text(encoding="utf-8")
        for needle in ("set -euo pipefail", "STATION_ADMIN_PASS", "STATION_GUEST_PASS",
                       "gate.py --sync-admin", "gate.py --on", "--host 0.0.0.0",
                       'PORT:-${STATION_PORT:-7860}', "$HERE/station"):
            self.assertIn(needle, t)

    def test_guide_says_the_limits_out_loud(self):
        t = (HF / "README-HF-FA.md").read_text(encoding="utf-8")
        for needle in ("کارت بانکی", "۴۸", "عمومی", "پاک می‌شود", "حذف", "STATION_GUEST_OFF"):
            self.assertIn(needle, t)


@unittest.skipUnless(TOOLING_OK, WHY_NO_TOOLING)
class TestActivateScript(unittest.TestCase):
    """اسکریپت فعال‌سازی: بدون توکن چیزی نمی‌سازد، توکن را جایی نمی‌نویسد، و کارها را درست می‌چیند."""

    def _run(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(HF / "activate_hf.py"), *args],
                              capture_output=True, text=True, cwd=str(HF),
                              env={**os.environ, **(env or {})})

    def test_files_and_syntax(self):
        self.assertTrue((HF / "activate_hf.sh").exists())
        self.assertTrue((HF / "SIGNUP-FA.md").exists())
        r = subprocess.run(["bash", "-n", str(HF / "activate_hf.sh")], capture_output=True, text=True)
        self.assertEqual(0, r.returncode, r.stderr)
        subprocess.run([sys.executable, "-c",
                        "import ast,pathlib,sys; ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))",
                        str(HF / "activate_hf.py")], check=True)

    def test_dry_run_creates_no_space_and_no_credentials_file(self):
        """در حالت تمرین، بسته ساخته می‌شود (کار محلی است)، ولی هیچ حساب، Space یا رمزی ساخته نمی‌شود."""
        cred = BASE.parent / "delivery" / "HF-FIRST-LOGIN.txt"
        before_cred = cred.read_text(encoding="utf-8") if cred.exists() else None
        with tempfile.TemporaryDirectory() as tmp:
            r = self._run("--dry-run", "--bundle", str(Path(tmp) / "bundle"))
            self.assertEqual(0, r.returncode, r.stderr)
            self.assertIn("حالت تمرین", r.stdout)
            self.assertIn("STATION_ADMIN_PASS", r.stdout)          # چهار راز را نام می‌برد
            self.assertNotIn("بالا رفت", r.stdout)                  # هیچ پرونده‌ای فرستاده نشد
            self.assertNotIn("ساخته شد ✅", r.stdout)               # هیچ Space‌ای ساخته نشد
            self.assertTrue((Path(tmp) / "bundle" / "boot.sh").exists())   # بستهٔ تمرینی سر جایش است
        after_cred = cred.read_text(encoding="utf-8") if cred.exists() else None
        self.assertEqual(before_cred, after_cred, "در حالت تمرین پروندهٔ رمز ساخته/عوض شد!")

    def test_refuses_without_a_valid_token(self):
        r = self._run("--admin-pass", "x", env={"HF_TOKEN": "hf_not_a_real_token_value"})
        self.assertEqual(1, r.returncode)
        self.assertIn("توکن پذیرفته نشد", r.stdout)

    def test_never_writes_the_token_anywhere(self):
        src = (HF / "activate_hf.py").read_text(encoding="utf-8")
        for bad in ("write_text(token", 'json.dump(token', "print(token"):
            self.assertNotIn(bad, src)
        self.assertIn("getpass", src)                              # پرسیدن رمزآلود، نه چاپ آن

    def test_steps_match_the_hub_api(self):
        src = (HF / "activate_hf.py").read_text(encoding="utf-8")
        for needle in ("/api/repos/create", "/commit/main", "/api/spaces/{user}/{space}/secrets",
                       "/api/spaces/{repo}/restart", "/api/spaces/{user}/{space}", "hf.space",
                       "0o600", "HF-FIRST-LOGIN.txt"):
            self.assertIn(needle, src)

    def test_guide_is_complete_and_honest(self):
        t = (HF / "SIGNUP-FA.md").read_text(encoding="utf-8")
        for needle in ("huggingface.co/join", "settings/tokens", "New token", "Write",
                       "کارت بانکی", "۴۸", "Delete", "--dry-run", "hf.space"):
            self.assertIn(needle, t)


@unittest.skipUnless(TOOLING_OK, WHY_NO_TOOLING)
class TestBundle(unittest.TestCase):
    """بستهٔ واقعی را می‌سازیم و روی همان آزمون می‌گیریم."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "iran-desk-hf"
        r = subprocess.run([sys.executable, str(MAKE), "--out", str(cls.out)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise AssertionError(f"ساخت بسته شکست خورد: {r.stdout}{r.stderr}")
        # یک کپی جدا برای آزمون «بالا آمدن»: آن کپی دفتر و تنظیمات می‌سازد و دیگر بستهٔ اصلی
        # را دست نمی‌زند، پس ترتیب اجرای آزمون‌ها مهم نمی‌شود.
        cls.run_dir = Path(cls.tmp.name) / "run"
        shutil.copytree(cls.out, cls.run_dir)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_bundle_has_the_whole_station(self):
        for rel in ("station/web_server.py", "station/gate.py", "station/web/index.html",
                    "station/tests/test_gate.py", "station/run-tests.sh",
                    "desk/desk.py", "kodal-alert/kodal_alert.py",
                    "Dockerfile", "boot.sh", "README.md", "render.yaml", "README-HF-FA.md"):
            self.assertTrue((self.out / rel).exists(), rel)

    def test_bundle_keeps_no_secret_and_no_output(self):
        for banned in ("station/config/gate.json", "station/config/admin.json",
                       "station/export", "station/config/admin.json"):
            self.assertFalse((self.out / banned).exists(), banned)
        for f in self.out.rglob("*"):
            if not f.is_file():
                continue
            self.assertEqual([], find_secret_literals(f), f"{f} مقدار شبیه رمز دارد")

    def test_bundle_leaves_server_only_folders_behind(self):
        self.assertFalse((self.out / "station" / "deploy").exists())
        self.assertFalse((self.out / "station" / "share").exists())
        for junk in ("__pycache__", "node_modules", ".pytest_cache"):
            self.assertEqual([], [p for p in self.out.rglob(junk)], junk)
        self.assertEqual([], [p for p in self.out.rglob("*.log")])

    def test_manifest_reports_a_clean_scan(self):
        m = json.loads((self.out / "HF-BUNDLE-MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(0, m["secret_like_literals_found"])
        self.assertGreater(m["files"], 50)
        self.assertEqual({"Dockerfile", "README.md", "boot.sh", "README-HF-FA.md", "render.yaml"},
                         set(m["key_files"]))

    def test_boot_really_serves_with_the_gate_on(self):
        port = free_port()
        admin_pass = "Test-" + secrets.token_hex(6)
        guest_pass = "Test-" + secrets.token_hex(6)
        env = {**os.environ,
               "PYTHONDONTWRITEBYTECODE": "1",
               "STATION_PORT": str(port),
               "STATION_ADMIN_ID": "mafhoom", "STATION_ADMIN_PASS": admin_pass,
               "STATION_GUEST_ID": "masoud", "STATION_GUEST_PASS": guest_pass}
        proc = subprocess.Popen(["bash", "boot.sh"], cwd=self.run_dir, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            base = f"http://127.0.0.1:{port}"
            ready = False
            for _ in range(40):
                try:
                    if http(f"{base}/login") == 200:
                        ready = True
                        break
                except Exception:
                    pass
                time.sleep(0.5)
            self.assertTrue(ready, "ایستگاه روی میزبان بالا نیامد")

            self.assertEqual(401, http(f"{base}/files/offer"))              # بدون ورود
            body = json.dumps({"id": "masoud", "pass": guest_pass}).encode()
            req = urllib.request.Request(f"{base}/api/login", data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                self.assertEqual(200, r.status)
                raw = r.headers.get("Set-Cookie", "")
            self.assertIn("station_gate=", raw)
            cookie = raw.split(";")[0]
            self.assertEqual(200, http(f"{base}/", cookie=cookie))          # خود برنامه
            self.assertEqual(403, http(f"{base}/admin", cookie=cookie))     # پنل برای کارفرما بسته است
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    unittest.main(verbosity=2)
