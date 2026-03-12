from pathlib import Path
import unittest


class AdminStaticUiTests(unittest.TestCase):
    def test_admin_page_exists_and_covers_core_tabs(self):
        content = Path("static/admin.html").read_text(encoding="utf-8")
        self.assertIn("J.A.R.V.I.S. Admin", content)
        self.assertIn("Action Logs", content)
        self.assertIn("Runtime Defaults", content)
        self.assertIn("/admin/settings", content)
        self.assertIn("/admin/audit/events", content)
        self.assertIn("/admin/permissions/effective/", content)

    def test_chat_ui_links_to_admin_console(self):
        content = Path("static/index.html").read_text(encoding="utf-8")
        self.assertIn('id="adminBtn"', content)
        self.assertIn('window.location.href = "/static/admin.html";', content)


if __name__ == "__main__":
    unittest.main()
