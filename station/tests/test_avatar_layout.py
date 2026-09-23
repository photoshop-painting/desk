"""بار۴۳ — avatar/aspect/resizable/theme"""
import pathlib
WEB=pathlib.Path(__file__).resolve().parents[1]/"web"
INDEX=(WEB/"index.html").read_text(encoding="utf-8")
HELP=(WEB/"help.js").read_text(encoding="utf-8")
class TestAL:
    def test_css(self):
        for s in [".avatar",".avatar-group",".aspect-box",".resizable",".theme-toggle"]:
            assert s in INDEX, s
    def test_html(self):
        assert 'id="demo-avatar"' in INDEX
        assert 'avatar-group' in INDEX
        assert 'id="demo-aspect"' in INDEX
        assert 'id="demo-resizable"' in INDEX
        assert 'id="demo-resizable-handle"' in INDEX
        assert 'data-theme' in INDEX or 'toggleTheme' in INDEX
    def test_js(self):
        for fn in ["toggleTheme","startResize","resizableKey"]:
            assert fn in HELP, fn
