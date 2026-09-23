"""بار۳۵ — نگهبان‌های vibefarsi search-input + tags-input + multi-select."""
import pathlib, re

WEB = pathlib.Path(__file__).resolve().parents[1] / "web"
INDEX = (WEB / "index.html").read_text(encoding="utf-8")
ADMIN = (WEB / "admin.html").read_text(encoding="utf-8")
HELP = (WEB / "help.js").read_text(encoding="utf-8")

class TestSearchCSS:
    def test_search_css(self):
        for sel in [".search-wrap", ".search-input", ".search-icon", ".search-clear", ".search-kbd"]:
            assert sel in INDEX, f"{sel} نیست"
        assert "direction:rtl" in INDEX.replace(" ","").lower() or "direction: rtl" in INDEX

    def test_admin_same(self):
        for sel in [".search-wrap", ".tags-input", ".multi-select"]:
            assert sel in ADMIN, f"{sel} در admin نیست"

class TestSearchHTML:
    def test_demo_search(self):
        assert 'id="demo-search"' in INDEX
        assert 'class="search-input"' in INDEX
        assert 'class="search-wrap"' in INDEX
        assert '🔍' in INDEX or 'search-icon' in INDEX
        assert '⌘K' in INDEX
        assert 'id="demo-search-clear"' in INDEX
        assert 'id="demo-search-hint"' in INDEX
        # signals search also
        assert 'id="signals-search"' in INDEX

    def test_tags_html(self):
        assert 'id="demo-tags"' in INDEX
        assert 'class="tags-input"' in INDEX
        assert 'id="demo-tags-input"' in INDEX
        assert 'handleTagsKey' in INDEX
        assert 'handleTagsPaste' in INDEX
        assert 'ری‌اکت' in INDEX
        assert '۲ / ۵' in INDEX
        assert '،' in INDEX  # Persian comma mention

    def test_multi_html(self):
        assert 'id="demo-multi"' in INDEX
        assert 'class="multi-select"' in INDEX
        assert 'multi-select-trigger' in INDEX
        assert 'multi-select-dropdown' in INDEX
        assert 'toggleMulti' in INDEX
        assert 'role="combobox"' in INDEX
        assert 'role="listbox"' in INDEX
        assert 'role="option"' in INDEX
        assert '+۰ مورد دیگر' in INDEX or 'مورد دیگر' in INDEX

class TestSearchJS:
    def test_helpers_exist(self):
        for fn in ["debouncedSearchSignals", "attachSearchInputs", "addTag", "removeTag", "handleTagsKey", "handleTagsPaste", "toggleMulti", "toggleMultiValue", "filterMulti"]:
            assert fn in HELP, f"{fn} در help.js نیست"

    def test_search_logic(self):
        assert "300" in HELP  # debounce
        assert "getElementById(\"demo-search-hint\")" in HELP or "demo-search-hint" in HELP
        assert "Ctrl" in HELP or "ctrlKey" in HELP
        assert "metaKey" in HELP

    def test_tags_logic(self):
        assert "5" in HELP  # max 5
        assert "duplicate" in HELP.lower() or "existing" in HELP or "indexOf" in HELP
        assert "split" in HELP
        assert "،" in HELP
        assert "clipboardData" in HELP or "paste" in HELP.lower()

    def test_multi_logic(self):
        assert "aria-expanded" in HELP
        assert "tag-chip" in HELP
        assert "+\" مورد دیگر\"" in HELP or "مورد دیگر" in HELP
        assert "outside" in HELP.lower() or "contains" in HELP

    def test_offline(self):
        for blob, name in [(INDEX, "index.html"), (HELP, "help.js")]:
            assert "https://cdn" not in blob.lower(), f"{name} CDN دارد"

class TestBehavior:
    def test_search_clear_shows(self):
        assert ".search-clear.show" in INDEX
        assert "classList.add(\"show\")" in HELP or 'classList.add("show")' in HELP

    def test_tags_chip(self):
        assert ".tag-chip" in INDEX
        assert "Backspace" in HELP

    def test_multi_more(self):
        # check that more element exists and logic updates it
        assert 'id="demo-multi-more"' in INDEX
        assert "-more" in HELP and "مورد دیگر" in HELP
