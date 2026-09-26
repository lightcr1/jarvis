"""Tests fuer den Executor-Client und die Sandbox-Tools (Plan 4.2/5.1)."""
from __future__ import annotations

import pytest

from jarvis.executor_client import ExecutorClient, ExecutorError
from jarvis.tool_registry import ToolExecutionContext
from jarvis.tool_registry_tools import (_sandbox_create_handler, _sandbox_destroy_handler,
                                        _sandbox_exec_handler, build_pilot_tool_registry)


def _client(handler):
    calls = []
    def transport(method, path, body=None):
        calls.append((method, path, body))
        return handler(method, path)
    return ExecutorClient("http://exec:8120", "tok", transport=transport), calls


def test_from_env_is_none_without_config():
    assert ExecutorClient.from_env({}) is None
    assert ExecutorClient.from_env({"JARVIS_EXECUTOR_URL": "http://x"}) is None
    client = ExecutorClient.from_env({"JARVIS_EXECUTOR_URL": "http://x/", "JARVIS_AGENT_REQUEST_TOKEN": "t"})
    assert client is not None and client.base_url == "http://x" and client.token == "t"


def test_create_and_error_detail():
    runtime, calls = _client(lambda m, p: (201, {"sandbox": {"name": "jarvis-sandbox-1"}}))
    assert runtime.create(image="alpine:latest")["sandbox"]["name"] == "jarvis-sandbox-1"
    assert calls == [("POST", "/sandboxes", {"image": "alpine:latest", "command": ""})]

    bad, _ = _client(lambda m, p: (409, {"detail": "gesperrt"}))
    with pytest.raises(ExecutorError) as exc:
        bad.destroy("searxng")
    assert "gesperrt" in str(exc.value)


def test_handlers_unconfigured_and_configured():
    class Fake:
        def create(self, image, command=""):
            return {"sandbox": {"name": "jarvis-sandbox-abc", "image": image}}
        def run(self, name, command):
            return {"exit_code": 0, "running": False}
        def destroy(self, name):
            return {"destroyed": name}

    ctx = ToolExecutionContext(user_id="u", role="admin", deps={})
    assert _sandbox_create_handler(ctx, {"image": "alpine"})["data"]["error"] == "executor_unconfigured"

    ctx2 = ToolExecutionContext(user_id="u", role="admin", deps={"executor_client": Fake()})
    assert _sandbox_create_handler(ctx2, {"image": "alpine"})["data"]["route"] == "sandbox_created"
    assert _sandbox_exec_handler(ctx2, {"name": "jarvis-sandbox-abc", "command": "echo hi"})["data"]["exit_code"] == 0
    assert _sandbox_destroy_handler(ctx2, {"name": "jarvis-sandbox-abc"})["data"]["route"] == "sandbox_destroyed"


def test_sandbox_tools_registered_with_capabilities():
    registry = build_pilot_tool_registry()
    assert registry.get("sandbox_create").capability == "vm.sandbox.create"
    assert registry.get("sandbox_exec").capability == "vm.sandbox.exec"
    assert registry.get("sandbox_destroy").capability == "vm.sandbox.destroy"
