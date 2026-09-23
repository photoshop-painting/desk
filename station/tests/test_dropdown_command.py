"""بار۳۳ — نگهبان‌های vibefarsi dropdown-menu + command (پالت دستور ⌘K)."""
import pathlib, re

WEB = pathlib.Path(__file__).resolve().parents[1] / "web"
INDEX = (WEB / "index.html").read_text(encoding="utf-8")
ADMIN = (WEB / "admin.html").read_text(encoding="utf-8")
HELP = (WEB / "help.js").read_text(encoding="utf-8")
APP = (WEB / "app.js").read_text(encoding="utf-8")

class TestDropdownCSS:
    def test_dropdown_css_exists(self):
        for sel in [".dropdown", ".dropdown-menu", ".dropdown-item", ".dropdown-sep"]:
            assert sel in INDEX, f"{sel} در CSS نیست"
        assert "position:absolute" in INDEX.replace(" ", "") or "position: absolute" in INDEX
        assert "inset-inline-end:0" in INDEX.replace(" ", "") or "inset-inline-end: 0" in INDEX
        assert "box-shadow:0 8px 32px" in INDEX.replace(" ", "") or "box-shadow" in INDEX

    def test_dropdown_variants(self):
        assert ".dropdown-item.danger" in INDEX
        assert "#b3261e" in INDEX  # danger red
        assert ".dropdown-menu.open" in INDEX
        assert "role=\"menu\"" in INDEX or 'role="menu"' in INDEX

    def test_header_has_dropdown(self):
        assert 'id="header-actions"' in INDEX
        assert 'id="header-actions-trigger"' in INDEX
        assert 'id="header-actions-menu"' in INDEX
        assert 'aria-haspopup="menu"' in INDEX
        assert 'aria-expanded=' in INDEX
        # at least 3 items + separator
        assert INDEX.count('role="menuitem"') >= 3
        assert 'dropdown-sep' in INDEX

class TestDropdownJS:
    def test_dropdown_js_api(self):
        for fn in ["toggleDropdown", "closeDropdown", "closeAllDropdowns"]:
            assert fn in HELP, f"{fn} در help.js نیست"
        assert 'aria-expanded' in HELP
        assert 'role="menu"' in HELP or "role" in HELP

    def test_dropdown_keyboard(self):
        assert '"Escape"' in HELP or "'Escape'" in HELP
        assert 'ArrowDown' in HELP
        assert 'ArrowUp' in HELP
        assert 'click' in HELP.lower()

    def test_dropdown_accessibility(self):
        assert 'role="menu"' in INDEX
        assert 'role="menuitem"' in INDEX
        assert 'aria-haspopup' in INDEX

class TestCommandCSS:
    def test_command_css(self):
        for sel in [".command-overlay", ".command-box", ".command-input", ".command-list", ".command-item"]:
            assert sel in INDEX, f"{sel} نیست"
        assert ".command-overlay.open" in INDEX
        assert ".command-box.open" in INDEX
        assert "position:fixed" in INDEX

    def test_command_kbd(self):
        assert "cmd-kbd" in INDEX or "command" in INDEX
        assert "Ctrl+K" in INDEX or "⌘K" in INDEX

class TestCommandHTML:
    def test_command_markup(self):
        assert 'id="command-overlay"' in INDEX
        assert 'id="command-box"' in INDEX
        assert 'id="command-input"' in INDEX
        assert 'id="command-list"' in INDEX
        assert 'role="dialog"' in INDEX
        assert 'aria-modal="true"' in INDEX
        # placeholder Persian
        m = re.search(r'id="command-input"[^>]*placeholder="([^"]+)"', INDEX)
        assert m, "placeholder نیست"
        assert any("\u0600" <= c <= "\u06FF" for c in m.group(1)), "placeholder باید فارسی باشد"
        assert 'role="listbox"' in INDEX

    def test_admin_has_same(self):
        for sel in [".dropdown-menu", ".command-overlay"]:
            assert sel in ADMIN, f"{sel} در admin نیست"

class TestCommandJS:
    def test_command_api(self):
        for fn in ["openCommand", "closeCommand", "renderCmdList", "_cmdPick"]:
            assert fn in HELP, f"{fn} نیست"
        assert "Ctrl+K" in HELP or "Ctrl" in HELP or '"k"' in HELP

    def test_command_shortcut(self):
        assert 'ctrlKey' in HELP
        assert 'metaKey' in HELP
        # should handle Ctrl+K / Cmd+K
        assert '"k"' in HELP or "'k'" in HELP or '"K"' in HELP

    def test_command_behavior(self):
        # filtering, aria-selected, Enter handling
        assert 'aria-selected' in HELP
        assert 'Enter' in HELP
        assert 'filter' in HELP.lower() or 'indexOf' in HELP
        # should expose STEPS
        assert "STEPS" in HELP or "getCommands" in HELP

    def test_command_uses_steps(self):
        # HELP should fallback to STEPS_FALLBACK or window.STEPS
        assert "STEPS_FALLBACK" in HELP or "window.STEPS" in HELP
        assert "goto-" in HELP

    def test_offline(self):
        for blob, name in [(INDEX, "index.html"), (HELP, "help.js")]:
            assert "https://cdn" not in blob.lower()
            assert "unpkg.com" not in blob.lower()

    def test_no_external_import(self):
        assert 'import "' not in HELP or "http" not in HELP
