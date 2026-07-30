from __future__ import annotations

import os
import time
import uuid


def _emergency_stop_active() -> bool:
    return (os.getenv("JARVIS_EMERGENCY_STOP") or "0").strip().lower() in {"1", "true", "yes", "on"}


class TaskAccessError(PermissionError):
    pass


VALID_STATUSES = {"open", "in_progress", "done"}
VALID_PRIORITIES = {"low", "medium", "high"}


class TaskService:
    def __init__(
        self,
        *,
        store,
        user_store,
        membership_store,
        permission_store,
        resolve_effective_permissions,
        normalize_role,
        share_store=None,
        group_store=None,
        audit_log=None,
    ) -> None:
        self.store = store
        self.user_store = user_store
        self.membership_store = membership_store
        self.permission_store = permission_store
        self.resolve_effective_permissions = resolve_effective_permissions
        self.normalize_role = normalize_role
        self.share_store = share_store
        self.group_store = group_store
        self.audit_log = audit_log

    def _write_audit(self, event: str, *, actor_user_id: str | None, actor_role: str | None, payload: dict | None = None) -> None:
        if not self.audit_log:
            return
        body = {
            "actor_user_id": actor_user_id,
            "actor_role": self.normalize_role(actor_role),
            **(payload or {}),
        }
        try:
            self.audit_log.write(event, body)
        except Exception:
            return

    def _effective_permissions(self, user_id: str | None, role: str | None) -> set[str]:
        return set(self.resolve_effective_permissions(self.normalize_role(role), user_id, self.membership_store, self.permission_store))

    def require_access(self, *, user_id: str | None, role: str | None, required_permission: str) -> dict[str, object]:
        normalized_role = self.normalize_role(role)
        effective = self._effective_permissions(user_id, role)
        if normalized_role != "admin" and required_permission not in effective:
            raise TaskAccessError(f"missing permission: {required_permission}")
        return {"role": normalized_role, "effective_permissions": sorted(effective)}

    def _owned_task(self, task_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        task = self.store.get_task(task_id)
        if not task:
            raise LookupError("task not found")
        if task.get("owner_user_id") != user_id and self.normalize_role(role) != "admin":
            raise LookupError("task not found")
        return task

    def _shared_access(self, task_id: str, user_group_ids: set[str]) -> str | None:
        if self.share_store is None:
            return None
        best: str | None = None
        for share in self.share_store.list_shares_for_task(task_id):
            if share.get("group_id") not in user_group_ids:
                continue
            if share.get("permission") == "write":
                best = "write"
            elif best is None and share.get("permission") == "read":
                best = "read"
        return best

    def _access_level(self, task: dict, *, user_id: str | None, role: str | None, user_group_ids: set[str]) -> str | None:
        if task.get("owner_user_id") == user_id or self.normalize_role(role) == "admin":
            return "owner"
        if task.get("assignee_user_id") == user_id:
            return "write"
        return self._shared_access(task["id"], user_group_ids)

    def _accessible_task(self, task_id: str, *, user_id: str | None, role: str | None) -> tuple[dict, str]:
        """Returns (task, access) where access is 'owner' | 'write' | 'read'.
        Raises LookupError (404, not 403 — preserves existence-hiding behavior)
        if the task doesn't exist or the caller has no access at all.
        """
        task = self.store.get_task(task_id)
        if not task:
            raise LookupError("task not found")
        user_group_ids = set(self.membership_store.list_user_groups(user_id or ""))
        access = self._access_level(task, user_id=user_id, role=role, user_group_ids=user_group_ids)
        if access is None:
            raise LookupError("task not found")
        return task, access

    def _visible_tasks(self, *, user_id: str | None, role: str | None) -> list[dict]:
        user_group_ids = set(self.membership_store.list_user_groups(user_id or ""))
        visible = []
        for task in self.store.list_all_tasks():
            access = self._access_level(task, user_id=user_id, role=role, user_group_ids=user_group_ids)
            if access is not None:
                visible.append({**task, "access": access})
        return visible

    def list_tasks(self, *, user_id: str | None, role: str | None, status: str | None = None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="tasks.read")
        tasks = self._visible_tasks(user_id=user_id, role=role)
        if status:
            tasks = [item for item in tasks if item.get("status") == status]
        tasks.sort(key=lambda item: item.get("created_at", 0), reverse=True)
        return {"policy": policy, "tasks": tasks}

    def get_task(self, task_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="tasks.read")
        task, access = self._accessible_task(task_id, user_id=user_id, role=role)
        return {"policy": policy, "task": task, "access": access}

    def _validate_task_fields(self, payload: dict[str, object], *, partial: bool) -> dict[str, object]:
        patch: dict[str, object] = {}
        if not partial or "title" in payload:
            title = str((payload or {}).get("title") or "").strip()
            if not title:
                raise ValueError("task title required")
            patch["title"] = title
        if not partial or "description" in payload:
            patch["description"] = str((payload or {}).get("description") or "").strip()
        if not partial or "status" in payload:
            status = str((payload or {}).get("status") or "open").strip().lower()
            if status not in VALID_STATUSES:
                raise ValueError("invalid task status")
            patch["status"] = status
        if not partial or "priority" in payload:
            priority = str((payload or {}).get("priority") or "medium").strip().lower()
            if priority not in VALID_PRIORITIES:
                raise ValueError("invalid task priority")
            patch["priority"] = priority
        if not partial or "due_at" in payload:
            due_at = (payload or {}).get("due_at")
            patch["due_at"] = int(due_at) if due_at is not None else None
        if not partial or "steps" in payload:
            steps = (payload or {}).get("steps")
            if steps is not None and not isinstance(steps, list):
                raise ValueError("steps must be a list of strings")
            patch["steps"] = [str(item) for item in steps] if steps else []
        if not partial or "assignee_user_id" in payload:
            assignee = (payload or {}).get("assignee_user_id") or None
            if assignee is not None and not self.user_store.get_user(assignee):
                raise ValueError("assignee not found")
            patch["assignee_user_id"] = assignee
        return patch

    def create_task(self, payload: dict[str, object], *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="tasks.write")
        fields = self._validate_task_fields(payload or {}, partial=False)
        now = int(time.time())
        task = self.store.add_task(
            {
                "id": (payload or {}).get("id") or f"task-{uuid.uuid4().hex[:12]}",
                "owner_user_id": user_id,
                **fields,
                "created_at": now,
                "updated_at": now,
            }
        )
        self._write_audit("task_created", actor_user_id=user_id, actor_role=role, payload={"task_id": task["id"], "title": task["title"]})
        return {"policy": policy, "task": task}

    def update_task(self, task_id: str, payload: dict[str, object], *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="tasks.write")
        _, access = self._accessible_task(task_id, user_id=user_id, role=role)
        if access == "read":
            raise TaskAccessError("read-only access to this task")
        if "assignee_user_id" in (payload or {}) and access != "owner":
            raise TaskAccessError("only the task owner can reassign this task")
        patch = self._validate_task_fields(payload or {}, partial=True)
        patch["updated_at"] = int(time.time())
        updated = self.store.update_task(task_id, patch)
        self._write_audit("task_updated", actor_user_id=user_id, actor_role=role, payload={"task_id": task_id})
        return {"policy": policy, "task": updated}

    def complete_task(self, task_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="tasks.write")
        _, access = self._accessible_task(task_id, user_id=user_id, role=role)
        if access == "read":
            raise TaskAccessError("read-only access to this task")
        updated = self.store.complete_task(task_id)
        self._write_audit("task_completed", actor_user_id=user_id, actor_role=role, payload={"task_id": task_id})
        return {"policy": policy, "task": updated}

    def delete_task(self, task_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="tasks.manage")
        self._owned_task(task_id, user_id=user_id, role=role)
        if self.share_store is not None:
            self.share_store.remove_shares_for_task(task_id)
        deleted = self.store.delete_task(task_id)
        self._write_audit("task_deleted", actor_user_id=user_id, actor_role=role, payload={"task_id": task_id})
        return {"policy": policy, "deleted": deleted}

    def set_task_steps(self, task_id: str, steps: list[str], *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="tasks.write")
        _, access = self._accessible_task(task_id, user_id=user_id, role=role)
        if access == "read":
            raise TaskAccessError("read-only access to this task")
        cleaned = [str(item).strip() for item in steps if str(item).strip()]
        updated = self.store.update_task(task_id, {"steps": cleaned, "updated_at": int(time.time())})
        self._write_audit("task_breakdown_generated", actor_user_id=user_id, actor_role=role, payload={"task_id": task_id, "step_count": len(cleaned)})
        return {"policy": policy, "task": updated}

    def find_open_task_by_title(self, title_query: str, *, user_id: str | None, role: str | None) -> dict[str, object] | None:
        self.require_access(user_id=user_id, role=role, required_permission="tasks.read")
        needle = (title_query or "").strip().lower()
        if not needle:
            return None
        for task in self._visible_tasks(user_id=user_id, role=role):
            if task.get("status") != "done" and needle in str(task.get("title") or "").lower():
                return task
        return None

    # ------------------------------------------------------------------
    # Assignment & sharing
    # ------------------------------------------------------------------

    def list_assignable_users(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="tasks.read")
        users = [{"id": u["id"], "username": u["username"]} for u in self.user_store.list_users() if u.get("enabled", True)]
        users.sort(key=lambda u: u["username"])
        return {"policy": policy, "users": users}

    def list_my_groups(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="tasks.read")
        groups = [{"id": g["id"], "name": g["name"]} for g in (self.group_store.list_groups() if self.group_store else [])]
        groups.sort(key=lambda g: g["name"])
        return {"policy": policy, "groups": groups}

    def share_task(self, task_id: str, group_id: str, permission: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="tasks.share")
        self._owned_task(task_id, user_id=user_id, role=role)
        if self.share_store is None:
            raise TaskAccessError("task sharing is not configured")
        if permission not in ("read", "write"):
            raise ValueError("permission must be 'read' or 'write'")
        if not self.group_store or not self.group_store.get_group(group_id):
            raise ValueError("group not found")
        share = self.share_store.add_share(task_id, group_id, permission, user_id or "")
        self._write_audit("task_shared", actor_user_id=user_id, actor_role=role, payload={"task_id": task_id, "group_id": group_id, "permission": permission})
        return {"policy": policy, "share": share}

    def unshare_task(self, share_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="tasks.share")
        if self.share_store is None:
            raise LookupError("share not found")
        share = self.share_store.get_share(share_id)
        if not share:
            raise LookupError("share not found")
        self._owned_task(share["task_id"], user_id=user_id, role=role)
        deleted = self.share_store.remove_share(share_id)
        self._write_audit("task_unshared", actor_user_id=user_id, actor_role=role, payload={"share_id": share_id, "task_id": share["task_id"]})
        return {"policy": policy, "deleted": deleted}

    def list_task_shares(self, task_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="tasks.share")
        self._owned_task(task_id, user_id=user_id, role=role)
        enriched = []
        for share in (self.share_store.list_shares_for_task(task_id) if self.share_store else []):
            group = self.group_store.get_group(share.get("group_id")) if self.group_store else None
            enriched.append({**share, "group_name": (group or {}).get("name") or "(deleted group)"})
        enriched.sort(key=lambda s: s.get("created_at", 0))
        return {"policy": policy, "shares": enriched}

    def list_shared_with_me(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="tasks.read")
        entries = []
        if self.share_store is not None:
            seen_task_ids: set[str] = set()
            for group_id in self.membership_store.list_user_groups(user_id or ""):
                for share in self.share_store.list_shares_for_group(group_id):
                    task_id = share.get("task_id")
                    if task_id in seen_task_ids:
                        continue
                    task = self.store.get_task(task_id)
                    if not task:
                        continue
                    seen_task_ids.add(task_id)
                    owner_user = self.user_store.get_user(task["owner_user_id"])
                    entries.append({"task": task, "owner_username": (owner_user or {}).get("username"), "access": share.get("permission")})
        return {"policy": policy, "shared": entries}
