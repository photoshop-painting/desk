"""لاگِ ممیزی — کارِ هر کاربر، با جزئیات.

برای دو کار:
  ۱. مدیر بداند هر کاربر چه کارهایی کرده (چه دکمه‌ای، چه نتیجه‌ای).
  ۲. هر وقت برنامه با خطا مواجه شد، همان لحظه و با جزئیات خطا در لاگ بماند تا
     ریشهٔ باگ قابل پیگیری باشد.

قاعده‌ها:
  - نوشتن در یک پروندهٔ سطر-به-سطر (JSONL) در پوشهٔ data/audit — ساده، قابل کپی، قابل ریست.
  - هرگز مقادیر حساس (رمز، کلید) در لاگ نمی‌نشینند؛ فیلدهای حساس با «•••» جایگزین می‌شوند.
  - «پاک کردن» لاگ را خالی می‌کند؛ «ریست» اول آرشیو می‌کند و بعد خالی می‌کند.
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

_LOCK = threading.Lock()

# فیلدهایی که هرگز به‌صورت خوانا در لاگ نمی‌نشینند
_SENSITIVE = re.compile(
    r"(pass|password|رمز|key|کلید|secret|token|توکن|live-key)", re.IGNORECASE)

MAX_ERROR_LEN = 1200     # حداکثر طول متن خطا در هر ردیف
MAX_LINE = 64 * 1024     # سقف اندازهٔ هر ردیف (پیشگیری از پروندهٔ غول‌پیکر)


def _dir(data_dir: Path) -> Path:
    d = Path(data_dir) / "audit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file(data_dir: Path) -> Path:
    return _dir(data_dir) / "audit.jsonl"


def _archive_dir(data_dir: Path) -> Path:
    a = _dir(data_dir) / "archived"
    a.mkdir(parents=True, exist_ok=True)
    return a


def redact(obj):
    """فیلدهای حساس را در یک ساختارِ جیسون‌مانند با ••• جایگزین می‌کند (عمیق)."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if _SENSITIVE.search(str(k)) and isinstance(v, (str, int)) and v not in ("", None):
                out[str(k)] = "•••"
            else:
                out[str(k)] = redact(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact(x) for x in obj]
    if isinstance(obj, str) and len(obj) > 400:
        return obj[:400] + "…"
    return obj


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write(data_dir: Path, *, user: str = "—", role: str = "—", ip: str = "—",
          method: str, path: str, action: str = "", details=None,
          status: int = 0, ms: int = 0, level: str = "info", error: str | None = None) -> None:
    """یک ردیف به لاگ می‌نویسد. هرگز استثنا نمی‌دهد: لاگ نباید خود برنامه را بشکند."""
    try:
        entry = {
            "ts": _now(), "user": str(user)[:60], "role": str(role)[:20], "ip": str(ip)[:40],
            "method": str(method)[:10], "path": str(path)[:200], "action": str(action)[:200],
            "details": redact(details or {}), "status": int(status or 0),
            "ms": int(ms or 0), "level": level,
        }
        if error:
            entry["error"] = str(error)[:MAX_ERROR_LEN]
        line = json.dumps(entry, ensure_ascii=False)
        with _LOCK:
            f = _file(data_dir)
            if f.exists() and f.stat().st_size > 25 * 1024 * 1024:
                # سقفِ نرم: اگر پرونده بزرگ شد، خودبه‌خود آرشیو و تازه‌سازی
                reset(data_dir)
            with open(f, "a", encoding="utf-8") as fh:
                fh.write(line[:MAX_LINE] + "\n")
    except Exception:
        pass   # لاگِ شکسته نباید درخواست را خراب کند


def read(data_dir: Path, limit: int = 500, user: str | None = None,
         q: str | None = None, level: str | None = None) -> list[dict]:
    """ردیف‌های تازه‌تر را (از پایین به بالا) با فیلتر برمی‌گرداند."""
    f = _file(data_dir)
    if not f.exists():
        return []
    try:
        limit = max(1, min(int(limit), 5000))
    except (TypeError, ValueError):
        limit = 500
    with _LOCK:
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
    out = []
    for raw in reversed(lines[-limit * 4:]):        # از نو به کهنه
        if not raw.strip():
            continue
        try:
            e = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if user and e.get("user") != user:
            continue
        if level and e.get("level") != level:
            continue
        if q:
            blob = json.dumps(e, ensure_ascii=False)
            if q not in blob:
                continue
        out.append(e)
        if len(out) >= limit:
            break
    return out


def text(data_dir: Path, limit: int = 5000) -> str:
    """متنِ کپی‌شدنیِ لاگ (جدیدترین آخرِ متن)."""
    rows = read(data_dir, limit=limit)
    if not rows:
        return "(لاگ خالی است)"
    lines = []
    for e in rows:
        det = e.get("details") or {}
        det_s = " · ".join(f"{k}={v}" for k, v in list(det.items())[:8]) if isinstance(det, dict) else str(det)
        line = (f"{e.get('ts','?')} · {e.get('user','—')} ({e.get('role','—')}) · "
                f"{e.get('method','')} {e.get('path','')} · {e.get('action','')} · "
                f"وضعیت {e.get('status','?')} · {e.get('ms',0)}ms")
        if det_s:
            line += f" · {det_s}"
        if e.get("error"):
            line += f" · خطا: {e['error'][:400]}"
        lines.append(line)
    return "\n".join(lines)


def clear(data_dir: Path) -> int:
    """لاگ را خالی می‌کند؛ تعداد ردیف‌های پاک‌شده برمی‌گردد."""
    f = _file(data_dir)
    if not f.exists():
        return 0
    n = 0
    with _LOCK:
        try:
            n = sum(1 for line in f.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip())
        except OSError:
            n = 0
        f.write_text("", encoding="utf-8")
    return n


def reset(data_dir: Path) -> str:
    """لاگ جاری را آرشیو می‌کند و پروندهٔ تازه می‌سازد؛ نام آرشیو برمی‌گردد."""
    f = _file(data_dir)
    if not f.exists() or f.stat().st_size == 0:
        return ""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    with _LOCK:
        dest = _archive_dir(data_dir) / f"audit-{stamp}.jsonl"
        f.replace(dest)
    return dest.name


def stats(data_dir: Path) -> dict:
    f = _file(data_dir)
    if not f.exists():
        try:
            a = len(list(_archive_dir(data_dir).glob("audit-*.jsonl")))
        except OSError:
            a = 0
        return {"entries": 0, "errors": 0, "users": 0, "bytes": 0, "archived": a}
    n = err = 0
    users = set()
    try:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.strip():
                    continue
                n += 1
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("level") == "error":
                    err += 1
                if e.get("user") not in (None, "—"):
                    users.add(e.get("user"))
    except OSError:
        pass
    a = _archive_dir(data_dir)
    return {"entries": n, "errors": err, "users": len(users), "bytes": f.stat().st_size,
            "archived": len(list(a.glob("audit-*.jsonl")))}
