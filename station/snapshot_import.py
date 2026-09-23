#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ورود اعداد کارگزاری از متن کپی‌شده — برای کم‌کردن خطای انسانی.

کاربر نوآموز این اعداد را از سامانهٔ کارگزاری یا سایت مرجع کپی می‌کند. به‌جای تایپ دستی، متن را
این‌جا می‌چسباند و برنامه خودش ردیف‌ها را می‌سازد: رقم‌های فارسی، جداکنندهٔ هزارگان، «تومان»،
و خط‌های کج‌وکوله را می‌فهمد و هر چیزی را که نفهمید، صادقانه به‌عنوان «مشکل» برمی‌گرداند.

قالب سادهٔ پیشنهادی (هر خط یک ردیف):
    نماد , راهبرد , عددها...
    اهرم , basis , 20000 , 22800 , 90 , 20000000 , 900 , 0.005
    فولاد , covered_call , 7000 , 7600 , 400 , 45 , 7000 , 160 , 0.018

اگر نام راهبرد را ننویسید، از روی تعداد و بزرگی عددها حدس زده می‌شود و در «هشدارها» گفته می‌شود
که جای حدس است. این ماژول هیچ‌وقت خودش ذخیره نمی‌کند؛ ذخیره فقط با تیک تأیید خودِ کاربر انجام
می‌شود تا روز «واقعی» بی‌اجازه ساخته نشود.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

VERSION = "0.2.0"
BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import datafeed as df  # noqa: E402

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

KIND_WORDS = {
    "basis": "basis", "کری": "basis", "نقدی": "basis", "cash": "basis",
    "covered_call": "covered_call", "covered": "covered_call", "پوشش": "covered_call",
    "پوشش‌داده‌شده": "covered_call", "کاورد": "covered_call",
    "tabei": "tabei", "تبعی": "tabei", "تضمین": "tabei",
    "box": "box", "باکس": "box", "جعبه": "box",
    "parity": "parity", "تساوی": "parity", "پوت‌کال": "parity",
}

# ترتیب عددها برای هر راهبرد (همان ترتیبی که موتور می‌خواند)
NUM_ORDER = {
    "basis": ("spot", "future", "days"),
    "covered_call": ("spot", "strike", "premium", "days"),
    "tabei": ("stock_price", "put_price", "strike", "days"),
    "box": ("call_low", "put_low", "call_high", "put_high", "strike_low", "strike_high", "days"),
    "parity": ("call", "put", "spot", "strike", "days"),
}
OPTIONAL_ORDER = ("margin_per_contract", "liquidity_contracts_per_day", "spread_pct")

PRICE_FIELDS = ("spot", "stock_price", "future", "strike", "strike_low", "strike_high", "premium",
                "put_price", "call", "put", "call_low", "call_high", "put_low", "put_high",
                "margin_per_contract")

HEADER_MAP = {
    "قیمت پایه": "spot", "قیمت نقدی": "spot", "قیمت سهم": "stock_price", "نقدی": "spot",
    "پایه": "spot", "سهم": "stock_price", "آتی": "future", "اعمال": "strike",
    "پرمیوم": "premium", "پوت": "put", "کال": "call", "روز": "days", "سررسید": "days",
    "وجه تضمین": "margin_per_contract", "تضمین": "margin_per_contract",
    "حجم": "liquidity_contracts_per_day", "نقدشوندگی": "liquidity_contracts_per_day",
    "اسپرد": "spread_pct",
}

_SEP = re.compile(r"\t|,|،|;|؛|\s{2,}|\|")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")     # «7,600» عدد است، نه دو ستون
_NUM = re.compile(r"^-?\d+(?:\.\d+)?$")


def norm_digits(text: str) -> str:
    """رقم‌های فارسی/عربی را به لاتین برمی‌گرداند و نویسه‌های مزاحم را پاک می‌کند."""
    out = str(text or "").translate(PERSIAN_DIGITS)
    out = out.replace("٬", ",").replace("،", ",").replace("\u200f", "").replace("\u200e", "")
    out = re.sub(r"\u200c", " ", out)          # نیم‌فاصله
    return out


def to_number(token: str) -> float | None:
    """'۲۰٬۰۰۰ ریال' یا '20,000' یا '1.5' را به عدد می‌گرداند؛ اگر عدد نبود None."""
    t = norm_digits(token).strip().strip('"').strip("'")
    if not t:
        return None
    t = re.sub(r"(ریال|تومان|درصد|٪|%)", "", t).strip()
    t = t.replace(" ", "").replace(",", "")
    if not _NUM.match(t):
        return None
    try:
        return float(t)
    except ValueError:
        return None



def _is_label(token: str) -> bool:
    """آیا این کلمه یک برچسب شناخته‌شده است (نام راهبرد یا نام ستون)؟"""
    t = norm_digits(token).strip().lower()
    if t in KIND_WORDS:
        return True
    return any(word in t for word in HEADER_MAP)


def map_headers(parts: list[str]) -> list[str | None]:
    """سرستون‌های فارسی را به نام فیلد تبدیل می‌کند (هر چه نفهمید None)."""
    out: list[str | None] = []
    for p in parts:
        t = norm_digits(p).strip()
        hit = None
        for word, field in HEADER_MAP.items():
            if word in t:
                hit = field
                break
        out.append(hit)
    return out


FAMILY = {
    "spot": "price", "stock_price": "price", "future": "future",
    "strike": "strike", "strike_low": "strike_low", "strike_high": "strike_high",
    "premium": "premium", "put_price": "premium",
    "call": "call", "call_low": "call", "call_high": "call",
    "put": "put", "put_low": "put", "put_high": "put",
    "days": "days", "margin_per_contract": "margin",
    "liquidity_contracts_per_day": "liquidity", "spread_pct": "spread",
}


def kind_from_headers(fields: list[str | None]) -> str | None:
    """راهبرد را از روی خانوادهٔ سرستون‌ها می‌فهمد (قیمت/اعمال/پرمیوم/روز و مانند آن)."""
    fams = {FAMILY[f] for f in fields if f}
    if {"call", "put", "price", "strike", "days"} <= fams:
        return "parity"
    if {"strike_low", "strike_high", "call", "put", "days"} <= fams:
        return "box"
    if {"price", "future", "days"} <= fams:
        return "basis"
    if {"price", "strike", "days"} <= fams and "put" in fams and "call" not in fams:
        return "tabei"                 # «قیمت سهم + پوت + اعمال» یعنی تضمین فروش
    if {"price", "strike", "premium", "days"} <= fams:
        return "covered_call"          # با «قیمت سهم و پرمیوم» می‌خواند؛ دوپهلو گزارش می‌شود
    if {"price", "strike", "days"} <= fams:
        return "covered_call"
    return None


def candidates(numbers: list[float]) -> list[tuple[str, int]]:
    """راهبردهایی که با این تعداد عدد می‌خوانند (عددهای اختیاری: وجه تضمین، حجم، اسپرد)."""
    n = len(numbers)
    out = []
    for kind, order in NUM_ORDER.items():
        need = len(order)
        if need <= n <= need + len(OPTIONAL_ORDER):
            # «روز» باید کوچک و مثبت باشد، وگرنه این حدس بی‌معنی است
            if 0 < numbers[need - 1] <= 1500:
                out.append((kind, need))
    return out


def pick_kind(numbers: list[float], kind_token: str = "", default_kind: str | None = None,
              header_kind: str | None = None) -> tuple[str, str, bool]:
    """(راهبرد، دلیل، دوپهلو؟) — اولویت: راهبرد نوشته‌شده، بعد سرستون، بعد حدس."""
    if kind_token:
        key = kind_token.strip().lower()
        if key in KIND_WORDS:
            return KIND_WORDS[key], "راهبرد از خودِ متن خوانده شد", False
    if default_kind:
        return default_kind, "راهبرد پیش‌فرض انتخاب‌شده", False
    if header_kind:
        return header_kind, "راهبرد از روی سرستون‌ها فهمیده شد", False
    cand = candidates(numbers)
    if not cand:
        kind, why = guess_kind(numbers)
        return kind, why, True
    cand.sort(key=lambda k: -k[1])          # بزرگ‌ترین تعداد لازم، محافظه‌کارانه‌تر است
    kind, need = cand[0]
    ambiguous = len(cand) > 1
    return kind, f"{len(numbers)} عدد ⇒ {kind} ({need} عدد لازم + {len(numbers) - need} عدد اختیاری)", ambiguous



# اسلات هر فیلد در سرستون‌ها (نام‌های هم‌معنی پذیرفته می‌شوند)
SLOT = {
    "spot": "price", "stock_price": "price", "future": "future",
    "strike": "strike", "strike_low": "strike_low", "strike_high": "strike_high",
    "premium": "premium", "put_price": "put_price",
    "call": "call", "call_low": "call_low", "call_high": "call_high",
    "put": "put", "put_low": "put_low", "put_high": "put_high",
    "days": "days", "margin_per_contract": "margin",
    "liquidity_contracts_per_day": "liquidity", "spread_pct": "spread",
}

# برای هر راهبرد: (فیلد موتور، اسلات‌های پذیرفته‌شده)
KIND_FIELD_SLOTS = {
    "basis": [("spot", {"price"}), ("future", {"future"}), ("days", {"days"})],
    "covered_call": [("spot", {"price"}), ("strike", {"strike"}),
                     ("premium", {"premium", "call", "call_low", "call_high"}), ("days", {"days"})],
    "tabei": [("stock_price", {"price"}), ("put_price", {"put_price", "put", "premium"}),
              ("strike", {"strike"}), ("days", {"days"})],
    "parity": [("call", {"call"}), ("put", {"put"}), ("spot", {"price"}),
               ("strike", {"strike"}), ("days", {"days"})],
}


def fill_by_headers(row: dict, kind: str, numbers: list[float],
                    header_fields: list[str | None]) -> tuple[int, list[str]]:
    """عددها را بر پایهٔ نام سرستون‌ها در جای درست می‌گذارد. (تعداد مصرف‌شده، هشدارها)"""
    warnings: list[str] = []
    plan = [[field, set(accept), False] for field, accept in KIND_FIELD_SLOTS[kind]]
    used = 0
    for name in header_fields:
        if used >= len(numbers):
            break
        slot = SLOT.get(name) if name else None
        value = numbers[used]
        used += 1
        if slot is None:
            warnings.append("یک سرستون ناشناخته بود؛ شمارهٔ آن نادیده گرفته شد")
            continue
        for item in plan:
            if not item[2] and slot in item[1]:
                row[item[0]] = value
                item[2] = True
                break
        else:
            warnings.append(f"عدد مربوط به «{slot}» در جای شناخته‌شده‌ای جا نگرفت")
    missing = [item[0] for item in plan if not item[2]]
    return used, warnings, missing



def row_header_fields(tokens: list[str]) -> list[str | None]:
    """اگر خودِ ردیف برچسب داشته باشد («قیمت سهم، پوت، اعمال، روز»)، همان‌ها را سرستون می‌گیریم.

    خروجی: فهرستی هم‌طول با تعداد برچسب‌ها؛ برای هر برچسب، نام فیلد (یا None).
    """
    labels = [norm_digits(t).strip() for t in tokens
              if to_number(t) is None and _is_label(t)]
    if len(labels) < 2:
        return []
    names: list[str | None] = []
    for lab in labels:
        hit = None
        for word, field in HEADER_MAP.items():
            if word in lab:
                hit = field
                break
        names.append(hit)
    return names


def numbers_by_labels(tokens: list[str]) -> list[float]:
    """عددهایی که پشت هر برچسب آمده‌اند، به همان ترتیب برچسب‌ها."""
    out: list[float] = []
    for t in tokens:
        v = to_number(t)
        if v is not None:
            out.append(v)
    return out


def _split(line: str) -> list[str]:
    guarded = _THOUSANDS.sub("\u0001", line.strip())      # جداکنندهٔ هزارگان را نگه می‌داریم
    parts = [p.strip() for p in _SEP.split(guarded) if p.strip()]
    if len(parts) <= 1:                        # تک‌فاصله‌ای، مثل «اهرم 20000 22800 90»
        parts = [p for p in re.split(r"\s+", guarded) if p]
    return [p.replace("\u0001", ",") for p in parts]


CONFLICT_FIELDS = ("spot", "stock_price", "strike", "premium", "put_price", "call", "put", "days")


def conflict_hint(symbol: str, kind: str, row: dict, numbers: list[float]) -> str:
    """اگر «سرستون‌ها» یک خوانش بدهند و «ترتیب معمولی» خوانش دیگری، صریح بگو.

    این تنها جایی است که می‌تواند خطای انسانی بسازد: جدولی که سرستونش با ترتیب
    عددهایش نمی‌خواند. به‌جای اینکه بی‌صدا یکی را انتخاب کنیم، هر دو خوانش را نشان می‌دهیم.
    """
    order = NUM_ORDER.get(kind) or []
    if not order or len(numbers) < len(order):
        return ""
    pairs = []
    for field, value in zip(order, numbers):
        if field in CONFLICT_FIELDS and field in row:
            got, alt = float(row[field]), float(value)
            if got and abs(got - alt) > max(abs(got), abs(alt)) * 0.2:
                pairs.append(f"{field}: سرستون {got:,.0f} ↔ ترتیب {alt:,.0f}")
    if not pairs:
        return ""
    return (f"{symbol}: سرستون‌ها و ترتیب معمولی با هم نمی‌خوانند؛ بازبینی کنید → "
            + " · ".join(pairs[:3]))


def sanity_problems(symbol: str, kind: str, row: dict) -> list[str]:
    """بازبینی عقلی: عددهایی که از نظر اقتصادی محال‌اند، بی‌صدا رد نمی‌شوند.

    این جدول برای تازه‌کار است: اگر ستون‌ها جابه‌جا چسبیده باشند، معمولاً همین‌جا لو می‌رود.
    """
    out: list[str] = []
    def num(k):
        v = row.get(k)
        return float(v) if isinstance(v, (int, float)) else None
    for f in PRICE_FIELDS:
        v = num(f)
        if v is not None and v <= 0:
            out.append(f"{symbol}: «{f}» صفر یا منفی است")
    if kind == "covered_call":
        sp, st, pr = num("spot"), num("strike"), num("premium")
        if sp and st and st < sp:
            out.append(f"{symbol}: قیمت اعمال ({st:,.0f}) از قیمت سهم ({sp:,.0f}) کمتر است؛ "
                       f"در پوشش‌داده‌شده اعمال باید بالاتر باشد")
        if sp and pr and pr > sp * 0.3:
            out.append(f"{symbol}: پرمیوم ({pr:,.0f}) نسبت به قیمت سهم ({sp:,.0f}) بزرگ است؛ "
                       f"احتمالاً ستون‌ها جابه‌جا چسبیده‌اند")
    if kind == "tabei":
        sp, st = num("stock_price"), num("strike")
        if sp and st and st < sp:
            out.append(f"{symbol}: در تبعی، قیمت اعمال ({st:,.0f}) باید از قیمت سهم ({sp:,.0f}) "
                       f"بیشتر باشد؛ این اعداد جابه‌جا شده‌اند")
    if kind == "basis":
        sp, fu = num("spot"), num("future")
        if sp and fu and fu < sp:
            out.append(f"{symbol}: قیمت آتی ({fu:,.0f}) از نقدی ({sp:,.0f}) کمتر است؛ مبنای منفی "
                       f"معمولاً یعنی ستون‌ها جابه‌جا شده‌اند")
    if kind == "box":
        low, high = num("strike_low"), num("strike_high")
        if low and high and high <= low:
            out.append(f"{symbol}: اعمال بالا باید از پایین بزرگ‌تر باشد")
    return out


def guess_kind(numbers: list[float], symbol_hint: str = "") -> tuple[str, str]:
    """راهبرد را از تعداد و بزرگی عددها حدس می‌زند؛ (راهبرد، دلیل) برمی‌گرداند."""
    n = len(numbers)
    if symbol_hint:
        key = symbol_hint.strip().lower()
        if key in KIND_WORDS:
            return KIND_WORDS[key], "راهبرد از خودِ متن خوانده شد"
    if n <= 3:
        return "basis", f"{n} عدد ⇒ کری (نقدی/آتی/روز)"
    if n == 5:
        return "parity", "۵ عدد ⇒ تساوی پوت‌کال"
    if n >= 7:
        return "box", f"{n} عدد ⇒ باکس اسپرد"
    # چهار عدد: یا پوشش‌داده‌شده یا تبعی
    if n == 4:
        if numbers[1] > numbers[0] and numbers[2] < numbers[0]:
            return "covered_call", "۴ عدد و ترتیب شبیه پوشش‌داده‌شده"
        if numbers[1] < numbers[0] and numbers[3] > 200:
            return "tabei", "۴ عدد و ترتیب شبیه تبعی"
        return "covered_call", "۴ عدد؛ راهبرد حدس زده شد، لطفاً در جدول بازبینی کنید"
    return "basis", f"{n} عدد؛ راهبرد حدس زده شد"


def parse_paste(text: str, *, toman_to_rial: bool = False,
                default_kind: str | None = None) -> dict:
    """متن چسبانده‌شده را به ردیف‌های اسنپ‌شات تبدیل می‌کند (بدون ذخیره‌کردن)."""
    rows: list[dict] = []
    problems: list[str] = []
    hints: list[str] = []
    header_fields: list[str | None] = []
    header_kind: str | None = None
    scaled = False
    header_seen = False

    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        parts = _split(line)
        if not parts:
            continue

        head = norm_digits(parts[0]).strip()
        if head.lower().startswith(("نماد", "symbol")):
            header_fields = map_headers(parts[1:])
            header_kind = kind_from_headers(header_fields)
            header_seen = True
            continue

        symbol = ""
        if to_number(parts[0]) is None:
            symbol = head
            parts = parts[1:]
        else:
            problems.append(f"بی‌نماد: خط «{raw.strip()[:40]}» نماد ندارد؛ رد شد")
            continue

        kind_token = ""
        if parts and to_number(parts[0]) is None and \
                norm_digits(parts[0]).strip().lower() in KIND_WORDS:
            kind_token = norm_digits(parts[0]).strip()
            parts = parts[1:]

        numbers: list[float] = []
        dropped: list[str] = []
        for p in parts:
            v = to_number(p)
            if v is None:
                if not _is_label(p):
                    dropped.append(norm_digits(p).strip())
            else:
                numbers.append(v)

        local_headers = row_header_fields(parts)          # برچسب‌های داخل خودِ ردیف
        if local_headers and not kind_token and not default_kind:
            local_kind = kind_from_headers(local_headers)
            if local_kind:
                kind_token = local_kind                     # راهبرد از برچسب‌های ردیف
        if local_headers:
            header_fields, header_kind = local_headers, kind_from_headers(local_headers)
        dropped = [d for d in dropped if not _is_label(d)]
        if dropped:
            hints.append(f"{symbol}: این‌ها عدد نبودند و نادیده گرفته شد → {'، '.join(dropped[:4])}")
        if not numbers:
            problems.append(f"{symbol}: هیچ عددی پیدا نشد")
            continue

        kind, why, ambiguous = pick_kind(numbers, kind_token, default_kind, header_kind)
        order = NUM_ORDER.get(kind)
        if not order:
            problems.append(f"{symbol}: راهبرد ناشناخته «{kind}»")
            continue

        row: dict = {"symbol": symbol, "kind": kind, "unit": "قرارداد" if kind != "tabei" else "سهم"}
        used = 0
        if header_fields and header_kind == kind and kind in KIND_FIELD_SLOTS:
            used, warns, missing = fill_by_headers(row, kind, numbers, header_fields)
            for w in warns:
                hints.append(f"{symbol}: {w}")
            if missing:
                problems.append(f"{symbol}: از روی سرستون‌ها این‌ها جا نیفتاد → {'، '.join(missing)}")
                continue
            for field in OPTIONAL_ORDER:              # عددهای باقی‌مانده = وجه تضمین/حجم/اسپرد
                if used < len(numbers) and field not in row:
                    row[field] = numbers[used]
                    used += 1
        else:
            main = numbers[:len(order)]
            extras = numbers[len(order):]
            if len(main) < len(order):
                problems.append(
                    f"{symbol}: برای «{kind}» به {len(order)} عدد نیاز است ولی {len(main)} عدد داده شد. "
                    f"ترتیب لازم: {' , '.join(order)}")
                continue
            for field, value in zip(order, main):
                row[field] = value
            for field, value in zip(OPTIONAL_ORDER, extras):
                row[field] = value
            used = len(order) + min(len(extras), len(OPTIONAL_ORDER))
        if len(numbers) > used:
            hints.append(f"{symbol}: {len(numbers) - used} عدد اضافه بود و نادیده گرفته شد")

        if "spread_pct" in row and row["spread_pct"] > 1:      # ۱٫۸ یعنی ۱٫۸٪
            row["spread_pct"] = round(row["spread_pct"] / 100, 6)
            hints.append(f"{symbol}: اسپرد به درصد داده شده بود؛ به کسری تبدیل شد")
        for f in ("spot", "stock_price", "future", "strike", "strike_low", "strike_high", "premium",
                  "put_price", "call", "put", "call_low", "call_high", "put_low", "put_high",
                  "days", "margin_per_contract", "liquidity_contracts_per_day"):
            if f in row:
                row[f] = int(row[f]) if float(row[f]).is_integer() else float(row[f])
        if not row.get("days") or int(row["days"]) <= 0:
            problems.append(f"{symbol}: «روز» درست خوانده نشد")
            continue
        missing_opt = [f for f in OPTIONAL_ORDER if f not in row]
        if missing_opt:
            hints.append(f"{symbol}: {'، '.join(missing_opt)} داده نشد؛ در جدول خودتان پر کنید")
        for warn in sanity_problems(symbol, kind, row):
            problems.append(warn)
        conflict = conflict_hint(symbol, kind, row, numbers)
        if conflict:
            hints.append(conflict)
        if not kind_token and not default_kind:
            note = "راهبرد حدس زده شد" + (" (دوپهلو: از فهرست جدول بازبینی کنید)" if ambiguous else "")
            hints.append(f"{symbol}: {note} ({kind})")
        hints.append(f"{symbol}: {why}")
        if toman_to_rial:
            for f in PRICE_FIELDS:
                if f in row:
                    row[f] = row[f] * 10
            scaled = True
        rows.append(row)

    if header_seen:
        named = [f for f in header_fields if f]
        hints.append("سرستون خوانده شد: " + " | ".join(named or ["(ناشناخته)"]))
    if scaled:
        hints.append("عددهای قیمتی ×۱۰ شد (تومان به ریال)")
    return {"ok": bool(rows), "rows": rows, "problems": problems, "hints": hints,
            "count": len(rows), "version": VERSION}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ورود اعداد از متن کپی‌شده")
    ap.add_argument("--text", help="متن چندخطی (اگر ندهید، از ورودی استاندارد می‌خواند)")
    ap.add_argument("--file", help="مسیر پروندهٔ متنی")
    ap.add_argument("--toman", action="store_true", help="عددها به تومان است (×۱۰ می‌شود)")
    ap.add_argument("--kind", help="راهبرد پیش‌فرض برای همهٔ خط‌ها")
    ap.add_argument("--json", action="store_true", help="خروجی ماشین‌خوان")
    ap.add_argument("--version", action="version", version=f"snapshot_import {VERSION}")
    args = ap.parse_args(argv)

    text = args.text or ""
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8-sig")
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read()
    res = parse_paste(text, toman_to_rial=args.toman, default_kind=args.kind)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0 if res["ok"] else 1
    print(f"{res['count']} ردیف خوانده شد.")
    for row in res["rows"]:
        print("  •", json.dumps(row, ensure_ascii=False))
    for p in res["problems"]:
        print("  ✗", p)
    for h in res["hints"]:
        print("  ·", h)
    checks = df.clean_rows(res["rows"])[1] if res["rows"] else []
    for c in checks:
        print("  !", c)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
