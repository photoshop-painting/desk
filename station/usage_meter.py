#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""دفتر استفادهٔ موفق + گواهی دواِمضا با زنجیرهٔ هش (نسخهٔ ۰.۱.۰).

ایدهٔ شما: هر کار موفقی که برنامه انجام می‌دهد جایی ثبت شود تا معلوم شود کارفرما چقدر از آن
استفادهٔ موفق داشته؛ و بعد بشود «درصد» گرفت.

جواب صادقانه:
  ۱) **ثبت کار** — هر کار موفق (اجرای موتور، داوری سیگنال، تصمیم، شاهد، بستهٔ شرکت، …) با نوع،
     زمان و زنجیرهٔ هش ثبت می‌شود. دفتر **فقط محلی** است و **عدد مالی در آن نمی‌نشیند**
     (`privacy_check` همین را بازمی‌سنجد: قیمت، سود، موجودی، شمارهٔ حساب ممنوع).
  ۲) **درصد از سود؟ نه** — سود بازار تضمینی نیست؛ سهم‌بردن از سود، هم اندازه‌گیری‌اش بیرون از دست ما
     است، هم انگیزه را به سمت ریسک درشت می‌برد. جایگزین‌های قابل راستی‌آزمایی: اشتراک ماهانه،
     اشتراک به‌ازای «روز فعال» (عددش از همین دفتر می‌آید) و پاداش برای هر برگهٔ شاهد.
  ۳) **اثبات استفاده** — گواهی دواِمضا که زنجیرهٔ هش دفتر را نشان می‌دهد؛ هر کسی با یک فرمان
     بازتولیدش می‌کند.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import reportkit as rk  # noqa: E402

VERSION = "0.1.0"
DATA = BASE / "data"
LEDGER = DATA / "usage-ledger.json"
STATEMENT_HTML = DATA / "usage-statement.html"
STATEMENT_MD = DATA / "usage-statement.md"

# نوع کارهایی که کارساز/رابط گرافیکی ثبت می‌کنند (کلید انگلیسی می‌ماند تا روایت عوض نشود).
KIND_LABELS = {
    "run": "اجرای موتور روی دادهٔ روز",
    "judge": "داوری سیگنال (می‌ماند یا می‌افتد)",
    "decision": "تصمیم ثبت‌شده (خرید/فروش/رد)",
    "ritual": "مراسم روزانهٔ شصت‌ثانیه‌ای",
    "exam": "آزمون ۱۰ دقیقه‌ای ایستگاه",
    "bundle": "بستهٔ شاهد شرکت",
    "blind": "آزمون کور سرمایه‌گذار",
    "witness": "برگهٔ شاهد زندهٔ داده",
    "ladder": "پلهٔ تصمیم (چه بخرم/کِی بفروشم)",
    "pledge": "پیمان‌نامهٔ نمایش",
    "license": "مجوز دسترسی و پشتیبانی",
    "offer": "پیشنهاد یک‌صفحه‌ای به شرکت",
    "outreach": "پیام معرفی و پیگیری",
    "prospect": "تابلوی پیگیری مخاطبان",
    "onboarding": "روز اول مشتری",
    "sales": "مراسم فروش امروز",
    "review": "جلسهٔ بازبینی دو هفته",
    "dossier": "پروندهٔ سرمایه‌گذار",
    "snapshot": "ثبت اعداد روز",
    "import": "ورود اعداد از متن کارگزاری",
    "strategy": "برگهٔ راهبردها و شوک‌آزمون",
    "math": "ریاضیِ بقا و مسیر رشد",
}

# نام‌های ممنوع در دفتر: هیچ‌کدام نباید به‌عنوان کلید در دفتر ظاهر شود.
FINANCIAL_KEYS = ("price", "spot", "strike", "premium", "balance", "account", "profit",
                  "loss", "pnl", "payoff", "capital", "margin", "position", "shares",
                  "wallet", "card", "iban", "sheba", "مبلغ", "سود", "موجودی")

MINUTE_VALUE_RIAL = 1_500_000   # فرضِ صریح برای «ارزش کار» (نه ادعا)

_STRIP = (
    (re.compile(r"\b\d{1,3}(?:[٬,]\d{3})+\b"), "‹عدد›"),
    (re.compile(r"\b\d{7,}\b"), "‹عدد›"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "‹نشانی›"),
    (re.compile(r"(?:\+?98|0)\d{9,10}"), "‹تلفن›"),
)


# ------------------------------------------------------------------ ابزار پایه

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean(text, limit: int) -> str:
    out = " ".join(str(text if text is not None else "").split())
    for pat, rep in _STRIP:
        out = pat.sub(rep, out)
    return out[:limit]


def _fingerprint(rec: dict, prev: str) -> str:
    payload = json.dumps({k: v for k, v in rec.items() if k != "chain"},
                         ensure_ascii=False, sort_keys=True)
    return hashlib.sha256((prev + payload).encode("utf-8")).hexdigest()[:16]


def rows(path: Path | str | None = None) -> list[dict]:
    """سطرهای دفتر. اگر فایل نبود یا خراب بود، فهرست خالی (نه خطا)."""
    p = Path(path or LEDGER)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def record(kind: str, label: str = "", note: str = "", *, when: str | None = None,
           path: Path | str | None = None) -> dict:
    """یک کار موفق را ثبت می‌کند. نوع ناشناخته رد می‌شود تا دفتر بی‌معنی نشود."""
    if kind not in KIND_LABELS:
        raise KeyError(f"نوع ناشناخته «{kind}»؛ نوع‌های مجاز: {'، '.join(KIND_LABELS)}")
    p = Path(path or LEDGER)
    p.parent.mkdir(parents=True, exist_ok=True)
    chain = rows(p)
    prev = chain[-1].get("chain", "0" * 16) if chain else "0" * 16
    rec = {"ts": when or now_iso(), "kind": kind, "label": _clean(label, 80),
           "note": _clean(note, 120)}
    rec["chain"] = _fingerprint(rec, prev)
    chain.append(rec)
    p.write_text(json.dumps(chain, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def record_event(kind: str, label: str = "", note=None, *, when: str | None = None,
                 path: Path | str | None = None) -> dict:
    """نامی که کارساز صدا می‌زند؛ در برابر برچسب خالی/None هم مقاوم است."""
    return record(kind, label or "", "" if note is None else note, when=when, path=path)


def verify(path: Path | str | None = None) -> dict:
    """زنجیرهٔ هش را بازمی‌سنجد: آیا سطری بعد از ثبت عوض شده است؟"""
    chain = rows(path)
    prev = "0" * 16
    for i, rec in enumerate(chain, start=1):
        if _fingerprint(rec, prev) != rec.get("chain"):
            return {"ok": False, "rows": len(chain), "broken_at": i, "chain": prev,
                    "detail": (f"ردیف {i} با اثر انگشت زنجیره نمی‌خواند؛ یعنی بعد از ثبت عوض "
                               f"شده است.")}
        prev = rec.get("chain", prev)
    return {"ok": True, "rows": len(chain), "broken_at": None, "chain": prev,
            "detail": ("اثر انگشت زنجیرهٔ دفتر سالم است؛ هیچ ردیفی بعد از ثبت عوض نشده."
                       if chain else "دفتر خالی است؛ هنوز کاری ثبت نشده.")}


def verify_chain(path: Path | str | None = None) -> dict:
    return verify(path)


def privacy_check(path: Path | str | None = None) -> dict:
    """دفتر نباید هیچ عدد یا نام مالی داشته باشد. این بازرسی، خودش شاهد است."""
    bad: list[str] = []
    for rec in rows(path):
        for key in rec:
            low = str(key).strip().lower()
            if low in FINANCIAL_KEYS and low not in bad:
                bad.append(low)
    return {"clean": not bad, "offending_keys": bad, "checked_keys": list(FINANCIAL_KEYS),
            "detail": ("دفتر پاکیزه است: هیچ کلید مالی (قیمت/سود/موجودی/حساب) در آن نیست."
                       if not bad else
                       "در دفتر کلید مالی پیدا شد: " + "، ".join(bad) +
                       " — این کلیدها باید بروند، وگرنه دفتر به دفتر سرمایه تبدیل می‌شود.")}


def day_of(rec: dict) -> str:
    return str(rec.get("ts", ""))[:10]


def summary(path: Path | str | None = None, *, trial_days: int | None = None,
            real_days: int | None = None, now: datetime | None = None) -> dict:
    """چکیدهٔ استفاده: شمارش کل، امروز، هفت روز، روزهای فعال، به‌تفکیک نوع کار."""
    chain = rows(path)
    ref = now or datetime.now(timezone.utc)
    today = ref.date().isoformat()
    week_ago = (ref.date() - timedelta(days=6)).isoformat()
    by_kind: dict[str, int] = {}
    for rec in chain:
        k = rec.get("kind", "?")
        by_kind[k] = by_kind.get(k, 0) + 1
    days = sorted({day_of(r) for r in chain if day_of(r)})
    chain_state = verify(path)
    return {
        "version": VERSION,
        "total": len(chain), "success_total": len(chain), "rows": len(chain),
        "today": sum(1 for r in chain if day_of(r) == today),
        "last_7_days": sum(1 for r in chain if day_of(r) >= week_ago),
        "active_days": len(days), "days": days,
        "first_day": days[0] if days else "", "last_day": days[-1] if days else "",
        "by_kind": by_kind,
        "by_kind_label": {KIND_LABELS.get(k, k): v
                          for k, v in sorted(by_kind.items(), key=lambda x: -x[1])},
        "verify": chain_state, "chain_ok": chain_state["ok"],
        "broken_at": chain_state["broken_at"], "last_chain": chain_state.get("chain", ""),
        "kept_local": True, "privacy": privacy_check(path),
        "trial_days": trial_days, "real_days": real_days,
        "ledger": str(path or LEDGER), "generated_at": now_iso(),
    }


def avoided_cost(s: dict, *, minute_value_rial: int = MINUTE_VALUE_RIAL,
                 minutes_per_work: int = 5) -> dict:
    """ارزش تقریبی کار انجام‌شده، با فرض صریح (نه ادعا)."""
    minutes = int(s.get("success_total", 0)) * minutes_per_work
    return {"assumed_minute_value_rial": minute_value_rial,
            "assumed_minutes_per_work": minutes_per_work,
            "assumed_value_rial": minutes * minute_value_rial,
            "note": (f"این عدد فرض است، نه واقعیت: {minute_value_rial:,} ریال برای هر دقیقه کار "
                     f"انسانی و {minutes_per_work} دقیقه برای هر کار. اگر این فرض قبول نشود، "
                     f"فقط ستون شمارش و اثر انگشت زنجیره بماند.")}


def percent_model(*, monthly_price_rial: int = 0, active_days_price_rial: int = 0,
                  bonus_per_witness_rial: int = 0) -> dict:
    """پاسخ صادقانه به «درصدی از سود بگیرم؟» + سه جایگزین قابل راستی‌آزمایی."""
    return {
        "percent_of_profit": {
            "verdict": "رد می‌کنم",
            "why": ("۱) سود بازار تضمینی نیست؛ «درصد از سود» یعنی تقسیم چیزی که ممکن است نباشد. "
                    "۲) اندازه‌گیری سود مشتری به دفتر سرمایه و اعتماد او گره می‌خورد و از دست ما "
                    "بیرون است. ۳) انگیزه را به ریسک درشت می‌برد: اگر روی سود شریک باشی، زیان را "
                    "طرف مقابل تنها می‌کشد."),
            "when_it_makes_sense": ("فقط اگر خودِ مشتری بخواهد و حساب شاهددار باشد؛ سال اول "
                                    "هیچ‌وقت."),
        },
        "alternatives": [
            {"name": "اشتراک ماهانه", "price_rial": monthly_price_rial,
             "who": "شرکت/کارگزاری که برنامه را روزانه به کار می‌برد.",
             "verifiable": "تاریخ پرداخت، نه ادعای سود."},
            {"name": "اشتراک به‌ازای روز فعال", "price_rial": active_days_price_rial,
             "who": "کسی که بعضی روزها کار می‌کند؛ از ماهانهٔ ثابت منصفانه‌تر است.",
             "verifiable": "«روزهای فعال» همین دفتر، عدد قابل بازتولید است."},
            {"name": "پاداش به‌ازای شاهد", "price_rial": bonus_per_witness_rial,
             "who": "برای هر برگهٔ شاهد زنده یا آزمون کور که تحویل داده می‌شود.",
             "verifiable": "برگه اثر انگشت دارد؛ هر دو طرف می‌توانند بسنجند."},
        ],
        "honesty": ("هیچ‌کدام «درصد موفقیت بازار» نیست. دفتر استفاده می‌گوید چند کار انجام شد، نه "
                    "چند ریال سود. اگر کسی درصد سود وعده بدهد، همان لحظه باید به او شک کرد."),
    }


# ------------------------------------------------------------------ گواهی

def build_statement(s: dict, *, client: str = "", period: str = "",
                    html_path: Path | str | None = None, md_path: Path | str | None = None,
                    minute_value_rial: int = MINUTE_VALUE_RIAL) -> tuple[Path, Path]:
    """گواهی استفاده: دو امضا + اثر انگشت زنجیره. خروجی: (مسیر HTML، مسیر متن)."""
    hp = Path(html_path) if html_path else STATEMENT_HTML
    mp = Path(md_path) if md_path else STATEMENT_MD
    hp.parent.mkdir(parents=True, exist_ok=True)
    mp.parent.mkdir(parents=True, exist_ok=True)
    verify_state = s.get("verify") or verify()
    cost = avoided_cost(s, minute_value_rial=minute_value_rial)
    stamp = s.get("generated_at") or now_iso()
    client_txt = client.strip() or "________________"
    period_txt = period.strip() or f"از ابتدا تا {stamp[:10]}"
    rows_md = [f"| {KIND_LABELS.get(k, k)} | `{k}` | {v} |" for k, v in s["by_kind"].items()]
    if not rows_md:
        rows_md = ["| — | — | 0 |"]
    chain_line = ("اثر انگشت زنجیرهٔ دفتر: سالم ✅" if verify_state["ok"]
                  else f"اثر انگشت زنجیرهٔ دفتر: شکسته ⚠️ (ردیف {verify_state['broken_at']})")
    md = "\n".join([
        f"# گواهی استفادهٔ موفق — نسخهٔ {VERSION}", "",
        f"**کارفرما/سرمایه‌گذار:** {client_txt}", "",
        f"**دوره:** {period_txt}", "",
        f"مجموع کارهای ثبت‌شده: **{s.get('success_total', 0)}**", "",
        "| نوع کار | کلید | تعداد |", "| --- | --- | --- |", *rows_md, "",
        f"- امروز: {s.get('today', 0)} · هفت روز گذشته: {s.get('last_7_days', 0)} · "
        f"روزهای فعال: {s.get('active_days', 0)}",
        f"- اولین روز: {s.get('first_day') or '—'} · آخرین روز: {s.get('last_day') or '—'}",
        (f"- روزهای تمرینی ثبت‌شده: {s['trial_days']} · روزهای واقعی ثبت‌شده: {s['real_days']}"
         if s.get("trial_days") is not None or s.get("real_days") is not None else
         "- روزهای تمرینی/واقعی: تفکیک نشده"),
        f"- **{chain_line}** · کلید آخر: `{s.get('last_chain') or '—'}`",
        f"- دفتر استفاده، فقط روی همین رایانه: `{s.get('ledger', LEDGER)}`", "",
        "## این گواهی چه چیزی را اثبات نمی‌کند", "",
        "- **سود** را اثبات نمی‌کند؛ هیچ عدد مالی در دفتر نیست و ثبت هم نمی‌شود.",
        "- **درستی تصمیم‌های بازار** را اثبات نمی‌کند؛ آن را فقط پروندهٔ سود و آزمون کور نشان می‌دهد.",
        "- «درصد موفقیت» به‌معنای «موفقیت در بازار» نیست؛ فقط شمارش کارهای انجام‌شده است.", "",
        f"ارزش فرضی کار (اگر بخواهید): {cost['assumed_value_rial']:,} ریال — {cost['note']}", "",
        "## بازبینی در یک فرمان", "",
        "```bash", "cd MATERIALS/money/gui && python3 usage_meter.py --summary --verify", "```", "",
        "---", "",
        "امضای ارائه‌دهنده: ____________________     "
        "امضای کاربر/شرکت: ____________________", "",
        f"دولوپر: مهندس مسعود مجربیان · همراه: 09126630554 · Telegram: Mojarabian",
        "✍️ تهیه‌کنندهٔ جزوات: Masoud Mojarabian · 📱 +989126630554 · "
        "✈️ Telegram: Mojarabian · 📸 Instagram: Mojarabian.Art", "",
    ])
    mp.write_text(md, encoding="utf-8")

    table_html = "".join(f'<tr><td>{rk.esc(KIND_LABELS.get(k, k))}</td><td><code>{rk.esc(k)}</code>'
                         f'</td><td class="num">{v}</td></tr>' for k, v in s["by_kind"].items())
    if not table_html:
        table_html = '<tr><td colspan="3" class="hint">هنوز کاری ثبت نشده است.</td></tr>'
    body = "".join([
        '<div class="honest"><b>این گواهی «درصد موفقیت بازار» نیست.</b> فقط می‌گوید چه کاری، چند بار،'
        ' در چه روزهایی انجام شد — با اثری که دست‌کاری را لو می‌دهد. هیچ عدد مالی در دفتر نیست.</div>',
        f'<p class="sub">کارفرما/سرمایه‌گذار: <b>{rk.esc(client_txt)}</b> · دوره: {rk.esc(period_txt)}'
        f' · ساخته‌شده: {rk.esc(stamp)}</p>',
        '<h2>۱. شمارش کارهای موفق</h2>',
        f'<table><thead><tr><th>نوع کار</th><th>کلید</th><th class="num">تعداد</th></tr></thead>'
        f'<tbody>{table_html}</tbody><tfoot><tr><td colspan="2"><b>مجموع</b></td>'
        f'<td class="num"><b>{s.get("success_total", 0)}</b></td></tr></tfoot></table>',
        '<h2>۲. روزهای فعالیت</h2>',
        f'<p>امروز: <b>{s.get("today", 0)}</b> · هفت روز گذشته: {s.get("last_7_days", 0)} · '
        f'روزهای فعال: <b>{s.get("active_days", 0)}</b> · اولین روز: {rk.esc(s.get("first_day") or "—")}'
        f' · آخرین روز: {rk.esc(s.get("last_day") or "—")}</p>',
        '<h2>۳. اثر انگشت زنجیرهٔ دفتر</h2>',
        (f'<p>سالم ✅ — {rk.esc(verify_state["detail"])}<br>کلید آخر: '
         f'<code>{rk.esc(s.get("last_chain") or "—")}</code></p>' if verify_state["ok"] else
         f'<p>شکسته ⚠️ — {rk.esc(verify_state["detail"])}</p>'),
        '<h2>۴. این گواهی چه می‌گوید و چه نمی‌گوید</h2>',
        '<ul><li><b>می‌گوید:</b> چند کار موفق، در چه روزهایی، و اینکه دفتر بعد از ثبت دست‌کاری نشده.</li>'
        '<li><b>نمی‌گوید:</b> سود، درستی تصمیم بازار، یا درصد موفقیت در معامله. هیچ عدد مالی در دفتر '
        'نیست.</li></ul>',
        f'<h2>۵. ارزش فرضی کار (اختیاری)</h2><p>{cost["assumed_value_rial"]:,} ریال — '
        f'<span class="hint">{rk.esc(cost["note"])}</span></p>',
        '<h2>۶. بازبینی مستقل</h2><p class="note">هر کسی می‌تواند با '
        '<code>python3 usage_meter.py --summary --verify</code> همین عددها را بازتولید کند.</p>',
        '<p class="sub">امضای ارائه‌دهنده: ____________________ &nbsp;&nbsp; '
        'امضای کاربر/شرکت: ____________________</p>',
        '<p class="sub">دولوپر: <b>مهندس مسعود مجربیان</b> · همراه: <a href="tel:+989126630554">09126630554</a> · Telegram: <a href="https://t.me/Mojarabian" target="_blank">Mojarabian</a> · Instagram: <a href="https://instagram.com/Mojarabian.Art" target="_blank">Mojarabian.Art</a></p>',
        '<p class="sub">✍️ تهیه‌کنندهٔ جزوات: <b>Masoud Mojarabian</b> · 📱 +989126630554 · '
        '✈️ <a href="https://t.me/Mojarabian">Telegram: Mojarabian</a> · '
        '📸 <a href="https://instagram.com/Mojarabian.Art">Instagram: Mojarabian.Art</a></p>',
    ])
    hp.write_text(rk.page("گواهی استفادهٔ موفق", body,
                          subtitle=f"{s.get('success_total', 0)} کار موفق · "
                                   f"{s.get('active_days', 0)} روز فعال · نسخهٔ {VERSION}"),
                  encoding="utf-8")
    return hp, mp


# ------------------------------------------------------------------ خط فرمان

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="دفتر استفادهٔ موفق + گواهی زنجیره‌هش‌دار")
    ap.add_argument("--record", metavar="KIND", help=f"ثبت یک کار. نوع‌ها: {', '.join(KIND_LABELS)}")
    ap.add_argument("--label", default="")
    ap.add_argument("--note", default="")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--statement", action="store_true")
    ap.add_argument("--client", default="")
    ap.add_argument("--period", default="")
    ap.add_argument("--percent-model", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if a.record:
        try:
            rec = record(a.record, a.label, a.note)
        except KeyError as e:
            print("خطا:", e)
            return 1
        print("ثبت شد:", json.dumps(rec, ensure_ascii=False))
        return 0

    if a.percent_model:
        print(json.dumps(percent_model(), ensure_ascii=False, indent=1))
        return 0

    if a.statement:
        h, m = build_statement(summary(), client=a.client, period=a.period)
        print("گواهی ساخته شد:", h)
        print("نسخهٔ متنی برای ایمیل:", m)
        return 0

    s = summary()
    if a.json:
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return 0

    print(f"دفتر استفادهٔ موفق — نسخهٔ {VERSION}")
    print(f"  کار موفق: {s['success_total']} · امروز {s['today']} · هفت روز {s['last_7_days']} · "
          f"روزهای فعال {s['active_days']}")
    for k, v in s["by_kind_label"].items():
        print(f"    · {k}: {v}")
    print(f"  دفتر (فقط محلی): {s['ledger']}")
    print(f"  حریم: {s['privacy']['detail']}")
    if a.verify:
        print(f"  زنجیرهٔ دفتر: {s['verify']['detail']}")
        return 0 if s["verify"]["ok"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
