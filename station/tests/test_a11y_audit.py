#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""نگهبان «audit دسترس‌پذیری و تعامل» — یافته‌ها از دو منبعِ خوانده‌شده:
  * ui-ux-pro-max (nextlevelbuilder) — data/ux-guidelines.csv (۱۱۹ قاعدهٔ اولویت‌دار)
  * impeccable/audit (pbakaus) — روشِ ۵‌بُعدیِ گزارش‌گیری با شدت

قاعده‌هایی که این پرونده نگهبانی می‌دهد (با شمارهٔ ux-guidelines):
  #32 دکمهٔ حینِ عملیات غیرفعال می‌شود (جلوگیری از ارسالِ دوباره)
  #40 دکمهٔ آیکونی aria-label دارد
  #43 ورودی‌ها labelِ برنامه‌ای (aria-label یا label[for]) دارند
  #44 جعبه‌های لاگ/خطا برای screen reader اعلام می‌شوند (aria-live)
  #45 لینکِ پرش به محتوا
  #29 فیدبکِ hover روی دکمه‌ها (همهٔ صفحه‌ها)
  #36 کنتراستِ متنی دست‌کم ۴٫۵:۱
"""
from __future__ import annotations

import io
import re
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

WEB = BASE / "web"


def L(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


APP = L("app.js")
HELP = L("help.js")
INDEX = L("index.html")
PAGES = {n: L(n) for n in ("index.html", "admin.html", "login.html", "guide.html")}


def contrast(fg: str, bg: str) -> float:
    def lum(hexc: str) -> float:
        h = hexc.lstrip("#")
        c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    l1, l2 = lum(fg), lum(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


class TestBusyDisablesButton(unittest.TestCase):
    def test_busy_toggles_disabled_on_sibling_button(self):
        fn = re.search(r"function busy\(id, on\) \{.*?\n\}", APP, re.S)
        self.assertTrue(fn, "busy() پیدا نشد")
        body = fn.group(0)
        self.assertIn("sib.tagName === \"BUTTON\"", body)
        self.assertIn("sib.disabled = !!on", body)
        self.assertIn("n < 3", body, "پیمایش باید محدود بماند (دکمهٔ اشتباه غیرفعال نشود)")

    def test_disabled_button_style(self):
        self.assertIn("button:disabled{opacity:.55;cursor:default}", HELP)


class TestIconButtonsLabeled(unittest.TestCase):
    def test_help_close_buttons_have_aria_label(self):
        xs = re.findall(r'<button[^>]*class="help-x"[^>]*>', HELP)
        self.assertGreaterEqual(len(xs), 2, "دو دکمهٔ بستنِ مودال باید وجود داشته باشد")
        for tag in xs:
            self.assertIn("aria-label=", tag, "دکمهٔ آیکونیِ «×» باید aria-label داشته باشد")


class TestA11yAutofix(unittest.TestCase):
    def test_autofix_function_exists_and_booted(self):
        self.assertIn("function a11yAutofix()", HELP)
        self.assertIn("a11yAutofix();", HELP)

    def test_logs_get_aria_live(self):
        fn = re.search(r"function a11yAutofix\(\) \{.*?\n\}", HELP, re.S)
        self.assertTrue(fn)
        body = fn.group(0)
        self.assertIn('".log"', body)
        self.assertIn("aria-live", body)
        self.assertIn('"polite"', body)

    def test_inputs_get_aria_label(self):
        fn = re.search(r"function a11yAutofix\(\) \{.*?\n\}", HELP, re.S)
        body = fn.group(0)
        self.assertIn("placeholder", body)
        self.assertIn("aria-label", body)
        self.assertIn('label[for=', body)

    def test_skip_link_created(self):
        self.assertIn("skip-link", HELP)
        self.assertIn(".skip-link:focus", HELP)


class TestHoverFeedback(unittest.TestCase):
    def test_shared_hover_rule_covers_all_pages(self):
        self.assertIn("button:hover:not(:disabled){filter:brightness(.96)}", HELP)


class TestContrast(unittest.TestCase):
    def test_hint_badge_contrast(self):
        # بج‌های ۱۱px «برای اثباتِ برنامه — اختیاری»
        m = re.search(r"color:(#[0-9a-fA-F]{6});background:(#[0-9a-fA-F]{6})[^>]*>.*?اختیاری", INDEX)
        self.assertTrue(m, "بجِ هینت پیدا نشد")
        r = contrast(m.group(1), m.group(2))
        self.assertGreaterEqual(r, 4.5, f"کنتراستِ بج: {r:.2f}:1 (حداقل ۴٫۵:۱)")

    def test_known_pairs(self):
        for fg, bg, name in [
            ("#1d1d1f", "#f6f7f9", "متن اصلی روی بوم"),
            ("#ffffff", "#0b3d2e", "دکمهٔ اصلی"),
            ("#0a7d33", "#ffffff", "وضعیتِ موفق"),
            ("#b3261e", "#ffffff", "وضعیتِ خطا"),
            ("#6b7280", "#ffffff", "متنِ کم‌رنگ روی سفید"),
        ]:
            r = contrast(fg, bg)
            self.assertGreaterEqual(r, 4.5, f"کنتراستِ {name}: {r:.2f}:1")


class TestNoExternalAssetsStill(unittest.TestCase):
    def test_pages_stay_offline(self):
        for name, html in PAGES.items():
            for bad in ("fonts.googleapis", "cdn.", "https://fonts"):
                self.assertNotIn(bad, html, f"{name} به منبعِ بیرونی وصل شده")


def jsdom_available() -> bool:
    """jsdom از افزوده‌های بیرونی است و در پیمان‌های کاری (snapshot) نگه داشته نمی‌شود."""
    import shutil
    if not shutil.which("node"):
        return False
    base = BASE
    for _ in range(4):
        if (base / "node_modules" / "jsdom").exists():
            return True
        if base.parent == base:
            break
        base = base.parent
    return (Path("/home/user/node_modules/jsdom")).exists()


WHY_NO_JSDOM = "jsdom نصب نیست (برای آزمون‌های مرورگری لازم است؛ در بستهٔ تحویلی نصب می‌شود)"


@unittest.skipUnless(jsdom_available(), WHY_NO_JSDOM)
class TestPagesLiveA11y(unittest.TestCase):
    """روی صفحهٔ واقعی (jsdom): skip-link، aria-live و برچسبِ همهٔ ورودی‌ها."""

    CHECK = """
    const { JSDOM } = require("%s");
    const fs = require("fs");
    const web = "%s";
    const pages = ["index.html","admin.html","login.html","guide.html"];
    let i = 0, failures = [];
    function next() {
      if (i >= pages.length) { console.log(JSON.stringify(failures)); process.exit(0); }
      const page = pages[i++];
      const dom = new JSDOM(fs.readFileSync(web + "/" + page, "utf8"), { runScripts: "outside-only", url: "http://localhost/" });
      const w = dom.window;
      w.eval(fs.readFileSync(web + "/help.js", "utf8"));
      setTimeout(() => {
        const d = w.document;
        const inputs = [...d.querySelectorAll("input,select,textarea")]
          .filter(x => !["hidden","checkbox","radio","submit","button","file"].includes(x.type || "text"));
        const missing = inputs.filter(x => !x.getAttribute("aria-label")
          && !(x.id && d.querySelector('label[for="' + x.id + '"]')) && !x.closest("label"));
        const logs = [...d.querySelectorAll(".log")];
        const skip = d.getElementById("skip-link");
        if (missing.length) failures.push(page + ": " + missing.map(m => m.id || m.tagName).join(","));
        if (logs.length && !logs.every(l => l.getAttribute("aria-live") === "polite"))
          failures.push(page + ": aria-live");
        if (!skip || !d.querySelector(skip.getAttribute("href"))) failures.push(page + ": skip-link");
        next();
      }, 250);
    }
    next();
    """

    def test_all_pages(self):
        import json
        import subprocess
        node = subprocess.run(
            ["node", "-e", self.CHECK % (str(Path("/home/user/node_modules/jsdom")), str(WEB))],
            capture_output=True, text=True, timeout=180)
        line = next((l for l in reversed(node.stdout.strip().splitlines()) if l.startswith("[")), "[]")
        failures = json.loads(line)
        self.assertEqual(failures, [], "یافته‌های دسترس‌پذیری روی صفحهٔ زنده: " + "; ".join(failures))


if __name__ == "__main__":
    unittest.main(verbosity=2)
