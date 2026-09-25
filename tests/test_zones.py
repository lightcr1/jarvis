"""Tests fuer die Zonen-Policy (Plan 4.1)."""
from __future__ import annotations

from jarvis.zones import (authorize_service, available_sandbox_slots, backend_of,
                          critical_services, is_forbidden, load_zones, sandbox_limits,
                          service_zone)

ZONES = load_zones()


def test_critical_services_are_forbidden():
    assert critical_services(ZONES) == {"runpod-controller", "searxng"}
    assert is_forbidden("runpod-controller", ZONES)
    assert is_forbidden("searxng", ZONES)
    assert not is_forbidden("jarvis-app", ZONES)


def test_service_zone_classification():
    assert service_zone("runpod-controller", ZONES) == "forbidden"
    assert service_zone("jarvis-sandbox-test1", ZONES) == "sandbox"
    assert service_zone("jarvis-app", ZONES) == "managed"


def test_authorize_service_blocks_critical_and_empty():
    assert authorize_service("jarvis-app", ZONES) == (True, "managed")
    ok, reason = authorize_service("searxng", ZONES)
    assert ok is False and "kritisch" in reason
    assert authorize_service("", ZONES)[0] is False


def test_sandbox_limits_and_backend():
    limits = sandbox_limits(ZONES)
    assert limits["max_concurrent"] == 4 and limits["cpus"] == 1.0
    assert limits["memory_mb"] == 2048 and limits["disk_gb"] == 25
    assert backend_of("sandbox", ZONES) == "docker"


def test_available_sandbox_slots_respects_host_reserve():
    # Host 4 CPU / 16 GiB, Reserve 1 CPU / 4 GiB, je Sandbox 1 CPU / 2 GiB.
    free = available_sandbox_slots(0, 4, 16384, ZONES)
    assert free["max_total"] == 3          # CPU begrenzt: (4-1)/1
    assert free["reasons"]["by_cpu"] == 3 and free["reasons"]["by_memory"] == 6
    assert available_sandbox_slots(2, 4, 16384, ZONES)["available"] == 1
    assert available_sandbox_slots(3, 4, 16384, ZONES)["available"] == 0
    assert available_sandbox_slots(9, 4, 16384, ZONES)["available"] == 0
