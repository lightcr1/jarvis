from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Header, HTTPException, Request, WebSocket, WebSocketDisconnect

from .api_models import HomeAssistantDiscoveryCandidateIn
from .router_dependencies import LiveRef


def build_home_assistant_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if isinstance(value, LiveRef) else value

    def client_ip_from_request(request: Request, x_forwarded_for: str | None) -> str | None:
        forwarded = (x_forwarded_for or "").split(",")[0].strip()
        if forwarded:
            return forwarded
        if request.client and request.client.host:
            return request.client.host
        return None

    @router.websocket("/ws/home-assistant")
    async def home_assistant_live(websocket: WebSocket):
        token = (websocket.query_params.get("session") or "").strip()
        if not token:
            await websocket.close(code=4401)
            return
        try:
            session = deps["require_identity_session"](token)
        except HTTPException:
            await websocket.close(code=4401)
            return

        service = current("home_assistant_service")
        try:
            await websocket.accept()
            last_payload = ""
            while True:
                snapshot = service.live_snapshot(
                    user_id=session["user"]["id"],
                    role=session["user"]["role"],
                )
                payload = {
                    "type": "snapshot",
                    "areas": snapshot.get("areas") or [],
                    "entities": snapshot.get("entities") or [],
                    "automations": snapshot.get("automations") or [],
                    "sync": snapshot.get("sync") or {},
                }
                serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                if serialized != last_payload:
                    await websocket.send_json(payload)
                    last_payload = serialized
                await asyncio.sleep(5)
        except PermissionError:
            await websocket.close(code=4403)
        except WebSocketDisconnect:
            return

    @router.get("/home-assistant/overview")
    def home_assistant_overview(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").overview(
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/home-assistant/device-profiles")
    def home_assistant_device_profiles(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").device_profiles(
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/home-assistant/system-target-profiles")
    def home_assistant_system_target_profiles(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").system_target_profiles(
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/home-assistant/areas")
    def home_assistant_areas(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").area_summary(
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/home-assistant/security-posture")
    def home_assistant_security_posture(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").security_posture(
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/home-assistant/automations")
    def home_assistant_automations(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").list_automation_rules(
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/home-assistant/recovery-playbooks")
    def home_assistant_recovery_playbooks(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").list_recovery_playbooks(
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/home-assistant/recovery-playbooks/{playbook_id}/execute")
    def home_assistant_execute_recovery_playbook(playbook_id: str, x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").execute_recovery_playbook(
                playbook_id,
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/home-assistant/automations")
    def home_assistant_create_automation(payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").create_automation_rule(
                payload,
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/home-assistant/automations/{rule_id}/toggle")
    def home_assistant_toggle_automation(
        rule_id: str,
        payload: dict[str, object] | None = None,
        x_jarvis_session: str | None = Header(default=None),
    ):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").toggle_automation_rule(
                rule_id,
                payload or {},
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/home-assistant/discovery/candidates")
    def home_assistant_discovery_candidates(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").list_discovery_candidates(
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/home-assistant/discovery/candidates")
    def home_assistant_add_candidate(payload: HomeAssistantDiscoveryCandidateIn, x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").create_discovery_candidate(
                payload.model_dump(),
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
    
    @router.post("/home-assistant/discovery/candidates/{candidate_id}/approve")
    def home_assistant_approve_candidate(
        candidate_id: str,
        payload: dict[str, object] | None = None,
        x_jarvis_session: str | None = Header(default=None),
    ):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").approve_discovery_candidate(
                candidate_id,
                payload or {},
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except (PermissionError, ValueError) as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/home-assistant/entities")
    def home_assistant_entities(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").list_managed_entities(
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/home-assistant/system-targets")
    def home_assistant_system_targets(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").list_system_targets(
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/home-assistant/system-targets")
    def home_assistant_create_system_target(payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").create_system_target(
                payload,
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/home-assistant/sync/entities")
    def home_assistant_sync_entities(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").sync_managed_entities(
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/home-assistant/health")
    def home_assistant_health(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").health_status(
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/home-assistant/control-requests")
    def home_assistant_control_requests(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").list_control_requests(
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/home-assistant/entities/{entity_id}/actions")
    def home_assistant_entity_action(
        entity_id: str,
        payload: dict[str, object],
        request: Request,
        x_jarvis_session: str | None = Header(default=None),
        x_forwarded_for: str | None = Header(default=None),
    ):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").request_entity_action(
                entity_id,
                payload,
                user_id=session["user"]["id"],
                role=session["user"]["role"],
                client_ip=client_ip_from_request(request, x_forwarded_for),
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/home-assistant/system-targets/{target_id}/actions")
    def home_assistant_system_target_action(
        target_id: str,
        payload: dict[str, object],
        request: Request,
        x_jarvis_session: str | None = Header(default=None),
        x_forwarded_for: str | None = Header(default=None),
    ):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").request_system_target_action(
                target_id,
                payload,
                user_id=session["user"]["id"],
                role=session["user"]["role"],
                client_ip=client_ip_from_request(request, x_forwarded_for),
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/home-assistant/control-requests/{request_id}/confirm")
    def home_assistant_confirm_control_request(
        request_id: str,
        payload: dict[str, object] | None = None,
        x_jarvis_session: str | None = Header(default=None),
    ):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").confirm_control_request(
                request_id,
                payload or {},
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/home-assistant/shopping-list")
    def home_assistant_shopping_list(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").list_shopping_list_items(
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/home-assistant/calendar")
    def home_assistant_calendar(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").list_calendar_items(
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/home-assistant/calendar/items")
    def home_assistant_add_calendar_item(payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").add_calendar_item(
                payload,
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/home-assistant/calendar/items/{item_id}/actions")
    def home_assistant_calendar_item_action(
        item_id: str,
        payload: dict[str, object] | None = None,
        x_jarvis_session: str | None = Header(default=None),
    ):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").act_on_calendar_item(
                item_id,
                payload or {},
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/home-assistant/sync/calendar")
    def home_assistant_sync_calendar(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").sync_calendar_items(
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/home-assistant/inbox")
    def home_assistant_inbox(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").list_inbox_items(
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/home-assistant/inbox/items")
    def home_assistant_add_inbox_item(payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").add_inbox_item(
                payload,
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/home-assistant/inbox/items/{item_id}/actions")
    def home_assistant_inbox_item_action(
        item_id: str,
        payload: dict[str, object] | None = None,
        x_jarvis_session: str | None = Header(default=None),
    ):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").act_on_inbox_item(
                item_id,
                payload or {},
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/home-assistant/sync/inbox")
    def home_assistant_sync_inbox(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").sync_inbox_items(
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/home-assistant/shopping-list/items")
    def home_assistant_add_shopping_list_item(payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").add_shopping_list_item(
                payload,
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/home-assistant/scenes")
    def home_assistant_scenes(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").list_scenes(
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/home-assistant/scenes/{scene_id}/activate")
    def home_assistant_activate_scene(scene_id: str, x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("home_assistant_service").activate_scene(
                scene_id,
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    return router
