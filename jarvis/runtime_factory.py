"""Waehlt die Sandbox-Laufzeit anhand des konfigurierten Backends (Review-Punkt 1)."""
from __future__ import annotations

import os

from .zones import backend_of, load_zones


def build_sandbox_runtime(zones: dict | None = None):
    data = zones if zones is not None else load_zones()
    backend = backend_of("sandbox", data)
    if backend == "proxmox":
        from .proxmox_runtime import ProxmoxRuntime
        runtime = ProxmoxRuntime.from_env()
        if runtime is None:
            raise RuntimeError("backend 'proxmox' konfiguriert, aber JARVIS_PROXMOX_* fehlen")
        return runtime
    if backend == "k8s":
        raise RuntimeError("backend 'k8s' ist noch nicht implementiert")
    from .docker_runtime import DockerRuntime
    return DockerRuntime(os.getenv("JARVIS_DOCKER_API", "http://docker-socket-proxy:2375"))
