"""Encrypted TOTP state with persistent, cross-process replay protection."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile
import threading
import time

from . import totp
from .secret_crypto import (
    SecretDecryptionError, SecretEncryptionUnavailable,
    decrypt_secret, encrypt_secret, encryption_available,
)


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
        self._lock = threading.RLock()
        # Migrate existing plaintext only when the owner-managed key is available.
        # Without it, enrollment/verification fail closed; enabled status is retained.
        with self._transaction():
            if encryption_available():
                changed = False
                for entry in self.data["users"].values():
                    if entry.get("secret") and not entry["secret"].startswith("fernet:v1:"):
                        entry["secret"] = encrypt_secret(entry["secret"])
                        changed = True
                if changed:
                    self._save()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"users": {}}
        # Never silently turn corrupt 2FA state into disabled 2FA.
        content = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(content, dict) or not isinstance(content.get("users"), dict):
            raise ValueError("invalid TOTP state")
        if any(not isinstance(entry, dict) for entry in content["users"].values()):
            raise ValueError("invalid TOTP user state")
        return content

    @contextmanager
    def _transaction(self):
        # A separate lock file survives atomic replacement of the state file.
        with self._lock:
            # The directory can disappear if a test/tmpdir is cleaned up while a
            # module-level store is still referenced; recreate it defensively.
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
            fd = os.open(str(self.path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                self.data = self._load()
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def _save(self) -> None:
        fd, name = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(self.data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def get(self, user_id: str) -> dict | None:
        with self._transaction():
            entry = self.data["users"].get(user_id)
            # No secret (plaintext or ciphertext) needs to leave this store.
            return {k: v for k, v in entry.items() if k != "secret"} if entry else None

    def enabled(self, user_id: str) -> bool:
        with self._transaction():
            entry = self.data["users"].get(user_id)
            # An enabled but damaged entry must still demand a second factor.
            return bool(entry and entry.get("enabled"))

    def start_enrollment(self, user_id: str) -> str:
        with self._transaction():
            if self.data["users"].get(user_id, {}).get("enabled"):
                raise ValueError("disable existing 2FA with a fresh code before reenrolling")
            secret = totp.generate_secret()
            self.data["users"][user_id] = {
                "secret": encrypt_secret(secret), "enabled": False,
                "created_at": int(time.time()), "last_counter": -1,
            }
            self._save()
            return secret

    def _consume(self, entry: dict, code: str) -> bool:
        try:
            secret = decrypt_secret(entry.get("secret") or "")
            counter = totp.matching_counter(secret, code)
            if counter is None or counter <= int(entry.get("last_counter", -1)):
                return False
        except (SecretEncryptionUnavailable, SecretDecryptionError, ValueError, TypeError):
            return False
        entry["last_counter"] = counter
        return True

    def activate(self, user_id: str, code: str) -> bool:
        with self._transaction():
            entry = self.data["users"].get(user_id)
            if not entry or entry.get("enabled") or not self._consume(entry, code):
                return False
            entry["enabled"] = True
            entry["activated_at"] = int(time.time())
            self._save()
            return True

    def verify(self, user_id: str, code: str) -> bool:
        with self._transaction():
            entry = self.data["users"].get(user_id)
            if not entry or not entry.get("enabled") or not self._consume(entry, code):
                return False
            self._save()
            return True

    def disable(self, user_id: str, code: str | None = None) -> bool:
        with self._transaction():
            entry = self.data["users"].get(user_id)
            if not entry or not entry.get("enabled") or not self._consume(entry, code or ""):
                return False
            self.data["users"].pop(user_id)
            self._save()
            return True
