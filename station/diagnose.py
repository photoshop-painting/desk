#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""گزارش عیب‌یابی یک‌کلیکی — «پشتیبانی بدون دانش فنی».

کسی که این برنامه را ارائه می‌دهد لازم نیست مهندس پشتیبانی باشد. با یک دکمه، همهٔ چیزهایی که
برای تشخیص لازم است در یک پروندهٔ خوانا جمع می‌شود: نسخه‌ها، سلامت اجزا، وضعیت اجازه‌نامه،
محل پرونده‌ها، اثر انگشت موتور، وضعیت دفتر، و آخرین خطاها. همان پرونده را برای هر تکنسین یا
برای ادامهٔ کار در گفتگو بفرستید؛ دیگر لازم نیست چیزی را دستی توضیح دهید.

نمونه:
    python diagnose.py                # ساخت گزارش و ذخیره در data/diagnostic-report.html
    python diagnose.py --json         # خروجی ماشین‌خوان
    python diagnose.py --text         # متن ساده برای کپی‌کردن در پیام
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.1.0"
BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
REPORT_HTML = DATA / "diagnostic-report.html"
REPORT_TXT = DATA / "diagnostic-report.txt"
for p in (str(BASE), str((BASE.parent / "desk").resolve())):
    if p not in sys.path:
        sys.path.insert(0, p)

CREDIT = ("دولوپر: مهندس مسعود مجربیان · تهیه‌کننده: Masoud Mojarabian · https://www.instagram.com/Mojarabian.Art/ · "
          "tel:+989126630554 · https://t.me/Mojarabian")


def _safe(fn, default):
    try:
        return fn()
    except Exception as e:                      # هر خطایی خودش یک شاهد در گزارش است
        return default if default is not None else {"error": f"{type(e).__name__}: {e}"}


def collect(run_tests: bool = True) -> dict:
    """همهٔ سنجه‌های تشخیصی، بدون هیچ تغییری در داده‌های کار."""
    out: dict = {"ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                 "diagnose_version": VERSION,
                 "python": sys.version.split()[0],
                 "platform": f"{platform.system()} {platform.release()} ({platform.machine()})"}
    try:
        import station as st
        ok, items = st.health_report()
        out["station_version"] = st.VERSION
        out["health"] = {"ok": ok, "items": [{"name": n, "ok": f, "note": r} for n, f, r in items]}
    except Exception as e:
        out["health"] = {"ok": False, "items": [], "error": f"{type(e).__name__}: {e}"}

    try:
        import license as licmod            # noqa: A004  (نام ماژول خودمان)
        out["license"] = licmod.verify()
    except Exception as e:
        out["license"] = {"state": "نامعلوم", "ok": False, "detail": f"{type(e).__name__}: {e}"}

    def engine_fp() -> dict:
        import hashlib
        sys.path.insert(0, str((BASE.parent / "tools").resolve()))
        import derivatives_scout as scout     # noqa: WPS433
        src = Path(scout.__file__).read_bytes()
        return {"path": str(scout.__file__),
                "sha256_16": hashlib.sha256(src).hexdigest()[:16],
                "version": getattr(scout, "VERSION", "?")}
    out["engine"] = _safe(engine_fp, {})

    def trial_state() -> dict:
        import daily_trial as dt
        score = dt.scorecard(log_path=DATA / "trial-daily.log")
        return {"days": score.get("days"), "real_days": score.get("real_days"),
                "ready": score.get("ready"), "hash_chain_ok": score.get("chain_ok")}
    out["trial"] = _safe(trial_state, {})

    def files_state() -> dict:
        rows = []
        for name, path in (("اجازه‌نامه", BASE / "config" / "license.json"),
                           ("دفتر اتصال", BASE / "config" / "connections.json"),
                           ("کلید ذخیره‌شده", BASE / "config" / "keys.local.json"),
                           ("دفتر آزمون", DATA / "trial-daily.log"),
                           ("برگهٔ آزمون", DATA / "exam-sheet.html"),
                           ("پروندهٔ سرمایه‌گذار", DATA / "investor-dossier.html"),
                           ("آخرین بستهٔ شاهد", None)):
            if path is None:
                exports = sorted((BASE / "export").glob("bundle-*"))
                path = exports[-1] if exports else None
            rows.append({"name": name, "path": str(path) if path else "—",
                         "exists": bool(path and Path(path).exists()),
                         "bytes": Path(path).stat().st_size if path and Path(path).exists() else 0})
        return rows
    out["files"] = _safe(files_state, [])

    def connections_state() -> dict:
        import connections as conn
        store = conn.load_store()
        active = conn.active_or_none() or {}
        return {"profiles": len(store.get("profiles", [])),
                "active": active.get("name") or "—",
                "active_label": active.get("label") or "—",
                "key_where": active.get("key_where") or "—"}
    out["connections"] = _safe(connections_state, {})

    def tests_state() -> dict:
        """آزمون‌های واحد را در حالت کوتاه اجرا می‌کند (اگر کند بود، ناموفق گزارش می‌شود)."""
        p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                           cwd=str(BASE), capture_output=True, text=True, timeout=600)
        return {"ok": p.returncode == 0, "tail": pick_test_tail(p.stderr)}
    out["tests"] = (_safe(tests_state, {"ok": False, "tail": "اجرا نشد"}) if run_tests
                    else {"ok": True, "tail": "اجرا نشد (حالت سریع)"})
    out["ok"] = bool(out["health"].get("ok", False)) and bool(out.get("tests", {}).get("ok"))
    return out


def summary_line(rep: dict) -> str:
    return (f"سلامت: {'سبز' if rep.get('health', {}).get('ok') else 'سرخ'} · "
            f"آزمون‌ها: {'سبز' if rep.get('tests', {}).get('ok') else 'سرخ'} · "
            f"مجوز: {rep.get('license', {}).get('state', '—')} · "
            f"اتصال فعال: {rep.get('connections', {}).get('active', '—')} · "
            f"موتور: {rep.get('engine', {}).get('sha256_16', '—')}")


def pick_test_tail(stderr: str) -> str:
    """از خروجی آزمون‌ها، خط «نتیجه» را برمی‌دارد و هشدارهای بی‌ربط پایان کار را دور می‌ریزد."""
    lines = [ln.strip() for ln in (stderr or "").strip().splitlines() if ln.strip()]
    lines = [ln for ln in lines if "ResourceWarning" not in ln and not ln.startswith("<sys>:")]
    summary = next((ln for ln in reversed(lines) if ln.startswith(("OK", "FAILED"))), None)
    if summary is None:
        summary = lines[-1] if lines else "بی‌پاسخ"
    reds = [ln for ln in lines if ln.startswith(("FAIL:", "ERROR:"))][:4]
    return (" · ".join([summary] + reds) if reds else summary)[:400]


def build_report(rep: dict, path: Path | str = REPORT_HTML) -> tuple[Path, Path]:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    items = "\n".join(
        f"<tr><td>{i['name']}</td><td>{'✅' if i['ok'] else '❌'}</td><td class='hint'>{i['note']}</td></tr>"
        for i in rep.get("health", {}).get("items", []))
    files = "\n".join(
        f"<tr><td>{f['name']}</td><td>{'✅' if f['exists'] else '—'}</td>"
        f"<td class='hint'>{f['path']}</td><td class='num'>{f['bytes'] or ''}</td></tr>"
        for f in rep.get("files", []))
    html = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8"><title>گزارش عیب‌یابی ایستگاه</title>
<style>
 body{{font-family:Tahoma,system-ui,sans-serif;background:#f6f7fb;color:#151a26;margin:0;padding:26px}}
 .wrap{{max-width:900px;margin:auto;background:#fff;border:1px solid #e3e6ef;border-radius:14px;padding:24px}}
 h1{{font-size:19px;margin:0 0 6px}} h2{{font-size:15px;margin:18px 0 6px}}
 table{{width:100%;border-collapse:collapse}} th,td{{border:1px solid #e3e6ef;padding:6px 9px;font-size:13px;text-align:right}}
 th{{background:#f2f4fa}} .hint{{color:#5b6478;font-size:12px}} .num{{font-variant-numeric:tabular-nums}}
 pre{{background:#f8f9fd;border:1px dashed #ccd3e6;border-radius:8px;padding:10px;font-size:12px;direction:ltr;text-align:left}}
 .foot{{margin-top:16px;border-top:1px solid #e3e6ef;padding-top:8px;color:#5b6478;font-size:12px}}
</style></head><body><div class="wrap">
<h1>گزارش عیب‌یابی ایستگاه</h1>
<p class="hint">{rep.get('ts')} · نسخهٔ گزارش: {rep.get('diagnose_version')} · {rep.get('platform')} · پایتون {rep.get('python')}</p>
<p><b>{summary_line(rep)}</b></p>
<h2>سلامت اجزا</h2>
<table><thead><tr><th>جزء</th><th>وضعیت</th><th>توضیح</th></tr></thead><tbody>{items}</tbody></table>
<h2>پرونده‌های مهم</h2>
<table><thead><tr><th>پرونده</th><th>هست؟</th><th>مسیر</th><th>بایت</th></tr></thead><tbody>{files}</tbody></table>
<h2>اجازه‌نامه و اتصال</h2>
<pre>{json.dumps({'license': rep.get('license'), 'connections': rep.get('connections'), 'trial': rep.get('trial')}, ensure_ascii=False, indent=1)}</pre>
<h2>موتور ریاضی</h2>
<pre>{json.dumps(rep.get('engine'), ensure_ascii=False, indent=1)}</pre>
<div class="foot">{CREDIT}<br>این گزارش هیچ دادهٔ معاملاتی داخلی را منتقل نمی‌کند؛ فقط وضعیت فنی است.</div>
</div></body></html>
"""
    txt = (f"گزارش عیب‌یابی ایستگاه\n{rep.get('ts')} · پایتون {rep.get('python')} · {rep.get('platform')}\n"
           f"{summary_line(rep)}\n\n"
           + "\n".join(f"- {i['name']}: {'OK' if i['ok'] else 'FAIL'} · {i['note']}"
                       for i in rep.get("health", {}).get("items", []))
           + "\n\n" + json.dumps({"license": rep.get("license"), "connections": rep.get("connections"),
                                  "engine": rep.get("engine"), "trial": rep.get("trial")},
                                 ensure_ascii=False, indent=1)
           + f"\n\n{CREDIT}\n")
    t = Path(REPORT_TXT)
    t.write_text(txt, encoding="utf-8")
    p.write_text(html, encoding="utf-8")
    return p, t


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="گزارش عیب‌یابی یک‌کلیکی")
    ap.add_argument("--json", action="store_true", help="خروجی ماشین‌خوان")
    ap.add_argument("--text", action="store_true", help="متن ساده، برای کپی در پیام")
    ap.add_argument("--quick", action="store_true", help="بدون اجرای آزمون‌های واحد")
    ap.add_argument("--version", action="version", version=f"diagnose {VERSION}")
    args = ap.parse_args(argv)

    rep = collect(run_tests=not args.quick)
    h, t = build_report(rep)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 0 if rep.get("ok") else 1
    if args.text:
        print(t.read_text(encoding="utf-8"))
        return 0 if rep.get("ok") else 1
    print(summary_line(rep))
    print(f"گزارش ساخته شد:\n  {h}\n  {t}")
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
