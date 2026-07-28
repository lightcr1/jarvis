from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

DEFAULT_PORTS: dict[str, int] = {"rdp": 3389, "vnc": 5900}
VALID_OS_TYPES = {"windows", "linux"}
VALID_PROTOCOLS = {"rdp", "vnc"}


class WorkspaceTargetStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_WORKSPACE_STORE_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/workspace_targets.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"targets": [], "updated_at": 0}

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            merged = {**self._empty(), **content}
            if not isinstance(merged.get("targets"), list):
                merged["targets"] = []
            return merged
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        self.data["updated_at"] = int(time.time())
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_targets(self) -> list[dict]:
        return [dict(item) for item in self.data.get("targets", [])]

    def get_target(self, target_id: str) -> dict | None:
        for item in self.data.get("targets", []):
            if item.get("id") == target_id:
                return dict(item)
        return None

    def add_target(self, target: dict) -> dict:
        target = {**target, "id": target.get("id") or f"wt-{uuid.uuid4().hex[:12]}"}
        self.data.setdefault("targets", []).append(target)
        self._save()
        return target

    def update_target(self, target_id: str, patch: dict) -> dict | None:
        targets = self.data.setdefault("targets", [])
        for idx, item in enumerate(targets):
            if item.get("id") != target_id:
                continue
            updated = {**item, **patch}
            targets[idx] = updated
            self._save()
            return updated
        return None

    def delete_target(self, target_id: str) -> bool:
        targets = self.data.setdefault("targets", [])
        for idx, item in enumerate(targets):
            if item.get("id") == target_id:
                targets.pop(idx)
                self._save()
                return True
        return False
