"""Tests fuer das Proxmox-Backend (Review-Punkt 1), mit Fake-Transport."""
from __future__ import annotations

from jarvis.proxmox_runtime import ProxmoxError, ProxmoxRuntime


def _runtime(handler):
    calls = []
    def transport(method, path, body=None):
        calls.append((method, path, body))
        return handler(method, path, body)
    return ProxmoxRuntime("https://pve:8006", "root@pam!jarvis", "sec", "pve",
                          template_id=9000, transport=transport), calls


def test_from_env():
    assert ProxmoxRuntime.from_env({}) is None
    rt = ProxmoxRuntime.from_env({"JARVIS_PROXMOX_URL": "https://pve:8006/",
                                  "JARVIS_PROXMOX_TOKEN_ID": "a", "JARVIS_PROXMOX_TOKEN_SECRET": "b",
                                  "JARVIS_PROXMOX_NODE": "pve", "JARVIS_PROXMOX_TEMPLATE": "9000"})
    assert rt is not None and rt.template_id == 9000


def test_list_filters_prefix():
    vms = [{"vmid": 101, "name": "jarvis-sandbox-a", "status": "running"},
           {"vmid": 102, "name": "other-vm", "status": "stopped"}]
    rt, _ = _runtime(lambda m, p, b: (200, {"data": vms}))
    names = [v["name"] for v in rt.list_sandboxes("jarvis-sandbox-")]
    assert names == ["jarvis-sandbox-a"]


def test_create_clone_config_start():
    def handler(m, p, b):
        if p.endswith("/qemu") and m == "GET":
            return 200, {"data": []}
        return 200, {"data": {"upid": "x"}}
    rt, calls = _runtime(handler)
    out = rt.create_sandbox({"name": "jarvis-sandbox-x", "memory_mb": 2048, "cpus": 1})
    assert out["name"] == "jarvis-sandbox-x" and out["id"] == 9100
    assert ("POST", "/api2/json/nodes/pve/qemu/9000/clone",
            {"newid": 9100, "name": "jarvis-sandbox-x", "pool": "jarvis-sandbox", "full": 1}) in calls
    assert any(c[1].endswith("/qemu/9100/config") and c[2] == {"memory": 2048} for c in calls)
    assert ("POST", "/api2/json/nodes/pve/qemu/9100/status/start", None) in calls


def test_destroy_stop_and_delete():
    def handler(m, p, b):
        if m == "GET":
            return 200, {"data": [{"vmid": 101, "name": "jarvis-sandbox-x", "status": "running"}]}
        return 200, {"data": None}
    rt, calls = _runtime(handler)
    rt.destroy_sandbox("jarvis-sandbox-x")
    assert ("POST", "/api2/json/nodes/pve/qemu/101/status/stop", None) in calls
    assert ("DELETE", "/api2/json/nodes/pve/qemu/101", None) in calls


def test_exec_and_snapshot_rollback():
    def handler(m, p, b):
        if m == "GET" and p.endswith("/qemu"):
            return 200, {"data": [{"vmid": 101, "name": "jarvis-sandbox-x"}]}
        if "agent/exec-status" in p:
            return 200, {"data": {"exitcode": 0, "exited": True}}
        if "agent/exec" in p:
            return 200, {"data": {"pid": 42}}
        return 200, {"data": None}
    rt, calls = _runtime(handler)
    assert rt.exec_in_sandbox("jarvis-sandbox-x", "echo hi")["exit_code"] == 0
    rt.snapshot(101, "pre-change")
    rt.rollback(101, "pre-change")
    assert any("snapshot" in c[1] and c[2] == {"snapname": "pre-change"} for c in calls)
    assert any("snapshot/pre-change/rollback" in c[1] for c in calls)


def test_error_status_raises():
    rt, _ = _runtime(lambda m, p, b: (403, {}))
    try:
        rt.list_sandboxes("jarvis-sandbox-")
    except ProxmoxError:
        pass
    else:  # pragma: no cover
        raise AssertionError("403 must raise")
