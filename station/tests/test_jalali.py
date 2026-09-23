#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""نگهبان «تقویمِ شمسی» (web/jalali.js): تبدیلِ گریگوری↔شمسی برای نمایشِ زمان‌ها.

چرا: برنامهٔ آفلاین است و اجازهٔ کتابخانهٔ بیرونی ندارد؛ الگوریتمِ عمومیِ
jalaali-js (Borkowski، مجوز MIT) همین‌جا بازپیموده شده است. این تست:
  ۱. الگوریتم را با نقطه‌های معلومِ رسمی می‌سنجد (از خروجیِ خودِ کتابخانهٔ رسمی).
  ۲. اگر کتابخانهٔ رسمی (jalaali-js) در دسترس باشد، ۵۰٬۰۰۰ روز را با آن تطبیق می‌کند.
  ۳. قالبِ نمایش را می‌سنجد: وقتِ تهران (UTC+3:30) و ارقامِ فارسی.
  ۴. اتصالِ UI را می‌سنجد: پنل، jalali.js را بار می‌کند و جدولِ لاگ، زمانِ شمسی نشان می‌دهد.
  ۵. قاعدهٔ فونت: در همهٔ چهار صفحه، Vazirmatn/IRANSans سرِ استکِ فونت است.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

WEB = BASE / "web"
JALALI = WEB / "jalali.js"
ADMIN = (WEB / "admin.html").read_text(encoding="utf-8")
ADMINJS = (WEB / "admin.js").read_text(encoding="utf-8")
PAGES = {
    "index": (WEB / "index.html").read_text(encoding="utf-8"),
    "admin": (WEB / "admin.html").read_text(encoding="utf-8"),
    "login": (WEB / "login.html").read_text(encoding="utf-8"),
    "guide": (WEB / "guide.html").read_text(encoding="utf-8"),
}
LIB_DIR = Path("/tmp/jj/node_modules/jalaali-js")  # فقط برای تطبیقِ اختیاری

NODE = shutil.which("node")


def _run_node(code: str) -> str:
    assert NODE, "node در دسترس نیست"
    p = subprocess.run([NODE, "-e", code], capture_output=True, text=True, timeout=180)
    if p.returncode != 0:
        raise AssertionError("node خطا داد:\n" + p.stderr[-2000:])
    return p.stdout


class TestJalaliAlgorithm(unittest.TestCase):
    """الگوریتمِ تبدیل — با نقطه‌های معلوم (همه از خروجیِ jalaali-js رسمی 2.x گرفته‌اند)."""

    @unittest.skipUnless(NODE, "node در دسترس نیست")
    def test_anchor_points(self):
        out = _run_node(
            "const J=require('" + str(JALALI) + "');\n"
            "const r=(gy,gm,gd)=>J.g2j(gy,gm,gd).join('/');\n"
            "console.log(JSON.stringify({\n"
            " a:r(1985,7,31),  // نمونهٔ رسمیِ الگوریتم\n"
            " b:r(2026,3,21),  // نوروز ۱۴۰\n"
            " c:r(2025,3,21),  // نوروز ۱۴۰\n"
            " d:r(2026,9,23),  // امروزِ مرجع\n"
            " e:J.j2g(1364,5,9).join('/'),\n"
            " f:J.j2g(1405,7,1).join('/')\n"
            "}));"
        )
        d = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(d["a"], "1364/5/9", "نمونهٔ رسمیِ الگوریتم (۱۹/۷/۳۱)")
        self.assertEqual(d["b"], "1405/1/1", "نوروز ۱۴۰ = ۲۱ مارس ۲۰")
        self.assertEqual(d["c"], "1404/1/1", "نوروز ۱۴ = ۲۱ مارس ۲۰۲")
        self.assertEqual(d["d"], "1405/7/1", "۲۳ سپتامبر ۲۰۶ = ۱ شهریور ۱۴۰")
        self.assertEqual(d["e"], "1985/7/31", "برگشتِ نمونهٔ رسمی")
        self.assertEqual(d["f"], "2026/9/23", "برگشتِ امروزِ مرجع")

    @unittest.skipUnless(NODE and LIB_DIR.is_dir(), "کتابخانهٔ رسمی jalaali-js در دسترس نیست")
    def test_matches_official_library_50000_days(self):
        out = _run_node(
            "const J=require('" + str(JALALI) + "');\n"
            "const L=require('" + str(LIB_DIR) + "');\n"
            "let bad=0;\n"
            "for(let i=0;i<50000;i++){\n"
            "  const d=new Date(Date.UTC(1800,0,1)+i*86400000);\n"
            "  const g=[d.getUTCFullYear(),d.getUTCMonth()+1,d.getUTCDate()];\n"
            "  const a=J.g2j(g[0],g[1],g[2]);\n"
            "  const b=L.toJalaali(g[0],g[1],g[2]);\n"
            "  if(a[0]!==b.jy||a[1]!==b.jm||a[2]!==b.jd){bad++;if(bad<3)console.error('mismatch',g.join('/'),a,b);}\n"
            "  const back=J.j2g(a[0],a[1],a[2]);\n"
            "  if(back.join('/')!==g.join('/'))bad++;\n"
            "  if(J.monthLength(a[0],a[1])!==L.jalaaliMonthLength(b.jy,b.jm))bad++;\n"
            "}\n"
            "console.log(bad);"
        )
        self.assertEqual(out.strip().splitlines()[-1], "0",
                         "g2j/j2g/monthLength باید با jalaali-js رسمی یکی باشد (۱۸۰–۲۰۶)")

    @unittest.skipUnless(NODE, "node در دسترس نیست")
    def test_display_format_tehran_time_fa_digits(self):
        def t(x):
            return chr(0x06F0 + x)

        def build(y, m, d, hh, mm):
            s = f"{y:04d}/{m:02d}/{d:02d} {hh:02d}:{mm:02d}"
            return "".join(t(int(c)) if c.isdigit() else c for c in s)

        out = _run_node(
            "const J=require('" + str(JALALI) + "');\n"
            "console.log(J.fmt('2026-09-23T14:50:15Z'));\n"
            "console.log(J.fmt('2026-09-23T20:00:00Z'));\n"
            "console.log(J.fmt('نه-تاریخ'));\n"
            "let ok=true;for(let i=0;i<10;i++)ok=ok&&J.faNum(i)===String.fromCharCode(0x06F0+i);\n"
            "console.log(ok?'DOK':'DBAD');"
        )
        lines = out.strip().splitlines()
        self.assertEqual(lines[0], build(1405, 7, 1, 18, 20),
                         "UTC 14:50:15 → وقتِ تهران ۱۸:۲۰ با ارقامِ فارسی")
        self.assertEqual(lines[1], build(1405, 7, 1, 23, 30),
                         "UTC 20:00 → ۲۳:۳۰ِ همان روزِ شمسی")
        self.assertEqual(lines[2], "نه-تاریخ", "ورودیِ بد → همان ورودی (بازگشتِ امن)")
        self.assertEqual(lines[3], "DOK", "نگاشتِ ارقامِ فارسی ۰–۹")


class TestJalaliWiring(unittest.TestCase):
    """اتصالِ UI: پنلِ مدیریت، زمانِ شمسی نشان می‌دهد و فونتِ فارسی سرِ استک است."""

    def test_admin_loads_jalali_before_admin_js(self):
        self.assertIn('src="jalali.js"', ADMIN, "پنل باید jalali.js را بار کند")
        self.assertLess(ADMIN.index('src="jalali.js"'), ADMIN.index('src="admin.js"'),
                        "jalali.js باید پیش از admin.js بار شود")

    def test_admin_audit_uses_jalali_fmt(self):
        self.assertIn("Jalali.fmt(e.ts)", ADMINJS, "جدولِ لاگ باید Jalali.fmt را بزند")
        self.assertIn("زمان (تهران، شمسی)", ADMIN, "سرستونِ زمان باید شمسی/تهران را بگوید")
        self.assertNotIn("<td style=\"white-space:nowrap\">${e.ts}</td>", ADMINJS,
                         "زمانِ خامِ UTC نباید مستقیم در جدول بیاید")

    def test_fa_fonts_first_in_all_pages(self):
        for name, html in PAGES.items():
            for line in html.splitlines():
                if "font-family" in line and "sans-serif" in line and "monospace" not in line:
                    head = line.split("font-family:", 1)[1].strip()
                    self.assertTrue(head.startswith('"Vazirmatn"') or head.startswith("Vazirmatn"),
                                    f"{name}: فونتِ فارسی باید سرِ استک باشد: {head[:60]}")
                    break
            else:
                self.fail(f"{name}: استکِ فونتِ اصلی پیدا نشد")

    def test_jalali_is_self_contained(self):
        src = JALALI.read_text(encoding="utf-8")
        self.assertNotIn("http", src, "jalali.js باید کاملاً آفلاین/خودکفا باشد")
        self.assertNotIn("fetch(", src)
        self.assertNotIn("XMLHttpRequest", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
