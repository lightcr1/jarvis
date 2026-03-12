from __future__ import annotations


def get_active_user_or_raise(user_store, user_id: str | None) -> dict | None:
    if not user_id:
        return None

    user = user_store.get_user(user_id)
    if not user:
        raise LookupError("user not found")

    if not bool(user.get("enabled", False)):
        raise PermissionError("user disabled")

    return user
