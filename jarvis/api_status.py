import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .router_dependencies import LiveRef


def build_status_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if isinstance(value, LiveRef) else value

    @router.websocket("/ws/status")
    async def ws_status(websocket: WebSocket):
        await websocket.accept()
        hub = current("status_hub")
        last_version = -1
        try:
            while True:
                snapshot = hub.snapshot()
                version = int(snapshot.get("version") or 0)
                if version != last_version:
                    await websocket.send_json(snapshot)
                    last_version = version
                await asyncio.sleep(0.25)
        except WebSocketDisconnect:
            return

    return router
