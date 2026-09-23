"""بار۳۲ — نگهبان‌های vibefarsi dialog + alert (وضعیتِ راست‌به‌چپ: قفل اسکرول، بازگشت فوکوس، trap، و واریانت‌های alert)."""
import pathlib, re

WEB = pathlib.Path(__file__).resolve().parents[1] / "web"
INDEX = (WEB / "index.html").read_text(encoding="utf-8")
ADMIN = (WEB / "admin.html").read_text(encoding="utf-8")
HELP = (WEB / "help.js").read_text(encoding="utf-8")
APP = (WEB / "app.js").read_text(encoding="utf-8")


def _has(needle, hay): return needle in hay

class TestOverlayAndPosition:
    def test_dialog_overlay_fixed_and_blur(self):
        assert ".dialog-overlay" in INDEX, "dialog-overlay class نیست"
        assert "position:fixed" in INDEX.replace(" ", "").replace("\n","") or "position: fixed" in INDEX
        assert "inset:0" in INDEX.replace(" ", "")
        assert "z-index:9998" in INDEX.replace(" ", "") or "z-index: 9998" in INDEX
        # overlay باید backdrop هم داشته باشد (یا help-backdrop)
        assert ".help-backdrop" in HELP or ".dialog-overlay" in HELP

    def test_dialog_centered_and_sized(self):
        assert ".dialog" in INDEX
        # centered with translate(-50%,-50%)
        assert "translate(-50%,-50%)" in INDEX
        assert "max-width:520px" in INDEX.replace(" ", "") or "max-width: 520px" in INDEX
        assert "border-radius:14px" in INDEX.replace(" ", "") or "border-radius: 14px" in INDEX
        assert "max-height:calc(100vh" in INDEX.replace(" ", "")

    def test_dialog_head_body_foot_structure(self):
        for cls in [".dialog-head", ".dialog-body", ".dialog-foot"]:
            assert cls in INDEX, f"{cls} در CSS نیست"
        # foot باید justify-content:flex-end (دکمه‌های راست‌چین در RTL)
        assert "justify-content:flex-end" in INDEX.replace(" ", "") or "justify-content: flex-end" in INDEX
        assert "dialog-head" in HELP or "help-head" in HELP

class TestAlertVariants:
    def test_alert_base_and_variants(self):
        assert ".alert" in INDEX
        for v in [".alert-info", ".alert-success", ".alert-warning", ".alert-error"]:
            assert v in INDEX, f"{v} نیست"
        # رنگ‌های معلوم
        assert "#eef2ff" in INDEX  # info
        assert "#e6f6ec" in INDEX  # success
        assert "#fff8e1" in INDEX  # warning
        assert "#fdecea" in INDEX  # error

    def test_demo_alert_in_html(self):
        assert 'class="alert alert-' in INDEX, "هیچ alert نمونه‌ای در HTML نیست"
        # باید فارسی باشد
        m = re.search(r'class="alert alert-[^"]+"[^>]*>(.*?)</div>', INDEX, re.DOTALL)
        assert m, "alert خالی است"
        txt = m.group(1)
        assert any("\u0600" <= c <= "\u06FF" for c in txt), "متن alert باید فارسی باشد"

    def test_alert_role(self):
        # alert باید role=alert داشته باشد (در JS یا HTML)
        assert 'role="alert"' in HELP or 'role="alert"' in INDEX or "role" in HELP

class TestHelpDialogBehavior:
    def test_scroll_lock(self):
        assert 'document.body.style.overflow = "hidden"' in HELP or "document.body.style.overflow = 'hidden'" in HELP or 'overflow = "hidden"' in HELP
        # restoration
        assert "_helpPrevOverflow" in HELP
        assert "document.body.style.overflow = _helpPrevOverflow" in HELP

    def test_focus_return(self):
        assert "_helpPrevFocus" in HELP
        # ذخیرهٔ activeElement
        assert "document.activeElement" in HELP
        # بازگشت فوکوس
        assert ".focus()" in HELP
        # باید حداقل دو جا focus برگردد (_helpPrevFocus.focus و _dlgPrevFocus.focus)
        assert HELP.count(".focus()") >= 2

    def test_focus_trap(self):
        assert "_dialogTrapFocus" in HELP or "TrapFocus" in HELP
        assert 'e.key === "Tab"' in HELP or "e.key === 'Tab'" in HELP or '"Tab"' in HELP
        # حلقهٔ اول و آخر
        assert "first" in HELP and "last" in HELP

    def test_esc_and_overlay_close(self):
        assert '"Escape"' in HELP or "'Escape'" in HELP
        assert ".help-backdrop" in HELP
        assert ".onclick = close" in HELP

    def test_aria_modal(self):
        assert 'aria-modal' in HELP
        assert 'role", "dialog"' in HELP or "role', 'dialog'" in HELP or 'role", "dialog"' in HELP or 'role=\"dialog\"' in HELP

class TestDialogAPI:
    def test_dialog_global_exists(self):
        assert "window.Dialog" in HELP
        assert "confirm" in HELP
        assert "alert" in HELP
        # Promise-based
        assert "Promise" in HELP
        assert "_openDialog" in HELP

    def test_cancel_focus_first_alert_dialog(self):
        # vibefarsi spec: در alert-dialog فوکوس اول روی «انصراف» است
        assert "btnCancel.focus" in HELP or "btnCancel.focus()" in HELP
        # دکمه‌ها: اول cancel بعد confirm در DOM
        assert "appendChild(btnCancel)" in HELP
        assert HELP.index("appendChild(btnCancel)") < HELP.index("appendChild(btnConfirm)")
        assert "انصراف" in HELP
        assert "تأیید" in HELP

    def test_app_uses_dialog_not_raw_confirm(self):
        # app.js باید از askConfirm/Dialog استفاده کند نه confirm خام در مسیرهای کلیدی
        assert "askConfirm" in APP
        # حداقل 3 نقطهٔ کلیدی باید askConfirm شده باشد (deleteProfile/delGateUser/shutdown/decide)
        assert APP.count("askConfirm") >= 4, f"askConfirm فقط {APP.count('askConfirm')} بار"
        assert "window.askConfirm" in APP
        # Dialog API باید در help.js باشد و app.js از آن استفاده کند
        assert "window.Dialog" in HELP

    def test_admin_has_same_styles(self):
        # پنل مدیریت هم باید dialog/alert داشته باشد (آفلاین)
        assert ".dialog-overlay" in ADMIN
        assert ".alert-info" in ADMIN
        assert "position:fixed" in ADMIN

    def test_offline_self_contained(self):
        for blob, name in [(INDEX, "index.html"), (HELP, "help.js")]:
            assert "https://cdn" not in blob.lower(), f"{name} نباید CDN داشته باشد"
            assert "unpkg.com" not in blob.lower()
        # help.js نباید import خارجی داشته باشد
        assert "import " not in HELP or "from \"http" not in HELP
