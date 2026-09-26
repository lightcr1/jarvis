"""Speicher fuer TOTP-Geheimnisse je Benutzer (2. Faktor)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import totp


class TotpStore:
    def __init__(self, path: str | Path | None = None) -> None:
        if path is not None:
            self.path = Path(path)
        elif os.getenv("JARVIS_TOTP_STORE_PATH"):
            self.path = Path(os.getenv("JARVIS_TOTP_STORE_PATH"))
        elif os.getenv("JARVIS_USER_STORE_PATH"):
            self.path = Path(os.getenv("JARVIS_USER_STORE_PATH")).resolve().parent / "admin_2fa.json"
        else:
            self.path = Path("/var/lib/jarvis/admin_2fa.json")
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

    def get(self, user_id: str) -> dict | None:
        entry = self.data.get("users", {}).get(user_id)
        return entry if isinstance(entry, dict) else None

    def enabled(self, user_id: str) -> bool:
        entry = self.get(user_id)
        return bool(entry and entry.get("enabled") and entry.get("secret"))

    def start_enrollment(self, user_id: str) -> str:
        secret = totp.generate_secret()
        self.data.setdefault("users", {})[user_id] = {
            "secret": secret, "enabled": False, "created_at": int(time.time())}
        self._save()
        return secret

    def activate(self, user_id: str, code: str) -> bool:
        entry = self.get(user_id)
        if not entry or not entry.get("secret"):
            return False
        if not totp.verify(entry["secret"], code):
            return False
        entry["enabled"] = True
        entry["activated_at"] = int(time.time())
        self._save()
        return True

    def verify(self, user_id: str, code: str) -> bool:
        entry = self.get(user_id)
        return bool(entry and entry.get("secret") and totp.verify(entry["secret"], code))

    def disable(self, user_id: str, code: str | None = None) -> bool:
        if not self.verify(user_id, code or ""):
            return False
        self.data.get("users", {}).pop(user_id, None)
        self._save()
        return True
