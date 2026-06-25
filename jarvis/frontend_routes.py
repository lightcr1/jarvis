from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_ASSETS_DIR = FRONTEND_DIST_DIR / "assets"

frontend_router = APIRouter()


def mount_frontend_assets(app: FastAPI) -> None:
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    if FRONTEND_ASSETS_DIR.exists():
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_ASSETS_DIR)), name="frontend-assets")


def frontend_index_response() -> FileResponse:
    if FRONTEND_DIST_DIR.exists():
        return FileResponse(str(FRONTEND_DIST_DIR / "index.html"), headers={"Cache-Control": "no-store"})
    return FileResponse(str(STATIC_DIR / "index.html"), headers={"Cache-Control": "no-store"})


@frontend_router.get("/")
def root():
    return frontend_index_response()


@frontend_router.get("/manifest.json")
def manifest():
    manifest_path = FRONTEND_DIST_DIR / "manifest.json"
    if manifest_path.exists():
        return FileResponse(str(manifest_path), media_type="application/manifest+json")
    return FileResponse(str(PROJECT_ROOT / "frontend" / "manifest.json"), media_type="application/manifest+json")


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
@frontend_router.get("/workspace/home-assistant")
@frontend_router.get("/workspace/home-assistant/{path:path}")
def frontend_routes(path: str | None = None):
    return frontend_index_response()
