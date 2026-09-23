#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""امکان‌سنجی مسیرهای داده، پیش از خرید: کدام روش واقعاً به کار ایستگاه می‌خورد؟

سه روشی که صاحب پرونده نام برد، این‌جا سنجیده می‌شوند:
  ۱. خرید وب‌سرویس رسمی (pull، نیازمند کلید و پول)
  ۲. سرویس‌های رایگان سایت مرجع (pull، بی‌تعهد، احتمال گپ زمانی)
  ۳. پوش لحظه‌ای (websocket / RLC) از کارگزاری یا سازمان بورس

این ابزار «تبلیغ» نمی‌کند؛ فقط می‌سنجد و می‌گوید:
  • کدام نشانی جواب می‌دهد و چقدر طول می‌کشد،
  • کدام میدان دادهٔ ایستگاه از آن درمی‌آید و کدام درنمی‌آید،
  • دو فراخوانی پشت‌سرهم چه می‌گویند (تازه می‌شود یا همان عدد می‌مانَد)،
  • و پوش لحظه‌ای اصلاً دسترسی‌پذیر است یا نه.

اجرا:
  python data_sources.py --all --symbol فولاد
  python data_sources.py --ws wss://example.ir/market
  python data_sources.py --fixture          (نمایش شکل خروجی با دادهٔ ساختگی محلی)
  python data_sources.py --sheet            (برگهٔ نیاز داده برای فرستادن به فروشنده)
"""
from __future__ import annotations

import argparse
import json
import random
import socket
import ssl
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

VERSION = "0.1.0"
BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
TSETMC_HOST = "https://cdn.tsetmc.com"

for p in (str(BASE),):
    if p not in sys.path:
        sys.path.insert(0, p)

import datafeed  # noqa: E402
import reportkit as rk  # noqa: E402

# ---------------------------------------------------------------- نقشهٔ نقاط پایانی
ENDPOINTS: list[dict] = [
    {"name": "symbol_search", "label": "جست‌وجوی نماد و گرفتن کد نماد",
     "url": TSETMC_HOST + "/api/Instrument/GetInstrumentSearch/{symbol}",
     "needs": "symbol", "gives": "کد نماد (insCode) برای بقیهٔ فراخوانی‌ها، نام کامل، بازار",
     "paths": ["instrumentSearch.0.insCode", "instrumentSearch.0.lVal18AFC", "instrumentSearch.0.market"],
     "dynamic": False},
    {"name": "price_info", "label": "اطلاعات قیمت یک نماد",
     "url": TSETMC_HOST + "/api/ClosingPrice/GetClosingPriceInfo/{code}",
     "needs": "code", "gives": "آخرین قیمت، دامنهٔ مجاز، قیمت پایانی",
     "paths": ["closingPriceInfo.pDrCotVal", "closingPriceInfo.priceMin", "closingPriceInfo.priceMax",
               "closingPriceInfo.pClosing"]},
    {"name": "closing_daily", "label": "قیمت پایانی روزانه (سری زمانی)",
     "url": TSETMC_HOST + "/api/ClosingPrice/GetClosingPriceDailyList/{code}/0",
     "needs": "code", "gives": "تاریخچهٔ قیمت پایانی، حجم و ارزش معاملات (لازم برای پس‌آزمایی)",
     "paths": ["closingPriceDaily.0.pClosing", "closingPriceDaily.0.pDrCotVal",
               "closingPriceDaily.0.vol", "closingPriceDaily.0.qTotTran5J"]},
    {"name": "best_limits", "label": "بهترین سفارش‌های خرید و فروش",
     "url": TSETMC_HOST + "/api/BestLimits/{code}",
     "needs": "code", "gives": "بهترین خرید/فروش و حجمشان (برای محاسبهٔ اسپرد و نقدشوندگی)",
     "paths": ["bestLimits.0.pMeDemand", "bestLimits.0.pMeOffer"]},
    {"name": "market_watch", "label": "تابلوی کل بازار",
     "url": TSETMC_HOST + "/api/ClosingPrice/GetMarketWatch",
     "needs": "", "gives": "قیمت آخرین معاملهٔ همهٔ نمادها در یک درخواست",
     "paths": ["marketwatchData.0.pDrCotVal", "marketwatchData.0.lVal18AFC"]},
    {"name": "client_type", "label": "خریدار و فروشندهٔ حقیقی و حقوقی",
     "url": TSETMC_HOST + "/api/ClientType/GetClientTypeHistory/{code}",
     "needs": "code", "gives": "ترکیب حقیقی/حقوقی (برای تحلیل جریان پول، اختیاری)",
     "paths": ["clientType.0.buy_I_Volume", "clientType.0.sell_I_Volume"]},
]

# نیازهای خودِ ایستگاه، برای داوری روش‌ها
NEEDS: list[dict] = [
    {"field": "قیمت پایه سهم یا صندوق", "freq": "هر ۱ تا ۵ دقیقه", "route": "pull (رایگان یا پولی)"},
    {"field": "قیمت آتی", "freq": "هر ۱ تا ۵ دقیقه", "route": "pull؛ در سرویس‌های رایگان باید جدا تست شود"},
    {"field": "قیمت اعمال و پرمیوم اختیار", "freq": "هر ۱ تا ۵ دقیقه", "route": "pull؛ پوشش کامل تضمین‌شده نیست"},
    {"field": "نقدشوندگی و اسپرد", "freq": "هر ۱ تا ۵ دقیقه", "route": "pull (بهترین سفارش‌ها)"},
    {"field": "روز تا سررسید", "freq": "روزانه", "route": "محاسبهٔ خودمان از تقویم"},
    {"field": "وجه تضمین هر قرارداد", "freq": "روزانه (اعلامی)", "route": "فقط سامانهٔ کارگزاری، نه سرویس داده"},
    {"field": "تاریخ قیمت برای پس‌آزمایی", "freq": "گذشته", "route": "سری روزانه؛ در سرویس رایگان کوتاه است"},
]


# ---------------------------------------------------------------- سنجش pull
def _top_keys(payload) -> list[str]:
    if isinstance(payload, dict):
        return list(payload.keys())[:8]
    if isinstance(payload, list):
        return [f"list[{len(payload)}]"]
    return [type(payload).__name__]


def probe_endpoint(ep: dict, *, symbol: str = "", code: str = "", host: str = "",
                   allow_network: bool = True, timeout: float = 12.0) -> dict:
    """یک نقطهٔ پایانی را می‌خواند و می‌گوید چه آمد، چقدر طول کشید، و کدام میدان‌ها درآمد."""
    url = ep["url"]
    if host:
        url = url.replace(TSETMC_HOST, host.rstrip("/"))
    if ep["needs"] == "symbol":
        if not symbol:
            return _fail(ep, "نام نماد داده نشده است.")
        url = url.replace("{symbol}", rk_quote(symbol))
    elif ep["needs"] == "code":
        if not code:
            return _fail(ep, "کد نماد (insCode) نداریم؛ اول جست‌وجوی نماد باید موفق شود.")
        url = url.replace("{code}", str(code))
    if not allow_network:
        return _fail(ep, "شبکه خاموش است؛ سنجش انجام نشد.", url=url)

    started = time.time()
    text, status = datafeed.fetch(url, timeout=timeout, retries=0, cache_name=None, cache_seconds=0,
                        stale_ok=False)
    latency = int((time.time() - started) * 1000)
    if not text:
        return _fail(ep, f"پاسخی نیامد ({status})", url=url, latency_ms=latency)
    try:
        payload = json.loads(text)
    except Exception:
        return _fail(ep, "پاسخ JSON نبود (شاید صفحهٔ HTML باشد)", url=url, latency_ms=latency,
                     bytes=len(text))
    found: list[dict] = []
    for path in ep["paths"]:
        value = datafeed.dig(payload, path)
        if value is not None:
            found.append({"path": path, "value": value if isinstance(value, (int, float, str)) else str(value)})
    primary = next((f["value"] for f in found
                    if isinstance(f["value"], (int, float)) and not isinstance(f["value"], bool)), None)
    if primary is None:
        primary = none_primary(payload)
    return {"name": ep["name"], "label": ep["label"], "ok": bool(found),
            "url": url, "http": status, "latency_ms": latency, "bytes": len(text),
            "top_keys": _top_keys(payload), "fields": found, "count": len(found),
            "primary": primary, "reason": "پاسخ سالم آمد" if found else
            "پاسخ آمد ولی هیچ‌یک از میدان‌های موردنیاز پیدا نشد؛ ساختار عوض شده است",
            "gives": ep["gives"]}


def none_primary(payload) -> float | None:
    """یک عدد کلیدی برای مقایسهٔ دو فراخوانی (اولین عدد معنادار در پاسخ)."""
    for path, value in datafeed.numeric_paths(payload, max_items=6):
        if isinstance(value, (int, float)) and value not in (0, 1):
            return float(value)
    return None


def _fail(ep: dict, reason: str, *, url: str = "", latency_ms: int = 0, bytes: int = 0) -> dict:
    return {"name": ep["name"], "label": ep["label"], "ok": False, "url": url or ep["url"],
            "http": "", "latency_ms": latency_ms, "bytes": bytes, "top_keys": [], "fields": [],
            "count": 0, "primary": None, "reason": reason, "gives": ep["gives"]}


def stability_check(ep: dict, *, symbol: str = "", code: str = "", host: str = "",
                    wait: float = 2.0, timeout: float = 12.0) -> dict:
    """دو فراخوانی پشت‌سرهم: داده تازه می‌شود یا همان عدد می‌مانَد؟

    این همان «گپ زمانی» است که خودتان اشاره کردید: سرویس رایگان ممکن است بی‌حرکت باشد.
    """
    if not ep.get("dynamic", True):
        return {"name": ep["name"], "checked": False,
                "reason": "این نشانی قیمت نیست؛ سنجش تازگی برایش معنا ندارد."}
    first = probe_endpoint(ep, symbol=symbol, code=code, host=host, timeout=timeout)
    if not first["ok"]:
        return {"name": ep["name"], "checked": False, "reason": first["reason"]}
    time.sleep(max(0.2, wait))
    second = probe_endpoint(ep, symbol=symbol, code=code, host=host, timeout=timeout)
    a, b = first.get("primary"), second.get("primary")
    if a is None or b is None:
        verdict, note = "نامعلوم", "عدد کلیدی برای مقایسه پیدا نشد."
    elif a == b:
        verdict = "بی‌حرکت"
        note = "دو فراخوانی با فاصلهٔ چند ثانیه همان عدد را دادند؛ یعنی نرخ به‌روزرسانی این نشانی کند است."
    else:
        verdict = "تازه‌شونده"
        note = "عدد بین دو فراخوانی عوض شد؛ این نشانی زنده است."
    return {"name": ep["name"], "checked": True, "verdict": verdict, "note": note,
            "first": a, "second": b, "latency_ms": first["latency_ms"]}


def probe_all(*, symbol: str = "فولاد", code: str = "", host: str = "", allow_network: bool = True,
              timeout: float = 12.0, with_stability: bool = True) -> dict:
    """همهٔ نقاط پایانی رایگان را می‌سنجد و کد نماد را هم در صورت نیاز درمی‌آورد."""
    items = []
    resolved = code
    search = next(e for e in ENDPOINTS if e["name"] == "symbol_search")
    search_res = probe_endpoint(search, symbol=symbol, host=host, allow_network=allow_network, timeout=timeout)
    items.append(search_res)
    if not resolved and search_res["ok"]:
        for f in search_res["fields"]:
            if f["path"].endswith("insCode") and str(f["value"]).strip():
                resolved = str(f["value"]).strip()
                break
    for ep in ENDPOINTS:
        if ep["name"] == "symbol_search":
            continue
        items.append(probe_endpoint(ep, symbol=symbol, code=resolved, host=host,
                                    allow_network=allow_network, timeout=timeout))
    stability = []
    if with_stability and allow_network:
        for ep in ENDPOINTS:
            if ep["needs"] == "code" and not resolved:
                continue
            stability.append(stability_check(ep, symbol=symbol, code=resolved, host=host, timeout=timeout))
    ok_count = len([1 for i in items if i["ok"]])
    return {"ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "symbol": symbol, "code": resolved, "host": host or TSETMC_HOST,
            "items": items, "stability": stability,
            "summary": {"total": len(items), "ok": ok_count, "failed": len(items) - ok_count,
                        "usable_for_engine": ok_count >= 3},
            "verdict": (f"{ok_count} از {len(items)} نشانی جواب داد. "
                        + ("برای شروع کافی است؛ وجه تضمین را همچنان از کارگزاری بردارید."
                           if ok_count >= 3 else
                           "از این محیط به سامانه‌های ایرانی دسترسی نبود یا ساختار عوض شده؛ "
                           "همین آزمون را روی رایانهٔ خودتان (داخل ایران) اجرا کنید."))}


def rk_quote(value: str) -> str:
    from urllib.parse import quote
    return quote(str(value))


# ---------------------------------------------------------------- سنجش پوش لحظه‌ای
WS_VERDICTS = {
    101: "قابل اتصال و ارتقا؛ اگر توکن داشته باشید، پیام‌ها هم می‌آیند.",
    400: "دسترسی هست ولی درخواست ناقص است (احتمالاً پارامتر یا توکن لازم دارد).",
    401: "سرویس هست ولی احراز هویت می‌خواهد؛ بی توکن راه نمی‌دهد.",
    403: "سرویس هست ولی اجازه نمی‌دهد (دسترسی شما مجاز نیست).",
    404: "نشانی یا مسیر اشتباه است.",
    426: "ارتقا لازم است ولی سرور شرایطش را نپذیرفت.",
}


def probe_ws(url: str, *, timeout: float = 8.0, extra_headers: str = "") -> dict:
    """آیا اصلاً می‌شود به پوش لحظه‌ای وصل شد؟ (TCP + TLS + تلاش ارتقای HTTP)

    این آزمون نمی‌گوید «داده می‌آید»؛ می‌گوید «سرویس هست یا نه و چه می‌خواهد».
    برای خواندن پیام‌ها، توکن و مجوز کارگزاری لازم است.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("ws", "wss") or not parsed.hostname:
        return {"url": url, "ok": False, "tcp": False, "tls": False, "status": None,
                "verdict": "نشانی نامعتبر", "note": "نشانی باید با ws:// یا wss:// شروع شود."}
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    out = {"url": url, "ok": False, "tcp": False, "tls": False, "status": None,
           "verdict": "", "note": "", "host": parsed.hostname, "port": port}
    started = time.time()
    try:
        sock = socket.create_connection((parsed.hostname, port), timeout=timeout)
        out["tcp"] = True
    except OSError as e:
        out["verdict"] = "دسترس نیست"
        out["note"] = f"اتصال TCP ممکن نشد: {type(e).__name__} ({e})"
        out["latency_ms"] = int((time.time() - started) * 1000)
        return out
    try:
        if parsed.scheme == "wss":
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=parsed.hostname)
            out["tls"] = True
        key = "dGhlIHNhbXBsZSBub25jZQ=="
        headers = [f"GET {path} HTTP/1.1", f"Host: {parsed.hostname}",
                   "Upgrade: websocket", "Connection: Upgrade",
                   f"Sec-WebSocket-Key: {key}", "Sec-WebSocket-Version: 13"]
        for line in [x for x in extra_headers.split(";") if x.strip()]:
            headers.append(line.strip())
        sock.sendall(("\r\n".join(headers) + "\r\n\r\n").encode("utf-8"))
        sock.settimeout(timeout)
        raw = sock.recv(4096).decode("utf-8", errors="replace")
        first_line = raw.splitlines()[0] if raw else ""
        code = None
        parts = first_line.split()
        if len(parts) >= 2 and parts[1].isdigit():
            code = int(parts[1])
        out["status"] = code
        out["ok"] = code == 101
        out["verdict"] = WS_VERDICTS.get(code, f"پاسخ {code or 'ناشناخته'} از سرور")
        out["note"] = ("پاسخ سرور: " + first_line) if first_line else "سرور چیزی برنگرداند."
        out["response_preview"] = raw[:300]
    except (ssl.SSLError, OSError, socket.timeout) as e:
        out["verdict"] = "دسترسی شبکه‌ای ناتمام"
        out["note"] = f"{type(e).__name__}: {e}"
    finally:
        try:
            sock.close()
        except OSError:
            pass
        out["latency_ms"] = int((time.time() - started) * 1000)
    return out


def real_ws_read(url: str, *, token: str = "", seconds: float = 5.0) -> dict:
    """اگر کتابخانهٔ websocket-client نصب باشد، واقعاً پیام می‌خواند؛ وگرنه صریح می‌گوید نبود."""
    try:
        import websocket  # type: ignore
    except ImportError:
        return {"ok": False, "reason": "کتابخانهٔ websocket-client نصب نیست. برای خواندن واقعی پیام‌ها: "
                                       "pip install websocket-client"}
    header = [f"Authorization: Bearer {token}"] if token else []
    try:
        ws = websocket.create_connection(url, timeout=seconds, header=header)
        ws.settimeout(seconds)
        msg = ws.recv()
        ws.close()
        return {"ok": True, "first_message": str(msg)[:400]}
    except Exception as e:                                  # پیام روشن، بی استثنای خام
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


# ---------------------------------------------------------------- سرور نمونه (برای نمایش شکل خروجی)
FIXTURE_DATA = {
    "instrumentSearch": [{"insCode": "46348559193224090", "lVal18AFC": "فولاد", "market": 1}],
    "closingPriceInfo": {"pDrCotVal": 7015, "priceMin": 6650, "priceMax": 7350, "pClosing": 7015},
    "closingPriceDaily": [{"pClosing": 7015, "pDrCotVal": 7015, "vol": 124500000, "qTotTran5J": 8720}],
    "bestLimits": [{"pMeDemand": 7010, "pMeOffer": 7020}],
    "marketwatchData": [{"lVal18AFC": "فولاد", "pDrCotVal": 7015}],
    "clientType": [{"buy_I_Volume": 51230000, "sell_I_Volume": 40110000}],
}


class FixtureHandler(BaseHTTPRequestHandler):
    """سرور نمونهٔ محلی با همان ساختار نشانی‌های واقعی (داده ساختگی است)."""

    protocol_version = "HTTP/1.1"
    hits = 0

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        type(self).hits += 1
        payload = json.loads(json.dumps(FIXTURE_DATA))       # رونوشت تازه
        # هر فراخوانی، قیمت‌ها را کمی جابه‌جا می‌کند تا «بی‌حرکت» به‌نظر نرسد
        jitter = random.Random(type(self).hits).uniform(-0.004, 0.004)
        info = payload["closingPriceInfo"]
        for key in ("pDrCotVal", "pClosing", "priceMin", "priceMax"):
            info[key] = round(float(info[key]) * (1 + jitter), 2)
        payload["closingPriceDaily"][0]["pDrCotVal"] = round(
            7015 * (1 + jitter), 2)
        payload["closingPriceDaily"][0]["pClosing"] = round(7015 * (1 + jitter), 2)
        payload["bestLimits"][0]["pMeDemand"] = round(7010 * (1 + jitter), 2)
        payload["bestLimits"][0]["pMeOffer"] = round(7020 * (1 + jitter), 2)
        payload["marketwatchData"][0]["pDrCotVal"] = round(7015 * (1 + jitter), 2)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Fixture", "synthetic")
        self.end_headers()
        self.wfile.write(body)


def start_fixture(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    """سرور نمونه را روی یک درگاه آزاد بالا می‌آورد و نشانی‌اش را برمی‌گرداند."""
    httpd = ThreadingHTTPServer(("127.0.0.1", port), FixtureHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


# ---------------------------------------------------------------- خروجی‌ها
def build_matrix() -> list[dict]:
    """داوری سه مسیر در برابر نیاز ایستگاه."""
    return [
        {"route": "۱. خرید وب‌سرویس رسمی (pull)",
         "gives": "قیمت زنده و تاریخچهٔ کامل، قرارداد و فاکتور",
         "misses": "وجه تضمین، و «تصمیم»",
         "cost": "بالا (استعلام لازم است)",
         "verdict": "فعلاً نه: پول جلوتر از شاهد. اگر خریدار شرکت باشد و فاکتور رسمی لازم داشته باشد، بله.",
         "test": "پس از گرفتن کلید: قالب نشانی را در گام ۲ بگذارید و «آزمایش اتصال» بزنید."},
        {"route": "۲. سرویس‌های عمومی سایت مرجع (pull)",
         "gives": "قیمت پایه، بخشی از آتی و اختیار، بهترین سفارش‌ها، سری روزانه",
         "misses": "وجه تضمین؛ ضمانت ندارد و ممکن است گپ زمانی داشته باشد",
         "cost": "صفر",
         "verdict": "بله، همین امروز: کافی است. فقط گپ و بی‌حرکتی را با همین ابزار بسنجید.",
         "test": "«سنجش نقاط پایانی» + «سنجش دوفراخوانی» در همین صفحه."},
        {"route": "۳. پوش لحظه‌ای (websocket / RLC)",
         "gives": "جریان لحظه‌ای، اگر کارگزاری یا سازمان دسترسی بدهد",
         "misses": "برای افراد عادی معمولاً بسته است؛ مجوز و قرارداد می‌خواهد",
         "cost": "نامعلوم، وابسته به قرارداد",
         "verdict": "نیاز نداریم: افق تصمیم این راهبردها دقیقه‌ای است، نه میلی‌ثانیه‌ای.",
         "test": "«سنجش پوش لحظه‌ای»: اول ببینید سرویس هست یا نه، بعد سراغ مجوز بروید."},
    ]


def requirement_sheet() -> str:
    """برگهٔ نیاز داده، برای فرستادن به فروشنده‌ها و گرفتن استعلام قیمت."""
    lines = ["# برگهٔ نیاز داده (برای فرستادن به فروشنده‌ها)",
             "",
             "سلام. برای یک سامانهٔ تصمیم‌گیری روی اوراق مشتقهٔ بورس تهران، این داده‌ها را لازم دارم.",
             "لطفاً برای هر ردیف بنویسید: دارید یا نه، نرخ به‌روزرسانی، و قیمت ماهانه.",
             "",
             "| داده | نرخ لازم | توضیح | دارید؟ | نرخ به‌روزرسانی | قیمت |",
             "|---|---|---|---|---|---|",
             "| قیمت پایه سهام و صندوق‌ها | ۱ تا ۵ دقیقه | همهٔ نمادهای بورس و فرابورس | | | |",
             "| قیمت قراردادهای آتی | ۱ تا ۵ دقیقه | کالا و اوراق | | | |",
             "| قیمت اعمال و پرمیوم اختیار خرید و فروش | ۱ تا ۵ دقیقه | همهٔ سررسیدها | | | |",
             "| بهترین سفارش خرید و فروش | ۱ تا ۵ دقیقه | برای محاسبهٔ اسپرد و نقدشوندگی | | | |",
             "| سری روزانهٔ قیمت پایانی | روزانه | تاریخچهٔ حداقل ۱۲ ماه برای پس‌آزمایی | | | |",
             "| حجم و ارزش معاملات | روزانه | برای فیلتر نقدشوندگی | | | |",
             "| وضعیت نماد (باز، متوقف) | روزانه | برای جلوگیری از تصمیم روی نماد بسته | | | |",
             "",
             "## پرسش‌های فنی",
             "",
             "۱. قالب دسترسی: REST یا websocket؟ مسیر JSON پاسخ به چه شکل است؟",
             "۲. احراز هویت: کلید در نشانی یا در هدر؟ محدودیت تعداد درخواست در دقیقه چقدر است؟",
             "۳. پایداری: ساعت کاری و قطعی‌های معمول؛ در صورت قطع، داده دوباره پر می‌شود؟",
             "۴. پرداخت: ریالی؟ فاکتور رسمی؟ دورهٔ زمانی و شرایط لغو؟",
             "۵. اجازهٔ استفاده: آیا استفاده در یک سامانهٔ تحلیل و تصمیم‌یار مجاز است؟",
             "",
             "## یادآوری برای خودم",
             "",
             "- وجه تضمین را هیچ فروشندهٔ داده‌ای ندارد؛ از سامانهٔ کارگزاری برداشته می‌شود (۶۰ ثانیه در روز).",
             "- تا وقتی کارنامهٔ آزمون «آماده» نشود، خرید داده معنی ندارد: اول باید ببینم موتور روزانه فرصت پیدا می‌کند.",
             "- پیش از امضا، قالب نشانی فروشنده را در گام ۲ ایستگاه می‌گذارم و «آزمایش اتصال» می‌زنم.",
             ""]
    return "\n".join(lines)


def build_report(result: dict, matrix: list[dict], ws: dict | None = None,
                 path: Path | None = None) -> Path:
    out = Path(path or (DATA / "data-feasibility.html"))
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = "".join(
        f'<tr class="{"pass" if i["ok"] else "fail"}"><td>{rk.esc(i["label"])}</td>'
        f'<td>{"✅" if i["ok"] else "✗"} {rk.esc(i["reason"])}</td>'
        f'<td class="num">{rk.esc(i.get("latency_ms", 0))}</td>'
        f'<td class="num">{rk.esc(i.get("http", ""))}</td>'
        f'<td class="num">{rk.esc(", ".join(i.get("top_keys") or []) or "—")}</td></tr>'
        for i in result["items"])
    stability = "".join(
        f'<tr><td>{rk.esc(s["name"])}</td><td>{rk.esc(s.get("verdict", "سنجیده نشد"))}</td>'
        f'<td>{rk.esc(s.get("note", s.get("reason", "")))}</td></tr>' for s in result.get("stability", []))
    mrows = "".join(
        f'<tr><td>{rk.esc(m["route"])}</td><td>{rk.esc(m["gives"])}</td><td>{rk.esc(m["misses"])}</td>'
        f'<td>{rk.esc(m["cost"])}</td><td>{rk.esc(m["verdict"])}</td><td class="hint">{rk.esc(m["test"])}</td></tr>'
        for m in matrix)
    needs = "".join(f'<tr><td>{rk.esc(n["field"])}</td><td>{rk.esc(n["freq"])}</td>'
                    f'<td>{rk.esc(n["route"])}</td></tr>' for n in NEEDS)
    ws_block = ""
    if ws:
        ws_block = (f'<h2>سنجش پوش لحظه‌ای</h2><table><tbody>'
                    f'<tr><td>نشانی</td><td class="num">{rk.esc(ws.get("url", ""))}</td></tr>'
                    f'<tr><td>اتصال TCP</td><td class="num">{"بله" if ws.get("tcp") else "نه"}</td></tr>'
                    f'<tr><td>لایهٔ امن (TLS)</td><td class="num">{"بله" if ws.get("tls") else "نه"}</td></tr>'
                    f'<tr><td>کد پاسخ ارتقا</td><td class="num">{rk.esc(ws.get("status") or "—")}</td></tr>'
                    f'<tr><td>داوری</td><td>{rk.esc(ws.get("verdict", ""))}</td></tr>'
                    f'<tr><td>توضیح</td><td>{rk.esc(ws.get("note", ""))}</td></tr></tbody></table>')
    body = [
        '<div class="honest"><b>این سنجش چه می‌گوید و چه نمی‌گوید.</b> می‌گوید کدام نشانی جواب می‌دهد، '
        'چقدر طول می‌کشد، و کدام میدان دادهٔ موتور از آن درمی‌آید. نمی‌گوید سود می‌دهد یا نه؛ '
        'و اگر از بیرون ایران اجرا شود، نبود دسترسی به سامانه‌های ایرانی را باید صریح گزارش کند، نه اینکه '
        'آن را به‌حساب «خرابی سرویس» بگذارد.</div>',
        f'<p class="sub">زمان اجرا: {rk.esc(result["ran_at"])} · نماد: {rk.esc(result["symbol"])} · '
        f'کد نماد: <code>{rk.esc(result["code"] or "—")}</code> · میزبان: <code>{rk.esc(result["host"])}</code></p>',
        '<h2>۱. نیاز واقعی موتور</h2>',
        '<table><thead><tr><th>داده</th><th>هر چند وقت</th><th>از کدام مسیر</th></tr></thead><tbody>'
        + needs + '</tbody></table>',
        '<h2>۲. سنجش سرویس‌های رایگان سایت مرجع</h2>',
        '<table><thead><tr><th>نقطهٔ پایانی</th><th>نتیجه</th><th class="num">میلی‌ثانیه</th>'
        '<th class="num">HTTP</th><th class="num">کلیدهای پاسخ</th></tr></thead><tbody>' + rows + '</tbody></table>',
        f'<p class="note">{rk.esc(result["verdict"])}</p>',
        '<h2>۳. گپ زمانی: دو فراخوانی پشت‌سرهم</h2>',
        '<table><thead><tr><th>نقطهٔ پایانی</th><th>داوری</th><th>توضیح</th></tr></thead><tbody>'
        + stability + '</tbody></table>',
        ws_block,
        '<h2>۴. داوری سه مسیر</h2>',
        '<table><thead><tr><th>مسیر</th><th>چه می‌دهد</th><th>چه ندارد</th><th>هزینه</th>'
        '<th>داوری</th><th>آزمون</th></tr></thead><tbody>' + mrows + '</tbody></table>',
    ]
    if result.get("fixture"):
        body.insert(1, '<div class="note"><b>توجه:</b> این اجرا روی <b>دادهٔ ساختگی محلی</b> انجام شده است '
                       'تا شکل خروجی دیده شود؛ نتیجه‌اش دربارهٔ سرویس‌های واقعی چیزی نمی‌گوید.</div>')
    out.write_text(rk.page("امکان‌سنجی مسیرهای داده — پیش از خرید", "".join(body),
                           subtitle=f"نسخهٔ {VERSION} · {len(result['items'])} نشانی سنجیده شد"),
                   encoding="utf-8")
    return out


# ---------------------------------------------------------------- خط فرمان
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=f"امکان‌سنجی مسیرهای داده — نسخه {VERSION}")
    ap.add_argument("--all", action="store_true", help="سنجش همهٔ نقاط پایانی رایگان")
    ap.add_argument("--symbol", default="فولاد", help="نام نماد برای سنجش")
    ap.add_argument("--code", default="", help="کد نماد (insCode) اگر می‌دانید")
    ap.add_argument("--host", default="", help="میزبان جایگزین (پیش‌فرض: cdn.tsetmc.com)")
    ap.add_argument("--ws", default="", help="نشانی پوش لحظه‌ای برای سنجش، مثل wss://host/path")
    ap.add_argument("--ws-token", default="", help="توکن پوش لحظه‌ای (اگر دارید)")
    ap.add_argument("--fixture", action="store_true", help="اجرای آزمایشی روی سرور نمونهٔ محلی (دادهٔ ساختگی)")
    ap.add_argument("--sheet", action="store_true", help="نوشتن برگهٔ نیاز داده برای فروشنده")
    ap.add_argument("--timeout", type=float, default=12.0, help="مهلت هر درخواست (ثانیه)")
    ap.add_argument("--no-stability", action="store_true", help="سنجش دو فراخوانی را انجام نده")
    ap.add_argument("--json", action="store_true", help="خروجی ماشین‌خوان")
    ap.add_argument("--version", action="version", version=VERSION)
    args = ap.parse_args(argv)

    if args.sheet:
        out = DATA / "data-requirement-sheet.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(requirement_sheet(), encoding="utf-8")
        print("برگهٔ نیاز داده نوشته شد:", out)
        return 0

    httpd = None
    host = args.host
    fixture = bool(args.fixture)
    if fixture:
        httpd, host = start_fixture()
        # در حالت ماشین‌خوان، این پیام نباید خروجی JSON را آلوده کند
        print(f"سرور نمونهٔ محلی روی {host} بالا آمد (دادهٔ ساختگی).",
              file=sys.stderr if args.json else sys.stdout)

    result = probe_all(symbol=args.symbol, code=args.code, host=host, timeout=args.timeout,
                       with_stability=not args.no_stability)
    result["fixture"] = fixture
    ws = probe_ws(args.ws) if args.ws else None
    if ws and not ws.get("ok") and args.ws_token:
        ws["real_read"] = real_ws_read(args.ws, token=args.ws_token)
    report = build_report(result, build_matrix(), ws)
    if httpd:
        httpd.shutdown()

    if args.json:
        print(json.dumps({"result": result, "ws": ws, "matrix": build_matrix()}, ensure_ascii=False, indent=2))
        return 0
    print(f"سنجش مسیرهای داده — نماد {result['symbol']} · کد {result['code'] or '—'}")
    print("-" * 78)
    for item in result["items"]:
        mark = "✓" if item["ok"] else "✗"
        print(f"[{mark}] {item['label']}: {item['reason']} · {item.get('latency_ms', 0)} میلی‌ثانیه"
              + (f" · میدان‌های یافته: {item['count']}" if item["ok"] else ""))
    for s in result.get("stability", []):
        if s.get("checked"):
            print(f"    · دو فراخوانی {s['name']}: {s['verdict']} — {s['note']}")
    print("-" * 78)
    print(result["verdict"])
    if ws:
        print(f"پوش لحظه‌ای: {ws['verdict']} — {ws['note']}")
    print("گزارش:", report)
    return 0 if result["summary"]["ok"] >= 3 else 1


if __name__ == "__main__":
    raise SystemExit(main())
