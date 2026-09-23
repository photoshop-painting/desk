#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""مراسم روزانه — یک دستور، تمام کارهای آزمون دو هفته‌ای.

منطق کار: هر روز کاری یک بار این برنامه را اجرا می‌کنید (یا ویندوز خودش اجرا می‌کند).
شش کار انجام می‌شود و هیچ‌کدام سفارش‌گذاری نیست:

  ۱. قیمت‌ها خوانده می‌شوند (زنده، یا پروندهٔ دستی، یا دادهٔ نمونه — با برچسب صادق).
  ۲. موتور ریاضی روی همان قیمت‌ها اجرا می‌شود.
  ۳. سیگنال‌های امروز در «دفتر آزمون زنده» ثبت می‌شوند (با زنجیرهٔ هش).
  ۴. ردیف‌های قبلی با قیمت‌های تازه بازسنجی می‌شوند.
  ۵. سالم‌بودن زنجیره بررسی و گزارش سرمایه‌گذار ساخته می‌شود.
  ۶. «کارنامه» به‌روز می‌شود: آیا سابقهٔ ثبت‌شده به‌قدری هست که خرید دادهٔ زنده و رفتن
     به جلسهٔ شرکت معنی داشته باشد، یا هنوز نه.

هر اجرا در `data/trial-daily.log` هم ثبت می‌شود تا روزها قابل شمارش باشند.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.1.0"
BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DESK_DIR = (BASE.parent / "desk").resolve()
KODAL_DIR = (BASE.parent / "kodal-alert").resolve()
LOG_FILE = DATA / "trial-daily.log"
REPORT_FILE = DATA / "trial-report.html"
RUNNING_SNAPSHOT = DATA / "current-snapshot.json"

for p in (str(BASE), str(DESK_DIR), str(KODAL_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import datafeed  # noqa: E402
import live_trial as trial  # noqa: E402

DEFAULT_RULES = {
    "capital": 20_000_000_000, "hurdle": 0.39,
    "min_edge_arbitrage_pct": 3.0, "min_edge_leveraged_pct": 5.0,
    "max_margin_pct": 0.20, "max_position_pct": 0.35, "max_positions": 3,
    "min_liquidity_contracts_per_day": 20, "max_spread_pct": 0.03,
    "max_plausible_arb_pct": 250.0, "max_plausible_lev_pct": 400.0,
}

SYNTHETIC_MARKS = ("ساختگی", "نمونهٔ همراه")
SYNTHETIC_PATH_MARKS = ("demo", "sample", "template", "نمونه", "قالب")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today() -> str:
    return time.strftime("%Y-%m-%d")


def is_synthetic(source_label: str) -> bool:
    """آیا این داده ساختگی است؟ برچسب منبع را می‌خوانیم، نه حدس را."""
    return any(m in str(source_label or "") for m in SYNTHETIC_MARKS)


def path_is_synthetic(path) -> bool:
    """پروندهٔ نمونه و قالب (مثل market-demo.json) دادهٔ واقعی حساب نمی‌شود.

    بی این سنجه، کسی می‌توانست با دادن پروندهٔ نمونه، روز «واقعی» جعل کند و کارنامه
    بی‌دلیل سبز شود.
    """
    if not path:
        return False
    name = str(path).replace("\\", "/").lower()
    base = name.rsplit("/", 1)[-1]
    if any(m in base for m in SYNTHETIC_PATH_MARKS):
        return True
    return any(part in ("demo", "samples", "templates") for part in name.split("/")[:-1])


def write_running_snapshot(snap, rules: dict, path: Path | str | None = None) -> Path:
    """اسنپ‌شات جاری را به قالب بازار میز معاملات می‌نویسد."""
    rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in snap.rows]
    out = Path(path or RUNNING_SNAPSHOT)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"as_of": time.strftime("%Y-%m-%d %H:%M"),
                               "hurdle": rules.get("hurdle", 0.39),
                               "capital": rules.get("capital", 20_000_000_000),
                               "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def scan_signals(market_path: Path | str, rules: dict, *, desk_db=None, kodal_db=None) -> list:
    """موتور میز معاملات را روی اسنپ‌شات اجرا می‌کند و سیگنال‌های خام را برمی‌گرداند."""
    import desk as deskmod
    cfg = dict(getattr(deskmod, "DEFAULT_CONFIG", {}))
    cfg.update({k: v for k, v in (rules or {}).items() if k in DEFAULT_RULES})
    if desk_db:
        cfg["desk_db"] = str(desk_db)
    desk_obj = deskmod.Desk(cfg.get("desk_db") or getattr(deskmod, "DEFAULT_DB"))
    return deskmod.scan_market(market_path, cfg, desk_obj, kodal_db)


def now_map_from_signals(sigs, rules: dict) -> dict:
    """حاشیهٔ امروز هر نماد، از سیگنال‌های تازه."""
    out: dict = {}
    for s in sigs or []:
        kind = getattr(s, "kind", "")
        floor = (rules.get("min_edge_arbitrage_pct", 3.0) if kind in ("basis", "arbitrage")
                 else rules.get("min_edge_leveraged_pct", 5.0))
        detail = getattr(s, "detail", {}) or {}
        out[str(getattr(s, "symbol", ""))] = {
            "expected_now": getattr(s, "annualized_pct", None),
            "floor": floor,
            "spot_now": detail.get("spot") or detail.get("stock_price"),
            "future_now": detail.get("future"),
        }
    return out


def pick_source(*, mode: str = "auto", file_path=None, live_cfg=None, key: str = "",
                allow_network: bool = True, fallback_file=None, progress=None) -> tuple[object, str, list[str]]:
    """منبع داده را انتخاب می‌کند: زنده (اگر تنظیم شده) ← پرونده ← نمونه. با برچسب صادق."""
    notes: list[str] = []

    def say(m: str) -> None:
        notes.append(m)
        if progress:
            progress(m)

    live_cfg = live_cfg or {}
    url_ok = bool(str(live_cfg.get("url_template", "")).strip())
    mode = (mode or "auto").lower()
    if mode in ("live", "auto") and url_ok and allow_network:
        snap = datafeed.build_snapshot("live", file_path=file_path, live_cfg=live_cfg, key=key,
                                       allow_network=True, progress=progress)
        if snap.status in ("ok", "partial") and snap.live_prices:
            say(f"منبع: {snap.source_label} · {snap.messages[-1] if snap.messages else ''}")
            return snap, "live", notes
        say(f"دادهٔ زنده نیامد ({snap.status})؛ به منبع پشتیبان می‌رویم.")
    if mode == "sim":
        snap = datafeed.demo_snapshot()
        say("منبع: دادهٔ نمونهٔ همراه برنامه (ساختگی).")
        return snap, "sim", notes
    path = file_path or fallback_file
    if path and Path(path).exists():
        snap = datafeed.load_snapshot_file(path)
        say(f"منبع: پروندهٔ دستی {Path(path).name} — تازگی: {snap.freshness_label}")
        return snap, "file", notes
    snap = datafeed.demo_snapshot()
    say("پرونده‌ای داده نشد؛ با دادهٔ نمونهٔ همراه برنامه (ساختگی) ادامه می‌دهیم.")
    return snap, "sim", notes


def run_daily(*, mode: str = "auto", file_path=None, live_cfg=None, key: str = "",
              rules: dict | None = None, note: str = "", db=None, report=None,
              allow_network: bool = True, use_kodal: bool = True, add_span: float = 0.0,
              fallback_file=None, desk_db=None, progress=None, log_path=None) -> dict:
    """مراسم یک روز. خروجی: خلاصهٔ کارهایی که انجام شد (برای نمایش و برای لاگ)."""
    rules = {k: (rules or {}).get(k, v) for k, v in DEFAULT_RULES.items()}
    notes: list[str] = []

    def say(m: str) -> None:
        notes.append(m)
        if progress:
            progress(m)

    errors: list[str] = []
    snap, used_mode, src_notes = pick_source(mode=mode, file_path=file_path, live_cfg=live_cfg,
                                             key=key, allow_network=allow_network,
                                             fallback_file=fallback_file, progress=progress)
    if not snap.rows:
        return {"ok": False, "errors": ["هیچ ردیفی برای محاسبه نیست؛ منبع داده را بررسی کنید."],
                "notes": notes, "handled": 0}

    market_path = write_running_snapshot(snap, rules)
    kodal_db = None
    if use_kodal:
        cand = KODAL_DIR / "data" / "demo.sqlite3"
        kodal_db = cand if cand.exists() else None
    try:
        sigs = scan_signals(market_path, rules, kodal_db=kodal_db, desk_db=desk_db)
    except Exception as e:                      # موتور نباید مراسم روزانه را بخواباند
        return {"ok": False, "errors": [f"محاسبه انجام نشد: {e}"], "notes": notes, "handled": 0}
    say(f"محاسبه انجام شد: {len(sigs)} ردیف.")

    t = trial.Trial(db or trial.DEFAULT_DB)
    saved = t.record_from_signals(sigs, source_label=snap.source_label, mode=used_mode,
                                  add_span=add_span)
    say(f"دفتر: {len(saved)} ردیف تازه ثبت شد (تکراری‌ها رد شدند).")
    marked = t.mark(now_map_from_signals(sigs, rules))
    say(f"دفتر: {len(marked)} ردیف با قیمت‌های امروز بازسنجی شد.")
    chain_ok, chain_msg = t.verify_chain()
    say(("زنجیرهٔ هش سالم است." if chain_ok else f"هشدار زنجیره: {chain_msg}"))

    report_path = t.write_report(report or REPORT_FILE)
    csv_path = t.write_csv(DATA / "trial-entries.csv")
    summary = t.summary()

    used_file = None
    if used_mode == "file":
        candidate = file_path or fallback_file
        used_file = str(candidate) if candidate else None
    unconfirmed = bool(used_file) and not datafeed.snapshot_confirmed(used_file)
    synthetic = (is_synthetic(getattr(snap, "source_label", ""))
                 or path_is_synthetic(used_file) or unconfirmed)
    rec = {
        "ts": _now(), "date": today(), "mode": used_mode,
        "source": getattr(snap, "source_label", ""),
        "data_file": (Path(used_file).name if used_file else ""),
        "confirmed_file": (datafeed.snapshot_confirmed(used_file) if used_file else False),
        "synthetic": synthetic,
        "rows": len(snap.rows), "signals": len(sigs), "recorded": len(saved),
        "marked": len(marked), "entries": summary["entries"], "chain_ok": chain_ok,
        "note": note, "report": str(report_path),
    }
    append_log(rec, log_path)                 # مسیر لاگ را می‌شود داد تا آزمون‌ها به دفتر واقعی دست نزنند
    score = scorecard(t, log_records=read_log(log_path))
    return {"ok": True, "notes": notes, "errors": errors, "record": rec, "summary": summary,
            "scorecard": score, "report": str(report_path), "csv": str(csv_path),
            "handled": len(saved), "source_label": getattr(snap, "source_label", ""),
            "synthetic": rec["synthetic"], "market_path": str(market_path),
            "snapshot_obj": snap, "signals": len(sigs)}


# ---------------------------------------------------------------- لاگ روزانه
def append_log(rec: dict, path: Path | str | None = None) -> Path:
    """هر اجرا یک خط؛ مسیر پیش‌فرض در لحظهٔ اجرا خوانده می‌شود تا آزمون‌پذیر باشد."""
    path = Path(path or LOG_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def read_log(path: Path | str | None = None) -> list[dict]:
    path = Path(path or LOG_FILE)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


# ---------------------------------------------------------------- کارنامه
def scorecard(t=None, *, log_records=None, log_path=None, target_days: int = 10,
              target_real_days: int = 5, min_marked_ratio: float = 0.6, min_moves: int = 3) -> dict:
    """آیا سابقهٔ ثبت‌شده به‌قدر کافی هست؟ پنج شرط، همه با عدد، هیچ شرط سلیقه‌ای."""
    t = t or trial.Trial()
    summary = t.summary()
    log_records = read_log(log_path) if log_records is None else log_records
    days = sorted({r.get("date") for r in log_records if r.get("date") and r.get("chain_ok", True)})
    real_days = sorted({r["date"] for r in log_records
                        if r.get("date") and not r.get("synthetic", True)})
    marks = t.latest_marks()
    deltas = [m["delta_pp"] for m in marks.values() if isinstance(m.get("delta_pp"), (int, float))]
    moved = [d for d in deltas if abs(d) >= 1.0]
    up = [d for d in deltas if d >= 1.0]
    down = [d for d in deltas if d <= -1.0]
    entries = summary.get("entries", 0)
    marked = summary.get("marked", 0)
    marked_ratio = (marked / entries) if entries else 0.0

    criteria = [
        {"key": "days", "name": "تداوم روزانه (روزهای ثبت‌شده)",
         "have": len(days), "want": target_days, "ok": len(days) >= target_days,
         "hint": "هر روز کاری یک بار «مراسم امروز» را اجرا کنید."},
        {"key": "real_days", "name": "روزهای با دادهٔ واقعی (نه ساختگی)",
         "have": len(real_days), "want": target_real_days, "ok": len(real_days) >= target_real_days,
         "hint": "خوراک آزمایشی برای تمرین است؛ برای ارائه به شرکت روزهای واقعی لازم است."},
        {"key": "marked", "name": "سهم بازسنجی‌شدهٔ دفتر",
         "have": round(marked_ratio, 3), "want": min_marked_ratio, "ok": marked_ratio >= min_marked_ratio,
         "hint": "بازسنجی نشان می‌دهد موتور با قیمت‌های تازه هم اجرا می‌شود."},
        {"key": "moves", "name": "حرکت واقعی در دفتر (بازتر و بسته)",
         "have": {"moved": len(moved), "up": len(up), "down": len(down)},
         "want": {"moved": min_moves, "up": 1, "down": 1},
         "ok": len(moved) >= min_moves and len(up) >= 1 and len(down) >= 1,
         "hint": "هم فرصت تازه لازم است، هم فرصتی که بسته شده؛ هر دو نشانهٔ درست‌کاری است."},
        {"key": "chain", "name": "زنجیرهٔ هش سالم",
         "have": bool(summary.get("chain_ok")), "want": True, "ok": bool(summary.get("chain_ok")),
         "hint": "اگر زنجیره بشکند، یعنی ردیفی دست‌کاری شده؛ تا پیدا نشود به دفتر استناد نکنید."},
    ]
    ready = all(c["ok"] for c in criteria)
    missing = [c for c in criteria if not c["ok"]]
    if ready:
        verdict = ("آماده: سابقهٔ ثبت‌شده کافی است. حالا خرید دادهٔ زنده و بردن گزارش دفتر به شرکت معنی دارد.")
    else:
        verdict = ("هنوز نه: " + " · ".join(
            f"{c['name']} ({c['have']} از {c['want']})" for c in missing[:2]) +
            " — بعد از انجام، همین دکمه را دوباره بزنید.")
    return {"ready": ready, "criteria": criteria, "verdict": verdict,
            "days": len(days), "real_days": len(real_days),
            "moved": len(moved), "up": len(up), "down": len(down),
            "marked_ratio": round(marked_ratio, 3), "entries": entries, "marked": marked,
            "last_run": (log_records[-1].get("ts") if log_records else None),
            "runs": len(log_records)}


def status_text(score: dict) -> str:
    lines = ["کارنامهٔ آزمون دو هفته‌ای:"]
    for c in score["criteria"]:
        mark = "✓" if c["ok"] else "✗"
        lines.append(f"  {mark} {c['name']}: {c['have']} (لازم: {c['want']}) — {c['hint']}")
    lines.append("  " + ("آماده" if score["ready"] else "ناتمام"))
    lines.append("  " + score["verdict"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="مراسم روزانهٔ آزمون زندهٔ ایستگاه")
    ap.add_argument("--mode", default="auto", choices=("auto", "live", "file", "sim"))
    ap.add_argument("--file", dest="file_path", help="پروندهٔ اسنپ‌شات دستی")
    ap.add_argument("--note", default="", help="یادداشت امروز")
    ap.add_argument("--status", action="store_true", help="فقط کارنامه را نشان بده")
    ap.add_argument("--report", action="store_true", help="فقط گزارش سرمایه‌گذار را بساز")
    ap.add_argument("--add-span", type=float, default=0.0, help="کاهش/افزایش انتظار (واحد درصد)")
    ap.add_argument("--version", action="store_true")
    ap.add_argument("--reset", action="store_true",
                    help="پاک‌کردن دفتر و لاگ برای شروع دوباره (نیازمند --yes)")
    ap.add_argument("--yes", action="store_true", help="تأیید پاک‌کردن")
    args = ap.parse_args(argv)
    if args.version:
        print(f"daily-trial {VERSION}")
        return 0
    if args.reset:
        if not args.yes:
            print("برای پاک‌کردن دفتر، این را با --yes اجرا کنید: python daily_trial.py --reset --yes")
            return 1
        removed = []
        for path in (trial.DEFAULT_DB, LOG_FILE, DATA / "trial-entries.csv", REPORT_FILE):
            if Path(path).exists():
                Path(path).unlink()
                removed.append(Path(path).name)
        print("پاک شد: " + ("، ".join(removed) or "چیزی برای پاک‌کردن نبود"))
        print("یادآوری: دفتر آزمون پاک شد؛ ردیف‌های قبلی قابل بازگشت نیستند.")
        return 0

    if args.report:
        t = trial.Trial()
        print(t.write_report(REPORT_FILE))
        print(t.write_csv(DATA / "trial-entries.csv"))
        return 0
    if args.status:
        print(status_text(scorecard()))
        return 0

    import connections as conn
    live_cfg, key = {}, ""
    active = conn.active_or_none()
    if active:
        live_cfg, key = active["live_cfg"], active["key"]
    rules_path = BASE / "config" / "daily-rules.json"
    rules = DEFAULT_RULES
    if rules_path.exists():
        try:
            rules = {**DEFAULT_RULES, **json.loads(rules_path.read_text(encoding="utf-8"))}
        except Exception:
            rules = DEFAULT_RULES
    res = run_daily(mode=args.mode, file_path=args.file_path, live_cfg=live_cfg, key=key,
                    rules=rules, note=args.note, add_span=args.add_span,
                    fallback_file=DESK_DIR / "market-demo.json", progress=lambda m: print("· " + m))
    if not res["ok"]:
        for e in res["errors"]:
            print("خطا: " + e)
        return 2
    r = res["record"]
    print(f"\nامروز ({r['date']}): منبع {r['source'] or '—'} · "
          f"{'ساختگی' if r['synthetic'] else 'واقعی'} · ردیف {r['rows']} · ثبت {r['recorded']} · "
          f"بازسنجی {r['marked']}")
    print("گزارش: " + res["report"])
    print()
    print(status_text(res["scorecard"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
