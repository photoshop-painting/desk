#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""میز معاملات (دستیار تصمیم با تأیید انسان) — نسخهٔ ۰٫۱٫۰

این برنامه سه کار می‌کند:
  ۱. دادهٔ بازار (اسنپ‌شات JSON) را روی موتور ریاضی مشتقه می‌گذارد.
  ۲. هشدارهای «دیده‌بان کدال» را به سیگنال‌های ریاضی می‌چسباند.
  ۳. بستهٔ سفارش آماده می‌کند تا **انسان** آن را در سامانهٔ کارگزاری اجرا کند.

هیچ سفارشی از این برنامه ارسال نمی‌شود. علت: معاملات الگوریتمی خودکار در
بورس و فرابورس ایران، طبق ابلاغیهٔ مهر ۱۳۹۹ سازمان بورس، «تا اطلاع ثانوی» ممنوع است.

دستورها:
  python desk.py selftest
  python desk.py run --market market-demo.json --kodal-db ../kodal-alert/data/demo.sqlite3
  python desk.py list --status pending
  python desk.py approve 3f2a... --note "ریسک پذیرفته شد"
  python desk.py reject 3f2a... --note "نقدشوندگی کم"
  python desk.py packet 3f2a...
"""
from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.1.0"
BASE = Path(__file__).resolve().parent
DEFAULT_DB = BASE / "data" / "desk.sqlite3"
DEFAULT_REPORT = BASE / "data" / "dashboard.html"
SCOUT_PATH = (BASE.parent / "tools" / "derivatives_scout.py").resolve()
CREDIT = ("تهیه‌کننده: Masoud Mojarabian · https://www.instagram.com/Mojarabian.Art/ · "
          "tel:+989126630554 · https://t.me/Mojarabian")

DEFAULT_CONFIG: dict = {
    "capital": 5_000_000_000,
    "hurdle": 0.39,
    "min_edge_arbitrage_pct": 3.0,
    "min_edge_leveraged_pct": 5.0,
    "max_margin_pct": 0.20,
    "max_positions": 3,
    "max_position_pct": 0.35,
    "min_liquidity_contracts_per_day": 20,
    "max_spread_pct": 0.03,
    "alert_score_threshold": 60,
    "max_plausible_arb_pct": 250.0,      # سقف باورپذیری بازده سالانهٔ راهبردهای آربیتراژی
    "max_plausible_lev_pct": 400.0,      # سقف باورپذیری بازده سالانهٔ راهبردهای اهرمی
    "desk_db": "",
    "report_path": "",
    "credit": CREDIT,
    "report_title": "میز معاملات — داشبورد تصمیم",
}

# ---------------------------------------------------------------- دسترسی به موتور ریاضی
_SCOUT_CACHE: dict[str, object] = {}


def load_scout(path: Path = SCOUT_PATH):
    """موتور ریاضی مشتقه را از پروندهٔ همسایه بارگذاری می‌کند (بدون نصب بسته).

    نتیجه در حافظه می‌ماند: بی این کش، پس‌آزمایی هر سطر یک بار کل موتور را از نو
    بارگذاری می‌کرد و صد سطر تاریخ چند ثانیه طول می‌کشید.
    """
    key = str(Path(path).resolve())
    cached = _SCOUT_CACHE.get(key)
    if cached is not None:
        return cached
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"موتور ریاضی پیدا نشد: {path}")
    spec = importlib.util.spec_from_file_location("derivatives_scout", str(p))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # ثبت در sys.modules پیش از اجرا لازم است، وگرنه dataclass داخل موتور خطا می‌دهد
    sys.modules["derivatives_scout"] = module
    spec.loader.exec_module(module)
    _SCOUT_CACHE[key] = module
    return module


# ---------------------------------------------------------------- ابزار پایه
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def g2j(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    jm = 1 + days // 31 if days < 186 else 7 + (days - 186) // 30
    jd = 1 + days % 31 if days < 186 else 1 + (days - 186) % 30
    return jy, jm, jd


def fa_time(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    jy, jm, jd = g2j(dt.year, dt.month, dt.day)
    return f"{jy:04d}/{jm:02d}/{jd:02d} {dt.hour:02d}:{dt.minute:02d}"


def log(msg: str) -> None:
    print(f"[{fa_time()}] {msg}")


def load_config(path: str | None = None) -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG, ensure_ascii=False))
    p = Path(path) if path else BASE / "config.json"
    if p.exists():
        try:
            user = json.loads(p.read_text(encoding="utf-8"))
            for k, v in user.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
        except json.JSONDecodeError as e:
            log(f"تنظیمات خوانده نشد ({e})؛ پیش‌فرض به کار می‌رود.")
    return cfg


# ---------------------------------------------------------------- داده‌ها
@dataclass
class Signal:
    sid: str
    symbol: str
    kind: str
    name: str
    annualized_pct: float | None
    score_pp: float
    go: bool
    detail: dict = field(default_factory=dict)
    margin_per_contract: float = 0.0
    contracts: int = 0
    margin_locked: float = 0.0
    status: str = "pending"
    gate_note: str = ""
    alerts: list[dict] = field(default_factory=list)

    @property
    def unit(self) -> str:
        return str(self.detail.get("unit") or "قرارداد")

    def as_row(self) -> tuple:
        return (self.sid, now_iso(), self.symbol, self.kind, self.name,
                self.annualized_pct, self.score_pp, int(self.go),
                json.dumps(self.detail, ensure_ascii=False), self.margin_per_contract,
                self.contracts, self.margin_locked, self.status, self.gate_note,
                json.dumps(self.alerts, ensure_ascii=False))

    @staticmethod
    def from_row(row) -> "Signal":
        (sid, _ts, symbol, kind, name, annualized, score_pp, go,
         detail, margin, contracts, locked, status, gate_note, alerts) = row
        return Signal(sid=sid, symbol=symbol, kind=kind, name=name, annualized_pct=annualized,
                      score_pp=score_pp, go=bool(go), detail=json.loads(detail or "{}"),
                      margin_per_contract=margin or 0.0, contracts=contracts or 0,
                      margin_locked=locked or 0.0, status=status, gate_note=gate_note or "",
                      alerts=json.loads(alerts or "[]"))


SIGNAL_SELECT = ("SELECT sid, ts, symbol, kind, name, annualized, score_pp, go, detail, "
                 "margin_per_contract, contracts, margin_locked, status, gate_note, alerts FROM signals")


class Desk:
    def __init__(self, path: Path | str = DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            sid TEXT PRIMARY KEY, ts TEXT, symbol TEXT, kind TEXT, name TEXT,
            annualized REAL, score_pp REAL, go INTEGER, detail TEXT,
            margin_per_contract REAL, contracts INTEGER, margin_locked REAL,
            status TEXT, gate_note TEXT, alerts TEXT);
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, sid TEXT, action TEXT, note TEXT);
        """)
        self.conn.commit()

    # ── بستن تمیز (پایان کار / پرونده‌های موقت)
    def close(self) -> None:
        """پیوند پایگاه‌داده را می‌بندد. چند بار صدا زدنش بی‌خطر است."""
        try:
            self.conn.close()
        except Exception:      # noqa: BLE001 — بستن نباید برنامه را بیندازد
            pass

    def __enter__(self) -> "Desk":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()


    # ---------- ثبت سیگنال
    def upsert(self, sig: Signal, keep_status: bool = True) -> None:
        old = self.get(sig.sid)
        if old and keep_status:
            sig.status = old.status
            if old.gate_note and not sig.gate_note:
                sig.gate_note = old.gate_note
        self.conn.execute("DELETE FROM signals WHERE sid = ?", (sig.sid,))
        self.conn.execute(
            "INSERT INTO signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", sig.as_row())
        self.conn.commit()

    def get(self, sid: str) -> Signal | None:
        cur = self.conn.execute(SIGNAL_SELECT + " WHERE sid = ?", (sid,))
        row = cur.fetchone()
        return Signal.from_row(row) if row else None

    def all(self, status: str | None = None, limit: int = 200) -> list[Signal]:
        q = SIGNAL_SELECT + (" WHERE status = ?" if status else "") + " ORDER BY score_pp DESC LIMIT ?"
        args = (status, limit) if status else (limit,)
        return [Signal.from_row(r) for r in self.conn.execute(q, args).fetchall()]

    def locked_margin(self, exclude_sid: str | None = None) -> float:
        cur = self.conn.execute(
            "SELECT COALESCE(SUM(margin_locked),0) FROM signals WHERE status = 'approved' AND sid IS NOT ?",
            (exclude_sid,))
        return float(cur.fetchone()[0])

    def decide(self, sid: str, action: str, note: str) -> bool:
        sig = self.get(sid)
        if not sig:
            return False
        sig.status = action
        if note:
            sig.gate_note = note
        self.upsert(sig, keep_status=False)  # وضعیت تازه، عمداً بر وضعیت قبلی نوشته می‌شود
        self.conn.execute("INSERT INTO decisions (ts, sid, action, note) VALUES (?,?,?,?)",
                          (now_iso(), sid, action, note))
        self.conn.commit()
        return True

    def human_decided(self, sid: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM decisions WHERE sid = ? LIMIT 1", (sid,))
        return cur.fetchone() is not None

    def decisions(self, limit: int = 50) -> list[tuple]:
        return self.conn.execute(
            "SELECT ts, sid, action, note FROM decisions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


# ---------------------------------------------------------------- خواندن هشدارهای کدال
def read_alerts(kodal_db: Path | str, min_score: int = 60, limit: int = 50) -> list[dict]:
    """هشدارهای دیده‌بان را می‌خواند. اگر پایگاه‌داده نبود، فهرست خالی برمی‌گرداند."""
    p = Path(kodal_db)
    if not p.exists():
        log(f"پایگاه‌داده دیده‌بان پیدا نشد: {p}")
        return []
    try:
        conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        rows = conn.execute(
            "SELECT title, symbol, category, direction, score, url FROM items "
            "WHERE score >= ? ORDER BY score DESC LIMIT ?", (min_score, limit)).fetchall()
        conn.close()
    except sqlite3.Error as e:
        log(f"خواندن هشدارها ممکن نشد: {e}")
        return []
    return [{"title": t, "symbol": s, "category": c, "direction": d, "score": sc, "url": u}
            for t, s, c, d, sc, u in rows]


def related_alerts(symbol: str, alerts: list[dict]) -> list[dict]:
    out = []
    for a in alerts:
        sym = (a.get("symbol") or "").strip()
        if sym and (sym == symbol or sym in symbol or symbol in sym):
            out.append(a)
        elif not sym and symbol and symbol in (a.get("title") or ""):
            out.append(a)
    return out


# ---------------------------------------------------------------- موتور ریاضی
KIND_LABELS = {
    "basis": "پایهٔ نقدی‌آتی",
    "box": "باکس اسپرد",
    "tabei": "اوراق تبعی",
    "covered_call": "پوشش‌داده‌شده",
    "parity": "تساوی پوت‌کال",
}


def math_for_row(row: dict, hurdle: float) -> dict:
    """هر ردیف اسنپ‌شات را روی موتور ریاضی می‌گذارد و خروجی استاندارد برمی‌گرداند."""
    scout = load_scout()
    sc = scout.Scenario(name=row.get("symbol", "?"), rows=[{k: v for k, v in row.items() if k != "margin_per_contract"}],
                        hurdle=hurdle)
    result = scout.run_scenario(sc)[0]
    if "error" in result:
        raise ValueError(f"ردیف نامعتبر است: {result['error']}")
    result["kind"] = row.get("kind", "نامشخص")  # برچسب فارسی راهبرد در گزارش‌ها
    result["margin_per_contract"] = float(row.get("margin_per_contract", 0) or 0)
    return result


def signal_from_result(symbol: str, res: dict, cfg: dict) -> Signal:
    kind = str(res.get("kind") or res.get("strategy") or "نامشخص")
    name = f"{symbol} · {KIND_LABELS.get(kind, kind)}"
    annual = res.get("annualized_pct")
    sid = hashlib.sha1(f"{symbol}|{kind}|{json.dumps(res.get('detail', res), sort_keys=True, default=str)}"
                       .encode("utf-8")).hexdigest()[:12]
    return Signal(sid=sid, symbol=symbol, kind=kind, name=name,
                  annualized_pct=annual if isinstance(annual, (int, float)) else None,
                  score_pp=float(res.get("score_pp", -999)),
                  go=bool(res.get("go")), detail=res,
                  margin_per_contract=float(res.get("margin_per_contract", 0) or 0))


def gate_checks(sig: Signal, cfg: dict, desk: Desk) -> list[str]:
    """دروازه‌های ریسک بدون اندازه‌گذاری: نقدشوندگی، اسپرد، تأیید موتور، سقف موقعیت."""
    d = sig.detail
    reasons: list[str] = []
    if not sig.go:
        reasons.append("موتور ریاضی این فرصت را تأیید نکرد.")
    edge = sig.score_pp
    threshold = (cfg["min_edge_arbitrage_pct"] if sig.kind in ("box", "parity", "tabei")
                 else cfg["min_edge_leveraged_pct"])
    if edge < threshold:
        reasons.append(f"حاشیهٔ {edge:.2f} واحد درصد کمتر از کف {threshold:.2f} درصدی این راهبرد است.")
    liq = d.get("liquidity_contracts_per_day", 999)
    if isinstance(liq, (int, float)) and liq < cfg["min_liquidity_contracts_per_day"]:
        reasons.append(f"حجم روزانهٔ {liq} کمتر از کف نقدشوندگی {cfg['min_liquidity_contracts_per_day']} است.")
    # دروازهٔ باورپذیری: بازده غیرمنطقی یعنی داده اشتباه است، نه فرصت تاریخی
    ceiling = (cfg.get("max_plausible_arb_pct", 250.0) if sig.kind in ("box", "parity", "tabei")
               else cfg.get("max_plausible_lev_pct", 400.0))
    if isinstance(sig.annualized_pct, (int, float)) and abs(sig.annualized_pct) > ceiling:
        reasons.append(f"بازده محاسبه‌شده {sig.annualized_pct:,.0f} درصد از سقف باورپذیری ({ceiling:,.0f} درصد) "
                       f"بیشتر است؛ یعنی یکی از اعداد ورودی غلط یا کهنه است. اول داده را بازبینی کنید.")
    spread = d.get("spread_pct", 0) or 0
    if spread > cfg["max_spread_pct"]:
        reasons.append(f"اسپرد {spread * 100:.2f} درصد از سقف مجاز بیشتر است.")
    if not sig.alerts and edge < threshold * 2:
        reasons.append("بدون پشتوانهٔ خبری و با حاشیهٔ کم؛ اولویت پایین است.")
    return reasons


def size_position(sig: Signal, budget: float) -> str:
    """اندازهٔ موقعیت را از بودجهٔ باقی‌مانده حساب می‌کند؛ در صورت نبود جا، پیام دلیل را می‌دهد."""
    unit = sig.unit
    if (sig.margin_per_contract or 0) <= 0:
        sig.contracts = 0
        return f"نرخ وجه تضمین هر {unit} در اسنپ‌شات مشخص نشده؛ از مشخصات قرارداد بخوانید."
    n = int(budget // sig.margin_per_contract)
    if n < 1:
        sig.contracts = 0
        return f"بودجهٔ وجه تضمین (سقف {sig.margin_per_contract:,.0f} ریال برای هر {unit}) تمام شده است."
    sig.contracts = n
    sig.margin_locked = n * sig.margin_per_contract
    return ""


def apply_risk_gates(sig: Signal, cfg: dict, desk: Desk) -> Signal:
    """نسخهٔ تک‌سیگنالی (برای آزمون و بازبینی دستی)."""
    reasons = gate_checks(sig, cfg, desk)
    approved_so_far = len([s for s in desk.all("approved") if s.sid != sig.sid])
    if approved_so_far >= cfg["max_positions"]:
        reasons.append(f"سقف {cfg['max_positions']} موقعیت تأییدشده پر است؛ اول یکی را ببندید.")
    budget = cfg["capital"] * cfg["max_margin_pct"] - desk.locked_margin(exclude_sid=sig.sid)
    budget = max(budget, 0.0)
    note = size_position(sig, budget)
    if reasons or note:
        sig.status = "rejected"
        sig.gate_note = " | ".join(reasons + ([note] if note else []))
    else:
        sig.status = "pending"
        sig.gate_note = (f"حاشیهٔ {sig.score_pp:.2f} واحد درصد · {sig.contracts:,} {sig.unit} · "
                         f"سرمایهٔ درگیر {sig.margin_locked:,.0f} ریال")
    return sig


def scan_market(market_path: Path | str, cfg: dict, desk: Desk,
                kodal_db: Path | str | None = None) -> list[Signal]:
    """محاسبهٔ همهٔ ردیف‌ها، سپس تخصیص بودجهٔ وجه تضمین به‌ترتیب امتیاز."""
    data = json.loads(Path(market_path).read_text(encoding="utf-8"))
    hurdle = float(data.get("hurdle", cfg["hurdle"]))
    if data.get("capital"):
        cfg["capital"] = float(data["capital"])
    alerts = read_alerts(kodal_db, cfg["alert_score_threshold"]) if kodal_db else []
    candidates: list[Signal] = []
    for row in data.get("rows", []):
        symbol = str(row.get("symbol", "?"))
        try:
            res = math_for_row(row, hurdle)
        except Exception as e:  # ورودی ناقص یا فرمول نامعتبر
            log(f"ردیف {symbol} محاسبه نشد: {type(e).__name__}: {e}")
            continue
        res.setdefault("unit", row.get("unit") or ("سهم" if row.get("kind") in
                       ("tabei", "covered_call", "parity") else "قرارداد"))
        sig = signal_from_result(symbol, res, cfg)
        sig.alerts = related_alerts(symbol, alerts)
        sig.gate_note = " | ".join(gate_checks(sig, cfg, desk))
        candidates.append(sig)

    candidates.sort(key=lambda s: s.score_pp, reverse=True)
    budget_total = max(cfg["capital"] * cfg["max_margin_pct"] - desk.locked_margin(), 0.0)
    policy = {"capital": cfg["capital"], "max_margin_pct": cfg["max_margin_pct"],
              "cap_total": cfg["capital"] * cfg["max_margin_pct"],
              "max_positions": cfg["max_positions"], "hurdle": hurdle}
    for sig in candidates:
        sig.detail["_policy"] = policy
    budget = budget_total
    per_position = budget_total * float(cfg.get("max_position_pct", 1.0))
    for sig in candidates:
        existing = desk.get(sig.sid)
        if existing and desk.human_decided(sig.sid):
            # تصمیم انسان بازنویسی نمی‌شود: اندازه و یادداشت همان می‌ماند
            sig.status, sig.contracts = existing.status, existing.contracts
            sig.margin_locked, sig.gate_note = existing.margin_locked, existing.gate_note
            desk.upsert(sig)
            continue
        if sig.gate_note:
            sig.status = "rejected"
        else:
            note = size_position(sig, max(min(budget, per_position), 0.0))
            if note:
                sig.status = "rejected"
                sig.gate_note = note
            else:
                budget -= sig.margin_locked
                sig.status = "pending"
                sig.gate_note = (f"حاشیهٔ {sig.score_pp:.2f} واحد درصد · {sig.contracts:,} {sig.unit} · "
                                 f"سرمایهٔ درگیر {sig.margin_locked:,.0f} ریال")
        desk.upsert(sig)
    return candidates


def recheck_tasks(cfg: dict, desk: Desk, kodal_db: Path | str, market_path: Path | str) -> list[dict]:
    """نمادهایی که خبر مهم داشته‌اند ولی در اسنپ‌شات بازار ردیفی ندارند."""
    data = json.loads(Path(market_path).read_text(encoding="utf-8"))
    covered = {str(r.get("symbol", "")) for r in data.get("rows", [])}
    out = []
    for a in read_alerts(kodal_db, cfg["alert_score_threshold"]):
        sym = (a.get("symbol") or "").strip()
        if sym and sym in covered:
            continue
        if sym:
            out.append({"symbol": sym, "reason": "خبر مهم، ولی دادهٔ آپشن/آتی این نماد در اسنپ‌شات نیست",
                        "alert": a})
    return out


# ---------------------------------------------------------------- بستهٔ سفارش
def order_packet(sig: Signal) -> str:
    d = sig.detail
    lines = [
        "بستهٔ سفارش (اجرا فقط توسط انسان در سامانهٔ کارگزاری)",
        "=" * 62,
        f"نماد: {sig.symbol}    راهبرد: {KIND_LABELS.get(sig.kind, sig.kind)}",
        f"شمارهٔ سیگنال: {sig.sid}",
        f"بازده سالانهٔ خالص برآوردی: {sig.annualized_pct if sig.annualized_pct is not None else '—'} درصد",
        f"امتیاز نسبت به نرخ سد: {sig.score_pp} واحد درصد",
        f"تعداد پیشنهادی: {sig.contracts:,} {sig.unit}",
        f"سرمایهٔ درگیر (وجه تضمین یا بهای خرید): {sig.margin_locked:,.0f} ریال",
        "",
        "جزئیات ریاضی:",
    ]
    for k, v in d.items():
        if k in ("name", "strategy", "kind", "liquidity_contracts_per_day", "spread_pct", "leverage_used"):
            continue
        lines.append(f"  · {k}: {v}")
    if sig.alerts:
        lines.append("")
        lines.append("خبرهای مرتبط (فقط برای زمینه؛ خبر به‌تنهایی سیگنال نیست):")
        for a in sig.alerts:
            lines.append(f"  · [{a.get('score')}] {a.get('title')}")
    lines += [
        "",
        "یادآوری‌های اجرایی:",
        "  ۱. پیش از ثبت، قیمت لحظه‌ای و عمق بازار را دوباره ببینید؛ اعداد اسنپ‌شات، تاریخی‌اند.",
        "  ۲. پاهای آربیتراژ را در یک پنجرهٔ زمانی کوتاه و هم‌زمان اجرا کنید، وگرنه ریسک اجرا می‌گیرید.",
        "  ۳. این بسته «پیشنهاد» است؛ تصمیم و مسئولیت با شماست. سود تضمینی وجود ندارد.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- داشبورد HTML
def build_dashboard(desk: Desk, cfg: dict, path: Path | str = DEFAULT_REPORT,
                    tasks: list[dict] | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    all_sigs = desk.all(limit=500)
    pending = [s for s in all_sigs if s.status == "pending"]
    approved = [s for s in all_sigs if s.status == "approved"]
    rejected = [s for s in all_sigs if s.status == "rejected"]

    def rows(items: list[Signal], show_gate: bool = True) -> str:
        out = []
        for s in items:
            color = "#0a7d33" if s.score_pp > 10 else ("#8a6d00" if s.score_pp > 0 else "#b3261e")
            news = "<br>".join(html.escape(a.get("title", "")[:110]) for a in s.alerts[:3]) or "—"
            out.append(f"""<tr>
      <td class="id">{html.escape(s.sid)}</td>
      <td>{html.escape(s.symbol)}</td>
      <td>{html.escape(KIND_LABELS.get(s.kind, s.kind))}</td>
      <td class="num">{'' if s.annualized_pct is None else f'{s.annualized_pct:.2f}'}</td>
      <td class="num" style="color:{color}">{s.score_pp:.2f}</td>
      <td class="num">{s.contracts:,} {html.escape(s.unit)}</td>
      <td class="num">{s.margin_locked:,.0f}</td>
      <td class="status">{html.escape(s.status)}</td>
      <td class="note">{html.escape(s.gate_note)}{f'<div class="news">{news}</div>' if news != '—' else ''}</td>
    </tr>""")
        return "".join(out) or '<tr><td colspan="9">موردی نیست.</td></tr>'

    tasks_html = "".join(
        f"<li><b>{html.escape(t['symbol'])}</b> — {html.escape(t['reason'])} "
        f"<span class='news'>{html.escape(str(t['alert'].get('title', ''))[:120])}</span></li>"
        for t in (tasks or [])) or "<li>موردی نیست.</li>"

    doc = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<title>{html.escape(cfg['report_title'])} — {fa_time()}</title>
<style>
  body {{ font-family: Tahoma, "Segoe UI", "Vazirmatn", sans-serif; margin: 0; background: #f6f7f9; color: #1d1d1f; }}
  header {{ background: #0b3d2e; color: #fff; padding: 18px 22px; }}
  header h1 {{ margin: 0 0 6px; font-size: 20px; }}
  header .meta {{ font-size: 12px; opacity: .85; }}
  .cards {{ display: flex; gap: 12px; flex-wrap: wrap; padding: 16px 22px 0; }}
  .card {{ background: #fff; border: 1px solid #e3e6ea; border-radius: 10px; padding: 12px 14px; min-width: 170px; }}
  .card .k {{ font-size: 12px; color: #6b7280; }}
  .card .v {{ font-size: 18px; font-weight: bold; margin-top: 4px; }}
  main {{ padding: 14px 22px 40px; }}
  h2 {{ font-size: 16px; margin: 22px 0 8px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; font-size: 12.5px; }}
  th, td {{ border-bottom: 1px solid #e6e8ec; padding: 7px 9px; text-align: right; vertical-align: top; }}
  th {{ background: #eef2f7; font-size: 12px; }}
  .num {{ font-variant-numeric: tabular-nums; }}
  .id {{ font-family: Consolas, monospace; font-size: 11.5px; color: #0b5394; }}
  .note {{ color: #444; max-width: 330px; }}
  .news {{ color: #0b5394; font-size: 11.5px; margin-top: 4px; }}
  .status {{ font-weight: bold; }}
  .warn {{ background: #fff8e1; border: 1px solid #f0e0a8; border-radius: 8px; padding: 10px 12px; font-size: 12.5px; margin: 10px 0 0; }}
  ul {{ margin: 6px 0 0; padding-right: 20px; font-size: 12.5px; }}
  footer {{ margin-top: 22px; font-size: 11.5px; color: #6b7280; line-height: 1.9; }}
</style></head>
<body>
<header>
  <h1>{html.escape(cfg['report_title'])}</h1>
  <div class="meta">زمان: {fa_time()} · نسخهٔ {VERSION} · نرخ سد: {cfg['hurdle'] * 100:.1f} درصد</div>
</header>
<div class="cards">
  <div class="card"><div class="k">سرمایه</div><div class="v">{cfg['capital']:,.0f}</div></div>
  <div class="card"><div class="k">سیگنال منتظر تأیید</div><div class="v">{len(pending)}</div></div>
  <div class="card"><div class="k">تأییدشده</div><div class="v">{len(approved)}</div></div>
  <div class="card"><div class="k">وجه تضمین قفل‌شده</div><div class="v">{desk.locked_margin():,.0f}</div></div>
  <div class="card"><div class="k">رد شده</div><div class="v">{len(rejected)}</div></div>
</div>
<main>
  <div class="warn">این داشبورد «دستیار تصمیم» است. هیچ سفارشی خودکار ارسال نمی‌شود؛
  معاملات الگوریتمی خودکار در بورس و فرابورس ایران مجاز نیست. تصمیم نهایی و مسئولیت آن با انسان است و هیچ سود تضمینی وجود ندارد.</div>

  <h2>سیگنال‌های منتظر تأیید</h2>
  <table><thead><tr><th>شناسه</th><th>نماد</th><th>راهبرد</th><th>بازده سالانهٔ خالص (٪)</th>
  <th>حاشیه (واحد ٪)</th><th>تعداد</th><th>وجه تضمین</th><th>وضعیت</th><th>یادداشت دروازه / خبر مرتبط</th></tr></thead>
  <tbody>{rows(pending)}</tbody></table>

  <h2>تأییدشده (آمادهٔ اجرای انسانی)</h2>
  <table><thead><tr><th>شناسه</th><th>نماد</th><th>راهبرد</th><th>بازده سالانهٔ خالص (٪)</th>
  <th>حاشیه (واحد ٪)</th><th>تعداد</th><th>وجه تضمین</th><th>وضعیت</th><th>یادداشت دروازه / خبر مرتبط</th></tr></thead>
  <tbody>{rows(approved)}</tbody></table>

  <h2>رد‌شده‌ها و دلیل</h2>
  <table><thead><tr><th>شناسه</th><th>نماد</th><th>راهبرد</th><th>بازده سالانهٔ خالص (٪)</th>
  <th>حاشیه (واحد ٪)</th><th>تعداد</th><th>وجه تضمین</th><th>وضعیت</th><th>یادداشت دروازه / خبر مرتبط</th></tr></thead>
  <tbody>{rows(rejected)}</tbody></table>

  <h2>کارهای بازبینی (خبر مهم بدون دادهٔ بازار)</h2>
  <ul>{tasks_html}</ul>

  <h2>دستورهای تأیید و اجرا</h2>
  <ul>
    <li><code>python desk.py list --status pending</code> فهرست سیگنال‌ها</li>
    <li><code>python desk.py approve &lt;شناسه&gt; --note "ریسک پذیرفته شد"</code> تأیید انسانی</li>
    <li><code>python desk.py reject &lt;شناسه&gt; --note "نقدشوندگی کم"</code> رد با دلیل</li>
    <li><code>python desk.py packet &lt;شناسه&gt;</code> چاپ بستهٔ سفارش برای اجرا در سامانهٔ کارگزاری</li>
  </ul>

  <footer>ساختهٔ میز معاملات نسخهٔ {VERSION} · {html.escape(cfg['credit'])}</footer>
</main></body></html>"""
    path.write_text(doc, encoding="utf-8")
    return path


# ---------------------------------------------------------------- دستورها
def cmd_scan(args) -> int:
    cfg = load_config(args.config)
    desk = Desk(cfg.get("desk_db") or DEFAULT_DB)
    sigs = scan_market(args.market, cfg, desk, args.kodal_db)
    for s in sigs[:20]:
        mark = "✅" if s.status == "pending" else ("🟢" if s.status == "approved" else "✖")
        ann = f"{s.annualized_pct:.2f}٪" if isinstance(s.annualized_pct, (int, float)) else "—"
        print(f"{mark} [{s.sid}] {s.symbol:<8} {KIND_LABELS.get(s.kind, s.kind):<16} بازده {ann:<9} حاشیه {s.score_pp:>7.2f} قرارداد {s.contracts}")
        if s.status == "rejected":
            print(f"     دلیل: {s.gate_note}")
    log(f"{len(sigs)} سیگنال محاسبه شد؛ {len([s for s in sigs if s.status == 'pending'])} منتظر تأیید.")
    return 0


def cmd_run(args) -> int:
    cfg = load_config(args.config)
    desk = Desk(cfg.get("desk_db") or DEFAULT_DB)
    sigs = scan_market(args.market, cfg, desk, args.kodal_db)
    tasks = recheck_tasks(cfg, desk, args.kodal_db, args.market) if args.kodal_db else []
    path = build_dashboard(desk, cfg, cfg.get("report_path") or DEFAULT_REPORT, tasks)
    log(f"{len(sigs)} سیگنال · {len(tasks)} کار بازبینی · داشبورد: {path}")
    for s in sigs:
        if s.status == "pending":
            print(f"   → منتظر تأیید: [{s.sid}] {s.name} با حاشیهٔ {s.score_pp:.2f} واحد درصد")
    return 0


def cmd_list(args) -> int:
    cfg = load_config(args.config)
    desk = Desk(cfg.get("desk_db") or DEFAULT_DB)
    items = desk.all(args.status, args.limit)
    if not items:
        print("موردی نیست.")
        return 0
    for s in items:
        ann = f"{s.annualized_pct:.2f}٪" if isinstance(s.annualized_pct, (int, float)) else "—"
        print(f"[{s.sid}] {s.status:<9} {s.symbol:<8} {KIND_LABELS.get(s.kind, s.kind):<16} "
              f"بازده {ann:<9} حاشیه {s.score_pp:>7.2f} {s.contracts:,} {s.unit}")
        if s.gate_note:
            print(f"     {s.gate_note}")
    return 0


def cmd_decide(args, action: str) -> int:
    cfg = load_config(args.config)
    desk = Desk(cfg.get("desk_db") or DEFAULT_DB)
    sig = desk.get(args.sid)
    if not sig:
        print("شناسه پیدا نشد.")
        return 2
    if action == "approved":
        policy = sig.detail.get("_policy") or {}
        cap = float(policy.get("cap_total") or cfg["capital"] * cfg["max_margin_pct"])
        max_positions = int(policy.get("max_positions") or cfg["max_positions"])
        used = desk.locked_margin(exclude_sid=sig.sid) + sig.margin_locked
        count = len([s for s in desk.all("approved") if s.sid != sig.sid])
        if used > cap or count >= max_positions:
            print(f"توقف: تأیید این سیگنال سقف ریسک را رد می‌کند "
                  f"(سرمایهٔ درگیر {used:,.0f} از سقف {cap:,.0f} ریال · موقعیت‌های تأییدشده {count} از {max_positions}).")
            if not getattr(args, "force", False):
                print("اگر آگاهانه می‌خواهید رد کنید، دستور را با --force تکرار کنید.")
                return 3
            print("با --force رد شد؛ این تصمیم در دفتر ثبت می‌شود.")
    desk.decide(args.sid, action, args.note or "")
    print(f"{'تأیید' if action == 'approved' else 'رد'} شد: {args.sid}")
    if action == "approved":
        sig = desk.get(args.sid)
        assert sig is not None
        print()
        print(order_packet(sig))
    return 0


def cmd_packet(args) -> int:
    cfg = load_config(args.config)
    desk = Desk(cfg.get("desk_db") or DEFAULT_DB)
    sig = desk.get(args.sid)
    if not sig:
        print("شناسه پیدا نشد.")
        return 2
    if sig.status != "approved":
        print(f"هشدار: وضعیت این سیگنال «{sig.status}» است، نه تأییدشده. "
              f"برای اجرا اول با دستور approve تأیید کنید.")
    print(order_packet(sig))
    return 0


def cmd_stats(args) -> int:
    cfg = load_config(args.config)
    desk = Desk(cfg.get("desk_db") or DEFAULT_DB)
    rows = desk.conn.execute(
        "SELECT status, COUNT(*), COALESCE(SUM(margin_locked),0) FROM signals GROUP BY status").fetchall()
    print(f"{'وضعیت':<12}{'تعداد':>8}{'وجه تضمین قفل‌شده':>22}")
    for st, n, locked in rows:
        print(f"{st:<12}{n:>8}{locked:>22,.0f}")
    print(f"\nتصمیم‌های ثبت‌شده: {len(desk.decisions(1000))}")
    return 0


def cmd_selftest(args) -> int:
    checks = 0
    scout = load_scout()
    assert hasattr(scout, "box_spread") and hasattr(scout, "tabei_min_yield")
    checks += 1
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    desk = Desk(BASE / "data" / "_selftest.sqlite3")
    desk.conn.execute("DELETE FROM signals")
    desk.conn.commit()
    market = BASE / "market-demo.json"
    if market.exists():
        sigs = scan_market(market, cfg, desk)
        assert sigs, "اسنپ‌شات نمونه سیگنالی تولید نکرد"
        checks += 1
        assert any(s.status == "pending" for s in sigs) or all(s.gate_note for s in sigs)
        checks += 1
    assert g2j(2026, 9, 22) == (1405, 6, 31)
    checks += 1
    print(f"خودآزمون: {checks} بررسی موفق")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="میز معاملات — دستیار تصمیم با تأیید انسان (بدون ارسال سفارش)")
    ap.add_argument("--config", help="مسیر config.json")
    sub = ap.add_subparsers(dest="cmd")

    p_scan = sub.add_parser("scan", help="محاسبهٔ ریاضی روی اسنپ‌شات بازار")
    p_scan.add_argument("--market", required=True)
    p_scan.add_argument("--kodal-db", help="پایگاه‌دادهٔ دیده‌بان کدال")
    p_scan.set_defaults(func=cmd_scan)

    p_run = sub.add_parser("run", help="محاسبه + چسباندن خبرها + داشبورد")
    p_run.add_argument("--market", required=True)
    p_run.add_argument("--kodal-db")
    p_run.set_defaults(func=cmd_run)

    p_list = sub.add_parser("list", help="فهرست سیگنال‌ها")
    p_list.add_argument("--status", choices=["pending", "approved", "rejected"])
    p_list.add_argument("--limit", type=int, default=50)
    p_list.set_defaults(func=cmd_list)

    p_app = sub.add_parser("approve", help="تأیید انسانی سیگنال")
    p_app.add_argument("sid")
    p_app.add_argument("--note", default="")
    p_app.add_argument("--force", action="store_true", help="رد کردن آگاهانهٔ سقف ریسک")
    p_app.set_defaults(func=lambda a: cmd_decide(a, "approved"))

    p_rej = sub.add_parser("reject", help="رد سیگنال با دلیل")
    p_rej.add_argument("sid")
    p_rej.add_argument("--note", default="")
    p_rej.set_defaults(func=lambda a: cmd_decide(a, "rejected"))

    p_list.set_defaults(func=cmd_list)  # نگهبان

    p_pack = sub.add_parser("packet", help="چاپ بستهٔ سفارش")
    p_pack.add_argument("sid")
    p_pack.set_defaults(func=cmd_packet)

    sub.add_parser("stats", help="آمار وضعیت‌ها").set_defaults(func=cmd_stats)
    sub.add_parser("selftest", help="آزمون سریع").set_defaults(func=cmd_selftest)
    sub.add_parser("version", help="نسخه").set_defaults(func=lambda a: (print(f"desk {VERSION}"), 0)[1])

    args = ap.parse_args(argv)
    if not getattr(args, "cmd", None):
        ap.print_help()
        return 0
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
