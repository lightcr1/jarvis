import unittest

from starlette.responses import FileResponse, RedirectResponse

from jarvis.frontend_routes import chat_legacy_redirect, frontend_index_response, orb_legacy_redirect


class FrontendRouteModuleTests(unittest.TestCase):
    def test_frontend_index_response_is_never_cached(self):
        response = frontend_index_response()
        self.assertIsInstance(response, FileResponse)
        self.assertEqual(response.headers.get("cache-control"), "no-store")

    def test_legacy_routes_redirect_to_spa_paths(self):
        orb_response = orb_legacy_redirect()
        chat_response = chat_legacy_redirect()

        self.assertIsInstance(orb_response, RedirectResponse)
        self.assertEqual(orb_response.headers.get("location"), "/orb")
        self.assertEqual(orb_response.status_code, 307)

        self.assertIsInstance(chat_response, RedirectResponse)
        self.assertEqual(chat_response.headers.get("location"), "/chat")
        self.assertEqual(chat_response.status_code, 307)


if __name__ == "__main__":
    unittest.main()
