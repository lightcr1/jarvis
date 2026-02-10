import importlib
import unittest


class AppStartupTests(unittest.TestCase):
    def test_import_app_and_stt_route_registration(self):
        try:
            importlib.import_module("python_multipart")
        except ModuleNotFoundError:
            self.skipTest("python-multipart is not installed in this test environment")

        module = importlib.import_module("jarvisappv4")
        self.assertTrue(hasattr(module, "app"))

        routes = {getattr(route, "path", "") for route in module.app.routes}
        self.assertIn("/stt", routes)


if __name__ == "__main__":
    unittest.main()
