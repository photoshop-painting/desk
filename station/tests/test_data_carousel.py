"""بار۴۰ — data-table/carousel"""
import pathlib
WEB=pathlib.Path(__file__).resolve().parents[1]/"web"
INDEX=(WEB/"index.html").read_text(encoding="utf-8")
HELP=(WEB/"help.js").read_text(encoding="utf-8")
ADMIN=(WEB/"admin.html").read_text(encoding="utf-8")
class TestDT:
    def test_css(self):
        for s in [".data-table-wrap",".carousel",".carousel-track"]:
            assert s in INDEX, s
    def test_html(self):
        assert 'id="demo-dt"' in INDEX
        assert 'id="demo-dt-filter"' in INDEX
        assert 'data-sort="amount"' in INDEX
        assert '۵۹۰٬۰۰۰ تومان' in INDEX
        assert 'id="demo-dt-empty"' in INDEX
        assert 'id="demo-carousel"' in INDEX
        assert 'carousel-card' in INDEX
        assert 'RTL واقعی' in INDEX
    def test_js(self):
        for fn in ["sortDT","filterDT","pageDT","reloadDT","carouselNext","carouselPrev"]:
            assert fn in HELP, fn
    def test_admin(self):
        assert ".data-table-wrap" in ADMIN
