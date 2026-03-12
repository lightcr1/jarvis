from __future__ import annotations

import json
import os
from pathlib import Path
import time


class MembershipStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_MEMBERSHIP_STORE_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/memberships.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"memberships": []}

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            merged = {**self._empty(), **content}
            if not isinstance(merged.get("memberships"), list):
                merged["memberships"] = []
            return merged
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_memberships(self) -> list[dict]:
        return list(self.data.get("memberships", []))

    def list_user_groups(self, user_id: str) -> list[str]:
        return [m["group_id"] for m in self.data.get("memberships", []) if m.get("user_id") == user_id]

    def add_membership(self, user_id: str, group_id: str) -> dict:
        now = int(time.time())
        memberships = self.data.setdefault("memberships", [])
        for item in memberships:
            if item.get("user_id") == user_id and item.get("group_id") == group_id:
                raise ValueError("membership already exists")
        entry = {"user_id": user_id, "group_id": group_id, "created_at": now}
        memberships.append(entry)
        self._save()
        return entry

    def remove_membership(self, user_id: str, group_id: str) -> bool:
        memberships = self.data.setdefault("memberships", [])
        before = len(memberships)
        memberships[:] = [m for m in memberships if not (m.get("user_id") == user_id and m.get("group_id") == group_id)]
        if len(memberships) == before:
            return False
        self._save()
        return True

    def remove_user_memberships(self, user_id: str) -> int:
        memberships = self.data.setdefault("memberships", [])
        before = len(memberships)
        memberships[:] = [m for m in memberships if m.get("user_id") != user_id]
        removed = before - len(memberships)
        if removed > 0:
            self._save()
        return removed

    def remove_group_memberships(self, group_id: str) -> int:
        memberships = self.data.setdefault("memberships", [])
        before = len(memberships)
        memberships[:] = [m for m in memberships if m.get("group_id") != group_id]
        removed = before - len(memberships)
        if removed > 0:
            self._save()
        return removed
