from __future__ import annotations

from fastapi import APIRouter, Header

from .router_dependencies import LiveRef


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

    return router
