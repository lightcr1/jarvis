from __future__ import annotations

import json
import os
from pathlib import Path
import time
import uuid

from .jarvis_engine import VALID_ROLES


class UserStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_USER_STORE_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/users.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"users": {}}

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            return {**self._empty(), **content}
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_users(self) -> list[dict]:
        users = list(self.data.get("users", {}).values())
        users.sort(key=lambda u: u.get("created_at", 0), reverse=True)
        return users

    def get_user(self, user_id: str) -> dict | None:
        return self.data.get("users", {}).get(user_id)

    def _username_exists(self, username: str, *, exclude_user_id: str | None = None) -> bool:
        normalized = (username or "").strip().lower()
        for uid, user in self.data.get("users", {}).items():
            if exclude_user_id and uid == exclude_user_id:
                continue
            if (user.get("username") or "").strip().lower() == normalized:
                return True
        return False

    def create_user(self, username: str, role: str = "standard_user", enabled: bool = True) -> dict:
        now = int(time.time())
        uid = f"usr-{uuid.uuid4().hex[:12]}"
        username_clean = (username or "").strip() or uid
        if self._username_exists(username_clean):
            raise ValueError("username already exists")
        role_clean = (role or "standard_user").strip().lower()
        if role_clean not in VALID_ROLES:
            raise ValueError("invalid role")
        item = {
            "id": uid,
            "username": username_clean,
            "role": role_clean,
            "enabled": bool(enabled),
            "created_at": now,
            "updated_at": now,
        }
        self.data.setdefault("users", {})[uid] = item
        self._save()
        return item

    def update_user(self, user_id: str, role: str | None = None, enabled: bool | None = None) -> dict | None:
        user = self.get_user(user_id)
        if not user:
            return None
        if role is not None:
            role_clean = role.strip().lower()
            if role_clean not in VALID_ROLES:
                raise ValueError("invalid role")
            user["role"] = role_clean
        if enabled is not None:
            user["enabled"] = bool(enabled)
        user["updated_at"] = int(time.time())
        self.data.setdefault("users", {})[user_id] = user
        self._save()
        return user

    def delete_user(self, user_id: str) -> bool:
        users = self.data.setdefault("users", {})
        if user_id not in users:
            return False
        users.pop(user_id, None)
        self._save()
        return True

    def enabled_admin_count(self) -> int:
        count = 0
        for user in self.data.get("users", {}).values():
            if (user.get("role") == "admin") and bool(user.get("enabled", False)):
                count += 1
        return count
