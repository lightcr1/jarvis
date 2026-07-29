import json
import os
import time
from pathlib import Path

from .secret_crypto import (
    decrypt_secret,
    encrypt_secret,
    encryption_available,
    SecretDecryptionError,
    SecretEncryptionUnavailable,
)

_MIGRATABLE_INTEGRATIONS = {"calendar", "email"}


class IntegrationCredentialStore:
    """Per-user encrypted multi-field credential storage, shared across integrations
    that need more than one secret field (CalDAV URL/user/pass, IMAP+SMTP host/port/
    user/pass) — unlike ByokKeyStore's single-string-per-provider shape.

    Schema: {"credentials": {key: {ciphertext, field_names, user_id, integration,
    account_id, label, is_primary, created_at, updated_at}}}

    `key` is `f"{user_id}:{integration}"` for the "default" account (the exact
    legacy single-account format, never rewritten — this store is also used by
    jarvis/workspace/service.py with an integration name that already contains a
    colon, e.g. "workspace:{target_id}", so a key-rewriting migration cannot safely
    tell "legacy 2-part key" apart from "workspace's own key shape"; keeping
    "default" pinned to the legacy format sidesteps that entirely) or
    `f"{user_id}:{integration}:{account_id}"` for any additional account.

    `ciphertext` is a Fernet-encrypted JSON blob of the raw field dict. Only
    `field_names` (never values) are ever returned to a caller that isn't decrypting
    server-side. This store is excluded from /admin/backup — users must re-enter
    credentials after a restore, same as jarvis/byok_store.py.
    """

    def __init__(self) -> None:
        path_str = os.getenv("JARVIS_INTEGRATION_CREDENTIALS_PATH") or ""
        if path_str:
            self.path = Path(path_str)
        else:
            base = Path(os.getenv("JARVIS_USER_STORE_PATH") or "/var/lib/jarvis")
            self.path = base.parent / "integration_credentials.json" if base.suffix else base / "integration_credentials.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"credentials": {}}

    @staticmethod
    def _backfill_legacy_entries(data: dict) -> bool:
        changed = False
        for key, entry in data.get("credentials", {}).items():
            if not isinstance(entry, dict) or "account_id" in entry or ":" not in key:
                continue
            user_id, integration = key.rsplit(":", 1)
            if integration not in _MIGRATABLE_INTEGRATIONS:
                continue
            entry["user_id"] = user_id
            entry["integration"] = integration
            entry["account_id"] = "default"
            entry["is_primary"] = True
            entry.setdefault("label", "Primary")
            changed = True
        return changed

    def _load(self) -> dict:
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            data = {**self._empty(), **content}
        except (OSError, json.JSONDecodeError):
            return self._empty()
        if self._backfill_legacy_entries(data):
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _key(user_id: str, integration: str, account_id: str = "default") -> str:
        if account_id == "default":
            return f"{user_id}:{integration}"
        return f"{user_id}:{integration}:{account_id}"

    @staticmethod
    def _default_label(account_id: str) -> str:
        return "Primary" if account_id == "default" else f"Account {account_id[:6]}"

    def _has_primary(self, user_id: str, integration: str) -> bool:
        return any(
            e.get("is_primary")
            for e in self.data["credentials"].values()
            if e.get("user_id") == user_id and e.get("integration") == integration
        )

    def set_credentials(
        self,
        user_id: str,
        integration: str,
        fields: dict[str, str],
        *,
        account_id: str = "default",
        label: str | None = None,
    ) -> dict:
        if not encryption_available():
            raise SecretEncryptionUnavailable(
                "JARVIS_SECRET_KEY is not configured — integration credential storage is unavailable."
            )
        now = int(time.time())
        ciphertext = encrypt_secret(json.dumps(fields, ensure_ascii=False))
        key = self._key(user_id, integration, account_id)
        existing = self.data["credentials"].get(key, {})
        is_primary = existing.get("is_primary")
        if is_primary is None:
            is_primary = not self._has_primary(user_id, integration)
        entry = {
            "user_id": user_id,
            "integration": integration,
            "account_id": account_id,
            "ciphertext": ciphertext,
            "field_names": sorted(fields.keys()),
            "label": label if label is not None else (existing.get("label") or self._default_label(account_id)),
            "is_primary": is_primary,
            "created_at": existing.get("created_at", now),
            "updated_at": now,
        }
        self.data["credentials"][key] = entry
        self._save()
        return {"integration": integration, "account_id": account_id, "field_names": entry["field_names"], "updated_at": now}

    def get_credentials(self, user_id: str, integration: str, account_id: str = "default") -> dict[str, str] | None:
        """Server-internal only. Never expose raw fields via an HTTP endpoint."""
        entry = self.data["credentials"].get(self._key(user_id, integration, account_id))
        if not entry:
            return None
        try:
            return json.loads(decrypt_secret(entry["ciphertext"]))
        except (SecretDecryptionError, SecretEncryptionUnavailable, json.JSONDecodeError):
            return None

    def has_credentials(self, user_id: str, integration: str, account_id: str = "default") -> bool:
        return self._key(user_id, integration, account_id) in self.data["credentials"]

    def status(self, user_id: str, integration: str, account_id: str = "default") -> dict:
        entry = self.data["credentials"].get(self._key(user_id, integration, account_id))
        if not entry:
            return {"configured": False, "field_names": [], "updated_at": None}
        return {"configured": True, "field_names": entry.get("field_names", []), "updated_at": entry.get("updated_at")}

    def delete_credentials(self, user_id: str, integration: str, account_id: str = "default") -> bool:
        key = self._key(user_id, integration, account_id)
        if key not in self.data["credentials"]:
            return False
        del self.data["credentials"][key]
        self._save()
        return True

    def list_accounts(self, user_id: str, integration: str) -> list[dict]:
        entries = [
            e
            for e in self.data["credentials"].values()
            if e.get("user_id") == user_id and e.get("integration") == integration
        ]
        entries.sort(key=lambda e: (0 if e.get("is_primary") else 1, e.get("created_at", 0)))
        return [
            {
                "account_id": e["account_id"],
                "label": e.get("label") or e["account_id"],
                "field_names": e.get("field_names", []),
                "updated_at": e.get("updated_at"),
                "is_primary": bool(e.get("is_primary")),
            }
            for e in entries
        ]

    def primary_account_id(self, user_id: str, integration: str) -> str | None:
        accounts = self.list_accounts(user_id, integration)
        if not accounts:
            return None
        primary = next((a for a in accounts if a["is_primary"]), None)
        if primary:
            return primary["account_id"]
        if any(a["account_id"] == "default" for a in accounts):
            return "default"
        return accounts[0]["account_id"]

    def set_primary_account(self, user_id: str, integration: str, account_id: str) -> bool:
        target_key = self._key(user_id, integration, account_id)
        if target_key not in self.data["credentials"]:
            return False
        for key, entry in self.data["credentials"].items():
            if entry.get("user_id") == user_id and entry.get("integration") == integration:
                entry["is_primary"] = key == target_key
        self._save()
        return True

    def list_users_with_credential(self, integration: str) -> list[dict]:
        return [
            {
                "user_id": e.get("user_id"),
                "account_id": e.get("account_id", "default"),
                "label": e.get("label"),
                "is_primary": bool(e.get("is_primary")),
                "field_names": e.get("field_names", []),
                "updated_at": e.get("updated_at"),
            }
            for e in self.data["credentials"].values()
            if e.get("integration") == integration
        ]
