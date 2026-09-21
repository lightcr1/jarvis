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

    @staticmethod
    def _route_paths(route) -> set[str]:
        """Collect all registered paths reachable from a route, depth-first.

        Newer Starlette versions wrap ``include_router()``-added routes in an
        opaque ``_IncludedRouter`` object instead of flattening them into
        ``app.routes``.  Descending into ``original_router.routes`` (and any
        other nested ``.routes`` attribute) keeps this assertion stable across
        Starlette versions.
        """
        paths: set[str] = set()
        path = getattr(route, "path", None)
        if path:
            paths.add(path)
        nested_router = getattr(route, "original_router", None)
        nested = getattr(nested_router, "routes", None)
        if nested is None and path is None:
            nested = getattr(route, "routes", None)
        if nested:
            for child in nested:
                paths |= AppStartupTests._route_paths(child)
        return paths

    def test_import_app_and_stt_route_registration(self):
        module = self._get_module()
        self.assertTrue(hasattr(module, "app"))
        routes = set()
        for route in module.app.routes:
            routes |= self._route_paths(route)
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
