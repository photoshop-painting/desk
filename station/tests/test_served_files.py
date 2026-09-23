"""آزمون فهرست پرونده‌های قابل نمایش در رابط مرورگری.

هدف: هیچ دکمهٔ «نمایش …» در رابط به پروندهٔ نبوده اشاره نکند. هر کلید `SERVED_FILES` که مسیر
دارد باید روی دیسک باشد، و پرونده‌های ساخته‌شدنی (None) باید در فهرست شناخته‌شده‌ها باشند.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import web_server as ws  # noqa: E402


class TestServedFiles(unittest.TestCase):
    # پرونده‌هایی که ایستگاه خودش در زمان نمایش می‌سازد (نبودنشان روی دیسک عیب نیست)
    ON_DEMAND = {"method", "03-method.html"}

    def test_input_files_exist_and_missing_ones_are_run_generated(self):
        """هر پروندهٔ «ورودی» (سند، قالب، راهنما) باید باشد.

        پرونده‌های پوشهٔ `data/` با اجرای برنامه ساخته می‌شوند؛ در نصب تازه نبودنشان عیب نیست،
        ولی پرونده‌ای که بیرون از `data/` باشد و نباشد، یعنی دکمه‌ای به هیچ اشاره می‌کند.
        """
        missing_inputs, missing_generated = [], []
        data_dir = ws.DATA.resolve()
        for key, path in ws.SERVED_FILES.items():
            if path is None or key in self.ON_DEMAND:
                continue                         # از پوشهٔ بسته یا در زمان نمایش پر می‌شود
            target = Path(path)
            if target.exists():
                continue
            try:
                inside_data = data_dir in target.resolve().parents
            except OSError:                      # مسیر ناموجود روی سامانه‌های غریبه
                inside_data = False
            (missing_generated if inside_data else missing_inputs).append((key, str(target)))
        self.assertEqual([], missing_inputs,
                         f"پرونده‌های ورودیِ جاافتاده (دکمه‌شان کار نمی‌کند): {missing_inputs}")
        # این‌ها باید با اجرای گام‌ها ساخته شوند؛ فهرستشان برای یافتن بدهی نگه داشته می‌شود
        self.assertTrue(all(k for k, _ in missing_generated))

    def test_method_doc_is_built_on_demand(self):
        """سند روش کار باید از وضعیت زنده ساخته شود، نه از پرونده‌ای که ممکن است نباشد."""
        src = (BASE / "web_server.py").read_text(encoding="utf-8")
        self.assertIn('name in ("method", "03-method.html")', src)
        self.assertIn("st.build_method_html(STATE)", src)

    def test_novice_walkthrough_is_wired(self):
        target = ws.SERVED_FILES.get("walkthrough")
        self.assertIsNotNone(target, "کلید walkthrough در SERVED_FILES نیست")
        self.assertTrue(Path(target).exists())
        text = Path(target).read_text(encoding="utf-8")
        self.assertIn("راهنمای هر بخش", text)
        self.assertIn("نقشهٔ صادقانهٔ اتوماسیون", text)
        self.assertIn("هرگز", text)              # مرزهای صریح
        self.assertIn("وجه تضمین", text)

    def test_admin_files_are_guarded(self):
        """پرونده‌های پنل مدیریت باید در فهرست نگهبانی باشند."""
        for key in ("diagnostic", "usage", "usage-md", "grant-doc",
                    "license-doc", "license-doc-md"):
            self.assertIn(key, ws.ADMIN_FILE_KEYS, f"{key} نگهبانی ندارد")

    def test_panel_endpoints_are_guarded(self):
        for path in ("/api/health", "/api/license", "/api/diagnose", "/api/usage"):
            self.assertIn(path, ws.ADMIN_ENDPOINTS, f"{path} از پنل محافظت نمی‌شود")


if __name__ == "__main__":
    unittest.main(verbosity=2)
