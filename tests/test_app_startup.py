import importlib
import unittest

from fastapi.testclient import TestClient


class AppStartupTests(unittest.TestCase):
    def _get_module(self):
        try:
            importlib.import_module("python_multipart")
        except ModuleNotFoundError:
            self.skipTest("python-multipart is not installed in this test environment")
        return importlib.import_module("jarvisappv4")

    def test_import_app_and_stt_route_registration(self):
        module = self._get_module()
        self.assertTrue(hasattr(module, "app"))
        routes = {getattr(route, "path", "") for route in module.app.routes}
        self.assertIn("/stt", routes)
        self.assertIn("/admin/login", routes)

    def test_health_endpoint_returns_version_and_uptime(self):
        module = self._get_module()
        client = TestClient(module.app)
        resp = client.get("/health")
        self.assertEqual(200, resp.status_code)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("version", data)
        self.assertIn("uptime_sec", data)
        self.assertIn("active_tokens", data)

    def test_version_endpoint(self):
        module = self._get_module()
        client = TestClient(module.app)
        resp = client.get("/version")
        self.assertEqual(200, resp.status_code)
        data = resp.json()
        self.assertIn("version", data)
        self.assertRegex(data["version"], r"^\d+\.\d+\.\d+$")

    def test_version_constant_exposed(self):
        module = self._get_module()
        self.assertTrue(hasattr(module, "JARVIS_VERSION"))
        self.assertRegex(module.JARVIS_VERSION, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
