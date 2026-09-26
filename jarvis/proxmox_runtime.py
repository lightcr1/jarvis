"""Proxmox-Backend fuer den Executor (Review-Punkt 1).

Erzeugt **echte VMs** aus einem Template, fuehrt Befehle ueber den QEMU Guest
Agent aus und loescht sie wieder. Der API-Token darf **nur** Rechte auf den Pool
``jarvis-sandbox`` haben (eigenes VLAN). Fuer die Zone "verwaltet" gibt es
Snapshot/Rollback-Helfer.
"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

from .zones import sandbox_prefix


class ProxmoxError(RuntimeError):
    """Proxmox-API-Fehler."""


class ProxmoxRuntime:
    def __init__(self, base_url: str, token_id: str, token_secret: str, node: str,
                 *, pool: str = "jarvis-sandbox", bridge: str = "vmbr-sandbox",
                 template_id: int | None = None, transport=None,
                 ca_file: str = "", verify_tls: bool = True, timeout: float = 120.0):
        self.base_url = str(base_url).rstrip("/")
        self.token_id = token_id
        self.token_secret = token_secret
        self.node = node
        self.pool = pool
        self.bridge = bridge
        self.template_id = template_id
        self.ca_file = ca_file
        self.verify_tls = verify_tls
        self.timeout = timeout
        self._transport = transport or self._http

    # ---- Transport ------------------------------------------------------
    def _http(self, method: str, path: str, body: dict | None):
        data = urllib.parse.urlencode(body).encode() if body else None
        request = urllib.request.Request(self.base_url + path, data=data, method=method)
        request.add_header("Authorization", f"PVEAPIToken={self.token_id}={self.token_secret}")
        if data is not None:
            request.add_header("Content-Type", "application/x-www-form-urlencoded")
        ctx = ssl.create_default_context()
        if self.ca_file:
            ctx.load_verify_locations(self.ca_file)
        if not self.verify_tls:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=ctx) as response:
                raw = response.read().decode("utf-8", errors="replace")
                try:
                    data_out = json.loads(raw) if raw.strip() else {}
                except json.JSONDecodeError:
                    data_out = {}
                return response.status, data_out
        except urllib.error.HTTPError as exc:
            return exc.code, {}
        except Exception as exc:  # noqa: BLE001
            raise ProxmoxError(str(exc)) from exc

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        status, data = self._transport(method, path, body)
        if status >= 400:
            raise ProxmoxError(f"{method} {path} -> HTTP {status}")
        # Proxmox verpackt Antworten in {"data": ...}
        return data.get("data") if isinstance(data, dict) and "data" in data else data

    def _qemu(self, vmid: int, suffix: str = "") -> str:
        return f"/api2/json/nodes/{self.node}/qemu/{vmid}{suffix}"

    # ---- VM-Inventar ----------------------------------------------------
    def _list_vms(self) -> list[dict]:
        result = self._call("GET", f"/api2/json/nodes/{self.node}/qemu")
        return result if isinstance(result, list) else []

    def _find_vmid(self, name: str) -> int | None:
        for vm in self._list_vms():
            if str(vm.get("name") or "") == name:
                return int(vm.get("vmid"))
        return None

    # ---- SandboxRuntime-Protokoll --------------------------------------
    def list_sandboxes(self, prefix: str | None = None) -> list[dict]:
        prefix = prefix or sandbox_prefix()
        return [{"name": vm.get("name"), "id": vm.get("vmid"), "state": vm.get("status")}
                for vm in self._list_vms() if str(vm.get("name") or "").startswith(prefix)]

    def create_sandbox(self, spec: dict) -> dict:
        if self.template_id is None:
            raise ProxmoxError("kein Template konfiguriert (JARVIS_PROXMOX_TEMPLATE)")
        vmid = int(spec.get("vmid") or self._next_vmid())
        self._call("POST", self._qemu(self.template_id, "/clone"), {
            "newid": vmid, "name": spec["name"], "pool": self.pool, "full": 1,
        })
        if spec.get("memory_mb"):
            self._call("POST", self._qemu(vmid, "/config"), {"memory": int(spec["memory_mb"])})
        if spec.get("cpus"):
            self._call("POST", self._qemu(vmid, "/config"), {"cores": int(spec["cpus"])})
        self._call("POST", self._qemu(vmid, "/status/start"))
        return {"name": spec["name"], "id": vmid, "state": "running"}

    def destroy_sandbox(self, name: str) -> None:
        vmid = self._find_vmid(name)
        if vmid is None:
            return
        try:
            self._call("POST", self._qemu(vmid, "/status/stop"))
        except ProxmoxError:
            pass
        self._call("DELETE", self._qemu(vmid))

    def exec_in_sandbox(self, name: str, command: str) -> dict:
        vmid = self._find_vmid(name)
        if vmid is None:
            raise ProxmoxError(f"VM '{name}' nicht gefunden")
        started = self._call("POST", self._qemu(vmid, "/agent/exec"), {
            "command": ["/bin/sh", "-lc", command],
        })
        pid = (started or {}).get("pid")
        status = self._call("GET", f"{self._qemu(vmid, '/agent/exec-status')}?pid={pid}")
        status = status if isinstance(status, dict) else {}
        return {"exit_code": status.get("exitcode"), "running": bool(status.get("exited") is False)}

    def _next_vmid(self) -> int:
        vms = [int(v.get("vmid") or 0) for v in self._list_vms()]
        return (max(vms) + 1) if vms else 9100

    # ---- Zone "verwaltet": Snapshot/Rollback ---------------------------
    def snapshot(self, vmid: int, name: str) -> dict:
        return self._call("POST", self._qemu(vmid, "/snapshot"), {"snapname": name})

    def rollback(self, vmid: int, name: str) -> dict:
        return self._call("POST", self._qemu(vmid, f"/snapshot/{name}/rollback"))

    @classmethod
    def from_env(cls, env: dict | None = None) -> "ProxmoxRuntime | None":
        import os
        source = os.environ if env is None else env
        url = str(source.get("JARVIS_PROXMOX_URL", "") or "").strip()
        token = str(source.get("JARVIS_PROXMOX_TOKEN_ID", "") or "").strip()
        secret = str(source.get("JARVIS_PROXMOX_TOKEN_SECRET", "") or "").strip()
        node = str(source.get("JARVIS_PROXMOX_NODE", "") or "").strip()
        if not (url and token and secret and node):
            return None
        template = source.get("JARVIS_PROXMOX_TEMPLATE", "")
        return cls(url, token, secret, node,
                   pool=str(source.get("JARVIS_PROXMOX_POOL", "jarvis-sandbox")),
                   bridge=str(source.get("JARVIS_PROXMOX_BRIDGE", "vmbr-sandbox")),
                   template_id=int(template) if str(template).strip().isdigit() else None,
                   ca_file=str(source.get("JARVIS_PROXMOX_CA_FILE", "") or ""),
                   verify_tls=str(source.get("JARVIS_PROXMOX_VERIFY_TLS", "1")) != "0")
