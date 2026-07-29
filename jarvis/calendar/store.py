from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path


class CalendarEventStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_CALENDAR_STORE_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/calendar_events.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"events": [], "updated_at": 0}

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            merged = {**self._empty(), **content}
            if not isinstance(merged.get("events"), list):
                merged["events"] = []
            return merged
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        self.data["updated_at"] = int(time.time())
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_events(self, user_id: str, start: int | None = None, end: int | None = None) -> list[dict]:
        items = [dict(item) for item in self.data.get("events", []) if item.get("user_id") == user_id]
        if start is not None:
            items = [item for item in items if item.get("end", item.get("start", 0)) >= start]
        if end is not None:
            items = [item for item in items if item.get("start", 0) <= end]
        items.sort(key=lambda item: item.get("start", 0))
        return items

    def get_event(self, event_id: str) -> dict | None:
        for item in self.data.get("events", []):
            if item.get("id") == event_id:
                return dict(item)
        return None

    def add_event(self, event: dict) -> dict:
        event = {**event, "id": event.get("id") or f"cal-{uuid.uuid4().hex[:12]}"}
        self.data.setdefault("events", []).append(event)
        self._save()
        return event

    def update_event(self, event_id: str, patch: dict) -> dict | None:
        events = self.data.setdefault("events", [])
        for idx, item in enumerate(events):
            if item.get("id") != event_id:
                continue
            updated = {**item, **patch}
            events[idx] = updated
            self._save()
            return updated
        return None

    def delete_event(self, event_id: str) -> bool:
        events = self.data.setdefault("events", [])
        for idx, item in enumerate(events):
            if item.get("id") == event_id:
                events.pop(idx)
                self._save()
                return True
        return False

    def replace_synced_events(self, user_id: str, synced: list[dict]) -> list[dict]:
        """Replaces all previously-synced ("caldav"-sourced) events for `user_id` with a
        fresh remote snapshot, while leaving not-yet-synced local events untouched.
        """
        events = self.data.setdefault("events", [])
        kept = [e for e in events if not (e.get("user_id") == user_id and e.get("source") == "caldav")]
        now = int(time.time())
        fresh = []
        for raw in synced:
            fresh.append({
                "id": f"cal-{raw['uid']}",
                "user_id": user_id,
                "uid": raw["uid"],
                "title": raw.get("title", ""),
                "description": raw.get("description", ""),
                "location": raw.get("location", ""),
                "start": raw.get("start"),
                "end": raw.get("end"),
                "href": raw.get("href", ""),
                "etag": raw.get("etag", ""),
                "source": "caldav",
                "synced_at": now,
                "created_at": now,
                "updated_at": now,
            })
        self.data["events"] = kept + fresh
        self._save()
        return fresh

    def find_overlapping(self, user_id: str, start: int, end: int, exclude_id: str | None = None) -> list[dict]:
        conflicts = []
        for item in self.list_events(user_id):
            if item.get("id") == exclude_id:
                continue
            other_start, other_end = item.get("start", 0), item.get("end", 0)
            if other_start < end and other_end > start:
                conflicts.append(item)
        return conflicts
