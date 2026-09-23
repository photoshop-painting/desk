"""جلسهٔ بازبینی دو هفته‌ای — سه شاهد، دو خروجی، یک تصمیم.

جای این برگه در زنجیره: `outreach.py` جلسه را می‌گیرد، `onboarding.py` روز اول را راه می‌اندازد،
`sales_ritual.py` کار روزانه را نگه می‌دارد. این برگه برای **روز چهاردهم** است: همان جایی که
آزمون تمام می‌شود و باید تصمیم گرفته شود — ادامه با پرداخت، تمدید بی‌هزینه، یا توقف.

قاعده‌ها از جای دیگری خوانده می‌شوند، نه از حافظهٔ من:

- **طول آزمون** و **روز بازبینی**: از `license.TRIAL_DAYS` (`start + TRIAL_DAYS`).
- **شرط‌های «کارنامهٔ آماده»**: از `daily_trial.scorecard` (همان پنج شرطی که `onboarding.py` هم
  نشان می‌دهد؛ یک منبع، دو برگه).
- **سه پلهٔ ارائه**: از `license.ladder()` · **قیمت**: از `offer.price_line` (اگر عددی داده نشود،
  «توافقی» — قیمت خودساخته روی برگه نمی‌رود).
- **عددهای بستهٔ تحویل**: از `KIT-MANIFEST.json`.

اجرا:
    python3 review_meeting.py --client "نام مشتری" --start 2026-09-22
    python3 review_meeting.py --client "نام مشتری" --on 2026-10-06 --monthly 40000000
    python3 review_meeting.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import license as licmod  # noqa: E402
import reportkit as rk  # noqa: E402
from offer import _kit_facts as kit_facts, fa, fa_num, price_line  # noqa: E402
from onboarding import gate_conditions  # noqa: E402  (یک منبع برای پنج شرط کارنامه)

VERSION = "0.1.0"
DATA = BASE / "data"
REVIEW_MD = DATA / "review-meeting.md"
REVIEW_HTML = DATA / "review-meeting.html"

# پیگیری بعد از جلسه: اگر همان روز تصمیم نگرفتند، روز سرزدن پیش‌فرض یک ماه بعد است.
FOLLOW_ON_DAYS = 30


def trial_days() -> int:
    """طول آزمون — از خود ماژول اجازه‌نامه."""
    return int(getattr(licmod, "TRIAL_DAYS", 14))


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _parse(value: str | None) -> date:
    if not value:
        return _today()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:                       # تاریخ خراب = خطای روشن، نه سکوت
        raise ValueError(f"تاریخ «{value}» خوانده نشد؛ قالب درست: YYYY-MM-DD") from exc


def review_day(start: str | None = None) -> date:
    """روز بازبینی: همان روزی که اجازه‌نامهٔ آزمون تمام می‌شود."""
    return _parse(start) + timedelta(days=trial_days())


def days_left(start: str | None = None, on: str | None = None) -> int:
    """چند روز تا بازبینی مانده (منفی یعنی گذشته)."""
    return (review_day(start) - _parse(on)).days


def status_line(start: str | None = None, on: str | None = None) -> str:
    """وضعیت امروز نسبت به روز بازبینی — بدون فشار و بدون اغراق."""
    left = days_left(start, on)
    if left > 0:
        return f"{fa(left)} روز تا روز بازبینی مانده؛ این برگه را برای همان روز نگه دارید."
    if left == 0:
        return "امروز روز بازبینی است؛ همین نشست، تصمیم را روشن می‌کند."
    return (f"{fa(-left)} روز از روز بازبینی گذشته است. جلسه را عقب نیندازید: همین هفته، "
            "همان نیم‌ساعت.")


def witness_rows() -> list[dict]:
    """سه شاهد (و یک شاهد اختیاری برای شرکت): چه فرمانی، چه چیزی را نشان می‌دهد، چه چیزی را نه."""
    return [
        {"n": 1, "name": "کارنامهٔ دو هفته",
         "where": "ترمینال، در پوشهٔ station",
         "cmd": "python3 daily_trial.py --status",
         "shows": "پنج شرط دو هفته: تداوم روزانه، روزهای با دادهٔ واقعی، بازسنجی دفتر، حرکت "
                  "معنادار، و سالم‌بودن زنجیرهٔ هش.",
         "not_shows": "این‌که کدام تصمیم سود داد — کارنامه کیفیت کار است، نه پیش‌بینی."},
        {"n": 2, "name": "دفتر استفادهٔ موفق",
         "where": "ترمینال، در پوشهٔ station",
         "cmd": "python3 usage_meter.py --summary --verify",
         "shows": "چه کاری چند بار انجام شده، با دو امضا (ارائه‌دهنده و شرکت) و اثر انگشت "
                  "زنجیرهٔ دفتر.",
         "not_shows": "درست‌بودن تصمیم‌ها؛ فقط نشان می‌دهد بعد از ثبت، کسی عدد را جای دیگری "
                      "عوض نکرده است."},
        {"n": 3, "name": "آزمون خودِ ایستگاه",
         "where": "ترمینال، در پوشهٔ station",
         "cmd": "python3 selftest.py",
         "shows": "پانزده سنجه، هر کدام دو بار: یک بار با موتور و یک بار با حساب دستی مستقل.",
         "not_shows": "آینده را؛ فقط نشان می‌دهد حساب‌ها امروز درست بسته می‌شوند."},
        {"n": 4, "name": "بستهٔ راستی‌آزمایی (اختیاری، برای شرکت)",
         "where": "گام ۸ → «ساخت بستهٔ راستی‌آزمایی»",
         "cmd": None,
         "shows": "همان عددها با اثر انگشت `sha256` هر پرونده و چک‌لیست پنج‌دقیقه‌ای، برای "
                  "بازبینی توسط شخص سوم.",
         "not_shows": "هیچ عدد تازه‌ای؛ برای بازبینی است، نه برای تبلیغ."},
    ]


def outcomes(monthly_rial: int = 0, setup_rial: int = 0) -> list[dict]:
    """دو خروجی روشن جلسه: ادامه با پرداخت، یا توقف بی‌گلایه‌مندی."""
    price = price_line(monthly_rial, setup_rial)
    ladder = licmod.ladder()
    return [
        {"key": "continue", "title": "خروجی یک — ادامه با پرداخت",
         "lines": [
             "**پله‌ها:** " + " · ".join(f"{r['step']} ({r['basis']})" for r in ladder),
             f"**قیمت:** {price['text']}",
             "**قاعده:** پرداخت در برابر **پروندهٔ همان پله** است، نه وعده. صورت‌جلسهٔ همین دو "
             "هفته ضمیمهٔ پلهٔ دوم می‌شود: کارنامه، دفتر استفاده و بستهٔ شاهد.",
             "**جملهٔ آماده برای گفتن:** «پلهٔ دوم را از امروز شروع می‌کنیم؛ صورت‌کار این دو هفته "
             "هم ضمیمه است — هر عددش را خودتان می‌توانید بازتولید کنید.»",
         ]},
        {"key": "stop", "title": "خروجی دو — توقف، بی‌گلایه‌مندی",
         "lines": [
             "**سه کار همان شب:** (۱) در تابلو نتیجهٔ «نه» ثبت شود؛ (۲) اجازه‌نامه در همان تاریخ "
             "نام‌دار تمام می‌شود و هیچ قفلی روی برنامه نیست؛ (۳) پرونده‌ها و دفترها روی رایانهٔ "
             "خودشان می‌مانَد.",
             "**خروجی‌ها را با خودشان ببرند:** `python3 usage_meter.py --statement` · "
             "`python3 investor_test.py --sheet` · بستهٔ تحویل (`iran-desk-kit.zip`).",
             "**جملهٔ آماده برای گفتن:** «امروز کار تمام است؛ اجازه‌نامه سر تاریخ خودش تمام می‌شود "
             "و چیزی بدهکار نیستید. هر وقت خواستید، همان عددها اینجا هست.»",
         ]},
    ]


def follow_up(on: str | None = None, follow_on: str | None = None) -> dict:
    """اگر همان روز تصمیم نگرفتند: روز سرزدن تاریخ‌دار + دو پیام کوتاه، بدون عدد و بدون فشار."""
    day = _parse(on)
    nxt = _parse(follow_on) if follow_on else day + timedelta(days=FOLLOW_ON_DAYS)
    return {
        "on": day.isoformat(),
        "next_on": nxt.isoformat(),
        "days": (nxt - day).days,
        "messages": [
            {"when": "روز ۳",
             "text": "سلام، وقتتان بخیر. فقط یک یادآوری کوچک: صورت‌جلسهٔ بازبینی و کارنامهٔ دو "
                     "هفته در همان پرونده است. اگر سؤالی دربارهٔ یکی از عددها داشتید، همان را "
                     "جواب می‌دهم."},
            {"when": "روز ۷",
             "text": "سلام. نمی‌خواهم وقتتان را بگیرم؛ فقط بگویم پرونده دست‌نخورده و آماده است. "
                     "اگر خواستید، همان نیم‌ساعت را می‌گذاریم و تصمیم را با هم روشن می‌کنیم."},
        ],
        "rule": "حداکثر همین دو پیام؛ بعد ساکت. اگر جواب نداد، پرونده در تابلو با تاریخ سرزدن "
                "بسته می‌شود — همان قاعدهٔ سه‌بارِ پیگیری، بدون پیام سوم.",
    }


QUESTIONS = [
    "چه چیزی را باید در این دو هفته می‌دیدید تا بگویید ارزش داشت؟",
    "کدام عدد برایتان مهم‌تر بود: کارنامه، دفتر استفاده، یا آزمون ایستگاه؟",
    "اگر فقط یک چیز را عوض کنیم، چه باشد؟",
]

MISTAKES = [
    "**فشار آوردن برای تصمیم همان جلسه**؛ تصمیم دیرهنگام بهتر از تصمیم کور است.",
    "**نشان دادن سود فرضی یا عدد ساخته**؛ اگر عددی نیست، «توافقی» و «کارنامه» جواب است.",
    "**وعدهٔ تاریخ پول**؛ وعدهٔ پرداخت به آیندهٔ بازار داده نمی‌شود، به تحویل پرونده داده می‌شود.",
]

BOUNDARIES = [
    "**هیچ سود تضمینی** و **هیچ پیش‌بینی قیمت** در کار نیست؛ خروجی این ایستگاه «عدد و دلیل» است.",
    "**هیچ سفارشی** به کارگزاری فرستاده نمی‌شود و کدی هم برایش نوشته نشده (ابلاغیهٔ مهر ۱۳۹۹).",
    "**هیچ درصدی از سود** گرفته نمی‌شود؛ اگر کسی چنین چیزی پیشنهاد داد، همان‌جا رد کنید.",
    "**تصمیم، تصمیم خودشان است**؛ برنامه عدد و دلیل می‌دهد، نه دستور.",
]


def checklist(monthly_rial: int = 0, setup_rial: int = 0) -> list[str]:
    """چک‌لیست دقیقه‌به‌دقیقهٔ همان جلسه (بیست دقیقه)."""
    return [
        "دقیقهٔ ۰–۳: سه شاهد روی همان لپ‌تاپ اجرا شود؛ آن‌ها فرمان را می‌زنند، شما دست به "
        "صفحه نمی‌زنید.",
        "دقیقهٔ ۳–۸: کارنامه خوانده شود؛ هر شرطی که نشده، همان‌جا گفته شود.",
        "دقیقهٔ ۸–۱۲: سه پرسش پایان، یکی‌یکی و با گوش دادن.",
        "دقیقهٔ ۱۲–۱۷: خروجی روشن — ادامه با پرداخت، تمدید بی‌هزینه، یا توقف.",
        "دقیقهٔ ۱۷–۲۰: اگر تصمیم نگرفتند، تاریخ سرزدن را همین‌جا در تابلو ثبت کنید.",
    ]


def build_review(client: str = "", *, start: str | None = None, on: str | None = None,
                 monthly_rial: int = 0, setup_rial: int = 0, follow_on: str | None = None,
                 html_path: Path | str | None = None,
                 md_path: Path | str | None = None) -> tuple[Path, Path]:
    """برگهٔ جلسهٔ بازبینی را می‌سازد. خروجی: (مسیر HTML، مسیر متن)."""
    hp = Path(html_path) if html_path else REVIEW_HTML
    mp = Path(md_path) if md_path else REVIEW_MD
    hp.parent.mkdir(parents=True, exist_ok=True)
    mp.parent.mkdir(parents=True, exist_ok=True)

    client_txt = client.strip() or "نام مشتری"
    day0 = _parse(start)
    today_on = _parse(on)
    review = review_day(start)
    witnesses = witness_rows()
    gates = gate_conditions()
    exits = outcomes(monthly_rial, setup_rial)
    after = follow_up(on, follow_on)
    status = status_line(start, on)
    kit = kit_facts()
    rows = checklist(monthly_rial, setup_rial)

    kit_sentence = (
        f"پروندهٔ کد و اسناد (`{kit['kit']}`) هم با اثر انگشت هر پرونده تحویل شده است."
        if kit.get("files") else
        "پروندهٔ کد و اسناد با اثر انگشت هر پرونده تحویل شده است.")

    header = (f"**برای:** {client_txt} · **شروع:** {fa(day0.isoformat())} · "
              f"**روز بازبینی:** {fa(review.isoformat())} · **امروز:** {fa(today_on.isoformat())}")
    witness_rows_md = [
        f"{fa(w['n'])}. **{w['name']}** — {w['where']}" +
        (f"  \n   `{w['cmd']}`" if w.get("cmd") else "") +
        f"  \n   نشان می‌دهد: {w['shows']}  \n   نشان نمی‌دهد: {w['not_shows']}"
        for w in witnesses]
    gate_rows_md = [f"| {g['name']} | {g['want']} | {g['why']} |" for g in gates]
    exit_md: list[str] = []
    for e in exits:
        exit_md.append(f"### {e['title']}")
        exit_md.append("")
        exit_md.extend(f"- {line}" for line in e["lines"])
        exit_md.append("")
    follow_md = [
        f"- **تاریخ سرزدن پیش‌فرض:** {fa(after['next_on'])} (امروز + {fa(after['days'])} روز).",
        f"- **ثبت در تابلو:** `python3 prospects.py --outcome \"{client_txt}\" --result \"بعداً\" "
        f"--next-on {after['next_on']}`",
    ]
    for msg in after["messages"]:
        follow_md.append(f"- **{msg['when']}:** «{msg['text']}»")

    md = "\n".join([
        "# جلسهٔ بازبینی دو هفته‌ای — سه شاهد، دو خروجی، یک تصمیم",
        "",
        header,
        "",
        f"**وضعیت:** {status}",
        "",
        "## ۱. بیست دقیقهٔ همین جلسه",
        "",
        *[f"- {row}" for row in rows],
        "",
        "## ۲. سه شاهد که خودشان می‌سازند",
        "",
        *[line for row in witness_rows_md for line in (row, "")],
        "",
        "## ۳. کارنامهٔ «آماده» — پنج شرط",
        "",
        "| شرط | عدد لازم | چرا |",
        "| --- | --- | --- |",
        *gate_rows_md,
        "",
        f"«آماده» یعنی همهٔ پنج شرط با هم. اگر یکی مانده، تصمیم امروز **تمدید** است، نه پرداخت: "
        f"یک بار، بی‌هزینه، {fa(trial_days())} روز دیگر، با همان شرط‌ها.",
        "",
        "## ۴. دو خروجی روشن",
        "",
        *exit_md,
        "## ۵. سه پرسش پایان",
        "",
        *[f"- {q}" for q in QUESTIONS],
        "",
        "## ۶. اگر امروز تصمیم نگرفتند",
        "",
        *follow_md,
        "",
        f"**قاعده:** {after['rule']}",
        "",
        "## ۷. سه اشتباه در این جلسه",
        "",
        *[f"- {m}" for m in MISTAKES],
        "",
        "## ۸. آنچه ادعا نمی‌کنم",
        "",
        *[f"- {b}" for b in BOUNDARIES],
        "",
        "---",
        "",
        f"شرکت: {client_txt} · تاریخ جلسه: {fa(today_on.isoformat())}",
        "",
        "امضای ارائه‌دهنده: ____________________     امضای شما: ____________________",
        "",
        kit_sentence,
        "",
        "سند راهنمای این جلسه: `MATERIALS/money/16-review-meeting-fa.md`.",
        "",
        rk.DEVELOPER_HTML,
        "",
    ])
    mp.write_text(md, encoding="utf-8")

    witness_html = [
        f'<li><b>{rk.esc(w["name"])}</b> — <span class="hint">{rk.esc(w["where"])}</span>'
        + (f'<br><code>{rk.esc(w["cmd"])}</code>' if w.get("cmd") else "")
        + f'<br>نشان می‌دهد: {rk.esc(w["shows"])}'
        + f'<br><span class="hint">نشان نمی‌دهد: {rk.esc(w["not_shows"])}</span></li>'
        for w in witnesses]
    exits_html = [
        f'<h3>{rk.esc(e["title"])}</h3><ul>'
        + "".join(f"<li>{rk.esc(line.replace('**', ''))}</li>" for line in e["lines"])
        + "</ul>"
        for e in exits]
    body = "".join([
        '<div class="honest"><b>این برگه برای روز چهاردهم است.</b> سه شاهد روی همان لپ‌تاپ اجرا '
        'می‌شود، بعد یک تصمیم روشن گرفته می‌شود: ادامه با پرداخت، تمدید بی‌هزینه، یا توقف — '
        'بی‌گلایه‌مندی.</div>',
        f'<p class="sub">برای: <b>{rk.esc(client_txt)}</b> · شروع: {fa(day0.isoformat())} · '
        f'روز بازبینی: <b>{fa(review.isoformat())}</b> · امروز: {fa(today_on.isoformat())}</p>',
        f'<p class="note">{rk.esc(status)}</p>',
        "<h2>۱. بیست دقیقهٔ همین جلسه</h2>",
        "<ul>" + "".join(f"<li>{rk.esc(row)}</li>" for row in rows) + "</ul>",
        "<h2>۲. سه شاهد که خودشان می‌سازند</h2>",
        "<ol>" + "".join(witness_html) + "</ol>",
        "<h2>۳. کارنامهٔ «آماده» — پنج شرط</h2>",
        "<table><thead><tr><th>شرط</th><th>عدد لازم</th><th>چرا</th></tr></thead><tbody>"
        + "".join(f"<tr><td>{rk.esc(g['name'])}</td><td>{rk.esc(g['want'])}</td>"
                  f"<td class=\"hint\">{rk.esc(g['why'])}</td></tr>" for g in gates)
        + "</tbody></table>",
        f'<p>«آماده» یعنی همهٔ پنج شرط با هم. اگر یکی مانده، تصمیم امروز <b>تمدید</b> است، نه '
        f'پرداخت: یک بار، بی‌هزینه، {fa(trial_days())} روز دیگر.</p>',
        "<h2>۴. دو خروجی روشن</h2>", "".join(exits_html),
        "<h2>۵. سه پرسش پایان</h2>",
        "<ul>" + "".join(f"<li>{rk.esc(q)}</li>" for q in QUESTIONS) + "</ul>",
        "<h2>۶. اگر امروز تصمیم نگرفتند</h2>",
        f'<p>تاریخ سرزدن: <b>{fa(after["next_on"])}</b> (امروز + {fa(after["days"])} روز). '
        f'ثبت در تابلو: <code>python3 prospects.py --outcome "{rk.esc(client_txt)}" '
        f'--result "بعداً" --next-on {after["next_on"]}</code></p>',
        "<ul>" + "".join(f'<li><b>{rk.esc(m["when"])}:</b> «{rk.esc(m["text"])}»</li>'
                         for m in after["messages"]) + "</ul>",
        f'<p class="hint">{rk.esc(after["rule"])}</p>',
        "<h2>۷. سه اشتباه در این جلسه</h2>",
        "<ul>" + "".join(f"<li>{rk.esc(m.replace('**', ''))}</li>" for m in MISTAKES) + "</ul>",
        "<h2>۸. آنچه ادعا نمی‌کنم</h2>",
        "<ul>" + "".join(f"<li>{rk.esc(b.replace('**', ''))}</li>" for b in BOUNDARIES) + "</ul>",
        f'<p class="sub">تاریخ جلسه: {fa(today_on.isoformat())} · '
        'امضای ارائه‌دهنده: ____________________ &nbsp;&nbsp; امضای شما: ____________________</p>',
        f'<p class="sub">{rk.esc(kit_sentence)}</p>',
        f'<p class="sub">{rk.DEVELOPER_HTML}</p>',
    ])
    hp.write_text(rk.page("جلسهٔ بازبینی دو هفته‌ای — ایستگاه تصمیم مشتقه", body,
                          subtitle=f"{client_txt} · {fa(review.isoformat())}"),
                  encoding="utf-8")
    return hp, mp


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="برگهٔ جلسهٔ بازبینی دو هفته‌ای (سه شاهد، دو خروجی)")
    ap.add_argument("--client", default="", help="نام مشتری یا شرکت")
    ap.add_argument("--start", default="", help="روز شروع آزمون YYYY-MM-DD (پیش‌فرض: امروز)")
    ap.add_argument("--on", default="", help="روز جلسهٔ بازبینی YYYY-MM-DD (پیش‌فرض: امروز)")
    ap.add_argument("--monthly", type=int, default=0, help="حق دسترسی ماهانه (ریال)؛ ندهید، «توافقی»")
    ap.add_argument("--setup", type=int, default=0, help="مبلغ راه‌اندازی/آموزش (ریال)")
    ap.add_argument("--follow-on", default="", help="تاریخ سرزدن اگر تصمیم نگرفتند (پیش‌فرض: +۳۰ روز)")
    ap.add_argument("--html", default="", help="مسیر برگهٔ چاپی (پیش‌فرض: data/review-meeting.html)")
    ap.add_argument("--md", default="", help="مسیر نسخهٔ متنی (پیش‌فرض: data/review-meeting.md)")
    ap.add_argument("--json", action="store_true", help="خروجی ماشین‌خوان")
    ap.add_argument("--version", action="version", version=f"review_meeting {VERSION}")
    a = ap.parse_args(argv)

    try:
        h, m = build_review(a.client, start=a.start or None, on=a.on or None,
                            monthly_rial=a.monthly, setup_rial=a.setup,
                            follow_on=a.follow_on or None,
                            html_path=a.html or None, md_path=a.md or None)
    except ValueError as exc:
        print(f"خطا: {exc}", file=sys.stderr)
        return 2

    left = days_left(a.start or None, a.on or None)
    if a.json:
        print(json.dumps({"html": str(h), "md": str(m), "client": a.client or None,
                          "start": _parse(a.start or None).isoformat(),
                          "on": _parse(a.on or None).isoformat(),
                          "review": review_day(a.start or None).isoformat(),
                          "days_left": left, "trial_days": trial_days(),
                          "follow_on": follow_up(a.on or None,
                                                 a.follow_on or None)["next_on"],
                          "price_given": bool(a.monthly or a.setup),
                          "kit": kit_facts(),
                          "gates": [{"name": g["name"], "want": g["want"]} for g in gate_conditions()],
                          "outcomes": [e["key"] for e in outcomes(a.monthly, a.setup)]},
                         ensure_ascii=False))
        return 0
    print("برگهٔ جلسهٔ بازبینی ساخته شد:")
    print("  برگهٔ چاپی:", h)
    print("  نسخهٔ متنی (برای ایمیل/واتساپ):", m)
    print("  روز بازبینی:", fa(review_day(a.start or None).isoformat()), "·", status_line(a.start or None, a.on or None))
    print("  قیمت:", price_line(a.monthly, a.setup)["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
