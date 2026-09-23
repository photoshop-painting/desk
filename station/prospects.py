"""تابلوی پیگیری مخاطبان — همان «پنج نام» هفتگی که سند ۱۴ می‌گوید.

چرا این ابزار: سند `14-first-meeting-fa.md` یک ریتم هفتگی دارد (پنج مخاطب، پیام، پیگیری روز ۳ و
روز ۱۰) و سه عدد که هر هفته باید شمرده شود. انجام دادنش با دفتر کاغذی ممکن است، ولی خیلی زود
«کی را باید پیگیری کنم؟» از دست می‌رود. این ابزار فقط همان کار را می‌کند و بس:

- فهرست محلی مخاطبان روی همین رایانه (هیچ شبکه‌ای در کار نیست).
- می‌گوید **امروز** چه کسی پیگیری لازم دارد (روز ۳، روز ۱۰، قرار جلسه، ثبت نتیجه).
- سه عدد هفته را می‌شمارد: چند پیام، چند تماس، چند جلسه.
- یک برگهٔ چاپی «تابلوی پیگیری» می‌سازد تا روی میز باشد.

قاعده‌های اخلاقی که در خودِ ابزار قفل شده‌اند: پیگیری فقط سه بار (روز ۰، ۳، ۱۰) · هیچ فوریت
ساختگی · هیچ شمارهٔ تلفنی در دفتر ذخیره نمی‌شود (شماره جای دیگری است، این‌جا فقط نام و وضعیت) ·
«بعداً» بی‌تاریخ نمی‌مانَد: سی روز بعد، همان روز به «کار امروز» برمی‌گردد (یک پیام، نه بیشتر).

اجرا:
    python3 prospects.py --add "نام مخاطب" --kind brokerage --channel telegram
    python3 prospects.py --sent "نام مخاطب"
    python3 prospects.py --reply "نام مخاطب" --note "پرسید داده از کجاست"
    python3 prospects.py --meeting "نام مخاطب" --date 2026-09-27
    python3 prospects.py --outcome "نام مخاطب" --result بله
    python3 prospects.py --outcome "نام مخاطب" --result بعداً --next-on 2026-10-22
    python3 prospects.py --todo            # امروز چه کسی را پیگیری کنم
    python3 prospects.py --week            # سه عدد این هفته
    python3 prospects.py --sheet           # برگهٔ چاپی تابلوی پیگیری
"""
from __future__ import annotations

import argparse
import json
import os
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
STORE = Path(os.environ.get("IRAN_DESK_PROSPECTS") or (DATA / "prospects.json"))
SHEET_MD = DATA / "prospects-board.md"
SHEET_HTML = DATA / "prospects-board.html"

# کانال‌ها و لحن‌ها همان چیزهایی است که سند ۱۴ و بستهٔ پیام‌ها می‌شناسند
CHANNELS = {"telegram": "تلگرام", "whatsapp": "واتساپ", "phone": "تلفن",
            "inperson": "حضوری", "linkedin": "لینکدین", "email": "ایمیل"}
KINDS = {"brokerage": "کارگزاری / تأمین سرمایه", "company": "شرکت غیرمالی",
         "teacher": "مدرس یا تحلیلگر", "known": "آشنای بازار", "university": "دانشگاه / انجمن علمی"}
RESULTS = ("بله", "نه", "بعداً", "بی‌جواب")
FOLLOWUP_DAYS = (3, 10)          # فقط دو پیگیری؛ بار سوم یعنی «ببند»
LATER_DAYS = 30                  # «بعداً» یعنی سی روز دیگر سر بزن؛ بی‌تاریخ، فراموش می‌شود
WEEKLY_TARGET = {"messages": 5, "calls": 1, "meetings": 1}

_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa(value) -> str:
    return str(value).translate(_DIGITS)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _iso(d: date) -> str:
    return d.isoformat()


def _parse(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


# ------------------------------------------------------------------ انبار محلی

def load(path: Path | str | None = None) -> list[dict]:
    p = Path(path) if path else STORE
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    rows = data if isinstance(data, list) else data.get("prospects", [])
    return [r for r in rows if isinstance(r, dict) and r.get("name")]


def save(rows: list[dict], path: Path | str | None = None) -> Path:
    p = Path(path) if path else STORE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return p



_MASK = (
    (re.compile(r"\b\d{1,3}(?:[٬,]\d{3})+\b"), "‹عدد›"),      # عدد جداکننده‌دار (مبلغ)
    (re.compile(r"\b\d{7,}\b"), "‹عدد›"),                      # عدد بلند (شمارهٔ حساب/تلفن)
    (re.compile(r"(?:\+?98|0)\d{9,10}"), "‹تلفن›"),              # شمارهٔ تلفن
)


def clean_note(text: str) -> str:
    """یادداشت را از عدد و شماره پاک می‌کند؛ این دفتر محلی است و نباید جای دادهٔ حساس شود."""
    out = (text or "").strip()[:200]
    for pat, rep in _MASK:
        out = pat.sub(rep, out)
    return out


def _find(rows: list[dict], name: str) -> dict | None:
    name = name.strip()
    for r in rows:
        if r.get("name") == name:
            return r
    return None


def add(name: str, *, kind: str = "company", channel: str = "telegram",
        note: str = "", path: Path | str | None = None, when: str | None = None) -> dict:
    """مخاطب تازه. نام تکراری ساخته نمی‌شود."""
    name = (name or "").strip()
    if not name:
        raise ValueError("نام مخاطب خالی است.")
    rows = load(path)
    if _find(rows, name):
        return {"ok": False, "detail": f"«{name}» از قبل در تابلو هست.", "row": _find(rows, name)}
    row = {"name": name, "kind": kind if kind in KINDS else "company",
           "channel": channel if channel in CHANNELS else "telegram",
           "note": clean_note(note), "created": _iso(_parse(when) or _today()),
           "sent": None, "followup": [], "replied": None, "meeting": None, "result": None,
           "history": []}
    rows.append(row)
    save(rows, path)
    return {"ok": True, "row": row, "count": len(rows)}


def mark(name: str, event: str, *, when: str | None = None, note: str = "",
         result: str = "", next_on: str | None = None,
         path: Path | str | None = None) -> dict:
    """یک گام را ثبت می‌کند: sent | followup | reply | meeting | outcome."""
    rows = load(path)
    row = _find(rows, name)
    if not row:
        return {"ok": False, "detail": f"«{name}» در تابلو نیست."}
    day = _parse(when) or _today()
    stamp = _iso(day)
    if event == "sent":
        row["sent"] = row.get("sent") or stamp
        row.setdefault("history", []).append(f"پیام اول — {stamp}")
    elif event == "followup":
        # فقط دو پیگیری؛ بار سوم رد می‌شود (قاعدهٔ سند ۱۴)
        if len(row.get("followup") or []) >= len(FOLLOWUP_DAYS):
            return {"ok": False, "detail": "دو پیگیری ثبت شده؛ قاعده این است که ببندی و رهایش کنی.",
                    "row": row}
        row.setdefault("followup", []).append(stamp)
        row.setdefault("history", []).append(f"پیگیری {len(row['followup'])} — {stamp}")
    elif event == "reply":
        row["replied"] = stamp
        if note:
            row["note"] = clean_note(note)
        row.setdefault("history", []).append(f"جواب داد — {stamp}" + (f" · {note}" if note else ""))
    elif event == "meeting":
        row["meeting"] = stamp
        row.setdefault("history", []).append(f"جلسه — {stamp}")
    elif event == "outcome":
        if result not in RESULTS:
            return {"ok": False, "detail": f"نتیجه باید یکی از این‌ها باشد: {' · '.join(RESULTS)}",
                    "row": row}
        row["result"] = result
        if result == "بعداً":
            # «بعداً» بی‌تاریخ یعنی فراموشی؛ پس تاریخ سر‌زدن هم ثبت می‌شود
            back = _parse(next_on) if next_on else (day + timedelta(days=LATER_DAYS))
            if not back:
                return {"ok": False, "detail": "تاریخ سر‌زدن خوانده نشد؛ قالب: YYYY-MM-DD",
                        "row": row}
            row["next_on"] = _iso(back)
            row.setdefault("history", []).append(
                f"نتیجه: بعداً — {stamp} · سر زدن: {_iso(back)}" + (f" · {note}" if note else ""))
        else:
            row.pop("next_on", None)
            row.setdefault("history", []).append(f"نتیجه: {result} — {stamp}"
                                                 + (f" · {note}" if note else ""))
    else:
        return {"ok": False, "detail": f"گام ناشناخته: {event}"}
    save(rows, path)
    return {"ok": True, "row": row, "event": event, "when": stamp}



def _within(value: str | None, start: date, end: date) -> bool:
    """آیا این تاریخ (رشته) داخل بازه است؟ رشتهٔ خراب یا خالی، «نه» است."""
    d = _parse(value)
    return bool(d) and start <= d <= end


def todo(rows: list[dict] | None = None, *, on: str | None = None,
         path: Path | str | None = None) -> list[dict]:
    """امروز چه کاری برای چه کسی لازم است (بر پایهٔ روز ۳ و روز ۱۰)."""
    rows = rows if rows is not None else load(path)
    day = _parse(on) or _today()
    out: list[dict] = []
    for r in rows:
        if r.get("result"):
            if r["result"] == "بعداً":
                back = _parse(r.get("next_on")) or ((_parse(r.get("created")) or day)
                                                    + timedelta(days=LATER_DAYS))
                if day >= back:
                    out.append({"name": r["name"],
                                "action": "روز موعود رسید — یک پیام صادقانه بفرست",
                                "why": f"قرار بود {fa(_iso(back))} سر بزنیم و کارشان را ببینیم.",
                                "urgent": (day - back).days >= 7})
            continue
        sent = _parse(r.get("sent"))
        fups = [d for d in (_parse(x) for x in (r.get("followup") or [])) if d]
        if r.get("meeting"):
            mday = _parse(r["meeting"])
            if day >= mday:
                out.append({"name": r["name"], "action": "نتیجهٔ جلسه را ثبت کن",
                            "why": f"جلسه {fa(mday.isoformat())} بود.", "urgent": day > mday})
            continue
        if not sent and not r.get("replied"):
            out.append({"name": r["name"], "action": "پیام اول را بفرست",
                        "why": f"از {fa(r.get('created', '—'))} در تابلو است و هنوز پیامی نرفته.",
                        "urgent": (day - (_parse(r.get("created")) or day)).days >= 2})
            continue
        if r.get("replied") and not r.get("meeting"):
            out.append({"name": r["name"], "action": "قرار جلسه را بگذار",
                        "why": f"روز {fa((day - _parse(r['replied'])).days)} پیش جواب داد.",
                        "urgent": (day - _parse(r["replied"])).days >= 2})
            continue
        # هنوز جوابی نداده: نوبت پیگیری است؟
        if sent is None:                     # جواب داده ولی «پیام اول» ثبت نشده
            out.append({"name": r["name"], "action": "قرار جلسه را بگذار",
                        "why": "جواب داده است؛ ثبت «پیام اول» جا افتاده، ولی کار بعدی روشن است.",
                        "urgent": False})
            continue
        gap = (day - sent).days
        for i, need in enumerate(FOLLOWUP_DAYS):
            if gap >= need and len(fups) <= i:
                out.append({"name": r["name"],
                            "action": f"پیگیری {fa(i + 1)} (روز {fa(need)})",
                            "why": f"{fa(gap)} روز از پیام اول گذشته و جوابی نیامده.",
                            "urgent": gap >= need + 3})
                break
        else:
            if len(fups) >= len(FOLLOWUP_DAYS) and gap > FOLLOWUP_DAYS[-1] + 7:
                out.append({"name": r["name"], "action": "ببند و رهایش کن",
                            "why": f"{fa(gap)} روز و دو پیگیری؛ قاعده می‌گوید بس است.",
                            "urgent": False})
    return sorted(out, key=lambda x: (not x["urgent"], x["name"]))


def week_numbers(rows: list[dict] | None = None, *, on: str | None = None,
                 path: Path | str | None = None) -> dict:
    """سه عدد هفته: پیام فرستاده‌شده، تماس، جلسه — با هدف هفتگی."""
    rows = rows if rows is not None else load(path)
    day = _parse(on) or _today()
    since = day - timedelta(days=6)
    messages, followups, calls, meetings, replies = [], [], [], [], []
    for r in rows:
        name = r["name"]
        if _within(r.get("sent"), since, day):
            messages.append(name)
            if r.get("channel") == "phone":
                calls.append(name)
        if any(_within(x, since, day) for x in (r.get("followup") or [])):
            followups.append(name)
        if _within(r.get("meeting"), since, day):
            meetings.append(name)
        if _within(r.get("replied"), since, day):
            replies.append(name)
    return {"from": _iso(since), "to": _iso(day),
            "messages": len(messages), "followups": len(followups), "calls": len(calls),
            "meetings": len(meetings), "replies": len(replies),
            "targets": dict(WEEKLY_TARGET),
            "names": {"messages": messages, "meetings": meetings, "replies": replies},
            "note": ("این سه عدد را کنترل می‌کنی، نه بازار را. هدف هفته: پنج پیام، یک تماس، "
                     "یک جلسه.")}


def close(name: str, *, path: Path | str | None = None) -> dict:
    """پرونده را می‌بندد (بدون نتیجهٔ «بله»): از فهرست پیگیری بیرون می‌رود."""
    rows = load(path)
    row = _find(rows, name)
    if not row:
        return {"ok": False, "detail": f"«{name}» در تابلو نیست."}
    row["result"] = row.get("result") or "بی‌جواب"
    row.setdefault("history", []).append("بسته شد — بدون نتیجه")
    save(rows, path)
    return {"ok": True, "row": row}


def build_sheet(rows: list[dict] | None = None, *, md_path: Path | str | None = None,
                html_path: Path | str | None = None, on: str | None = None,
                path: Path | str | None = None) -> tuple[Path, Path]:
    """برگهٔ چاپی تابلوی پیگیری: هر مخاطب، وضعیت، کار بعدی، و سه عدد هفته."""
    rows = rows if rows is not None else load(path)
    mp = Path(md_path) if md_path else SHEET_MD
    hp = Path(html_path) if html_path else SHEET_HTML
    mp.parent.mkdir(parents=True, exist_ok=True)
    hp.parent.mkdir(parents=True, exist_ok=True)
    day = _parse(on) or _today()
    items = todo(rows, on=day.isoformat())
    wk = week_numbers(rows, on=day.isoformat())
    todo_by_name = {i["name"]: i for i in items}

    def status(r: dict) -> str:
        if r.get("result"):
            if r["result"] == "بعداً":
                back = r.get("next_on") or _iso((_parse(r.get("created")) or day)
                                                + timedelta(days=LATER_DAYS))
                return f"بعداً — سر زدن {fa(back)}"
            return f"بسته — {r['result']}"
        if r.get("meeting"):
            return f"جلسه: {fa(r['meeting'])}"
        if r.get("replied"):
            return "جواب داده، قرار جلسه مانده"
        if r.get("sent"):
            return f"پیام رفته ({fa(len(r.get('followup') or []))} پیگیری)"
        return "هنوز پیامی نرفته"

    md = "\n".join([
        "# تابلوی پیگیری مخاطبان", "",
        f"**تاریخ:** {fa(day.isoformat())} · **در تابلو:** {fa(len(rows))} · "
        f"**کار امروز:** {fa(len(items))}", "",
        "## سه عدد این هفته", "",
        f"- پیام فرستاده‌شده: **{fa(wk['messages'])}** (هدف {fa(WEEKLY_TARGET['messages'])}) · "
        f"تماس: **{fa(wk['calls'])}** (هدف {fa(WEEKLY_TARGET['calls'])}) · "
        f"جلسه: **{fa(wk['meetings'])}** (هدف {fa(WEEKLY_TARGET['meetings'])})",
        f"- پیگیری‌های رفته: {fa(wk['followups'])} · جواب‌های آمده: {fa(wk['replies'])}", "",
        "## کار امروز (به همین ترتیب)", "",
        *([f"{fa(i + 1)}. **{t['name']}** — {t['action']}" + (" ⚡" if t["urgent"] else "") +
           f"  \n   چرا: {t['why']}" for i, t in enumerate(items)]
          if items else ["امروز کاری در نوبت نیست. اگر تازه‌کاری، پنج نام این هفته را اضافه کن."]),
        "", "## تابلو", "",
        "| مخاطب | دسته | کانال | وضعیت | کار بعدی |", "| --- | --- | --- | --- | --- |",
        *[f"| {r['name']} | {KINDS.get(r.get('kind'), '—')} | {CHANNELS.get(r.get('channel'), '—')} | "
          f"{status(r)} | {todo_by_name.get(r['name'], {}).get('action', '—')} |" for r in rows],
        "", "## قاعده‌ها", "",
        "- پیگیری فقط سه بار: روز ۰ (پیام اول)، روز ۳، روز ۱۰. بعد پرونده را ببند.",
        "- هیچ عدد سودی در هیچ پیامی نمی‌رود؛ هدف هر پیام، گرفتن یک نیم‌ساعت وقت است.",
        "- شمارهٔ تلفن و نشانی هیچ‌جا در این دفتر ذخیره نمی‌شود؛ این دفتر محلی است و به هیچ "
        "شبکه‌ای وصل نیست.",
        "", "✍️ تهیه‌کنندهٔ جزوات: Masoud Mojarabian · 📱 [989126630554](tel:+989126630554) · "
        "✈️ [Telegram: Mojarabian](https://t.me/Mojarabian) · "
        "📸 [Instagram: Mojarabian.Art](https://instagram.com/Mojarabian.Art)", "",
    ])
    mp.write_text(md, encoding="utf-8")

    def row_html(r: dict) -> str:
        nxt = todo_by_name.get(r["name"], {})
        urgent = " ⚡" if nxt.get("urgent") else ""
        return (f"<tr><td><b>{rk.esc(r['name'])}</b></td><td>{rk.esc(KINDS.get(r.get('kind'), '—'))}</td>"
                f"<td>{rk.esc(CHANNELS.get(r.get('channel'), '—'))}</td>"
                f"<td>{rk.esc(status(r))}</td>"
                f"<td>{rk.esc(nxt.get('action', '—'))}{urgent}</td></tr>")

    body = "".join([
        '<div class="honest"><b>این دفتر محلی است</b> و به هیچ شبکه‌ای وصل نیست. هدفش یک چیز است: '
        'هر هفته پنج پیام، و آن‌که نوبتش است از دست نرود.</div>',
        f'<p class="sub">تاریخ: {fa(day.isoformat())} · در تابلو: <b>{fa(len(rows))}</b> · '
        f'کار امروز: <b>{fa(len(items))}</b></p>',
        "<h2>۱. سه عدد این هفته</h2>",
        f'<p>پیام فرستاده‌شده: <b>{fa(wk["messages"])}</b> (هدف {fa(WEEKLY_TARGET["messages"])}) · '
        f'تماس: <b>{fa(wk["calls"])}</b> (هدف {fa(WEEKLY_TARGET["calls"])}) · '
        f'جلسه: <b>{fa(wk["meetings"])}</b> (هدف {fa(WEEKLY_TARGET["meetings"])}) · '
        f'پیگیری‌های رفته: {fa(wk["followups"])} · جواب‌های آمده: {fa(wk["replies"])}</p>',
        "<h2>۲. کار امروز</h2>",
        ("<ol>" + "".join(f'<li><b>{rk.esc(t["name"])}</b> — {rk.esc(t["action"])}'
                          f'{" ⚡" if t["urgent"] else ""}<br>'
                          f'<span class="hint">چرا: {rk.esc(t["why"])}</span></li>' for t in items)
         + "</ol>") if items else '<p class="hint">امروز کاری در نوبت نیست.</p>',
        "<h2>۳. تابلو</h2>",
        "<table><thead><tr><th>مخاطب</th><th>دسته</th><th>کانال</th><th>وضعیت</th>"
        "<th>کار بعدی</th></tr></thead><tbody>"
        + "".join(row_html(r) for r in rows) + "</tbody></table>",
        "<h2>۴. قاعده‌ها</h2>",
        '<ul><li>پیگیری فقط سه بار: روز ۰، روز ۳، روز ۱۰. بعد پرونده را ببند.</li>'
        '<li>هیچ عدد سودی در هیچ پیامی نمی‌رود؛ هدف هر پیام، گرفتن یک نیم‌ساعت وقت است.</li>'
        '<li>شمارهٔ تلفن و نشانی در این دفتر ذخیره نمی‌شود.</li></ul>',
        f'<p class="sub">{rk.DEVELOPER_HTML}</p>',
    ])
    hp.write_text(rk.page("تابلوی پیگیری مخاطبان", body,
                          subtitle=f"{fa(day.isoformat())} · {fa(len(rows))} مخاطب"),
                  encoding="utf-8")
    return hp, mp


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="تابلوی پیگیری مخاطبان (محلی، بدون شبکه)")
    ap.add_argument("--add", metavar="نام", help="مخاطب تازه")
    ap.add_argument("--sent", metavar="نام", help="پیام اول فرستاده شد")
    ap.add_argument("--followup", metavar="نام", help="پیگیری رفته (روز ۳ یا ۱۰)")
    ap.add_argument("--reply", metavar="نام", help="جواب داد")
    ap.add_argument("--meeting", metavar="نام", help="جلسه گذاشته شد")
    ap.add_argument("--outcome", metavar="نام", help="نتیجهٔ جلسه")
    ap.add_argument("--close", metavar="نام", help="پرونده را ببند")
    ap.add_argument("--kind", default="company", choices=sorted(KINDS))
    ap.add_argument("--channel", default="telegram", choices=sorted(CHANNELS))
    ap.add_argument("--date", default="", help="تاریخ YYYY-MM-DD (پیش‌فرض: امروز)")
    ap.add_argument("--note", default="")
    ap.add_argument("--result", default="", choices=[""] + list(RESULTS))
    ap.add_argument("--next-on", default="", help="برای نتیجهٔ «بعداً»: روز سر‌زدن YYYY-MM-DD "
                                                  f"(پیش‌فرض: {LATER_DAYS} روز بعد)")
    ap.add_argument("--todo", action="store_true", help="امروز چه کسی را پیگیری کنم")
    ap.add_argument("--week", action="store_true", help="سه عدد این هفته")
    ap.add_argument("--sheet", action="store_true", help="برگهٔ چاپی تابلوی پیگیری")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--version", action="version", version=f"prospects {VERSION}")
    a = ap.parse_args(argv)

    when = a.date or None
    ops = [("--add", a.add, lambda: add(a.add, kind=a.kind, channel=a.channel, note=a.note, when=when)),
           ("--sent", a.sent, lambda: mark(a.sent, "sent", when=when, note=a.note)),
           ("--followup", a.followup, lambda: mark(a.followup, "followup", when=when, note=a.note)),
           ("--reply", a.reply, lambda: mark(a.reply, "reply", when=when, note=a.note)),
           ("--meeting", a.meeting, lambda: mark(a.meeting, "meeting", when=when, note=a.note)),
           ("--outcome", a.outcome, lambda: mark(a.outcome, "outcome", when=when, note=a.note,
                                                 result=a.result, next_on=a.next_on or None)),
           ("--close", a.close, lambda: close(a.close))]
    for _, value, fn in ops:
        if value:
            out = fn()
            if a.json:
                print(json.dumps(out, ensure_ascii=False))
            else:
                print(("✅ " if out.get("ok") else "⚠️ ") + str(out.get("detail") or "ثبت شد."))
            return 0 if out.get("ok") else 1

    if a.sheet:
        h, m = build_sheet()
        print("برگهٔ چاپی:", h)
        print("نسخهٔ متنی:", m)
        return 0

    if a.todo:
        items = todo()
        if a.json:
            print(json.dumps(items, ensure_ascii=False, indent=1))
            return 0
        if not items:
            print("امروز کاری در نوبت نیست.")
            return 0
        for i, t in enumerate(items, 1):
            print(f"{fa(i)}. {t['name']} — {t['action']}{' ⚡' if t['urgent'] else ''}")
            print(f"   چرا: {t['why']}")
        return 0

    if a.week:
        wk = week_numbers()
        if a.json:
            print(json.dumps(wk, ensure_ascii=False))
            return 0
        print(f"هفته {fa(wk['from'])} تا {fa(wk['to'])}")
        print(f"  پیام: {fa(wk['messages'])} (هدف {fa(WEEKLY_TARGET['messages'])}) · "
              f"تماس: {fa(wk['calls'])} (هدف {fa(WEEKLY_TARGET['calls'])}) · "
              f"جلسه: {fa(wk['meetings'])} (هدف {fa(WEEKLY_TARGET['meetings'])})")
        print(f"  پیگیری رفته: {fa(wk['followups'])} · جواب آمده: {fa(wk['replies'])}")
        print(f"  {wk['note']}")
        return 0

    rows = load()
    if a.json:
        print(json.dumps({"prospects": rows, "todo": todo(rows), "week": week_numbers(rows)},
                         ensure_ascii=False))
        return 0
    print(f"تابلوی پیگیری — {fa(len(rows))} مخاطب · دفتر محلی: {STORE}")
    for r in rows:
        print(f"  · {r['name']} ({KINDS.get(r.get('kind'), '—')}) — "
              + (f"نتیجه: {r['result']}" if r.get("result") else
                 f"جلسه {fa(r['meeting'])}" if r.get("meeting") else
                 "جواب داده" if r.get("replied") else
                 f"پیام رفته {fa(r['sent'])}" if r.get("sent") else "هنوز پیامی نرفته"))
    items = todo(rows)
    print(f"  کار امروز: {fa(len(items))}")
    for t in items:
        print(f"    → {t['name']}: {t['action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
