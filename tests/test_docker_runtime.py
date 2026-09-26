"""Tests fuer den Docker-Runtime-Adapter (Plan 4.2), ohne Docker."""
from __future__ import annotations

import pytest

from jarvis.docker_runtime import DockerError, DockerRuntime

SPEC = {"name": "jarvis-sandbox-abc", "image": "alpine:latest", "network": "jarvis-sandbox",
        "cpus": 1.0, "memory_mb": 2048, "pids_limit": 512, "read_only": True,
        "cap_drop": ["ALL"], "labels": {"jarvis.zone": "sandbox"}, "command": "sleep 5"}


def _runtime(handler):
    calls = []

    def transport(method, path, body=None):
        calls.append((method, path, body))
        return handler(method, path)

    return DockerRuntime("http://socket-proxy:2375", transport=transport), calls


def test_create_sends_isolation_and_limits():
    runtime, calls = _runtime(lambda m, p: (201, {"Id": "abc"}) if "create" in p else (204, {}))
    out = runtime.create_sandbox(SPEC)
    create = next(c for c in calls if "/containers/create" in c[1])
    host = create[2]["HostConfig"]
    assert host["NetworkMode"] == "jarvis-sandbox" and host["CapDrop"] == ["ALL"]
    assert host["ReadonlyRootfs"] is True and host["SecurityOpt"] == ["no-new-privileges"]
    assert host["Memory"] == 2048 * 1024 * 1024 and host["NanoCpus"] == 1_000_000_000
    assert host["PidsLimit"] == 512 and host["Tmpfs"]["/tmp"].startswith("rw,noexec")
    assert create[2]["Cmd"] == ["sh", "-lc", "sleep 5"]
    assert create[2]["Labels"]["jarvis.zone"] == "sandbox"
    assert out["id"] == "abc" and out["state"] == "running"
    assert any(c[1] == "/containers/abc/start" for c in calls)


def test_list_filters_by_prefix():
    containers = [{"Id": "1", "Names": ["/jarvis-sandbox-a"], "Image": "alpine:latest", "State": "running"},
                  {"Id": "2", "Names": ["/jarvis-app"], "Image": "ghcr", "State": "running"}]
    runtime, _ = _runtime(lambda m, p: (200, containers))
    names = [c["name"] for c in runtime.list_sandboxes("jarvis-sandbox-")]
    assert names == ["jarvis-sandbox-a"]


def test_destroy_stops_and_removes():
    runtime, calls = _runtime(lambda m, p: (204, {}))
    runtime.destroy_sandbox("jarvis-sandbox-abc")
    assert ("POST", "/containers/jarvis-sandbox-abc/stop?t=5", None) in calls
    assert ("DELETE", "/containers/jarvis-sandbox-abc?force=1", None) in calls


def test_exec_returns_exit_code():
    def handler(m, p):
        if p.endswith("/exec"):
            return 201, {"Id": "e1"}
        if p == "/exec/e1/json":
            return 200, {"ExitCode": 0, "Running": False}
        return 204, {}
    runtime, calls = _runtime(handler)
    assert runtime.exec_in_sandbox("jarvis-sandbox-abc", "echo hi") == {"exit_code": 0, "running": False}
    assert ("POST", "/exec/e1/start", {"Detach": True, "Tty": False}) in calls


def test_http_error_raises():
    runtime, _ = _runtime(lambda m, p: (403, {}))
    with pytest.raises(DockerError):
        runtime.list_sandboxes("jarvis-sandbox-")


def test_http_tolerates_non_json_body(monkeypatch):
    class _Resp:
        status = 200
        def read(self):
            return b"raw-stream-bytes"
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False

    import jarvis.docker_runtime as mod
    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda *a, **k: _Resp())
    assert mod.DockerRuntime("http://x")._call("POST", "/exec/e1/start", {"Detach": True}) == {}


def test_create_passes_proxy_env():
    runtime, calls = _runtime(lambda m, p: (201, {"Id": "abc"}) if "create" in p else (204, {}))
    spec = dict(SPEC, env={"HTTP_PROXY": "http://allowlist-proxy:3128"})
    runtime.create_sandbox(spec)
    create = next(c for c in calls if "/containers/create" in c[1])
    assert create[2]["Env"] == ["HTTP_PROXY=http://allowlist-proxy:3128"]
