from __future__ import annotations

from fastapi import HTTPException

from jarvis_engine import normalize_role
from session_auth import bearer_token_from_header, is_token_active


def require_admin_access(
    user_store,
    tokens: dict[str, float],
    x_jarvis_user_id: str | None,
    x_jarvis_role: str | None,
    authorization: str | None,
    *,
    allow_bootstrap: bool = False,
) -> tuple[str, str]:
    token = bearer_token_from_header(authorization)
    if not is_token_active(tokens, token):
        raise HTTPException(401, "admin token required")

    users = user_store.list_users() if hasattr(user_store, "list_users") else []
    has_users = bool(users)

    if not x_jarvis_user_id:
        # First-run bootstrap path: allow only on endpoints that explicitly opt in.
        if allow_bootstrap and not has_users and normalize_role(x_jarvis_role) == "admin":
            return "bootstrap", "admin"
        raise HTTPException(401, "admin user required")

    user = user_store.get_user(x_jarvis_user_id)
    if not user:
        raise HTTPException(401, "admin user not found")
    if not bool(user.get("enabled", False)):
        raise HTTPException(403, "admin user disabled")

    caller_role = normalize_role(user.get("role"))
    if caller_role != "admin":
        raise HTTPException(403, "admin role required")

    claimed_role = normalize_role(x_jarvis_role)
    if claimed_role != caller_role:
        raise HTTPException(403, "role header mismatch")

    return x_jarvis_user_id, caller_role
