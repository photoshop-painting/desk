"""بار۴۱ — popover/hover-card/context-menu/sheet/separator/spinner"""
import pathlib
WEB=pathlib.Path(__file__).resolve().parents[1]/"web"
INDEX=(WEB/"index.html").read_text(encoding="utf-8")
HELP=(WEB/"help.js").read_text(encoding="utf-8")
ADMIN=(WEB/"admin.html").read_text(encoding="utf-8")
class TestOverlay:
    def test_css(self):
        for s in [".popover-panel",".hover-card",".context-menu",".sheet",".separator",".spinner"]:
            assert s in INDEX, s
    def test_html(self):
        assert 'id="demo-popover"' in INDEX
        assert 'id="demo-ctx"' in INDEX
        assert 'oncontextmenu' in INDEX
        assert 'id="demo-sheet"' in INDEX
        assert 'class="separator"' in INDEX
        assert 'یا' in INDEX
        assert 'spinner' in INDEX
        assert '@negar' in INDEX
    def test_js(self):
        for fn in ["togglePopover","openContext","closeContext","openSheet","closeSheet"]:
            assert fn in HELP, fn
    def test_admin(self):
        assert ".popover-panel" in ADMIN
