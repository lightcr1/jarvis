from __future__ import annotations

import json
import os
import time
from pathlib import Path


class TaskStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_TASKS_STORE_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/tasks.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"tasks": [], "updated_at": 0}

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            merged = {**self._empty(), **content}
            if not isinstance(merged.get("tasks"), list):
                merged["tasks"] = []
            return merged
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        self.data["updated_at"] = int(time.time())
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_tasks(self, owner_user_id: str) -> list[dict]:
        return [dict(item) for item in self.data.get("tasks", []) if item.get("owner_user_id") == owner_user_id]

    def list_all_tasks(self) -> list[dict]:
        return [dict(item) for item in self.data.get("tasks", [])]

    def get_task(self, task_id: str) -> dict | None:
        for item in self.data.get("tasks", []):
            if item.get("id") == task_id:
                return dict(item)
        return None

    def add_task(self, task: dict) -> dict:
        self.data.setdefault("tasks", []).append(task)
        self._save()
        return task

    def update_task(self, task_id: str, patch: dict) -> dict | None:
        tasks = self.data.setdefault("tasks", [])
        for idx, item in enumerate(tasks):
            if item.get("id") != task_id:
                continue
            updated = {**item, **patch}
            tasks[idx] = updated
            self._save()
            return updated
        return None

    def complete_task(self, task_id: str) -> dict | None:
        return self.update_task(task_id, {"status": "done", "updated_at": int(time.time())})

    def delete_task(self, task_id: str) -> bool:
        tasks = self.data.setdefault("tasks", [])
        for idx, item in enumerate(tasks):
            if item.get("id") == task_id:
                tasks.pop(idx)
                self._save()
                return True
        return False
