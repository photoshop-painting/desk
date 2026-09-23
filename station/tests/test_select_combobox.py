"""بار۳۸ — نگهبان‌های vibefarsi select/combobox/checkbox-group/radio-group/segmented."""
import pathlib
WEB = pathlib.Path(__file__).resolve().parents[1] / "web"
INDEX = (WEB / "index.html").read_text(encoding="utf-8")
ADMIN = (WEB / "admin.html").read_text(encoding="utf-8")
HELP = (WEB / "help.js").read_text(encoding="utf-8")

class TestSelectCSS:
    def test_css(self):
        for sel in [".select-wrap",".combobox",".combobox-list",".checkbox-group",".radio-card",".segmented"]:
            assert sel in INDEX, sel
    def test_admin(self):
        for sel in [".select-wrap",".combobox",".checkbox-group",".radio-group",".segmented"]:
            assert sel in ADMIN, sel

class TestSelectHTML:
    def test_select(self):
        assert 'id="demo-select"' in INDEX
        assert 'تهران' in INDEX
        assert 'شورون' in INDEX or '▾' in INDEX
    def test_combobox(self):
        assert 'id="demo-combo"' in INDEX
        assert 'role="combobox"' in INDEX
        assert 'filterCombo' in INDEX
        assert 'combobox-opt' in INDEX
        assert 'ری‌اکت' in INDEX
    def test_checkbox(self):
        assert 'id="demo-checks"' in INDEX
        assert 'check-all' in INDEX
        assert 'indeterminate' in HELP
        assert 'انتخاب همه' in INDEX
    def test_radio(self):
        assert 'id="demo-radios"' in INDEX
        assert 'role="radiogroup"' in INDEX
        assert 'radio-card' in INDEX
        assert 'پست پیشتاز' in INDEX
        assert '۳ تا ۵ روز' in INDEX
    def test_segmented(self):
        assert 'id="demo-seg"' in INDEX
        assert 'segmented' in INDEX
        assert 'segmented-pill' in INDEX
        assert 'روزانه' in INDEX and 'هفتگی' in INDEX and 'ماهانه' in INDEX

class TestSelectJS:
    def test_helpers(self):
        for fn in ["openCombo","closeCombo","filterCombo","pickCombo","comboKey","toggleCheckAll","updateCheckAll","pickRadio","pickSeg"]:
            assert fn in HELP, fn
    def test_combobox_logic(self):
        assert "startsWith" in HELP or "starts" in HELP
        assert "includes" in HELP.lower() or "indexOf" in HELP
        assert "mark" in HELP
    def test_checkbox_logic(self):
        assert "indeterminate" in HELP
    def test_segmented_logic(self):
        assert "segmented-pill" in HELP or "pickSeg" in HELP
        assert "aria-selected" in HELP
    def test_offline(self):
        assert "https://cdn" not in INDEX.lower()
