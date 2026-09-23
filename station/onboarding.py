"""روز اول مشتری — برگهٔ «از بله تا پایان هفتهٔ دوم».

جای این برگه در زنجیره: `offer.py` پیش از جلسه دست طرف مقابل می‌افتد، `outreach.py` جلسه را
می‌گیرد، `prospects.py` پیگیری را نگه می‌دارد. این برگه برای لحظهٔ بعد از «بله» است و یک چیز را
جواب می‌دهد: **فردا صبح چه کار کنم و در دو هفتهٔ اول چه چیزی نمی‌فروشم؟**

سه قاعده که در خود برگه قفل شده‌اند و از جای دیگری خوانده می‌شوند (نه دست‌نویس):

- **طول آزمون**: از `license.TRIAL_DAYS` (روزشمار اجازه‌نامهٔ آزمون) — پس تاریخ بازبینی، خودِ
  همان روزی است که اجازه‌نامهٔ آزمون تمام می‌شود.
- **شرط‌های «کارنامهٔ آماده»**: از پیش‌فرض‌های `daily_trial.scorecard` (ده روز ثبت، پنج روز واقعی،
  شصت درصد بازسنجی، سه حرکت معنادار، زنجیرهٔ سالم).
- **عددهای بستهٔ تحویل**: از `KIT-MANIFEST.json` — عدد حدسی روی این برگه نمی‌رود.

اجرا:
    python3 onboarding.py --client "نام مشتری"
    python3 onboarding.py --client "نام مشتری" --start 2026-09-22 --monthly 40000000
    python3 onboarding.py --json
"""
from __future__ import annotations

import argparse
import inspect
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import daily_trial as dailytrial  # noqa: E402
import license as licmod  # noqa: E402
import reportkit as rk  # noqa: E402
from offer import _kit_facts as kit_facts, fa, fa_num, price_line  # noqa: E402

VERSION = "0.1.0"
DATA = BASE / "data"
PACK_MD = DATA / "onboarding-pack.md"
PACK_HTML = DATA / "onboarding-pack.html"

def trial_days() -> int:
    """طول آزمون دو هفته‌ای — از خود ماژول اجازه‌نامه، نه از حافظهٔ من."""
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


def gate_conditions() -> list[dict]:
    """پنج شرط «کارنامهٔ آماده» با عددهای خودِ کد (اگر کسی شرط‌ها را عوض کند، برگه هم عوض می‌شود)."""
    p = inspect.signature(dailytrial.scorecard).parameters
    days = int(p["target_days"].default)
    real_days = int(p["target_real_days"].default)
    ratio = int(round(float(p["min_marked_ratio"].default) * 100))
    moves = int(p["min_moves"].default)
    return [
        {"name": "تداوم روزانه", "want": f"{fa(days)} روز ثبت‌شده",
         "why": f"هر روز کاری یک بار «مراسم امروز»؛ {fa(days)} روز یعنی دو هفتهٔ کاری."},
        {"name": "روزهای با دادهٔ واقعی", "want": f"{fa(real_days)} روز واقعی (نه ساختگی)",
         "why": "خوراک آزمایشی برای تمرین است؛ برای تصمیم، روز واقعی لازم است."},
        {"name": "بازسنجی دفتر", "want": f"دست‌کم {fa(ratio)}٪ ردیف‌ها بازسنجی‌شده",
         "why": "بازسنجی نشان می‌دهد موتور با قیمت‌های تازه هم اجرا می‌شود."},
        {"name": "حرکت واقعی در دفتر", "want": f"{fa(moves)} حرکت معنادار (دست‌کم یکی بازتر، یکی بسته)",
         "why": "هم فرصت تازه لازم است، هم فرصتی که بسته شده؛ هر دو نشانهٔ درست‌کاری است."},
        {"name": "زنجیرهٔ هش دفتر", "want": "سالم (هیچ ردیفی دست‌کاری نشده)",
         "why": "اگر زنجیره بشکند، تا پیدا نشود به دفتر استناد نکنید."},
    ]


def first_day_steps(client: str) -> list[dict]:
    """پنج کار روز اول، به همین ترتیب. هر ردیف: چه کاری، کجا، و چرا."""
    name = client.strip() or "نام مشتری"
    return [
        {"n": 1, "title": "اجازه‌نامهٔ آزمون دو هفته‌ای، نام‌دار",
         "where": "ترمینال، در پوشهٔ station",
         "cmd": f'python3 license.py --grant "{name}" --trial --save',
         "then": "python3 license.py --document",
         "why": f"تا پایان این {fa(trial_days())} روز هیچ تعهد ماهانه‌ای گرفته نمی‌شود؛ دسترسی "
                "روزشمار، نام‌دار و امضاشده است. سند چاپی‌اش را همان روز بدهید."},
        {"n": 2, "title": "نصب روی رایانهٔ خودشان",
         "where": "بستهٔ تحویل → `iran-desk-kit.zip` → `START-HERE-FA.md` → `run-gui.bat`",
         "cmd": None, "then": None,
         "why": "همه‌چیز محلی است: نه حسابی ساخته می‌شود، نه رمز سامانهٔ کارگزاری پرسیده می‌شود، "
                "نه داده‌ای به بیرون می‌رود."},
        {"n": 3, "title": "اتصال داده: سه پروفایل رایگان، صفر خرید",
         "where": "گام ۲ → «امتحان منابع رایگان»",
         "cmd": None, "then": None,
         "why": "تا کارنامه آماده نشود، هیچ خرید داده‌ای پیشنهاد نمی‌شود؛ اگر روزی سرویس خریدنی "
                "گرفتید، جایش در همان گام ۲ است."},
        {"n": 4, "title": "اعداد امروز از کارگزاری خودشان",
         "where": "گام ۲ → جدول اسنپ‌شات (دستی یا «چسباندن از سامانهٔ کارگزاری»)",
         "cmd": None, "then": None,
         "why": "موتور با عدد واقعی خودشان کار می‌کند، نه با نمونهٔ ما؛ وجه تضمین و کارمزد جزو "
                "همان عددهای ورودی است."},
        {"n": 5, "title": "مراسم امروز و راستی‌آزمایی به دست خودشان",
         "where": "گام ۹ → «اجرای مراسم امروز» و بعد پروندهٔ سرمایه‌گذار",
         "cmd": "python3 selftest.py",
         "then": "python3 -m unittest discover -s tests",
         "why": "روز اول کارنامه زرد و قرمز است — این طبیعی است. عددها ساختهٔ ما نیستند؛ خودشان "
                "می‌توانند هر ردیف را بازتولید کنند."},
    ]


def no_buy_gate() -> list[str]:
    """دو هفتهٔ اول چه چیزی خریده نمی‌شود (سرمایهٔ خودشان دست‌نخورده می‌مانَد)."""
    d = fa(trial_days())
    return [
        f"**هیچ دادهٔ خریدنی** لازم نیست؛ در این {d} روز فقط پروفایل‌های رایگان و اسنپ‌شات خودتان.",
        "**هیچ سفارشی** به کارگزاری فرستاده نمی‌شود و کدی هم برایش نوشته نشده (ابلاغیهٔ مهر ۱۳۹۹).",
        "**هیچ سرمایه‌ای** از طرف شما درگیر نمی‌شود؛ تمرین روی همان حساب واقعی خودتان، با اندازهٔ "
        "کوچک، تصمیم خودتان.",
        f"**هیچ پرداخت ماهانه‌ای** در این {d} روز گرفته نمی‌شود؛ فقط پلهٔ راه‌اندازی/آموزش.",
    ]


def build_onboarding(client: str = "", *, start: str | None = None, monthly_rial: int = 0,
                     setup_rial: int = 0, html_path: Path | str | None = None,
                     md_path: Path | str | None = None) -> tuple[Path, Path]:
    """برگهٔ روز اول را می‌سازد. خروجی: (مسیر HTML، مسیر متن)."""
    hp = Path(html_path) if html_path else PACK_HTML
    mp = Path(md_path) if md_path else PACK_MD
    hp.parent.mkdir(parents=True, exist_ok=True)
    mp.parent.mkdir(parents=True, exist_ok=True)

    client_txt = client.strip() or "نام مشتری"
    day0 = _parse(start)
    review = day0 + timedelta(days=trial_days())
    steps = first_day_steps(client_txt)
    gates = gate_conditions()
    kit = kit_facts()
    price = price_line(monthly_rial, setup_rial)
    ladder = licmod.ladder()

    kit_sentence = (
        f"بستهٔ `{kit['kit']}` با {fa(kit['files'])} پرونده و اثر انگشت `sha256` هر پرونده"
        if kit.get("files") else
        "بستهٔ کد و اسناد با اثر انگشت `sha256` هر پرونده")

    md = "\n".join([
        "# روز اول مشتری — از «بله» تا پایان هفتهٔ دوم", "",
        f"**برای:** {client_txt} · **شروع:** {fa(day0.isoformat())} · "
        f"**روز بازبینی:** {fa(review.isoformat())}", "",
        f"**قرار امروز:** دسترسی آزمون {fa(trial_days())} روزه، بدون هیچ تعهد ماهانه.", "",
        "## پنج کار روز اول (به همین ترتیب)", "",
        *[f"{fa(s['n'])}. **{s['title']}** — {s['where']}" +
          (f"  \n   `{s['cmd']}`" if s.get("cmd") else "") +
          (f"  \n   بعد: `{s['then']}`" if s.get("then") else "") + f"  \n   چرا: {s['why']}"
          for s in steps],
        "",
        "## در این دو هفته چه چیزی خریده نمی‌شود", "",
        *[f"- {row}" for row in no_buy_gate()],
        "",
        "## شرط‌های پایان هفتهٔ دوم (کارنامهٔ «آماده»)", "",
        "| شرط | عدد لازم | چرا |", "| --- | --- | --- |",
        *[f"| {g['name']} | {g['want']} | {g['why']} |" for g in gates], "",
        f"روز بازبینی: **{fa(review.isoformat())}**. اگر کارنامه «آماده» بود، پلهٔ دوم معنی دارد؛ "
        "اگر نبود، بازبینی را عقب می‌اندازیم و همان دو هفته‌ای که هست را بررسی می‌کنیم — بدون "
        "ادعا و بدون عجله.", "",
        "## پله‌ها و قاعدهٔ پرداخت", "",
        *[f"- **{row['step']}**: {row['what']} — {row['basis']}" for row in ladder],
        "",
        f"**قیمت:** {price['text']}", "",
        "پرداخت در برابر **شاهد** است، نه وعده: هر پله پس از تحویل پروندهٔ همان پله. "
        "**درصدی از سود گرفته نمی‌شود**؛ اگر روزی کسی چنین چیزی پیشنهاد داد، همان‌جا رد کنید.", "",
        "**هیچ سود تضمینی و هیچ پیش‌بینی قیمت در کار نیست**؛ خروجی این ایستگاه «عدد و دلیل» است "
        "و تصمیم، تصمیم خودتان.", "",
        "## ریتم روز شما (شصت ثانیه)", "",
        "- هر روز کاری: «مراسم امروز» (گام ۹) — یک بار، همان ساعت.",
        "- هفتهٔ اول: فقط ثبت و نگاه؛ هیچ تصمیم بزرگی بر پایهٔ کارنامهٔ ناتمام گرفته نمی‌شود.",
        f"- پایان {fa(trial_days())} روز: بازبینی با هم، روی همان لپ‌تاپ، با پروندهٔ سرمایه‌گذار و "
        "زنجیرهٔ سالم.", "",
        "## اگر وسط راه پشیمان شدید", "",
        "- دسترسی در همان تاریخ نام‌دار تمام می‌شود؛ هیچ قفلی روی برنامه نیست.",
        "- پرونده‌ها، دفترها و اعداد روی رایانهٔ خودتان می‌مانَد (مالکیت با شماست).",
        "- دادهٔ شما هیچ‌وقت جایی فرستاده نشده که پس گرفته شود.", "",
        "## سؤال پایان بازبینی", "",
        "«چه چیزی را باید در این دو هفته ببینید تا بگویید ارزش داشت؟» — جواب همین سؤال، کارِ "
        "هفتهٔ سوم را تعیین می‌کند.", "",
        "---", "",
        f"اجرا و آموزش (پلهٔ ۱): پرداخت‌شده · اجازه‌نامهٔ آزمون تا {fa(review.isoformat())}", "",
        "امضای ارائه‌دهنده: ____________________     امضای شما: ____________________", "",
        f"تحویل داده می‌شود: {kit_sentence}.", "",
        rk.DEVELOPER_HTML if hasattr(rk, "DEVELOPER_HTML") else licmod.CREDIT, "",
    ])
    mp.write_text(md, encoding="utf-8")

    def steps_html() -> str:
        rows = []
        for s in steps:
            cmd = f'<br><code>{rk.esc(s["cmd"])}</code>' if s.get("cmd") else ""
            then = f'<br>بعد: <code>{rk.esc(s["then"])}</code>' if s.get("then") else ""
            rows.append(f'<li><b>{rk.esc(s["title"])}</b> — <span class="hint">{rk.esc(s["where"])}'
                        f'</span>{cmd}{then}<br><span class="hint">چرا: {rk.esc(s["why"])}</span></li>')
        return "<ol>" + "".join(rows) + "</ol>"

    body = "".join([
        '<div class="honest"><b>این برگه بعد از «بله» است، نه قبل از آن.</b> دو هفتهٔ اول، '
        'دسترسی آزمون است و هیچ تعهد ماهانه‌ای گرفته نمی‌شود؛ هدف این دو هفته فقط یک چیز است: '
        'دیدن اینکه کارنامه «آماده» می‌شود یا نه.</div>',
        f'<p class="sub">برای: <b>{rk.esc(client_txt)}</b> · شروع: {fa(day0.isoformat())} · '
        f'روز بازبینی: <b>{fa(review.isoformat())}</b></p>',
        "<h2>۱. پنج کار روز اول</h2>", steps_html(),
        "<h2>۲. در این دو هفته چه چیزی خریده نمی‌شود</h2>",
        "<ul>" + "".join(f"<li>{rk.esc(row.replace('**', ''))}</li>" for row in no_buy_gate()) + "</ul>",
        "<h2>۳. شرط‌های پایان هفتهٔ دوم (کارنامهٔ «آماده»)</h2>",
        "<table><thead><tr><th>شرط</th><th>عدد لازم</th><th>چرا</th></tr></thead><tbody>"
        + "".join(f"<tr><td>{rk.esc(g['name'])}</td><td>{rk.esc(g['want'])}</td>"
                  f"<td class=\"hint\">{rk.esc(g['why'])}</td></tr>" for g in gates)
        + "</tbody></table>",
        f'<p class="note">روز بازبینی <b>{fa(review.isoformat())}</b> است. اگر کارنامه «آماده» بود، '
        'پلهٔ دوم معنی دارد؛ اگر نبود، بازبینی عقب می‌افتد و همان دو هفته بررسی می‌شود.</p>',
        "<h2>۴. پله‌ها و قاعدهٔ پرداخت</h2>",
        "<table><thead><tr><th>پله</th><th>چه چیزی</th><th>در برابر چه چیزی</th></tr></thead><tbody>"
        + "".join(f"<tr><td>{rk.esc(r['step'])}</td><td>{rk.esc(r['what'])}</td>"
                  f"<td>{rk.esc(r['basis'])}</td></tr>" for r in ladder)
        + "</tbody></table>",
        f'<p><b>قیمت:</b> {rk.esc(price["text"])}</p>',
        '<p>پرداخت در برابر <b>شاهد</b> است، نه وعده: هر پله پس از تحویل پروندهٔ همان پله. '
        '<b>هیچ درصدی از سود گرفته نمی‌شود.</b></p>',
        '<p><b>هیچ سود تضمینی و هیچ پیش‌بینی قیمت در کار نیست</b>؛ خروجی این ایستگاه «عدد و '
        'دلیل» است و تصمیم، تصمیم خودتان.</p>',
        "<h2>۵. ریتم روز شما (شصت ثانیه)</h2>",
        "<ul><li>هر روز کاری، همان ساعت: «مراسم امروز» در گام ۹.</li>"
        "<li>هفتهٔ اول فقط ثبت و نگاه؛ هیچ تصمیم بزرگی بر پایهٔ کارنامهٔ ناتمام.</li>"
        f"<li>پایان {fa(trial_days())} روز: بازبینی با هم، روی همان لپ‌تاپ.</li></ul>",
        "<h2>۶. اگر وسط راه پشیمان شدید</h2>",
        "<ul><li>دسترسی در همان تاریخ نام‌دار تمام می‌شود؛ هیچ قفلی روی برنامه نیست.</li>"
        "<li>پرونده‌ها و دفترها روی رایانهٔ خودتان می‌مانَد؛ مالکیت با شماست.</li>"
        "<li>داده‌ای جایی فرستاده نشده که پس گرفته شود.</li></ul>",
        "<h2>۷. سؤال پایان بازبینی</h2>",
        '<p class="note">«چه چیزی را باید در این دو هفته ببینید تا بگویید ارزش داشت؟» — '
        'جواب همین سؤال، کارِ هفتهٔ سوم را تعیین می‌کند.</p>',
        f'<p class="sub">اجرا و آموزش (پلهٔ ۱): پرداخت‌شده · اجازه‌نامهٔ آزمون تا '
        f'{fa(review.isoformat())}</p>',
        '<p class="sub">امضای ارائه‌دهنده: ____________________ &nbsp;&nbsp; '
        'امضای شما: ____________________</p>',
        f'<p class="sub">تحویل داده می‌شود: {rk.esc(kit_sentence)}.</p>',
        f'<p class="sub">{rk.DEVELOPER_HTML}</p>',
    ])
    hp.write_text(rk.page("روز اول مشتری — ایستگاه تصمیم مشتقه", body,
                          subtitle=f"{client_txt} · {fa(day0.isoformat())}"),
                  encoding="utf-8")
    return hp, mp


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="برگهٔ روز اول مشتری (از «بله» تا پایان هفتهٔ دوم)")
    ap.add_argument("--client", default="", help="نام مشتری یا شرکت")
    ap.add_argument("--start", default="", help="روز شروع YYYY-MM-DD (پیش‌فرض: امروز)")
    ap.add_argument("--monthly", type=int, default=0, help="حق دسترسی ماهانه (ریال)؛ ندهید، «توافقی»")
    ap.add_argument("--setup", type=int, default=0, help="مبلغ راه‌اندازی/آموزش (ریال)")
    ap.add_argument("--json", action="store_true", help="خروجی ماشین‌خوان")
    ap.add_argument("--version", action="version", version=f"onboarding {VERSION}")
    a = ap.parse_args(argv)

    try:
        h, m = build_onboarding(a.client, start=a.start or None,
                                monthly_rial=a.monthly, setup_rial=a.setup)
    except ValueError as exc:
        print(f"خطا: {exc}", file=sys.stderr)
        return 2

    day0 = _parse(a.start or None)
    if a.json:
        print(json.dumps({"html": str(h), "md": str(m), "client": a.client or None,
                          "start": day0.isoformat(),
                          "review": (day0 + timedelta(days=trial_days())).isoformat(),
                          "trial_days": trial_days(), "price_given": bool(a.monthly or a.setup),
                          "kit": kit_facts(),
                          "gates": [{"name": g["name"], "want": g["want"]} for g in gate_conditions()]},
                         ensure_ascii=False))
        return 0
    print("برگهٔ روز اول مشتری ساخته شد:")
    print("  برگهٔ چاپی:", h)
    print("  نسخهٔ متنی (برای ایمیل/واتساپ):", m)
    print(f"  روز بازبینی: {fa((day0 + timedelta(days=trial_days())).isoformat())}")
    print("  قیمت:", price_line(a.monthly, a.setup)["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
