"""Tests fuer die Backend-Auswahl (Docker vs. Proxmox)."""
from __future__ import annotations

import pytest

from jarvis.runtime_factory import build_sandbox_runtime
from jarvis.zones import load_zones


def test_default_is_docker(monkeypatch):
    monkeypatch.setenv("JARVIS_DOCKER_API", "http://proxy:2375")
    runtime = build_sandbox_runtime(load_zones())
    assert runtime.__class__.__name__ == "DockerRuntime"


def test_proxmox_without_env_raises(monkeypatch):
    zones = load_zones()
    zones["zones"]["sandbox"]["backend"] = "proxmox"
    for var in ("JARVIS_PROXMOX_URL", "JARVIS_PROXMOX_TOKEN_ID", "JARVIS_PROXMOX_TOKEN_SECRET", "JARVIS_PROXMOX_NODE"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError):
        build_sandbox_runtime(zones)


def test_proxmox_with_env(monkeypatch):
    zones = load_zones()
    zones["zones"]["sandbox"]["backend"] = "proxmox"
    monkeypatch.setenv("JARVIS_PROXMOX_URL", "https://pve:8006")
    monkeypatch.setenv("JARVIS_PROXMOX_TOKEN_ID", "a")
    monkeypatch.setenv("JARVIS_PROXMOX_TOKEN_SECRET", "b")
    monkeypatch.setenv("JARVIS_PROXMOX_NODE", "pve")
    monkeypatch.setenv("JARVIS_PROXMOX_TEMPLATE", "9000")
    assert build_sandbox_runtime(zones).__class__.__name__ == "ProxmoxRuntime"
