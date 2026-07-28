from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from .email.service import summarize_email_body
from .router_dependencies import LiveRef
from .secret_crypto import SecretEncryptionUnavailable


def build_email_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if isinstance(value, LiveRef) else value

    @router.get("/email/messages")
    def list_messages(folder: str | None = None, unread_only: bool = False, x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("email_service").list_messages(
                user_id=session["user"]["id"], role=session["user"]["role"], folder=folder, unread_only=unread_only,
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/email/messages/{message_id}")
    def get_message(message_id: str, x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("email_service").get_message(
                message_id, user_id=session["user"]["id"], role=session["user"]["role"],
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/email/messages/{message_id}/body")
    def fetch_body(message_id: str, x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("email_service").fetch_body(
                message_id, user_id=session["user"]["id"], role=session["user"]["role"],
            )
        except LookupError as exc:
            raise HTTPException(409, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from exc

    @router.post("/email/messages/{message_id}/read")
    def mark_read(message_id: str, x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("email_service").mark_read(
                message_id, user_id=session["user"]["id"], role=session["user"]["role"],
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/email/messages/{message_id}/summarize")
    def summarize(message_id: str, x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        service = current("email_service")
        try:
            fetched = service.fetch_body(message_id, user_id=session["user"]["id"], role=session["user"]["role"])
        except LookupError as exc:
            raise HTTPException(409, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from exc
        summary = summarize_email_body(
            fetched["body"], get_provider=deps.get("get_provider"), get_gemini=deps.get("get_gemini"), get_openai=deps.get("get_openai"),
        )
        return service.set_summary(message_id, summary, user_id=session["user"]["id"], role=session["user"]["role"])

    @router.get("/email/drafts")
    def list_drafts(status: str | None = None, x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("email_service").list_drafts(
                user_id=session["user"]["id"], role=session["user"]["role"], status=status,
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/email/drafts")
    def create_draft(payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("email_service").create_draft(
                payload, user_id=session["user"]["id"], role=session["user"]["role"],
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.delete("/email/drafts/{draft_id}")
    def discard_draft(draft_id: str, x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("email_service").discard_draft(
                draft_id, user_id=session["user"]["id"], role=session["user"]["role"],
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/email/drafts/{draft_id}/send")
    def send_draft(draft_id: str, payload: dict[str, object] | None = None, x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        confirm = bool((payload or {}).get("confirm"))
        try:
            return current("email_service").send_draft(
                draft_id, user_id=session["user"]["id"], role=session["user"]["role"], confirm=confirm,
            )
        except LookupError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from exc

    @router.get("/email/credentials/status")
    def credentials_status(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("email_service").credentials_status(
                user_id=session["user"]["id"], role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.put("/email/credentials")
    def set_credentials(payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("email_service").set_credentials(
                payload, user_id=session["user"]["id"], role=session["user"]["role"],
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except SecretEncryptionUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.delete("/email/credentials")
    def delete_credentials(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("email_service").delete_credentials(
                user_id=session["user"]["id"], role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/email/sync")
    def sync(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("email_service").sync_inbox(
                user_id=session["user"]["id"], role=session["user"]["role"],
            )
        except LookupError as exc:
            raise HTTPException(409, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    return router
