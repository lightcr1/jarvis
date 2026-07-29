from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from .calendar.client import CalDavConnectionError
from .router_dependencies import LiveRef
from .secret_crypto import SecretEncryptionUnavailable


def build_calendar_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if isinstance(value, LiveRef) else value

    @router.get("/calendar/events")
    def list_events(start: int | None = None, end: int | None = None, x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("calendar_service").list_events(
                user_id=session["user"]["id"], role=session["user"]["role"], start=start, end=end,
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/calendar/events")
    def create_event(payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        force = bool(payload.get("force"))
        try:
            return current("calendar_service").create_event(
                payload, user_id=session["user"]["id"], role=session["user"]["role"], force=force,
            )
        except LookupError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from exc

    @router.delete("/calendar/events/{event_id}")
    def delete_event(event_id: str, x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("calendar_service").delete_event(
                event_id, user_id=session["user"]["id"], role=session["user"]["role"],
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/calendar/credentials/status")
    def credentials_status(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("calendar_service").credentials_status(
                user_id=session["user"]["id"], role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.put("/calendar/credentials")
    def set_credentials(payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("calendar_service").set_credentials(
                payload, user_id=session["user"]["id"], role=session["user"]["role"],
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except SecretEncryptionUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        except CalDavConnectionError as exc:
            raise HTTPException(502, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.delete("/calendar/credentials")
    def delete_credentials(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("calendar_service").delete_credentials(
                user_id=session["user"]["id"], role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/calendar/sync")
    def sync(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("calendar_service").sync(
                user_id=session["user"]["id"], role=session["user"]["role"],
            )
        except LookupError as exc:
            raise HTTPException(409, str(exc)) from exc
        except CalDavConnectionError as exc:
            raise HTTPException(502, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    return router
