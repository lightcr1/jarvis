import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .router_dependencies import LiveRef


def build_alerts_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if isinstance(value, LiveRef) else value

    def build_alert_items(user_id: str, role: str) -> list[dict[str, object]]:
        service = current("home_assistant_service")
        overview = service.overview(user_id=user_id, role=role)
        health = service.health_status(user_id=user_id, role=role)
        items: list[dict[str, object]] = []

        for alert in overview.get("alerts") or []:
            code = str(alert.get("code") or "ha_alert")
            message = str(alert.get("message") or "").strip()
            if not message:
                continue
            items.append(
                {
                    "id": f"overview:{code}",
                    "level": str(alert.get("level") or "info"),
                    "title": "Home Assistant",
                    "message": message,
                    "source": "home_assistant",
                    "code": code,
                }
            )

        for entity in (health.get("alerts") or {}).get("unavailable_entities") or []:
            entity_id = str(entity.get("entity_id") or "").strip()
            if not entity_id:
                continue
            items.append(
                {
                    "id": f"entity:{entity_id}",
                    "level": "warning",
                    "title": "Entity unavailable",
                    "message": f"{entity.get('label') or entity_id} is unavailable.",
                    "source": "home_assistant",
                    "code": "entity_unavailable",
                }
            )

        for request in (health.get("alerts") or {}).get("pending_requests") or []:
            request_id = str(request.get("id") or "").strip()
            if not request_id:
                continue
            entity_label = str(request.get("entity_label") or request.get("entity_id") or "device")
            action = str(request.get("action") or "action")
            items.append(
                {
                    "id": f"request:{request_id}",
                    "level": "info",
                    "title": "Confirmation required",
                    "message": f"{entity_label} is waiting for confirmation to {action}.",
                    "source": "home_assistant",
                    "code": "pending_confirmation",
                }
            )

        return items

    @router.websocket("/ws/alerts")
    async def ws_alerts(websocket: WebSocket):
        token = (websocket.query_params.get("session") or "").strip()
        if not token:
            await websocket.close(code=4401)
            return
        try:
            session = deps["require_identity_session"](token)
        except Exception:
            await websocket.close(code=4401)
            return

        user = session["user"]
        await websocket.accept()
        previous_ids: set[str] = set()
        try:
            while True:
                try:
                    alerts = build_alert_items(user["id"], user["role"])
                except PermissionError:
                    alerts = []
                current_ids = {str(item.get("id") or "") for item in alerts}
                new_alerts = [item for item in alerts if str(item.get("id") or "") not in previous_ids]
                previous_ids = current_ids
                if new_alerts:
                    await websocket.send_json({"type": "alerts", "alerts": new_alerts})
                await asyncio.sleep(5)
        except WebSocketDisconnect:
            return

    return router
