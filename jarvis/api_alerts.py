from __future__ import annotations

import asyncio
import threading
import time
from typing import Callable

from fastapi import APIRouter, Header, HTTPException, WebSocket, WebSocketDisconnect

from .api_models import AlertRuleCreate, AlertRuleUpdate
from .router_dependencies import LiveRef


class AlertBroadcaster:
    """Fan-out broadcaster for connected /ws/alerts clients."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._clients: set[WebSocket] = set()

    def connect(self, ws: WebSocket) -> None:
        with self._lock:
            self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, payload: dict) -> None:
        with self._lock:
            targets = list(self._clients)
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                self._clients.discard(ws)


_broadcaster = AlertBroadcaster()


def get_alert_broadcaster() -> AlertBroadcaster:
    return _broadcaster


def build_alerts_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if isinstance(value, LiveRef) else value

    def _admin_guard(
        x_jarvis_user_id: str | None = None,
        x_jarvis_role: str | None = None,
        authorization: str | None = None,
    ) -> tuple[str, str]:
        require_admin = current("require_admin_access")
        return require_admin(x_jarvis_user_id, x_jarvis_role, authorization)

    def _audit(event: str, actor_user_id: str, actor_role: str, payload: dict | None = None) -> None:
        fn: Callable = current("audit_admin_event")
        fn(event, actor_user_id, actor_role, payload)

    @router.get("/admin/alerts/rules")
    def list_rules(
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        store = current("alert_rules_store")
        return {"rules": store.list_rules()}

    @router.post("/admin/alerts/rules", status_code=201)
    def create_rule(
        body: AlertRuleCreate,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        actor_id, actor_role = _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        store = current("alert_rules_store")
        rule = store.create_rule(body.model_dump())
        _audit("alert.rule.created", actor_id, actor_role, {"rule_id": rule["id"], "name": rule["name"]})
        return {"rule": rule}

    @router.patch("/admin/alerts/rules/{rule_id}")
    def update_rule(
        rule_id: str,
        body: AlertRuleUpdate,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        actor_id, actor_role = _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        store = current("alert_rules_store")
        patch = {k: v for k, v in body.model_dump().items() if v is not None}
        updated = store.update_rule(rule_id, patch)
        if updated is None:
            raise HTTPException(404, "Rule not found")
        _audit("alert.rule.updated", actor_id, actor_role, {"rule_id": rule_id, "patch": list(patch.keys())})
        return {"rule": updated}

    @router.delete("/admin/alerts/rules/{rule_id}")
    def delete_rule(
        rule_id: str,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        actor_id, actor_role = _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        store = current("alert_rules_store")
        deleted = store.delete_rule(rule_id)
        if not deleted:
            raise HTTPException(404, "Rule not found")
        _audit("alert.rule.deleted", actor_id, actor_role, {"rule_id": rule_id})
        return {"ok": True, "id": rule_id}

    @router.post("/admin/alerts/rules/{rule_id}/test")
    async def test_rule(
        rule_id: str,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        actor_id, actor_role = _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        store = current("alert_rules_store")
        rule = store.get_rule(rule_id)
        if rule is None:
            raise HTTPException(404, "Rule not found")
        engine = current("alert_engine")
        event = await engine.fire_test_alert(rule)
        _audit("alert.rule.tested", actor_id, actor_role, {"rule_id": rule_id})
        return {"ok": True, "event": event}

    @router.get("/admin/alerts/history")
    def get_history(
        limit: int = 100,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        engine = current("alert_engine")
        return {"alerts": engine.get_history(limit=min(limit, 500))}

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

        await websocket.accept()
        _broadcaster.connect(websocket)

        try:
            ha_alerts = _get_ha_alerts(deps, session)
        except Exception:
            ha_alerts = []
        if ha_alerts:
            await websocket.send_json({"type": "alerts", "alerts": ha_alerts})

        try:
            while True:
                await asyncio.sleep(30)
                try:
                    new_ha = _get_ha_alerts(deps, session)
                except Exception:
                    new_ha = []
                if new_ha:
                    await websocket.send_json({"type": "alerts", "alerts": new_ha})
        except WebSocketDisconnect:
            pass
        finally:
            _broadcaster.disconnect(websocket)

    return router


def _get_ha_alerts(deps: dict, session: dict) -> list[dict]:
    def current(name: str):
        value = deps.get(name)
        return value.get() if isinstance(value, LiveRef) else value

    service = current("home_assistant_service")
    if service is None:
        return []
    user = session["user"]
    overview = service.overview(user_id=user["id"], role=user["role"])
    health = service.health_status(user_id=user["id"], role=user["role"])
    items: list[dict] = []

    for alert in overview.get("alerts") or []:
        code = str(alert.get("code") or "ha_alert")
        message = str(alert.get("message") or "").strip()
        if not message:
            continue
        items.append({
            "type": "alerts",
            "id": f"overview:{code}",
            "level": str(alert.get("level") or "info"),
            "title": "Home Assistant",
            "message": message,
            "source": "home_assistant",
            "code": code,
        })

    for entity in (health.get("alerts") or {}).get("unavailable_entities") or []:
        entity_id = str(entity.get("entity_id") or "").strip()
        if not entity_id:
            continue
        items.append({
            "type": "alerts",
            "id": f"entity:{entity_id}",
            "level": "warning",
            "title": "Entity unavailable",
            "message": f"{entity.get('label') or entity_id} is unavailable.",
            "source": "home_assistant",
            "code": "entity_unavailable",
        })

    return items
