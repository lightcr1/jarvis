import datetime
import json

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response

from .api_models import (
    AdminGroupCreateIn,
    AdminGroupUpdateIn,
    AdminMembershipIn,
    AdminPermissionSetIn,
    AdminSettingsIn,
    AdminUserCreateIn,
    AdminUserUpdateIn,
    UserPasswordIn,
)
from .router_dependencies import LiveRef


def build_admin_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if isinstance(value, LiveRef) else value

    require_admin_access = deps["require_admin_access"]
    prepare_audit_filters = deps["prepare_audit_filters"]
    validate_audit_query = deps["validate_audit_query"]
    normalize_role = deps["normalize_role"]
    audit_admin_event = deps["audit_admin_event"]
    known_permissions = deps["known_permissions"]
    get_active_user_or_raise = deps["get_active_user_or_raise"]
    build_permission_context = deps["build_permission_context"]
    permission_decision = deps["permission_decision"]
    settings_env_summary = deps["settings_env_summary"]

    @router.get("/admin/audit/events")
    def admin_audit_events(
        limit: int = 100,
        event: str | None = None,
        role: str | None = None,
        since_ts: int | None = None,
        until_ts: int | None = None,
        actor_user_id: str | None = None,
        token_fingerprint: str | None = None,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        filters = prepare_audit_filters(event, role, actor_user_id, token_fingerprint)
        validate_audit_query(limit, since_ts, until_ts)
        events = current("audit_log").read_events(
            limit=limit,
            event=filters["event"],
            role=filters["role"],
            since_ts=since_ts,
            until_ts=until_ts,
            actor_user_id=filters["actor_user_id"],
            token_fingerprint=filters["token_fingerprint"],
        )
        return {"events": events, "count": len(events), "filters": {"limit": limit, **filters, "since_ts": since_ts, "until_ts": until_ts}}

    @router.get("/admin/audit/counts")
    def admin_audit_counts(
        event: str | None = None,
        role: str | None = None,
        since_ts: int | None = None,
        until_ts: int | None = None,
        actor_user_id: str | None = None,
        token_fingerprint: str | None = None,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        filters = prepare_audit_filters(event, role, actor_user_id, token_fingerprint)
        validate_audit_query(100, since_ts, until_ts)
        counts = current("audit_log").aggregate_counts(
            event=filters["event"],
            role=filters["role"],
            since_ts=since_ts,
            until_ts=until_ts,
            actor_user_id=filters["actor_user_id"],
            token_fingerprint=filters["token_fingerprint"],
        )
        return {"total": sum(counts.values()), "counts": counts, "filters": {**filters, "since_ts": since_ts, "until_ts": until_ts}}

    @router.get("/admin/audit/count")
    def admin_audit_count(
        event: str | None = None,
        role: str | None = None,
        since_ts: int | None = None,
        until_ts: int | None = None,
        actor_user_id: str | None = None,
        token_fingerprint: str | None = None,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        filters = prepare_audit_filters(event, role, actor_user_id, token_fingerprint)
        validate_audit_query(100, since_ts, until_ts)
        count = current("audit_log").count_events(
            event=filters["event"],
            role=filters["role"],
            since_ts=since_ts,
            until_ts=until_ts,
            actor_user_id=filters["actor_user_id"],
            token_fingerprint=filters["token_fingerprint"],
        )
        return {"count": count, "filters": {**filters, "since_ts": since_ts, "until_ts": until_ts}}

    @router.get("/admin/users")
    def admin_list_users(x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        import time
        now = time.time()
        tokens = current("identity_tokens")
        active_users: dict[str, float] = {}
        for data in tokens.values():
            uid = data.get("user_id")
            exp = data.get("exp", 0)
            if uid and exp > now:
                active_users[uid] = max(active_users.get(uid, 0), exp)
        users = current("user_store").list_users()
        for u in users:
            uid = u["id"]
            if uid in active_users:
                u["active_session"] = True
                u["session_expires_at"] = int(active_users[uid])
            else:
                u["active_session"] = False
                u["session_expires_at"] = None
        return {"users": users}

    @router.post("/admin/users")
    def admin_create_user(payload: AdminUserCreateIn, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_user_id, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization, allow_bootstrap=True)
        if actor_user_id == "bootstrap":
            if normalize_role(payload.role) != "admin":
                raise HTTPException(400, "bootstrap can only create admin user")
            if not bool(payload.enabled):
                raise HTTPException(400, "bootstrap admin must be enabled")
        try:
            created = current("user_store").create_user(payload.username, role=payload.role, enabled=payload.enabled)
        except ValueError as exc:
            detail = str(exc)
            if detail == "username already exists":
                raise HTTPException(409, detail)
            raise HTTPException(400, detail)
        if payload.password:
            current("admin_password_store").set_password(created["id"], payload.password)
        audit_admin_event("admin_user_created", actor_user_id, caller_role, {"user_id": created["id"], "username": created["username"], "role": created["role"]})
        return created

    @router.patch("/admin/users/{user_id}")
    def admin_update_user(user_id: str, payload: AdminUserUpdateIn, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_user_id, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        existing_user = current("user_store").get_user(user_id)
        if not existing_user:
            raise HTTPException(404, "user not found")
        if bool(existing_user.get("enabled", False)) and existing_user.get("role") == "admin" and payload.enabled is False and current("user_store").enabled_admin_count() <= 1:
            raise HTTPException(400, "cannot disable last enabled admin")
        if bool(existing_user.get("enabled", False)) and existing_user.get("role") == "admin" and payload.role is not None and normalize_role(payload.role) != "admin" and current("user_store").enabled_admin_count() <= 1:
            raise HTTPException(400, "cannot demote last enabled admin")
        try:
            updated = current("user_store").update_user(user_id, role=payload.role, enabled=payload.enabled)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        audit_admin_event("admin_user_updated", actor_user_id, caller_role, {"user_id": user_id})
        return updated

    @router.put("/admin/users/{user_id}/password")
    def admin_set_user_password(user_id: str, payload: UserPasswordIn, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_user_id, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        user = current("user_store").get_user(user_id)
        if not user:
            raise HTTPException(404, "user not found")
        current("admin_password_store").set_password(user_id, payload.password)
        audit_admin_event("admin_user_password_updated", actor_user_id, caller_role, {"user_id": user_id})
        return {"ok": True, "id": user_id}

    @router.delete("/admin/users/{user_id}")
    def admin_delete_user(user_id: str, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_user_id, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        target = current("user_store").get_user(user_id)
        if not target:
            raise HTTPException(404, "user not found")
        if target.get("role") == "admin" and bool(target.get("enabled", False)) and current("user_store").enabled_admin_count() <= 1:
            raise HTTPException(400, "cannot delete last enabled admin")
        deleted = current("user_store").delete_user(user_id)
        if not deleted:
            raise HTTPException(404, "user not found")
        removed_password = current("admin_password_store").delete_password(user_id)
        removed_preferences = current("user_preferences_store").delete(user_id)
        removed_memberships = current("membership_store").remove_user_memberships(user_id)
        removed_permissions = current("permission_store").clear_user_permissions(user_id)
        audit_admin_event("admin_user_deleted", actor_user_id, caller_role, {"user_id": user_id, "removed_password": removed_password, "removed_preferences": removed_preferences, "removed_memberships": removed_memberships, "removed_user_permissions": bool(removed_permissions)})
        return {"ok": True, "id": user_id}

    @router.get("/admin/groups")
    def admin_list_groups(x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        return {"groups": current("group_store").list_groups()}

    @router.post("/admin/groups")
    def admin_create_group(payload: AdminGroupCreateIn, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_user_id, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        try:
            created = current("group_store").create_group(payload.name, description=payload.description)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        audit_admin_event("admin_group_created", actor_user_id, caller_role, {"group_id": created["id"], "name": created["name"]})
        return created

    @router.patch("/admin/groups/{group_id}")
    def admin_update_group(group_id: str, payload: AdminGroupUpdateIn, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_user_id, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        try:
            updated = current("group_store").update_group(group_id, name=payload.name, description=payload.description)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        if not updated:
            raise HTTPException(404, "group not found")
        audit_admin_event("admin_group_updated", actor_user_id, caller_role, {"group_id": group_id})
        return updated

    @router.delete("/admin/groups/{group_id}")
    def admin_delete_group(group_id: str, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_user_id, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        deleted = current("group_store").delete_group(group_id)
        if not deleted:
            raise HTTPException(404, "group not found")
        removed_memberships = current("membership_store").remove_group_memberships(group_id)
        removed_permissions = current("permission_store").clear_group_permissions(group_id)
        audit_admin_event("admin_group_deleted", actor_user_id, caller_role, {"group_id": group_id, "removed_memberships": removed_memberships, "removed_group_permissions": bool(removed_permissions)})
        return {"ok": True, "id": group_id}

    @router.get("/admin/assignments")
    def admin_list_assignments(x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        return {"memberships": current("membership_store").list_memberships()}

    @router.post("/admin/assignments")
    def admin_add_assignment(payload: AdminMembershipIn, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_user_id, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        if not current("user_store").get_user(payload.user_id):
            raise HTTPException(404, "user not found")
        if not current("group_store").get_group(payload.group_id):
            raise HTTPException(404, "group not found")
        try:
            item = current("membership_store").add_membership(payload.user_id, payload.group_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        audit_admin_event("admin_assignment_added", actor_user_id, caller_role, {"user_id": payload.user_id, "group_id": payload.group_id})
        return item

    @router.delete("/admin/assignments")
    def admin_remove_assignment(user_id: str, group_id: str, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_user_id, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        removed = current("membership_store").remove_membership(user_id, group_id)
        if not removed:
            raise HTTPException(404, "assignment not found")
        audit_admin_event("admin_assignment_removed", actor_user_id, caller_role, {"user_id": user_id, "group_id": group_id})
        return {"ok": True, "user_id": user_id, "group_id": group_id}

    @router.get("/admin/permissions")
    def admin_list_permissions(x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        return {
            "known_permissions": sorted(known_permissions),
            "group_permissions": current("permission_store").list_group_permissions(),
            "user_permissions": current("permission_store").list_user_permissions(),
        }

    @router.put("/admin/permissions/groups/{group_id}")
    def admin_set_group_permissions(group_id: str, payload: AdminPermissionSetIn, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_user_id, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        if not current("group_store").get_group(group_id):
            raise HTTPException(404, "group not found")
        invalid = current("permission_store").invalid_permissions(payload.permissions)
        if invalid:
            raise HTTPException(400, f"invalid permissions: {', '.join(invalid)}")
        try:
            updated = current("permission_store").set_group_permissions(group_id, payload.permissions)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        audit_admin_event("admin_group_permissions_set", actor_user_id, caller_role, {"group_id": group_id, "count": len(updated)})
        return {"group_id": group_id, "permissions": updated}

    @router.put("/admin/permissions/users/{user_id}")
    def admin_set_user_permissions(user_id: str, payload: AdminPermissionSetIn, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_user_id, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        if not current("user_store").get_user(user_id):
            raise HTTPException(404, "user not found")
        invalid = current("permission_store").invalid_permissions(payload.permissions)
        if invalid:
            raise HTTPException(400, f"invalid permissions: {', '.join(invalid)}")
        try:
            updated = current("permission_store").set_user_permissions(user_id, payload.permissions)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        audit_admin_event("admin_user_permissions_set", actor_user_id, caller_role, {"user_id": user_id, "count": len(updated)})
        return {"user_id": user_id, "permissions": updated}

    @router.delete("/admin/permissions/groups/{group_id}")
    def admin_clear_group_permissions(group_id: str, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_user_id, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        cleared = current("permission_store").clear_group_permissions(group_id)
        if not cleared:
            raise HTTPException(404, "group permissions not found")
        audit_admin_event("admin_group_permissions_cleared", actor_user_id, caller_role, {"group_id": group_id})
        return {"ok": True, "group_id": group_id}

    @router.delete("/admin/permissions/users/{user_id}")
    def admin_clear_user_permissions(user_id: str, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_user_id, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        cleared = current("permission_store").clear_user_permissions(user_id)
        if not cleared:
            raise HTTPException(404, "user permissions not found")
        audit_admin_event("admin_user_permissions_cleared", actor_user_id, caller_role, {"user_id": user_id})
        return {"ok": True, "user_id": user_id}

    @router.get("/admin/permissions/effective/{user_id}")
    def admin_effective_permissions(user_id: str, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        try:
            user = get_active_user_or_raise(current("user_store"), user_id)
        except LookupError:
            raise HTTPException(404, "user not found")
        except PermissionError:
            raise HTTPException(403, "user disabled")
        context = build_permission_context(user.get("role"), user_id, current("membership_store"), current("permission_store"))
        return {"user": user, "permissions": context}

    @router.get("/admin/authz/check")
    def admin_check_authorization(user_id: str, permission: str, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        try:
            user = get_active_user_or_raise(current("user_store"), user_id)
        except LookupError:
            raise HTTPException(404, "user not found")
        except PermissionError:
            raise HTTPException(403, "user disabled")
        decision = permission_decision(user.get("role"), user_id, permission, current("membership_store"), current("permission_store"))
        return {"user": user, **decision}

    @router.get("/admin/status/summary")
    def admin_status_summary(x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        users = current("user_store").list_users()
        groups = current("group_store").list_groups()
        user_ids = {user.get("id") for user in users}
        group_ids = {group.get("id") for group in groups}
        enabled_admins = [user for user in users if user.get("role") == "admin" and bool(user.get("enabled", False))]
        disabled_admins = [user for user in users if user.get("role") == "admin" and not bool(user.get("enabled", False))]
        admin_lockout_state = "locked_out" if len(enabled_admins) == 0 else "at_risk" if len(enabled_admins) == 1 else "ok"
        memberships = current("membership_store").list_memberships()
        orphan_memberships = [membership for membership in memberships if (membership.get("user_id") not in user_ids) or (membership.get("group_id") not in group_ids)]
        group_permissions = current("permission_store").list_group_permissions()
        user_permissions = current("permission_store").list_user_permissions()
        orphan_group_permission_sets = [group_id for group_id in group_permissions.keys() if group_id not in group_ids]
        orphan_user_permission_sets = [user_id for user_id in user_permissions.keys() if user_id not in user_ids]
        return {
            "counts": {
                "users": len(users),
                "enabled_admins": len(enabled_admins),
                "disabled_admins": len(disabled_admins),
                "groups": len(groups),
                "memberships": len(memberships),
                "group_permission_sets": len(group_permissions),
                "user_permission_sets": len(user_permissions),
                "audit_events": current("audit_log").count_events(),
                "orphan_memberships": len(orphan_memberships),
                "orphan_group_permission_sets": len(orphan_group_permission_sets),
                "orphan_user_permission_sets": len(orphan_user_permission_sets),
                "admin_lockout_risk": len(enabled_admins) <= 1,
                "admin_lockout_state": admin_lockout_state,
            },
            "orphans": {
                "memberships": orphan_memberships,
                "group_permission_sets": orphan_group_permission_sets,
                "user_permission_sets": orphan_user_permission_sets,
            },
            "settings": settings_env_summary(),
        }

    @router.get("/admin/settings")
    def admin_get_settings(x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        return {"settings": current("admin_settings_store").get(), "effective": settings_env_summary()}

    @router.put("/admin/settings")
    def admin_update_settings(payload: AdminSettingsIn, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_user_id, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        updated = current("admin_settings_store").update(payload.model_dump())
        audit_admin_event("admin_settings_updated", actor_user_id, caller_role, {"token_ttl_min": updated["usage_limits"]["token_ttl_min"], "max_active_tokens": updated["usage_limits"]["max_active_tokens"], "wakeword_enabled": updated["voice"]["wakeword_enabled"], "wakeword_phrase": updated["voice"]["wakeword_phrase"], "stt_provider": updated["voice"]["stt_provider"]})
        return {"settings": updated, "effective": settings_env_summary()}

    @router.get("/admin/sessions")
    def admin_list_sessions(x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        import time as _time
        require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        now = _time.time()
        tokens = current("identity_tokens")
        users = {u["id"]: u for u in current("user_store").list_users()}
        sessions = []
        for _tok, data in list(tokens.items()):
            exp = float(data.get("exp", 0))
            if exp < now:
                continue
            uid = data.get("user_id", "")
            u = users.get(uid, {})
            sessions.append({
                "user_id": uid,
                "username": u.get("username", uid),
                "role": data.get("role", "unknown"),
                "expires_at": int(exp),
                "expires_in_sec": int(exp - now),
            })
        sessions.sort(key=lambda s: s["expires_in_sec"], reverse=True)
        return {"sessions": sessions, "count": len(sessions)}

    @router.delete("/admin/sessions/{user_id}")
    def admin_revoke_sessions(user_id: str, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        tokens = current("identity_tokens")
        revoked = [tok for tok, data in list(tokens.items()) if data.get("user_id") == user_id]
        for tok in revoked:
            tokens.pop(tok, None)
        current("audit_log").write("admin_sessions_revoked", {"target_user_id": user_id, "revoked_count": len(revoked)})
        return {"ok": True, "revoked": len(revoked), "user_id": user_id}

    @router.get("/admin/backup")
    def admin_backup(x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        data = {
            "backup_version": 1,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "users": current("user_store").list_users(),
            "groups": current("group_store").list_groups(),
            "memberships": current("membership_store").list_memberships(),
            "permissions": {
                "groups": current("permission_store").list_group_permissions(),
                "users": current("permission_store").list_user_permissions(),
            },
            "settings": current("admin_settings_store").get(),
        }
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"jarvis_backup_{ts}.json"
        return Response(
            content=json.dumps(data, indent=2, default=str),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.delete("/admin/users/{user_id}/conversations")
    def admin_delete_user_conversations(user_id: str, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        user = current("user_store").get_user(user_id)
        if not user:
            raise HTTPException(404, "User not found")
        owner_key = f"user:{user_id}"
        deleted = current("chat_history").delete_all_sessions(owner_key)
        current("audit_log").write("admin_conversations_deleted", {"target_user_id": user_id, "deleted_count": deleted, "admin_user_id": x_jarvis_user_id})
        return {"ok": True, "deleted": deleted}

    @router.post("/admin/backup/restore")
    def admin_backup_restore(payload: dict, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
        ver = payload.get("backup_version")
        if ver != 1:
            raise HTTPException(400, f"Unsupported backup_version: {ver!r} — only version 1 is accepted.")

        restored: dict[str, int] = {}

        users = payload.get("users") or []
        if isinstance(users, list):
            us = current("user_store")
            us.data["users"] = {u["id"]: u for u in users if isinstance(u, dict) and "id" in u}
            us._save()
            restored["users"] = len(us.data["users"])

        groups = payload.get("groups") or []
        if isinstance(groups, list):
            gs = current("group_store")
            gs.data["groups"] = {g["id"]: g for g in groups if isinstance(g, dict) and "id" in g}
            gs._save()
            restored["groups"] = len(gs.data["groups"])

        memberships = payload.get("memberships") or []
        if isinstance(memberships, list):
            ms = current("membership_store")
            ms.data["memberships"] = [m for m in memberships if isinstance(m, dict)]
            ms._save()
            restored["memberships"] = len(ms.data["memberships"])

        perms = payload.get("permissions") or {}
        if isinstance(perms, dict):
            ps = current("permission_store")
            if "groups" in perms:
                ps.data["group_permissions"] = perms["groups"]
            if "users" in perms:
                ps.data["user_permissions"] = perms["users"]
            ps._save()
            restored["permissions"] = len(perms.get("groups", {})) + len(perms.get("users", {}))

        settings = payload.get("settings")
        if isinstance(settings, dict):
            current("admin_settings_store").update(settings)
            restored["settings"] = 1

        current("audit_log").write("admin_backup_restored", {"restored": restored, "admin_user_id": x_jarvis_user_id})
        return {"ok": True, "restored": restored}

    return router
