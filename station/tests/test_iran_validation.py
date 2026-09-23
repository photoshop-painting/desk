"""بار۳۶ — نگهبان‌های vibefarsi iran-validation (phone/iban/national-id/card/plate)."""
import pathlib, re

WEB = pathlib.Path(__file__).resolve().parents[1] / "web"
INDEX = (WEB / "index.html").read_text(encoding="utf-8")
ADMIN = (WEB / "admin.html").read_text(encoding="utf-8")
HELP = (WEB / "help.js").read_text(encoding="utf-8")

class TestIranCSS:
    def test_css_exists(self):
        for sel in [".iran-field", ".iran-prefix", ".iran-hint", ".plate-wrap"]:
            assert sel in INDEX, f"{sel} نیست"
        assert ".iran-hint.ok" in INDEX
        assert ".iran-hint.bad" in INDEX

    def test_admin_same(self):
        for sel in [".iran-field", ".plate-wrap"]:
            assert sel in ADMIN, f"{sel} در admin نیست"

class TestIranHTML:
    def test_phone(self):
        assert 'id="demo-phone"' in INDEX
        assert 'class="phone-input"' in INDEX or 'phone-input' in INDEX
        assert '+98' in INDEX
        assert 'id="demo-phone-hint"' in INDEX
        assert 'validatePhone' in INDEX

    def test_iban(self):
        assert 'id="demo-iban"' in INDEX
        assert 'IR' in INDEX
        assert 'id="demo-iban-hint"' in INDEX
        assert 'validateIban' in INDEX
        assert 'mod-97' in INDEX

    def test_nid(self):
        assert 'id="demo-nid"' in INDEX
        assert 'id="demo-nid-hint"' in INDEX
        assert 'validateNid' in INDEX
        assert '۱۲۳-۴۵۶۷۸۹-۰' in INDEX

    def test_card(self):
        assert 'id="demo-card"' in INDEX
        assert 'id="demo-card-hint"' in INDEX
        assert 'validateCard' in INDEX
        assert '۶۲۱۹' in INDEX or 'Luhn' in INDEX

    def test_plate(self):
        assert 'id="demo-plate"' in INDEX
        assert 'id="plate-2"' in INDEX
        assert 'id="plate-letter"' in INDEX
        assert 'id="plate-3"' in INDEX
        assert 'id="plate-city"' in INDEX
        assert 'I.R.IRAN' in INDEX
        assert 'validatePlate' in INDEX

class TestIranJS:
    def test_helpers(self):
        for fn in ["validatePhone", "validateIban", "validateNid", "validateCard", "validatePlate", "onlyDigits"]:
            assert fn in HELP, f"{fn} نیست"

    def test_phone_logic(self):
        assert "opMap" in HELP or "همراه اول" in HELP
        assert "iran-hint ok" in HELP or "iran-hint" in HELP
        assert "toFa" in HELP

    def test_iban_logic(self):
        assert "mod-97" in HELP or "mod97" in HELP.lower() or "% 97" in HELP
        assert "bankMap" in HELP or "بانک" in HELP

    def test_nid_logic(self):
        assert "رقم کنترل" in HELP
        assert "% 11" in HELP or "%11" in HELP

    def test_card_logic(self):
        assert "Luhn" in HELP or "luhn" in HELP.lower()
        assert "binMap" in HELP or "bin6" in HELP

    def test_plate_logic(self):
        assert "plate-2" in HELP or "validatePlate" in HELP
        # Ensure letter options like ب ج د
        assert 'value="ب"' in INDEX

    def test_offline(self):
        for blob, name in [(INDEX, "index.html"), (HELP, "help.js")]:
            assert "https://cdn" not in blob.lower()

class TestIranBehavior:
    def test_grouping(self):
        # Check that grouping logic exists for each
        assert "گروه‌بندی" in INDEX or "گروه ۴تایی" in INDEX
        assert "۳-۶-۱" in INDEX
        assert "۴ گروه ۴تایی" in INDEX

    def test_persian_digits(self):
        assert "۰۱۲۳۴۵۶۷۸۹" in HELP or "fa" in HELP
        assert "toFa" in HELP

    def test_invalid_valid_classes(self):
        assert "valid" in HELP and "invalid" in HELP
        assert "iran-hint ok" in HELP
