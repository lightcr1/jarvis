from __future__ import annotations

import json
import os
from pathlib import Path
import time
import uuid


class GroupStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_GROUP_STORE_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/groups.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"groups": {}}

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

    def list_groups(self) -> list[dict]:
        groups = list(self.data.get("groups", {}).values())
        groups.sort(key=lambda g: g.get("created_at", 0), reverse=True)
        return groups

    def get_group(self, group_id: str) -> dict | None:
        return self.data.get("groups", {}).get(group_id)

    def _group_name_exists(self, name: str, *, exclude_group_id: str | None = None) -> bool:
        normalized = (name or "").strip().lower()
        for gid, group in self.data.get("groups", {}).items():
            if exclude_group_id and gid == exclude_group_id:
                continue
            if (group.get("name") or "").strip().lower() == normalized:
                return True
        return False

    def create_group(self, name: str, description: str = "") -> dict:
        now = int(time.time())
        gid = f"grp-{uuid.uuid4().hex[:12]}"
        name_clean = (name or "").strip() or gid
        if self._group_name_exists(name_clean):
            raise ValueError("group name already exists")
        item = {
            "id": gid,
            "name": name_clean,
            "description": (description or "").strip(),
            "created_at": now,
            "updated_at": now,
        }
        self.data.setdefault("groups", {})[gid] = item
        self._save()
        return item

    def update_group(self, group_id: str, name: str | None = None, description: str | None = None) -> dict | None:
        group = self.get_group(group_id)
        if not group:
            return None
        if name is not None:
            candidate = name.strip() or group["name"]
            if self._group_name_exists(candidate, exclude_group_id=group_id):
                raise ValueError("group name already exists")
            group["name"] = candidate
        if description is not None:
            group["description"] = description.strip()
        group["updated_at"] = int(time.time())
        self.data.setdefault("groups", {})[group_id] = group
        self._save()
        return group

    def delete_group(self, group_id: str) -> bool:
        groups = self.data.setdefault("groups", {})
        if group_id not in groups:
            return False
        groups.pop(group_id, None)
        self._save()
        return True
