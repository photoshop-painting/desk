#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""کارساز محلی ایستگاه — رابط گرافیکی مرورگری (بهترین نمایش فارسی روی هر سیستم).

اجرا:  python web_server.py            (پیش‌فرض روی درگاه ۸۷۶۵)
       python web_server.py --port 9000 --host 0.0.0.0
       python web_server.py --no-browser  (باز کردن خودکار مرورگر را خاموش می‌کند)

چرا مرورگر؟ خط و نشان فارسی در tb/tk روی لینوکس شکسته و برعکس رندر می‌شود؛
مرورگر روی همهٔ سیستم‌ها فارسی را درست و راست‌به‌چپ نشان می‌دهد.
این کارساز فقط روی همین رایانه سرو می‌کند و هیچ داده‌ای جایی نمی‌فرستد.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import threading
import traceback
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote

VERSION = "0.1.0"
BASE = Path(__file__).resolve().parent
GUI = BASE          # پوشهٔ خودِ ایستگاه (شامل station.py، web/، data/، demo/)
DESK_DIR = (GUI.parent / "desk").resolve()
KODAL_DIR = (GUI.parent / "kodal-alert").resolve()
DATA = GUI / "data"
WEB = GUI / "web"
EXPORT = GUI / "export"

for p in (str(GUI), str(DESK_DIR), str(KODAL_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ladder as laddermod  # noqa: E402
import datafeed  # noqa: E402
import backtest as bt  # noqa: E402
import station as st  # noqa: E402
import connections as conn  # noqa: E402
import live_trial as trial  # noqa: E402
import mock_feed  # noqa: E402
import daily_trial as dailytrial  # noqa: E402
import autoconnect as autoconn  # noqa: E402
import selftest as selfcheck  # noqa: E402
import dossier as dossier_mod  # noqa: E402
import data_sources as sourcesmod  # noqa: E402
import investor_test as invtest  # noqa: E402
import signal_judge as judger  # noqa: E402
import license as licmod  # noqa: A004
import diagnose as diagmod  # noqa: E402
import audit  # noqa: E402
import snapshot_import as snapimp  # noqa: E402
import adminauth as admauth  # noqa: E402
import usage_meter as usagemod  # noqa: E402
import offer as offermod  # noqa: E402
import outreach as outreachmod  # noqa: E402
import prospects as prospectsmod  # noqa: E402
import onboarding as onbmod  # noqa: E402
import sales_ritual as ritualmod  # noqa: E402
import review_meeting as reviewmod  # noqa: E402
import gate as gatemod  # noqa: E402
import strategy_audit as stratmod  # noqa: E402
import edge_stress as stressmod  # noqa: E402
import bankroll as bankmod  # noqa: E402
import demo_day as demoday  # noqa: E402

import desk as deskmod  # noqa: E402
import kodal_alert as kodal  # noqa: E402

STATE: dict = {
    "mode": "sim",
    "file_path": str(DESK_DIR / "market-demo.json"),
    "live_cfg": dict(datafeed.DEFAULT_LIVE_CONFIG),
    "key": "",
    "use_kodal": True,
    "kodal_db": str(KODAL_DIR / "data" / "demo.sqlite3"),
    "rules": {
        "capital": 20_000_000_000, "hurdle": 0.39,
        "min_edge_arbitrage_pct": 3.0, "min_edge_leveraged_pct": 5.0,
        "max_margin_pct": 0.20, "max_position_pct": 0.35, "max_positions": 3,
        "min_liquidity_contracts_per_day": 20, "max_spread_pct": 0.03,
        "max_plausible_arb_pct": 250.0, "max_plausible_lev_pct": 400.0,
    },
    "snapshot": None,
    "backtest_result": None,
    "bundle_dir": None,
    "connection": {"name": "", "label": "", "key_where": "بدون کلید", "is_mock": False},
    "trial_db": str(trial.DEFAULT_DB),
    "last_sigs": [],
    "trial_last_mark": [],
}

# ---------------------------------------------------------------- دفتر اتصال و دفتر آزمون
def apply_saved_connection() -> dict:
    """پروفایل فعالِ ذخیره‌شده را روی وضعیت برنامه می‌نشاند (هر بار که برنامه بالا می‌آید)."""
    active = conn.active_or_none()
    if not active:
        return STATE["connection"]
    prof = active["profile"]
    STATE["live_cfg"] = active["live_cfg"]
    if active["key"]:
        STATE["key"] = active["key"]
    STATE["mode"] = "live"
    STATE["connection"] = {"name": prof["name"], "label": prof["label"],
                           "key_where": active["key_where"], "is_mock": active["is_mock"]}
    return STATE["connection"]


def connection_payload() -> dict:
    store = conn.load_store()
    keys = {p["name"]: conn.key_status(p["name"]) for p in store.get("profiles", [])}
    return {"profiles": store.get("profiles", []), "selected": store.get("selected", ""),
            "active": STATE["connection"], "store_file": str(conn.PROFILES_FILE),
            "keys_file": str(conn.KEYS_FILE), "keys_stored": bool(conn.load_keys()),
            "key_status": keys}


def peek_payload(body: dict) -> dict:
    """پاسخ خام سرویس را می‌خواند و مسیرهای عددی‌اش را نشان می‌دهد (برای پیدا کردن مسیر JSON)."""
    url = str(body.get("url") or "").strip()
    if not url:
        return {"ok": False, "error": "نشانی خالی است."}
    key = str(body.get("key") or "")
    if "{key}" in url and not key:
        return {"ok": False, "error": "این نشانی {key} دارد ولی کلید خالی است."}
    url = url.replace("{key}", urlparse_quote(key))
    text, status = datafeed.fetch(url, timeout=float(body.get("timeout_seconds", 12)), retries=1,
                                  key_header=str(body.get("key_header") or ""), key=key,
                                  cache_name="peek.json", cache_seconds=0, stale_ok=False)
    if not text:
        return {"ok": False, "error": f"پاسخی نیامد ({status}). نشانی و اینترنت را بررسی کنید.", "status": status}
    try:
        payload = json.loads(text)
    except Exception:
        return {"ok": False, "status": status, "error": "پاسخ JSON نبود (شاید صفحهٔ HTML است).",
                "preview": text[:600]}
    paths = datafeed.numeric_paths(payload)
    out = {"ok": True, "status": status, "bytes": len(text),
           "preview": text[:800], "paths": [{"path": p, "value": v} for p, v in paths],
           "count": len(paths)}
    # اگر کاربر مسیری را که در تنظیمات دارد هم بفرستد، صریح می‌گوییم «همین مسیر عدد دارد یا نه».
    wanted = str(body.get("json_path") or "").strip()
    if wanted:
        value = datafeed.dig(payload, wanted)
        out["json_path"] = wanted
        out["path_ok"] = value is not None
        out["path_value"] = value
        out["path_hint"] = (f"مسیر «{wanted}» در پاسخ هست و مقدارش {value} است؛ همین را در "
                           f"تنظیمات بگذارید." if value is not None else
                           f"مسیر «{wanted}» در پاسخ نبود. از فهرست بالا یکی از مسیرهای عددی را "
                           f"بردارید و در تنظیمات بگذارید.")
    return out


def urlparse_quote(value: str) -> str:
    from urllib.parse import quote
    return quote(str(value))


def build_now_map(sigs) -> dict:
    """از سیگنال‌های تازه، حاشیهٔ امروز هر نماد را درمی‌آورد."""
    cfg = STATE["rules"]
    out: dict = {}
    for s in sigs or []:
        kind = getattr(s, "kind", "")
        floor = (cfg["min_edge_arbitrage_pct"] if kind in ("basis", "arbitrage")
                 else cfg["min_edge_leveraged_pct"])
        detail = getattr(s, "detail", {}) or {}
        out[str(getattr(s, "symbol", ""))] = {
            "expected_now": getattr(s, "annualized_pct", None),
            "floor": floor,
            "spot_now": detail.get("spot") or detail.get("stock_price"),
            "future_now": detail.get("future"),
        }
    return out


def trial_payload() -> dict:
    t = trial.Trial(STATE["trial_db"])
    marks = t.latest_marks()
    entries = []
    for e in t.all(limit=200):
        m = marks.get(e["id"], {})
        entries.append({"id": e["id"], "ts": e["ts"], "symbol": e["symbol"], "kind": e["kind"],
                        "decision": e["decision"], "expected": e["expected"],
                        "expected_now": m.get("expected_now"), "delta_pp": m.get("delta_pp"),
                        "status_now": m.get("status", "بازسنجی‌نشده"), "marked_at": m.get("ts"),
                        "note": e["note"], "source_label": e["source_label"] or "",
                        "hash": e["hash"][:16] + "…"})
    score = dailytrial.scorecard(t, log_records=dailytrial.read_log())
    runs = dailytrial.read_log()[-8:]
    return {"summary": t.summary(), "entries": entries, "db": str(t.path),
            "report_ready": (GUI / "data" / "trial-report.html").exists(),
            "scorecard": score, "runs": runs}


# ------------------------------------------------------------------ پنل مدیریت

# این سه دسته از برنامه به پنل مدیریت رفته‌اند و بدون ورود، پاسخ نمی‌دهند.
ADMIN_ENDPOINTS = ("/api/health", "/api/license", "/api/diagnose", "/api/usage", "/api/state/info")
ADMIN_MAP = {
    "/api/admin/health": "/api/health",
    "/api/admin/license": "/api/license",
    "/api/admin/diagnose": "/api/diagnose",
    "/api/admin/usage": "/api/usage",
    "/api/admin/state": "/api/state/info",
    "/api/admin/backup": "/api/state/backup",
}
ADMIN_FILE_KEYS = ("diagnostic", "usage", "usage-md", "grant-doc",
                   "license-doc", "license-doc-md")



def state_keeper():
    """نگهبان وضعیت ابری را می‌آورد — فقط در نسخهٔ روی Hugging Face این پرونده وجود دارد.

    چرا این‌جا و با این احتیاط: روی رایانهٔ خودِ کاربر (`kit`/`backpack`) پشتیبان‌گیری محلی
    سرِ جای خود است و این پرونده نیست؛ پس نبودنش خطا نیست و پنل باید صادقانه «خاموش» بگوید.
    """
    for base in (Path(__file__).resolve().parent.parent, Path(__file__).resolve().parent):
        if not (base / "space_state.py").exists():
            continue
        if str(base) not in sys.path:
            sys.path.insert(0, str(base))
        try:
            import importlib
            return importlib.import_module("space_state")
        except Exception as e:                                # noqa: BLE001
            log(f"نگهبان وضعیت بار نشد: {type(e).__name__}: {e}")
            return None
    return None


OFFLINE_STATE = {"ok": True, "online": False, "files": 0, "interval_seconds": 0, "last": {}, "restored": {},
                 "note": "این نسخه روی میزبان ابری نیست؛ پشتیبان‌گیری محلی سرِ جای خود است."}


def doc_path(name: str) -> Path:
    """سندها را در چند جای ممکن می‌جوید تا بستهٔ کپی‌شده روی هر رایانه‌ای کار کند.

    ترتیب: پوشهٔ «money» (کنار desk و gui) ← زیرپوشهٔ «docs» همان پا (بستهٔ تحویل شرکت)
    ← پوشهٔ «docs» داخل خودِ ایستگاه.
    """
    for cand in (DESK_DIR.parent / name, DESK_DIR.parent / "docs" / name, GUI / "docs" / name):
        if cand.exists():
            return cand
    return DESK_DIR.parent / name          # اگر نبود، همان مسیر پیش‌فرض را برگردان


def doc_dir(name: str) -> Path:
    """پوشهٔ اسناد چندبخشی (مثل جزوهٔ راهبردها)."""
    for cand in (DESK_DIR.parent / name, DESK_DIR.parent / "docs" / name, GUI / "docs" / name):
        if cand.exists():
            return cand
    return DESK_DIR.parent / name


SERVED_FILES = {
    "dashboard": GUI / "data" / "dashboard.html",
    "backtest": GUI / "data" / "backtest.html",
    "backtest.csv": GUI / "data" / "backtest.csv",
    "method": GUI / "data" / "method-preview.html",
    "05-backtest.html": GUI / "data" / "backtest.html",
    "07-manifest.json": None,   # از پوشهٔ بسته پر می‌شود
    "03-method.html": GUI / "data" / "method-preview.html",
    "trial": GUI / "data" / "trial-report.html",
    "trial-report.html": GUI / "data" / "trial-report.html",
    "trial-entries.csv": GUI / "data" / "trial-entries.csv",
    "selftest": GUI / "data" / "selftest-report.html",
    "exam": GUI / "data" / "exam-sheet.html",
    "exam-sheet.html": GUI / "data" / "exam-sheet.html",
    "dossier": GUI / "data" / "investor-dossier.html",
    "dossier-md": GUI / "data" / "investor-dossier.md",
    "demo-investor": GUI / "DEMO-INVESTOR-FA.md",
    "readme": GUI / "README-FA.md",
    "data-routes": doc_path("05-data-routes-fa.md"),
    "feasibility": GUI / "data" / "data-feasibility.html",
    "requirement-sheet": GUI / "data" / "data-requirement-sheet.md",
    "data-strategy": doc_path("06-data-feasibility-fa.md"),
    "blind-sheet": GUI / "data" / "investor-blind-test.html",
    "blind-md": GUI / "data" / "investor-blind-test.md",
    "blind-sample": GUI / "data" / "investor-blind-test-sample.html",
    "ladder": GUI / "data" / "investor-ladder.md",
    "ladder-json": GUI / "data" / "investor-ladder.json",
    "pledge": GUI / "data" / "investor-pledge.md",
    "strategies": GUI / "data" / "strategy-library.html",
    "strategies-md": doc_dir("strategies") / "strategy-library-fa.md",
    "strategies-index": doc_dir("strategies") / "README-FA.md",
    "strategies-refs": doc_dir("strategies") / "references-fa.md",
    "stress": GUI / "data" / "edge-stress.html",
    "stress-md": GUI / "data" / "edge-stress.md",
    "bankroll": GUI / "data" / "bankroll.html",
    "bankroll-md": GUI / "data" / "bankroll.md",
    "judge": GUI / "data" / "signal-verdict.html",
    "judge-md": GUI / "data" / "signal-verdict.md",
    "differentiation": doc_path("08-differentiation-and-trust-fa.md"),
    "grant-doc": doc_path("09-sell-or-grant-access-fa.md"),
    "diagnostic": GUI / "data" / "diagnostic-report.html",
    "prospects": GUI / "data" / "prospects-board.html",
    "prospects-md": GUI / "data" / "prospects-board.md",
    "outreach": GUI / "data" / "outreach-pack.html",
    "outreach-md": GUI / "data" / "outreach-pack.md",
    "offer": GUI / "data" / "offer-one-pager.html",
    "offer-md": GUI / "data" / "offer-one-pager.md",
    "onboarding": GUI / "data" / "onboarding-pack.html",
    "onboarding-md": GUI / "data" / "onboarding-pack.md",
    "sales-today": GUI / "data" / "sales-today.html",
    "sales-today-md": GUI / "data" / "sales-today.md",
    "review-meeting": GUI / "data" / "review-meeting.html",
    "review-meeting-md": GUI / "data" / "review-meeting.md",
    "license-doc": GUI / "data" / "license-doc.html",
    "license-doc-md": GUI / "data" / "license-doc.md",
    "usage": GUI / "data" / "usage-statement.html",
    "usage-md": GUI / "data" / "usage-statement.md",
    "daily-inputs": doc_path("10-daily-inputs-fa.md"),
    "walkthrough": doc_path("13-novice-walkthrough-fa.md"),
    "snapshot-template": GUI / "data" / "snapshot-template.json",
    "zero-cost": doc_path("07-zero-cost-test-fa.md"),
    "witness": GUI / "data" / "witness-live.html",
    "witness-md": GUI / "data" / "witness-live.md",
}


# ---------------------------------------------------------------- کارهای مشترک
def snapshot_payload(snap) -> dict:
    label = snap.source_label
    if STATE.get("connection", {}).get("is_mock"):
        label = f"{label} · خوراک آزمایشی محلی (ساختگی)"      # هرگز دادهٔ ساختگی را واقعی جا نزنیم
    return {
        "status": snap.status,
        "source_label": label,
        "freshness": snap.freshness_label,
        "rows": len(snap.rows),
        "messages": list(snap.messages),
        "missing_fields": list(snap.missing_fields),
        "mode": snap.mode,
    }


def build_snapshot_for_state(mode: str | None = None, *, allow_network: bool = True,
                             live_cfg: dict | None = None):
    mode = mode or STATE["mode"]
    snap = datafeed.build_snapshot(mode, file_path=STATE.get("file_path") or None,
                                   live_cfg=live_cfg or STATE.get("live_cfg"), key=STATE.get("key"),
                                   allow_network=allow_network)
    STATE["snapshot"] = snap
    return snap


def fresh_live_cfg() -> dict:
    """نسخه‌ای از تنظیمات زنده که حافظهٔ نهان را دور می‌زند (برای بازسنجی دفتر)."""
    cfg = dict(STATE.get("live_cfg") or {})
    cfg["cache_seconds"] = 0
    return cfg


def materialize(snap) -> Path:
    rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in snap.rows]
    out = DATA / "current-snapshot.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"as_of": time.strftime("%Y-%m-%d %H:%M"), "hurdle": STATE["rules"]["hurdle"],
                               "capital": STATE["rules"]["capital"], "rows": rows},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def desk_config() -> dict:
    cfg = json.loads(json.dumps(deskmod.DEFAULT_CONFIG, ensure_ascii=False))
    cfg.update(STATE["rules"])
    return cfg


def signal_payload(s) -> dict:
    return {
        "sid": s.sid, "symbol": s.symbol, "kind": s.kind,
        "kind_label": deskmod.KIND_LABELS.get(s.kind, s.kind),
        "annualized": f"{s.annualized_pct:,.2f}" if isinstance(s.annualized_pct, (int, float)) else "—",
        "edge": f"{s.score_pp:,.2f}", "status": s.status,
        "status_label": {"pending": "منتظر تأیید", "approved": "تأییدشده", "rejected": "رد شده"}.get(s.status, s.status),
        "size": f"{s.contracts:,} {s.unit}", "contracts": s.contracts, "unit": s.unit,
        "margin_locked": s.margin_locked, "gate_note": s.gate_note, "alerts": s.alerts,
        "detail": {k: v for k, v in s.detail.items() if k != "_policy"},
        "mark": {"pending": "✅", "approved": "🟢", "rejected": "✖"}.get(s.status, "•"),
    }


def run_scan() -> dict:
    snap = STATE.get("snapshot") or build_snapshot_for_state()
    if not snap.rows:
        return {"error": "هیچ ردیفی برای محاسبه نیست؛ منبع داده را در گام ۲ بررسی کنید."}
    path = materialize(snap)
    cfg = desk_config()
    desk = deskmod.Desk()
    kodal_db = STATE["kodal_db"] if STATE.get("use_kodal") else None
    sigs = deskmod.scan_market(path, cfg, desk, kodal_db)
    STATE["last_sigs"] = sigs
    tasks = deskmod.recheck_tasks(cfg, desk, kodal_db, path) if kodal_db else []
    dash = deskmod.build_dashboard(desk, cfg, GUI / "data" / "dashboard.html", tasks)
    payloads = [signal_payload(s) for s in sigs]
    counts = {
        "total": len(payloads),
        "pending": len([s for s in sigs if s.status == "pending"]),
        "approved": len([s for s in sigs if s.status == "approved"]),
        "rejected": len([s for s in sigs if s.status == "rejected"]),
        "tasks": len(tasks),
        "locked": desk.locked_margin(),
    }
    return {"signals": payloads, "tasks": tasks, "counts": counts, "dashboard": str(dash),
            **snapshot_payload(snap)}


def decide(sid: str, action: str, note: str, force: bool = False) -> dict:
    desk = deskmod.Desk()
    sig = desk.get(sid)
    if not sig:
        return {"error": "شناسه پیدا نشد."}
    if action == "approved":
        policy = sig.detail.get("_policy") or {}
        cap = float(policy.get("cap_total") or STATE["rules"]["capital"] * STATE["rules"]["max_margin_pct"])
        max_positions = int(policy.get("max_positions") or STATE["rules"]["max_positions"])
        used = desk.locked_margin(exclude_sid=sid) + sig.margin_locked
        count = len([s for s in desk.all("approved") if s.sid != sid])
        if (used > cap or count >= max_positions) and not force:
            return {"blocked": True,
                    "message": f"تأیید این سیگنال سقف ریسک را رد می‌کند: سرمایهٔ درگیر {used:,.0f} از سقف {cap:,.0f} ریال · "
                               f"موقعیت‌های تأییدشده {count} از {max_positions}."}
        if force:
            note = (note + " | تأیید با رد سقف ریسک").strip(" |")
    desk.decide(sid, action, note)
    packet = deskmod.order_packet(desk.get(sid)) if action == "approved" else ""
    return {"ok": True, "status": action, "packet": packet}


def do_backtest(path: str) -> dict:
    rules = {k: STATE["rules"][k] for k in ("min_edge_arbitrage_pct", "min_edge_leveraged_pct",
                                            "min_liquidity_contracts_per_day", "max_spread_pct",
                                            "max_plausible_arb_pct", "max_plausible_lev_pct")}
    result = bt.run_backtest(path, rules=rules, capital=float(STATE["rules"]["capital"]))
    bt.build_report(result, GUI / "data" / "backtest.html")
    bt.write_csv(result, GUI / "data" / "backtest.csv")
    STATE["backtest_result"] = result
    return {"summary": result["summary"], "problems": result["summary"].get("problems", []),
            "file": str(path),
            "by_kind": {k: {kk: vv for kk, vv in v.items() if kk != "realized" and kk != "expected"}
                        for k, v in result["by_kind"].items()}}


def do_bundle() -> dict:
    snap = STATE.get("snapshot") or build_snapshot_for_state()
    state = {"data_mode": STATE["mode"], "snapshot": snap, "rules": STATE["rules"],
             "backtest_result": STATE.get("backtest_result")}
    out = st.build_bundle(state)
    STATE["bundle_dir"] = out
    files = []
    for f in sorted(Path(out).iterdir()):
        files.append({"file": f.name, "desc": _describe(f.name), "size": f.stat().st_size})
    return {"path": str(out), "files": files}


def _describe(name: str) -> str:
    table = {
        "01-dashboard.html": "داشبورد تصمیم‌ها (تأیید، رد، منتظر تأیید)",
        "02-signals.csv": "فهرست کامل سیگنال‌ها با دلیل دروازه‌ها",
        "03-method.html": "سند روش کار و چک‌لیست راستی‌آزمایی شرکت",
        "04-packets.txt": "بستهٔ سفارش سیگنال‌های تأییدشده و منتظر تأیید",
        "05-backtest.html": "گزارش پس‌آزمایی روی دادهٔ تاریخ",
        "06-backtest-rows.csv": "سطر به سطر نتیجهٔ پس‌آزمایی",
        "07-manifest.json": "شناسنامهٔ فنی بسته (نسخه‌ها، پارامترها، شمارش‌ها)",
        "README-FA.md": "چک‌لیست راستی‌آزمایی برای شرکت",
    }
    return table.get(name, "پروندهٔ همراه بسته")


# ---------------------------------------------------------------- کارساز

def _allowed_roots() -> list[Path]:
    """پوشه‌هایی که سرو کردن پرونده از آن‌ها مجاز است (هر چیز دیگر = ۴۰۳)."""
    # سندهای تحلیلی کنار خودِ ایستگاه می‌نشینند (پوشهٔ money) و باید سرو شوند؛
    # نام پرونده پیش‌تر پاک‌سازی می‌شود، پس از این پوشه‌ها هم چیزی بیرون نمی‌رود.
    roots = [WEB, GUI / "data", GUI / "demo", GUI / "docs", GUI.parent]
    bundle = (STATE.get("bundle_dir") if isinstance(STATE, dict) else None)
    if bundle:
        roots.append(Path(bundle))
    return roots


def _inside_allowed(path: Path) -> bool:
    try:
        target = Path(path).resolve()
    except OSError:
        return False
    for root in _allowed_roots():
        try:
            if target.is_relative_to(Path(root).resolve()):
                return True
        except (OSError, ValueError):
            continue
    return False


def _safe_output_name(raw: str) -> str | None:
    """نام پروندهٔ خروجی را پاک می‌کند؛ هر چیز مشکوک (اسلش، بازگشت به عقب، نویسهٔ صفر) رد می‌شود."""
    name = str(raw or "").strip().strip("\x00")
    if not name or "/" in name or "\\" in name or ".." in name or name.startswith("."):
        return None
    if len(name) > 120 or any(c in name for c in ("\n", "\r", "\t")):
        return None
    return name


def _meter(kind: str, label: str = "") -> None:
    """یک کار را در «دفتر استفاده» ثبت می‌کند؛ در برابر هر خطا ساکت است تا کار اصلی نشکند."""
    try:
        usagemod.record_event(kind, label=label)
    except Exception:
        pass

MAX_BODY_BYTES = 2 * 1024 * 1024          # سقف بدنهٔ درخواست: ۲ مگابایت (ضد پرکردن حافظه)
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
       "script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; "
       "form-action 'self'; base-uri 'none'")
TRUST_PROXY = str(os.environ.get("STATION_TRUST_PROXY") or "").strip() in ("1", "true", "yes")

# میزبان‌هایی که درخواستشان «همان برنامه» حساب می‌شود (وقتی پروکسی، هدر Host را عوض می‌کند).
# پیش‌فرض خالی است؛ روی میزبان ابری مثل Hugging Face، نام Space اینجا گذاشته می‌شود.
ALLOW_HOSTS = tuple(h.strip().lower() for h in
                    str(os.environ.get("STATION_ALLOW_HOSTS") or "").split(",") if h.strip())


class Handler(BaseHTTPRequestHandler):
    server_version = f"IranDeskStation/{VERSION}"

    def log_message(self, fmt, *args):  # ساکت کردن لاگ پیش‌فرض
        return

    # ---------- کمکی‌های امنیتی
    def _client_ip(self) -> str:
        """نشانی برای قفل تلاش‌های ناموفق.

        پیش‌فرض: نشانی واقعی سوکت (هدرها را باور نمی‌کنیم). اگر STATION_TRUST_PROXY=1 باشد و
        درخواست از پروکسی (تونل/بازکنندهٔ HTTPS) بیاید، نشانی کاربر از هدر خوانده می‌شود تا
        خطای یک نفر، بقیه را قفل نکند.
        """
        if TRUST_PROXY:
            for key in ("CF-Connecting-IP", "X-Real-IP", "X-Forwarded-For"):
                val = str(self.headers.get(key) or "").split(",")[0].strip()
                if val:
                    return val
        return str(self.client_address[0])

    def _secure_cookie(self) -> bool:
        """اگر درخواست از مسیر HTTPS آمده، کوکی Secure هم بشود."""
        proto = str(self.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
        if not proto:
            visitor = str(self.headers.get("CF-Visitor") or "")
            proto = "https" if '"https"' in visitor else ""
        return proto == "https"

    def _guard(self, method: str, run) -> None:
        """هر خطای پیش‌بینی‌نشده را به پاسخ ۵۰۰ خوانا تبدیل می‌کند + لاگِ ممیزی می‌نویسد.

        چرا: پیش‌تر اگر وسط یک درخواست خطایی رخ می‌داد، کارساز بدون پاسخ اتصال را می‌بست و
        کلاینت فقط «اتصال قطع شد» می‌دید (روی میزبان ابری همین اتفاق افتاد و ریشه‌یابی را سخت
        کرد). حالا هم پیام روشن برمی‌گردد، هم ردِ خطا در گزارش می‌ماند، هم کارِ هر کاربر
        در لاگِ ممیزی (پنل مدیریت ← لاگ‌ها) ثبت می‌شود تا هم «چه کار کرد» معلوم باشد و هم
        «باگ دقیقاً چی بوده».
        """
        t0 = time.monotonic()
        u = urlparse(self.path)
        path = u.path
        # چه کسی: از نشستِ دروازه (اگر هست)
        role = self._role()
        uid = self._role_id() if role else "—"
        self._audit_status = 0
        err = None
        try:
            run()
        except (BrokenPipeError, ConnectionResetError):
            pass                                   # کلاینت خودش رفت؛ کاری لازم نیست
        except Exception as e:                     # noqa: BLE001 — نگهبانِ آخر
            err = traceback.format_exc(limit=8)
            print(f"[{method}] خطای پیش‌بینی‌نشده: {e}\n{err}", flush=True)
            try:
                self._json({"error": f"خطای داخلی برنامه: {type(e).__name__} — {str(e)[:200]}",
                            "path": self.path, "kind": "internal_error"}, 500)
            except Exception:
                pass
        finally:
            self._audit_log(method, path, role, uid, int((time.monotonic() - t0) * 1000), err)

    # نامِ فارسیِ کارِ رایجِ هر مسیر — در لاگِ ممیزی به‌جای «POST /api/run»
    ACTION_LABELS = {
        "/": "باز شدن برنامه",
        "/admin": "باز شدن پنل مدیریت",
        "/login": "باز شدن صفحهٔ ورود",
        "/guide": "باز شدن راهنما",
        "/api/login": "ورود (شناسه/رمز)",
        "/api/logout": "خروج",
        "/api/admin/login": "ورود به پنل مدیریت",
        "/api/run": "شروع محاسبه",
        "/api/decide": "تأیید/رد سیگنال",
        "/api/snapshot": "ذخیرهٔ اسنپ‌شات",
        "/api/connections": "ذخیره/خواندن دفتر اتصال",
        "/api/test-live": "آزمایش دادهٔ زنده",
        "/api/autoconnect": "اتصال خودکار",
        "/api/daily": "اجرای مراسم امروز",
        "/api/trial": "ثبت/بازسنجی دفتر",
        "/api/backtest": "اجرای پس‌آزمایی",
        "/api/bundle": "ساخت بستهٔ تحویل",
        "/api/selftest": "اجرای آزمون ۱۰ دقیقه‌ای",
        "/api/dossier": "ساخت پروندهٔ سرمایه‌گر",
        "/api/health": "بررسی سلامت",
        "/api/diagnose": "گزارش عیب‌یابی",
        "/api/usage": "گواهی استفاده",
        "/api/license": "مجوز دسترسی",
        "/api/state/backup": "پشتیبان‌گیری",
        "/api/gate/update": "تغییر دروازه (کاربر/رمز/خاموشی)",
        "/api/prospects": "تابلوی پیگیری مخاطبان",
        "/api/ritual": "مراسم فروش امروز",
    }

    def _audit_log(self, method: str, path: str, role, uid, ms: int, err: str | None) -> None:
        """یک ردیف به لاگِ ممیزی می‌نویسد — هرگز نباید خودش خطا بدهد."""
        try:
            # فقط کارها و صفحاتِ معنادار؛ پرونده‌های ثابت و فیس‌آیکون لاگ نمی‌شوند تا پر نشود
            if not (path.startswith("/api/") or path in ("/", "/admin", "/guide", "/login")):
                return
            # خطاهای ۴۰۴ِ مسیریِ غیرموجود هم ثبت می‌شوند (نشانهٔ لینک خراب)
            status = getattr(self, "_audit_status", 0) or 0
            level = "error" if (err or status >= 500) else "info"
            label = self.ACTION_LABELS.get(path, f"{method} {path}")
            ip = "—"
            try:
                ip = str(self.client_address[0]) if self.client_address else "—"
            except Exception:
                pass
            details = {"query": dict(parse_qs(urlparse(self.path).query)) if urlparse(self.path).query else None}
            audit.write(DATA, user=uid, role=str(role or "بیرونی"), ip=ip, method=method,
                        path=path, action=label, details=details, status=status, ms=ms,
                        level=level, error=err)
        except Exception:
            pass

    def _reject_method(self) -> None:
        self._send(405, '{"error": "این روش درخواست پشتیبانی نمی‌شود."}'.encode("utf-8"),
                   headers={"Allow": "GET, POST"})

    do_PUT = do_DELETE = do_PATCH = do_TRACE = _reject_method

    def do_OPTIONS(self):
        self._send(204, b"", headers={"Allow": "GET, POST"})

    # ---------- کمکی‌ها
    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8",
              headers: dict | None = None) -> None:
        self._audit_status = code
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # سرآیندهای امنیتی: برنامه در قاب سایت دیگری جا نگیرد، مرورگر محتوا را جور دیگری
        # تفسیر نکند، و موتور جست‌وجو ایندکسش نکند.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive")
        self.send_header("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy", CSP)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    # ---------- دروازهٔ ورود (مدیر / مهمان)
    LOGIN_OPEN = ("/login", "/login.html", "/guide", "/guide.html", "/api/login",
                  "/api/gate/status", "/favicon.ico", "/api/admin/login")
# «/api/admin/login» عمداً باز است: رمز پنل همان رمز مدیر دروازه است و خودش قفل تلاش و
# محدودیت دارد؛ باز بودنش فقط یک ورودِ اضافی را حذف می‌کند، نه یک درِ تازه باز می‌کند.

    def _cookies(self) -> dict:
        out: dict[str, str] = {}
        for part in str(self.headers.get("Cookie") or "").split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                out[k.strip()] = v.strip()
        return out

    def _drain_body(self, limit: int = 32 * 1024 * 1024) -> None:
        """بدنهٔ رهاشده را تکه‌تکه می‌خواند و دور می‌ریزد تا پاسخ ما به دست کاربر برسد."""
        try:
            left = min(int(self.headers.get("Content-Length", 0) or 0), limit)
        except ValueError:
            left = 0
        while left > 0:
            chunk = self.rfile.read(min(65536, left))
            if not chunk:
                break
            left -= len(chunk)
        self.close_connection = True

    def _csrf_ok(self) -> bool:
        """اگر مرورگر مبدأ بفرستد، باید همان میزبان ما باشد (ضد CSRF)."""
        origin = str(self.headers.get("Origin") or "").strip()
        if not origin or origin == "null":
            return True
        try:
            netloc = urlparse(origin).netloc
        except ValueError:
            return False
        host = str(self.headers.get("Host") or "").strip().lower()
        if netloc == host:
            return True
        # پشت پروکسی میزبان ابری، هدر Host ممکن است نام داخلی باشد؛ پس نام عمومی Space را هم
        # می‌پذیریم — ولی فقط همان نام‌هایی که خودمان در محیط گذاشته‌ایم (بدون الگوی عام).
        return netloc in ALLOW_HOSTS

    def _gate_token(self) -> str | None:
        return self._cookies().get(gatemod.COOKIE) or None

    def _role(self) -> str | None:
        return gatemod.role_of(self._gate_token())

    def _role_id(self) -> str:
        return (gatemod.who(self._gate_token()) or {}).get("id") or "—"

    @staticmethod
    def _guest_blocked(path: str) -> bool:
        """چیزهایی که مهمان/کارفرما نباید ببیند: پنل مدیریت، صدور مجوز، دروازه، خاموشی."""
        return (path == "/admin" or path.startswith("/admin") or path.startswith("/api/admin")
                or path.startswith("/api/license") or path in ("/api/shutdown", "/api/gate/update"))

    def _gate_guard(self, path: str) -> bool:
        """True = بگذر. اگر پاسخ داده شد (۴۰۱/۴۰۳/ریدایرکت)، False."""
        if not gatemod.enabled() or path in self.LOGIN_OPEN:
            return True
        role = self._role()
        if role is None:
            if path.startswith(("/api/", "/files/")):
                self._json({"error": "برای دیدن برنامه اول وارد شوید.", "login_required": True}, 401)
            else:
                self._send(302, b"", "text/plain; charset=utf-8",
                           headers={"Location": "/login?next=" + quote(path)})
            return False
        if role == "guest" and self._guest_blocked(path):
            if path.startswith(("/api/", "/files/")):
                self._json({"error": "این بخش فقط با حساب مدیر باز می‌شود.",
                            "guest_blocked": True}, 403)
            else:
                body = ("<!DOCTYPE html><html lang=\"fa\" dir=\"rtl\"><head><meta charset=\"utf-8\">"
                        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
                        "<title>فقط با حساب مدیر</title></head>"
                        "<body style=\"font-family:Tahoma,sans-serif;background:#f5f7f9;color:#12202e;"
                        "display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0\">"
                        "<div style=\"background:#fff;border:1px solid #e3e6ea;border-radius:14px;"
                        "padding:26px 28px;max-width:460px;line-height:2\">"
                        "<h2 style=\"margin:0 0 10px\">این بخش فقط با حساب مدیر باز می‌شود</h2>"
                        "<p style=\"margin:0 0 16px;color:#5b6b7c;font-size:14px\">این بخش برای صدور "
                        "اجازه‌نامه، عوض‌کردن رمزها و خاموش‌کردن برنامه است. حساب کارفرما (مهمان) به آن "
                        "دسترسی ندارد؛ باقی برنامه و همهٔ خروجی‌ها باز است.</p>"
                        "<a href=\"/\" style=\"display:inline-block;padding:10px 16px;border-radius:10px;"
                        "background:#0f766e;color:#fff;text-decoration:none\">بازگشت به برنامه</a>"
                        "</div></body></html>")
                self._send(403, body.encode("utf-8"), "text/html; charset=utf-8")
            return False
        return True

    def _token(self, body: dict | None = None) -> str:
        """توکن پنل را از سرآیند، پارامتر نشانی یا بدنهٔ درخواست می‌خواند."""
        head = str(self.headers.get("X-Admin-Token") or "").strip()
        if head:
            return head
        q = parse_qs(urlparse(self.path).query)
        if (q.get("token") or [""])[0]:
            return str((q.get("token") or [""])[0])
        return str((body or {}).get("token") or "").strip()

    def _json(self, payload: dict, code: int = 200, headers: dict | None = None) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        if length > MAX_BODY_BYTES:
            raise ValueError(f"بدنهٔ درخواست بسیار بزرگ است ({length} بایت).")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _serve_file(self, path: Path) -> None:
        # لایهٔ دوم نگهبانی: مسیر نهایی باید داخل پوشه‌های مجاز باشد
        if not _inside_allowed(path):
            return self._json({"error": "دسترسی به این مسیر مجاز نیست."}, 403)
        if not path.exists():
            self._json({"error": f"پرونده پیدا نشد: {path}"}, 404)
            return
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if path.suffix == ".html":
            ctype = "text/html; charset=utf-8"
        elif path.suffix == ".json":
            ctype = "application/json; charset=utf-8"
        elif path.suffix in (".md", ".csv", ".txt"):
            ctype = "text/plain; charset=utf-8"
        self._send(200, path.read_bytes(), ctype)

    # ---------- مسیرها
    def do_GET(self):
        return self._guard("GET", self._do_get)

    def _do_get(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._gate_guard(u.path):
            return

        if u.path in ("/login", "/login.html"):
            return self._serve_file(WEB / "login.html")
        if u.path in ("/guide", "/guide.html"):
            # راهنمای کارفرما: پیش از ورود هم باز است تا کسی بی‌راهنما نماند
            return self._serve_file(WEB / "guide.html")
        if u.path in ("/api/state/info", "/api/admin/state"):
            if not admauth.check_token(self._token()):
                return self._json({"error": "این بخش فقط با ورود به پنل مدیریت در دسترس است.",
                                   "needs_admin": True}, 403)
            sk = state_keeper()
            return self._json(sk.info() if sk else OFFLINE_STATE)

        if u.path == "/api/gate/status":
            s = gatemod.status()
            role = self._role()
            # شناسه‌ها و فهرست کاربران فقط برای مدیر؛ بیرون از ورود، حداقل اطلاعات
            payload = {"enabled": s["enabled"], "logged_in": role is not None, "role": role,
                       "id": self._role_id() if role else "—", "rule": s["rule"],
                       "ttl_hours": s["ttl_hours"], "open_sessions": s["open_sessions"]}
            if role == "admin":
                payload.update({"guest": s["accounts"]["guest"], "admin": s["accounts"]["admin"],
                                "users": s["users"]})
            return self._json(payload)

        if u.path in ("/", "/index.html"):
            return self._serve_file(WEB / "index.html")
        if u.path == "/app.js":
            return self._serve_file(WEB / "app.js")
        if u.path == "/help.js":
            return self._serve_file(WEB / "help.js")
        if u.path in ("/admin", "/admin.html"):
            return self._serve_file(WEB / "admin.html")
        if u.path == "/admin.js":
            return self._serve_file(WEB / "admin.js")
        if u.path == "/favicon.ico":
            return self._send(204, b"")

        if u.path == "/api/admin/audit":
            if not admauth.check_token(self._token()):
                return self._json({"error": "این بخش فقط با ورود به پنل مدیریت در دسترس است.",
                                   "needs_admin": True}, 403)
            try:
                limit = int((q.get("limit") or ["500"])[0])
            except ValueError:
                limit = 500
            entries = audit.read(DATA, limit=limit, user=(q.get("user") or [None])[0] or None,
                                 q=(q.get("search") or [None])[0] or None,
                                 level=(q.get("level") or [None])[0] or None)
            return self._json({"ok": True, "entries": entries, "count": len(entries),
                               "stats": audit.stats(DATA)})

        if u.path == "/api/health":
            # «بررسی سلامت» به پنل مدیریت منتقل شده است؛ خواندنش هم با توکن ورود می‌شود.
            if not admauth.check_token(self._token()):
                return self._json({"error": "بررسی سلامت به پنل مدیریت منتقل شده است؛ از /admin وارد شوید.",
                                   "needs_admin": True}, 403)
            ok, items = st.health_report()
            return self._json({"items": [{"name": n, "ok": f, "note": r} for n, f, r in items],
                               "passed": len([1 for _, f, _ in items if f]), "total": len(items),
                               "ok": ok, "version": VERSION})

        if u.path == "/api/state":
            return self._json({"rules": STATE["rules"], "mode": STATE["mode"],
                               "file_path": STATE.get("file_path"), "kodal_db": STATE["kodal_db"],
                               "use_kodal": STATE["use_kodal"], "connection": STATE["connection"]})

        if u.path == "/api/data-guide":
            return self._json({
                "rows": [list(r) for r in st.API_GUIDE_ROWS],
                "snapshot_template": STATE.get("file_path") or str(DESK_DIR / "market-demo.json"),
                "history_template": str(GUI / "demo" / "history-demo.csv"),
                "kodal_db": STATE["kodal_db"],
            })

        if u.path == "/api/mode-info":
            mode = (q.get("mode") or ["sim"])[0]
            card = datafeed.SOURCE_CARDS.get(mode, {})
            return self._json({"mode": mode, **{k: card.get(k, "") for k in ("label", "cost", "gives", "after", "how")}})

        if u.path == "/api/snapshot/rows":
            path = STATE.get("file_path") or str(DESK_DIR / "market-demo.json")
            data = datafeed.load_snapshot_rows(path)
            data["mode"] = STATE["mode"]
            data["dir"] = str(GUI / "data" / "snapshots")
            data["last_dated"] = sorted([f.name for f in (GUI / "data" / "snapshots").glob("snapshot-*.json")])[-3:] \
                if (GUI / "data" / "snapshots").exists() else []
            return self._json(data)

        if u.path == "/api/connections":
            return self._json(connection_payload())

        if u.path == "/api/trial":
            return self._json(trial_payload())

        if u.path == "/api/signals":
            db = deskmod.Desk()
            return self._json({"signals": [signal_payload(s) for s in db.all(limit=300)]})

        if u.path == "/api/alerts":
            dbs = (q.get("db") or [STATE["kodal_db"]])[0]
            return self._json({"items": datafeed.read_alerts(dbs, 55, 30)})

        if u.path.startswith("/files/"):
            name = _safe_output_name(u.path[len("/files/"):])
            if name is None:
                return self._json({"error": "نام پروندهٔ نامعتبر."}, 400)
            if name in ("method", "03-method.html"):
                # سند روش کار از وضعیت همین لحظه ساخته می‌شود تا دکمهٔ «نمایش سند روش کار» خالی نماند
                target = GUI / "data" / "method-preview.html"
                try:
                    rk_write = st.build_method_html(STATE)
                except Exception as e:                      # نباید پنهان بماند
                    return self._json({"error": f"ساخت سند روش کار ناموفق: {type(e).__name__}: {e}"}, 500)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(rk_write, encoding="utf-8")
                return self._serve_file(target)
            if name in ADMIN_FILE_KEYS and not admauth.check_token(self._token()):
                return self._json({"error": "این پرونده از پنل مدیریت است؛ اول وارد شوید.",
                                   "needs_admin": True}, 403)
            if name in SERVED_FILES:
                target = SERVED_FILES[name] or (Path(STATE["bundle_dir"]) / name if STATE.get("bundle_dir") else None)
                if target:
                    return self._serve_file(Path(target))
            if STATE.get("bundle_dir"):
                cand = Path(STATE["bundle_dir"]) / name
                if cand.exists():
                    return self._serve_file(cand)
            return self._json({"error": "پروندهٔ خواسته‌شده ساخته نشده است."}, 404)

        return self._json({"error": "مسیر ناشناخته"}, 404)

    def do_POST(self):
        return self._guard("POST", self._do_post)

    def _do_post(self):
        u = urlparse(self.path)
        try:
            body = self._read_json()
        except ValueError as e:                       # بدنهٔ بزرگ یا خراب
            self._drain_body()                        # بقیهٔ بدنه را بی‌آنکه نگه داریم می‌خوانیم
            return self._json({"error": str(e)}, 413, headers={"Connection": "close"})
        if not self._csrf_ok():                       # درخواست از سایت دیگر
            return self._json({"error": "این درخواست از جای دیگری آمده و پذیرفته نمی‌شود."}, 403)
        if not self._gate_guard(u.path):
            return

        # --- دروازه: ورود، خروج، مدیریت دسترسی، خاموشی ---
        if u.path == "/api/login":
            out = gatemod.login(str((body or {}).get("id") or ""),
                                str((body or {}).get("pass") or ""),
                                ip=self._client_ip())
            if not out.get("ok"):
                return self._json(out, 401)
            cookie = (f"{gatemod.COOKIE}={out['token']}; Path=/; HttpOnly; SameSite=Lax; "
                      f"Max-Age={gatemod.TTL_SECONDS}" + ("; Secure" if self._secure_cookie() else ""))
            return self._json({"ok": True, "role": out["role"], "id": out["id"],
                               "expires_in_minutes": out["expires_in_minutes"]},
                              headers={"Set-Cookie": cookie})
        if u.path == "/api/logout":
            closed = gatemod.logout(self._gate_token())
            return self._json({"ok": True, "closed": closed},
                              headers={"Set-Cookie": f"{gatemod.COOKIE}=; Path=/; Max-Age=0" +
                                                      ("; Secure" if self._secure_cookie() else "")})
        if u.path == "/api/gate/update":
            if self._role() != "admin":
                return self._json({"error": "این کار فقط با حساب مدیر.", "guest_blocked": True}, 403)
            action = str((body or {}).get("action") or "")
            try:
                if action == "gate-on":
                    gatemod.set_enabled(True); note = "دروازه روشن شد."
                elif action == "gate-off":
                    gatemod.set_enabled(False); note = "دروازه خاموش شد: همین رایانه = مدیر."
                elif action == "guest-on":
                    gatemod.set_enabled_account("guest", True); note = "دسترسی مهمان روشن شد."
                elif action == "guest-off":
                    gatemod.set_enabled_account("guest", False)
                    note = "دسترسی مهمان قطع شد؛ نشست باز او هم بسته شد."
                elif action == "close-guest-sessions":
                    n = gatemod.close_sessions("guest")
                    note = f"{n} نشست مهمان بسته شد."
                elif action == "set-guest":
                    gatemod.set_account("guest", str((body or {}).get("id") or ""),
                                        str((body or {}).get("pass") or ""))
                    note = "شناسه و رمز مهمان عوض شد."
                elif action == "user-add":
                    u = gatemod.add_user(str((body or {}).get("id") or ""),
                                         str((body or {}).get("pass") or ""),
                                         note=str((body or {}).get("note") or ""))
                    note = (f"کاربر «{u['id']}» ساخته شد؛ با همین شناسه و رمز وارد می‌شود "
                            "(فقط هش روی دیسک می‌ماند).")
                elif action in ("user-del", "user-delete"):
                    out = gatemod.delete_user(str((body or {}).get("id") or ""))
                    note = (f"کاربر «{out['id']}» کامل حذف شد؛ {out['closed']} نشست بازش هم "
                            f"بسته شد. {out['left']} کاربر دیگر مانده.")
                elif action == "user-on":
                    u = gatemod.set_user_enabled(str((body or {}).get("id") or ""), True)
                    note = f"دسترسی «{u['id']}» وصل شد."
                elif action == "user-off":
                    u = gatemod.set_user_enabled(str((body or {}).get("id") or ""), False)
                    note = (f"دسترسی «{u['id']}» قطع شد؛ {u['closed']} نشست بازش هم بسته شد.")
                elif action == "set-admin":
                    gatemod.set_account("admin", str((body or {}).get("id") or ""),
                                        str((body or {}).get("pass") or ""))
                    note = "شناسه و رمز مدیر عوض شد."
                else:
                    return self._json({"error": f"کار ناشناخته: {action or '—'}"}, 400)
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            s = gatemod.status()
            return self._json({"ok": True, "note": note, "enabled": s["enabled"],
                               "guest": s["accounts"]["guest"], "admin": s["accounts"]["admin"],
                               "users": s["users"]})
        if u.path == "/api/shutdown":
            if self._role() != "admin":
                return self._json({"error": "خاموش کردن برنامه فقط با حساب مدیر.",
                                   "guest_blocked": True}, 403)
            if (body or {}).get("dry"):
                return self._json({"ok": True, "would_stop": True,
                                   "note": "بررسی خشک: هیچ‌چیز خاموش نشد."})
            if not (body or {}).get("confirm"):
                return self._json({"error": "برای خاموش کردن، confirm بفرستید."}, 400)

            def _stop():
                try:
                    self.server.shutdown()
                finally:
                    time.sleep(0.4)
                    os._exit(0)              # خوراک آزمایشی و هر رشتهٔ دیگری هم می‌رود

            threading.Timer(0.7, _stop).start()
            return self._json({"ok": True, "note": "برنامه خاموش می‌شود؛ برای روشن کردن دوباره، "
                                                   "همان run-gui را بزنید."})

        # --- پنل مدیریت: ورود، خروج، و نگهبانیِ سه بخش منتقل‌شده ---
        if u.path == "/api/admin/login":
            out = admauth.login(str((body or {}).get("id") or ""),
                                str((body or {}).get("pass") or ""),
                                ip=self._client_ip())
            return self._json(out, 200 if out.get("ok") else 401)
        if u.path == "/api/admin/whoami":
            ok = admauth.check_token(self._token(body))
            return self._json({"ok": ok, "error": "" if ok else "توکن نامعتبر یا منقضی است."},
                              200 if ok else 401)
        if u.path == "/api/admin/logout":
            admauth.revoke_token(self._token(body))
            return self._json({"ok": True})
        if u.path == "/api/admin/audit":
            if not admauth.check_token(self._token(body)):
                return self._json({"error": "این بخش فقط با ورود به پنل مدیریت در دسترس است.",
                                   "needs_admin": True}, 403)
            action = str((body or {}).get("action") or "").strip()
            if action == "clear":
                n = audit.clear(DATA)
                return self._json({"ok": True, "cleared": n})
            if action == "reset":
                name = audit.reset(DATA)
                return self._json({"ok": True, "archived": name or "(لاگ خالی بود)"})
            if action == "copy":
                try:
                    limit = int((body or {}).get("limit") or 5000)
                except (TypeError, ValueError):
                    limit = 5000
                return self._json({"ok": True, "text": audit.text(DATA, limit=limit),
                                   "stats": audit.stats(DATA)})
            return self._json({"error": "کار ناشناخته: فقط copy / clear / reset."}, 400)
        if u.path in ADMIN_MAP:
            if not admauth.check_token(self._token(body)):
                return self._json({"error": "این بخش فقط با ورود به پنل مدیریت در دسترس است.",
                                   "needs_admin": True}, 403)
            if u.path == "/api/admin/health":
                ok, items = st.health_report()
                return self._json({"items": [{"name": n, "ok": f, "note": r} for n, f, r in items],
                                   "passed": len([1 for _, f, _ in items if f]), "total": len(items),
                                   "ok": ok, "version": VERSION})
            u = u._replace(path=ADMIN_MAP[u.path])
        elif u.path in ADMIN_ENDPOINTS and not admauth.check_token(self._token(body)):
            return self._json({"error": "این بخش به پنل مدیریت منتقل شده است؛ از /admin وارد شوید.",
                               "needs_admin": True}, 403)

        if u.path == "/api/state/info":
            sk = state_keeper()
            return self._json(sk.info() if sk else OFFLINE_STATE)
        if u.path == "/api/state/backup":
            sk = state_keeper()
            if not sk:
                return self._json({**OFFLINE_STATE, "ok": False})
            return self._json(sk.backup_now("درخواست مدیر از پنل"))

        if u.path == "/api/autoconnect":
            rep = autoconn.autoconnect(
                symbol=str(body.get("symbol") or "اهرم"),
                timeout=float(body.get("timeout") or 10.0),
                allow_network=not bool(body.get("offline")),
                save=bool(body.get("save")))
            if rep.get("saved"):
                active = conn.apply_profile(conn.load_store(), rep["saved"]["name"])
                STATE["live_cfg"] = active["live_cfg"]
                if active["key"]:
                    STATE["key"] = active["key"]
                STATE["mode"] = "live"
                STATE["connection"] = {"name": active["name"], "label": active["profile"]["label"],
                                       "key_where": active["key_where"], "is_mock": active["is_mock"]}
                rep["active"] = STATE["connection"]
                cand = next((c for c in autoconn.CANDIDATES if c["name"] == rep["saved"]["name"]), {})
                if cand.get("needs_code"):
                    snap_data = datafeed.load_snapshot_rows(STATE.get("file_path") or "")
                    if snap_data.get("rows"):
                        rows, notes = autoconn.enrich_snapshot_with_codes(
                            snap_data["rows"], cand, timeout=float(body.get("timeout") or 10.0))
                        if any(r.get("feed_symbol") for r in rows):
                            out = datafeed.save_dated_snapshot(rows, note="کد نمادها خودکار پر شد")
                            STATE["file_path"] = str(out)
                            STATE["mode"] = "live"
                            rep["codes_file"] = str(out)
                        rep["code_notes"] = notes
            rep["connections"] = connection_payload()
            return self._json(rep, 200 if rep.get("ok") else 200)

        if u.path == "/api/snapshot/import":
            _meter("import", "ورود اعداد از متن کارگزاری")
            text = str((body or {}).get("text") or "")
            res = snapimp.parse_paste(text, toman_to_rial=bool((body or {}).get("toman")),
                                      default_kind=(str((body or {}).get("kind") or "").strip() or None))
            if res.get("rows"):
                clean, problems = datafeed.clean_rows(res["rows"])
                res["rows"] = clean
                res["problems"] = list(res.get("problems") or []) + list(problems)
                res["count"] = len(clean)
                res["ok"] = bool(clean)
            return self._json(res)

        if u.path == "/api/snapshot/save":
            _meter("snapshot", "ذخیرهٔ اسنپ‌شات تاریخ‌دار")
            if not body.get("confirm_real"):
                return self._json({"error": "برای ذخیره، تیک «این اعداد را خودم از سامانهٔ کارگزاری برداشتم» "
                                            "را بزنید. بدون آن، این پرونده روز «واقعی» حساب نمی‌شود."}, 400)
            rows = body.get("rows") or []
            clean, problems = datafeed.clean_rows(rows)
            if not clean:
                return self._json({"error": "هیچ ردیف درستی وارد نشد.", "problems": problems}, 400)
            path = datafeed.save_dated_snapshot(
                clean, as_of=body.get("as_of") or None,
                hurdle=float(body.get("hurdle") or STATE["rules"]["hurdle"]),
                capital=float(body.get("capital") or STATE["rules"]["capital"]),
                note=str(body.get("note") or ""))
            STATE["file_path"] = str(path)
            STATE["mode"] = "file"
            snap = build_snapshot_for_state("file", allow_network=False)
            return self._json({"ok": True, "path": str(path), "problems": problems,
                               "rows": len(clean),
                               "checklist": ["عکس صفحهٔ سامانهٔ کارگزاری را هم برای همین تاریخ نگه دارید",
                                             "وجه تضمین هر قرارداد را از سامانه بردارید، نه از حافظه",
                                             "این پرونده با تاریخ ذخیره شد و روز «واقعی» حساب می‌شود"],
                               "snapshot": snapshot_payload(snap)})

        if u.path == "/api/connections/save":
            store = conn.load_store()
            prof = conn.upsert_profile(store, body.get("profile") or {})
            if body.get("select", True):
                conn.select_profile(store, prof["name"])
            conn.save_store(store)
            key = str(body.get("key") or "")
            if body.get("save_key"):
                conn.save_key(prof["name"], key)
            elif key:
                pass                      # کلید فقط در حافظه می‌ماند
            active = conn.apply_profile(conn.load_store(), prof["name"], inline_key=key)
            STATE["live_cfg"] = active["live_cfg"]
            if active["key"]:
                STATE["key"] = active["key"]
            STATE["connection"] = {"name": prof["name"], "label": prof["label"],
                                   "key_where": active["key_where"], "is_mock": active["is_mock"]}
            return self._json({"ok": True, "profile": prof, "active": STATE["connection"],
                               "keys_stored": bool(conn.load_keys()),
                               "saved_to": str(conn.PROFILES_FILE)})

        if u.path == "/api/connections/select":
            store = conn.load_store()
            name = str(body.get("name") or "")
            if conn.find_profile(store, name) is None:
                return self._json({"error": "پروفایل پیدا نشد."}, 404)
            conn.select_profile(store, name)
            conn.save_store(store)
            active = conn.apply_profile(conn.load_store(), name, inline_key=str(body.get("key") or ""))
            STATE["live_cfg"] = active["live_cfg"]
            if active["key"]:
                STATE["key"] = active["key"]
            STATE["mode"] = "live"
            STATE["connection"] = {"name": active["name"], "label": active["profile"]["label"],
                                   "key_where": active["key_where"], "is_mock": active["is_mock"]}
            return self._json({"ok": True, "active": STATE["connection"], "live_cfg": STATE["live_cfg"],
                               "is_mock": active["is_mock"]})

        if u.path == "/api/connections/delete":
            store = conn.load_store()
            name = str(body.get("name") or "")
            if name in ("mock-local", "custom") and conn.find_profile(store, name):
                return self._json({"error": "این دو پروفایل پایه‌اند و پاک نمی‌شوند."}, 400)
            gone = conn.delete_profile(store, name)
            conn.save_store(store)
            conn.save_key(name, "")          # کلید ذخیره‌شدهٔ آن هم پاک شود
            return self._json({"ok": True, "deleted": gone, "selected": conn.load_store().get("selected")})

        if u.path == "/api/connections/key":
            name = str(body.get("name") or STATE["connection"].get("name") or "")
            key = str(body.get("key") or "")
            if not name:
                return self._json({"error": "اول یک پروفایل انتخاب کنید."}, 400)
            if body.get("save"):
                conn.save_key(name, key)
            STATE["key"] = key
            return self._json({"ok": True, "saved": bool(body.get("save")),
                               "key_status": conn.key_status(name)})

        if u.path == "/api/peek":
            return self._json(peek_payload(body))

        if u.path == "/api/trial/record":
            sigs = STATE.get("last_sigs") or []
            if not sigs:
                return self._json({"error": "اول گام ۵ (اجرا و محاسبه) را بزنید تا سیگنالی برای ثبت باشد."}, 400)
            wanted = body.get("sids") or []
            if wanted:
                sigs = [x for x in sigs if getattr(x, "sid", "") in set(wanted)]
            t = trial.Trial(STATE["trial_db"])
            snap = STATE.get("snapshot")
            label = getattr(snap, "source_label", "") if snap else ""
            saved = t.record_from_signals(sigs, source_label=str(label),
                                          mode=STATE.get("mode", ""),
                                          add_span=float(body.get("add_span") or 0.0))
            return self._json({"ok": True, "saved": len(saved),
                               "skipped": len(sigs) - len(saved),
                               "trial": trial_payload()})

        if u.path == "/api/sources/feasibility":
            fixture = bool(body.get("fixture"))
            httpd = None
            host = ""
            try:
                if fixture:
                    httpd, host = sourcesmod.start_fixture()
                result = sourcesmod.probe_all(
                    symbol=str(body.get("symbol") or "فولاد"),
                    host=host,
                    timeout=float(body.get("timeout") or 8.0),
                    with_stability=not bool(body.get("no_stability")),
                    code=str(body.get("code") or ""))
                result["fixture"] = fixture
                ws = sourcesmod.probe_ws(str(body["ws_url"]), timeout=float(body.get("timeout") or 8.0)) \
                    if body.get("ws_url") else None
                report = sourcesmod.build_report(result, sourcesmod.build_matrix(), ws)
            finally:
                if httpd:
                    httpd.shutdown()
            return self._json({"ok": True, **result, "ws": ws, "matrix": sourcesmod.build_matrix(),
                               "report": str(report), "needs": sourcesmod.NEEDS})

        if u.path == "/api/sources/sheet":
            out = GUI / "data" / "data-requirement-sheet.md"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(sourcesmod.requirement_sheet(), encoding="utf-8")
            return self._json({"ok": True, "path": str(out)})

        if u.path == "/api/license":
            action = str((body or {}).get("action") or "status")
            if action == "grant":
                months = int((body or {}).get("months") or 12)
                row = licmod.make_license(str((body or {}).get("client") or "بدون نام"),
                                          months=months,
                                          contact=str((body or {}).get("contact") or ""),
                                          note=str((body or {}).get("note") or ""))
                path = licmod.write_license(row)
                _meter("license", f"صدور مجوز دسترسی: {months} ماه")
                return self._json({"ok": True, "license": row, "path": str(path),
                                   "status": licmod.verify(row), "ladder": licmod.ladder()})
            if action == "document":
                try:
                    h, m = licmod.build_document()
                except (OSError, ValueError) as e:
                    return self._json({"error": f"ساخت سند ناموفق: {e}"}, 500)
                _meter("license", "سند چاپی اجازه‌نامه")
                return self._json({"ok": True, "html": str(h), "md": str(m),
                                   "status": licmod.verify()})

            if action == "trial":
                row = licmod.make_trial(str((body or {}).get("client") or "آزمون ارزیابی"))
                path = licmod.write_license(row)
                _meter("license", "صدور مجوز آزمون ارزیابی")
                return self._json({"ok": True, "license": row, "path": str(path),
                                   "status": licmod.verify(row)})
            if action == "revoke":
                p = Path(licmod.LICENSE_FILE)
                if p.exists():
                    p.unlink()
                _meter("license", "باطل‌کردن مجوز")
                return self._json({"ok": True, "status": licmod.verify(None)})
            return self._json({"ok": True, "status": licmod.verify(),
                               "license": licmod.read_license(), "ladder": licmod.ladder()})

        if u.path == "/api/prospects":
            action = str((body or {}).get("action") or "list")
            name = str((body or {}).get("name") or "").strip()
            when = str((body or {}).get("date") or "") or None
            if action == "add":
                try:
                    out = prospectsmod.add(name, kind=str((body or {}).get("kind") or "company"),
                                           channel=str((body or {}).get("channel") or "telegram"),
                                           note=str((body or {}).get("note") or ""), when=when)
                except ValueError as e:
                    return self._json({"error": str(e)}, 400)
                if out.get("ok"):
                    _meter("prospect", f"مخاطب تازه: {name}")
            elif action in ("sent", "followup", "reply", "meeting", "outcome"):
                out = prospectsmod.mark(name, action, when=when,
                                        note=str((body or {}).get("note") or ""),
                                        result=str((body or {}).get("result") or ""))
                if out.get("ok"):
                    _meter("prospect", f"{action}: {name}")
            elif action == "close":
                out = prospectsmod.close(name)
            elif action == "sheet":
                h, m = prospectsmod.build_sheet()
                _meter("prospect", "برگهٔ تابلوی پیگیری")
                return self._json({"ok": True, "html": str(h), "md": str(m),
                                   "week": prospectsmod.week_numbers(),
                                   "todo": prospectsmod.todo()})
            else:
                out = {"ok": True}
            if not out.get("ok"):
                return self._json({"error": out.get("detail") or "انجام نشد.", "row": out.get("row")}, 400)
            rows = prospectsmod.load()
            return self._json({"ok": True, "row": out.get("row"), "prospects": rows,
                               "todo": prospectsmod.todo(rows),
                               "week": prospectsmod.week_numbers(rows)})

        if u.path == "/api/outreach":
            client = str((body or {}).get("client") or "")
            kind = str((body or {}).get("kind") or "company")
            if kind not in outreachmod.KINDS:
                kind = "company"
            h, m = outreachmod.build_pack(client, kind=kind)
            _meter("outreach", f"پیام معرفی برای {client or 'بدون نام'} ({kind})")
            return self._json({"ok": True, "html": str(h), "md": str(m), "kind": kind,
                               "kind_label": outreachmod.KINDS[kind],
                               "rules": len(outreachmod.messages(client, kind=kind)["rules"])})

        if u.path == "/api/offer":
            client = str((body or {}).get("client") or "")
            try:
                monthly = int((body or {}).get("monthly") or 0)
                setup = int((body or {}).get("setup") or 0)
            except (TypeError, ValueError):
                return self._json({"error": "مبلغ باید عدد باشد (ریال)."}, 400)
            h, m = offermod.build_offer(client, monthly_rial=monthly, setup_rial=setup)
            _meter("offer", f"پیشنهاد یک‌صفحه‌ای برای {client or 'بدون نام'}")
            return self._json({"ok": True, "html": str(h), "md": str(m),
                               "price_given": bool(monthly or setup),
                               "kit": offermod._kit_facts()})

        if u.path == "/api/sales-ritual":
            sender = str((body or {}).get("sender") or "مسعود")
            on = str((body or {}).get("on") or "") or None
            p = ritualmod.plan(on=on, sender=sender)
            h, m = ritualmod.build_sheet(on=on, sender=sender)
            _meter("sales", f"مراسم فروش {p['date']} — "
                            f"{p['counts']['messages']} پیام · {p['counts']['calls']} تماس")
            return self._json({"ok": True, "html": str(h), "md": str(m), "date": p["date"],
                               "used_minutes": p["used_minutes"], "budget": p["budget"],
                               "counts": p["counts"], "deferred": p["deferred"],
                               "items": [{"name": i["name"], "action": i["action"],
                                          "kind": i["kind"], "channel_label": i["channel_label"]}
                                         for i in p["items"]],
                               "week": p["week"], "note": p["note"]})

        if u.path == "/api/review-meeting":
            client = str((body or {}).get("client") or "")
            start = str((body or {}).get("start") or "") or None
            on = str((body or {}).get("on") or "") or None
            try:
                monthly = int((body or {}).get("monthly") or 0)
                setup = int((body or {}).get("setup") or 0)
                follow_on = str((body or {}).get("follow_on") or "") or None
                h, m = reviewmod.build_review(client, start=start, on=on,
                                              monthly_rial=monthly, setup_rial=setup,
                                              follow_on=follow_on)
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            left = reviewmod.days_left(start, on)
            _meter("review", f"برگهٔ جلسهٔ بازبینی برای {client or 'بدون نام'}")
            return self._json({"ok": True, "html": str(h), "md": str(m),
                               "client": client or None,
                               "start": reviewmod._parse(start).isoformat(),
                               "on": reviewmod._parse(on).isoformat(),
                               "review": reviewmod.review_day(start).isoformat(),
                               "days_left": left, "status": reviewmod.status_line(start, on),
                               "price_given": bool(monthly or setup),
                               "outcomes": [e["key"] for e in reviewmod.outcomes(monthly, setup)],
                               "gates": [g["want"] for g in reviewmod.gate_conditions()]})

        if u.path == "/api/onboarding":
            client = str((body or {}).get("client") or "")
            start = str((body or {}).get("start") or "") or None
            try:
                monthly = int((body or {}).get("monthly") or 0)
                setup = int((body or {}).get("setup") or 0)
                h, m = onbmod.build_onboarding(client, start=start, monthly_rial=monthly,
                                               setup_rial=setup)
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            day0 = onbmod._parse(start)
            review = (day0 + timedelta(days=onbmod.trial_days())).isoformat()
            _meter("onboarding", f"برگهٔ روز اول برای {client or 'بدون نام'}")
            return self._json({"ok": True, "html": str(h), "md": str(m),
                               "client": client or None, "start": day0.isoformat(),
                               "review": review, "trial_days": onbmod.trial_days(),
                               "price_given": bool(monthly or setup),
                               "gates": [g["want"] for g in onbmod.gate_conditions()]})

        if u.path == "/api/usage":
            action = str((body or {}).get("action") or "summary")
            if action == "statement":
                client = str((body or {}).get("client") or "________________")
                h, m = usagemod.build_statement(usagemod.summary(), client=client)
                return self._json({"ok": True, "html": str(h), "md": str(m),
                                   "summary": usagemod.summary()})
            return self._json({"ok": True, "summary": usagemod.summary(),
                               "chain": usagemod.verify_chain()})

        if u.path == "/api/witness":
            # برگهٔ شاهد زنده: عددها را همین حالا می‌خواند، هش پاسخ خام و ساعت را چاپ می‌کند.
            syms = [s_.strip() for s_ in str((body or {}).get("symbols") or "").split(",") if s_.strip()]
            try:
                doc = demoday.build(symbols=syms,
                                    timeout=float((body or {}).get("timeout") or 8.0))
            except Exception as e:                      # هیچ خطایی نباید صفحه را بشکند
                return self._json({"ok": False, "error": f"{type(e).__name__}: {e}"})
            _meter("witness", "برگهٔ شاهد زندهٔ داده")
            ok_count = len([p for p in doc["probes"] if p.get("ok")])
            return self._json({
                "ok": bool(ok_count), "summary": demoday.summary_line(doc),
                "probes_ok": ok_count, "probes_total": len(doc["probes"]),
                "ready": bool(doc["decision"].get("ready")),
                "note": doc["decision"].get("mixed_note", ""),
                "reason": doc["decision"].get("reason", ""),
                "page": doc.get("page", ""), "md": doc.get("md", ""),
                "hash": doc["page_hash"], "connection": doc["connection"]["label"],
            })

        if u.path == "/api/diagnose":
            rep = diagmod.collect(run_tests=not bool((body or {}).get("quick")))
            h, t = diagmod.build_report(rep)
            rep.update({"ok": bool(rep.get("ok")), "html": str(h), "text": str(t),
                        "summary": diagmod.summary_line(rep)})
            return self._json(rep)

        if u.path == "/api/judge":
            _meter("judge", "داوری سیگنال بیرونی")
            kind = str(body.get("kind") or "")
            params = body.get("params") or {}
            if isinstance(params, str):
                try:
                    params = json.loads(params or "{}")
                except json.JSONDecodeError:
                    return self._json({"error": "عددهای ورودی JSON درست نیستند."}, 400)
            res = judger.judge(
                kind, params,
                hurdle=float(body.get("hurdle") or judger.HURDLE_DEFAULT),
                capital=float(body.get("capital") or 100_000_000),
                margin_per_contract=float(body.get("margin") or 0),
                contracts=float(body.get("contracts") or 0),
                notional_per_contract=(float(body["notional"]) if body.get("notional") else None),
                maintenance=float(body.get("maintenance") or judger.MAINTENANCE_DEFAULT),
                current_price=(float(body["price"]) if body.get("price") else None),
                claimed_return_pct=(float(body["claimed"]) if body.get("claimed") else None))
            if res.get("ok") and body.get("sheet"):
                h, m = judger.build_sheet(res)
                res["sheet_html"], res["sheet_md"] = str(h), str(m)
            return self._json(res, 200 if res.get("ok") else 400)

        if u.path == "/api/investor/cases":
            return self._json({"ok": True, "cases": invtest.cases(reveal=bool(body.get("reveal")))})

        if u.path == "/api/investor/check":
            _meter("blind", "سنجش حدس سرمایه‌گذار")
            res = invtest.check(str(body.get("id") or ""), body.get("guess"))
            return self._json(res, 200 if res.get("ok") else 400)

        if u.path == "/api/investor/ladder":
            cfg = desk_config()
            doc = {}
            try:
                doc = laddermod.build(
                    capital=float(cfg.get("capital") or 20_000_000_000.0),
                    risk_pct=float(cfg.get("max_margin_pct") or 0.20),
                    margin_per_contract=float(cfg.get("margin_per_contract") or 2_000_000_000.0),
                    client=str((body or {}).get("client") or ""),
                    path_md=laddermod.LADDER_MD, path_json=laddermod.LADDER_JSON)
            except (OSError, ValueError, KeyError, ZeroDivisionError) as e:
                doc = {"counts": {}, "buy": [], "no_buy": [], "sizing": {},
                       "error": f"سند پلهٔ تصمیم ساخته نشد: {e}"}
            else:
                _meter("ladder", f"پلهٔ تصمیم: {doc['counts']['actionable']} ردیف قابل اجرا")
            return self._json({"ok": True, "ladder": invtest.strategy_table(),
                               "sizing": invtest.size_sensitivity(),
                               "doc": {"counts": doc.get("counts", {}),
                                       "md": doc.get("path_md", ""),
                                       "json": doc.get("path_json", ""),
                                       "verify": doc.get("verify", {}),
                                       "sizing_real": doc.get("sizing", {}),
                                       "titles": [e["title"] for e in doc.get("buy", [])],
                                       "no_buy_titles": [e["title"] for e in doc.get("no_buy", [])],
                                       "error": doc.get("error", "")}})

        if u.path == "/api/investor/reconcile":
            try:
                entry = float(body.get("entry"))
                exit_ = float(body.get("exit"))
            except (TypeError, ValueError):
                return self._json({"error": "قیمت ورود و خروج را عدد وارد کنید."}, 400)
            rec = invtest.reconcile(symbol=str(body.get("symbol") or "بدون‌نام"),
                                    entry=entry, exit=exit_,
                                    days=float(body.get("days") or 30),
                                    units=float(body.get("units") or 1),
                                    expected=(float(body["expected"])
                                                       if body.get("expected") not in (None, "") else None))
            invtest.append_log(rec)
            return self._json({"ok": True, **rec, "chain": invtest.verify_chain()})

        if u.path == "/api/investor/sheet":
            _meter("blind", "ساخت برگهٔ آزمون کور")
            try:
                out = invtest.build_sheet(client=str((body or {}).get("client") or ""))
            except (OSError, ValueError, FileNotFoundError) as e:
                return self._json({"error": f"ساخت برگه ناموفق: {e}"}, 500)
            return self._json({"ok": True, **out})

        if u.path == "/api/investor/verify":
            return self._json(invtest.verify_chain())

        if u.path == "/api/investor/blind":
            try:
                return self._json({"ok": True, "cases": invtest.cases(reveal=bool(body.get("reveal"))),
                                   "scorecard": invtest.scorecard(),
                                   "log_rows": len(invtest.read_log()),
                                   "verify": invtest.verify_chain(),
                                   "contract": str(invtest.PLEDGE_MD),
                                   "sheet": str(invtest.SHEET_HTML)})
            except (FileNotFoundError, OSError, ValueError, KeyError) as e:
                return self._json({"error": f"آزمون کور آماده نشد: {e}"}, 500)

        if u.path == "/api/investor/blind/check":
            case = str((body or {}).get("case") or "").strip()
            guess = (body or {}).get("guess")
            if not case or guess in (None, ""):
                return self._json({"error": "شمارهٔ پرسش و حدس سرمایه‌گذار لازم است."}, 400)
            try:
                res = invtest.judge(guess, str((body or {}).get("note") or ""), case_id=case,
                                    client=str((body or {}).get("client") or ""))
            except KeyError as e:
                return self._json({"error": str(e)}, 404)
            _meter("blind", f"حدس {case}: {guess}")
            return self._json({"ok": True, "status": res["status"], "delta_pct": res["delta_pct"],
                               "note": res["note"], "answer": invtest.answer_text(res["case"]),
                               "title": res["case"]["title"], "chain": res["record"]["chain"],
                               "scorecard": invtest.scorecard()})

        if u.path == "/api/investor/blind/sheet":
            try:
                out = invtest.build_sheet(client=str((body or {}).get("client") or ""))
            except (OSError, ValueError, FileNotFoundError) as e:
                return self._json({"error": f"ساخت برگه ناموفق: {e}"}, 500)
            _meter("blind", "برگهٔ آزمون کور سرمایه‌گذار")
            return self._json({"ok": True, **out})

        if u.path == "/api/investor/pledge":
            try:
                text = invtest.build_pledge(client=str((body or {}).get("client") or ""))
            except (OSError, ValueError) as e:
                return self._json({"error": f"ساخت پیمان‌نامه ناموفق: {e}"}, 500)
            _meter("pledge", "پیمان‌نامهٔ نمایش")
            return self._json({"ok": True, "path": str(invtest.PLEDGE_MD), "chars": len(text),
                               "verify": invtest.verify_chain()})

        if u.path == "/api/strategies/sheet":
            _meter("strategy", "جزوهٔ راهبردها + شوک‌آزمون")
            doc = stratmod.build(write=True)
            stress_doc = stressmod.build(write=True)
            return self._json({
                "ok": True, "md": doc.get("md"), "html": doc.get("html"), "refs": doc.get("refs"),
                "index": doc.get("index"), "table": doc["table"], "honesty": doc["honesty"],
                "stress_html": stress_doc.get("html"), "counts": stress_doc["counts"],
                "solid": stress_doc["solid"], "weak": stress_doc["weak"],
                "marginal": stress_doc.get("marginal"), "dead": stress_doc["dead"],
                "stress_rows": [{"title": r["title"], "annualized_pct": r["annualized_pct"],
                                 "survives_today": r["survives_today"],
                                 "resilience_pct": r["resilience_pct"],
                                 "first_failure": r["first_failure"],
                                 "min_margin_pp": r.get("min_margin_pp"),
                                 "neutral_matches_engine": r["neutral_matches_engine"],
                                 "annualized_matches_engine": True}
                                for r in stress_doc["rows"]],
            })

        if u.path == "/api/edge-stress/sheet":
            _meter("strategy", "شوک‌آزمون راهبردها")
            doc = stressmod.build(write=True)
            return self._json({"ok": True, "html": doc.get("html"), "md": doc.get("md"),
                               "counts": doc["counts"], "solid": doc["solid"],
                               "weak": doc["weak"], "marginal": doc.get("marginal"),
                               "dead": doc["dead"],
                               "rows": [{"title": r["title"], "annualized_pct": r["annualized_pct"],
                                         "survives_today": r["survives_today"],
                                         "resilience_pct": r["resilience_pct"],
                                         "first_failure": r["first_failure"],
                                         "fee_tolerance": (r.get("fee_tolerance") or {}).get("detail"),
                                         "margin": r.get("margin")}
                                        for r in doc["rows"]]})

        if u.path == "/api/bankroll/sheet":
            _meter("math", "ریاضیِ بقا و مسیر رشد")
            doc = bankmod.build(capital=float(body.get("capital") or 100_000_000.0),
                                target=(float(body["target"]) if body.get("target") else None),
                                win_prob=float(body.get("win_prob") or 0.55),
                                win_pct=float(body.get("win_pct") or 8.0),
                                loss_pct=float(body.get("loss_pct") or 5.0),
                                trials=int(body.get("trials") or bankmod.DEFAULT_TRIALS),
                                strategy_annualized_pct=float(body.get("strategy_pct") or 68.482),
                                churn_per_year=float(body.get("churn") or 1.0), write=True)
            return self._json({"ok": True, "html": doc.get("html"), "md": doc.get("md"),
                               "kelly": doc["kelly"], "sim": doc["sim"], "path": doc["path"],
                               "strategy_path": doc["strategy_path"], "checks": doc["checks"],
                               "breakeven": doc["breakeven"], "honesty": doc["honesty"],
                               "used_risk_fraction": doc["used_risk_fraction"],
                               "capital": doc["capital"], "target": doc["target"]})

        if u.path == "/api/selftest":
            _meter("exam", "اجرای آزمون ۱۰ دقیقه‌ای")
            result = selfcheck.run_all()
            report = selfcheck.build_report(result)
            sheet = selfcheck.build_exam_sheet(result)
            return self._json({"ok": result["summary"]["ok"], "summary": result["summary"],
                               "engine": result["engine"], "ran_at": result["ran_at"],
                               "duration_ms": result["duration_ms"],
                               "cases": [{"id": c["id"], "title": c["title"], "why": c["why"],
                                          "ok": c["ok"], "inputs": c["inputs"],
                                          "rows": c["rows"], "hand": c["hand"]}
                                         for c in result["cases"]],
                               "report": str(report), "exam": str(sheet)})

        if u.path == "/api/dossier":
            _meter("dossier", "ساخت پروندهٔ سرمایه‌گذار")
            paths = dossier_mod.build(STATE)
            return self._json({"ok": True, **paths})

        if u.path == "/api/trial/mark":
            if body.get("file_path"):
                STATE["file_path"] = body["file_path"]
            build_snapshot_for_state(allow_network=True, live_cfg=fresh_live_cfg())  # قیمت تازه، نه حافظهٔ کهنه
            res = run_scan()
            now_map = build_now_map(STATE.get("last_sigs") or [])
            t = trial.Trial(STATE["trial_db"])
            marked = t.mark(now_map)
            STATE["trial_last_mark"] = marked
            payload = trial_payload()
            payload["now_map"] = {k: v for k, v in now_map.items()}
            payload["marked_now"] = len(marked)
            payload["scan_counts"] = res.get("counts", {})
            return self._json(payload)

        if u.path == "/api/trial/daily":
            res = dailytrial.run_daily(
                mode=(body.get("mode") or ("live" if STATE["mode"] == "live" else "auto")),
                file_path=STATE.get("file_path"), live_cfg=STATE.get("live_cfg"),
                key=STATE.get("key"), rules=STATE["rules"], note=body.get("note", ""),
                add_span=float(body.get("add_span") or 0.0),
                use_kodal=bool(STATE.get("use_kodal")), db=STATE["trial_db"],
                report=GUI / "data" / "trial-report.html",
                log_path=GUI / "data" / "trial-daily.log",
                fallback_file=DESK_DIR / "market-demo.json",
                allow_network=not bool(body.get("offline")))
            snap = res.pop("snapshot_obj", None)
            if snap is not None:
                STATE["snapshot"] = snap
            res["trial"] = trial_payload()
            return self._json(res, 200 if res.get("ok") else 400)

        if u.path == "/api/trial/report":
            t = trial.Trial(STATE["trial_db"])
            html = t.write_report(GUI / "data" / "trial-report.html")
            csvp = t.write_csv(GUI / "data" / "trial-entries.csv")
            payload = trial_payload()
            payload.update({"ok": True, "html": str(html), "csv": str(csvp)})
            return self._json(payload)

        if u.path == "/api/trial/verify":
            t = trial.Trial(STATE["trial_db"])
            ok, msg = t.verify_chain()
            return self._json({"ok": ok, "message": msg})

        if u.path == "/api/mode":
            mode = body.get("mode", STATE["mode"])
            if mode not in ("sim", "file", "live"):
                return self._json({"error": "حالت ناشناخته"}, 400)
            STATE["mode"] = mode
            if mode == "sim":
                STATE["file_path"] = str(DESK_DIR / "market-demo.json")
            return self._json({"ok": True, "mode": mode})

        if u.path == "/api/rules":
            for k, v in (body or {}).items():
                if k in STATE["rules"]:
                    try:
                        STATE["rules"][k] = float(v)
                    except (TypeError, ValueError):
                        pass
            return self._json({"ok": True, "rules": STATE["rules"]})

        if u.path == "/api/template":
            kind = body.get("kind", "snapshot")
            if kind == "history":
                p = datafeed.write_history_template(DATA / "history-template.csv")
            else:
                p = datafeed.write_snapshot_template(DATA / "snapshot-template.json")
                STATE["file_path"] = str(p)
            return self._json({"path": str(p), "kind": kind})

        if u.path == "/api/test-data":
            STATE["mode"] = body.get("mode", STATE["mode"])
            if body.get("file_path"):
                STATE["file_path"] = body["file_path"]
            snap = build_snapshot_for_state(allow_network=True)
            return self._json(snapshot_payload(snap))

        if u.path == "/api/test-live":
            cfg = dict(STATE.get("live_cfg") or datafeed.DEFAULT_LIVE_CONFIG)
            incoming = {k: v for k, v in (body.get("live_cfg") or {}).items() if v not in ("", None)}
            cfg.update(incoming)               # هر فیلدی که در کادر پر شده باشد، جای پروفایل را می‌گیرد
            if not str(cfg.get("url_template", "")).strip():
                return self._json({"status": "failed", "rows": 0, "freshness": "—",
                                   "source_label": "تنظیم نشده",
                                   "messages": ["هیچ نشانی‌ای تنظیم نشده است: در گام ۲ یک پروفایل انتخاب کنید "
                                                "یا قالب نشانی سرویس را در کادر بگذارید."]}, 200)
            STATE["live_cfg"] = cfg
            STATE["key"] = body.get("key", "") or STATE.get("key", "")
            if body.get("file_path"):
                STATE["file_path"] = body["file_path"]
            STATE["mode"] = "live"
            snap = build_snapshot_for_state("live", allow_network=True)
            return self._json(snapshot_payload(snap))

        if u.path == "/api/run":
            _meter("run", "اجرای موتور روی داده")
            STATE["mode"] = body.get("mode", STATE["mode"])
            if body.get("file_path"):
                STATE["file_path"] = body["file_path"]
            if body.get("kodal_db"):
                STATE["kodal_db"] = body["kodal_db"]
            STATE["use_kodal"] = bool(body.get("use_kodal", STATE["use_kodal"]))
            if body.get("key"):
                STATE["key"] = body["key"]
            if body.get("live_cfg"):
                cfg = dict(STATE.get("live_cfg") or datafeed.DEFAULT_LIVE_CONFIG)
                cfg.update({k: v for k, v in body["live_cfg"].items() if v not in ("", None)})
                STATE["live_cfg"] = cfg
            if body.get("rules"):
                for k, v in body["rules"].items():
                    if k in STATE["rules"]:
                        STATE["rules"][k] = v
            # در حالت زنده هر بار قیمت تازه خوانده می‌شود؛ اسنپ‌شات کهنه هرگز جای دادهٔ زنده را نمی‌گیرد.
            if STATE["mode"] == "live" or STATE.get("snapshot") is None:
                build_snapshot_for_state(allow_network=True)
            return self._json(run_scan())

        if u.path == "/api/decide":
            result = decide(body.get("sid", ""), body.get("action", "approved"),
                            body.get("note", ""), bool(body.get("force")))
            return self._json(result, 200 if "error" not in result else 400)

        if u.path == "/api/backtest":
            path = body.get("path") or str(GUI / "demo" / "history-demo.csv")
            return self._json(do_backtest(path))

        if u.path == "/api/kodal/demo":
            cfg = json.loads(json.dumps(kodal.DEFAULT_CONFIG, ensure_ascii=False))
            cfg["db_path"] = str(KODAL_DIR / "data" / "demo.sqlite3")
            cfg["report_path"] = str(KODAL_DIR / "data" / "demo-report.html")
            store = kodal.Store(cfg["db_path"])
            items = kodal.run_pipeline(cfg, store, ["demo"])
            STATE["kodal_db"] = cfg["db_path"]
            return self._json({"items": [{"title": it.title, "symbol": it.symbol, "score": it.score,
                                          "direction": it.direction, "category": it.category} for it in items[:40]],
                               "kodal_db": cfg["db_path"], "count": len(items)})

        if u.path == "/api/bundle":
            _meter("bundle", "ساخت بستهٔ شاهد")
            return self._json(do_bundle())

        return self._json({"error": "مسیر ناشناخته"}, 404)


def start_mock_feed(port: int = 8788) -> bool:
    """خوراک آزمایشی محلی را در نخ جداگانه بالا می‌آورد (بدون هزینه، بدون اینترنت)."""
    try:
        httpd = mock_feed.serve(port)
    except OSError as e:
        print(f"خوراک آزمایشی محلی بالا نیامد ({e}) — اگر خودش جداگانه اجرا شده، اشکالی ندارد.")
        return False
    threading.Thread(target=httpd.serve_forever, daemon=True, name="mock-feed").start()
    print(f"خوراک آزمایشی محلی روی http://127.0.0.1:{port}/ آماده است (دادهٔ ساختگی، برای آزمایش).")
    return True


def serve(host: str, port: int, open_browser: bool = True, mock_feed_port: int | None = 8788) -> None:
    if mock_feed_port:
        start_mock_feed(mock_feed_port)
    active = apply_saved_connection()
    if active.get("name"):
        print(f"اتصال ذخیره‌شده فعال شد: {active.get('label')} (کلید: {active.get('key_where')})")
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"ایستگاه روی {url} آماده است. برای بستن، کلید Ctrl+C را بزنید.")
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nبسته شد.")
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="کارساز محلی ایستگاه (رابط گرافیکی مرورگری)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--mock-feed-port", type=int, default=8788,
                    help="درگاه خوراک آزمایشی محلی (۰ = خاموش)")
    ap.add_argument("--version", action="store_true")
    args = ap.parse_args(argv)
    if args.version:
        print(f"station-web {VERSION}")
        return 0
    serve(args.host, args.port, not args.no_browser, args.mock_feed_port or None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
