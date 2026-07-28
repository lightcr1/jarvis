from __future__ import annotations

import os
import time
from typing import Callable
from urllib.parse import quote

from .guac_auth import GuacamoleTokenError, encode_json_auth_token
from .store import DEFAULT_PORTS, VALID_OS_TYPES, VALID_PROTOCOLS
from .wol import build_magic_packet, normalize_mac

INTEGRATION_PREFIX = "workspace"
# Workspace targets are shared home-lab devices, not per-user data — there is no
# natural "owner" for their RDP/VNC credentials. IntegrationCredentialStore keys
# on (user_id, integration); we use this fixed sentinel as the user_id half of
# that key and fold the target id into the integration half, so credentials are
# addressed purely by target regardless of which admin set them.
CREDENTIAL_OWNER = "workspace"
GUACAMOLE_TOKEN_TTL_SEC = 90


def _emergency_stop_active() -> bool:
    return (os.getenv("JARVIS_EMERGENCY_STOP") or "0").strip().lower() in {"1", "true", "yes", "on"}


def _credential_integration(target_id: str) -> str:
    return f"{INTEGRATION_PREFIX}:{target_id}"


class WorkspaceAccessError(PermissionError):
    pass


class WorkspaceConfigError(RuntimeError):
    pass


class WorkspaceCredentialsMissing(LookupError):
    pass


class WorkspaceWakeUnavailable(RuntimeError):
    pass


class WorkspaceService:
    def __init__(
        self,
        *,
        store,
        credential_store,
        membership_store,
        permission_store,
        resolve_effective_permissions,
        normalize_role,
        audit_log=None,
        guacamole_url_fn: Callable[[], str | None] | None = None,
        guacamole_secret_fn: Callable[[], str | None] | None = None,
        token_ttl_sec: int = GUACAMOLE_TOKEN_TTL_SEC,
    ) -> None:
        self.store = store
        self.credential_store = credential_store
        self.membership_store = membership_store
        self.permission_store = permission_store
        self.resolve_effective_permissions = resolve_effective_permissions
        self.normalize_role = normalize_role
        self.audit_log = audit_log
        self.guacamole_url_fn = guacamole_url_fn or (lambda: os.getenv("JARVIS_WORKSPACE_GUACAMOLE_URL"))
        self.guacamole_secret_fn = guacamole_secret_fn or (lambda: os.getenv("JARVIS_WORKSPACE_JSON_SECRET"))
        self.token_ttl_sec = token_ttl_sec

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
            raise WorkspaceAccessError(f"missing permission: {required_permission}")
        return {"role": normalized_role, "effective_permissions": sorted(effective)}

    def _get_target_or_raise(self, target_id: str) -> dict:
        target = self.store.get_target(target_id)
        if not target:
            raise LookupError("workspace target not found")
        return target

    def list_targets(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="workspace.read")
        targets = sorted(self.store.list_targets(), key=lambda item: item.get("created_at", 0))
        return {"policy": policy, "targets": targets}

    def get_target(self, target_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="workspace.read")
        return {"policy": policy, "target": self._get_target_or_raise(target_id)}

    def _validate_target_fields(self, payload: dict[str, object], *, partial: bool, existing: dict | None = None) -> dict[str, object]:
        fields: dict[str, object] = {}
        base = existing or {}
        if not partial or "name" in payload:
            name = str((payload or {}).get("name") or "").strip()
            if not name:
                raise ValueError("target name required")
            fields["name"] = name
        if not partial or "os_type" in payload:
            os_type = str((payload or {}).get("os_type") or "").strip().lower()
            if os_type not in VALID_OS_TYPES:
                raise ValueError(f"os_type must be one of {sorted(VALID_OS_TYPES)}")
            fields["os_type"] = os_type
        if not partial or "protocol" in payload:
            protocol = str((payload or {}).get("protocol") or "").strip().lower()
            if protocol not in VALID_PROTOCOLS:
                raise ValueError(f"protocol must be one of {sorted(VALID_PROTOCOLS)}")
            fields["protocol"] = protocol
        if not partial or "tailscale_host" in payload:
            host = str((payload or {}).get("tailscale_host") or "").strip()
            if not host:
                raise ValueError("tailscale_host required")
            fields["tailscale_host"] = host
        if not partial or "port" in payload:
            port = (payload or {}).get("port")
            if port is None or port == "":
                effective_protocol = str(fields.get("protocol") or base.get("protocol") or "rdp")
                port = DEFAULT_PORTS.get(effective_protocol, 3389)
            try:
                port = int(port)
            except (TypeError, ValueError) as exc:
                raise ValueError("port must be an integer") from exc
            if not (1 <= port <= 65535):
                raise ValueError("port must be between 1 and 65535")
            fields["port"] = port
        if not partial or "wol_relay_host" in payload:
            relay = (payload or {}).get("wol_relay_host")
            fields["wol_relay_host"] = str(relay).strip() if relay else None
        if not partial or "wol_mac" in payload:
            mac = (payload or {}).get("wol_mac")
            fields["wol_mac"] = normalize_mac(str(mac)) if mac else None
        return fields

    def create_target(self, payload: dict[str, object], *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="workspace.write")
        fields = self._validate_target_fields(payload or {}, partial=False)
        now = int(time.time())
        target = self.store.add_target({**fields, "created_at": now, "updated_at": now})
        self._write_audit("workspace_target_created", actor_user_id=user_id, actor_role=role, payload={"target_id": target["id"], "name": target["name"]})
        return {"policy": policy, "target": target}

    def update_target(self, target_id: str, payload: dict[str, object], *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="workspace.write")
        existing = self._get_target_or_raise(target_id)
        patch = self._validate_target_fields(payload or {}, partial=True, existing=existing)
        patch["updated_at"] = int(time.time())
        updated = self.store.update_target(target_id, patch)
        self._write_audit("workspace_target_updated", actor_user_id=user_id, actor_role=role, payload={"target_id": target_id})
        return {"policy": policy, "target": updated}

    def delete_target(self, target_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="workspace.write")
        self._get_target_or_raise(target_id)
        deleted = self.store.delete_target(target_id)
        self.credential_store.delete_credentials(CREDENTIAL_OWNER, _credential_integration(target_id))
        self._write_audit("workspace_target_deleted", actor_user_id=user_id, actor_role=role, payload={"target_id": target_id})
        return {"policy": policy, "deleted": deleted}

    def set_credentials(self, target_id: str, fields: dict[str, str], *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="workspace.write")
        target = self._get_target_or_raise(target_id)
        password = str((fields or {}).get("password") or "").strip()
        username = str((fields or {}).get("username") or "").strip()
        if target["protocol"] == "rdp" and not username:
            raise ValueError("username required for RDP targets")
        if not password:
            raise ValueError("password required")
        clean = {"password": password}
        if username:
            clean["username"] = username
        record = self.credential_store.set_credentials(CREDENTIAL_OWNER, _credential_integration(target_id), clean)
        self._write_audit("workspace_credentials_set", actor_user_id=user_id, actor_role=role, payload={"target_id": target_id})
        return {"policy": policy, "credentials": record}

    def credentials_status(self, target_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="workspace.read")
        self._get_target_or_raise(target_id)
        status = self.credential_store.status(CREDENTIAL_OWNER, _credential_integration(target_id))
        return {"policy": policy, "status": status}

    def delete_credentials(self, target_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="workspace.write")
        self._get_target_or_raise(target_id)
        deleted = self.credential_store.delete_credentials(CREDENTIAL_OWNER, _credential_integration(target_id))
        self._write_audit("workspace_credentials_deleted", actor_user_id=user_id, actor_role=role, payload={"target_id": target_id})
        return {"policy": policy, "deleted": deleted}

    def _connection_parameters(self, target: dict, creds: dict[str, str]) -> dict[str, str]:
        params = {"hostname": target["tailscale_host"], "port": str(target["port"])}
        if target["protocol"] == "rdp":
            params["username"] = creds.get("username", "")
            params["password"] = creds.get("password", "")
            params["ignore-cert"] = "true"
        else:
            params["password"] = creds.get("password", "")
            if creds.get("username"):
                params["username"] = creds["username"]
        return params

    def generate_connection_token(self, target_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="workspace.connect")
        target = self._get_target_or_raise(target_id)
        guac_url = (self.guacamole_url_fn() or "").strip()
        secret = (self.guacamole_secret_fn() or "").strip()
        if not guac_url or not secret:
            raise WorkspaceConfigError(
                "workspace not configured — set JARVIS_WORKSPACE_GUACAMOLE_URL and JARVIS_WORKSPACE_JSON_SECRET"
            )
        creds = self.credential_store.get_credentials(CREDENTIAL_OWNER, _credential_integration(target_id))
        if not creds:
            raise WorkspaceCredentialsMissing("credentials not configured for this workspace target")
        now_ms = int(time.time() * 1000)
        expires_ms = now_ms + self.token_ttl_sec * 1000
        payload = {
            "username": f"jarvis:{user_id or 'guest'}",
            "expires": expires_ms,
            "connections": {
                target["name"]: {
                    "protocol": target["protocol"],
                    "parameters": self._connection_parameters(target, creds),
                }
            },
        }
        try:
            token = encode_json_auth_token(secret, payload)
        except GuacamoleTokenError as exc:
            raise WorkspaceConfigError(str(exc)) from exc
        url = f"{guac_url.rstrip('/')}/?data={quote(token, safe='')}"
        self._write_audit("workspace_connect_token_issued", actor_user_id=user_id, actor_role=role, payload={"target_id": target_id})
        return {"policy": policy, "url": url, "token": token, "expires_at": expires_ms // 1000}

    def trigger_wake(self, target_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="workspace.connect")
        target = self._get_target_or_raise(target_id)
        relay = (target.get("wol_relay_host") or "").strip()
        mac = (target.get("wol_mac") or "").strip()
        if not relay:
            raise WorkspaceWakeUnavailable(
                "wake-on-LAN is unavailable for this target — no wol_relay_host configured. Tailscale does not "
                "forward LAN broadcast traffic, so a relay device on the target's own physical network is required."
            )
        if not mac:
            raise WorkspaceWakeUnavailable("wake-on-LAN is unavailable for this target — no wol_mac configured.")
        packet = build_magic_packet(mac)
        self._write_audit("workspace_wake_attempted", actor_user_id=user_id, actor_role=role, payload={"target_id": target_id, "relay_host": relay})
        return {
            "policy": policy,
            "status": "stub_not_sent",
            "relay_host": relay,
            "magic_packet_hex": packet.hex(),
            "detail": (
                "Magic packet constructed but not transmitted — dispatching it to the relay's own listener is not "
                "yet implemented (the relay-side agent is out of scope for this change). Implement a small listener "
                "on the relay host and a client call here to complete wake support."
            ),
        }
