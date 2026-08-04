from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from pathlib import Path


def _hash_password(password: str, *, rounds: int = 120_000) -> dict:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return {
        "salt": base64.b64encode(salt).decode("ascii"),
        "hash": base64.b64encode(derived).decode("ascii"),
        "rounds": rounds,
    }


def _verify_password(password_hash: dict, password: str) -> bool:
    try:
        salt = base64.b64decode(password_hash["salt"])
        expected = base64.b64decode(password_hash["hash"])
        rounds = int(password_hash.get("rounds", 120_000))
    except (KeyError, ValueError, TypeError):
        return False
    derived = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt, rounds)
    return hmac.compare_digest(derived, expected)


class FileLinkShareStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_FILES_LINK_SHARE_STORE_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/files_link_shares.json")
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

    def list_shares_for_file(self, file_id: str) -> list[dict]:
        return [dict(item) for item in self.data.get("shares", []) if item.get("file_id") == file_id]

    def get_share(self, share_id: str) -> dict | None:
        for item in self.data.get("shares", []):
            if item.get("id") == share_id:
                return dict(item)
        return None

    def get_by_token(self, token: str) -> dict | None:
        for item in self.data.get("shares", []):
            if item.get("token") == token:
                return dict(item)
        return None

    def create_share(
        self,
        file_id: str,
        created_by: str,
        *,
        expires_at: int | None = None,
        password: str | None = None,
    ) -> dict:
        shares = self.data.setdefault("shares", [])
        token = secrets.token_urlsafe(24)
        while any(item.get("token") == token for item in shares):
            token = secrets.token_urlsafe(24)
        share = {
            "id": f"lshare-{uuid.uuid4().hex[:12]}",
            "file_id": file_id,
            "token": token,
            "created_by": created_by,
            "created_at": int(time.time()),
            "expires_at": expires_at,
            "password_hash": _hash_password(password) if password else None,
            "download_count": 0,
        }
        shares.append(share)
        self._save()
        return share

    def record_download(self, share_id: str) -> None:
        shares = self.data.setdefault("shares", [])
        for idx, item in enumerate(shares):
            if item.get("id") == share_id:
                shares[idx] = {**item, "download_count": int(item.get("download_count") or 0) + 1}
                self._save()
                return

    def remove_share(self, share_id: str) -> bool:
        shares = self.data.setdefault("shares", [])
        for idx, item in enumerate(shares):
            if item.get("id") == share_id:
                shares.pop(idx)
                self._save()
                return True
        return False

    def remove_shares_for_file(self, file_id: str) -> int:
        shares = self.data.setdefault("shares", [])
        remaining = []
        removed = 0
        for item in shares:
            if item.get("file_id") == file_id:
                removed += 1
            else:
                remaining.append(item)
        if removed:
            self.data["shares"] = remaining
            self._save()
        return removed

    @staticmethod
    def verify_password(share: dict, password: str | None) -> bool:
        password_hash = share.get("password_hash")
        if not password_hash:
            return True
        return _verify_password(password_hash, password or "")

    @staticmethod
    def is_expired(share: dict) -> bool:
        expires_at = share.get("expires_at")
        return bool(expires_at) and int(expires_at) < int(time.time())
