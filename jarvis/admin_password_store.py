from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import time


class AdminPasswordStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_ADMIN_PASSWORD_STORE_PATH")
        if configured:
            self.path = Path(configured)
        else:
            user_store_path = os.getenv("JARVIS_USER_STORE_PATH")
            if user_store_path:
                self.path = Path(user_store_path).resolve().parent / "admin_passwords.json"
            else:
                self.path = Path("/var/lib/jarvis/admin_passwords.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"credentials": {}}

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

    def has_password(self, user_id: str) -> bool:
        return user_id in self.data.get("credentials", {})

    @staticmethod
    def hash_password(password: str, *, rounds: int = 120_000) -> dict:
        salt = secrets.token_bytes(16)
        derived = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt, rounds)
        return {
            "salt": base64.b64encode(salt).decode("ascii"),
            "hash": base64.b64encode(derived).decode("ascii"),
            "rounds": rounds,
            "updated_at": int(time.time()),
        }

    def set_record(self, user_id: str, record: dict) -> None:
        entry = {**record, "updated_at": int(time.time())}
        self.data.setdefault("credentials", {})[user_id] = entry
        self._save()

    def set_password(self, user_id: str, password: str, *, rounds: int = 120_000) -> None:
        record = self.hash_password(password, rounds=rounds)
        self.set_record(user_id, record)

    def verify_password(self, user_id: str, password: str) -> bool:
        record = self.data.get("credentials", {}).get(user_id)
        if not record:
            return False
        try:
            salt = base64.b64decode(record["salt"])
            expected = base64.b64decode(record["hash"])
            rounds = int(record.get("rounds", 120_000))
        except (KeyError, ValueError, TypeError):
            return False
        derived = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt, rounds)
        return hmac.compare_digest(derived, expected)

    def delete_password(self, user_id: str) -> bool:
        removed = self.data.setdefault("credentials", {}).pop(user_id, None)
        if removed is not None:
            self._save()
            return True
        return False
