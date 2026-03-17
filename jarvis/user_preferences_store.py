from __future__ import annotations

import json
import os
from pathlib import Path
import time


DEFAULT_PREFERENCES = {
    "display_name": "",
    "accent_color": "cyan",
    "auto_play_voice": True,
    "compact_mode": False,
    "orb_detail": "high",
}


class UserPreferencesStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_USER_PREFERENCES_PATH")
        if configured:
            self.path = Path(configured)
        else:
            user_store_path = os.getenv("JARVIS_USER_STORE_PATH")
            if user_store_path:
                self.path = Path(user_store_path).resolve().parent / "user_preferences.json"
            else:
                self.path = Path("/var/lib/jarvis/user_preferences.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"preferences": {}}

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

    def get(self, user_id: str) -> dict:
        stored = self.data.get("preferences", {}).get(user_id, {})
        return {**DEFAULT_PREFERENCES, **stored}

    def update(self, user_id: str, payload: dict) -> dict:
        current = self.get(user_id)
        merged = {
            **current,
            "display_name": str(payload.get("display_name", current["display_name"])).strip(),
            "accent_color": str(payload.get("accent_color", current["accent_color"])).strip() or current["accent_color"],
            "auto_play_voice": bool(payload.get("auto_play_voice", current["auto_play_voice"])),
            "compact_mode": bool(payload.get("compact_mode", current["compact_mode"])),
            "orb_detail": str(payload.get("orb_detail", current["orb_detail"])).strip() or current["orb_detail"],
            "updated_at": int(time.time()),
        }
        self.data.setdefault("preferences", {})[user_id] = merged
        self._save()
        return merged

    def delete(self, user_id: str) -> bool:
        removed = self.data.setdefault("preferences", {}).pop(user_id, None)
        if removed is not None:
            self._save()
            return True
        return False
