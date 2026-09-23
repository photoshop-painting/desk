"""بار 28 — تقویمِ شمسیِ ایستگاه (کامپوننتِ jalali-calendar + فیلترِ بازهٔ لاگ).

منبعِ قواعد: مهارتِ jalali-calendar از وایب‌فارسی (vibefarsi.ir/skills/jalali-calendar):
  هفته از شنبه، جمعه تعطیل، فلش‌های RTL برعکس، حالت‌ها فقط با رنگ نه،
  ارقامِ فارسی، وقتِ تهران، بازه‌های آماده در شمسی، ذخیره Gregorian/UTC.
تبدیلِ تاریخ با همان jalali.jsِ اعتبارسنجی‌شده (50,000 روز، bar 25).

ارقامِ فارسیِ این پرونده فقط با F() (ساختِ برنامه‌ای) نوشته می‌شوند؛ تایپِ دستی ممنوع.
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

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
WEB = BASE / "web"

F = lambda d: ''.join(chr(0x06F0 + int(c)) for c in d)

CAL = (WEB / "jalali-calendar.js").read_text(encoding="utf-8")
ADMIN_HTML = (WEB / "admin.html").read_text(encoding="utf-8")
ADMIN_JS = (WEB / "admin.js").read_text(encoding="utf-8")
AUDIT_PY = (BASE / "audit.py").read_text(encoding="utf-8")
SERVER_PY = (BASE / "web_server.py").read_text(encoding="utf-8")


class TestComponentSource(unittest.TestCase):
    """قواعدِ مهارتِ jalali-calendar، خط‌به‌خط در سورسِ کامپوننت."""

    def test_saturday_first(self):
        self.assertIn('var WEEK = ["ش", "ی", "د", "س", "چ", "پ", "ج"]', CAL)
        self.assertIn("(js + 1) % 7", CAL)     # تبدیلِ روزِ JS (یکشنبه=0) ← (شنبه=0)

    def test_friday_is_weekend(self):
        # سرستونِ جمعه و روزهای جمعهٔ شبکه، خاکستری
        self.assertIn('if (i === 6) s.className = "fr"', CAL)
        self.assertIn('(firstWeekday(view[0], view[1]) + day - 1) % 7 === 6', CAL)
        self.assertIn(".jlcal-d.fr{color:#9aa3ad}", CAL)

    def test_states_not_color_only(self):
        # امروز: حلقه؛ انتخاب‌شده: تیک — هر دو افزونه‌ای روی رنگ
        self.assertIn(".jlcal-d.today{box-shadow:inset 0 0 0 1.5px", CAL)
        self.assertIn("content:'✓ '", CAL)
        self.assertIn('aria-current", "date"', CAL)
        self.assertIn('aria-pressed", "true"', CAL)

    def test_rtl_arrows_flipped(self):
        # «ماهِ قبل → فلش به راست، ماهِ بعد → فلش به چپ»
        self.assertIn('bPrev.setAttribute("aria-label", "ماه قبل"); bPrev.textContent = "→"', CAL)
        self.assertIn('bNext.setAttribute("aria-label", "ماه بعد"); bNext.textContent = "←"', CAL)

    def test_tehran_time_no_dst(self):
        self.assertIn("var TEH_MS = 3.5 * 3600 * 1000", CAL)
        self.assertIn("Date.now() + TEH_MS", CAL)

    def test_persian_month_names_table(self):
        for name in ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
                     "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"):
            self.assertIn(name, CAL)

    def test_presets_in_jalali(self):
        # «7 روز گذشته / این ماه / ماه گذشته» — محاسبه در تقویمِ شمسی
        for key in ("week", "month", "lastMonth"):
            self.assertIn(key, CAL)
        self.assertIn("addDays(t, -6)", CAL)

    def test_uses_verified_converter(self):
        # الگوریتمِ leap از حافظه نیست: فقط همان jalali.jsِ اعتبارسنجی‌شده
        self.assertIn("var J = root.Jalali", CAL)
        self.assertIn('throw new Error("jalali-calendar.js بدونِ jalali.js کار نمی‌کند")', CAL)

    def test_offline_no_animation(self):
        for bad in ("http://", "https://", "fonts.googleapis", "cdn."):
            self.assertNotIn(bad, CAL)
        self.assertNotIn("transition", CAL)      # کامپوننتِ استاتیک = reduced-motion safe
        self.assertNotIn("@keyframes", CAL)

    def test_range_mode_spec(self):
        # specِ date-range-picker: دو ماهِ کنارِ هم، پیش‌نمایشِ هاور، شمارشِ روز، بازه‌های آماده
        self.assertIn("openRange", CAL)
        self.assertIn('grid-template-columns:1fr 1fr', CAL)          # دو ماه
        self.assertIn(".jlcal-d.pv{background:#eef4f1}", CAL)       # پیش‌نمایشِ بازه با هاور
        self.assertIn("fa(n) + \" روز\"", CAL)                      # شمارشِ روزها
        for label in ("۷ روز گذشته", "این ماه", "ماه گذشته"):
            self.assertIn(label, CAL)                               # بازه‌های آماده داخلِ پنل
        self.assertIn("prevMonthOf", CAL)                           # ماهِ چپ = ماهِ قبل
        self.assertIn("aria-live", CAL)                             # شمارش برای screen reader


class TestWiringSource(unittest.TestCase):
    """اتصالِ کامپوننت به پنلِ مدیریت و سرور."""

    def test_admin_html_fields(self):
        m = re.search(r'<input[^>]*id="audit-range"[^>]*>', ADMIN_HTML)
        self.assertTrue(m, "audit-range")
        tag = m.group(0)
        self.assertIn('aria-label', tag)
        self.assertIn("openAuditRange", tag)
        self.assertIn("readonly", tag)
        # اسکریپتِ تقویم بعد از jalali.js
        i_cal = ADMIN_HTML.index("jalali-calendar.js")
        i_jal = ADMIN_HTML.index("jalali.js")
        i_adm = ADMIN_HTML.index("admin.js")
        self.assertTrue(i_jal < i_cal < i_adm)

    def test_admin_js_range_query(self):
        self.assertIn("tehranDayUtc", ADMIN_JS)
        self.assertIn('qs.set("from", b.fromIso)', ADMIN_JS)
        self.assertIn('qs.set("to", b.toIso)', ADMIN_JS)
        self.assertIn("window.openAuditRange = openAuditRange", ADMIN_JS)
        self.assertIn("JalaliCal.openRange(el", ADMIN_JS)
        # حالتِ خالیِ جدول (specِ empty-state: وضعیت + قدمِ بعدی)
        self.assertIn("colspan", ADMIN_JS)
        self.assertIn("هیچ ردیفی در این فیلترها نیست", ADMIN_JS)

    def test_server_side(self):
        self.assertIn("from_utc: str | None = None, to_utc: str | None = None", AUDIT_PY)
        self.assertIn("_ISO_DAY_RE.match(str(from_utc))", AUDIT_PY)
        self.assertIn('ts < from_utc', AUDIT_PY)
        self.assertIn('ts >= to_utc', AUDIT_PY)
        self.assertIn('from_utc=(q.get("from") or [None])[0] or None', SERVER_PY)
        self.assertIn('to_utc=(q.get("to") or [None])[0] or None', SERVER_PY)

    def test_scripts_are_served(self):
        # «درسِ بار 29»: اسکریپتِ تقویم در مرورگرِ واقعی باید سرو شود (jsdom این را نمی‌بیند)
        self.assertIn('if u.path == "/jalali.js":', SERVER_PY)
        self.assertIn('if u.path == "/jalali-calendar.js":', SERVER_PY)


def jsdom_available() -> bool:
    import shutil
    if not shutil.which("node"):
        return False
    return (Path("/home/user/node_modules/jsdom")).exists()


WHY_NO_JSDOM = "jsdom نصب نیست (برای آزمون‌های مرورگری لازم است؛ در بستهٔ تحویلی نصب می‌شود)"


@unittest.skipUnless(jsdom_available(), WHY_NO_JSDOM)
class TestCalendarLive(unittest.TestCase):
    """کامپوننت روی DOMِ واقعی (jsdom) با وقتِ ثابت: 2026-09-23T12:00:00Z = 1 مهر 1405، 15:30 تهران."""

    NOW_MS = 1790164800000  # 2026-09-23T12:00:00Z (محاسبه‌شده، نه حدس)

    def _run(self, body: str) -> str:
        script = """
        const { JSDOM } = require("/home/user/node_modules/jsdom");
        const fs = require("fs");
        const web = "%s";
        const dom = new JSDOM('<body><input id="anchor" style="position:fixed;left:40px;top:80px"></body>',
                              { runScripts: "outside-only", url: "http://localhost/" });
        const w = dom.window;
        w.eval(fs.readFileSync(web + "/jalali.js", "utf8"));
        w.eval(fs.readFileSync(web + "/jalali-calendar.js", "utf8"));
        w.eval("Date.now = function(){ return %d; };")
        %s
        """ % (str(WEB), self.NOW_MS, body)
        p = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])
        return p.stdout.strip().splitlines()[-1]

    def test_today_and_anchor(self):
        out = self._run("""
        const C = w.JalaliCal;
        const t = C.today();
        const out = [
          t.join("/"),
          w.Jalali.g2j(2026, 9, 23).join("/"),
          new Date(Date.UTC(2026, 8, 23)).getUTCDay(),
          C.fmt(t),
          C.firstWeekday(1405, 7),
          C.firstWeekday(1405, 1)
        ];
        console.log(out.join("|"));
        """)
        t, g, wd, fmt, fw7, fw1 = out.split("|")
        self.assertEqual(g, "1405/7/1")          # لنگرِ اعتبارسنجی‌شدهٔ jalali.js
        self.assertEqual(t, "1405/7/1")          # امروزِ تهران = 1 مهر 1405
        self.assertEqual(wd, "3")                # 2026-09-23 چهارشنبه است
        self.assertEqual(fmt, F("1405") + "/" + F("07") + "/" + F("01"))
        self.assertEqual(fw7, "4")               # 1 مهر در ستونِ چهارشنبه (شنبه=0)
        self.assertEqual(fw1, "0")               # نوروز 1405 = شنبه

    def test_grid_and_states(self):
        out = self._run("""
        const C = w.JalaliCal, d = w.document;
        C.open(d.getElementById("anchor"), {});
        const node = d.querySelector(".jlcal");
        const cells = node.querySelectorAll(".jlcal-g button.jlcal-d");
        const title = node.querySelector(".jlcal-t").textContent;
        const fridays = node.querySelectorAll(".jlcal-g .jlcal-d.fr").length;
        const todayCell = node.querySelector(".jlcal-d.today");
        const lead = node.querySelectorAll(".jlcal-g > span[style*='hidden']").length;
        const idx = Array.from(node.querySelectorAll(".jlcal-g .jlcal-d")).indexOf(todayCell);
        console.log([title, cells.length, lead, idx, fridays,
                     todayCell.getAttribute("aria-current")].join("|"));
        """)
        title, n, lead, idx, fr, cur = out.split("|")
        self.assertEqual(title, "مهر " + F("1405"))
        self.assertEqual(int(n), 30)             # مهر 30 روز
        self.assertEqual(int(lead), 4)           # 4 روزِ خالی تا چهارشنبه
        self.assertEqual(int(idx), 4)            # امروز در ستونِ چهارشنبه
        self.assertEqual(int(fr), 4)             # جمعه‌های 3، 10، 17، 24 مهر
        self.assertEqual(cur, "date")

    def test_navigation_and_year_boundary(self):
        out = self._run("""
        const C = w.JalaliCal, d = w.document;
        C.open(d.getElementById("anchor"), {});
        const prev = () => d.querySelector('.jlcal-b[aria-label="ماه قبل"]').click();
        const next = () => d.querySelector('.jlcal-b[aria-label="ماه بعد"]').click();
        const t = () => d.querySelector(".jlcal-t").textContent;
        const n = () => d.querySelectorAll(".jlcal-g .jlcal-d:not([style*='hidden'])").length;
        const seq = [];
        prev(); seq.push(t() + ":" + n());                        // شهریور 1405
        next(); next(); seq.push(t() + ":" + n());                // آبان 1405
        for (let i = 0; i < 3; i++) next();                       // بهمن 1405
        seq.push(t() + ":" + n());
        for (let i = 0; i < 11; i++) prev();                      // اسفند 1404 (از بهمن)
        seq.push(t() + ":" + n());
        next(); seq.push(t() + ":" + n());                         // فروردین 1405
        console.log(seq.join("|"));
        """)
        shahr, aban, bahman, esfand, farv = out.split("|")
        self.assertEqual(shahr, "شهریور " + F("1405") + ":31")
        self.assertEqual(aban, "آبان " + F("1405") + ":30")
        self.assertEqual(bahman, "بهمن " + F("1405") + ":30")
        self.assertTrue(esfand.startswith("اسفند " + F("1404") + ":29")
                        or esfand.startswith("اسفند " + F("1404") + ":30"), esfand)
        self.assertEqual(farv, "فروردین " + F("1405") + ":31")

    def test_pick_and_selection(self):
        out = self._run("""
        const C = w.JalaliCal, d = w.document;
        let picked = null;
        C.open(d.getElementById("anchor"), { onPick: (y, m, dd) => { picked = [y, m, dd]; } });
        const cells = d.querySelectorAll(".jlcal-g button.jlcal-d");
        cells[14].click();                        // روزِ 15
        const closed = !d.querySelector(".jlcal");
        console.log([picked.join("/"), closed ? "y" : "n",
                     C.fmtLong(picked)].join("|"));
        """)
        picked, closed, long = out.split("|")
        self.assertEqual(picked, "1405/7/15")
        self.assertEqual(closed, "y")
        self.assertIn(F("15") + " مهر " + F("1405"), long)
        self.assertIn("چهارشنبه", long)          # 1 + 14 روز = دوباره چهارشنبه

    def test_presets_and_range(self):
        out = self._run("""
        const C = w.JalaliCal;
        const p = C.presets();
        const b = C.tehranDayUtc(1405, 7, 1);
        console.log([
          p.week.from.join("/"), p.week.to.join("/"),
          p.month.from.join("/"), p.month.to.join("/"),
          p.lastMonth.from.join("/"), p.lastMonth.to.join("/"),
          b.fromIso, b.toIso,
          C.diffDays(p.week.from, p.week.to)
        ].join("|"));
        """)
        parts = out.split("|")
        self.assertEqual(parts[0], "1405/6/26")   # امروز + ۶ روزِ قبل = ۷ روزِ کامل
        self.assertEqual(parts[1], "1405/7/1")
        self.assertEqual(parts[2], "1405/7/1")
        self.assertEqual(parts[3], "1405/7/30")
        self.assertEqual(parts[4], "1405/6/1")
        self.assertEqual(parts[5], "1405/6/31")
        self.assertEqual(parts[6], "2026-09-22T20:30:00Z")   # نیمه‌شبِ 1 مهر، UTC
        self.assertEqual(parts[7], "2026-09-23T20:30:00Z")   # نیمه‌شبِ 2 مهر، UTC
        self.assertEqual(parts[8], "6")

    def test_parse(self):
        fa_input = F("1405") + "/" + F("07") + "/" + F("01")
        out = self._run("""
        const C = w.JalaliCal;
        const p = (x) => { const r = C.parse(x); return r ? r.join("/") : "null"; };
        console.log([p("1405/7/1"), p("%s"), p("1405-7-1"),
                     p("1405/13/1"), p("1405/7/31"), p("abc"), p([1405, 7, 1])].join("|"));
        """ % fa_input)
        parts = out.split("|")
        self.assertEqual(parts[0], "1405/7/1")
        self.assertEqual(parts[1], "1405/7/1")
        self.assertEqual(parts[2], "1405/7/1")
        self.assertEqual(parts[3], "null")
        self.assertEqual(parts[4], "null")
        self.assertEqual(parts[5], "null")
        self.assertEqual(parts[6], "1405/7/1")


@unittest.skipUnless(jsdom_available(), WHY_NO_JSDOM)
class TestAdminWiringLive(unittest.TestCase):
    """صفحهٔ واقعیِ پنل: دکمه‌های آماده، باز شدنِ تقویم، انتخاب، متنِ بازه، پاک‌کردن."""

    NOW_MS = 1790164800000  # 2026-09-23T12:00:00Z

    def _run(self, body: str) -> list:
        script = """
        const { JSDOM } = require("/home/user/node_modules/jsdom");
        const fs = require("fs");
        const web = "%s";
        const dom = new JSDOM(fs.readFileSync(web + "/admin.html", "utf8"),
                              { runScripts: "outside-only", url: "http://localhost/" });
        const w = dom.window;
        for (const f of ["help.js", "jalali.js", "jalali-calendar.js", "admin.js"])
          w.eval(fs.readFileSync(web + "/" + f, "utf8"));
        w.eval("Date.now = function(){ return %d; };")
        %s
        """ % (str(WEB), self.NOW_MS, body)
        p = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])
        return p.stdout.strip().splitlines()[-1].split("§")

    def test_full_flow(self):
        out = self._run("""
        const d = w.document, out = [];
        w.openAuditRange();
        out.push(d.querySelectorAll(".jlcal-range .jlcal-rm").length);
        out.push([...d.querySelectorAll(".jlcal-rm .jlcal-t")].map(x => x.textContent).join("|"));
        const leftCells = d.querySelectorAll(".jlcal-rm:last-child button.jlcal-d");
        leftCells[27].click();                                            // 28 شهریور (ماهِ چپ)
        const rightCells = d.querySelectorAll(".jlcal-rm:first-child button.jlcal-d");
        rightCells[0].dispatchEvent(new w.Event("mouseover"));            // هاور روی 1 مهر
        out.push(d.querySelector(".jlcal-rf .count").textContent);
        rightCells[0].click();                                            // 1 مهر → بازه تمام
        out.push(d.getElementById("audit-range").value);
        out.push(!!d.querySelector(".jlcal-range") ? "open" : "closed");
        w.openAuditRange();
        [...d.querySelectorAll(".jlcal-rf button")].find(b => b.textContent === "این ماه").click();
        [...d.querySelectorAll(".jlcal-rf button")].find(b => b.className === "primary").click();
        out.push(d.getElementById("audit-range").value);
        w.openAuditRange();
        [...d.querySelectorAll(".jlcal-rf button")].find(b => b.textContent === "پاک کردن بازه").click();
        [...d.querySelectorAll(".jlcal-rf button")].find(b => b.className === "primary").click();
        out.push(d.getElementById("audit-range").value);
        console.log(out.join("§"));
        """)
        self.assertEqual(out[0], "2")                              # دو ماهِ کنارِ هم
        self.assertEqual(out[1], "مهر " + F("1405") + "|شهریور " + F("1405"))
        self.assertEqual(out[2], F("5") + " روز")                 # پیش‌نمایشِ هاور: 28 شهریور تا 1 مهر
        self.assertEqual(out[3], "از " + F("1405") + "/" + F("06") + "/" + F("28") +
                         " تا " + F("1405") + "/" + F("07") + "/" + F("01") + " · " + F("5") + " روز")
        self.assertEqual(out[4], "closed")
        self.assertEqual(out[5], "از " + F("1405") + "/" + F("07") + "/" + F("01") +
                         " تا " + F("1405") + "/" + F("07") + "/" + F("30") + " · " + F("30") + " روز")
        self.assertEqual(out[6], "")


class TestAuditRangeFilter(unittest.TestCase):
    """audit.read با from_utc/to_utc — روی پروندهٔ موقت."""

    def _make(self, tmp: Path) -> Path:
        d = tmp / "audit"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "audit.jsonl"
        rows = [
            {"ts": "2026-09-20T20:30:00Z", "user": "a", "level": "info"},
            {"ts": "2026-09-22T20:30:00Z", "user": "a", "level": "info"},
            {"ts": "2026-09-23T10:00:00Z", "user": "b", "level": "error"},
            {"ts": "2026-09-23T20:30:00Z", "user": "a", "level": "info"},
        ]
        f.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                     encoding="utf-8")
        return f

    def test_window(self):
        import audit
        with tempfile.TemporaryDirectory() as t:
            self._make(Path(t))
            rows = audit.read(Path(t), from_utc="2026-09-22T20:30:00Z", to_utc="2026-09-23T20:30:00Z")
            ts = [r["ts"] for r in rows]
            # from شامل و to غیرشامل: دقیقاً دو ردیفِ وسط (از نو به کهنه)
            self.assertEqual(ts, ["2026-09-23T10:00:00Z", "2026-09-22T20:30:00Z"])

    def test_open_ended(self):
        import audit
        with tempfile.TemporaryDirectory() as t:
            self._make(Path(t))
            rows = audit.read(Path(t), from_utc="2026-09-22T20:30:00Z")
            self.assertEqual(len(rows), 3)
            rows = audit.read(Path(t), to_utc="2026-09-22T20:30:00Z")
            self.assertEqual([r["ts"] for r in rows], ["2026-09-20T20:30:00Z"])

    def test_invalid_ignored(self):
        import audit
        with tempfile.TemporaryDirectory() as t:
            self._make(Path(t))
            rows = audit.read(Path(t), from_utc="garbage", to_utc="2026-09-20T00:00:00Z")
            self.assertEqual(len(rows), 0)          # fromِ نامعتبر → نادیده؛ to اعمال شد
            rows = audit.read(Path(t), from_utc="2026-09-20", to_utc="bad")
            self.assertEqual(len(rows), 4)          # هر دو نامعتبر → بدون فیلتر


@unittest.skipUnless(jsdom_available(), WHY_NO_JSDOM)
class TestServerRangeFilter(unittest.TestCase):
    """سرورِ واقعی: پارامترهای from/to از HTTP تا پروندهٔ لاگ."""

    ADMIN = ("mafhoom", "Smm@1101001")

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="jcal-"))
        cls.cfg = cls.dir / "gate.json"
        import gate as g
        g.SESSIONS.clear()
        g.set_account("admin", *cls.ADMIN, path=cls.cfg)
        g.set_enabled(True, path=cls.cfg)
        s = socket.socket(); s.bind(("127.0.0.1", 0))
        cls.port = s.getsockname()[1]; s.close()
        env = {**os.environ, "STATION_GATE_CONFIG": str(cls.cfg),
               "PYTHONDONTWRITEBYTECODE": "1"}
        cls.proc = subprocess.Popen([sys.executable, "-m", "web_server",
                                     "--port", str(cls.port), "--host", "127.0.0.1",
                                     "--no-browser"],
                                    cwd=str(BASE), env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
        cls.base = f"http://127.0.0.1:{cls.port}"
        for _ in range(60):
            try:
                urllib.request.urlopen(cls.base + "/api/gate/status", timeout=2).read()
                break
            except Exception:
                time.sleep(0.5)
        # پروندهٔ لاگ را بکاپ بگیر و دو ردیفِ آزمایشی با tsِ معلوم اضافه کن
        cls.audit_file = BASE / "data" / "audit" / "audit.jsonl"
        cls.backup = None
        if cls.audit_file.exists():
            cls.backup = cls.audit_file.read_text(encoding="utf-8")
        cls.audit_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cls.audit_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": "2026-09-01T10:00:00Z", "user": "jcal-test",
                                 "role": "test", "ip": "127.0.0.1", "method": "GET",
                                 "path": "/jcal/old", "action": "test", "details": {},
                                 "status": 200, "ms": 1, "level": "info"},
                                ensure_ascii=False) + "\n")
            fh.write(json.dumps({"ts": "2026-09-23T10:00:00Z", "user": "jcal-test",
                                 "role": "test", "ip": "127.0.0.1", "method": "GET",
                                 "path": "/jcal/new", "action": "test", "details": {},
                                 "status": 200, "ms": 1, "level": "info"},
                                ensure_ascii=False) + "\n")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
        # برگرداندنِ پروندهٔ لاگ به حالتِ پیش
        if cls.backup is None:
            cls.audit_file.unlink(missing_ok=True)
        else:
            cls.audit_file.write_text(cls.backup, encoding="utf-8")
        import gate as g
        g.SESSIONS.clear()

    def _gate_cookie(self):
        # دروازهٔ کاربر باید هم روشن باشد (مثل test_security): کوکی + توکنِ پنل
        req = urllib.request.Request(self.base + "/api/login", method="POST",
                                     data=json.dumps({"id": "mafhoom", "pass": "Smm@1101001"}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.headers.get("Set-Cookie", "").split(";")[0]

    def _get(self, path, token, cookie):
        req = urllib.request.Request(self.base + path)
        req.add_header("X-Admin-Token", token)
        if cookie:
            req.add_header("Cookie", cookie)
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")

    def _admin_token(self):
        req = urllib.request.Request(self.base + "/api/admin/login", method="POST",
                                     data=json.dumps({"id": "mafhoom", "pass": "Smm@1101001"}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=25) as r:
            return (json.loads(r.read().decode("utf-8") or "{}")).get("token", "")

    def test_range_applied(self):
        token = self._admin_token()
        self.assertTrue(token, "توکنِ مدیر صادر نشد")
        cookie = self._gate_cookie()
        # بازهٔ تهرانِ 1 مهر 1405: [2026-09-22T20:30:00Z, 2026-09-23T20:30:00Z)
        code, d = self._get("/api/admin/audit?user=jcal-test&from=2026-09-22T20%3A30%3A00Z"
                            "&to=2026-09-23T20%3A30%3A00Z", token, cookie)
        self.assertEqual(code, 200)
        self.assertTrue(d.get("ok"))
        ts = [e["ts"] for e in d["entries"]]
        self.assertIn("2026-09-23T10:00:00Z", ts)
        self.assertNotIn("2026-09-01T10:00:00Z", ts)

    def test_invalid_param_ignored(self):
        token = self._admin_token()
        self.assertTrue(token, "توکنِ مدیر صادر نشد")
        cookie = self._gate_cookie()
        code, d = self._get("/api/admin/audit?user=jcal-test&from=bad&to=worse", token, cookie)
        self.assertEqual(code, 200)
        self.assertTrue(d.get("ok"))
        ts = [e["ts"] for e in d["entries"]]
        self.assertIn("2026-09-01T10:00:00Z", ts)
        self.assertIn("2026-09-23T10:00:00Z", ts)

    def test_calendar_scripts_served_live(self):
        """در مرورگرِ واقعی: هر دو اسکریپتِ تقویم باید 200 بدهند (با کوکیِ دروازه)."""
        cookie = self._gate_cookie()
        for name, needle in (("/jalali.js", "g2j"), ("/jalali-calendar.js", "openRange")):
            req = urllib.request.Request(self.base + name)
            req.add_header("Cookie", cookie)
            with urllib.request.urlopen(req, timeout=25) as r:
                body = r.read().decode("utf-8")
                self.assertEqual(r.status, 200, name)
                self.assertIn(needle, body, name)


if __name__ == "__main__":
    unittest.main()
