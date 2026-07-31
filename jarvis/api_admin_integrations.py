from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .home_assistant.client import HA_CREDENTIAL_INTEGRATION, HA_CREDENTIAL_OWNER
from .router_dependencies import LiveRef
from .secret_crypto import SecretEncryptionUnavailable


class HomeAssistantCredentialsIn(BaseModel):
    base_url: str = Field(..., min_length=5, max_length=300)
    api_token: str = Field(..., min_length=10, max_length=2000)


def _ha_token_hint(token: str) -> str:
    if len(token) <= 10:
        return "***"
    return f"{token[:6]}…{token[-4:]}"


def build_admin_integrations_router(deps: dict) -> APIRouter:
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

    def _enrich(entries: list[dict]) -> list[dict]:
        users = {u["id"]: u for u in current("user_store").list_users()}
        return [
            {**entry, "username": users.get(entry["user_id"], {}).get("username")}
            for entry in entries
        ]

    @router.get("/admin/integrations/status")
    def integrations_status(
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        store = current("integration_credential_store")
        return {
            "calendar": _enrich(store.list_users_with_credential("calendar")),
            "email": _enrich(store.list_users_with_credential("email")),
        }

    @router.get("/admin/integrations/home-assistant")
    def get_ha_credentials(
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        status = current("integration_credential_store").status(HA_CREDENTIAL_OWNER, HA_CREDENTIAL_INTEGRATION)
        client = current("home_assistant_client")
        return {
            "configured": bool(client.base_url and client.api_token),
            "custom": status["configured"],
            "base_url": client.base_url,
            "token_hint": _ha_token_hint(client.api_token) if client.api_token else "",
            "updated_at": status["updated_at"],
        }

    @router.put("/admin/integrations/home-assistant")
    def set_ha_credentials(
        payload: HomeAssistantCredentialsIn,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        user_id, role = _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        try:
            current("integration_credential_store").set_credentials(
                HA_CREDENTIAL_OWNER,
                HA_CREDENTIAL_INTEGRATION,
                {"base_url": payload.base_url.strip(), "api_token": payload.api_token.strip()},
            )
        except SecretEncryptionUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        current("sync_home_assistant_credentials")()
        current("audit_admin_event")("admin_home_assistant_credentials_set", user_id, role, {})
        client = current("home_assistant_client")
        return {"configured": bool(client.base_url and client.api_token), "base_url": client.base_url}

    @router.delete("/admin/integrations/home-assistant")
    def clear_ha_credentials(
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        user_id, role = _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        current("integration_credential_store").delete_credentials(HA_CREDENTIAL_OWNER, HA_CREDENTIAL_INTEGRATION)
        current("sync_home_assistant_credentials")()
        current("audit_admin_event")("admin_home_assistant_credentials_cleared", user_id, role, {})
        client = current("home_assistant_client")
        return {"configured": bool(client.base_url and client.api_token)}

    @router.post("/admin/integrations/home-assistant/test")
    def test_ha_connection(
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        client = current("home_assistant_client")
        return {"ok": client.check_connection()}

    return router
