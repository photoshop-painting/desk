"""پیشنهاد یک‌صفحه‌ای — برگه‌ای که دست شرکت یا کارگزاری می‌دهید.

چرا جدا از «سند مجوز» است: آن سند، پس از توافق امضا می‌شود؛ این برگه، **پیش از** توافق دست
طرف مقابل می‌افتد و در یک صفحه می‌گوید مسئله چیست، چه چیزی تحویل داده می‌شود، چطور راستی‌آزمایی
می‌کنند، و مرزها کجاست. هیچ عدد سودی در آن نیست و هیچ قیمتی هم از خودش نمی‌سازد: اگر قیمتی
نگویید، جای آن می‌نویسد «توافقی».

اجرا:
    python3 offer.py --client "نام شرکت"                 # ساخت برگه
    python3 offer.py --client "نام شرکت" --monthly 40000000
    python3 offer.py --json                              # خلاصهٔ ماشین‌خوان
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

import license as licmod  # noqa: E402
import reportkit as rk  # noqa: E402

VERSION = "0.1.0"
DATA = BASE / "data"
OFFER_MD = DATA / "offer-one-pager.md"
OFFER_HTML = DATA / "offer-one-pager.html"

_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa(value) -> str:
    """عدد را با رقم فارسی می‌نویسد (برگه دست شرکت می‌رود، پس فارسی‌خوان باشد)."""
    return str(value).translate(_DIGITS)


def fa_num(value: int) -> str:
    return fa(f"{int(value):,}").replace(",", "٬")


def _kit_facts() -> dict:
    """اگر بستهٔ تحویل ساخته شده باشد، عددهای واقعی‌اش را برمی‌دارد (نه عدد حدسی)."""
    # دو جا: درخت اصلی (پوشهٔ delivery) و خودِ بسته (وقتی همین کد داخل بسته اجرا می‌شود)
    for kit in (BASE.parent / "delivery" / "iran-desk-kit", BASE.parent):
        manifest = kit / "KIT-MANIFEST.json"
        if manifest.exists() and (kit / "docs").exists():
            try:
                m = json.loads(manifest.read_text(encoding="utf-8"))
                docs = len([p for p in (kit / "docs").glob("*.md") if p.name[:2].isdigit()])
                return {"kit": kit.name, "files": m.get("files_count"), "version": m.get("version"),
                        "bytes_kb": round((m.get("bytes") or 0) / 1024), "docs": docs or None}
            except (json.JSONDecodeError, OSError):
                break
    return {}


def _docs_phrase(facts: dict) -> str:
    """شمار سندهای تحلیلی از خودِ پوشه خوانده می‌شود؛ عدد ثابت در متن نمی‌نویسیم."""
    return (f"{fa(facts['docs'])} سند تحلیلی فارسی" if facts.get("docs")
            else "مجموعهٔ اسناد تحلیلی فارسی")


def price_line(monthly_rial: int = 0, setup_rial: int = 0) -> dict:
    """جملهٔ قیمت. عددی که ندهید، ساخته نمی‌شود."""
    if not monthly_rial and not setup_rial:
        return {"text": "توافقی؛ عدد را در جلسه با هم می‌گذاریم (اول راه‌اندازی، بعد ماهانه).",
                "given": False}
    parts = []
    if setup_rial:
        parts.append(f"راه‌اندازی یک‌باره: {fa_num(setup_rial)} ریال")
    if monthly_rial:
        parts.append(f"ماهانه: {fa_num(monthly_rial)} ریال")
    return {"text": " · ".join(parts), "given": True}


def build_offer(client: str = "", *, monthly_rial: int = 0, setup_rial: int = 0,
                html_path: Path | str | None = None,
                md_path: Path | str | None = None) -> tuple[Path, Path]:
    """برگهٔ پیشنهاد را می‌سازد. خروجی: (مسیر HTML، مسیر متن)."""
    hp = Path(html_path) if html_path else OFFER_HTML
    mp = Path(md_path) if md_path else OFFER_MD
    hp.parent.mkdir(parents=True, exist_ok=True)
    mp.parent.mkdir(parents=True, exist_ok=True)

    client_txt = client.strip() or "نام شرکت / کارگزاری شما"
    today = fa(datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    kit = _kit_facts()
    price = price_line(monthly_rial, setup_rial)
    ladder = licmod.ladder()

    kit_sentence = (
        f"بستهٔ کد و اسناد (`{kit['kit']}`) با {fa(kit['files'])} پرونده و اثر انگشت `sha256` هر پرونده — "
        "روی رایانهٔ خودتان، بدون نصب چیزی جز پایتون."
        if kit.get("files") else
        "بستهٔ کد و اسناد، همراه قالب‌های داده و اثر انگشت هر پرونده — روی رایانهٔ خودتان، "
        "بدون نصب چیزی جز پایتون.")

    md = "\n".join([
        "# پیشنهاد یک‌صفحه‌ای — ایستگاه تصمیم مشتقه", "",
        f"**برای:** {client_txt} · **تاریخ:** {today}", "",
        "## مسئله‌ای که می‌بینم", "",
        "سیگنال‌ها و نرم‌افزارهای زیادی «کجا سود هست» می‌گویند؛ هیچ‌کدام نمی‌گویند با **کارمزد، "
        "اسپرد و فاصله تا اخطاریهٔ مارجین** آن سیگنال می‌مانَد یا می‌افتد. نتیجه‌اش معامله‌هایی است "
        "که روی کاغذ سود داشتند و روی صورتحساب، زیان.", "",
        "## سه چیزی که این ایستگاه اضافه می‌کند", "",
        "۱. **داوری سیگنال** (می‌مانَد یا می‌افتد): هر سیگنال — از هر ابزاری — روی موتور ریاضی "
        "می‌رود و با دلیل روشن می‌گوید کدام دروازه را رد کرد.",
        "۲. **اندازه‌گیری ریسک پیش از سفارش**: وجه تضمین، سقف موقعیت، فاصله تا مارجین‌کال، نرخ برد "
        "سر‌به‌سر، و اینکه با شوک قیمت یا کارمزد دو برابر، معامله زنده می‌مانَد یا نه.",
        "۳. **بستهٔ شاهد بازتولیدپذیر**: همهٔ عددها همراه روش حساب و اثر انگشت `sha256` تحویل می‌شود؛ "
        "مدیر ریسک شما هر ردیف را خودش می‌تواند بازتولید کند.", "",
        "## چه چیزی تحویل داده می‌شود", "",
        f"- {kit_sentence}",
        f"- میز معاملات و دیده‌بان خبر، ایستگاه یازده‌گامی، جزوهٔ راهبردها با درصد هر کدام، و "
        f"{_docs_phrase(kit)} (از سنجش مسیرهای داده تا ریاضیِ بقا).",
        "- یک مجموعهٔ آزمون که **خودتان** اجرا می‌کنید و یک برگهٔ امضادار آزمون کور، تا ادعا را "
        "از دهان من نشنوید.", "",
        "## هزینه تا اولین تصمیم: صفر", "",
        "- سه پروفایل دادهٔ **رایگان و بدون کلید** همراه برنامه است (نرخ دلار، طلا و سکه، و یک "
        "صرافی ریالی). تا وقتی کارنامهٔ دو هفته‌ای «آماده» نشده، هیچ خرید داده‌ای پیشنهاد نمی‌شود.",
        "- روی رایانهٔ خودتان اجرا می‌شود؛ داده‌ای به بیرون نمی‌رود و رمز سامانهٔ کارگزاری هم "
        "هیچ‌وقت پرسیده نمی‌شود.", "",
        "## شکل ارائه", "",
        *[f"- **{row['step']}**: {row['what']} — {row['basis']}" for row in ladder], "",
        f"**قیمت:** {price['text']}", "",
        "## مرزها (همین‌ها را بی‌کم‌وکاست می‌گویم)", "",
        "- **هیچ سود تضمینی و هیچ پیش‌بینی قیمت در کار نیست.** خروجی، «عدد و دلیل» است.",
        "- **هیچ سفارشی به کارگزاری فرستاده نمی‌شود** و کدی هم برایش نوشته نشده؛ طبق ابلاغیهٔ مهر "
        "۱۳۹۹ سازمان بورس، معاملات الگوریتمی خودکار در بورس ایران مجاز نیست. اجرا با کاربر است.",
        "- **درصد از سود نمی‌گیرم**؛ حق دسترسی و پشتیبانی، مبلغ روشن و قابل پیش‌بینی است.",
        "- هیچ عدد بدون منبع وارد نمی‌شود؛ جای عدد ناشناخته (مثل وجه تضمین) عدد حدسی نمی‌نویسیم.", "",
        "## راستی‌آزمایی پیش از امضا", "",
        "جلسهٔ ۲۵ دقیقه‌ای روی لپ‌تاپ خودتان: سلامت برنامه، داوری یک سیگنال واقعی خودتان، "
        "حساب‌رسی یک معاملهٔ گذشته با کارمزد واقعی، و ساخت بستهٔ شاهد. بعد هم این فرمان‌ها را "
        "خودتان اجرا کنید:", "",
        "```bash",
        "cd station && python3 -m unittest discover -s tests   # مجموعهٔ آزمون همراه بسته",
        "python3 selftest.py                                  # آزمون ۱۰ دقیقه‌ای، هر سنجه دو بار",
        "```", "",
        "---", "",
        "امضای ارائه‌دهنده: ____________________     امضای شما: ____________________", "",
        rk.DEVELOPER_HTML if hasattr(rk, "DEVELOPER_HTML") else licmod.CREDIT, "",
    ])
    mp.write_text(md, encoding="utf-8")

    body = "".join([
        '<div class="honest"><b>یک‌صفحه، بدون وعده:</b> این برگه هیچ سودی را پیش‌بینی نمی‌کند و '
        'هیچ سفارشی نمی‌فرستد؛ فقط می‌گوید چه چیزی تحویل می‌شود و چطور خودتان بازبینی می‌کنید.</div>',
        f'<p class="sub">برای: <b>{rk.esc(client_txt)}</b> · تاریخ: {rk.esc(today)}</p>',
        "<h2>۱. مسئله‌ای که می‌بینم</h2>",
        '<p>سیگنال‌ها و نرم‌افزارهای زیادی «کجا سود هست» می‌گویند؛ هیچ‌کدام نمی‌گویند با '
        '<b>کارمزد، اسپرد و فاصله تا اخطاریهٔ مارجین</b> آن سیگنال می‌مانَد یا می‌افتد. نتیجه‌اش '
        'معامله‌هایی است که روی کاغذ سود داشتند و روی صورتحساب، زیان.</p>',
        "<h2>۲. سه چیزی که این ایستگاه اضافه می‌کند</h2>",
        "<ol><li><b>داوری سیگنال</b> (می‌مانَد یا می‌افتد): هر سیگنال، از هر ابزاری، روی موتور "
        "ریاضی می‌رود و با دلیل روشن می‌گوید کدام دروازه را رد کرد.</li>"
        "<li><b>اندازه‌گیری ریسک پیش از سفارش</b>: وجه تضمین، سقف موقعیت، فاصله تا مارجین‌کال، "
        "نرخ برد سر‌به‌سر، و آزمون شوک (کارمزد دو و سه برابر، حرکت مخالف).</li>"
        "<li><b>بستهٔ شاهد بازتولیدپذیر</b>: عددها همراه روش حساب و اثر انگشت <code>sha256</code> "
        "تحویل می‌شود.</li></ol>",
        "<h2>۳. چه چیزی تحویل داده می‌شود</h2>",
        f'<ul><li>{rk.esc(kit_sentence)}</li>'
        f"<li>میز معاملات و دیده‌بان خبر، ایستگاه یازده‌گامی، جزوهٔ راهبردها، و "
        f"{_docs_phrase(kit)}.</li>"
        "<li>یک مجموعهٔ آزمون که خودتان اجرا می‌کنید و یک برگهٔ امضادار آزمون کور.</li></ul>",
        "<h2>۴. هزینه تا اولین تصمیم: صفر</h2>",
        "<ul><li>سه پروفایل دادهٔ <b>رایگان و بدون کلید</b> همراه برنامه است. تا وقتی کارنامهٔ "
        "دو هفته‌ای «آماده» نشده، هیچ خرید داده‌ای پیشنهاد نمی‌شود.</li>"
        "<li>روی رایانهٔ خودتان اجرا می‌شود؛ داده‌ای به بیرون نمی‌رود و رمز سامانهٔ کارگزاری "
        "هیچ‌وقت پرسیده نمی‌شود.</li></ul>",
        "<h2>۵. شکل ارائه</h2>",
        "<table><thead><tr><th>پله</th><th>چه چیزی</th><th>در برابر چه چیزی</th></tr></thead><tbody>"
        + "".join(f"<tr><td>{rk.esc(row['step'])}</td><td>{rk.esc(row['what'])}</td>"
                  f"<td>{rk.esc(row['basis'])}</td></tr>" for row in ladder)
        + "</tbody></table>",
        f'<p><b>قیمت:</b> {rk.esc(price["text"])}</p>',
        "<h2>۶. مرزها</h2>",
        "<ul><li><b>هیچ سود تضمینی و هیچ پیش‌بینی قیمت در کار نیست.</b> خروجی، «عدد و دلیل» است.</li>"
        "<li><b>هیچ سفارشی به کارگزاری فرستاده نمی‌شود</b>؛ طبق ابلاغیهٔ مهر ۱۳۹۹ سازمان بورس، "
        "معاملات الگوریتمی خودکار در بورس ایران مجاز نیست.</li>"
        "<li><b>درصد از سود نمی‌گیرم</b>؛ حق دسترسی و پشتیبانی، مبلغ روشن و قابل پیش‌بینی است.</li>"
        "<li>هیچ عدد بدون منبع وارد نمی‌شود؛ جای عدد ناشناخته عدد حدسی نمی‌نویسیم.</li></ul>",
        "<h2>۷. راستی‌آزمایی پیش از امضا</h2>",
        '<p class="note">جلسهٔ ۲۵ دقیقه‌ای روی لپ‌تاپ خودتان: سلامت برنامه، داوری یک سیگنال واقعی '
        'خودتان، حساب‌رسی یک معاملهٔ گذشته با کارمزد واقعی، و ساخت بستهٔ شاهد. بعد این دو فرمان را '
        'خودتان اجرا کنید: <code>python3 -m unittest discover -s tests</code> و '
        '<code>python3 selftest.py</code>.</p>',
        '<p class="sub">امضای ارائه‌دهنده: ____________________ &nbsp;&nbsp; '
        'امضای شما: ____________________</p>',
        f'<p class="sub">{rk.DEVELOPER_HTML}</p>',
    ])
    hp.write_text(rk.page("پیشنهاد یک‌صفحه‌ای — ایستگاه تصمیم مشتقه", body,
                          subtitle=f"{client_txt} · {today}"), encoding="utf-8")
    return hp, mp


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="پیشنهاد یک‌صفحه‌ای برای شرکت یا کارگزاری")
    ap.add_argument("--client", default="", help="نام شرکت یا کارگزاری")
    ap.add_argument("--monthly", type=int, default=0, help="حق دسترسی ماهانه (ریال)؛ ندهید، «توافقی» می‌شود")
    ap.add_argument("--setup", type=int, default=0, help="مبلغ راه‌اندازی (ریال)")
    ap.add_argument("--json", action="store_true", help="خروجی ماشین‌خوان")
    ap.add_argument("--version", action="version", version=f"offer {VERSION}")
    a = ap.parse_args(argv)

    h, m = build_offer(a.client, monthly_rial=a.monthly, setup_rial=a.setup)
    if a.json:
        print(json.dumps({"html": str(h), "md": str(m), "client": a.client or None,
                          "price_given": bool(a.monthly or a.setup), "kit": _kit_facts()},
                         ensure_ascii=False))
        return 0
    print("پیشنهاد یک‌صفحه‌ای ساخته شد:")
    print("  برگهٔ چاپی:", h)
    print("  نسخهٔ متنی (برای ایمیل/واتساپ):", m)
    print("  قیمت:", price_line(a.monthly, a.setup)["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
