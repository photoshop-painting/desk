#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""اجازه‌نامهٔ دسترسی — «نمی‌فروشم؛ دسترسی می‌دهم».

چرا این پرونده هست: کاربر این برنامه یک برنامه‌نویس حرفه‌ای نیست و نمی‌خواهد/نمی‌تواند
محصول را بفروشد و پشتیبانی سنگین بدهد. راه‌حل، فروش نسخه نیست؛ **اجازه‌نامهٔ دسترسی** است:
نرم‌افزار نزد تهیه‌کننده می‌مانَد و شرکت اجازهٔ استفادهٔ نام‌دار و زمان‌دار می‌گیرد، همراه با
پشتیبانی. همین پرونده آن اجازه‌نامه را می‌سازد و در رابط برنامه نشان می‌دهد.

نمونه:
    python license.py --status                                   # وضعیت فعلی
    python license.py --grant "شرکت نمونه" --months 12 --contact "آقای ..." --save
    python license.py --check                                    # فقط بررسی اعتبار
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

VERSION = "0.1.0"
BASE = Path(__file__).resolve().parent
# پوشهٔ تنظیمات را می‌توان با متغیر محیطی جدا کرد (برای چند مشتری روی یک رایانه)
CONFIG = Path(os.environ.get("IRAN_DESK_CONFIG_DIR") or (BASE / "config"))
LICENSE_FILE = CONFIG / "license.json"
CREDIT = ("دولوپر: مهندس مسعود مجربیان · تهیه‌کننده: Masoud Mojarabian · https://www.instagram.com/Mojarabian.Art/ · "
          "tel:+989126630554 · https://t.me/Mojarabian")
TRIAL_DAYS = 14
SALT = "iran-desk-station-access-v1"     # فقط برای یکدست‌کردن امضا؛ کلید رمزنگاری نیست


def _now() -> date:
    return datetime.now(timezone.utc).date()


def _sign(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(f"{SALT}|{body}".encode("utf-8")).hexdigest()[:16]


def make_license(client: str, *, months: int = 12, contact: str = "", modules: str = "همه",
                 note: str = "", start: date | None = None) -> dict:
    start = start or _now()
    end = start + timedelta(days=30 * max(1, int(months)))
    lic = {
        "client": client.strip() or "بدون نام",
        "contact": contact.strip(),
        "modules": modules,
        "note": note.strip(),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "months": int(months),
        "kind": "اجازه‌نامهٔ دسترسی نام‌دار (نه فروش نسخه)",
        "issued": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "owner": CREDIT,
    }
    lic["signature"] = _sign({k: v for k, v in lic.items() if k != "signature"})
    return lic


def make_trial(client: str = "آزمون ارزیابی", *, days: int = TRIAL_DAYS) -> dict:
    """اجازه‌نامهٔ آزمون روزشمار (پیش‌فرض ۱۴ روز) برای ارزیابی شرکت."""
    start = _now()
    lic = {
        "client": client.strip() or "آزمون ارزیابی", "contact": "", "modules": "همه",
        "note": f"آزمون {int(days)} روزهٔ ارزیابی (بدون تعهد)",
        "start": start.isoformat(), "end": (start + timedelta(days=int(days))).isoformat(),
        "months": 0, "days": int(days),
        "kind": "اجازه‌نامهٔ آزمون (نه فروش نسخه)",
        "issued": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "owner": CREDIT,
    }
    lic["signature"] = _sign({k: v for k, v in lic.items() if k != "signature"})
    return lic


def read_license(path: Path | str | None = None) -> dict | None:
    p = Path(path or LICENSE_FILE)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_license(lic: dict, path: Path | str | None = None) -> Path:
    p = Path(path or LICENSE_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(lic, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def verify(lic: dict | None = None) -> dict:
    """اعتبار امضا و تاریخ را بررسی می‌کند. بدون اجازه‌نامه، برنامه در حالت «آزمون» کار می‌کند."""
    lic = lic if lic is not None else read_license()
    if not lic:
        return {"state": "بدون اجازه‌نامه", "ok": True, "client": "—", "days_left": None,
                "detail": ("اجازه‌نامه‌ای ثبت نشده؛ برنامه در حالت آزاد و بدون نامِ مشتری کار می‌کند. "
                           "برای شرکت، اجازه‌نامهٔ نام‌دار بسازید: python license.py --grant \"نام شرکت\" --save")}
    want = _sign({k: v for k, v in lic.items() if k != "signature"})
    if want != lic.get("signature"):
        return {"state": "امضا نامعتبر", "ok": False, "client": lic.get("client", "—"),
                "days_left": None,
                "detail": "فایل اجازه‌نامه دست‌کاری شده است؛ امضا نمی‌خواند."}
    try:
        end = date.fromisoformat(str(lic.get("end")))
    except ValueError:
        return {"state": "تاریخ نامعتبر", "ok": False, "client": lic.get("client", "—"),
                "days_left": None, "detail": "تاریخ پایان اجازه‌نامه خوانده نشد."}
    left = (end - _now()).days
    if left < 0:
        return {"state": "منقضی", "ok": False, "client": lic.get("client", "—"), "days_left": left,
                "detail": f"اجازه‌نامه در {lic.get('end')} تمام شده ({abs(left)} روز پیش). "
                          "برای ادامهٔ استفاده، اجازه‌نامهٔ تازه صادر کنید."}
    return {"state": "معتبر", "ok": True, "client": lic.get("client", "—"), "days_left": left,
            "modules": lic.get("modules", "—"),
            "detail": f"اجازه‌نامهٔ «{lic.get('client')}» تا {lic.get('end')} معتبر است "
                      f"({left} روز باقی مانده)."}


def ladder() -> list[dict]:
    """سه پلهٔ پیشنهادی ارائه: چه چیزی داده می‌شود و در برابر چه چیزی."""
    return [
        {"step": "۱. راه‌اندازی و آموزش",
         "what": "نصب روی رایانهٔ خودشان، تنظیم اتصال، آموزش گام‌به‌گام روی دادهٔ خودشان",
         "basis": "یک‌باره (بر پایهٔ روز کار)",
         "why": "پیش از این پله، هیچ تعهد ماهانه‌ای گرفته نمی‌شود."},
        {"step": "۲. اجازه‌نامهٔ دسترسی + پشتیبانی",
         "what": "استفادهٔ نام‌دار و زمان‌دار، رفع اشکال، به‌روزرسانی عددها و قواعد بازار",
         "basis": "ماهانه/سالانه (درآمد تکرارشونده)",
         "why": "همین پله است که درآمد پایدار می‌سازد و پشتیبانی را هم پوشش می‌دهد."},
        {"step": "۳. گزارش ماهانه و سفارشی‌سازی",
         "what": "گزارش ماهانه برای مدیر، افزودن دروازه‌ها یا راهبردهای موردنظرشان",
         "basis": "ماهانه یا پروژه‌ای",
         "why": "رشد درآمد بدون فروش نسخه؛ چون نرم‌افزار نزد شما می‌مانَد."},
    ]


# ------------------------------------------------------------------ سند چاپی

DATA = BASE / "data"
DOC_MD = DATA / "license-doc.md"
DOC_HTML = DATA / "license-doc.html"


def build_document(lic: dict | None = None, *, path: Path | str | None = None,
                   html_path: Path | str | None = None) -> tuple[Path, Path]:
    """سند چاپی اجازه‌نامهٔ دسترسی — برای جلسه و برای بستهٔ شاهد شرکت.

    خروجی: (مسیر HTML، مسیر متن). اگر اجازه‌نامه‌ای صادر نشده باشد، سند «آزمون» ساخته می‌شود
    و همان را هم صریح می‌نویسد؛ سندِ خالی و مبهم نمی‌سازیم.
    """
    import reportkit as rk
    lic = lic if lic is not None else read_license()
    state = verify(lic)
    mp = Path(path) if path else DOC_MD
    hp = Path(html_path) if html_path else DOC_HTML
    mp.parent.mkdir(parents=True, exist_ok=True)
    hp.parent.mkdir(parents=True, exist_ok=True)

    if lic:
        head = [f"**کارفرما/مشتری:** {lic.get('client', '—')}",
                f"**نوع:** {lic.get('kind', '—')} · **بخش‌ها:** {lic.get('modules', '—')}",
                f"**شروع:** {lic.get('start', '—')} · **پایان:** {lic.get('end', '—')} "
                f"({lic.get('months', '—')} ماه)",
                f"**امضا (چکسام):** `{lic.get('signature', '—')}`",
                f"**وضعیت بازبینی:** {state.get('state', '—')} — {state.get('detail', '')}"]
    else:
        head = ["**هنوز اجازه‌نامه‌ای صادر نشده است.**",
                "این برنامه در حالت آزاد کار می‌کند. برای جلسه، از پنل مدیریت "
                "(بخش «مجوز دسترسی») یا با این فرمان بسازید:",
                "",
                "```bash",
                'python3 license.py --grant "نام شرکت" --save',
                "```"]

    md = "\n".join([
        "# اجازه‌نامهٔ دسترسی — ایستگاه تصمیم مشتقه", "",
        f"نسخهٔ ایستگاه: {VERSION} · تاریخ سند: {_now().isoformat()}", "",
        *head, "",
        "## این اجازه‌نامه چه چیزی می‌دهد", "",
        "- استفادهٔ **نام‌دار و زمان‌دار** از ایستگاه روی رایانهٔ خود کارفرما (فروش نسخه نیست).",
        "- پشتیبانی و رفع اشکال در دورهٔ اعتبار، و به‌روزرسانی عددهای بازار (کارمزد، نرخ سد، "
        "حد نگهداری) در همان دوره.",
        "- سندِ روش کار و بستهٔ شاهد، تا هر عددی را خودشان بازتولید کنند.", "",
        "## این اجازه‌نامه چه چیزی نمی‌دهد", "",
        "- **هیچ سود تضمینی؛** هیچ وعدهٔ بازدهی. خروجی برنامه «عدد و دلیل» است.",
        "- **هیچ سفارش خودکاری:** ایستگاه به کارگزاری سفارش نمی‌فرستد (معاملات الگوریتمی خودکار "
        "در ایران مجاز نیست) و تصمیم نهایی با کاربر است.",
        "- هیچ حق انحصاری روی روش‌های عمومی بازار و هیچ تعهد حجم معامله.", "",
        "## چطور بازبینی کنند (یک فرمان)", "",
        "```bash", "cd MATERIALS/money/gui && python3 license.py --check", "```", "",
        "امضا یک **چکسام sha256** است (کلید خصوصی ندارد): کارش این است که دست‌کاری سهوی یا سادهٔ "
        "پرونده را لو بدهد، نه اینکه در برابر جاعل حرفه‌ای امنیت بدهد. همین را در جلسه بگویید.", "",
        "---", "",
        "امضای ارائه‌دهنده: ____________________     امضای کارفرما/مشتری: ____________________", "",
        CREDIT, "",
    ])
    mp.write_text(md, encoding="utf-8")

    rows = "".join(f'<tr><td>{rk.esc(k)}</td><td><b>{rk.esc(v)}</b></td></tr>'
                   for k, v in (("نام مشتری", lic.get("client", "—")),
                                ("نوع", lic.get("kind", "—")),
                                ("بخش‌ها", lic.get("modules", "—")),
                                ("شروع", lic.get("start", "—")),
                                ("پایان", lic.get("end", "—")),
                                ("امضا (چکسام)", lic.get("signature", "—")),
                                ("وضعیت", f"{state.get('state', '—')} — {state.get('detail', '')}"))
                   ) if lic else '<tr><td colspan="2" class="hint">اجازه‌نامه‌ای صادر نشده است.</td></tr>'
    body = "".join([
        '<div class="honest"><b>این سند «فروش نسخه» نیست؛ اجازه‌نامهٔ دسترسی نام‌دار و زمان‌دار '
        'است.</b> هیچ سود تضمینی و هیچ سفارش خودکاری در آن نیست.</div>',
        f'<p class="sub">نسخهٔ ایستگاه: {VERSION} · تاریخ سند: {_now().isoformat()}</p>',
        '<h2>۱. مشخصات اجازه‌نامه</h2>',
        f'<table><tbody>{rows}</tbody></table>',
        '<h2>۲. تعهدهای دو طرف</h2>',
        '<ul><li><b>ارائه‌دهنده:</b> نصب و آموزش، پشتیبانی و رفع اشکال در دورهٔ اعتبار، '
        'به‌روزرسانی عددهای بازار، و تحویل بستهٔ شاهد.</li>'
        '<li><b>کارفرما:</b> استفادهٔ درون‌سازمانی، تصمیم و سفارش‌گذاری با کاربر خودش، و نگه‌داشتن '
        'فایل‌های شاهد.</li></ul>',
        '<h2>۳. بازبینی مستقل</h2>',
        '<p class="note">هر کسی می‌تواند با <code>python3 license.py --check</code> همین امضا و '
        'تاریخ را بازتولید کند. امضا چکسام sha256 است؛ دست‌کاری ساده را لو می‌دهد، نه جعل حرفه‌ای.</p>',
        '<p class="sub">امضای ارائه‌دهنده: ____________________ &nbsp;&nbsp; '
        'امضای کارفرما/مشتری: ____________________</p>',
        f'<p class="sub">{rk.DEVELOPER_HTML if hasattr(rk, "DEVELOPER_HTML") else rk.esc(CREDIT)}</p>',
    ])
    hp.write_text(rk.page("اجازه‌نامهٔ دسترسی — ایستگاه تصمیم مشتقه", body,
                          subtitle=f"{lic.get('client', 'بدون مشتری') if lic else 'آزمون'} · "
                                   f"نسخهٔ {VERSION}"), encoding="utf-8")
    return hp, mp


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="اجازه‌نامهٔ دسترسی (نه فروش نسخه)")
    ap.add_argument("--status", action="store_true", help="وضعیت اجازه‌نامهٔ فعلی")
    ap.add_argument("--check", action="store_true", help="بررسی اعتبار")
    ap.add_argument("--document", action="store_true", help="ساخت سند چاپی اجازه‌نامه")
    ap.add_argument("--grant", metavar="نام مشتری", help="صدور اجازه‌نامهٔ نام‌دار")
    ap.add_argument("--months", type=int, default=12, help="مدت (ماه)")
    ap.add_argument("--contact", default="", help="نام و راه تماس مسئول شرکت")
    ap.add_argument("--note", default="", help="یادداشت قرارداد (شمارهٔ پیش‌فاکتور و مانند آن)")
    ap.add_argument("--trial", action="store_true", help="صدور اجازه‌نامهٔ آزمون دو هفته‌ای")
    ap.add_argument("--save", action="store_true", help="ذخیره در config/license.json")
    ap.add_argument("--json", action="store_true", help="خروجی ماشین‌خوان")
    ap.add_argument("--ladder", action="store_true", help="نمایش سه پلهٔ پیشنهادی ارائه")
    ap.add_argument("--version", action="version", version=f"license {VERSION}")
    args = ap.parse_args(argv)

    if args.ladder:
        for row in ladder():
            print(f"{row['step']}\n  چه می‌دهید: {row['what']}\n  در برابر: {row['basis']}\n  چرا: {row['why']}\n")
        return 0

    if args.grant or args.trial:
        lic = (make_trial(args.grant or "آزمون ارزیابی") if args.trial else
               make_license(args.grant, months=args.months, contact=args.contact, note=args.note))
        if args.save:
            path = write_license(lic)
        else:
            path = LICENSE_FILE
        out = {"license": lic, "saved": str(path) if args.save else None, "status": verify(lic)}
        span = (f"{lic['days']} روز" if lic.get("days") else f"{lic['months']} ماه")
        print(json.dumps(out, ensure_ascii=False, indent=1) if args.json else
              f"اجازه‌نامهٔ «{lic['client']}» صادر شد: {lic['start']} تا {lic['end']} "
              f"({span}) · امضا {lic['signature']}"
              + (f"\nذخیره شد: {path}" if args.save else "\n(ذخیره نشد؛ با --save ذخیره کنید)"))
        if args.document:
            h, m = build_document()
            print("سند چاپی:", h)
            print("نسخهٔ متنی برای ایمیل:", m)
        return 0

    if args.document:
        h, m = build_document()
        print("سند چاپی:", h)
        print("نسخهٔ متنی برای ایمیل:", m)
        return 0

    st = verify()
    if args.json:
        print(json.dumps({"status": st, "license": read_license()}, ensure_ascii=False))
        return 0 if st["ok"] else 1
    print(f"وضعیت اجازه‌نامه: {st['state']} · مشتری: {st['client']}"
          + (f" · {st['days_left']} روز باقی‌مانده" if st.get("days_left") is not None else ""))
    print(st["detail"])
    return 0 if st["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
