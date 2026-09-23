"""مراسم بیست‌دقیقه‌ای فروش — برگهٔ امروز، آماده برای اجرا.

جای این ماژول در زنجیره: `prospects.py` می‌گوید امروز نوبت کدام مخاطب است؛ `outreach.py` متن
آماده را دارد. این ماژول همان دو را کنار هم می‌گذارد و یک برگهٔ اجرایی می‌سازد: کدام کار، برای
کدام مخاطب، با کدام متن، و در چه دقیقه‌ای — جمعاً بیست دقیقه.

سه چیزی که در خود کد قفل است:

- **سقف پنج پیام در روز** (`MAX_MESSAGES_PER_DAY`) و **سقف بیست دقیقه** (`BUDGET_MIN`): هر کاری
  که جا نشد، با دلیلش به «فردا» می‌رود. هیچ‌وقت لیست را کش نمی‌دهیم تا کار بیشتر شود.
- **متن‌ها فقط از `outreach.messages` می‌آید**؛ این ماژول خودش متن تازه نمی‌سازد (تنها استثنا:
  پیام «روز موعود» که همین‌جا نوشته شده و همان آزمون‌های سختی را می‌دهد که متن‌های outreach).
- **روزِ خالی، پیام نمی‌سازد**: اگر «کار امروز» خالی است، برگه می‌گوید پنج نام تازه اضافه کن؛ به
  کسی که در نوبت نیست پیام نمی‌فرستیم تا عدد هفته پر شود.

اجرا:
    python3 sales_ritual.py                      # برنامهٔ امروز
    python3 sales_ritual.py --sender "مسعود"     # امضای پیام‌ها
    python3 sales_ritual.py --sheet              # برگهٔ چاپی امروز
    python3 sales_ritual.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import outreach as outreachmod  # noqa: E402
import prospects as prospectsmod  # noqa: E402
import reportkit as rk  # noqa: E402

VERSION = "0.1.0"
DATA = BASE / "data"
SHEET_MD = DATA / "sales-today.md"
SHEET_HTML = DATA / "sales-today.html"

BUDGET_MIN = 20
COST = {"message": 3, "call": 5, "internal": 2}
MAX_MESSAGES_PER_DAY = 5

# پیام «روز موعود» (نتیجهٔ «بعداً»): یک بار، بی‌فشار، بدون هیچ عددی
LATER_MESSAGE = (
    "سلام، وقتتان بخیر.\n\n"
    "قرارمان امروز بود که سر بزنم؛ فقط همین یک پیام. اگر آن موضوع قبلی هنوز برایتان باز است، "
    "همان نیم‌ساعت را بگذاریم؟\n\n"
    "اگر بسته شده است، همین یک جمله کافی است و من دیگر مزاحم نمی‌شوم."
)

RESULT_QUESTIONS = [
    "جوابشان دقیقاً چه بود: بله · بعداً · نه · بی‌جواب؟",
    "یک جملهٔ خودشان را عیناً بنویس (همان جمله، نه برداشت تو).",
    "تاریخ بعدی چه شد — و اگر «نه» بود، جواب سؤال «چه چیزی را باید ببینید؟» چه بود؟",
]

RULE_LINES = [
    "هر مخاطب در روز فقط یک پیام؛ پیام یکسان برای چند نفر، اسپم شناخته می‌شود.",
    "پیگیری فقط سه بار: روز ۰، ۳، ۱۰. بار سوم یعنی تمام — نه چهارمی.",
    "هیچ عدد سود، هیچ بازدهی و هیچ فوریت ساختگی در هیچ پیامی نیست.",
    "اگر «کار امروز» خالی است، پیام تازه نساز؛ پنج نام این هفته را اضافه کن.",
]

_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa(value) -> str:
    return str(value).translate(_DIGITS)


def _classify(item: dict, *, sender: str, kind: str, channel: str) -> dict:
    """کار امروز را به یک کار اجرایی تبدیل می‌کند: پیام، تماس، یا کار دفتری."""
    action = item["action"]
    m = outreachmod.messages(item["name"], kind=kind, sender=sender)
    row = {"name": item["name"], "action": action, "why": item.get("why", ""),
           "urgent": bool(item.get("urgent")), "kind_label": m["kind_label"],
           "channel": channel, "channel_label": prospectsmod.CHANNELS.get(channel, "—"),
           "text": None, "note": "", "minutes": 0, "start_min": None, "kind": None}
    if action.startswith("پیام اول"):
        row.update(kind="message", text=m["first_message"], minutes=COST["message"])
    elif action.startswith("پیگیری"):
        row.update(kind="message", text=m["followup_message"], minutes=COST["message"])
        row["note"] = ("آخرین پیگیری (روز ۱۰)؛ بعد از این پرونده بسته می‌شود."
                       if "۲" in action else "پیگیری اول (روز ۳).")
    elif action.startswith("قرار جلسه"):
        row.update(kind="message", text=m["confirm_message"], minutes=COST["message"])
    elif action.startswith("روز موعود"):
        row.update(kind="message", text=LATER_MESSAGE, minutes=COST["message"],
                   note="یک بار، بی‌فشار؛ اگر جواب نداد، پرونده بسته می‌شود.")
    elif action.startswith("نتیجهٔ جلسه"):
        row.update(kind="internal", minutes=COST["internal"], checklist=list(RESULT_QUESTIONS))
    elif action.startswith("ببند"):
        row.update(kind="internal", minutes=COST["internal"],
                   note="پیامی نمی‌فرستی؛ پرونده را در تابلو ببند.")
    else:
        row.update(kind="internal", minutes=COST["internal"])
    if row["kind"] in ("message", "call") and channel == "phone":
        # تماس تلفنی همان کار است، ولی گران‌تر: هزینه‌اش پنج دقیقه و متنش اسکریپت تماس
        row.update(kind="call", text=m["call_script"], minutes=COST["call"],
                   note=(row["note"] + " " if row["note"] else "") + "کانال تلفنی است؛ اسکریپت تماس، نه پیام.")
    return row


def plan(rows: list[dict] | None = None, *, on: str | None = None, sender: str = "مسعود",
         path: Path | str | None = None) -> dict:
    """برنامهٔ امروز: چه کاری، برای چه کسی، با چه متن، در چه دقیقه‌ای."""
    rows = rows if rows is not None else prospectsmod.load(path)
    day = prospectsmod._parse(on) or datetime.now(timezone.utc).date()
    items = prospectsmod.todo(rows, on=day.isoformat())
    by_name = {r["name"]: r for r in rows}

    scheduled: list[dict] = []
    deferred: list[dict] = []
    used = 0
    sent_messages = 0
    for item in items:
        row = by_name.get(item["name"], {})
        work = _classify(item, sender=sender, kind=row.get("kind", "company"),
                         channel=row.get("channel", "telegram"))
        if work["kind"] == "message" and sent_messages >= MAX_MESSAGES_PER_DAY:
            deferred.append({"name": work["name"], "action": work["action"],
                             "reason": f"سقف {fa(MAX_MESSAGES_PER_DAY)} پیام امروز پر شد."})
            continue
        if used + work["minutes"] > BUDGET_MIN:
            deferred.append({"name": work["name"], "action": work["action"],
                             "reason": f"بودجهٔ {fa(BUDGET_MIN)} دقیقه پر شد."})
            continue
        work["start_min"] = used
        used += work["minutes"]
        if work["kind"] == "message":
            sent_messages += 1
        scheduled.append(work)

    counts = {"messages": len([x for x in scheduled if x["kind"] == "message"]),
              "calls": len([x for x in scheduled if x["kind"] == "call"]),
              "internal": len([x for x in scheduled if x["kind"] == "internal"]),
              "deferred": len(deferred)}
    if scheduled:
        note = (f"هدف امروز {fa(counts['messages'] + counts['calls'])} پیام است، نه "
                f"{fa(counts['messages'] + counts['calls'])} فروش. وقتی پیام رفت، کار امروز تمام است.")
    elif rows:
        note = ("امروز کسی در نوبت نیست؛ به کسی که نوبتش نیست پیام نمی‌فرستیم. "
                "اگر تازه‌کاری، پنج نام این هفته را به تابلو اضافه کن.")
    else:
        note = ("تابلو خالی است. مرحلهٔ اول، اضافه‌کردن پنج نام است — تا آن‌ها نباشد، "
                "مراسم امروز کاری برای انجام‌دادن ندارد.")
    return {"date": day.isoformat(), "sender": sender, "budget": BUDGET_MIN,
            "used_minutes": used, "items": scheduled, "deferred": deferred, "counts": counts,
            "week": prospectsmod.week_numbers(rows, on=day.isoformat()),
            "board": len(rows), "targets": dict(prospectsmod.WEEKLY_TARGET), "note": note,
            "rules": list(RULE_LINES)}


def build_sheet(rows: list[dict] | None = None, *, on: str | None = None, sender: str = "مسعود",
                md_path: Path | str | None = None, html_path: Path | str | None = None,
                path: Path | str | None = None) -> tuple[Path, Path]:
    """برگهٔ چاپی امروز: برنامه، متن‌های آماده، کار دفتری، و فردا."""
    p = plan(rows, on=on, sender=sender, path=path)
    mp = Path(md_path) if md_path else SHEET_MD
    hp = Path(html_path) if html_path else SHEET_HTML
    mp.parent.mkdir(parents=True, exist_ok=True)
    hp.parent.mkdir(parents=True, exist_ok=True)

    def slot(i: dict) -> str:
        return f"دقیقهٔ {fa(i['start_min'])} تا {fa(i['start_min'] + i['minutes'])}"

    cap_line = (f"سقف امروز: {fa(MAX_MESSAGES_PER_DAY)} پیام و {fa(BUDGET_MIN)} دقیقه؛ هر کاری "
                "که جا نشد، با دلیلش به «فردا» می‌رود. سقف را جابه‌جا نمی‌کنیم تا لیست پر شود.")
    rules = [cap_line] + list(RULE_LINES)
    plan_rows = [f"| {slot(i)} | {i['action']} | {i['name']} | {i['channel_label']} |"
                 for i in p["items"]] or ["| — | امروز کاری در نوبت نیست | — | — |"]
    blocks = [f"### {i['name']} — {i['channel_label']} · {slot(i)}"
              + (f"\n\n> {i['note']}" if i["note"] else "")
              + f"\n\n```text\n{i['text']}\n```\n\n"
              + "فرستادم ☐    جواب آمد ☐    جوابش را در تابلو ثبت کردم ☐\n"
              for i in p["items"] if i["kind"] in ("message", "call")] or \
             ["امروز متن تازه‌ای برای فرستادن نیست."]
    desk_rows = [f"**{i['name']}** — {i['action']}"
                 + (f" · {i['note']}" if i["note"] else "") + "\n"
                 + "".join(f"   - {q}\n" for q in (i.get("checklist") or []))
                 for i in p["items"] if i["kind"] == "internal"] or ["—"]
    defer_rows = [f"- {d['name']} — {d['action']} ({d['reason']})" for d in p["deferred"]] or ["—"]

    md = "\n".join([
        "# برگهٔ فروش امروز — مراسم بیست‌دقیقه‌ای", "",
        f"**تاریخ:** {fa(p['date'])} · **امضا:** {p['sender']} · "
        f"**بودجه:** {fa(p['budget'])} دقیقه · **خرج‌شده:** {fa(p['used_minutes'])} دقیقه", "",
        f"**{p['note']}**", "",
        "## ۱. برنامهٔ امروز", "",
        "| دقیقه | کار | مخاطب | کانال |", "| --- | --- | --- | --- |",
        *plan_rows, "",
        "## ۲. متن‌های آماده (کپی کن و بفرست)", "",
        *blocks,
        "## ۳. کار دفتری (بدون پیام)", "",
        *desk_rows, "",
        "## ۴. فردا (اگر جا نشد)", "",
        *defer_rows, "",
        "## ۵. سه عدد این هفته", "",
        f"- پیام: **{fa(p['week']['messages'])}** (هدف {fa(p['targets']['messages'])}) · "
        f"تماس: **{fa(p['week']['calls'])}** (هدف {fa(p['targets']['calls'])}) · "
        f"جلسه: **{fa(p['week']['meetings'])}** (هدف {fa(p['targets']['meetings'])})", "",
        "## ۶. قاعده‌ها", "",
        *[f"- {r}" for r in rules], "",
        rk.DEVELOPER_HTML if hasattr(rk, "DEVELOPER_HTML") else "", "",
    ])
    mp.write_text(md, encoding="utf-8")

    rows_html = "".join(
        f"<tr><td>{slot(i)}</td><td>{rk.esc(i['action'])}</td><td><b>{rk.esc(i['name'])}</b></td>"
        f"<td>{rk.esc(i['channel_label'])}</td></tr>" for i in p["items"]
    ) or '<tr><td colspan="4" class="hint">امروز کاری در نوبت نیست.</td></tr>'

    boxes = '<div id="msgtext">' + ("".join(
        f'<div class="card" style="margin:10px 0"><h4>{rk.esc(i["name"])} — '
        f'{rk.esc(i["channel_label"])} · {slot(i)}</h4>'
        + (f'<p class="hint">{rk.esc(i["note"])}</p>' if i["note"] else "")
        + f'<pre class="note" style="white-space:pre-wrap">{rk.esc(i["text"])}</pre>'
          '<p class="sub">فرستادم ☐ &nbsp;&nbsp; جواب آمد ☐ &nbsp;&nbsp; در تابلو ثبت کردم ☐</p></div>'
        for i in p["items"] if i["kind"] in ("message", "call")
    ) or '<p class="hint">امروز متن تازه‌ای برای فرستادن نیست.</p>') + "</div>"

    desk = "".join(
        f'<p><b>{rk.esc(i["name"])}</b> — {rk.esc(i["action"])}'
        + (f' · <span class="hint">{rk.esc(i["note"])}</span>' if i["note"] else "")
        + "</p><ul>" + "".join(f"<li>{rk.esc(q)}</li>" for q in (i.get("checklist") or []))
        + "</ul>" for i in p["items"] if i["kind"] == "internal"
    ) or '<p class="hint">کار دفتری‌ای نمانده است.</p>'

    body = "".join([
        f'<div class="honest"><b>{rk.esc(p["note"])}</b></div>',
        f'<p class="sub">تاریخ: {fa(p["date"])} · امضا: {rk.esc(p["sender"])} · '
        f'بودجه: {fa(p["budget"])} دقیقه · خرج‌شده: <b>{fa(p["used_minutes"])}</b> دقیقه</p>',
        "<h2>۱. برنامهٔ امروز</h2>",
        "<table><thead><tr><th>دقیقه</th><th>کار</th><th>مخاطب</th><th>کانال</th></tr></thead>"
        f"<tbody>{rows_html}</tbody></table>",
        "<h2>۲. متن‌های آماده (کپی کن و بفرست)</h2>", boxes,
        "<h2>۳. کار دفتری (بدون پیام)</h2>", desk,
        "<h2>۴. فردا (اگر جا نشد)</h2>",
        "<ul>" + ("".join(f'<li><b>{rk.esc(d["name"])}</b> — {rk.esc(d["action"])} '
                          f'<span class="hint">({rk.esc(d["reason"])})</span></li>'
                          for d in p["deferred"]) or "<li>—</li>") + "</ul>",
        "<h2>۵. سه عدد این هفته</h2>",
        f'<p>پیام: <b>{fa(p["week"]["messages"])}</b> (هدف {fa(p["targets"]["messages"])}) · '
        f'تماس: <b>{fa(p["week"]["calls"])}</b> (هدف {fa(p["targets"]["calls"])}) · '
        f'جلسه: <b>{fa(p["week"]["meetings"])}</b> (هدف {fa(p["targets"]["meetings"])})</p>',
        "<h2>۶. قاعده‌ها</h2>",
        "<ul>" + "".join(f"<li>{rk.esc(r)}</li>" for r in rules) + "</ul>",
        f'<p class="sub">{rk.DEVELOPER_HTML}</p>',
    ])
    hp.write_text(rk.page("برگهٔ فروش امروز — مراسم بیست‌دقیقه‌ای", body,
                          subtitle=f"{fa(p['date'])} · {fa(p['used_minutes'])} از "
                                   f"{fa(p['budget'])} دقیقه"),
                  encoding="utf-8")
    return hp, mp


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="مراسم بیست‌دقیقه‌ای فروش (برگهٔ امروز)")
    ap.add_argument("--sender", default="مسعود", help="نام خودت در امضای پیام‌ها")
    ap.add_argument("--on", default="", help="تاریخ YYYY-MM-DD (پیش‌فرض: امروز)")
    ap.add_argument("--sheet", action="store_true", help="برگهٔ چاپی امروز")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--version", action="version", version=f"sales_ritual {VERSION}")
    a = ap.parse_args(argv)

    if a.sheet:
        h, m = build_sheet(on=a.on or None, sender=a.sender)
        print("برگهٔ چاپی امروز:", h)
        print("نسخهٔ متنی (برای کپی متن‌ها):", m)
        return 0

    p = plan(on=a.on or None, sender=a.sender)
    if a.json:
        print(json.dumps(p, ensure_ascii=False))
        return 0
    print(f"مراسم فروش — {fa(p['date'])} · بودجه {fa(p['budget'])} دقیقه "
          f"(خرج‌شده {fa(p['used_minutes'])})")
    if not p["items"]:
        print("  " + p["note"])
        return 0
    for i in p["items"]:
        mark = "☎" if i["kind"] == "call" else ("✉" if i["kind"] == "message" else "▣")
        print(f"  {mark} دقیقهٔ {fa(i['start_min'])} — {i['name']} ({i['channel_label']}): {i['action']}")
    for d in p["deferred"]:
        print(f"  ↷ فردا — {d['name']}: {d['action']} ({d['reason']})")
    print("  " + p["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
