from __future__ import annotations

from .jarvis_engine import ROLE_PERMISSIONS, normalize_role
from .permission_store import KNOWN_PERMISSIONS


def _normalized_permissions(values: list[str] | None) -> list[str]:
    seen = set()
    normalized: list[str] = []
    for value in values or []:
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if not cleaned or cleaned not in KNOWN_PERMISSIONS or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def _normalized_group_ids(values: list[str] | None) -> list[str]:
    seen = set()
    normalized: list[str] = []
    for value in values or []:
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def resolve_effective_permissions(
    role: str | None,
    user_id: str | None,
    membership_store,
    permission_store,
) -> set[str]:
    role_name = normalize_role(role)
    effective = set(ROLE_PERMISSIONS.get(role_name, set()))

    if not user_id:
        return effective

    user_permissions = _normalized_permissions(permission_store.list_user_permissions().get(user_id, []))
    effective.update(user_permissions)

    group_permissions = permission_store.list_group_permissions()
    for gid in _normalized_group_ids(membership_store.list_user_groups(user_id)):
        effective.update(_normalized_permissions(group_permissions.get(gid, [])))

    return effective


def build_permission_context(
    role: str | None,
    user_id: str | None,
    membership_store,
    permission_store,
) -> dict:
    role_name = normalize_role(role)
    role_permissions = sorted(ROLE_PERMISSIONS.get(role_name, set()))

    if not user_id:
        return {
            "role": role_name,
            "user_id": None,
            "role_permissions": role_permissions,
            "user_permissions": [],
            "group_ids": [],
            "group_permissions": {},
            "effective_permissions": role_permissions,
        }

    user_permissions = sorted(_normalized_permissions(permission_store.list_user_permissions().get(user_id, [])))
    group_ids = _normalized_group_ids(membership_store.list_user_groups(user_id))
    group_permissions_map = permission_store.list_group_permissions()
    group_permissions = {gid: sorted(_normalized_permissions(group_permissions_map.get(gid, []))) for gid in group_ids}

    effective = set(role_permissions)
    effective.update(user_permissions)
    for perms in group_permissions.values():
        effective.update(perms)

    return {
        "role": role_name,
        "user_id": user_id,
        "role_permissions": role_permissions,
        "user_permissions": user_permissions,
        "group_ids": group_ids,
        "group_permissions": group_permissions,
        "effective_permissions": sorted(effective),
    }


def permission_decision(
    role: str | None,
    user_id: str | None,
    permission: str,
    membership_store,
    permission_store,
) -> dict:
    ctx = build_permission_context(role, user_id, membership_store, permission_store)
    allowed = permission in set(ctx.get("effective_permissions", []))

    source = None
    if permission in set(ctx.get("role_permissions", [])):
        source = "role"
    elif permission in set(ctx.get("user_permissions", [])):
        source = "user"
    else:
        for gid, perms in (ctx.get("group_permissions") or {}).items():
            if permission in set(perms):
                source = f"group:{gid}"
                break

    return {
        "permission": permission,
        "allowed": allowed,
        "source": source,
        "context": ctx,
    }
