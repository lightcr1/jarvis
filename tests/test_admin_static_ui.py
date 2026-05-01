from pathlib import Path
import unittest


class AdminStaticUiTests(unittest.TestCase):
    def test_admin_spa_routes_cover_core_views(self):
        router = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
        shell = Path("frontend/src/shared/layout/AdminShell.tsx").read_text(encoding="utf-8")
        settings = Path("frontend/src/routes/admin/pages/SettingsPage.tsx").read_text(encoding="utf-8")
        logs = Path("frontend/src/routes/admin/pages/LogsPage.tsx").read_text(encoding="utf-8")
        permissions = Path("frontend/src/routes/admin/pages/PermissionsPage.tsx").read_text(encoding="utf-8")
        self.assertIn('path: "/dashboard"', router)
        self.assertIn('{ path: "logs"', router)
        self.assertIn('{ path: "settings"', router)
        self.assertIn('{ path: "permissions"', router)
        self.assertIn("Back to Chat", shell)
        self.assertIn("Wakeword", settings)
        self.assertIn("Audit", logs)
        self.assertIn("permission", permissions.lower())

    def test_chat_ui_links_to_dashboard_via_spa(self):
        app = Path("frontend/src/screens/JarvisApp.tsx").read_text(encoding="utf-8")
        self.assertIn('/dashboard', app)
        self.assertIn('Dashboard', app)
        self.assertIn('onLogout', app)


if __name__ == "__main__":
    unittest.main()
