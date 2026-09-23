#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""دفتر آزمون زنده — «برنامه چه گفت، بازار چه کرد».

این پرونده سه کار می‌کند و هیچ‌کدام ادعای سود نیست:

۱) **ثبت**: هر سیگنالی که موتور می‌سازد، با ساعت دقیق، قیمت‌های همان لحظه، نرخ سد و همهٔ
   ورودی‌های ریاضی، در یک دفتر می‌نشیند. این دفتر پاک نمی‌شود و بازنویسی نمی‌شود.
۲) **بازسنجی**: وقتی دوباره قیمت‌ها را می‌خوانید، همان موتور روی قیمت‌های تازه اجرا می‌شود و
   دفتر می‌گوید «حاشیهٔ آن سیگنال امروز چقدر است» — یعنی فرصت بازتر شد، بسته شد، یا زیر کف رفت.
۳) **زنجیرهٔ هش**: هر ثبت، هشِ ثبت قبلی را در خود دارد. اگر کسی بعداً یک ردیف را دست‌کاری یا
   حذف کند، زنجیره می‌شکند و گزارش همان را نشان می‌دهد. این «اثبات دست‌کاری‌ناپذیری مطلق» نیست،
   ولی برای ممیزی داخلی شرکت کافی است: تاریخ و ترتیب ثبت‌ها قابل بازسازی است.

چرا این مهم است؟ چون ارزش برنامه را با حرف نمی‌شود ثابت کرد، با سابقهٔ ثبت‌شده ثابت می‌شود.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

VERSION = "0.1.0"
BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DEFAULT_DB = DATA / "trial.sqlite3"
DEFAULT_REPORT = DATA / "trial-report.html"
CREDIT = ("✍️ تهیه‌کنندهٔ جزوات: Masoud Mojarabian · 📱 [+989126630554](tel:+989126630554) · "
          "✈️ [Telegram: Mojarabian](https://t.me/Mojarabian) · "
          "📸 [Instagram: Mojarabian.Art](https://instagram.com/Mojarabian.Art)")

CORE_FIELDS = ("ts", "symbol", "kind", "decision", "expected", "note", "legs",
               "source_label", "mode")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(payload: dict, prev_hash: str) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev_hash + "|" + body).encode("utf-8")).hexdigest()


class Trial:
    """دفتر آزمون زنده روی sqlite؛ سبک، بدون وابستگی بیرونی."""

    def __init__(self, db_path: str | Path = DEFAULT_DB):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    # ---------- پایه
    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _use(self):
        """پیوند sqlite را می‌سازد، کار را انجام می‌دهد و همیشه می‌بندد (بی‌هشدار)."""
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init(self) -> None:
        with self._use() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT, symbol TEXT, kind TEXT, decision TEXT, expected REAL,
                note TEXT, legs TEXT, source_label TEXT, mode TEXT,
                prev_hash TEXT, hash TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS marks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER, ts TEXT, expected_now REAL, floor REAL,
                spot_now REAL, future_now REAL, delta_pp REAL, status TEXT)""")

    # ---------- ثبت
    def _last_hash(self, conn: sqlite3.Connection) -> str:
        row = conn.execute("SELECT hash FROM entries ORDER BY id DESC LIMIT 1").fetchone()
        return row["hash"] if row else "GENESIS"

    def record(self, items: list[dict], *, source_label: str = "", mode: str = "",
               dedupe_hours: float = 1.0) -> list[dict]:
        """سیگنال‌ها را ثبت می‌کند. هر آیتم: symbol, kind, expected, decision, note, legs."""
        saved: list[dict] = []
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(0.0, dedupe_hours))).isoformat(timespec="seconds")
        with self._use() as c:
            prev = self._last_hash(c)
            for it in items:
                symbol = str(it.get("symbol", "")).strip()
                kind = str(it.get("kind", "")).strip()
                decision = str(it.get("decision", "recorded")).strip()
                if not symbol or not kind:
                    continue
                if dedupe_hours:
                    dup = c.execute("""SELECT id FROM entries WHERE symbol=? AND kind=? AND decision=? AND ts>=?
                                       ORDER BY id DESC LIMIT 1""",
                                    (symbol, kind, decision, cutoff)).fetchone()
                    if dup:
                        continue
                expected = it.get("expected")
                try:
                    expected = float(expected) if expected is not None else None
                except (TypeError, ValueError):
                    expected = None
                payload = {
                    "ts": _now(), "symbol": symbol, "kind": kind, "decision": decision,
                    "expected": expected, "note": str(it.get("note", "") or ""),
                    "legs": it.get("legs") or {}, "source_label": str(source_label or ""),
                    "mode": str(mode or ""),
                }
                h = digest({k: payload[k] for k in CORE_FIELDS}, prev)
                cur = c.execute("""INSERT INTO entries (ts, symbol, kind, decision, expected, note, legs,
                                   source_label, mode, prev_hash, hash)
                                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                                (payload["ts"], symbol, kind, decision, expected, payload["note"],
                                 json.dumps(payload["legs"], ensure_ascii=False), payload["source_label"],
                                 payload["mode"], prev, h))
                payload["id"] = int(cur.lastrowid)
                payload["hash"] = h
                payload["prev_hash"] = prev
                prev = h
                saved.append(payload)
        return saved

    def record_from_signals(self, signals: list, *, source_label: str = "", mode: str = "",
                            add_span: float = 0.0) -> list[dict]:
        """از فهرست سیگنال‌های میز معاملات، ردیف‌های دفتر را می‌سازد.

        add_span: چند واحد درصد به بازده انتظاری اضافه شود؟ (حاشیهٔ موتور + اسپرد اجرا)
        """
        items = []
        for s in signals:
            expected = getattr(s, "annualized_pct", None)
            if not isinstance(expected, (int, float)):
                continue
            legs = {"score_pp": getattr(s, "score_pp", None)}
            detail = getattr(s, "detail", {}) or {}
            for k in ("spot", "future", "strike", "premium", "stock_price", "put_price",
                      "days", "hurdle", "buy_fee_pct", "sell_fee_pct"):
                if k in detail:
                    legs[k] = detail[k]
            items.append({"symbol": getattr(s, "symbol", ""), "kind": getattr(s, "kind", ""),
                          "expected": round(float(expected) + float(add_span), 4),
                          "decision": getattr(s, "status", "recorded"),
                          "note": (getattr(s, "gate_note", "") or ""), "legs": legs})
        return self.record(items, source_label=source_label, mode=mode)

    # ---------- خواندن
    def all(self, limit: int = 500) -> list[dict]:
        with self._use() as c:
            rows = c.execute("SELECT * FROM entries ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["legs"] = json.loads(d.get("legs") or "{}")
            except Exception:
                d["legs"] = {}
            out.append(d)
        return out

    def count(self) -> int:
        with self._use() as c:
            return int(c.execute("SELECT COUNT(*) AS n FROM entries").fetchone()["n"])

    def verify_chain(self) -> tuple[bool, str]:
        with self._use() as c:
            rows = c.execute("SELECT * FROM entries ORDER BY id").fetchall()
        prev = "GENESIS"
        for r in rows:
            payload = {k: (json.loads(r["legs"]) if k == "legs" else r[k]) for k in CORE_FIELDS}
            if r["legs"] and not isinstance(payload["legs"], dict):
                payload["legs"] = {}
            want = digest(payload, prev)
            if r["prev_hash"] != prev:
                return False, f"زنجیره در ردیف {r['id']} شکسته است: پیوند قبلی جور نیست."
            if r["hash"] != want:
                return False, f"زنجیره در ردیف {r['id']} شکسته است: محتوا با هش ثبت‌شده نمی‌خواند."
            prev = r["hash"]
        return True, f"زنجیرهٔ {len(rows)} ثبت سالم است."

    # ---------- بازسنجی
    def mark(self, now_map: dict[str, dict]) -> list[dict]:
        """حاشیهٔ امروز هر نماد را با حاشیهٔ روز ثبت مقایسه می‌کند.

        now_map: {نماد: {"expected_now": عدد یا None, "floor": عدد, "spot_now": …, "future_now": …}}
        """
        out: list[dict] = []
        stamps = _now()
        with self._use() as c:
            for e in self.all(limit=1000):
                info = now_map.get(str(e["symbol"]))
                if not info:
                    continue
                now_val = info.get("expected_now")
                floor = info.get("floor")
                delta = None
                if isinstance(now_val, (int, float)) and isinstance(e.get("expected"), (int, float)):
                    delta = float(now_val) - float(e["expected"])
                if not isinstance(now_val, (int, float)):
                    status = "دادهٔ تازه نبود"
                elif isinstance(floor, (int, float)) and now_val < float(floor):
                    status = "زیر کف رفت"
                elif delta is None:
                    status = "بدون مقایسه"
                elif delta <= -1.0:
                    status = "کم شد"
                elif delta >= 1.0:
                    status = "بازتر شد"
                else:
                    status = "تقریباً ثابت"
                c.execute("""INSERT INTO marks (entry_id, ts, expected_now, floor, spot_now,
                             future_now, delta_pp, status) VALUES (?,?,?,?,?,?,?,?)""",
                          (e["id"], stamps, now_val if isinstance(now_val, (int, float)) else None,
                           floor if isinstance(floor, (int, float)) else None,
                           info.get("spot_now"), info.get("future_now"), delta, status))
                row = dict(e)
                row.update({"expected_now": now_val, "delta_pp": delta, "status_now": status,
                            "marked_at": stamps})
                out.append(row)
        return out

    def latest_marks(self) -> dict[int, dict]:
        with self._use() as c:
            rows = c.execute("""SELECT m.* FROM marks m JOIN
                                (SELECT entry_id, MAX(id) AS mid FROM marks GROUP BY entry_id) t
                                ON m.id = t.mid""").fetchall()
        return {int(r["entry_id"]): dict(r) for r in rows}

    def summary(self) -> dict:
        entries = self.all(limit=5000)
        marks = self.latest_marks()
        with_marks = [e for e in entries if e["id"] in marks]
        deltas = [marks[e["id"]]["delta_pp"] for e in with_marks if marks[e["id"]]["delta_pp"] is not None]
        buckets: dict[str, int] = {}
        for e in with_marks:
            buckets[marks[e["id"]]["status"]] = buckets.get(marks[e["id"]]["status"], 0) + 1
        ok, chain_msg = self.verify_chain()
        return {
            "entries": len(entries),
            "marked": len(with_marks),
            "unmarked": len(entries) - len(with_marks),
            "avg_expected": (sum(e["expected"] for e in entries if isinstance(e["expected"], (int, float)))
                             / len([e for e in entries if isinstance(e["expected"], (int, float))]))
            if any(isinstance(e["expected"], (int, float)) for e in entries) else None,
            "avg_delta_pp": (sum(deltas) / len(deltas)) if deltas else None,
            "best_delta_pp": max(deltas) if deltas else None,
            "worst_delta_pp": min(deltas) if deltas else None,
            "buckets": buckets,
            "chain_ok": ok, "chain_message": chain_msg,
            "first_ts": entries[-1]["ts"] if entries else None,
            "last_ts": entries[0]["ts"] if entries else None,
        }

    # ---------- گزارش
    def write_csv(self, path: str | Path = DATA / "trial-entries.csv") -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        marks = self.latest_marks()
        cols = ["id", "ts", "symbol", "kind", "decision", "expected", "expected_now", "delta_pp",
                "status_now", "marked_at", "note", "source_label", "hash"]
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["شناسه", "زمان ثبت", "نماد", "راهبرد", "تصمیم", "انتظار در ثبت (٪)",
                        "انتظار امروز (٪)", "تغییر (واحد درصد)", "وضعیت بازسنجی", "زمان بازسنجی",
                        "یادداشت", "منبع داده", "هش"])
            for e in self.all(limit=5000):
                m = marks.get(e["id"], {})
                w.writerow([e["id"], e["ts"], e["symbol"], e["kind"], e["decision"], e["expected"],
                            m.get("expected_now"), m.get("delta_pp"), m.get("status", ""),
                            m.get("ts", ""), e["note"], e["source_label"], e["hash"]])
            w.writerow(cols)                       # نام ستون‌های فنی برای مصرف برنامه‌ای
        return path

    def write_report(self, path: str | Path = DEFAULT_REPORT) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        s = self.summary()
        marks = self.latest_marks()
        entries = self.all(limit=5000)

        def fa(x, nd=2):
            return "—" if not isinstance(x, (int, float)) else f"{x:,.{nd}f}"

        rows = []
        for e in entries:
            m = marks.get(e["id"], {})
            delta = m.get("delta_pp")
            color = "#0a7d33" if isinstance(delta, (int, float)) and delta >= 1 else (
                "#b3261e" if isinstance(delta, (int, float)) and delta <= -1 else "#6b7280")
            rows.append(
                f"<tr><td class='hint'>{e['id']}</td><td class='hint'>{e['ts']}</td>"
                f"<td>{e['symbol']}</td><td>{e['kind']}</td><td>{e['decision']}</td>"
                f"<td class='num'>{fa(e['expected'])}</td><td class='num'>{fa(m.get('expected_now'))}</td>"
                f"<td class='num' style='color:{color};font-weight:bold'>{fa(delta)}</td>"
                f"<td>{m.get('status', 'بازسنجی‌نشده')}</td>"
                f"<td class='hint'>{(e['source_label'] or '—')}</td>"
                f"<td class='hint' style='direction:ltr;font-size:10.5px'>{e['hash'][:16]}…</td></tr>")
        buckets = " · ".join(f"{k}: {v}" for k, v in sorted(s["buckets"].items())) or "—"
        html = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>دفتر آزمون زندهٔ ایستگاه</title>
<style>
 body {{ margin:0; background:#f6f7f9; color:#1d1d1f; font-family:Tahoma,"Segoe UI",sans-serif; line-height:1.9; }}
 .wrap {{ max-width:1120px; margin:0 auto; padding:22px; }}
 header {{ background:#0b3d2e; color:#fff; padding:14px 18px; border-radius:10px; }}
 h1 {{ font-size:19px; margin:0 0 4px; }} h2 {{ font-size:16px; margin:22px 0 8px; }}
 .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(165px,1fr)); gap:9px; margin:12px 0; }}
 .kpi {{ background:#fff; border:1px solid #e3e6ea; border-radius:10px; padding:9px 11px; }}
 .kpi .k {{ font-size:11.5px; color:#6b7280; }} .kpi .v {{ font-size:16px; font-weight:bold; }}
 table {{ width:100%; border-collapse:collapse; background:#fff; font-size:12.5px; }}
 th,td {{ border-bottom:1px solid #e3e6ea; padding:6px 8px; text-align:right; }}
 th {{ background:#eef2f7; font-size:12px; }} td.num {{ font-variant-numeric:tabular-nums; }}
 .ok {{ background:#e7f6ec; border:1px solid #b7e0c6; color:#0a5c2a; padding:9px 11px; border-radius:9px; font-size:13px; }}
 .bad {{ background:#fdecea; border:1px solid #f3c3bd; color:#8a1c14; padding:9px 11px; border-radius:9px; font-size:13px; }}
 .warn {{ background:#fff8e1; border:1px solid #f0e0a8; border-radius:9px; padding:10px 12px; font-size:13px; }}
 .credit {{ font-size:12.5px; color:#4b5563; margin-top:18px; border-top:1px solid #e3e6ea; padding-top:10px; }}
 a {{ color:#0b3d2e; }}
</style></head><body><div class="wrap">
<header><h1>دفتر آزمون زنده — «برنامه چه گفت، بازار چه کرد»</h1>
<div style="font-size:12.5px;opacity:.92">هر ثبت با ساعت دقیق و هشِ زنجیره‌ای ذخیره شده است؛
این پرونده برای نشان‌دادن به سرمایه‌گذار ساخته می‌شود، نه برای وعدهٔ سود.</div></header>

<div class="cards">
  <div class="kpi"><div class="k">ثبت‌ها</div><div class="v">{s['entries']}</div></div>
  <div class="kpi"><div class="k">بازسنجی‌شده</div><div class="v">{s['marked']}</div></div>
  <div class="kpi"><div class="k">میانگین انتظار در ثبت (٪)</div><div class="v">{fa(s['avg_expected'])}</div></div>
  <div class="kpi"><div class="k">میانگین تغییر (واحد درصد)</div><div class="v">{fa(s['avg_delta_pp'])}</div></div>
  <div class="kpi"><div class="k">بهترین تغییر</div><div class="v">{fa(s['best_delta_pp'])}</div></div>
  <div class="kpi"><div class="k">بدترین تغییر</div><div class="v">{fa(s['worst_delta_pp'])}</div></div>
</div>

<h2>وضعیت زنجیرهٔ ثبت</h2>
<div class="{'ok' if s['chain_ok'] else 'bad'}">{s['chain_message']}
{'— هیچ ردیفی دست‌کاری نشده است.' if s['chain_ok'] else '— به این دفتر اعتماد نکنید تا علت پیدا شود.'}</div>

<h2>خلاصهٔ بازسنجی</h2>
<div class="warn">{buckets}<br>
بازهٔ ثبت‌ها: از {s['first_ts'] or '—'} تا {s['last_ts'] or '—'}<br>
«انتظار» یعنی بازده سالانهٔ انتظاری موتور در لحظهٔ ثبت؛ «تغییر» یعنی همین عدد امروز چقدر است.
عدد منفی یعنی فرصت بسته شده — این عادی و درست است؛ فرصت ریاضی به‌سرعت توسط بازار برداشته می‌شود.</div>

<h2>ردیف‌های دفتر</h2>
<table><thead><tr><th>#</th><th>زمان ثبت</th><th>نماد</th><th>راهبرد</th><th>تصمیم</th>
<th class="num">انتظار در ثبت</th><th class="num">انتظار امروز</th><th class="num">تغییر</th>
<th>وضعیت</th><th>منبع داده</th><th>هش</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan="11">هنوز چیزی ثبت نشده است.</td></tr>'}</tbody></table>

<h2>چه چیزی این گزارش نیست</h2>
<div class="warn">این گزارش «سود تحقق‌یافته» نیست. عددها بازده سالانهٔ <b>انتظاری</b> موتور در تاریخ‌های
مختلف‌اند و تغییر آن‌ها نشان می‌دهد فرصت بازتر شده یا بسته. برای سود تحقق‌یافته، فایل معاملات واقعی
کارگزاری لازم است. هیچ‌جای این دفتر عددی دست‌کاری یا بازنویسی نمی‌شود؛ اگر عددی اشتباه وارد شده باشد،
ردیف جدید ثبت می‌شود و ردیف قدیمی با یادداشت اصلاح باقی می‌ماند.</div>

<div class="credit">{CREDIT}</div>
</div></body></html>"""
        path.write_text(html, encoding="utf-8")
        return path


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="دفتر آزمون زنده")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--report", action="store_true", help="ساخت گزارش HTML")
    ap.add_argument("--csv", action="store_true", help="ساخت CSV")
    ap.add_argument("--verify", action="store_true", help="بررسی زنجیرهٔ هش")
    args = ap.parse_args(argv)
    t = Trial(args.db)
    if args.verify:
        ok, msg = t.verify_chain()
        print(("✓ " if ok else "✗ ") + msg)
    if args.report:
        print(t.write_report())
    if args.csv:
        print(t.write_csv())
    if not (args.report or args.csv or args.verify):
        s = t.summary()
        print(json.dumps(s, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
