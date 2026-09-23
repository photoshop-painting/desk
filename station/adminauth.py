#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""پنل مدیریت — احراز هویت محلی با شناسه و رمز (نسخهٔ ۰.۱.۰).

سه بخش برنامه (بررسی سلامت، مجوز دسترسی/عیب‌یابی، گواهی استفاده) به «پنل مدیریت» رفته‌اند و
این پوشه کلید ورود آن‌ها است:

  · رمز هرگز به‌صورت متن ذخیره نمی‌شود؛ فقط «نمک» و «هش» PBKDF2-SHA256 در `config/admin.json`.
  · اگر متغیرهای محیطی `STATION_ADMIN_ID` و `STATION_ADMIN_PASS` ست شده باشند، همان‌ها
    اولویت دارند (مناسب زمانی که نمی‌خواهید رمز روی دیسک بماند).
  · توکن ورود کوتاه‌عمر است و پنجرهٔ خطای ورود هم محدود می‌شود (پنج تلاش در پنج دقیقه).
  · پنل برای همین رایانه است؛ اگر روی شبکه بازش کردید، آن را پشت HTTPS بگذارید.

کارهایی که این پوشه نمی‌کند (صادقانه): رمز را از رهگیری شبکه در HTTP ساده حفظ نمی‌کند؛
مدیریت چند کاربر و نقش ندارد؛ لاگِ دسترسی جداگانه نمی‌سازد.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG = BASE / "config" / "admin.json"
VERSION = "0.1.0"

TOKEN_TTL_SECONDS = 60 * 60          # یک ساعت بی‌کاری
FAIL_WINDOW_SECONDS = 5 * 60
FAIL_LIMIT = 5
PBKDF2_ROUNDS = 200_000
MIN_PASS_LENGTH = 8

SESSIONS: dict[str, dict] = {}
FAILS: dict[str, list[float]] = {}


# ------------------------------------------------------------------ تنظیمات

def _hash(password: str, salt_hex: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex),
                             PBKDF2_ROUNDS)
    return dk.hex()


def _same(a, b) -> bool:
    """مقایسهٔ زمان‌ثابت که با متن فارسی هم کار می‌کند (compare_digest فقط ASCII می‌پذیرد)."""
    return hmac.compare_digest(str(a or "").encode("utf-8"), str(b or "").encode("utf-8"))


def env_credentials() -> tuple[str, str] | None:
    """اگر متغیرهای محیطی ست باشند، همان‌ها معتبرند و فایل خوانده نمی‌شود."""
    user = os.environ.get("STATION_ADMIN_ID", "").strip()
    password = os.environ.get("STATION_ADMIN_PASS", "")
    return (user, password) if user and password else None


def load_config(path: Path | str | None = None) -> dict | None:
    p = Path(path or CONFIG)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) and data.get("id") and data.get("hash") else None


def set_credentials(user_id: str, password: str, *, path: Path | str | None = None) -> Path:
    """شناسه و رمز را ذخیره می‌کند (فقط هش). رمز کوتاه رد می‌شود."""
    user_id = str(user_id or "").strip()
    if not user_id:
        raise ValueError("شناسهٔ ورود خالی است.")
    if len(str(password or "")) < MIN_PASS_LENGTH:
        raise ValueError(f"رمز باید دست‌کم {MIN_PASS_LENGTH} نویسه باشد.")
    p = Path(path or CONFIG)
    p.parent.mkdir(parents=True, exist_ok=True)
    salt = secrets.token_hex(16)
    p.write_text(json.dumps({"version": VERSION, "id": user_id, "salt": salt,
                             "rounds": PBKDF2_ROUNDS, "hash": _hash(password, salt)},
                            ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        p.chmod(0o600)          # فقط صاحب پرونده بخواند
    except OSError:
        pass
    return p


def is_configured(path: Path | str | None = None) -> bool:
    return env_credentials() is not None or load_config(path) is not None


def verify_credentials(user_id: str, password: str, *, path: Path | str | None = None) -> bool:
    """مقایسهٔ زمان‌ثابت؛ شناسهٔ اشتباه هم همان جواب را می‌دهد (بدون افشای کدام غلط بود)."""
    env = env_credentials()
    if env:
        same_id = _same(user_id, env[0])
        same_pass = _same(password, env[1])
        return bool(same_id and same_pass)
    cfg = load_config(path)
    if not cfg:
        return False
    rounds = int(cfg.get("rounds") or PBKDF2_ROUNDS)
    salt = str(cfg.get("salt") or "")
    try:
        dk = hashlib.pbkdf2_hmac("sha256", str(password or "").encode("utf-8"),
                                 bytes.fromhex(salt), rounds)
    except ValueError:
        return False
    same_id = _same(user_id, cfg.get("id"))
    same_pass = _same(dk.hex(), cfg.get("hash"))
    return bool(same_id and same_pass)


# ------------------------------------------------------------------ توکن و محدودیت

def issue_token(user_id: str, *, now: float | None = None) -> str:
    t = now if now is not None else time.time()
    token = secrets.token_hex(24)
    SESSIONS[token] = {"id": user_id, "expires": t + TOKEN_TTL_SECONDS, "made": t}
    return token


def check_token(token: str | None, *, now: float | None = None) -> bool:
    """توکن معتبر است؟ هر بررسی، عمر توکن را تازه می‌کند (بی‌کاری = انقضا)."""
    if not token:
        return False
    rec = SESSIONS.get(str(token))
    if not rec:
        return False
    t = now if now is not None else time.time()
    if rec["expires"] < t:
        SESSIONS.pop(str(token), None)
        return False
    rec["expires"] = t + TOKEN_TTL_SECONDS
    return True


def revoke_token(token: str | None) -> bool:
    return bool(SESSIONS.pop(str(token), None))


def active_tokens() -> int:
    return len(SESSIONS)


def rate_limited(ip: str, *, now: float | None = None) -> bool:
    """آیا این نشانی تازه بیش از حد خطا زده است؟"""
    t = now if now is not None else time.time()
    hits = [x for x in FAILS.get(str(ip), []) if t - x < FAIL_WINDOW_SECONDS]
    FAILS[str(ip)] = hits
    return len(hits) >= FAIL_LIMIT


def note_failure(ip: str, *, now: float | None = None) -> int:
    t = now if now is not None else time.time()
    hits = [x for x in FAILS.get(str(ip), []) if t - x < FAIL_WINDOW_SECONDS]
    hits.append(t)
    FAILS[str(ip)] = hits
    return len(hits)


def reset_failures(ip: str) -> None:
    FAILS.pop(str(ip), None)


def login(user_id: str, password: str, *, ip: str = "؟", path: Path | str | None = None,
          now: float | None = None) -> dict:
    """یک‌جا: محدودیت، بررسی، توکن. خروجی همیشه «ok» دارد تا کارساز ساده بماند."""
    if not is_configured(path):
        return {"ok": False, "error": ("هنوز شناسه و رمز پنل ساخته نشده. یک‌بار این را اجرا "
                                       "کنید: python3 adminauth.py --set-pass <رمز>")}
    if rate_limited(ip, now=now):
        return {"ok": False, "rate_limited": True,
                "error": "تلاش‌های ناموفق زیاد بود؛ چند دقیقه صبر کنید."}
    if not verify_credentials(user_id, password, path=path):
        left = FAIL_LIMIT - note_failure(ip, now=now)
        return {"ok": False, "error": f"شناسه یا رمز درست نیست. {max(left, 0)} تلاش تا قفل موقت."}
    reset_failures(ip)
    token = issue_token(str(user_id), now=now)
    return {"ok": True, "token": token, "ttl_seconds": TOKEN_TTL_SECONDS,
            "expires_in_minutes": TOKEN_TTL_SECONDS // 60}


# ------------------------------------------------------------------ خط فرمان

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="کلید ورود پنل مدیریت (شناسه و رمز)")
    ap.add_argument("--set-id", default="", help="شناسهٔ ورود")
    ap.add_argument("--set-pass", default="", help="رمز ورود (فقط هش ذخیره می‌شود)")
    ap.add_argument("--status", action="store_true", help="وضعیت پیکربندی")
    ap.add_argument("--check", nargs=2, metavar=("ID", "PASS"), help="آزمودن یک جفت شناسه/رمز")
    a = ap.parse_args(argv)
    if a.set_pass:
        path = set_credentials(a.set_id or "admin", a.set_pass)
        print(f"ذخیره شد: {path} (فقط هش؛ رمز روی دیسک نیست)")
        return 0
    if a.check:
        print("درست است ✅" if verify_credentials(a.check[0], a.check[1]) else "درست نیست ✗")
        return 0 if verify_credentials(*a.check) else 1
    if is_configured():
        cfg = load_config()
        where = "متغیر محیطی" if env_credentials() else f"پروندهٔ {CONFIG}"
        print(f"پنل مدیریت پیکربندی شده است — از {where}"
              + (f" · شناسه: {cfg['id']}" if cfg else ""))
        return 0
    print("پنل مدیریت هنوز پیکربندی نشده است.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
