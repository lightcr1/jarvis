"""Tests fuer den Executor-Dienst (Plan 4.2), offline ueber Fake-Runtime."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jarvis.executor import Executor
from jarvis.zones import load_zones

SCRIPT = Path(__file__).resolve().parents[1] / "services" / "executor" / "app.py"
spec = importlib.util.spec_from_file_location("jarvis_executor_app", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

HEADERS = {"X-Jarvis-Agent-Request-Token": "tok"}


class FakeRuntime:
    def __init__(self):
        self.created = []
        self.destroyed = []
    def list_sandboxes(self, prefix):
        return [c for c in self.created if c["name"].startswith(prefix)]
    def create_sandbox(self, spec):
        self.created.append(spec)
        return {"name": spec["name"], "image": spec["image"], "state": "running"}
    def destroy_sandbox(self, name):
        self.destroyed.append(name)
    def exec_in_sandbox(self, name, command):
        return {"exit_code": 0, "output": "ok"}


def _client(monkeypatch, *, enabled=True, token="tok", executor=None):
    monkeypatch.setenv("JARVIS_EXECUTOR_ENABLED", "1" if enabled else "0")
    monkeypatch.setenv("JARVIS_AGENT_REQUEST_TOKEN", token)
    module.set_executor(executor or Executor(FakeRuntime(), zones=load_zones(),
                                             host_cpus=4, host_memory_mb=16384))
    return TestClient(module.app)


def test_requires_agent_token(monkeypatch):
    client = _client(monkeypatch)
    assert client.get("/sandboxes").status_code == 401
    assert client.get("/sandboxes", headers={"X-Jarvis-Agent-Request-Token": "nope"}).status_code == 401


def test_disabled_executor_returns_503(monkeypatch):
    client = _client(monkeypatch, enabled=False)
    module.set_executor(None)
    assert client.get("/sandboxes", headers=HEADERS).status_code == 503


def test_health_reports_enabled(monkeypatch):
    client = _client(monkeypatch)
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["service"] == "executor" and body["enabled"] is True


def test_create_list_and_destroy(monkeypatch):
    client = _client(monkeypatch)
    created = client.post("/sandboxes", headers=HEADERS,
                          json={"image": "alpine:latest", "command": "sleep 1"})
    assert created.status_code == 201
    name = created.json()["sandbox"]["name"]
    assert name.startswith("jarvis-sandbox-")
    assert [s["name"] for s in client.get("/sandboxes", headers=HEADERS).json()["sandboxes"]] == [name]
    assert client.delete(f"/sandboxes/{name}", headers=HEADERS).json()["destroyed"] == name


def test_create_rejects_unknown_image(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/sandboxes", headers=HEADERS, json={"image": "evil:latest"})
    assert resp.status_code == 409


def test_exec_and_critical_block(monkeypatch):
    client = _client(monkeypatch)
    assert client.post("/sandboxes/jarvis-sandbox-x/exec", headers=HEADERS,
                       json={"command": "echo hi"}).json()["output"] == "ok"
    assert client.post("/sandboxes/searxng/exec", headers=HEADERS,
                       json={"command": "rm -rf /"}).status_code == 409


def test_reap_endpoint(monkeypatch):
    class Reaping(FakeRuntime):
        def list_sandboxes(self, prefix):
            return [{"name": "jarvis-sandbox-old", "labels": {"jarvis.expires_at": "1"}}]
        def destroy_sandbox(self, name):
            self.destroyed.append(name)
    ex = Executor(Reaping(), zones=load_zones(), host_cpus=4, host_memory_mb=16384, clock=lambda: 1000)
    client = _client(monkeypatch, executor=ex)
    resp = client.post("/sandboxes/reap", headers=HEADERS)
    assert resp.status_code == 200 and resp.json()["reaped"] == ["jarvis-sandbox-old"]


def test_audit_log_is_written(monkeypatch, tmp_path):
    log = tmp_path / "executor-audit.log"
    monkeypatch.setenv("JARVIS_EXECUTOR_AUDIT_LOG", str(log))
    ex = Executor(FakeRuntime(), zones=load_zones(), host_cpus=4, host_memory_mb=16384,
                  audit=module._audit)
    client = _client(monkeypatch, executor=ex)
    client.post("/sandboxes", headers=HEADERS, json={"image": "alpine:latest"})
    assert "sandbox.create" in log.read_text(encoding="utf-8")


def test_emergency_stop_blocks_create(monkeypatch):
    ex = Executor(FakeRuntime(), zones=load_zones(), host_cpus=4, host_memory_mb=16384,
                  emergency_stop=lambda: True)
    client = _client(monkeypatch, executor=ex)
    resp = client.post("/sandboxes", headers=HEADERS, json={"image": "alpine:latest"})
    assert resp.status_code == 409
