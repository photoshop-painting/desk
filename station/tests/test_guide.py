"""راهنمای کارفرما: کامل باشد، فنی نباشد، و از خودِ برنامه باز شود.

خواستهٔ صاحب برنامه همین بود: «کاربر از راهنمای داخل برنامه همهٔ نیازش را یاد بگیرد و از کسی
سؤال نکند» و «هیچ توضیح فنی و ریاضی نباشد که نرود به برنامه‌نویس دیگری بسپارد».

پس این آزمون‌ها سه چیز را سخت می‌گیرند:
  ۱. **کامل بودن**: پرسش‌های پرتکرار، جدول خطاها، روز اول، هر روز، روز چهاردهم، پشتیبانی.
  ۲. **بی‌زبانی فنی**: هیچ واژهٔ فنی/ریاضی و هیچ قطعه‌کد در متن نباشد.
  ۳. **در دسترس بودن**: از صفحهٔ ورود و از خود برنامه باز شود، و بدون اینترنت هم کار کند.
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

BASE = Path(__file__).resolve().parents[1]        # .../money/gui
WEB = BASE / "web"
GUIDE = WEB / "guide.html"
sys.path.insert(0, str(BASE))

import gate as g                                   # noqa: E402

TECH_WORDS = ("API", "JSON", "پایتون", "پای‌تون", "جاوااسکریپت", "دیتابیس", "الگوریتم",
              "فرمول", "معادله", "متغیر", "تابع", "سرور", "اسکریپت", "کامپایل", "داکر",
              "پورت", "هش", "sha", "npm", "برنامه‌نویسی", "کد نویسی", "کدنویسی", "کامپیوترِ",
              "مارجین", "کِلی", "توزیع نرمال", "انحراف معیار", "ریاضیات", "∑", "√", "∫",
              "تابع ریاضی", "پارامتر", "بهینه‌سازی")


class GuideFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = GUIDE.read_text(encoding="utf-8")
        cls.text = re.sub(r"<[^>]+>", " ", cls.html)

    def test_file_exists_and_is_not_huge(self):
        self.assertTrue(GUIDE.exists())
        self.assertLess(GUIDE.stat().st_size, 120_000)

    def test_has_no_technical_jargon(self):
        # با مرز واژه سنجیده می‌شود تا زیررشته‌های بی‌گناه (مثل «همه‌شان») گیر نیفتند
        found = []
        for word in TECH_WORDS:
            pattern = rf"(?<![\w\u0600-\u06FF]){re.escape(word)}(?![\w\u0600-\u06FF])"
            if re.search(pattern, self.html):
                found.append(word)
        self.assertEqual([], found, f"واژهٔ فنی در راهنما: {found}")

    def test_has_no_code_or_formulas(self):
        self.assertNotIn("<code", self.html)
        self.assertNotIn("<pre", self.html)
        self.assertEqual([], re.findall(r"\b\w+\([^)]*\)\s*=", self.html))     # چیزی شبیه کد
        self.assertNotIn("```", self.html)

    def test_is_fully_offline(self):
        # هیچ منبع بیرونی بارگذاری نمی‌شود (فقط پیوند تماس مجاز است)
        for pattern in (r'<link[^>]+href="https?://', r'<script[^>]+src="https?://',
                        r'<img[^>]+src="https?://', r"@import\s+url"):
            self.assertEqual([], re.findall(pattern, self.html), pattern)
        external = set(re.findall(r'href="https?://([^/"]+)', self.html))
        self.assertTrue(external <= {"t.me", "instagram.com"}, external)

    def test_persian_rtl_and_mobile_ready(self):
        self.assertIn('dir="rtl"', self.html)
        self.assertIn('lang="fa"', self.html)
        self.assertIn("width=device-width", self.html)

    def test_is_printable(self):
        self.assertIn("window.print()", self.html)
        self.assertIn("@media print", self.html)

    def test_covers_the_whole_journey(self):
        for phrase in ("روز اول تو", "هر روز", "شصت ثانیه", "دو هفته بعد", "جلسهٔ بازبینی",
                       "برگهٔ تصمیم", "کارنامهٔ آماده‌بودن", "دفتر شاهد"):
            self.assertIn(phrase, self.html, phrase)

    def test_answers_at_least_fifteen_questions(self):
        self.assertGreaterEqual(self.html.count("<details"), 15)

    def test_lists_the_error_messages_a_user_may_see(self):
        for msg in ("شناسه یا رمز درست نیست", "این بخش فقط با حساب مدیر باز می‌شود",
                    "برای دیدن برنامه اول وارد شوید", "پرونده ساخته نشده است",
                    "دست نزن"):
            self.assertIn(msg, self.html, msg)

    def test_says_clearly_it_does_not_trade_and_sells_nothing(self):
        self.assertIn("سفارش نمی‌فرستد", self.html)
        self.assertIn("هیچ‌چیز لازم نیست بخری", self.html)
        self.assertIn("وعدهٔ سود نمی‌دهد", self.html)

    def test_has_support_path_and_credit(self):
        self.assertIn("پشتیبانی", self.html)
        self.assertIn("Masoud Mojarabian", self.html)
        self.assertIn("tel:+989126630554", self.html)

    def test_explains_privacy_without_jargon(self):
        self.assertIn("حریم خصوصی", self.html)
        self.assertIn("جایی فرستاده نمی‌شوند", self.html)


class GuideIsReachable(unittest.TestCase):
    """راهنما از خودِ برنامه سرو می‌شود و بی‌ورود هم باز است (کسی بی‌راهنما نماند)."""

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="guide-"))
        cfg = cls.dir / "gate.json"
        g.SESSIONS.clear()
        g.set_account("admin", "mafhoom", "Smm@1101001", path=cfg)
        g.set_enabled(True, path=cfg)
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        cls.port = s.getsockname()[1]
        s.close()
        env = {**os.environ, "STATION_GATE_CONFIG": str(cfg), "PYTHONDONTWRITEBYTECODE": "1"}
        cls.proc = subprocess.Popen([sys.executable, "-m", "web_server", "--port", str(cls.port),
                                     "--host", "127.0.0.1", "--no-browser"],
                                    cwd=str(BASE), env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
        cls.base = f"http://127.0.0.1:{cls.port}"
        for _ in range(60):
            try:
                with urllib.request.urlopen(cls.base + "/api/gate/status", timeout=10):
                    break
            except Exception:
                time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.proc.kill()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=20) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")

    def test_guide_opens_without_login(self):
        code, body = self.get("/guide")
        self.assertEqual(200, code)
        self.assertIn("راهنمای کارفرما", body)
        self.assertIn("پرسش‌های پرتکرار", body)

    def test_program_and_login_link_to_the_guide(self):
        for path in ("/login",):
            code, body = self.get(path)
            self.assertEqual(200, code)
            self.assertIn('href="/guide"', body)
        self.assertIn('href="/guide"', (WEB / "index.html").read_text(encoding="utf-8"))

    def test_guide_is_still_served_after_login_and_behind_the_gate(self):
        # پشت دروازه هم باید باز بماند (کاربر وارد‌شده هم به آن نیاز دارد)
        req = urllib.request.Request(self.base + "/api/login",
                                     data=json.dumps({"id": "mafhoom",
                                                      "pass": "Smm@1101001"}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            cookie = r.headers.get("Set-Cookie", "").split(";")[0]
        req2 = urllib.request.Request(self.base + "/guide", headers={"Cookie": cookie})
        with urllib.request.urlopen(req2, timeout=20) as r2:
            self.assertEqual(200, r2.status)
            self.assertIn("راهنمای کارفرما", r2.read().decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
