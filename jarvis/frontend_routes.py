from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
PUBLIC_STATIC_DIR = PROJECT_ROOT / "frontend" / "public_static"
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_ASSETS_DIR = FRONTEND_DIST_DIR / "assets"
FRONTEND_ICONS_DIR = FRONTEND_DIST_DIR / "icons"

frontend_router = APIRouter()


def mount_frontend_assets(app: FastAPI) -> None:
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    if FRONTEND_ASSETS_DIR.exists():
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_ASSETS_DIR)), name="frontend-assets")
    if FRONTEND_ICONS_DIR.exists():
        app.mount("/icons", StaticFiles(directory=str(FRONTEND_ICONS_DIR)), name="frontend-icons")


def _dist_or_public(filename: str) -> Path:
    dist_path = FRONTEND_DIST_DIR / filename
    return dist_path if dist_path.exists() else PUBLIC_STATIC_DIR / filename


def frontend_index_response() -> FileResponse:
    if FRONTEND_DIST_DIR.exists():
        return FileResponse(str(FRONTEND_DIST_DIR / "index.html"), headers={"Cache-Control": "no-store"})
    return FileResponse(str(STATIC_DIR / "index.html"), headers={"Cache-Control": "no-store"})


@frontend_router.get("/")
def root():
    return frontend_index_response()


@frontend_router.api_route("/manifest.json", methods=["GET", "HEAD"])
def manifest():
    manifest_path = FRONTEND_DIST_DIR / "manifest.json"
    if manifest_path.exists():
        return FileResponse(str(manifest_path), media_type="application/manifest+json")
    return FileResponse(str(PROJECT_ROOT / "frontend" / "manifest.json"), media_type="application/manifest+json")


# GET + HEAD on these static-asset routes: FileResponse already handles HEAD
# correctly (headers only, no body — see starlette.responses.FileResponse.__call__),
# but Starlette's router 405s a HEAD request before ever reaching the endpoint
# unless HEAD is explicitly registered. PWA/uptime checks commonly probe with HEAD.
@frontend_router.api_route("/sw.js", methods=["GET", "HEAD"])
def service_worker():
    # Registered at the root path in main.tsx (`register('/sw.js')`) so it gets
    # scope "/" — matching manifest.json's own "scope": "/". Must be servable
    # here or the service worker never registers at all, silently disabling
    # every push notification the backend already sends.
    return FileResponse(str(_dist_or_public("sw.js")), media_type="application/javascript")


@frontend_router.api_route("/favicon.svg", methods=["GET", "HEAD"])
def favicon():
    return FileResponse(str(_dist_or_public("favicon.svg")), media_type="image/svg+xml")


@frontend_router.api_route("/robots.txt", methods=["GET", "HEAD"])
def robots():
    return FileResponse(str(_dist_or_public("robots.txt")), media_type="text/plain")


@frontend_router.get("/static/orb-v2.html")
def orb_legacy_redirect():
    return RedirectResponse(url="/orb", status_code=307)


@frontend_router.get("/static/static-v4-tts.html")
def chat_legacy_redirect():
    return RedirectResponse(url="/chat", status_code=307)


@frontend_router.get("/chat")
@frontend_router.get("/home-assistant")
@frontend_router.get("/orb")
@frontend_router.get("/login")
@frontend_router.get("/settings")
@frontend_router.get("/dashboard")
@frontend_router.get("/dashboard/{path:path}")
@frontend_router.get("/monitor")
@frontend_router.get("/monitor/{path:path}")
# Deliberately NOT a /workspace/{path:path} wildcard like /dashboard above:
# this router is included before build_workspace_router in jarvisappv4.py, so
# a wildcard here would shadow the real /workspace/targets* API routes (GET
# requests would get the SPA shell back instead of JSON). List each hub
# sub-page explicitly instead.
@frontend_router.get("/workspace")
@frontend_router.get("/workspace/overview")
@frontend_router.get("/workspace/files")
@frontend_router.get("/workspace/communication")
@frontend_router.get("/workspace/desktop")
@frontend_router.get("/s/{token}")
def frontend_routes(path: str | None = None, token: str | None = None):
    return frontend_index_response()
