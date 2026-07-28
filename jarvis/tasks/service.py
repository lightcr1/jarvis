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
    def __init__(self, *, store, user_store, membership_store, permission_store, resolve_effective_permissions, normalize_role, audit_log=None) -> None:
        self.store = store
        self.user_store = user_store
        self.membership_store = membership_store
        self.permission_store = permission_store
        self.resolve_effective_permissions = resolve_effective_permissions
        self.normalize_role = normalize_role
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

    def list_tasks(self, *, user_id: str | None, role: str | None, status: str | None = None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="tasks.read")
        tasks = self.store.list_tasks(user_id or "")
        if status:
            tasks = [item for item in tasks if item.get("status") == status]
        tasks.sort(key=lambda item: item.get("created_at", 0), reverse=True)
        return {"policy": policy, "tasks": tasks}

    def get_task(self, task_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="tasks.read")
        task = self._owned_task(task_id, user_id=user_id, role=role)
        return {"policy": policy, "task": task}

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
        self._owned_task(task_id, user_id=user_id, role=role)
        patch = self._validate_task_fields(payload or {}, partial=True)
        patch["updated_at"] = int(time.time())
        updated = self.store.update_task(task_id, patch)
        self._write_audit("task_updated", actor_user_id=user_id, actor_role=role, payload={"task_id": task_id})
        return {"policy": policy, "task": updated}

    def complete_task(self, task_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="tasks.write")
        self._owned_task(task_id, user_id=user_id, role=role)
        updated = self.store.complete_task(task_id)
        self._write_audit("task_completed", actor_user_id=user_id, actor_role=role, payload={"task_id": task_id})
        return {"policy": policy, "task": updated}

    def delete_task(self, task_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="tasks.manage")
        self._owned_task(task_id, user_id=user_id, role=role)
        deleted = self.store.delete_task(task_id)
        self._write_audit("task_deleted", actor_user_id=user_id, actor_role=role, payload={"task_id": task_id})
        return {"policy": policy, "deleted": deleted}

    def set_task_steps(self, task_id: str, steps: list[str], *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="tasks.write")
        self._owned_task(task_id, user_id=user_id, role=role)
        cleaned = [str(item).strip() for item in steps if str(item).strip()]
        updated = self.store.update_task(task_id, {"steps": cleaned, "updated_at": int(time.time())})
        self._write_audit("task_breakdown_generated", actor_user_id=user_id, actor_role=role, payload={"task_id": task_id, "step_count": len(cleaned)})
        return {"policy": policy, "task": updated}

    def find_open_task_by_title(self, title_query: str, *, user_id: str | None, role: str | None) -> dict[str, object] | None:
        self.require_access(user_id=user_id, role=role, required_permission="tasks.read")
        needle = (title_query or "").strip().lower()
        if not needle:
            return None
        for task in self.store.list_tasks(user_id or ""):
            if task.get("status") != "done" and needle in str(task.get("title") or "").lower():
                return task
        return None
