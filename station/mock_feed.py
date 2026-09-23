#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""خوراک آزمایشی محلی — «قیمت زنده بدون هزینه، بدون اینترنت، بدون کلید».

این برنامه یک بازار ساختگی کوچک را روی همین رایانه سرو می‌کند تا:
  • کل مسیر فنی «دادهٔ زنده» ایستگاه آزمایش شود (اتصال، تازگی داده، به‌روزرسانی، سیگنال)،
  • و بتوانید کارکرد برنامه را جلوی سرمایه‌گذار بگذارید، بدون هیچ هزینه‌ای.

صادق باشید: این قیمت‌ها ساختگی‌اند. ایستگاه هم همه‌جا همین را برچسب می‌زند.
برای اعداد واقعی، از پروفایل‌های رایگان در گام ۲ یا سرویس خریدنی استفاده کنید.

اجرا:  python mock_feed.py            (روی درگاه ۸۷۸۸)
       python mock_feed.py --port 9001 --event-after 6 --speed 2
"""
from __future__ import annotations

import argparse
import json
import math
import random
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

VERSION = "0.1.0"
BASE = Path(__file__).resolve().parent
HISTORY_CSV = BASE / "demo" / "history-demo.csv"

# قیمت‌های شروع ساختگی، فقط برای اینکه جدول پر به‌نظر برسد.
START_PRICES: dict[str, float] = {
    "اهرم": 20_000.0, "فولاد": 7_000.0, "کگل": 9_800.0, "شپنا": 12_500.0,
    "خساپا": 2_100.0, "طلا": 46_000_000.0, "وبملت": 5_400.0, "شاخص": 2_450_000.0,
}
VOLATILITY: dict[str, float] = {"default": 0.0016, "طلا": 0.0030, "اهرم": 0.0035}


class Market:
    """بازار ساختگی: گشت تصادفی آرام + یک رخداد برنامه‌ریزی‌شده برای دیدن سیگنال."""

    def __init__(self, *, seed: int = 1405, speed: float = 1.0, event_after: int = 10):
        self.rng = random.Random(seed)
        self.speed = max(0.1, float(speed))
        self.event_after = max(0, int(event_after))
        self.t0 = time.time()
        self.hits = 0
        self.event_on = False
        self.lock = threading.Lock()

    def tick(self, symbol: str) -> float:
        base = START_PRICES.get(symbol)
        if base is None:                        # نماد ناشناس: از درهم‌سازی نام یک قیمت پایدار بساز
            base = 1_000.0 + (abs(hash(symbol)) % 9_000)
        vol = VOLATILITY.get(symbol, VOLATILITY["default"])
        elapsed = time.time() - self.t0
        # گشت تصادفی + موج آرام، تا نمودار زنده و باورپذیر باشد
        wave = math.sin(elapsed / 21.0) * 0.35 + math.sin(elapsed / 7.0) * 0.15
        noise = self.rng.gauss(0, 1) * vol              # نوسان دیدنی هر خواندن (مثل نوار قیمت)
        bias = -0.02 if (symbol == "اهرم" and self.event_on) else 0.0   # رخداد: مبنای آتی باز می‌شود
        rel = 0.03 * wave + noise * math.sqrt(self.speed) + bias
        return round(base * (1.0 + rel), 2)

    def hit(self) -> bool:
        with self.lock:
            self.hits += 1
            if self.event_after and self.hits >= self.event_after and not self.event_on:
                self.event_on = True
                return True
            return False


MARKET = Market()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):          # لاگ پیش‌فرض را ساکت می‌کنیم
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, code: int = 200) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)

        if u.path == "/quote":
            symbol = (q.get("symbol") or [""])[0].strip()
            if not symbol:
                return self._json({"ok": False, "error": "پارامتر symbol لازم است"}, 400)
            just = MARKET.hit()
            price = MARKET.tick(symbol)
            return self._json({
                "ok": True,
                "data": [{"symbol": symbol, "pl": price,
                          "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                          "source": "خوراک آزمایشی محلی (ساختگی)"}],
                "event": just,
            })

        if u.path == "/symbols":
            return self._json({"ok": True, "symbols": list(START_PRICES),
                               "event_after": MARKET.event_after, "hits": MARKET.hits})

        if u.path == "/history.csv":
            if HISTORY_CSV.exists():
                return self._send(200, HISTORY_CSV.read_bytes(), "text/csv; charset=utf-8")
            return self._json({"ok": False, "error": "پروندهٔ تاریخ نمونه پیدا نشد"}, 404)

        if u.path in ("/", "/index.html"):
            return self._send(200, page_html(MARKET).encode("utf-8"), "text/html; charset=utf-8")

        return self._json({"ok": False, "error": "مسیر ناشناخته"}, 404)


def page_html(market: Market) -> str:
    """صفحهٔ نمایش قیمت‌های زنده — تک‌پرونده و آفلاین (فقط برای چشم سرمایه‌گذار)."""
    symbols = "،".join(f"«{s}»" for s in START_PRICES)
    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>خوراک آزمایشی محلی — بازار ساختگی</title>
<style>
 body {{ margin:0; background:#0f172a; color:#e5e7eb; font-family:Tahoma,"Segoe UI",sans-serif; line-height:1.9; }}
 .wrap {{ max-width:820px; margin:0 auto; padding:22px; }}
 h1 {{ font-size:19px; margin:0 0 6px; }}
 .warn {{ background:#3b2a00; border:1px solid #7c5e00; border-radius:10px; padding:10px 12px; font-size:13.5px; margin:12px 0; }}
 table {{ width:100%; border-collapse:collapse; font-size:14px; }}
 th,td {{ padding:7px 10px; border-bottom:1px solid #1f2a44; text-align:right; }}
 th {{ background:#16223c; font-size:12.5px; }}
 td.num {{ font-variant-numeric: tabular-nums; }}
 .up {{ color:#7ee2a8; }} .down {{ color:#fca5a5; }}
 .pulse {{ display:inline-block; width:9px; height:9px; border-radius:50%; background:#7ee2a8; margin-left:6px;
           animation:p 1.4s infinite; }}
 @keyframes p {{ 0%{{opacity:1}} 50%{{opacity:.25}} 100%{{opacity:1}} }}
 .hint {{ color:#94a3b8; font-size:12.5px; }}
 code {{ direction:ltr; display:inline-block; background:#16223c; padding:1px 6px; border-radius:5px; font-size:12.5px; }}
</style></head><body><div class="wrap">
<h1><span class="pulse"></span>خوراک آزمایشی محلی — بازار ساختگی</h1>
<div class="warn">این قیمت‌ها <b>ساختگی</b> هستند و از هیچ بازار واقعی نمی‌آیند. کاربردشان فقط این است که
مسیر «دادهٔ زنده» ایستگاه، بدون هزینه و بدون اینترنت، آزمایش و نمایش داده شود.
برای قیمت واقعی، در گام ۲ ایستگاه یکی از پروفایل‌های رایگان را آزمایش کنید.</div>
<p class="hint">نمادهای این خوراک: {symbols} — نشانی قیمت برای ایستگاه:
<code>http://127.0.0.1:{getattr(market, "port", 8788)}/quote?symbol={{symbol}}</code></p>
<table><thead><tr><th>نماد</th><th class="num">قیمت ساختگی</th><th class="num">تغییر</th><th>آخرین به‌روزرسانی</th></tr></thead>
<tbody id="rows"><tr><td colspan="4" class="hint">در حال خواندن…</td></tr></tbody></table>
<p class="hint">هر دو ثانیه خودکار تازه می‌شود. رخداد برنامه‌ریزی‌شده بعد از
<b>{market.event_after}</b> درخواست فعال می‌شود (برای دیدن اینکه ایستگاه چطور یک سیگنال تازه را می‌گیرد).</p>
</div><script>
const symbols = {json.dumps(list(START_PRICES), ensure_ascii=False)};
let last = {{}};
async function tick() {{
  const rows = [];
  for (const s of symbols) {{
    try {{
      const r = await fetch("/quote?symbol=" + encodeURIComponent(s));
      const j = await r.json();
      const p = j.data[0].pl;
      const prev = last[s];
      const diff = prev ? (p - prev) : 0;
      last[s] = p;
      const cls = diff > 0 ? "up" : (diff < 0 ? "down" : "");
      const arw = diff > 0 ? "▲" : (diff < 0 ? "▼" : "•");
      rows.push(`<tr><td>${{s}}</td><td class="num">${{p.toLocaleString("fa-IR")}}</td>
        <td class="num ${{cls}}">${{arw}} ${{Math.abs(diff).toLocaleString("fa-IR")}}</td>
        <td class="hint">${{new Date().toLocaleTimeString("fa-IR")}}</td></tr>`);
    }} catch (e) {{ rows.push(`<tr><td>${{s}}</td><td colspan="3" class="hint">نیامد</td></tr>`); }}
  }}
  document.getElementById("rows").innerHTML = rows.join("");
}}
tick(); setInterval(tick, 2000);
</script></body></html>"""


def serve(port: int = 8788, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), Handler)
    return httpd


def main(argv: list[str] | None = None) -> int:
    global MARKET
    ap = argparse.ArgumentParser(description="خوراک آزمایشی محلی ایستگاه (دادهٔ ساختگی)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8788)
    ap.add_argument("--seed", type=int, default=1405)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--event-after", type=int, default=10, help="بعد از چند درخواست، رخداد سیگنال‌ساز فعال شود")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    MARKET = Market(seed=args.seed, speed=args.speed, event_after=args.event_after)
    httpd = serve(args.port, args.host)
    if not args.quiet:
        print(f"خوراک آزمایشی محلی روی http://127.0.0.1:{args.port}/ آماده است (دادهٔ ساختگی).")
        print(f"نشانی قیمت برای ایستگاه: http://127.0.0.1:{args.port}/quote?symbol={{symbol}}")
        print("برای بستن، کلید Ctrl+C را بزنید.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nبسته شد.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
