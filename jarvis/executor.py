"""Executor: fuehrt Sandbox-/verwaltete Aktionen nach der Zonen-Policy aus (4.2).

Der Executor ist die **einzige** Stelle mit Zugriff auf die Laufzeit (lokal der
eingeschraenkte Docker-Proxy). Der Agent haelt keine Schluessel. Jede Aktion
laeuft durch den Freigabe-Kern (`authorize_action`); T2/T3 werden hier **nie**
selbst freigegeben. Die Laufzeit ist injizierbar, damit die Logik ohne Docker
testbar ist und spaeter auf Proxmox/K8s zeigen kann.
"""
from __future__ import annotations

import uuid
from typing import Protocol

from .capabilities import authorize_action
from .zones import (allowed_images, authorize_service, available_sandbox_slots,
                    is_forbidden, load_zones, sandbox_allow_lan, sandbox_env,
                    sandbox_limits, sandbox_network, sandbox_pids_limit, sandbox_prefix)


class SandboxError(RuntimeError):
    """Aktion verletzt die Zonen-Policy oder das Budget."""


class SandboxRuntime(Protocol):
    def list_sandboxes(self, prefix: str) -> list[dict]: ...
    def create_sandbox(self, spec: dict) -> dict: ...
    def destroy_sandbox(self, name: str) -> None: ...
    def exec_in_sandbox(self, name: str, command: str) -> dict: ...


class Executor:
    def __init__(self, runtime: SandboxRuntime, *, zones: dict | None = None,
                 host_cpus: float = 4.0, host_memory_mb: float = 16384.0,
                 clock=None, emergency_stop=None, audit=None, grant_store=None):
        import time as _time
        self.runtime = runtime
        self.zones = zones if zones is not None else load_zones()
        self.host_cpus = float(host_cpus)
        self.host_memory_mb = float(host_memory_mb)
        self.clock = clock or _time.time
        self.emergency_stop = emergency_stop
        self.audit = audit
        self.grant_store = grant_store

    # ---- Sandbox --------------------------------------------------------
    def list_sandboxes(self) -> list[dict]:
        return self.runtime.list_sandboxes(sandbox_prefix(self.zones))

    def create(self, *, image: str, command: str = "", actor: str = "agent",
               capability: str = "vm.sandbox.create", params: dict | None = None,
               standing_grant: dict | None = None) -> dict:
        if image not in allowed_images(self.zones):
            raise SandboxError(f"Image '{image}' ist nicht erlaubt")
        if sandbox_allow_lan(self.zones):
            raise SandboxError("Sandbox mit LAN-Zugriff ist nicht erlaubt (allow_lan=false erforderlich)")
        self._allow(capability, target=image, params=params, standing_grant=standing_grant)
        slots = available_sandbox_slots(len(self.list_sandboxes()), self.host_cpus,
                                        self.host_memory_mb, self.zones)
        if slots["available"] <= 0:
            raise SandboxError("kein Sandbox-Slot frei -- Budget erschoepft (T3 anfragen)")
        limits = sandbox_limits(self.zones)
        name = f"{sandbox_prefix(self.zones)}{uuid.uuid4().hex[:10]}"
        spec = {
            "name": name, "image": image, "command": command,
            "network": sandbox_network(self.zones),
            "cpus": limits["cpus"], "memory_mb": limits["memory_mb"],
            "pids_limit": sandbox_pids_limit(self.zones),
            "read_only": True, "cap_drop": ["ALL"], "no_new_privileges": True,
            "max_lifetime_minutes": limits["max_lifetime_minutes"],
            "env": sandbox_env(self.zones),
            "disk_gb": limits["disk_gb"],
            "labels": {"jarvis.zone": "sandbox", "jarvis.actor": str(actor),
                       "jarvis.created_at": str(int(self.clock())),
                       "jarvis.expires_at": self._expires_at(limits)},
        }
        created = self.runtime.create_sandbox(spec)
        self._audit("sandbox.create", {"name": name, "image": image, "actor": actor})
        return {"sandbox": created, "limits": limits, "slots": slots}

    def reap_expired(self, now: float | None = None) -> list[str]:
        """Beendet Sandboxen jenseits ihrer max. Laufzeit (Slots wieder frei)."""
        current = self.clock() if now is None else now
        reaped: list[str] = []
        for box in self.list_sandboxes():
            expires = str((box.get("labels") or {}).get("jarvis.expires_at") or "")
            if not expires:
                continue
            try:
                expires_at = int(expires)
            except ValueError:
                continue
            if expires_at and expires_at <= current:
                name = box.get("name")
                self.runtime.destroy_sandbox(name)
                reaped.append(name)
                self._audit("sandbox.reaped", {"name": name})
        return reaped

    def _expires_at(self, limits: dict) -> str:
        lifetime = int(limits.get("max_lifetime_minutes") or 0)
        return str(int(self.clock()) + lifetime * 60) if lifetime > 0 else ""

    def _audit(self, event: str, detail: dict) -> None:
        if self.audit is not None:
            try:
                self.audit(event, detail)
            except Exception:  # noqa: BLE001 - Audit darf nie die Aktion brechen
                pass

    def destroy(self, name: str, *, actor: str = "agent",
                capability: str = "vm.sandbox.destroy") -> dict:
        self._assert_sandbox(name)
        self._allow(capability, target=name)
        self.runtime.destroy_sandbox(name)
        self._audit("sandbox.destroy", {"name": name, "actor": actor})
        return {"destroyed": name}

    def run(self, name: str, command: str, *, actor: str = "agent",
            capability: str = "vm.sandbox.exec") -> dict:
        self._assert_sandbox(name)
        self._allow(capability, target=name)
        result = self.runtime.exec_in_sandbox(name, command)
        self._audit("sandbox.exec", {"name": name, "actor": actor})
        return result

    # ---- Verwaltete Zone (fuer Self-Deploy, 5.3) ------------------------
    def authorize_managed(self, service: str, *, capability: str = "service.restart",
                          params: dict | None = None, standing_grant: dict | None = None):
        ok, info = authorize_service(service, self.zones)
        if not ok:
            raise SandboxError(info)
        grant = standing_grant
        if grant is None and self.grant_store is not None:
            try:
                grant = self.grant_store.match_standing_grant(capability, service)
            except Exception:  # noqa: BLE001
                grant = None
        decision = authorize_action(capability, target=service, params=params, standing_grant=grant)
        if grant is not None and decision.decision == "allow" and decision.tier == "T2" \
                and self.grant_store is not None:
            try:
                self.grant_store.consume_standing_grant(grant["id"])
            except Exception:  # noqa: BLE001
                pass
        return decision

    # ---- intern ---------------------------------------------------------
    def _assert_sandbox(self, name: str) -> None:
        if is_forbidden(name, self.zones):
            raise SandboxError(f"'{name}' ist ein kritischer Dienst und gesperrt")
        if not str(name).startswith(sandbox_prefix(self.zones)):
            raise SandboxError(f"'{name}' liegt nicht in der Sandbox-Zone")

    def emergency_stop_active(self) -> bool:
        import os
        value = self.emergency_stop
        if callable(value):
            return bool(value())
        if value is None:
            return os.getenv("JARVIS_EMERGENCY_STOP", "0").strip() in ("1", "true", "yes")
        return bool(value)

    def _allow(self, capability: str, *, target: str = "", params: dict | None = None,
               standing_grant: dict | None = None) -> None:
        grant = standing_grant
        if grant is None and self.grant_store is not None:
            try:
                grant = self.grant_store.match_standing_grant(capability, target)
            except Exception:  # noqa: BLE001
                grant = None
        decision = authorize_action(capability, target=target, params=params,
                                    standing_grant=grant,
                                    emergency_stop=self.emergency_stop_active())
        if decision.decision == "deny":
            raise SandboxError(f"verweigert: {decision.reason}")
        if decision.decision == "ask":
            raise SandboxError(f"Freigabe erforderlich: {decision.reason}")
        if grant is not None and decision.tier == "T2" and self.grant_store is not None:
            try:
                self.grant_store.consume_standing_grant(grant["id"])
            except Exception:  # noqa: BLE001
                pass
