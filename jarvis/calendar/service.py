from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from .client import CalDavClient

REQUIRED_CREDENTIAL_FIELDS = ("url", "username", "password")
INTEGRATION_NAME = "calendar"


def _emergency_stop_active() -> bool:
    return (os.getenv("JARVIS_EMERGENCY_STOP") or "0").strip().lower() in {"1", "true", "yes", "on"}


class CalendarAccessError(PermissionError):
    pass


class CalendarService:
    def __init__(
        self,
        *,
        store,
        credential_store,
        user_store,
        membership_store,
        permission_store,
        resolve_effective_permissions,
        normalize_role,
        audit_log=None,
        client_factory: Callable[[dict], CalDavClient] | None = None,
    ) -> None:
        self.store = store
        self.credential_store = credential_store
        self.user_store = user_store
        self.membership_store = membership_store
        self.permission_store = permission_store
        self.resolve_effective_permissions = resolve_effective_permissions
        self.normalize_role = normalize_role
        self.audit_log = audit_log
        self.client_factory = client_factory or (lambda creds: CalDavClient(creds["url"], creds["username"], creds["password"]))

    def _write_audit(self, event: str, *, actor_user_id: str | None, actor_role: str | None, payload: dict | None = None) -> None:
        if not self.audit_log:
            return
        body = {"actor_user_id": actor_user_id, "actor_role": self.normalize_role(actor_role), **(payload or {})}
        try:
            self.audit_log.write(event, body)
        except Exception:
            return

    def _effective_permissions(self, user_id: str | None, role: str | None) -> set[str]:
        return set(self.resolve_effective_permissions(self.normalize_role(role), user_id, self.membership_store, self.permission_store))

    def require_access(self, *, user_id: str | None, role: str | None, required_permission: str) -> dict[str, object]:
        normalized_role = self.normalize_role(role)
        effective = self._effective_permissions(user_id, role)
        if normalized_role != "admin" and required_permission not in effective:
            raise CalendarAccessError(f"missing permission: {required_permission}")
        return {"role": normalized_role, "effective_permissions": sorted(effective)}

    def _owned_event(self, event_id: str, *, user_id: str | None, role: str | None) -> dict:
        event = self.store.get_event(event_id)
        if not event:
            raise LookupError("event not found")
        if event.get("user_id") != user_id and self.normalize_role(role) != "admin":
            raise LookupError("event not found")
        return event

    def set_credentials(self, fields: dict[str, str], *, user_id: str | None, role: str | None) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="calendar.write")
        missing = [f for f in REQUIRED_CREDENTIAL_FIELDS if not str(fields.get(f) or "").strip()]
        if missing:
            raise ValueError(f"missing required field(s): {', '.join(missing)}")
        clean = {k: str(fields[k]).strip() for k in REQUIRED_CREDENTIAL_FIELDS}
        record = self.credential_store.set_credentials(user_id, INTEGRATION_NAME, clean)
        self._write_audit("calendar_credentials_set", actor_user_id=user_id, actor_role=role)
        return {"policy": policy, "credentials": record}

    def credentials_status(self, *, user_id: str | None, role: str | None) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="calendar.read")
        return {"policy": policy, "status": self.credential_store.status(user_id, INTEGRATION_NAME)}

    def delete_credentials(self, *, user_id: str | None, role: str | None) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="calendar.write")
        deleted = self.credential_store.delete_credentials(user_id, INTEGRATION_NAME)
        self._write_audit("calendar_credentials_deleted", actor_user_id=user_id, actor_role=role)
        return {"policy": policy, "deleted": deleted}

    def _client_for(self, user_id: str | None) -> CalDavClient | None:
        creds = self.credential_store.get_credentials(user_id or "", INTEGRATION_NAME)
        if not creds:
            return None
        return self.client_factory(creds)

    def sync(self, *, user_id: str | None, role: str | None, days_ahead: int = 30, days_behind: int = 7) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="calendar.read")
        client = self._client_for(user_id)
        if client is None:
            raise LookupError("calendar not configured")
        now = datetime.now(timezone.utc)
        remote = client.list_events(now - timedelta(days=days_behind), now + timedelta(days=days_ahead))
        synced = self.store.replace_synced_events(user_id or "", remote)
        self._write_audit("calendar_synced", actor_user_id=user_id, actor_role=role, payload={"count": len(synced)})
        return {"policy": policy, "synced_count": len(synced)}

    def list_events(self, *, user_id: str | None, role: str | None, start: int | None = None, end: int | None = None) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="calendar.read")
        return {"policy": policy, "events": self.store.list_events(user_id or "", start, end)}

    def _validate_event_fields(self, payload: dict) -> dict:
        title = str(payload.get("title") or "").strip()
        if not title:
            raise ValueError("event title required")
        try:
            start = int(payload.get("start"))
            end = int(payload.get("end"))
        except (TypeError, ValueError) as exc:
            raise ValueError("start/end must be Unix epoch integers") from exc
        if end <= start:
            raise ValueError("event end must be after start")
        return {
            "title": title,
            "start": start,
            "end": end,
            "description": str(payload.get("description") or "").strip(),
            "location": str(payload.get("location") or "").strip(),
        }

    def create_event(self, payload: dict, *, user_id: str | None, role: str | None, force: bool = False) -> dict:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="calendar.write")
        fields = self._validate_event_fields(payload)
        conflicts = self.store.find_overlapping(user_id or "", fields["start"], fields["end"])
        if conflicts and not force:
            return {"policy": policy, "conflicts": conflicts, "created": False}
        client = self._client_for(user_id)
        if client is None:
            raise LookupError("calendar not configured")
        uid = uuid.uuid4().hex
        pushed = client.put_event({"uid": uid, **fields})
        if not pushed:
            raise RuntimeError("failed to create event on CalDAV server")
        now = int(time.time())
        event = self.store.add_event({
            "id": f"cal-{uid}",
            "user_id": user_id,
            "uid": uid,
            **fields,
            "source": "caldav",
            "synced_at": now,
            "created_at": now,
            "updated_at": now,
        })
        self._write_audit("calendar_event_created", actor_user_id=user_id, actor_role=role, payload={"event_id": event["id"]})
        return {"policy": policy, "event": event, "conflicts": conflicts, "created": True}

    def delete_event(self, event_id: str, *, user_id: str | None, role: str | None) -> dict:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="calendar.write")
        event = self._owned_event(event_id, user_id=user_id, role=role)
        client = self._client_for(event.get("user_id"))
        if client is not None and event.get("uid"):
            client.delete_event(event["uid"])
        deleted = self.store.delete_event(event_id)
        self._write_audit("calendar_event_deleted", actor_user_id=user_id, actor_role=role, payload={"event_id": event_id})
        return {"policy": policy, "deleted": deleted}
