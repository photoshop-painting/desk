#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""جعبه‌ابزار گزارش: صفحهٔ HTML خودبسندهٔ فارسی (راست‌به‌چپ، آمادهٔ چاپ).

چرا جدا؟ هم «کارنامهٔ آزمون» و هم «پروندهٔ سرمایه‌گذار» یک ظاهر و یک سربرگ
داشته باشند. همه‌چیز درون‌خطی است تا صفحه آفلاین هم درست دیده شود.
"""
from __future__ import annotations

import hashlib
import html
from datetime import datetime

VERSION = "0.1.0"

DEVELOPER_HTML = (
    'دولوپر: <b>مهندس مسعود مجربیان</b> · همراه: <a href="tel:+989126630554">09126630554</a> · Telegram: <a href="https://t.me/Mojarabian" target="_blank">Mojarabian</a> · Instagram: <a href="https://instagram.com/Mojarabian.Art" target="_blank">Mojarabian.Art</a>'
)

CREDIT_HTML = (
    'تهیه‌کنندهٔ جزوات: <a href="https://www.instagram.com/Mojarabian.Art/" target="_blank">'
    "Masoud Mojarabian</a> · "
    '<a href="tel:+989126630554">+989126630554</a> · '
    '<a href="https://t.me/Mojarabian" target="_blank">Telegram: Mojarabian</a> · '
    '<a href="https://www.instagram.com/Mojarabian.Art/" target="_blank">Instagram: Mojarabian.Art</a>'
)

CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { font-family: "Vazirmatn", "Tahoma", "Segoe UI", sans-serif; margin: 0; padding: 28px 20px 60px;
       background: #f6f7f9; color: #1e2430; line-height: 1.9; direction: rtl; }
.wrap { max-width: 1000px; margin: 0 auto; background: #fff; border: 1px solid #e3e6ec; border-radius: 14px;
        padding: 26px 28px 34px; box-shadow: 0 2px 10px rgba(20,30,50,.06); }
h1 { font-size: 24px; margin: 0 0 6px; }
h2 { font-size: 19px; margin: 26px 0 8px; padding-bottom: 6px; border-bottom: 2px solid #eef1f6; }
h3 { font-size: 16px; margin: 18px 0 6px; }
p, li { font-size: 14.5px; }
.sub { color: #5a6473; font-size: 13px; margin: 0 0 14px; }
table { width: 100%; border-collapse: collapse; margin: 10px 0 6px; font-size: 13.5px; }
th, td { border: 1px solid #e3e6ec; padding: 7px 9px; text-align: right; vertical-align: top; }
th { background: #f2f4f8; font-weight: 700; }
td.num, th.num { font-variant-numeric: tabular-nums; direction: ltr; text-align: left; }
tr.pass td:first-child { border-inline-start: 4px solid #1f9d55; }
tr.fail td:first-child { border-inline-start: 4px solid #d64545; }
.kpis { display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0; }
.kpi { flex: 1 1 150px; border: 1px solid #e3e6ec; border-radius: 10px; padding: 10px 12px; background: #fbfcfe; }
.kpi b { display: block; font-size: 20px; }
.kpi span { font-size: 12.5px; color: #5a6473; }
.badge { display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 12.5px; font-weight: 700; }
.badge.ok { background: #e6f6ec; color: #157347; border: 1px solid #b7e2c6; }
.badge.no { background: #fdeaea; color: #b02a2a; border: 1px solid #f3c2c2; }
.note { background: #fff8e6; border: 1px solid #f2dca9; border-radius: 10px; padding: 10px 12px; font-size: 13.5px; }
.honest { background: #eef6ff; border: 1px solid #cfe2fb; border-radius: 10px; padding: 10px 12px; font-size: 13.5px; }
code { background: #f2f4f8; padding: 1px 5px; border-radius: 5px; font-size: 12.8px; direction: ltr;
       display: inline-block; }
.foot { margin-top: 26px; padding-top: 12px; border-top: 1px solid #e3e6ec; color: #5a6473; font-size: 12.5px; }
.foot a { color: #2b5fb0; text-decoration: none; }
.lines { border-bottom: 1px dashed #b9c0cc; height: 22px; margin: 6px 0; }
details { margin: 8px 0; }
summary { cursor: pointer; font-weight: 700; }
@media print { body { background: #fff; padding: 0; } .wrap { border: none; box-shadow: none; } }
"""


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def num(value, digits: int = 2) -> str:
    """عدد فارسی‌خوان: جداکننده هزارگان + رقم اعشار ثابت."""
    if value is None:
        return "—"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return esc(value)
    if abs(f) >= 1000:
        return f"{f:,.{digits}f}"
    return f"{f:.{digits}f}"


def page(title: str, body: str, *, subtitle: str = "", extra_css: str = "") -> str:
    """یک صفحهٔ HTML کامل، خودبسنده و آمادهٔ چاپ."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>{CSS}{extra_css}</style>
</head>
<body>
<div class="wrap">
  <h1>{esc(title)}</h1>
  <p class="sub">{esc(subtitle) if subtitle else ""} · ساخته‌شده: {esc(stamp)}</p>
{body}
  <div class="foot">
    <p>{DEVELOPER_HTML}</p>
    <p>{CREDIT_HTML}</p>
    <p>این صفحه با کد ساخته شده است و همهٔ عددهایش از پرونده‌های همان اجرا خوانده می‌شود؛
    هیچ داده‌ای از اینترنت نمی‌آید و هیچ سود تضمینی در آن ادعا نمی‌شود.</p>
  </div>
</div>
</body>
</html>
"""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest_line(label: str, digest: str) -> str:
    return f'<p class="sub">{esc(label)}: <code>{esc(digest)}</code></p>'
