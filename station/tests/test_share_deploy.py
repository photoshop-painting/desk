"""آزمون بستهٔ اشتراک‌گذاری (`share/`) و 
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
from security_scan import find_secret_literals, looks_like_real_secret  # noqa: E402
بستهٔ بردن روی سایت (`deploy/`).

این دو پوشه، «آدرس دادن به کارفرما» و «نشانی ثابت» را برای کاربر تازه‌کار ساده می‌کنند؛ پس
آزمون‌ها دو چیز را می‌سنجند: (۱) اسکریپت‌ها همان کاری را می‌کنند که در راهنما نوشته شده و نحوشان
درست است؛ (۲) هیچ رمزی و هیچ پروندهٔ رازی داخل این دو پوشه نرفته باشد.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent            # .../money/gui
TOOLING_NEEDED = ("deploy/security_scan.py", "share")


# ── نگهبان بستهٔ تحویلی ─────────────────────────────────────────────────────
# این آزمون به ابزارهای «ساخت بسته» در پوشهٔ deploy نیاز دارد. آن ابزارها عمداً داخل بستهٔ
# تحویلی شرکت نیستند؛ پس اگر نبودند، باید تمیز «رد» شود نه اینکه هنگام بارگذاری بترکد
# (وگرنه «گزارش عیب‌یابی» در خودِ بسته، آزمون‌ها را سرخ نشان می‌دهد).
def _tooling_ready() -> tuple[bool, str]:
    for rel in TOOLING_NEEDED:
        if not (BASE / rel).exists():
            return False, f"ابزار ساخت در این بسته نیست: {rel}"
    return True, ""


TOOLING_OK, WHY_NO_TOOLING = _tooling_ready()

sys.path.insert(0, str(BASE / "deploy"))
try:
    from security_scan import find_secret_literals, looks_like_real_secret
except Exception as _e:                                     # noqa: BLE001
    find_secret_literals = None
    looks_like_real_secret = None
    _IMPORT_ERROR = f"{type(_e).__name__}: {_e}" 

SHARE = BASE / "share"
DEPLOY = BASE / "deploy"


@unittest.skipUnless(TOOLING_OK, WHY_NO_TOOLING)
class TestShare(unittest.TestCase):
    def test_files_exist(self):
        for name in ("share-gui.sh", "share-gui.bat", "stop-gui.sh", "stop-gui.bat",
                     "README-SHARE-FA.md"):
            self.assertTrue((SHARE / name).exists(), name)

    def test_shell_syntax(self):
        for name in ("share-gui.sh", "stop-gui.sh"):
            r = subprocess.run(["bash", "-n", str(SHARE / name)], capture_output=True, text=True)
            self.assertEqual(0, r.returncode, f"{name}: {r.stderr}")

    def test_share_script_has_the_kill_switch(self):
        t = (SHARE / "share-gui.sh").read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", t)
        self.assertIn("trap cleanup EXIT INT TERM", t)
        self.assertIn("trycloudflare", t)                 # آدرس تونل از خروجی خودش خوانده می‌شود
        self.assertIn("--no-tunnel", t)
        self.assertIn("gate.py --status", t)              # وضعیت دروازه را پیش از باز کردن نشان می‌دهد
        self.assertIn("kill \"$STATION_PID\"", t)         # بستن ایستگاه هنگام خروج
        self.assertIn("--keep-station", t)

    def test_windows_scripts_are_usable(self):
        b = (SHARE / "share-gui.bat").read_text(encoding="utf-8")
        s = (SHARE / "stop-gui.bat").read_text(encoding="utf-8")
        self.assertIn("chcp 65001", b)
        self.assertIn("web_server.py", b)
        self.assertIn("cloudflared", b)
        self.assertIn("stop-gui.bat", b)
        self.assertIn("taskkill", s)
        self.assertIn("netstat", s)

    def test_readme_explains_the_limits(self):
        t = (SHARE / "README-SHARE-FA.md").read_text(encoding="utf-8")
        self.assertIn("کلید خاموشی", t)
        self.assertIn("زنده می‌ماند", t)          # محدودیت زمانی لینک، بی‌پرده گفته شده
        self.assertIn("خروجی", t)          # جدول «می‌بیند / نمی‌تواند»


@unittest.skipUnless(TOOLING_OK, WHY_NO_TOOLING)
class TestDeploy(unittest.TestCase):
    def test_files_exist(self):
        for name in ("Dockerfile", "docker-compose.yml", "Caddyfile", "station.service",
                     "backup.sh", "README-DEPLOY-FA.md"):
            self.assertTrue((DEPLOY / name).exists(), name)

    def test_backup_script_is_safe(self):
        t = (DEPLOY / "backup.sh").read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", t)
        self.assertIn("sha256sum", t)
        self.assertIn("KEEP", t)
        r = subprocess.run(["bash", "-n", str(DEPLOY / "backup.sh")], capture_output=True, text=True)
        self.assertEqual(0, r.returncode, r.stderr)

    def test_dockerfile_runs_the_gate_kept_server(self):
        t = (DEPLOY / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("EXPOSE 8765", t)
        self.assertIn('"--host", "0.0.0.0"', t)
        self.assertIn("VOLUME", t)
        self.assertIn("HEALTHCHECK", t)
        self.assertIn("/login", t)                        # سلامت با صفحهٔ ورود سنجیده می‌شود

    def test_compose_keeps_the_port_local(self):
        t = (DEPLOY / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn('"127.0.0.1:8765:8765"', t)         # بیرون فقط از پشت Caddy
        self.assertIn("restart: unless-stopped", t)
        self.assertIn("volumes:", t)

    def test_caddy_does_tls_and_proxies(self):
        t = (DEPLOY / "Caddyfile").read_text(encoding="utf-8")
        self.assertIn("reverse_proxy 127.0.0.1:8765", t)
        self.assertIn("X-Frame-Options", t)

    def test_systemd_unit_restarts_and_binds(self):
        t = (DEPLOY / "station.service").read_text(encoding="utf-8")
        self.assertIn("Restart=always", t)
        self.assertIn("--host 0.0.0.0", t)
        self.assertIn("NoNewPrivileges=true", t)

    def test_readme_keeps_the_honest_borders(self):
        t = (DEPLOY / "README-DEPLOY-FA.md").read_text(encoding="utf-8")
        self.assertIn("پشتیبان", t)
        self.assertIn("هزینه", t)
        self.assertIn("سود تضمینی", t)


    def test_one_command_files_exist(self):
        for name in ("deploy.sh", "preflight.sh", "setup-domain.sh", ".env.example"):
            self.assertTrue((DEPLOY / name).exists(), name)

    def test_one_command_scripts_syntax(self):
        for name in ("deploy.sh", "preflight.sh", "setup-domain.sh"):
            r = subprocess.run(["bash", "-n", str(DEPLOY / name)], capture_output=True, text=True)
            self.assertEqual(0, r.returncode, f"{name}: {r.stderr}")

    def test_preflight_checks_the_things_that_actually_break(self):
        t = (DEPLOY / "preflight.sh").read_text(encoding="utf-8")
        for needle in ("docker compose version", "systemctl", "پایتون", "فضای دیسک",
                       "sha256sum", "cloudflared", "exit 1"):
            self.assertIn(needle, t)

    def test_deploy_is_one_command_with_a_practice_mode(self):
        t = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
        for needle in ("set -euo pipefail", "--dry-run", "--yes", "--skip-preflight",
                       "docker compose up -d --build", "docker compose exec -T station python3 gate.py"):
            self.assertIn(needle, t)

    def test_deploy_makes_passwords_and_locks_the_file(self):
        t = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
        self.assertIn("secrets.token_hex", t)              # رمز ساخته می‌شود، ثابت نیست
        self.assertIn("CREDENTIALS-FIRST-LOGIN.txt", t)
        self.assertIn("chmod 600", t)

    def test_deploy_always_shows_the_way_back(self):
        t = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
        for needle in ("docker compose down", "systemctl stop station", "--guest-off", "پشتیبان روزانه"):
            self.assertIn(needle, t)

    def test_setup_domain_refuses_strange_input(self):
        t = (DEPLOY / "setup-domain.sh").read_text(encoding="utf-8")
        self.assertIn("*[!a-zA-Z0-9.-]*", t)                # فقط حرف و رقم و نقطه و خط تیره
        self.assertIn("exit 2", t)
        self.assertIn("Caddyfile.bak.", t)                  # پشتیبان پیش از تغییر

    def test_env_example_has_no_secret(self):
        t = (DEPLOY / ".env.example").read_text(encoding="utf-8")
        self.assertNotIn("ADMIN_PASS=", t)                 # فقط شناسه، نه رمز
        self.assertNotIn("GUEST_PASS=", t)
        self.assertIn("STATION_DOMAIN=desk.example.ir", t)
        self.assertIn("BACKUP_KEEP=30", t)

    def test_practice_mode_writes_nothing(self):
        r = subprocess.run(["bash", str(DEPLOY / "deploy.sh"), "--systemd", "--dry-run",
                            "--skip-preflight"], capture_output=True, text=True, cwd=str(DEPLOY))
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("حالت تمرین", r.stdout)
        self.assertFalse((DEPLOY / ".env").exists(), ".env ساخته شد!")
        self.assertEqual([], list(DEPLOY.glob("Caddyfile.bak.*")), "پشتیبان Caddyfile ساخته شد!")
        self.assertFalse((BASE / "config" / "CREDENTIALS-FIRST-LOGIN.txt").exists(), "پروندهٔ رمز ساخته شد!")

    def test_readme_gives_one_command_and_the_removal_path(self):
        t = (DEPLOY / "README-DEPLOY-FA.md").read_text(encoding="utf-8")
        for needle in ("یک فرمان", "deploy.sh", "preflight.sh", "setup-domain.sh", "خاموش", "حذف"):
            self.assertIn(needle, t)


@unittest.skipUnless(TOOLING_OK, WHY_NO_TOOLING)
class TestBackupAndRestore(unittest.TestCase):
    """پشتیبان و بازگردانی روی پوشهٔ موقتِ ساختِ خودِ آزمون انجام می‌شود، نه روی دادهٔ واقعی."""

    def _fixture(self, tmp: str) -> Path:
        station = Path(tmp) / "station"
        for part in ("data", "config", "export"):
            (station / part).mkdir(parents=True, exist_ok=True)
        (station / "data" / "ledger.jsonl").write_text("دفتر آزمون\n", encoding="utf-8")
        (station / "config" / "gate.json").write_text("{}", encoding="utf-8")
        (station / "export" / "offer.html").write_text("برگه\n", encoding="utf-8")
        return station

    def _run(self, script: str, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(DEPLOY / script), *args],
                              capture_output=True, text=True,
                              env={**os.environ, **(env or {})})

    def test_real_backup_then_restore_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            station = self._fixture(tmp)
            bak = Path(tmp) / "bak"
            r = self._run("backup.sh", env={"STATION_DIR": str(station), "BACKUP_DIR": str(bak)})
            self.assertEqual(0, r.returncode, r.stderr)
            self.assertIn("اثر انگشت درست است", r.stdout)        # خودش پشتیبان تازه را بررسی می‌کند
            self.assertIn("data ✓", r.stdout)
            archives = sorted(bak.glob("iran-desk-*.tar.gz"))
            self.assertEqual(1, len(archives))
            self.assertTrue(Path(f"{archives[0]}.sha256").exists())

            (station / "data" / "ledger.jsonl").write_text("دادهٔ خراب\n", encoding="utf-8")
            dest = Path(tmp) / "restored"
            r2 = self._run("restore.sh", str(archives[0]), "--into", str(dest))
            self.assertEqual(0, r2.returncode, r2.stderr)
            self.assertEqual("دفتر آزمون\n", (dest / "data" / "ledger.jsonl").read_text(encoding="utf-8"))
            self.assertEqual("برگه\n", (dest / "export" / "offer.html").read_text(encoding="utf-8"))

    def test_restore_refuses_a_corrupt_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            station = self._fixture(tmp)
            bak = Path(tmp) / "bak"
            self._run("backup.sh", env={"STATION_DIR": str(station), "BACKUP_DIR": str(bak)})
            archive = sorted(bak.glob("iran-desk-*.tar.gz"))[0]
            Path(f"{archive}.sha256").write_text("0" * 64 + f"  {archive}\n", encoding="utf-8")
            r = self._run("restore.sh", str(archive), "--into", str(Path(tmp) / "x"))
            self.assertEqual(1, r.returncode)
            self.assertIn("اثر انگشت نمی‌خواند", r.stdout)
            self.assertFalse((Path(tmp) / "x").exists(), "با اثر انگشت خراب، چیزی باز شد!")

    def test_restore_will_not_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            station = self._fixture(tmp)
            bak = Path(tmp) / "bak"
            self._run("backup.sh", env={"STATION_DIR": str(station), "BACKUP_DIR": str(bak)})
            archive = sorted(bak.glob("iran-desk-*.tar.gz"))[0]
            r = self._run("restore.sh", str(archive), "--into", str(station))
            self.assertEqual(1, r.returncode)
            self.assertIn("خالی نیست", r.stdout)
            self.assertEqual("دفتر آزمون\n", (station / "data" / "ledger.jsonl").read_text(encoding="utf-8"))

    def test_backup_has_verify_and_list(self):
        t = (DEPLOY / "backup.sh").read_text(encoding="utf-8")
        for needle in ("--verify", "--list", "sha256sum -c", "tar -tzf", "KEEP"):
            self.assertIn(needle, t)

    def test_install_backup_line_only_gives_a_ready_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = self._run("install-backup.sh", "--line-only",
                          "--station", str(Path(tmp) / "st"), "--dest", str(Path(tmp) / "bk"))
            self.assertEqual(0, r.returncode, r.stderr)
            line = r.stdout.strip()
            self.assertTrue(line.startswith("0 3 * * *"), line)
            self.assertIn("backup.sh", line)
            self.assertIn("# iran-desk-backup", line)          # نشانه برای جایگزینی، نه تکرار

    def test_install_backup_replaces_not_duplicates(self):
        t = (DEPLOY / "install-backup.sh").read_text(encoding="utf-8")
        self.assertIn("grep -vF", t)
        self.assertIn("systemctl enable --now", t)
        self.assertIn("Persistent=true", t)

    def test_install_backup_leaves_the_bundle_clean(self):
        before = sorted(p.name for p in DEPLOY.iterdir())
        with tempfile.TemporaryDirectory() as tmp:
            self._run("install-backup.sh", "--station", str(Path(tmp) / "st"), "--dest", str(Path(tmp) / "bk"))
            units = sorted(p.name for p in (Path(tmp) / "bk").glob("station-backup.*"))
            self.assertEqual(["station-backup.service", "station-backup.timer"], units)
        self.assertEqual(before, sorted(p.name for p in DEPLOY.iterdir()),
                         "نصب پشتیبان، پوشهٔ بسته را شلوغ کرد!")

    def test_deploy_wires_the_daily_backup(self):
        t = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
        for needle in ("install-backup.sh", "--no-backup", "--backup-at", "restore.sh", "--run-now"):
            self.assertIn(needle, t)

    def test_readme_documents_backup_and_restore(self):
        t = (DEPLOY / "README-DEPLOY-FA.md").read_text(encoding="utf-8")
        for needle in ("install-backup.sh", "restore.sh", "بازگردانی", "--verify", "iran-desk-pre-restore"):
            self.assertIn(needle, t)


@unittest.skipUnless(TOOLING_OK, WHY_NO_TOOLING)
class TestNoSecrets(unittest.TestCase):
    def test_no_password_or_secret_file_in_these_folders(self):
        for folder in (SHARE, DEPLOY):
            for f in folder.rglob("*"):
                if not f.is_file():
                    continue
                self.assertEqual([], find_secret_literals(f), f"{f} مقدار شبیه رمز دارد")
                text = f.read_text(encoding="utf-8", errors="ignore")
                self.assertNotIn('"hash"', text.replace(" ", ""), f"{f} شبیه پروندهٔ رمز است")
                self.assertNotEqual("gate.json", f.name)
                self.assertNotEqual("admin.json", f.name)

    def test_share_logs_are_ignored_by_git_style_names(self):
        """گزارش‌های اجرا ساخته می‌شوند، ولی هرگز چیزی از رمز در آن‌ها نیست."""
        for name in ("share-tunnel.log", "share-station.log"):
            p = SHARE / name
            if not p.exists():
                continue
            self.assertEqual([], find_secret_literals(p), f"{name} چیزی از رمز دارد")


if __name__ == "__main__":
    unittest.main(verbosity=2)
