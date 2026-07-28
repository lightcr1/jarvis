from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path


class EmailMessageStore:
    """Metadata-only cache (subject/sender/date/read/summary) — message bodies are
    never persisted at rest, only fetched live from IMAP on demand.
    """

    def __init__(self) -> None:
        configured = os.getenv("JARVIS_EMAIL_STORE_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/email_messages.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"messages": [], "updated_at": 0}

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            merged = {**self._empty(), **content}
            if not isinstance(merged.get("messages"), list):
                merged["messages"] = []
            return merged
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        self.data["updated_at"] = int(time.time())
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_messages(self, user_id: str, folder: str | None = None, unread_only: bool = False) -> list[dict]:
        items = [dict(m) for m in self.data.get("messages", []) if m.get("user_id") == user_id]
        if folder:
            items = [m for m in items if m.get("folder") == folder]
        if unread_only:
            items = [m for m in items if not m.get("read")]
        items.sort(key=lambda m: m.get("date", 0), reverse=True)
        return items

    def get_message(self, message_id: str) -> dict | None:
        for item in self.data.get("messages", []):
            if item.get("id") == message_id:
                return dict(item)
        return None

    def upsert_messages(self, user_id: str, folder: str, fetched: list[dict]) -> list[dict]:
        messages = self.data.setdefault("messages", [])
        by_uid = {(m.get("user_id"), m.get("folder"), m.get("uid")): i for i, m in enumerate(messages)}
        now = int(time.time())
        result = []
        for raw in fetched:
            key = (user_id, folder, raw["uid"])
            if key in by_uid:
                idx = by_uid[key]
                messages[idx] = {**messages[idx], "subject": raw["subject"], "sender": raw["sender"], "date": raw["date"], "read": raw["read"], "synced_at": now}
                result.append(messages[idx])
            else:
                entry = {
                    "id": f"mail-{uuid.uuid4().hex[:12]}",
                    "user_id": user_id,
                    "uid": raw["uid"],
                    "folder": folder,
                    "subject": raw["subject"],
                    "sender": raw["sender"],
                    "date": raw["date"],
                    "read": raw["read"],
                    "summary": None,
                    "synced_at": now,
                }
                messages.append(entry)
                result.append(entry)
        self._save()
        return result

    def set_read(self, message_id: str, read: bool = True) -> dict | None:
        return self._patch(message_id, {"read": read})

    def set_summary(self, message_id: str, summary: str) -> dict | None:
        return self._patch(message_id, {"summary": summary})

    def _patch(self, message_id: str, patch: dict) -> dict | None:
        messages = self.data.setdefault("messages", [])
        for idx, item in enumerate(messages):
            if item.get("id") != message_id:
                continue
            messages[idx] = {**item, **patch}
            self._save()
            return messages[idx]
        return None


class EmailDraftStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_EMAIL_DRAFTS_STORE_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/email_drafts.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"drafts": [], "updated_at": 0}

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            merged = {**self._empty(), **content}
            if not isinstance(merged.get("drafts"), list):
                merged["drafts"] = []
            return merged
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        self.data["updated_at"] = int(time.time())
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_draft(self, draft: dict) -> dict:
        draft = {**draft, "id": draft.get("id") or f"draft-{uuid.uuid4().hex[:12]}"}
        self.data.setdefault("drafts", []).append(draft)
        self._save()
        return draft

    def get_draft(self, draft_id: str) -> dict | None:
        for item in self.data.get("drafts", []):
            if item.get("id") == draft_id:
                return dict(item)
        return None

    def list_drafts(self, user_id: str, status: str | None = None) -> list[dict]:
        items = [dict(d) for d in self.data.get("drafts", []) if d.get("user_id") == user_id]
        if status:
            items = [d for d in items if d.get("status") == status]
        items.sort(key=lambda d: d.get("created_at", 0), reverse=True)
        return items

    def update_draft(self, draft_id: str, patch: dict) -> dict | None:
        drafts = self.data.setdefault("drafts", [])
        for idx, item in enumerate(drafts):
            if item.get("id") != draft_id:
                continue
            updated = {**item, **patch}
            drafts[idx] = updated
            self._save()
            return updated
        return None
