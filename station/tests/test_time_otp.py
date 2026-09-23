"""بار۴۲ — time-picker/otp/collapsible/scroll/countdown"""
import pathlib
WEB=pathlib.Path(__file__).resolve().parents[1]/"web"
INDEX=(WEB/"index.html").read_text(encoding="utf-8")
HELP=(WEB/"help.js").read_text(encoding="utf-8")
class TestTO:
    def test_css(self):
        for s in [".time-picker",".otp-group",".collapsible",".scroll-area",".countdown"]:
            assert s in INDEX, s
    def test_html(self):
        assert 'id="demo-time"' in INDEX
        assert 'id="time-h"' in INDEX
        assert 'id="demo-otp"' in INDEX
        assert 'maxlength="1"' in INDEX
        assert 'id="demo-countdown"' in INDEX
        assert 'collapsible' in INDEX
        assert 'scroll-area' in INDEX
    def test_js(self):
        for fn in ["validateTime","stepTime","otpNext","otpBack","toggleCollapsible"]:
            assert fn in HELP, fn
