"""Zonen-Policy: was darf Jarvis wo, und wie viel (Plan 4.1).

Die Policy ist bewusst **backend-agnostisch**: lokal laeuft die Sandbox als
Docker-Container, aber dieselbe Config kann spaeter auf ``proxmox`` oder ``k8s``
zeigen (echtes VLAN, echte VMs). Kritische Dienste (``runpod-controller``,
``searxng``) sind fuer Agent und Executor unantastbar.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

VALID_BACKENDS = ("docker", "proxmox", "k8s")


def default_zones_path() -> Path:
    configured = os.getenv("JARVIS_ZONES_FILE")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "config" / "zones.json"


def load_zones(path: Path | None = None) -> dict:
    target = path or default_zones_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def critical_services(zones: dict | None = None) -> frozenset[str]:
    data = zones if zones is not None else load_zones()
    return frozenset(str(s) for s in (data.get("critical_services") or []))


def host_reserve(zones: dict | None = None) -> dict:
    data = zones if zones is not None else load_zones()
    reserve = data.get("host_reserve") or {}
    return {"cpus": float(reserve.get("cpus", 0) or 0),
            "memory_mb": float(reserve.get("memory_mb", 0) or 0)}


def zone(name: str, zones: dict | None = None) -> dict:
    data = zones if zones is not None else load_zones()
    return (data.get("zones") or {}).get(name) or {}


def sandbox_limits(zones: dict | None = None) -> dict:
    limits = dict(zone("sandbox", zones).get("resources") or {})
    limits.setdefault("max_concurrent", 0)
    limits.setdefault("cpus", 0.0)
    limits.setdefault("memory_mb", 0)
    limits.setdefault("disk_gb", 0)
    limits.setdefault("max_lifetime_minutes", 0)
    return limits


def sandbox_prefix(zones: dict | None = None) -> str:
    return str(zone("sandbox", zones).get("container_prefix") or "jarvis-sandbox-")


def backend_of(zone_name: str, zones: dict | None = None) -> str:
    value = str(zone(zone_name, zones).get("backend") or "docker").lower()
    return value if value in VALID_BACKENDS else "docker"


def is_forbidden(service: str, zones: dict | None = None) -> bool:
    """Kritische Dienste, die weder Agent noch Executor anfassen duerfen."""
    return str(service or "") in critical_services(zones)


def service_zone(service: str, zones: dict | None = None) -> str:
    """Ordnet einen Containernamen einer Zone zu: forbidden|sandbox|managed."""
    name = str(service or "")
    if is_forbidden(name, zones):
        return "forbidden"
    if name.startswith(sandbox_prefix(zones)):
        return "sandbox"
    return "managed"


def authorize_service(service: str, zones: dict | None = None) -> tuple[bool, str]:
    """Duerfen wir diesen Dienst veraendern? (False fuer kritische Dienste.)"""
    name = str(service or "").strip()
    if not name:
        return False, "kein Dienst angegeben"
    if is_forbidden(name, zones):
        return False, f"'{name}' ist ein kritischer Dienst und gesperrt"
    return True, service_zone(name, zones)


def available_sandbox_slots(active_count: int, host_cpus: float, host_memory_mb: float,
                            zones: dict | None = None) -> dict:
    """Wie viele weitere Sandboxen passen, ohne dem Host die Reserve zu nehmen?"""
    limits = sandbox_limits(zones)
    reserve = host_reserve(zones)
    cpus = float(limits["cpus"]) or 0.0
    memory = float(limits["memory_mb"]) or 0.0
    max_by_cpu = int((host_cpus - reserve["cpus"]) // cpus) if cpus > 0 else 0
    max_by_mem = int((host_memory_mb - reserve["memory_mb"]) // memory) if memory > 0 else 0
    max_total = max(0, min(max_by_cpu, max_by_mem, int(limits["max_concurrent"])))
    active = max(0, int(active_count))
    return {
        "max_total": max_total,
        "active": active,
        "available": max(0, max_total - active),
        "reasons": {"by_cpu": max(0, max_by_cpu), "by_memory": max(0, max_by_mem),
                    "by_max_concurrent": int(limits["max_concurrent"])},
    }
