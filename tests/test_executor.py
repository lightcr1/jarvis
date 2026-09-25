"""Tests fuer den Executor-Kern (Plan 4.2), ohne Docker."""
from __future__ import annotations

import pytest

from jarvis.executor import Executor, SandboxError
from jarvis.zones import load_zones


class FakeRuntime:
    def __init__(self):
        self.created = []
        self.destroyed = []
        self.execs = []

    def list_sandboxes(self, prefix):
        return [c for c in self.created if c["name"].startswith(prefix)]

    def create_sandbox(self, spec):
        self.created.append(spec)
        return {"name": spec["name"], "image": spec["image"], "status": "created"}

    def destroy_sandbox(self, name):
        self.destroyed.append(name)

    def exec_in_sandbox(self, name, command):
        self.execs.append((name, command))
        return {"exit_code": 0, "output": "ok"}


def _ex(runtime=None):
    return Executor(runtime or FakeRuntime(), zones=load_zones(),
                    host_cpus=4, host_memory_mb=16384, clock=lambda: 1000)


def test_create_applies_isolation_and_limits():
    runtime = FakeRuntime()
    _ex(runtime).create(image="debian:bookworm-slim", command="sleep 5")
    spec = runtime.created[0]
    assert spec["cap_drop"] == ["ALL"] and spec["read_only"] is True
    assert spec["no_new_privileges"] is True
    assert spec["cpus"] == 1.0 and spec["memory_mb"] == 2048 and spec["pids_limit"] == 512
    assert spec["network"] == "jarvis-sandbox" and spec["max_lifetime_minutes"] == 120
    assert spec["name"].startswith("jarvis-sandbox-")
    assert spec["labels"]["jarvis.zone"] == "sandbox"


def test_create_rejects_unknown_image():
    with pytest.raises(SandboxError):
        _ex().create(image="evil:latest")


def test_create_respects_budget_slots():
    executor = _ex()
    for _ in range(3):  # 4 CPU / Reserve 1 / 1 pro Sandbox -> max. 3
        executor.create(image="alpine:latest")
    with pytest.raises(SandboxError):
        executor.create(image="alpine:latest")


def test_destroy_and_run_guard_zone_and_critical():
    runtime = FakeRuntime()
    executor = _ex(runtime)
    executor.destroy("jarvis-sandbox-abc")
    assert runtime.destroyed == ["jarvis-sandbox-abc"]
    for forbidden in ("jarvis-app", "runpod-controller", "searxng"):
        with pytest.raises(SandboxError):
            executor.destroy(forbidden)


def test_run_only_in_sandbox():
    executor = _ex()
    assert executor.run("jarvis-sandbox-x", "echo hi")["output"] == "ok"
    with pytest.raises(SandboxError):
        executor.run("searxng", "rm -rf /")


def test_authorize_managed_blocks_critical_and_reports_tier():
    executor = _ex()
    with pytest.raises(SandboxError):
        executor.authorize_managed("searxng")
    decision = executor.authorize_managed("jarvis-app", capability="service.restart")
    assert decision.tier == "T2" and decision.decision in ("ask", "allow")
