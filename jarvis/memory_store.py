from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path


def _default_memory_path() -> Path:
    configured = os.getenv("JARVIS_MEMORY_PATH")
    if configured:
        return Path(configured)
    preferred = Path("/var/lib/jarvis/memory.json")
    try:
        preferred.parent.mkdir(parents=True, exist_ok=True)
        with preferred.open("a", encoding="utf-8"):
            pass
        return preferred
    except OSError:
        import tempfile
        fallback = Path(tempfile.gettempdir()) / "jarvis" / "memory.json"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback


class MemoryStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _default_memory_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._data = self._load()

    def _empty(self) -> dict:
        return {"schema_version": 1, "users": {}}

    def _load(self) -> dict:
        if not self._path.exists():
            return self._empty()
        try:
            content = json.loads(self._path.read_text(encoding="utf-8"))
            base = self._empty()
            base.update(content)
            return base
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)

    def _user(self, user_id: str) -> dict:
        users = self._data.setdefault("users", {})
        if user_id not in users:
            users[user_id] = {"notes": [], "aliases": {}}
        return users[user_id]

    def get_notes(self, user_id: str) -> list[dict]:
        with self._lock:
            return list(self._user(user_id).get("notes") or [])

    def add_note(self, user_id: str, text: str) -> dict:
        text = (text or "").strip()
        if not text:
            raise ValueError("note text cannot be empty")
        note = {"id": uuid.uuid4().hex, "text": text, "created_at": int(time.time())}
        with self._lock:
            self._user(user_id).setdefault("notes", []).append(note)
            self._save()
        return note

    def delete_note(self, user_id: str, note_id: str) -> bool:
        with self._lock:
            notes = self._user(user_id).get("notes") or []
            before = len(notes)
            self._user(user_id)["notes"] = [n for n in notes if n.get("id") != note_id]
            changed = len(self._user(user_id)["notes"]) < before
            if changed:
                self._save()
        return changed

    def get_aliases(self, user_id: str) -> dict[str, dict]:
        with self._lock:
            return dict(self._user(user_id).get("aliases") or {})

    def set_alias(self, user_id: str, alias: str, target: str) -> dict:
        alias = (alias or "").strip()
        target = (target or "").strip()
        if not alias or not target:
            raise ValueError("alias and target cannot be empty")
        entry = {"target": target, "created_at": int(time.time())}
        with self._lock:
            self._user(user_id).setdefault("aliases", {})[alias] = entry
            self._save()
        return entry

    def delete_alias(self, user_id: str, alias: str) -> bool:
        with self._lock:
            aliases = self._user(user_id).get("aliases") or {}
            if alias not in aliases:
                return False
            del aliases[alias]
            self._save()
        return True

    def clear_user(self, user_id: str) -> None:
        with self._lock:
            self._data.setdefault("users", {})[user_id] = {"notes": [], "aliases": {}}
            self._save()
