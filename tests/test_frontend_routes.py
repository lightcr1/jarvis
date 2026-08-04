import unittest

from starlette.responses import FileResponse, RedirectResponse

from jarvis.frontend_routes import chat_legacy_redirect, frontend_index_response, frontend_router, orb_legacy_redirect


class FrontendRouteModuleTests(unittest.TestCase):
    def test_frontend_index_response_is_never_cached(self):
        response = frontend_index_response()
        self.assertIsInstance(response, FileResponse)
        self.assertEqual(response.headers.get("cache-control"), "no-store")

    def test_workspace_spa_paths_are_registered(self):
        registered = {route.path for route in frontend_router.routes}
        for path in ("/workspace", "/workspace/overview", "/workspace/files", "/workspace/communication", "/workspace/desktop"):
            self.assertIn(path, registered)

    def test_workspace_spa_route_is_not_a_wildcard(self):
        # A /workspace/{path:path} wildcard would shadow the real
        # /workspace/targets* backend API (frontend_router is included before
        # build_workspace_router in jarvisappv4.py) — GET requests to it would
        # get the SPA shell back instead of JSON. See the comment in
        # frontend_routes.py above these routes.
        registered = {route.path for route in frontend_router.routes}
        self.assertNotIn("/workspace/{path:path}", registered)

    def test_public_share_link_spa_route_is_registered(self):
        registered = {route.path for route in frontend_router.routes}
        self.assertIn("/s/{token}", registered)

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
