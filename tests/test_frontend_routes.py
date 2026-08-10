import unittest

from fastapi import FastAPI
from starlette.responses import FileResponse, RedirectResponse

from jarvis.frontend_routes import (
    FRONTEND_DIST_DIR,
    FRONTEND_ICONS_DIR,
    PUBLIC_STATIC_DIR,
    chat_legacy_redirect,
    favicon,
    frontend_index_response,
    frontend_router,
    mount_frontend_assets,
    orb_legacy_redirect,
    robots,
    service_worker,
)


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

    def test_service_worker_route_serves_sw_js(self):
        # Must be servable at exactly this path — main.tsx calls
        # navigator.serviceWorker.register('/sw.js'), and a 404 here means the
        # service worker never registers, silently disabling every push
        # notification the backend sends.
        response = service_worker()
        self.assertIsInstance(response, FileResponse)
        self.assertTrue(response.path.endswith("sw.js"))
        self.assertEqual(response.media_type, "application/javascript")

    def test_favicon_route_serves_svg(self):
        response = favicon()
        self.assertIsInstance(response, FileResponse)
        self.assertTrue(response.path.endswith("favicon.svg"))
        self.assertEqual(response.media_type, "image/svg+xml")

    def test_robots_route_serves_txt(self):
        response = robots()
        self.assertIsInstance(response, FileResponse)
        self.assertTrue(response.path.endswith("robots.txt"))

    def test_root_static_file_paths_are_registered(self):
        registered = {route.path for route in frontend_router.routes}
        for path in ("/sw.js", "/favicon.svg", "/robots.txt", "/manifest.json"):
            self.assertIn(path, registered)

    def test_icons_directory_mounts_when_present(self):
        app = FastAPI()
        mount_frontend_assets(app)
        mount_paths = {getattr(route, "path", None) for route in app.routes}
        if FRONTEND_ICONS_DIR.exists():
            self.assertIn("/icons", mount_paths)

    def test_dist_or_public_resolves_to_an_existing_file(self):
        from jarvis.frontend_routes import _dist_or_public
        for filename in ("sw.js", "favicon.svg", "robots.txt"):
            resolved = _dist_or_public(filename)
            self.assertTrue(
                resolved == FRONTEND_DIST_DIR / filename or resolved == PUBLIC_STATIC_DIR / filename
            )
            self.assertTrue(resolved.exists(), f"{resolved} should exist in either dist or public_static")


if __name__ == "__main__":
    unittest.main()
