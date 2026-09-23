#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""پروندهٔ سرمایه‌گذار — یک فایل برای جلسه، ساخته‌شده از شاهدهای همان اجرا.

چه می‌کند؟ همهٔ شاهدهای موجود را از روی پرونده‌های واقعی برنامه جمع می‌کند:
قواعد قفل‌شده، نتیجهٔ «آزمون ۱۰ دقیقه‌ای»، دفتر آزمون و کارنامه، پس‌آزمایی تاریخی،
وضعیت داده و اتصال، و شناسنامهٔ پرونده‌ها با اثر انگشت (sha256).
بعد همه را در یک صفحهٔ HTML آمادهٔ چاپ و یک نسخهٔ متنی می‌ریزد.

چه نمی‌کند؟ هیچ عددی از خودش نمی‌سازد، هیچ سودی وعده نمی‌دهد، و هیچ داده‌ای بیرون نمی‌فرستد.

اجرا:  python dossier.py            (ساخت پرونده در پوشهٔ data)
       python dossier.py --json     (شاهدهای خام، ماشین‌خوان)
       python dossier.py --out <مسیر پروندهٔ HTML>
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.1.0"
BASE = Path(__file__).resolve().parent
DESK_DIR = (BASE.parent / "desk").resolve()
DATA = BASE / "data"

for p in (str(BASE), str(DESK_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import reportkit as rk  # noqa: E402
import selftest  # noqa: E402

DEFAULT_RULES: dict = {
    "capital": 20_000_000_000, "hurdle": 0.39,
    "min_edge_arbitrage_pct": 3.0, "min_edge_leveraged_pct": 5.0,
    "max_margin_pct": 0.20, "max_position_pct": 0.35, "max_positions": 3,
    "min_liquidity_contracts_per_day": 20, "max_spread_pct": 0.03,
    "max_plausible_arb_pct": 250.0, "max_plausible_lev_pct": 400.0,
}

RULE_NOTES = {
    "capital": "سرمایهٔ فرضی آزمون (ریال)",
    "hurdle": "نرخ سد: کمترین بازدهی که برای قبول‌کردن یک فرصت لازم است",
    "min_edge_arbitrage_pct": "کف حاشیه برای راهبردهای آربیتراژی (واحد درصد)",
    "min_edge_leveraged_pct": "کف حاشیه برای راهبردهای اهرمی (واحد درصد)",
    "max_margin_pct": "سقف سهم سرمایه در وجه تضمین",
    "max_position_pct": "سقف هر موقعیت نسبت به سرمایه",
    "max_positions": "بیشترین تعداد موقعیت باز هم‌زمان",
    "min_liquidity_contracts_per_day": "کف نقدشوندگی (قرارداد در روز)",
    "max_spread_pct": "سقف اسپرد خرید و فروش",
    "max_plausible_arb_pct": "سقف باورپذیری بازده سالانهٔ آربیتراژ (بالاتر از آن یعنی داده مشکوک)",
    "max_plausible_lev_pct": "سقف باورپذیری بازده سالانهٔ اهرمی",
}

LIMITATIONS = [
    "هیچ سفارشی به‌صورت خودکار ارسال نمی‌شود؛ خروجی برنامه پیشنهاد و هشدار است.",
    "هیچ سود تضمینی وجود ندارد؛ هیچ برنامه‌ای در هیچ بازاری سود را تضمین نمی‌کند.",
    "وجه تضمین و مشخصات هر قرارداد باید از سامانهٔ کارگزاری خوانده شود، نه از حافظه.",
    "بازده‌های گزارش‌شده، «بازده سالانهٔ محاسبه‌شده از اختلاف قیمت‌ها» هستند، نه سود محقق‌شده.",
    "روزهایی که با خوراک آزمایشی ثبت شوند، ساختی‌اند و در کارنامه از روزهای واقعی جدا شمرده می‌شوند.",
    "دادهٔ رایگان و بی‌تعهد ممکن است با تأخیر یا خطا بیاید؛ برنامه این را صریح گزارش می‌کند.",
]

VERIFY_STEPS = [
    ("گام ۱", "خودتان «آزمون ۱۰ دقیقه‌ای» را اجرا کنید",
     "python selftest.py", "کارنامهٔ سبز/سرخ را همان‌جا می‌بینید؛ سه موردش را با ماشین‌حساب چک کنید."),
    ("گام ۲", "خودتان دموی هزینهٔ صفر را اجرا کنید",
     "run-investor-demo.bat (ویندوز) یا bash run-investor-demo", "خوراک آزمایشی محلی می‌آید؛ هیچ اینترنتی لازم نیست."),
    ("گام ۳", "زنجیرهٔ دفتر را بیازمانید",
     "python live_trial.py --verify", "اگر ردیفی عوض شده باشد، همین دستور می‌گوید کدام ردیف."),
    ("گام ۴", "یک روز را با اعداد کارگزاری خودتان جایگزین کنید",
     "در گام ۵ رابط گرافیکی، جدول اعداد را پر کنید", "برنامه با همان اعداد دوباره محاسبه می‌کند و حکم را می‌گوید."),
]


# ---------------------------------------------------------------- گردآوری شاهدها
def _file_digest(path: Path) -> dict:
    from hashlib import sha256
    if not path.exists():
        return {"file": str(path), "exists": False}
    data = path.read_bytes()
    return {"file": path.name, "exists": True, "bytes": len(data),
            "sha256": sha256(data).hexdigest()[:16],
            "modified": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")}


def collect(state: dict | None = None, *, run_selftest: bool = True) -> dict:
    """شاهدهای پرونده را از پرونده‌های برنامه جمع می‌کند. هیچ عددی ساخته نمی‌شود."""
    import datafeed as df
    import connections as conn
    import live_trial as trialmod
    import daily_trial as dailytrial
    import backtest as bt

    state = dict(state or {})
    rules = dict(DEFAULT_RULES)
    rules.update({k: v for k, v in (state.get("rules") or {}).items() if k in DEFAULT_RULES})

    # اتصال فعال (کلیدها هرگز در پرونده نمی‌آیند)
    active = None
    try:
        active = conn.active_or_none()
    except Exception:
        active = None
    connection = dict(state.get("connection") or {})
    if active:
        connection.setdefault("name", active["profile"]["name"])
        connection.setdefault("label", active["profile"]["label"])
        connection["key_where"] = active.get("key_where") or "بدون کلید"
        connection["is_mock"] = bool(active.get("is_mock"))

    # اسنپ‌شات
    snap_path = Path(state.get("file_path") or (DESK_DIR / "market-demo.json"))
    snap = df.load_snapshot_rows(snap_path)
    dated = sorted((BASE / "data" / "snapshots").glob("snapshot-*.json")) \
        if (BASE / "data" / "snapshots").exists() else []

    # دفتر آزمون و کارنامه
    t = trialmod.Trial(state.get("trial_db") or trialmod.DEFAULT_DB)
    summary = t.summary()
    log = dailytrial.read_log()
    score = dailytrial.scorecard(t, log_records=log)
    entries = t.all(limit=5000)
    chain_ok, chain_msg = t.verify_chain()

    # پس‌آزمایی تاریخی (روی دادهٔ نمونهٔ همراه؛ صریح برچسب می‌خورد)
    backtest = None
    hist = BASE / "demo" / "history-demo.csv"
    if hist.exists():
        try:
            res = bt.run_backtest(hist, rules)
            backtest = {"summary": res["summary"], "rows": len(res.get("decisions", [])),
                        "source": hist.name, "synthetic": True}
        except Exception as e:
            backtest = {"error": f"{type(e).__name__}: {e}", "source": hist.name, "synthetic": True}

    self_test = None
    if run_selftest:
        st = selftest.run_all()
        self_test = {"summary": st["summary"], "engine": st["engine"],
                     "cases": [{"id": c["id"], "title": c["title"], "why": c["why"],
                                "ok": c["ok"], "hand": c["hand"],
                                "inputs": c["inputs"], "rows": c["rows"]} for c in st["cases"]]}

    files = [_file_digest(p) for p in (
        BASE / "station.py", BASE / "web_server.py", BASE / "daily_trial.py", BASE / "datafeed.py",
        BASE / "autoconnect.py", BASE / "connections.py", selftest.TOOLS_DIR / "derivatives_scout.py",
        DESK_DIR / "desk.py", BASE / "README-FA.md", BASE / "DEMO-INVESTOR-FA.md")]

    return {
        "version": VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "station_mode": state.get("mode", "sim"),
        "rules": rules,
        "connection": connection,
        "snapshot": {"path": str(snap_path), "rows": len(snap.get("rows") or []),
                     "as_of": snap.get("as_of", ""), "confirmed": bool(snap.get("confirmed")),
                     "source": snap.get("source", ""),
                     "dated_files": [f.name for f in dated]},
        "trial": {"entries": summary.get("entries"), "marked": summary.get("marked"),
                  "chain_ok": bool(chain_ok), "chain_message": chain_msg,
                  "buckets": summary.get("buckets") or {}, "avg_expected": summary.get("avg_expected"),
                  "last_ts": summary.get("last_ts"),
                  "first_rows": [{"symbol": e["symbol"], "kind": e["kind"], "expected": e["expected"],
                                  "ts": e["ts"], "hash": e["hash"][:12]} for e in entries[:5]]},
        "scorecard": score,
        "backtest": backtest,
        "self_test": self_test,
        "files": files,
    }


# ---------------------------------------------------------------- ساخت پرونده
def _summary_html(evidence: dict) -> str:
    st = evidence.get("self_test") or {}
    s = st.get("summary") or {}
    sc = evidence["scorecard"]
    kpis = [
        (f'{s.get("passed", 0)}/{s.get("total", 0)}', "آزمون‌های سبز موتور و فرایند"),
        (evidence["trial"]["entries"], "ردیف در دفتر آزمون"),
        (evidence["scorecard"]["days"], "روز ثبت‌شده در کارنامه"),
        (evidence["scorecard"]["real_days"], "روز با دادهٔ واقعی کارگزاری"),
        ("سالم" if evidence["trial"]["chain_ok"] else "شکسته", "زنجیرهٔ هش دفتر"),
    ]
    cards = "".join(f'<div class="kpi"><b>{rk.esc(v)}</b><span>{rk.esc(k)}</span></div>' for v, k in kpis)
    verdict = ("آمادهٔ جلسه: آزمون‌ها سبز است و دفتر سالم."
               if (s.get("ok") and evidence["trial"]["chain_ok"] and sc.get("ready")) else
               "برای جلسهٔ «خرید داده» هنوز زود است: " + rk.esc(sc.get("verdict", "کارنامه ناتمام است.")))
    return f'<div class="kpis">{cards}</div><div class="note">{verdict}</div>'


def _rules_html(evidence: dict) -> str:
    rows = "".join(f'<tr><td><code>{rk.esc(k)}</code></td><td class="num">{rk.esc(v)}</td>'
                   f'<td>{rk.esc(RULE_NOTES.get(k, ""))}</td></tr>' for k, v in evidence["rules"].items())
    return ('<table><thead><tr><th>پارامتر</th><th class="num">مقدار قفل‌شده</th>'
            '<th>معنایش در تصمیم</th></tr></thead><tbody>' + rows + "</tbody></table>")


def _selftest_html(evidence: dict) -> str:
    st = evidence.get("self_test")
    if not st:
        return '<div class="note">آزمون در این اجرا کنار گذاشته شده است.</div>'
    s = st["summary"]
    badge = f'<span class="badge {"ok" if s["ok"] else "no"}">{"همه سبز" if s["ok"] else "سرخ"}</span>'
    rows = "".join(f'<tr class="{"pass" if c["ok"] else "fail"}"><td><code>{rk.esc(c["id"])}</code></td>'
                   f'<td>{rk.esc(c["title"])}</td><td>{rk.esc(c["why"])}</td>'
                   f'<td>{"سبز" if c["ok"] else "سرخ"}</td></tr>' for c in st["cases"])
    picks = [c for c in st["cases"] if c["id"] in ("fees-kill-edge", "tamper-chain", "position-size")]
    samples = "".join(f'<li><b>{rk.esc(c["title"])}</b>: {rk.esc(c["hand"])}</li>' for c in picks)
    return (f'<p>{badge} · {s["passed"]} از {s["total"]} مورد · موتور '
            f'<code>{rk.esc(st["engine"]["version"])}</code> · اثر انگشت '
            f'<code>{rk.esc(st["engine"]["sha256"])}</code></p>'
            '<table><thead><tr><th>مورد</th><th>عنوان</th><th>چه چیزی را ثابت می‌کند</th>'
            '<th>وضعیت</th></tr></thead><tbody>' + rows + "</tbody></table>"
            f'<p class="honest">سه مورد که خودتان می‌توانید با ماشین‌حساب چک کنید:</p><ul>{samples}</ul>')


def _trial_html(evidence: dict) -> str:
    t = evidence["trial"]
    sc = evidence["scorecard"]
    rows = "".join(f'<tr class="{"pass" if c["ok"] else "fail"}"><td>{rk.esc(c["name"])}</td>'
                   f'<td class="num">{rk.esc(c["have"])}</td><td class="num">{rk.esc(c["want"])}</td>'
                   f'<td>{rk.esc(c["hint"])}</td></tr>' for c in sc["criteria"])
    first = "".join(f'<li><code>{rk.esc(e["hash"])}</code> · {rk.esc(e["symbol"])} · '
                    f'{rk.esc(e["kind"])} · انتظار {rk.esc(e["expected"])} واحد درصد · {rk.esc(e["ts"])}</li>'
                    for e in t["first_rows"]) or "<li>هنوز ردیفی ثبت نشده است.</li>"
    return (f'<p>ردیف‌های ثبت‌شده: <b>{rk.esc(t["entries"])}</b> · بازسنجی‌شده: <b>{rk.esc(t["marked"])}</b> · '
            f'وضعیت زنجیره: <b>{rk.esc(t["chain_message"])}</b></p>'
            '<table><thead><tr><th>شرط کارنامه</th><th class="num">داریم</th><th class="num">لازم</th>'
            '<th>راهنمای عمل</th></tr></thead><tbody>' + rows + "</tbody></table>"
            f'<p class="note">حکم کارنامه: {rk.esc(sc["verdict"])}</p>'
            f'<p class="sub">نمونهٔ ردیف‌های دفتر با هش هر ردیف:</p><ul>{first}</ul>')


def _backtest_html(evidence: dict) -> str:
    b = evidence.get("backtest")
    if not b:
        return '<div class="note">پس‌آزمایی اجرا نشده است.</div>'
    if b.get("error"):
        return f'<div class="note">پس‌آزمایی اجرا نشد: {rk.esc(b["error"])}</div>'
    s = b["summary"]
    pairs = [(k, v) for k, v in s.items() if isinstance(v, (int, float, str))]
    rows = "".join(f'<tr><td><code>{rk.esc(k)}</code></td><td class="num">{rk.esc(v)}</td></tr>'
                   for k, v in pairs)
    return ('<p class="honest">این پس‌آزمایی روی <b>دادهٔ نمونهٔ همراه برنامه</b> اجرا شده است، نه روی '
            'قیمت‌های واقعی بازار؛ عددهایش برای نشان‌دادن «روش» است نه پیش‌بینی سود.</p>'
            '<table><thead><tr><th>کمیت</th><th class="num">مقدار</th></tr></thead><tbody>'
            + rows + "</tbody></table>")


def _data_html(evidence: dict) -> str:
    c = evidence["connection"]
    snap = evidence["snapshot"]
    label = c.get("label") or "تنظیم‌نشده"
    mock = " · خوراک آزمایشی محلی (ساختگی)" if c.get("is_mock") else ""
    rows = [
        ("پروفایل اتصال فعال", f'{label}{mock}'),
        ("محل کلید", c.get("key_where") or "بدون کلید"),
        ("پروندهٔ دادهٔ فعلی", snap["path"]),
        ("تعداد ردیف", snap["rows"]),
        ("تاریخ داده", snap.get("as_of") or "—"),
        ("تأییدشده از سامانهٔ کارگزاری", "بله" if snap.get("confirmed") else "خیر"),
        ("اسنپ‌شات‌های تاریخ‌دار", "، ".join(snap.get("dated_files") or []) or "—"),
    ]
    body = "".join(f'<tr><td>{rk.esc(k)}</td><td class="num">{rk.esc(v)}</td></tr>' for k, v in rows)
    return ('<table><thead><tr><th>مورد</th><th class="num">وضعیت</th></tr></thead><tbody>'
            + body + "</tbody></table>" +
            '<p class="honest">برنامه از بیرون ایران نمی‌تواند به سامانه‌های ایرانی وصل شود؛ '
            'به همین دلیل اتصال روی رایانهٔ خودتان آزمایش می‌شود و نتیجه در همین پرونده می‌نشیند.</p>')


def _verify_html(evidence: dict) -> str:
    rows = "".join(f'<tr><td>{rk.esc(step)}</td><td>{rk.esc(title)}</td>'
                   f'<td><code>{rk.esc(cmd)}</code></td><td>{rk.esc(expect)}</td></tr>'
                   for step, title, cmd, expect in VERIFY_STEPS)
    return ('<table><thead><tr><th>گام</th><th>کار شما</th><th>دستور</th><th>چه می‌بینید</th>'
            '</tr></thead><tbody>' + rows + "</tbody></table>")


def _files_html(evidence: dict) -> str:
    rows = []
    for f in evidence["files"]:
        if f.get("exists"):
            rows.append(f'<tr><td>{rk.esc(f["file"])}</td><td class="num">{rk.esc(f["bytes"])}</td>'
                        f'<td class="num"><code>{rk.esc(f["sha256"])}</code></td>'
                        f'<td class="num">{rk.esc(f["modified"])}</td></tr>')
        else:
            rows.append(f'<tr><td>{rk.esc(f["file"])}</td><td>نیست</td><td>—</td><td>—</td></tr>')
    return ('<table><thead><tr><th>پرونده</th><th class="num">بایت</th>'
            '<th class="num">sha256 (۱۶ رقم اول)</th><th class="num">آخرین تغییر</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table>")


def build_html(evidence: dict) -> str:
    body = [
        '<div class="honest"><b>این پرونده چیست؟</b> یک گزارش راستی‌آزمایی برای تصمیم‌گیری دربارهٔ '
        'خرید داده و شروع کار. هر عددی که می‌بینید از پرونده‌های همان اجرا خوانده شده و '
        'اثر انگشت پرونده‌ها در پایان آمده است. هیچ سود تضمینی و هیچ سفارش خودکاری در کار نیست.</div>',
        _summary_html(evidence),
        "<h2>۱. مسئله‌ای که حل می‌شود</h2>",
        "<p>در بازار مشتقهٔ ایران، گرفتن تصمیم درست به سه چیز بسته است: دیدن قیمت‌های پایه، آتی و اعمال "
        "در یک جا؛ حساب‌کردن بازده خالص با کارمزد و وجه تضمین؛ و نگه‌داشتن سابقهٔ تصمیم‌ها تا معلوم شود "
        "کدام فرصت واقعاً باز ماند. برنامهٔ ایستگاه همین سه کار را با هم انجام می‌دهد: خواندن داده، "
        "محاسبهٔ قاعده‌محور، و ثبت دفتر با هش زنجیره‌ای. تصمیم نهایی و اجرا دست انسان و کارگزاری است.</p>",
        "<h2>۲. قواعد قفل‌شده</h2>",
        "<p>این پارامترها در پروندهٔ تنظیمات نشسته‌اند و در «آزمون ۱۰ دقیقه‌ای» هم تغییر نکرده‌اند؛ "
        "هر تغییری در آن‌ها باید آگاهانه و ثبت‌شده باشد.</p>",
        _rules_html(evidence),
        "<h2>۳. شاهد یک: آزمون ۱۰ دقیقه‌ای</h2>",
        "<p>هر مورد دو بار حساب می‌شود: یک بار با موتور برنامه، یک بار با حساب دستی که همان‌جا در کد "
        "نوشته شده و با ماشین‌حساب قابل چک است. جدا شدن این دو، مورد را سرخ می‌کند.</p>",
        _selftest_html(evidence),
        "<h2>۴. شاهد دو: دفتر آزمون و کارنامه</h2>",
        "<p>دفتر، سابقهٔ زندهٔ برنامه است: هر سیگنال با ساعت، ورودی‌ها و انتظارش ثبت می‌شود و بعداً با "
        "قیمت‌های تازه بازسنجی می‌شود. هر ردیف هشی دارد که به ردیف قبل زنجیر است.</p>",
        _trial_html(evidence),
        "<h2>۵. شاهد سه: پس‌آزمایی روی دادهٔ تاریخ</h2>",
        _backtest_html(evidence),
        "<h2>۶. داده و اتصال</h2>",
        _data_html(evidence),
        "<h2>۷. آنچه ادعا نمی‌کنیم</h2>",
        "<ul>" + "".join(f"<li>{rk.esc(x)}</li>" for x in LIMITATIONS) + "</ul>",
        "<h2>۸. راستی‌آزمایی مستقل توسط شما</h2>",
        _verify_html(evidence),
        "<h2>۹. شناسنامهٔ پرونده‌ها</h2>",
        _files_html(evidence),
    ]
    html = rk.page("پروندهٔ سرمایه‌گذار — ایستگاه تصمیم مشتقه",
                   "".join(body),
                   subtitle=f"ساخته‌شده از شاهدهای اجرای {evidence['built_at']} · "
                            f"نسخهٔ ایستگاه {evidence['version']}")
    return html


def build_markdown(evidence: dict) -> str:
    st = evidence.get("self_test") or {}
    s = st.get("summary") or {}
    sc = evidence["scorecard"]
    lines = [
        "# پروندهٔ سرمایه‌گذار — ایستگاه تصمیم مشتقه",
        "",
        f"ساخته‌شده از شاهدهای اجرای {evidence['built_at']} · نسخهٔ ایستگاه {evidence['version']}",
        "",
        "## خلاصه",
        "",
        f"- آزمون‌های سبز: {s.get('passed', 0)} از {s.get('total', 0)}",
        f"- ردیف‌های دفتر آزمون: {evidence['trial']['entries']} (بازسنجی‌شده: {evidence['trial']['marked']})",
        f"- روزهای ثبت‌شده در کارنامه: {sc['days']} · روز واقعی: {sc['real_days']}",
        f"- زنجیرهٔ هش: {evidence['trial']['chain_message']}",
        f"- حکم کارنامه: {sc['verdict']}",
        "",
        "## قواعد قفل‌شده",
        "",
    ]
    for k, v in evidence["rules"].items():
        lines.append(f"- `{k}` = {v} — {RULE_NOTES.get(k, '')}")
    lines += ["", "## آزمون ۱۰ دقیقه‌ای", ""]
    for c in (st.get("cases") or []):
        lines.append(f"- [{'سبز' if c['ok'] else 'سرخ'}] **{c['title']}**: {c['why']}")
        lines.append(f"  - چک دستی: {c['hand']}")
    lines += ["", "## آنچه ادعا نمی‌کنیم", ""]
    lines += [f"- {x}" for x in LIMITATIONS]
    lines += ["", "## راستی‌آزمایی مستقل", ""]
    lines += [f"{step}. {title}: `{cmd}` → {expect}" for step, title, cmd, expect in VERIFY_STEPS]
    lines += ["", "## شناسنامهٔ پرونده‌ها", ""]
    for f in evidence["files"]:
        lines.append(f"- {f['file']}: " + (f"`{f.get('sha256')}` ({f.get('bytes')} بایت)" if f.get("exists")
                                            else "نیست"))
    lines += ["", "---", "", rk.CREDIT_HTML.replace("<a href=", "[").replace("</a>", "]")]
    return "\n".join(lines) + "\n"


def build(state: dict | None = None, *, out: Path | None = None, write_md: bool = True,
          run_selftest: bool = True) -> dict:
    """پرونده را می‌سازد: HTML + Markdown + JSON ماشین‌خوان. مسیرها را برمی‌گرداند."""
    evidence = collect(state, run_selftest=run_selftest)
    html = build_html(evidence)
    out_html = Path(out or (DATA / "investor-dossier.html"))
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html, encoding="utf-8")
    paths = {"html": str(out_html), "md": None, "json": None,
             "sha256": rk.sha256_text(html)[:16],
             "summary": {"selftest": (evidence.get("self_test") or {}).get("summary"),
                         "chain_ok": evidence["trial"]["chain_ok"],
                         "scorecard_ready": evidence["scorecard"]["ready"],
                         "entries": evidence["trial"]["entries"]}}
    if write_md:
        md_path = out_html.with_suffix(".md")
        md_path.write_text(build_markdown(evidence), encoding="utf-8")
        paths["md"] = str(md_path)
    json_path = out_html.with_suffix(".json")
    json_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["json"] = str(json_path)
    return paths


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=f"پروندهٔ سرمایه‌گذار — نسخه {VERSION}")
    ap.add_argument("--out", help="مسیر پروندهٔ HTML (پیش‌فرض: data/investor-dossier.html)")
    ap.add_argument("--json", action="store_true", help="شاهدهای خام را چاپ کن")
    ap.add_argument("--no-md", action="store_true", help="نسخهٔ متنی نساز")
    ap.add_argument("--no-selftest", action="store_true", help="آزمون را دوباره اجرا نکن")
    ap.add_argument("--open", action="store_true", help="پرونده را در مرورگر باز کن")
    ap.add_argument("--version", action="version", version=VERSION)
    args = ap.parse_args(argv)

    if args.json:
        print(json.dumps(collect(run_selftest=not args.no_selftest), ensure_ascii=False, indent=2))
        return 0

    res = build(out=Path(args.out) if args.out else None, write_md=not args.no_md,
                run_selftest=not args.no_selftest)
    print("پروندهٔ سرمایه‌گذار ساخته شد:")
    for key in ("html", "md", "json"):
        if res.get(key):
            print(f"  {key}: {res[key]}")
    print(f"  اثر انگشت (sha256، ۱۶ رقم اول): {res['sha256']}")
    s = res["summary"]
    st = s.get("selftest") or {}
    print(f"  آزمون: {st.get('passed', 0)}/{st.get('total', 0)} · زنجیره: "
          f"{'سالم' if s['chain_ok'] else 'شکسته'} · کارنامه: {'آماده' if s['scorecard_ready'] else 'ناتمام'}")
    if args.open:
        import webbrowser
        webbrowser.open(Path(res["html"]).as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
