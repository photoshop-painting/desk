"""بار۳۹ — timeline/breadcrumb/pagination/tabs/stat/table"""
import pathlib
WEB = pathlib.Path(__file__).resolve().parents[1]/"web"
INDEX = (WEB/"index.html").read_text(encoding="utf-8")
ADMIN = (WEB/"admin.html").read_text(encoding="utf-8")
HELP = (WEB/"help.js").read_text(encoding="utf-8")

class TestNavCSS:
    def test_css(self):
        for s in [".timeline",".breadcrumb",".pagination",".tabs",".stat-grid"]:
            assert s in INDEX, s
    def test_admin(self):
        for s in [".timeline",".breadcrumb",".pagination",".tabs"]:
            assert s in ADMIN, s

class TestNavHTML:
    def test_breadcrumb(self):
        assert 'class="breadcrumb"' in INDEX
        assert 'خانه' in INDEX and 'فروشگاه' in INDEX
        assert '‹' in INDEX
    def test_tabs(self):
        assert 'id="demo-tabs"' in INDEX
        assert 'role="tablist"' in INDEX
        assert 'role="tab"' in INDEX
        assert 'switchTab' in INDEX
        assert 'پیش‌نمایش' in INDEX
    def test_timeline(self):
        assert 'class="timeline"' in INDEX
        assert '۱ مهر ۱۴۰۵' in INDEX
        assert 'سفارش تحویل شد' in INDEX
    def test_pagination(self):
        assert 'id="demo-pag"' in INDEX
        assert 'role="navigation"' in INDEX
        assert 'aria-current="page"' in INDEX
        assert '۱۲' in INDEX
    def test_stat_table(self):
        assert '۲۱۶٬۰۰۰٬۰۰۰' in INDEX
        assert '<table' in INDEX
        assert 'مریم احمدی' in INDEX

class TestNavJS:
    def test_helpers(self):
        for fn in ["switchTab","goPage"]:
            assert fn in HELP, fn
    def test_offline(self):
        assert "https://cdn" not in INDEX.lower()
