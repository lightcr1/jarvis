from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path


class FolderShareStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_FILES_SHARE_STORE_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/files_shares.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"shares": [], "updated_at": 0}

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            merged = {**self._empty(), **content}
            if not isinstance(merged.get("shares"), list):
                merged["shares"] = []
            return merged
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        self.data["updated_at"] = int(time.time())
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_shares_for_folder(self, folder_id: str) -> list[dict]:
        return [dict(item) for item in self.data.get("shares", []) if item.get("folder_id") == folder_id]

    def list_shares_for_group(self, group_id: str) -> list[dict]:
        return [dict(item) for item in self.data.get("shares", []) if item.get("group_id") == group_id]

    def get_share(self, share_id: str) -> dict | None:
        for item in self.data.get("shares", []):
            if item.get("id") == share_id:
                return dict(item)
        return None

    def add_share(self, folder_id: str, group_id: str, permission: str, created_by: str) -> dict:
        for item in self.data.get("shares", []):
            if item.get("folder_id") == folder_id and item.get("group_id") == group_id:
                raise ValueError("this folder is already shared with this group")
        share = {
            "id": f"share-{uuid.uuid4().hex[:12]}",
            "folder_id": folder_id,
            "group_id": group_id,
            "permission": permission,
            "created_by": created_by,
            "created_at": int(time.time()),
        }
        self.data.setdefault("shares", []).append(share)
        self._save()
        return share

    def update_share_permission(self, share_id: str, permission: str) -> dict | None:
        shares = self.data.setdefault("shares", [])
        for idx, item in enumerate(shares):
            if item.get("id") != share_id:
                continue
            updated = {**item, "permission": permission}
            shares[idx] = updated
            self._save()
            return updated
        return None

    def remove_share(self, share_id: str) -> bool:
        shares = self.data.setdefault("shares", [])
        for idx, item in enumerate(shares):
            if item.get("id") == share_id:
                shares.pop(idx)
                self._save()
                return True
        return False

    def remove_shares_for_folder(self, folder_id: str) -> int:
        shares = self.data.setdefault("shares", [])
        remaining = []
        removed = 0
        for item in shares:
            if item.get("folder_id") == folder_id:
                removed += 1
            else:
                remaining.append(item)
        if removed:
            self.data["shares"] = remaining
            self._save()
        return removed
