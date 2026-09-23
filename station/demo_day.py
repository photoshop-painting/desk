#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""برگهٔ شاهد زنده — «این عدد را من تایپ نکردم؛ خودِ برنامه از سرویس خواند».

مسئله‌ای که حل می‌کند: سرمایه‌گذار (یا کارفرما) به عددهای یک اسلاید اعتماد نمی‌کند. اینجا
برای هر عددی که برنامه رویش تصمیم می‌گیرد، سه چیز چاپ می‌شود:

  ۱) نشانی‌ای که همین حالا خوانده شد، و پاسخ خام سرویس (چند بایت اول).
  ۲) اثر انگشت sha256 همان پاسخ خام؛ اگر کسی عدد را دست‌کاری کند، هش عوض می‌شود.
  ۳) ساعت خواندن (UTC) و مدت خواندن؛ یعنی «الان»، نه «چند هفته پیش».

بعد از آن، برنامه روی همان عددها یک تصمیم نمونه می‌گیرد و **حساب‌وکتابش را هم می‌نویسد**
تا با ماشین‌حساب گوشی هم بشود راستی‌آزمایی کرد.

هزینه: صفر. با «خوراک آزمایشی محلی» هم کار می‌کند (بدون اینترنت) و با سرویس خریدنی هم.
صداقت برچسب: اگر نشانی روی همین رایانه باشد، در برگه با حروف درشت نوشته می‌شود که داده
ساختگی است و شاهد فقط «زنده‌بودن مسیر فنی» را نشان می‌دهد، نه بازار واقعی.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import datafeed  # noqa: E402
import connections as conn  # noqa: E402
import investor_test as inv  # noqa: E402
import reportkit as rk  # noqa: E402

VERSION = "0.1.0"

DATA = BASE / "data"
EXPORT = BASE / "export"
BASE_SNAPSHOT = (BASE.parent / "desk" / "market-demo.json")
PAGE = DATA / "witness-live.html"
MD = DATA / "witness-live.md"
JSONF = DATA / "witness-live.json"

LOCAL_HOSTS = ("127.0.0.1", "localhost", "0.0.0.0", "::1")


def stamps() -> tuple[str, str]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return now.isoformat(), now.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def build_url(live_cfg: dict, symbol: str, key: str) -> str:
    """نشانی نهایی یک نماد را می‌سازد (همان کاری که مسیر زندهٔ برنامه می‌کند)."""
    url = str(live_cfg.get("url_template") or "").replace("{symbol}", urllib.parse.quote(symbol))
    if "{key}" in url:
        url = url.replace("{key}", urllib.parse.quote(key or ""))
    return url


def _blank(symbol: str, url: str, error: str) -> dict:
    return {"symbol": symbol, "url": url, "ok": False, "error": error, "sha256": "", "bytes": 0,
            "latency_ms": None, "price": None, "fetched_at": stamps()[0], "snippet": "", "source": ""}


def probe(profile: dict, symbols: list[str], *, timeout: float = 8.0, key: str = "") -> list[dict]:
    """قیمت هر نماد را زنده می‌خواند (بدون حافظهٔ نهان) و شاهد خامش را برمی‌گرداند."""
    cfg = conn.live_config(profile)
    if not key:
        key, _where = conn.resolve_key(profile)
    out: list[dict] = []
    for symbol in symbols:
        url = build_url(cfg, symbol, key)
        if not url:
            out.append(_blank(symbol, "", "قالب نشانی خالی است"))
            continue
        t0 = time.time()
        text, status = datafeed.fetch(url, timeout=timeout, retries=0,
                                      key_header=str(cfg.get("key_header") or ""), key=key,
                                      cache_name=None, use_cache=False, stale_ok=False)
        latency = int(round((time.time() - t0) * 1000))
        utc, _local = stamps()
        source = ("خوراک آزمایشی محلی (ساختگی)" if any(h in url for h in LOCAL_HOSTS)
                  else "دادهٔ زندهٔ وب‌سرویس")
        record = _blank(symbol, url, "")
        record.update({"fetched_at": utc, "latency_ms": latency, "source": source})
        if not text:
            record["error"] = status
            out.append(record)
            continue
        record["sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        record["bytes"] = len(text.encode("utf-8"))
        record["snippet"] = " ".join(text.split())[:400]
        value, why = datafeed.parse_quote_payload(text, str(cfg.get("json_path") or ""), symbol)
        if value is None:
            record["error"] = f"عدد قیمت خوانده نشد ({why})"
        else:
            record["ok"] = True
            record["price"] = float(value)
            record["status_text"] = status
        out.append(record)
    return out


def symbols_of(path: Path | str = BASE_SNAPSHOT) -> list[str]:
    """نمادهای پروندهٔ پایه — همان ردیف‌هایی که برنامه رویشان تصمیم می‌گیرد."""
    try:
        snap = datafeed.load_snapshot_file(path)
    except Exception:
        return []
    seen, out = set(), []
    for row in snap.rows:
        name = str(row.get("symbol") or "").strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def decide(probes: list[dict], *, path: Path | str = BASE_SNAPSHOT, rules: dict | None = None) -> dict:
    """عددهای زنده را روی ردیف‌های پروندهٔ پایه می‌نشاند و بهترین ردیف را کامل باز می‌کند.

    عمداً همان تابع‌های خودِ ایستگاه صدا زده می‌شوند (`datafeed.finish_live`، `investor_test.solve`،
    `investor_test.ladder_for`) تا عددی که در برگهٔ شاهد چاپ می‌شود، همان عددی باشد که برنامه
    رویش تصمیم می‌گیرد — نه حساب‌وکتاب دومِ جداگانه.
    """
    out: dict = {"ready": False, "reason": "", "chosen": None, "others": [],
                 "snapshot": {}, "live_inputs": [], "file_path": str(path)}
    try:
        snap = datafeed.load_snapshot_file(path)
    except Exception as e:  # پروندهٔ پایه نبود → باید صریح گفته شود، نه سکوت
        out["reason"] = f"پروندهٔ پایهٔ ردیف‌ها خوانده نشد: {type(e).__name__}"
        return out
    if not getattr(snap, "rows", None):
        out["reason"] = f"پروندهٔ پایهٔ ردیف‌ها خوانده نشد یا خالی است: {path}"
        return out
    prices = {p["symbol"]: p["price"] for p in probes if p.get("ok") and p.get("price") is not None}
    fails = len([p for p in probes if not p.get("ok")])
    sources = {p.get("source", "") for p in probes if p.get("ok")}
    if sources:
        snap.source_label = sorted(sources)[0]
    snap.mode = "live"
    snap = datafeed.finish_live(snap, prices, stale_count=0, fail_count=fails)
    out["snapshot"] = {"status": snap.status, "source_label": snap.source_label,
                       "messages": list(snap.messages), "rows": len(snap.rows),
                       "as_of": getattr(snap, "as_of", ""), "mode": snap.mode,
                       "freshness_seconds": snap.freshness_seconds,
                       "file": str(path), "file_date": str(getattr(snap, "as_of", "") or "")}
    out["live_inputs"] = [{"symbol": p["symbol"], "price": p["price"], "sha256": p["sha256"],
                           "latency_ms": p["latency_ms"]} for p in probes if p.get("ok")]
    out["live"] = bool(prices)
    if not prices:
        # بدون قیمت زنده، برگهٔ شاهد «شاهد» نیست؛ عددهای پروندهٔ پایه را به اسم تصمیم امروز نمی‌فروشیم.
        out["reason"] = ("هیچ قیمتی از سرویس نیامد؛ پس این اجرا «زنده» نیست و تصمیم نمونه ساخته "
                         "نشد. علت هر نماد در جدول آمده است.")
        return out
    rows = [r for r in snap.rows if r.get("kind")]
    if not rows:
        out["reason"] = "هیچ ردیفی با «راهبرد» در پروندهٔ پایه نبود؛ راهبردها را در جدول پر کنید."
        return out
    scored = []
    for row in rows:
        try:
            solved = inv.solve(row)
            ladder = inv.ladder_for(row)
        except Exception as e:
            scored.append({"symbol": str(row.get("symbol", "")), "kind": str(row.get("kind", "")),
                           "error": f"{type(e).__name__}: {e}"})
            continue
        scored.append({"symbol": str(row.get("symbol", "")), "kind": str(row.get("kind", "")),
                       "row": dict(row), "title": solved.get("title", ""), "answer": solved.get("answer"),
                       "answer_num": solved.get("answer_num"), "unit": solved.get("unit", ""),
                       "given": solved.get("given", []), "checks": solved.get("checks", []),
                       "steps": solved.get("steps", []), "extras": solved.get("extras"),
                       "formula": solved.get("formula", ""), "hurdle_pct": ladder.get("hurdle_pct"),
                       "margin_pp": ladder.get("margin_pp"), "fees_pct": ladder.get("fees_pct"),
                       "verdict": ladder.get("verdict", ""), "why": ladder.get("why", ""),
                       "survives": ladder.get("survives"), "ladder": ladder.get("ladder", [])})
    ranked = [s for s in scored if isinstance(s.get("answer_num"), (int, float))]
    if not ranked:
        out["reason"] = "هیچ ردیفی عدد قابل‌محاسبه نداد؛ اعداد پروندهٔ پایه را بازبینی کنید."
        out["others"] = scored
        return out
    ranked.sort(key=lambda s: -float(s["answer_num"]))
    live_rows = [s for s in ranked
                 if str(s["row"].get("symbol", "")) in prices
                 and any(s["row"].get(f"{f}_manual") is not None for f in ("spot", "stock_price"))]
    if live_rows:                     # ردیفی که واقعاً قیمت زنده گرفت، بر ردیف پرونده‌ای مقدم است
        pick_from = live_rows
        scope = "ردیف‌هایی که قیمت زنده گرفتند"
    else:
        pick_from = ranked
        scope = "همهٔ ردیف‌ها (هیچ ردیفی قیمت زنده نگرفت)"
    chosen = pick_from[0]
    chosen["provenance"] = provenance_of(chosen, prices, path)
    others = [s for s in ranked if s is not chosen]
    for other in others:
        other["provenance"] = provenance_of(other, prices, path)
    out.update({"ready": True, "chosen": chosen, "others": others, "reason": "",
                "rank_scope": scope, "live_symbols": sorted(prices)})
    return out


FIELD_LABELS = (("spot", "قیمت نقدی"), ("stock_price", "قیمت سهم"), ("future", "قیمت آتی"),
                ("strike", "قیمت اعمال"), ("strike_low", "اعمال پایین"), ("strike_high", "اعمال بالا"),
                ("premium", "پرمیوم"), ("put_price", "پرمیوم پوت"), ("put", "پرمیوم پوت"),
                ("call", "پرمیوم کال"), ("call_low", "کال پایین"), ("call_high", "کال بالا"),
                ("put_low", "پوت پایین"), ("put_high", "پوت بالا"),
                ("days", "روز تا سررسید"), ("margin_per_contract", "وجه تضمین هر قرارداد"))


def provenance_of(chosen: dict, prices: dict, path: Path | str) -> list[dict]:
    """هر عدد ورودی از کجا آمد: سرویس زنده، پروندهٔ پایه، یا قاعدهٔ برنامه؟ (شفافیت کامل)"""
    row = chosen.get("row") or {}
    out: list[dict] = []
    for field, label in FIELD_LABELS:
        if field not in row or not isinstance(row.get(field), (int, float)):
            continue
        live = row.get(f"{field}_manual") is not None
        out.append({"label": label, "field": field, "value": row[field],
                    "source": "زنده از سرویس" if live else "از پروندهٔ پایه",
                    "detail": (f"قیمت پیش از به‌روزشدن در پرونده: {row[f'{field}_manual']:,.2f}"
                               if live else Path(path).name)})
    if isinstance(row.get("hurdle"), (int, float)):
        out.append({"label": "نرخ سد", "field": "hurdle", "value": row["hurdle"],
                    "source": "قاعدهٔ برنامه", "detail": "در گام ۱ قابل تغییر است"})
    return out


def mixed_sources_note(chosen: dict, live_symbols=None) -> str:
    """شفاف‌سازی صریح: چه چیزی زنده آمد، چه چیزی از پرونده آمد، و کدام عدد در تصمیم به‌کار رفت."""
    prov = chosen.get("provenance") or []
    live = [x for x in prov if x["source"] == "زنده از سرویس"]
    filed = [x for x in prov if x["source"] == "از پروندهٔ پایه"]
    read_live = bool(live_symbols) if live_symbols is not None else bool(live)
    if not read_live:
        return "هیچ قیمتی از سرویس نیامد؛ پس این اجرا «زنده» نیست و به عددهایش استناد نکنید."
    if not live:
        return ("قیمت‌های زنده خوانده شد، ولی ردیف برگزیده («" + str(chosen.get("symbol", "")) +
                "» · " + str(chosen.get("kind", "")) + ") هیچ قیمت زنده‌ای را در محاسبه به کار نمی‌برد؛ "
                "همهٔ عددهایش از پروندهٔ پایهٔ شماست. برای زنده‌شدن همین ردیف، قیمت‌های همان نماد "
                "هم باید از سرویس یا تابلوی کارگزار بیایند — وگرنه این عدد «فرصت امروز» نیست.")
    if filed:
        return ("توجه: بخشی از عددهای این ردیف از پروندهٔ پایهٔ خودتان آمده است ("
                + "، ".join(x["label"] for x in filed)
                + "). یعنی این عدد «آزمون زندهٔ قیمت پایه» است، نه یک فرصت معاملاتی امروز. "
                  "برای فرصت واقعی، قیمت هر دو سر معامله باید امروز از سرویس یا از تابلوی "
                  "کارگزاری بیاید.")
    return "همهٔ عددهای این ردیف همین حالا از سرویس خوانده شد و هیچ عددی از پرونده به کار نرفت."


def limits_of(doc: dict) -> list[str]:
    out = ["سودآوری را اثبات نمی‌کند؛ فقط نشان می‌دهد عددهای همین تصمیم از سرویس خوانده شده‌اند.",
           "قیمت لحظهٔ خواندن است؛ قیمت اجرای سفارش شما در کارگزار فری دارد و با آن فرق می‌کند.",
           "وجه تضمین را کارگزاری تعیین می‌کند؛ عدد این برگه از کارگزاری نیست.",
           "مشخصات قرارداد (قیمت اعمال، سررسید) از پروندهٔ پایهٔ خودتان خوانده شده، نه از سرویس."]
    if any(p.get("source", "").startswith("خوراک آزمایشی") for p in doc["probes"]):
        out.insert(0, "این اجرا روی «خوراک آزمایشی محلی» بوده؛ یعنی داده ساختگی است و برگه فقط "
                      "زنده‌بودن مسیر فنی (خواندن، هش، تصمیم) را نشان می‌دهد، نه بازار واقعی.")
    if any(not p.get("ok") for p in doc["probes"]):
        out.insert(0, "بعضی نمادها خوانده نشد؛ علت هرکدام در جدول آمده است.")
    if any(c.get("error") for c in [doc["decision"].get("chosen") or {}]):
        out.insert(0, "برای ردیف انتخابی، محاسبه کامل نشد؛ متن خطا در برگه آمده است.")
    return out


def build(*, symbols: list[str] | None = None, timeout: float = 8.0, profile: dict | None = None,
          key: str = "", path: Path | str = BASE_SNAPSHOT, write: bool = True,
          page: Path | str | None = None, md: Path | str | None = None,
          json_path: Path | str | None = None) -> dict:
    """برگهٔ شاهد را می‌سازد (و ذخیره می‌کند)."""
    active = conn.active_or_none()
    prof = profile or (active or {}).get("profile") or {}
    if not prof:
        prof = {"name": "custom", "label": "اتصال دلخواه (چیزی انتخاب نشده)", "cost": "",
                "url_template": "", "json_path": ""}
    key_where = "کادر همین لحظه" if key else (active or {}).get("key_where", "بدون کلید")
    names = [s for s in (symbols or []) if s] or symbols_of(path)
    utc, local = stamps()
    probes = probe(prof, names, timeout=timeout, key=key)
    doc = {
        "version": VERSION,
        "built_at_utc": utc,
        "built_at_local": local,
        "connection": {"name": prof.get("name", ""), "label": prof.get("label", ""),
                       "cost": prof.get("cost", ""), "key_where": key_where,
                       "url_template": prof.get("url_template", ""),
                       "json_path": prof.get("json_path", "")},
        "probes": probes,
    }
    doc["decision"] = decide(probes, path=path)
    doc["decision"]["mixed_note"] = (
        mixed_sources_note(doc["decision"]["chosen"],
                           doc["decision"].get("live_symbols") or [])
        if doc["decision"].get("chosen") else "")
    doc["limits"] = limits_of(doc)
    core = json.dumps({"probes": probes, "decision": doc["decision"]}, sort_keys=True,
                      ensure_ascii=False)
    doc["page_hash"] = hashlib.sha256(core.encode("utf-8")).hexdigest()[:16]
    doc["text"] = text_of(doc)
    if write:
        for target, content in ((page or PAGE, _page(doc)), (md or MD, doc["text"]),
                                (json_path or JSONF, json.dumps(doc, ensure_ascii=False, indent=1))):
            pth = Path(target)
            pth.parent.mkdir(parents=True, exist_ok=True)
            pth.write_text(content, encoding="utf-8")
        doc.update({"page": str(page or PAGE), "md": str(md or MD), "json": str(json_path or JSONF)})
    return doc


def text_of(doc: dict) -> str:
    d = doc["decision"]
    L = [f"# برگهٔ شاهد زندهٔ داده — نسخهٔ {VERSION}", "",
         f"ساعت خواندن: {doc['built_at_local']} (UTC: {doc['built_at_utc']})",
         f"اتصال فعال: {doc['connection']['label']} ({doc['connection']['cost']}) — کلید: {doc['connection']['key_where']}",
         f"قالب نشانی: `{doc['connection']['url_template'] or '—'}`", ""]
    L += ["## ۱. عددهایی که همین حالا خوانده شد", "",
          "| نماد | قیمت | منبع | بایت | اثر انگشت پاسخ خام | تأخیر | وضعیت |",
          "| --- | --- | --- | --- | --- | --- | --- |"]
    for p in doc["probes"]:
        price = f"{p['price']:,.4f}" if p.get("price") is not None else "—"
        state = "خوانده شد ✅" if p.get("ok") else f"نشد ❌ {p.get('error', '')}"
        L.append(f"| {p['symbol']} | {price} | {p.get('source', '')} | {p.get('bytes', 0)} | "
                 f"`{p.get('sha256', '')[:16]}` | {p.get('latency_ms', '—')} ms | {state} |")
    L += ["", "نشانی‌های خوانده‌شده:"] + [f"- {p['symbol']}: `{p['url']}`" for p in doc["probes"]]
    L += ["", "## ۲. تصمیمی که از همین عددها درآمد", ""]
    if d.get("ready"):
        s = d["chosen"]
        L += [f"- عکس زندهٔ بازار: {d['snapshot']['status']} · منبع: {d['snapshot']['source_label']}",
              f"- ردیف انتخابی (بالاترین بازده): **{s['symbol']}** · {s['kind']} — {s['title']}",
              f"- قیمت‌هایی که زنده خوانده شد: {'، '.join(d.get('live_symbols') or []) or '—'}",
              f"- دامنهٔ رتبه‌بندی: {d.get('rank_scope', '—')}"]
        if s.get("given"):
            L += ["- عددهای ورودی: " + " · ".join(f"{g[0]} {g[1]}" for g in s["given"])]
        for g in d["live_inputs"]:
            L += [f"  - {g['symbol']}: {g['price']:,.4f} (هش `{g['sha256'][:16]}` · {g['latency_ms']} ms)"]
        L += ["", f"**پاسخ: {s.get('answer')} {s.get('unit', '')}**", ""]
        if s.get("checks"):
            L += ["سنجش دو-روشی (هر سطر باید «می‌خواند» باشد):"]
            L += [f"- {c.get('note', '')}: `{c.get('value')}` — "
                  f"{'می‌خواند ✅' if c.get('agree') else 'نمی‌خواند ❌'}" for c in s["checks"]]
        if s.get("steps"):
            L += ["", "مسیر محاسبه (قابل بازتولید با ماشین‌حساب):"]
            L += [f"- {st}" for st in s["steps"]]
        if d.get("mixed_note"):
            L += ["", "> **" + d["mixed_note"] + "**", ""]
        if s.get("provenance"):
            L += ["", "هر عدد از کجا آمد:", "",
                  "| عدد | مقدار | از کجا | توضیح |", "| --- | --- | --- | --- |"]
            for pr in s["provenance"]:
                val = f"{pr['value']:,.4f}".rstrip("0").rstrip(".") if isinstance(pr["value"], float) \
                    else f"{pr['value']:,}"
                L.append(f"| {pr['label']} | {val} | {pr['source']} | {pr['detail']} |")
        if s.get("ladder"):
            L += ["", "پلهٔ خروج — «کِی بفروشم، کِی می‌افتد»:", "",
                  "| حد | کِی | روی چه قیمتی | کار |", "| --- | --- | --- | --- |"]
            for item in s["ladder"]:
                price = item.get("price")
                price_txt = f"{price:,.3f}" if isinstance(price, (int, float)) else str(price)
                L.append(f"| {item.get('label', '')} | {item.get('when', '')} | {price_txt} | "
                         f"{item.get('action', '')} |")
        for key, label in (("verdict", "داوری"), ("why", "چرا"), ("fees_pct", "کارمزد لحاظ‌شده (٪)"),
                           ("hurdle_pct", "نرخ سد (٪)"), ("margin_pp", "حاشیه روی سد (واحد درصد)")):
            if s.get(key) not in (None, ""):
                L.append(f"- {label}: {s[key]}")
        if d.get("others"):
            L += ["", "سایر ردیف‌ها:", "",
                  "| نماد | راهبرد | پاسخ |", "| --- | --- | --- |"]
            for o in d["others"]:
                L.append(f"| {o.get('symbol','')} | {o.get('kind','')} | "
                         f"{o.get('answer','—')} {o.get('unit','')} |")
    else:
        L.append(f"- تصمیم نمونه ساخته نشد: {d.get('reason', '')}")
    L += ["", f"اثر انگشت کل برگه: `{doc['page_hash']}`", "",
          "## ۳. راستی‌آزمایی مستقل", "",
          "۱) همان نشانی را در مرورگر باز کنید و عدد را ببینید. ۲) پاسخ خام بالا را با ماشین‌حساب "
          "بشمارید. ۳) اثر انگشت این برگه را با `data/witness-live.json` بسنجید.", "",
          "## ۴. این برگه چه چیزی را اثبات نمی‌کند", ""]
    L += [f"- {x}" for x in doc["limits"]]
    L += ["", "---", "",
          "✍️ تهیه‌کنندهٔ جزوات: **Masoud Mojarabian** · 📱 +989126630554 · "
          "✈️ Telegram: [Mojarabian](https://t.me/Mojarabian) · "
          "📸 Instagram: [Mojarabian.Art](https://instagram.com/Mojarabian.Art)"]
    return "\n".join(L)


def _page(doc: dict) -> str:
    c, d = doc["connection"], doc["decision"]
    mock = any(p.get("source", "").startswith("خوراک آزمایشی") for p in doc["probes"])
    head = [f'<div class="honest"><b>این برگه با همین ساعت ساخته شده.</b> برای هر عدد، نشانی و '
            f'اثر انگشت پاسخ خام سرویس چاپ شده تا خودتان راستی‌آزمایی کنید. '
            f'{rk.esc(doc["built_at_local"])} (UTC: <code>{rk.esc(doc["built_at_utc"])}</code>)</div>']
    if mock:
        head.append('<div class="warnbox"><b>توجه: این اجرا روی خوراک آزمایشی محلی است؛ داده ساختگی '
                    'است.</b> برگه فقط نشان می‌دهد که مسیر «خواندن از سرویس ← هش ← تصمیم» زنده کار '
                    'می‌کند. برای عدد بازار واقعی، پروفایل سرویس واقعی را انتخاب کنید.</div>')
    head.append(f'<p class="sub">اتصال فعال: <b>{rk.esc(c["label"])}</b> · هزینه: {rk.esc(c["cost"])} · '
                f'کلید: {rk.esc(c["key_where"])} · مسیر عدد در پاسخ: <code>{rk.esc(c["json_path"] or "—")}</code></p>')
    rows = []
    for p in doc["probes"]:
        if p.get("ok"):
            price, state = rk.num(p["price"], 4), '<span class="ok">خوانده شد ✅</span>'
        else:
            price = "—"
            state = ('<span class="bad">نشد ❌</span><br>'
                     f'<span class="hint">{rk.esc(p.get("error", ""))}</span>')
        rows.append(f'<tr><td>{rk.esc(p["symbol"])}</td><td class="num">{price}</td>'
                    f'<td>{rk.esc(p.get("source", ""))}</td><td class="num">{p.get("bytes", 0)}</td>'
                    f'<td class="num"><code>{rk.esc(p.get("sha256", "")[:16])}</code></td>'
                    f'<td class="num">{p.get("latency_ms", "—")}</td><td>{state}</td></tr>')
    table = ('<table><thead><tr><th>نماد</th><th class="num">قیمت</th><th>منبع</th>'
             '<th class="num">بایت</th><th class="num">اثر انگشت پاسخ</th>'
             '<th class="num">تأخیر (ms)</th><th>وضعیت</th></tr></thead><tbody>'
             + "".join(rows) + "</tbody></table>")
    raws = "".join(f'<p class="sub"><b>{rk.esc(p["symbol"])}</b> — <code>{rk.esc(p["url"])}</code></p>'
                   f'<pre>{rk.esc(p["snippet"])}</pre>' for p in doc["probes"] if p.get("snippet"))
    if d.get("ready"):
        s = d["chosen"]
        block = ['<table><tbody>',
                 f'<tr><td>عکس زندهٔ بازار</td><td>{rk.esc(d["snapshot"]["status"])} · '
                 f'{rk.esc(d["snapshot"]["source_label"])}</td></tr>',
                 f'<tr><td>ردیف انتخابی (بالاترین بازده)</td><td><b>{rk.esc(s["symbol"])}</b> · '
                 f'<code>{rk.esc(s["kind"])}</code> — {rk.esc(s.get("title", ""))}</td></tr>']
        if s.get("given"):
            block.append('<tr><td>عددهای ورودی</td><td class="num">'
                         + " · ".join(f'{rk.esc(g[0])} {rk.esc(g[1])}' for g in s["given"])
                         + '</td></tr>')
        for g in d["live_inputs"]:
            block.append(f'<tr><td>قیمت زندهٔ {rk.esc(g["symbol"])}</td>'
                         f'<td class="num">{rk.num(g["price"], 4)} '
                         f'<span class="hint">(هش <code>{rk.esc(g["sha256"][:16])}</code> · '
                         f'{g["latency_ms"]} ms)</span></td></tr>')
        block.append(f'<tr><td><b>پاسخ</b></td><td class="num"><b>{rk.esc(s.get("answer"))}</b> '
                     f'{rk.esc(s.get("unit", ""))}</td></tr>')
        for key, label in (("verdict", "داوری"), ("fees_pct", "کارمزد لحاظ‌شده (٪)"),
                           ("hurdle_pct", "نرخ سد (٪)"), ("margin_pp", "حاشیه روی سد (واحد درصد)")):
            if s.get(key) not in (None, ""):
                val = rk.num(s[key], 3) if isinstance(s[key], (int, float)) else rk.esc(s[key])
                block.append(f'<tr><td>{rk.esc(label)}</td><td class="num">{val}</td></tr>')
        block.append('</tbody></table>')
        checks = ""
        if s.get("checks"):
            checks = ("<h3>سنجش دو-روشی</h3><ul>" + "".join(
                f'<li>{rk.esc(c.get("note", ""))}: <code>{rk.esc(c.get("value"))}</code> — '
                f'{"می‌خواند ✅" if c.get("agree") else "نمی‌خواند ❌"}</li>' for c in s["checks"])
                + "</ul>")
        steps = ""
        if s.get("steps"):
            steps = ("<h3>مسیر محاسبه (با ماشین‌حساب هم می‌شود بازتولید کرد)</h3><ol>"
                     + "".join(f"<li>{rk.esc(x)}</li>" for x in s["steps"]) + "</ol>")
        prov = ""
        if s.get("provenance"):
            prows = []
            for pr in s["provenance"]:
                val = (rk.num(pr["value"], 4) if isinstance(pr["value"], float)
                       else f"{pr['value']:,}")
                cls = "ok" if pr["source"] == "زنده از سرویس" else "hint"
                prows.append(f'<tr><td>{rk.esc(pr["label"])}</td><td class="num">{val}</td>'
                             f'<td><span class="{cls}">{rk.esc(pr["source"])}</span></td>'
                             f'<td><span class="hint">{rk.esc(pr["detail"])}</span></td></tr>')
            prov = ('<h3>هر عدد از کجا آمد</h3><table><thead><tr><th>عدد</th><th class="num">مقدار</th>'
                    '<th>از کجا</th><th>توضیح</th></tr></thead><tbody>' + "".join(prows) + "</tbody></table>")
        ladder = ""
        if s.get("ladder"):
            lrows = []
            for item in s["ladder"]:
                price = item.get("price")
                price_txt = (f"{price:,.3f}" if isinstance(price, (int, float)) else str(price))
                lrows.append(f'<tr><td>{rk.esc(item.get("label", ""))}</td>'
                             f'<td>{rk.esc(item.get("when", ""))}</td>'
                             f'<td class="num">{rk.esc(price_txt)}</td>'
                             f'<td>{rk.esc(item.get("action", ""))}</td></tr>')
            ladder = ('<h3>پلهٔ خروج — «کِی بفروشم، کِی می‌افتد»</h3><table><thead><tr><th>حد</th>'
                      '<th>کِی</th><th class="num">روی چه قیمتی</th><th>کار</th></tr></thead><tbody>'
                      + "".join(lrows) + "</tbody></table>")
        others = ""
        if d.get("others"):
            orows = "".join(f'<tr><td>{rk.esc(o.get("symbol", ""))}</td>'
                            f'<td>{rk.esc(o.get("kind", ""))}</td>'
                            f'<td class="num">{rk.esc(str(o.get("answer", "—")))} '
                            f'{rk.esc(o.get("unit", ""))}</td></tr>' for o in d["others"])
            others = ('<h3>سایر ردیف‌ها</h3><table><thead><tr><th>نماد</th><th>راهبرد</th>'
                      '<th class="num">پاسخ</th></tr></thead><tbody>' + orows + "</tbody></table>")
        if d.get("mixed_note"):
            block.insert(0, f'<div class="warnbox"><b>{rk.esc(d["mixed_note"])}</b></div>')
        dec_body = "".join(block) + prov + checks + steps + ladder + others
        if s.get("why"):
            dec_body += f'<p class="note">{rk.esc(s["why"])}</p>'
    else:
        dec_body = f'<p class="warn">{rk.esc(d.get("reason", ""))}</p>'

    limits = "".join(f"<li>{rk.esc(x)}</li>" for x in doc["limits"])
    body = "".join(head + [
        "<h2>۱. عددهایی که همین حالا خوانده شد</h2>", table,
        "<h3>پاسخ خام سرویس (برای راستی‌آزمایی)</h3>",
        raws or '<p class="hint">پاسخی ثبت نشد.</p>',
        "<h2>۲. تصمیمی که از همین عددها درآمد</h2>", dec_body,
        "<h2>۳. راستی‌آزمایی مستقل</h2>",
        '<p class="note">سه راه برای اینکه به حرف برنامه اعتماد نکنید و خودتان بسنجید: '
        '۱) همان نشانی را در مرورگر باز کنید و عدد را ببینید. ۲) پاسخ خام بالا را با ماشین‌حساب '
        'بشمارید. ۳) اثر انگشت این برگه را با پروندهٔ <code>data/witness-live.json</code> بسنجید.</p>',
        f'<p class="sub">اثر انگشت برگه: <code>{rk.esc(doc["page_hash"])}</code></p>',
        "<h2>۴. این برگه چه چیزی را اثبات نمی‌کند</h2>", f"<ul>{limits}</ul>",
        '<p class="sub">نسخهٔ ' + VERSION + ' · ✍️ تهیه‌کنندهٔ جزوات: <b>Masoud Mojarabian</b> · '
        '📱 +989126630554 · ✈️ <a href="https://t.me/Mojarabian">Telegram: Mojarabian</a> · '
        '📸 <a href="https://instagram.com/Mojarabian.Art">Instagram: Mojarabian.Art</a></p>',
    ])
    ok = sum(1 for p in doc["probes"] if p.get("ok"))
    return rk.page("برگهٔ شاهد زندهٔ داده", body,
                   subtitle=f"خوانده‌شده از سرویس در {doc['built_at_local']} · "
                            f"{ok} از {len(doc['probes'])} نماد")


def summary_line(doc: dict) -> str:
    ok = [p for p in doc["probes"] if p.get("ok")]
    d = doc["decision"]
    line = f"{len(ok)} از {len(doc['probes'])} قیمت زنده خوانده شد"
    if d.get("ready"):
        s = d["chosen"]
        line += f" · ردیف برگزیده {s.get('symbol', '')} ({s.get('kind', '')})"
        if s.get("answer") is not None:
            line += f": {s.get('answer')} {s.get('unit', '')}"
        if s.get("verdict"):
            line += f" · {s['verdict'][:60]}"
    else:
        line += f" · تصمیم نمونه ساخته نشد: {d.get('reason', '')}"
    return line


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="برگهٔ شاهد زندهٔ داده (خواندن + هش + تصمیم نمونه)")
    ap.add_argument("--symbols", default="", help="نمادها با کاما (پیش‌فرض: نمادهای پروندهٔ پایه)")
    ap.add_argument("--file", default=str(BASE_SNAPSHOT), help="پروندهٔ پایهٔ ردیف‌ها")
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--out", default="", help="پوشهٔ خروجی (پیش‌فرض: data/)")
    a = ap.parse_args(argv)
    symbols = [s.strip() for s in a.symbols.split(",") if s.strip()]
    out = Path(a.out) if a.out else None
    doc = build(symbols=symbols, timeout=a.timeout, path=a.file,
                page=(out / "witness-live.html") if out else None,
                md=(out / "witness-live.md") if out else None,
                json_path=(out / "witness-live.json") if out else None)
    if a.json:
        print(json.dumps(doc, ensure_ascii=False, indent=1))
        return 0
    if not a.quiet:
        print(summary_line(doc))
        for p in doc["probes"]:
            if p.get("ok"):
                print(f"  · {p['symbol']}: {p['price']:,.4f}  (هش {p['sha256'][:12]} · "
                      f"{p['latency_ms']} ms · {p['source']})")
            else:
                print(f"  ✗ {p['symbol']}: {p.get('error', '')}")
        print(f"  برگه: {doc.get('page')}")
        print(f"  نسخهٔ متنی: {doc.get('md')}")
        print(f"  اثر انگشت برگه: {doc['page_hash']}")
    return 0 if any(p.get("ok") for p in doc["probes"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
