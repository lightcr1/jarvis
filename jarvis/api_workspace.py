from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from .router_dependencies import LiveRef
from .secret_crypto import SecretEncryptionUnavailable
from .workspace.service import WorkspaceConfigError, WorkspaceCredentialsMissing, WorkspaceWakeUnavailable


def build_workspace_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if isinstance(value, LiveRef) else value

    def _session(x_jarvis_session: str | None):
        return deps["require_identity_session"](x_jarvis_session)

    @router.get("/workspace/targets")
    def list_targets(x_jarvis_session: str | None = Header(default=None)):
        session = _session(x_jarvis_session)
        try:
            return current("workspace_service").list_targets(user_id=session["user"]["id"], role=session["user"]["role"])
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/workspace/targets")
    def create_target(payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        session = _session(x_jarvis_session)
        try:
            return current("workspace_service").create_target(payload, user_id=session["user"]["id"], role=session["user"]["role"])
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.patch("/workspace/targets/{target_id}")
    def update_target(target_id: str, payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        session = _session(x_jarvis_session)
        try:
            return current("workspace_service").update_target(target_id, payload, user_id=session["user"]["id"], role=session["user"]["role"])
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.delete("/workspace/targets/{target_id}")
    def delete_target(target_id: str, x_jarvis_session: str | None = Header(default=None)):
        session = _session(x_jarvis_session)
        try:
            return current("workspace_service").delete_target(target_id, user_id=session["user"]["id"], role=session["user"]["role"])
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/workspace/targets/{target_id}/credentials/status")
    def credentials_status(target_id: str, x_jarvis_session: str | None = Header(default=None)):
        session = _session(x_jarvis_session)
        try:
            return current("workspace_service").credentials_status(target_id, user_id=session["user"]["id"], role=session["user"]["role"])
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.put("/workspace/targets/{target_id}/credentials")
    def set_credentials(target_id: str, payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        session = _session(x_jarvis_session)
        try:
            return current("workspace_service").set_credentials(target_id, payload, user_id=session["user"]["id"], role=session["user"]["role"])
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except SecretEncryptionUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.delete("/workspace/targets/{target_id}/credentials")
    def delete_credentials(target_id: str, x_jarvis_session: str | None = Header(default=None)):
        session = _session(x_jarvis_session)
        try:
            return current("workspace_service").delete_credentials(target_id, user_id=session["user"]["id"], role=session["user"]["role"])
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/workspace/targets/{target_id}/connect")
    def connect(target_id: str, x_jarvis_session: str | None = Header(default=None)):
        session = _session(x_jarvis_session)
        try:
            return current("workspace_service").generate_connection_token(target_id, user_id=session["user"]["id"], role=session["user"]["role"])
        except WorkspaceCredentialsMissing as exc:
            raise HTTPException(409, str(exc)) from exc
        except WorkspaceConfigError as exc:
            raise HTTPException(503, str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/workspace/targets/{target_id}/wake")
    def wake(target_id: str, x_jarvis_session: str | None = Header(default=None)):
        session = _session(x_jarvis_session)
        try:
            return current("workspace_service").trigger_wake(target_id, user_id=session["user"]["id"], role=session["user"]["role"])
        except WorkspaceWakeUnavailable as exc:
            raise HTTPException(409, str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    return router
