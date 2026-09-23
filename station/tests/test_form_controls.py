"""بار۳۷ — نگهبان‌های vibefarsi slider/switch/rating/file-upload/password."""
import pathlib

WEB = pathlib.Path(__file__).resolve().parents[1] / "web"
INDEX = (WEB / "index.html").read_text(encoding="utf-8")
ADMIN = (WEB / "admin.html").read_text(encoding="utf-8")
HELP = (WEB / "help.js").read_text(encoding="utf-8")

class TestFormCSS:
    def test_css(self):
        for sel in [".switch", ".slider", ".slider-fill", ".slider-thumb", ".rating", ".file-drop", ".password-wrap", ".strength"]:
            assert sel in INDEX, sel
    def test_admin(self):
        for sel in [".switch", ".slider", ".rating", ".file-drop"]:
            assert sel in ADMIN, sel

class TestFormHTML:
    def test_switch(self):
        assert 'id="demo-switch"' in INDEX
        assert 'role="switch"' in INDEX
        assert 'toggleSwitch' in INDEX
    def test_slider(self):
        assert 'id="demo-slider"' in INDEX
        assert 'role="slider"' in INDEX
        assert 'aria-valuenow="6500000"' in INDEX
        assert '۶٬۵۰۰٬۰۰۰' in INDEX
        assert 'setSlider' in INDEX
    def test_rating(self):
        assert 'id="demo-rating"' in INDEX
        assert 'role="radiogroup"' in INDEX
        assert 'setRating' in INDEX
        assert 'previewRating' in INDEX
        assert '۴ از ۵' in INDEX
    def test_file(self):
        assert 'id="demo-drop"' in INDEX
        assert 'file-drop' in INDEX
        assert 'dragover' in INDEX
        assert 'handleFiles' in INDEX
        assert '۵ مگابایت' in INDEX
    def test_password(self):
        assert 'id="demo-pass"' in INDEX
        assert 'password-wrap' in INDEX
        assert 'togglePassword' in INDEX
        assert 'checkPassword' in INDEX

class TestFormJS:
    def test_helpers(self):
        for fn in ["toggleSwitch","setSlider","slideTo","slideKey","setRating","previewRating","onDragOver","onDrop","handleFiles","togglePassword","checkPassword"]:
            assert fn in HELP, fn
    def test_slider_logic(self):
        assert "insetInlineEnd" in HELP or "inset-inline-end" in HELP
        assert "fa-IR" in HELP or "toLocaleString" in HELP
    def test_rating_logic(self):
        assert "filled" in HELP
        assert "aria-checked" in HELP
    def test_file_logic(self):
        assert "5*1024*1024" in HELP or "5 مگابایت" in HELP
        assert "dragover" in HELP
    def test_password_logic(self):
        assert "checkPassword" in HELP and "togglePassword" in HELP
        assert "toFaDigits" in HELP or "۰۱۲۳۴۵۶۷۸۹" in HELP
    def test_offline(self):
        assert "https://cdn" not in INDEX.lower()
