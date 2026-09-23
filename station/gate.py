#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""دروازهٔ ورود برنامه — «مدیر» برای خودت، و کاربران مهمان (کارفرما/همکاران) (نسخهٔ ۰.۲.۰).

چرا این ماژول هست: برنامه روی رایانهٔ خودت می‌مانَد و می‌خواهی کارفرمایی در شهر دیگر از
طریق یک نشانی، همان برنامه را ببیند. دروازه دو کار می‌کند:

  · کسی که شناسه و رمز ندارد، به خودِ برنامه نمی‌رسد (نه فقط پنل مدیریت).
  · حساب «مهمان» می‌سازد که می‌تواند همه‌چیز را اجرا و تست کند، ولی نمی‌تواند مجوز صادر کند،
    رمز عوض کند، یا برنامه را خاموش کند.

سه قاعدهٔ صادقانه:

  ۱. رمز به‌صورت متن ذخیره نمی‌شود؛ همان PBKDF2-SHA256 پنل مدیریت (نمک + هش).
  ۲. **دروازهٔ خاموش = همان اعتماد محلی قبلی**: هر کسی که به این رایانه دسترسی دارد، مدیر است.
     پس اگر برنامه را روی اینترنت می‌گذاری، دروازه باید روشن باشد.
  ۳. نشست‌ها در حافظه‌اند؛ با بستن برنامه پاک می‌شوند. اگر رمز مهمان لو رفت، `--guest-off`
     همان لحظه دسترسی را می‌بندد (و `--set-guest-pass` رمز را عوض می‌کند).

اجرا:
    python3 gate.py --sync-admin                     # رمز مدیر = همان رمز پنل مدیریت
    python3 gate.py --on --guest-id masoud --guest-pass "رمز-مهمان"
    python3 gate.py --user-add ali "رمز-علی" --user-note "کارشناس شرکت"   # کاربر تازه (خودت می‌سازی)
    python3 gate.py --users                          # فهرست کاربران
    python3 gate.py --user-off ali                   # قطع فوری دسترسی یک کاربر
    python3 gate.py --user-del ali                   # حذف کامل کاربر (نشستش هم می‌بندد)
    python3 gate.py --status
    python3 gate.py --guest-off                      # قطع فوری حساب مهمانِ قدیمی
    python3 gate.py --off                            # خاموش کردن دروازه
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import adminauth as panel  # noqa: E402  (همان طرح هشِ پنل مدیریت، یک منبع)

VERSION = "0.2.0"
# مسیر پیکربندی: با STATION_GATE_CONFIG می‌شود پیکربندی دیگری را آزمود (مثلاً در تست‌ها)
import os  # noqa: E402
CONFIG = Path(os.environ.get("STATION_GATE_CONFIG") or (BASE / "config" / "gate.json"))
COOKIE = "station_gate"
TTL_SECONDS = 8 * 60 * 60          # یک روز کاری: کارفرما وسط دمو بیرون نیفتد
ROLES = ("admin", "guest")

SESSIONS: dict[str, dict] = {}


# ------------------------------------------------------------------ خواندن و نوشتن

def load(path: Path | str | None = None) -> dict | None:
    p = Path(path or CONFIG)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def save(cfg: dict, path: Path | str | None = None) -> Path:
    p = Path(path or CONFIG)
    p.parent.mkdir(parents=True, exist_ok=True)
    cfg = dict(cfg)
    cfg["version"] = VERSION
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:
        pass
    return p


def enabled(path: Path | str | None = None) -> bool:
    cfg = load(path)
    return bool(cfg and cfg.get("enabled"))


def set_enabled(flag: bool, *, path: Path | str | None = None) -> dict:
    cfg = load(path) or {}
    cfg["enabled"] = bool(flag)
    save(cfg, path)
    return status(path)


def _account(cfg: dict, role: str) -> dict:
    row = cfg.get(role) or {}
    return row if isinstance(row, dict) else {}


def accounts(path: Path | str | None = None) -> dict:
    """وضعیت حساب‌ها — بدون هیچ هش و رمزی."""
    cfg = load(path) or {}
    out = {}
    for role in ROLES:
        row = _account(cfg, role)
        out[role] = {"id": row.get("id") or "", "set": bool(row.get("hash") and row.get("salt")),
                     "enabled": bool(row.get("enabled", role == "admin"))}
    return out


def set_account(role: str, user_id: str, password: str, *,
                path: Path | str | None = None) -> dict:
    """حساب یک نقش را می‌سازد/عوض می‌کند. رمز کوتاه رد می‌شود (همان قاعدهٔ پنل)."""
    if role not in ROLES:
        raise ValueError(f"نقش ناشناخته: {role} (باید یکی از {ROLES} باشد)")
    user_id = str(user_id or "").strip()
    if not user_id:
        raise ValueError("شناسه خالی است.")
    if len(str(password or "")) < panel.MIN_PASS_LENGTH:
        raise ValueError(f"رمز باید دست‌کم {panel.MIN_PASS_LENGTH} نویسه باشد.")
    cfg = load(path) or {}
    salt = secrets.token_hex(16)
    cfg[role] = {"id": user_id, "salt": salt, "rounds": panel.PBKDF2_ROUNDS,
                 "hash": panel._hash(password, salt), "enabled": True,
                 "made": int(time.time())}
    save(cfg, path)
    return accounts(path)[role]


def _users(cfg: dict) -> list[dict]:
    rows = cfg.get("users")
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def users(path: Path | str | None = None) -> list[dict]:
    """فهرست کاربران مهمان — بدون هیچ هش و رمزی."""
    out = []
    for row in _users(load(path) or {}):
        uid = str(row.get("id") or "")
        out.append({"id": uid, "enabled": bool(row.get("enabled", True)),
                    "note": str(row.get("note") or ""), "made": int(row.get("made") or 0),
                    "sessions": len([1 for v in SESSIONS.values() if v.get("id") == uid])})
    return out


def find_user(user_id: str, *, path: Path | str | None = None) -> dict | None:
    uid = str(user_id or "").strip()
    return next((r for r in _users(load(path) or {}) if str(r.get("id")) == uid), None)


def add_user(user_id: str, password: str, *, note: str = "",
             path: Path | str | None = None) -> dict:
    """یک کاربر مهمان تازه می‌سازد. رمز فقط هش می‌شود. شناسهٔ تکراری رد می‌شود."""
    uid = str(user_id or "").strip()
    if not uid:
        raise ValueError("شناسه خالی است.")
    if len(uid) > 32 or any(c.isspace() for c in uid):
        raise ValueError("شناسه باید بی‌فاصله و کوتاه‌تر از ۳۲ نویسه باشد.")
    if len(str(password or "")) < panel.MIN_PASS_LENGTH:
        raise ValueError(f"رمز باید دست‌کم {panel.MIN_PASS_LENGTH} نویسه باشد.")
    cfg = load(path) or {}
    admin_id = str(_account(cfg, "admin").get("id") or "")
    if uid == admin_id:
        raise ValueError("این شناسه برای حساب مدیر است؛ شناسهٔ دیگری بردارید.")
    if find_user(uid, path=path):
        raise ValueError(f"کاربر «{uid}» از قبل هست. برای عوض‌کردن رمزش، اول حذفش کن.")
    salt = secrets.token_hex(16)
    row = {"id": uid, "salt": salt, "rounds": panel.PBKDF2_ROUNDS,
           "hash": panel._hash(password, salt), "enabled": True,
           "note": str(note or ""), "made": int(time.time())}
    rows = _users(cfg)
    rows.append(row)
    cfg["users"] = rows
    save(cfg, path)
    return {"id": uid, "enabled": True, "note": row["note"], "made": row["made"], "sessions": 0}


def delete_user(user_id: str, *, path: Path | str | None = None) -> dict:
    """کاربر را کامل حذف می‌کند و نشست‌های بازش را همان لحظه می‌بندد."""
    uid = str(user_id or "").strip()
    cfg = load(path) or {}
    rows = _users(cfg)
    left = [r for r in rows if str(r.get("id")) != uid]
    if len(left) == len(rows):
        raise ValueError(f"کاربری با شناسهٔ «{uid}» پیدا نشد.")
    cfg["users"] = left
    save(cfg, path)
    closed = close_sessions(user_id=uid)
    return {"id": uid, "closed": closed, "left": len(left)}


def set_user_enabled(user_id: str, flag: bool, *,
                     path: Path | str | None = None) -> dict:
    """قطع/وصل دسترسی یک کاربر. قطع = بستن نشست‌های بازش."""
    uid = str(user_id or "").strip()
    cfg = load(path) or {}
    rows = _users(cfg)
    row = next((r for r in rows if str(r.get("id")) == uid), None)
    if row is None:
        raise ValueError(f"کاربری با شناسهٔ «{uid}» پیدا نشد.")
    row["enabled"] = bool(flag)
    cfg["users"] = rows
    save(cfg, path)
    closed = 0 if flag else close_sessions(user_id=uid)
    return {"id": uid, "enabled": bool(flag), "closed": closed}


def _user_alive(cfg: dict, user_id: str) -> bool:
    """آیا این کاربرِ مهمان همین حالا اجازهٔ ورود دارد؟ (برای نقش مهمانِ نشست‌های باز)"""
    uid = str(user_id or "")
    if uid and uid == str(_account(cfg, "guest").get("id") or ""):
        return bool(_account(cfg, "guest").get("enabled"))
    row = next((r for r in _users(cfg) if str(r.get("id")) == uid), None)
    return bool(row and row.get("enabled", True))


def set_enabled_account(role: str, flag: bool, *, path: Path | str | None = None) -> dict:
    cfg = load(path) or {}
    row = _account(cfg, role)
    if not row:
        raise ValueError(f"حساب «{role}» ساخته نشده است.")
    row["enabled"] = bool(flag)
    cfg[role] = row
    save(cfg, path)
    if not flag:                      # قطع دسترسی = بستن نشست‌های باز همان نقش
        for tok in [k for k, v in SESSIONS.items() if v.get("role") == role]:
            SESSIONS.pop(tok, None)
    return accounts(path)[role]


def sync_admin_from_panel(panel_path: Path | str | None = None, *,
                          path: Path | str | None = None) -> dict:
    """رمز مدیر دروازه را با رمز پنل مدیریت یکی می‌کند (بدون نیاز به دانستن رمز)."""
    cfgp = panel.load_config(panel_path)
    if not cfgp:
        raise ValueError("پنل مدیریت هنوز رمز ندارد؛ اول این را اجرا کنید: "
                         "python3 adminauth.py --set-id ID --set-pass PASS")
    cfg = load(path) or {}
    cfg["admin"] = {"id": cfgp.get("id"), "salt": cfgp.get("salt"),
                    "rounds": int(cfgp.get("rounds") or panel.PBKDF2_ROUNDS),
                    "hash": cfgp.get("hash"), "enabled": True}
    save(cfg, path)
    return accounts(path)["admin"]


# ------------------------------------------------------------------ ورود و نشست

def role_of(token: str | None, *, path: Path | str | None = None,
            now: float | None = None) -> str | None:
    """نقش این نشست. **دروازهٔ خاموش = مدیر** (اعتماد محلی، مثل قبل از این ماژول)."""
    if not enabled(path):
        return "admin"
    if not token:
        return None
    rec = SESSIONS.get(str(token))
    if not rec:
        return None
    t = now if now is not None else time.time()
    if rec["expires"] < t:
        SESSIONS.pop(str(token), None)
        return None
    cfg = load(path) or {}
    if rec["role"] == "admin":
        if not _account(cfg, "admin").get("enabled", True):
            SESSIONS.pop(str(token), None)      # حساب مدیر قطع شده است
            return None
    elif not _user_alive(cfg, rec.get("id")):
        SESSIONS.pop(str(token), None)          # کاربر حذف/قطع شده است
        return None
    rec["expires"] = t + TTL_SECONDS
    return rec["role"]


def _verify_row(row: dict, user_id: str, password: str, *, role: str = "guest") -> bool:
    """یک ردیف حساب (هر نقشی) را با شناسه و رمز داده‌شده می‌سنجد."""
    if not (row.get("hash") and row.get("salt")):
        return False
    if not row.get("enabled", role == "admin"):
        return False
    rounds = int(row.get("rounds") or panel.PBKDF2_ROUNDS)
    try:
        import hashlib
        dk = hashlib.pbkdf2_hmac("sha256", str(password or "").encode("utf-8"),
                                 bytes.fromhex(str(row.get("salt"))), rounds)
    except ValueError:
        return False
    return bool(panel._same(user_id, row.get("id")) and panel._same(dk.hex(), row.get("hash")))


def _verify(role: str, user_id: str, password: str, cfg: dict) -> bool:
    return _verify_row(_account(cfg, role), user_id, password, role=role)


def login(user_id: str, password: str, *, ip: str = "؟", path: Path | str | None = None,
          now: float | None = None) -> dict:
    """ورود یکی از دو نقش. خروجی همیشه کلید «ok» دارد."""
    cfg = load(path)
    if not cfg or not cfg.get("enabled"):
        return {"ok": False, "gate_off": True,
                "error": "دروازه خاموش است؛ ورود لازم نیست (همین رایانه = مدیر)."}
    if panel.rate_limited(ip, now=now):
        return {"ok": False, "rate_limited": True,
                "error": "تلاش‌های ناموفق زیاد بود؛ چند دقیقه صبر کنید."}
    if not any(_account(cfg, r).get("hash") for r in ROLES) and not _users(cfg):
        return {"ok": False, "error": "هیچ حسابی ساخته نشده. اول: python3 gate.py --sync-admin"}
    role = next((r for r in ROLES if _verify(r, user_id, password, cfg)), None)
    if role is None:                            # شاید کاربرِ مهمانِ تازه‌ای باشد
        for row in _users(cfg):
            if _verify_row(row, user_id, password):
                role = "guest"
                break
    if not role:
        left = panel.FAIL_LIMIT - panel.note_failure(ip, now=now)
        return {"ok": False, "error": f"شناسه یا رمز درست نیست. {max(left, 0)} تلاش تا قفل موقت."}
    panel.reset_failures(ip)
    t = now if now is not None else time.time()
    token = secrets.token_hex(24)
    SESSIONS[token] = {"id": str(user_id), "role": role, "expires": t + TTL_SECONDS, "made": t}
    return {"ok": True, "token": token, "role": role, "id": str(user_id),
            "expires_in_minutes": TTL_SECONDS // 60}


def who(token: str | None, *, path: Path | str | None = None) -> dict | None:
    """شناسه و نقش این نشست (برای نمایش «وارد شدهاید: …» در رابط)."""
    role = role_of(token, path=path)
    if not role:
        return None
    if not enabled(path):
        return {"id": "—", "role": role, "local": True}
    rec = SESSIONS.get(str(token)) or {}
    return {"id": rec.get("id") or "—", "role": role, "local": False}


def close_sessions(role: str | None = None, *, user_id: str | None = None) -> int:
    """همهٔ نشست‌ها (یا نشست‌های یک نقش / یک کاربر) را می‌بندد."""
    doomed = [k for k, v in SESSIONS.items()
              if (role is None or v.get("role") == role)
              and (user_id is None or str(v.get("id")) == str(user_id))]
    for k in doomed:
        SESSIONS.pop(k, None)
    return len(doomed)


def logout(token: str | None) -> bool:
    return bool(SESSIONS.pop(str(token), None))


def active_sessions() -> int:
    return len(SESSIONS)


def status(path: Path | str | None = None) -> dict:
    """وضعیت برای نمایش در رابط و پنل — بدون هیچ رمز و هشی."""
    cfg = load(path)
    acc = accounts(path)
    return {"version": VERSION, "enabled": bool(cfg and cfg.get("enabled")),
            "backend": "متغیر محیطی" if panel.env_credentials() else f"پروندهٔ {CONFIG}",
            "accounts": acc, "users": users(path), "cookie": COOKIE,
            "ttl_hours": TTL_SECONDS // 3600,
            "open_sessions": active_sessions(),
            "rule": ("دروازه خاموش است: هر کسی که به این رایانه دسترسی دارد، مدیر است."
                     if not (cfg and cfg.get("enabled")) else
                     "دروازه روشن است: بدون شناسه و رمز، برنامه باز نمی‌شود.")}


# ------------------------------------------------------------------ خط فرمان

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="دروازهٔ ورود برنامه (مدیر و مهمان/کارفرما)")
    ap.add_argument("--on", action="store_true", help="دروازه را روشن کن")
    ap.add_argument("--off", action="store_true", help="دروازه را خاموش کن")
    ap.add_argument("--sync-admin", action="store_true", help="رمز مدیر = رمز پنل مدیریت")
    ap.add_argument("--admin-id", default="", help="شناسهٔ مدیر (با --admin-pass)")
    ap.add_argument("--admin-pass", default="", help="رمز مدیر")
    ap.add_argument("--guest-id", default="", help="شناسهٔ مهمان/کارفرما (با --guest-pass)")
    ap.add_argument("--guest-pass", default="", help="رمز مهمان/کارفرما")
    ap.add_argument("--guest-on", action="store_true", help="دسترسی مهمان را روشن کن")
    ap.add_argument("--guest-off", action="store_true", help="دسترسی مهمان را همین حالا قطع کن")
    ap.add_argument("--status", action="store_true", help="وضعیت دروازه و حساب‌ها")
    ap.add_argument("--users", action="store_true", help="فهرست کاربران مهمان")
    ap.add_argument("--user-add", nargs=2, metavar=("ID", "PASS"), help="کاربر مهمان تازه بساز")
    ap.add_argument("--user-note", default="", help="یادداشت کاربر تازه (اختیاری)")
    ap.add_argument("--user-del", default="", help="کاربر را کامل حذف کن (نشستش هم بسته می‌شود)")
    ap.add_argument("--user-on", default="", help="دسترسی این کاربر را وصل کن")
    ap.add_argument("--user-off", default="", help="دسترسی این کاربر را قطع کن")
    ap.add_argument("--check", nargs=2, metavar=("ID", "PASS"), help="آزمودن یک جفت شناسه/رمز")
    ap.add_argument("--config", default="", help="مسیر پروندهٔ دروازه (پیش‌فرض: config/gate.json)")
    ap.add_argument("--version", action="version", version=f"gate {VERSION}")
    a = ap.parse_args(argv)
    cfg_path = a.config or None

    try:
        if a.sync_admin:
            acc = sync_admin_from_panel(path=cfg_path)
            print(f"رمز مدیر دروازه با پنل مدیریت یکی شد · شناسه: {acc['id']}")
        if a.admin_id and a.admin_pass:
            acc = set_account("admin", a.admin_id, a.admin_pass, path=cfg_path)
            print(f"حساب مدیر ذخیره شد · شناسه: {acc['id']} (فقط هش روی دیسک)")
        if a.guest_id and a.guest_pass:
            acc = set_account("guest", a.guest_id, a.guest_pass, path=cfg_path)
            print(f"حساب مهمان (کارفرما) ذخیره شد · شناسه: {acc['id']} (فقط هش روی دیسک)")
        if a.guest_on:
            set_enabled_account("guest", True, path=cfg_path)
            print("دسترسی مهمان روشن شد.")
        if a.guest_off:
            set_enabled_account("guest", False, path=cfg_path)
            print("دسترسی مهمان قطع شد (نشست‌های باز هم بی‌اعتبار می‌شوند).")
        if a.on:
            set_enabled(True, path=cfg_path)
            print("دروازه روشن شد.")
        if a.off:
            set_enabled(False, path=cfg_path)
            print("دروازه خاموش شد: همین رایانه = مدیر.")
        if a.user_add:
            u = add_user(a.user_add[0], a.user_add[1], note=a.user_note, path=cfg_path)
            print(f"کاربر مهمان ساخته شد · شناسه: {u['id']} (فقط هش روی دیسک)")
        if a.user_del:
            out = delete_user(a.user_del, path=cfg_path)
            print(f"کاربر «{out['id']}» حذف شد · {out['closed']} نشستش هم بسته شد · "
                  f"{out['left']} کاربر دیگر مانده.")
        if a.user_on:
            u = set_user_enabled(a.user_on, True, path=cfg_path)
            print(f"دسترسی «{u['id']}» وصل شد.")
        if a.user_off:
            u = set_user_enabled(a.user_off, False, path=cfg_path)
            print(f"دسترسی «{u['id']}» قطع شد · {u['closed']} نشست بازش بسته شد.")
        if a.users and not a.status:
            rows = users(cfg_path)
            if not rows:
                print("هیچ کاربر مهمانی ساخته نشده است.")
            for u in rows:
                print(f"  · {u['id']} — " + ("فعال" if u["enabled"] else "قطع‌شده") +
                      (f" · یادداشت: {u['note']}" if u["note"] else "") +
                      (f" · نشست باز: {u['sessions']}" if u["sessions"] else ""))
        if a.check:
            cfg = load(cfg_path) or {}
            role = next((r for r in ROLES if _verify(r, a.check[0], a.check[1], cfg)), None)
            if role is None and any(_verify_row(u, a.check[0], a.check[1]) for u in _users(cfg)):
                role = "guest"
            print(f"درست است ✅ (نقش: {role})" if role else "درست نیست ✗")
            return 0 if role else 1
    except ValueError as e:
        print(f"خطا: {e}", file=sys.stderr)
        return 2

    if a.status or not any([a.on, a.off, a.sync_admin, a.admin_pass, a.guest_pass,
                            a.guest_on, a.guest_off, a.users, a.user_add, a.user_del,
                            a.user_on, a.user_off]):
        s = status(cfg_path)
        acc = s["accounts"]
        print(f"دروازه: {'روشن' if s['enabled'] else 'خاموش'} · {s['rule']}")
        print(f"  مدیر: {'ساخته شده — ' + acc['admin']['id'] if acc['admin']['set'] else 'ساخته نشده'}")
        print(f"  مهمان (کارفرما): " +
              (f"{acc['guest']['id']} — " + ("فعال" if acc['guest']['enabled'] else "قطع‌شده")
               if acc['guest']['set'] else "ساخته نشده"))
        rows = s.get("users") or []
        if rows:
            print("  کاربران مهمان: " + " · ".join(
                f"{u['id']} (" + ("فعال" if u['enabled'] else "قطع‌شده") + ")" for u in rows))
        else:
            print("  کاربران مهمان: هیچ‌کدام (می‌توانی بسازی: gate.py --user-add ID PASS)")
        print(f"  عمر نشست: {s['ttl_hours']} ساعت · نشست‌های باز: {s['open_sessions']}")
        if not s["enabled"]:
            print("  برای دیدن برنامه توسط کارفرما: python3 gate.py --on --guest-id ... --guest-pass ...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
