from __future__ import annotations

import json
import os
from pathlib import Path


KNOWN_PERMISSIONS = {
    "voice.use",
    "assistant.chat",
    "devices.read",
    "devices.manage",
    "calendar.read",
    "calendar.write",
    "email.read",
    "email.write",
    "actions.write.execute",
    "actions.dangerous.execute",
    "actions.dangerous.approve",
    "users.manage",
    "groups.manage",
    "permissions.manage",
    "audit.read",
    "settings.manage",
    "emergency_stop.trigger",
}


class PermissionStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_PERMISSION_STORE_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/permissions.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"group_permissions": {}, "user_permissions": {}}

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            merged = {**self._empty(), **content}
            if not isinstance(merged.get("group_permissions"), dict):
                merged["group_permissions"] = {}
            if not isinstance(merged.get("user_permissions"), dict):
                merged["user_permissions"] = {}
            return merged
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def invalid_permissions(permissions: list[str]) -> list[str]:
        invalid = []
        for item in permissions:
            p = (item or "").strip()
            if p and p not in KNOWN_PERMISSIONS:
                invalid.append(p)
        return invalid

    @staticmethod
    def _normalize_permissions(permissions: list[str]) -> list[str]:
        seen = set()
        out = []
        for item in permissions:
            p = (item or "").strip()
            if not p or p in seen:
                continue
            seen.add(p)
            out.append(p)
        return out

    def list_group_permissions(self) -> dict[str, list[str]]:
        return dict(self.data.get("group_permissions", {}))

    def list_user_permissions(self) -> dict[str, list[str]]:
        return dict(self.data.get("user_permissions", {}))

    def set_group_permissions(self, group_id: str, permissions: list[str]) -> list[str]:
        invalid = self.invalid_permissions(permissions)
        if invalid:
            raise ValueError(f"invalid permissions: {', '.join(invalid)}")
        normalized = self._normalize_permissions(permissions)
        self.data.setdefault("group_permissions", {})[group_id] = normalized
        self._save()
        return normalized

    def set_user_permissions(self, user_id: str, permissions: list[str]) -> list[str]:
        invalid = self.invalid_permissions(permissions)
        if invalid:
            raise ValueError(f"invalid permissions: {', '.join(invalid)}")
        normalized = self._normalize_permissions(permissions)
        self.data.setdefault("user_permissions", {})[user_id] = normalized
        self._save()
        return normalized

    def clear_group_permissions(self, group_id: str) -> bool:
        bucket = self.data.setdefault("group_permissions", {})
        if group_id not in bucket:
            return False
        bucket.pop(group_id, None)
        self._save()
        return True

    def clear_user_permissions(self, user_id: str) -> bool:
        bucket = self.data.setdefault("user_permissions", {})
        if user_id not in bucket:
            return False
        bucket.pop(user_id, None)
        self._save()
        return True
