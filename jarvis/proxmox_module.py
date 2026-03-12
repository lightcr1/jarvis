from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class ProxmoxHost:
    id: str
    name: str
    base_url: str
    api_token: str
    verify_tls: bool
    created_at: float


class ProxmoxHostIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    base_url: str = Field(..., min_length=5, max_length=200)
    api_token: str = Field(..., min_length=10, max_length=500)
    verify_tls: bool = True


class ProxmoxHostOut(BaseModel):
    id: str
    name: str
    base_url: str
    token_hint: str
    verify_tls: bool
    created_at: float


def _hosts_file_path() -> str:
    return os.getenv("PROXMOX_HOSTS_FILE") or "proxmox_hosts.json"


def _read_hosts() -> list[ProxmoxHost]:
    path = _hosts_file_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f) or []
    except json.JSONDecodeError as exc:
        raise HTTPException(500, f"Invalid proxmox host store: {exc}") from exc
    hosts = []
    for item in raw:
        try:
            hosts.append(
                ProxmoxHost(
                    id=item["id"],
                    name=item["name"],
                    base_url=item["base_url"],
                    api_token=item["api_token"],
                    verify_tls=bool(item.get("verify_tls", True)),
                    created_at=float(item.get("created_at", 0)),
                )
            )
        except KeyError:
            continue
    return hosts


def _write_hosts(hosts: list[ProxmoxHost]) -> None:
    path = _hosts_file_path()
    payload = [
        {
            "id": h.id,
            "name": h.name,
            "base_url": h.base_url,
            "api_token": h.api_token,
            "verify_tls": h.verify_tls,
            "created_at": h.created_at,
        }
        for h in hosts
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def _token_hint(token: str) -> str:
    if len(token) <= 10:
        return "***"
    return f"{token[:6]}…{token[-4:]}"


def _ssl_context(verify_tls: bool) -> ssl.SSLContext:
    if verify_tls:
        return ssl.create_default_context()
    return ssl._create_unverified_context()


def _request_json(host: ProxmoxHost, path: str) -> dict:
    url = host.base_url.rstrip("/") + path
    headers = {"Authorization": f"PVEAPIToken={host.api_token}"}
    req = urllib.request.Request(url, headers=headers)
    try:
        ctx = _ssl_context(host.verify_tls)
        with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
            data = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8") if exc.fp else ""
        raise HTTPException(exc.code, f"Proxmox error: {body or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(502, f"Proxmox unreachable: {exc.reason}") from exc
    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        raise HTTPException(502, f"Proxmox invalid JSON: {exc}") from exc


def _get_host(host_id: str) -> ProxmoxHost:
    for host in _read_hosts():
        if host.id == host_id:
            return host
    raise HTTPException(404, "Proxmox host not found")


def proxmox_vm_status(host_id: str, node: str, vmid: str) -> dict:
    host = _get_host(host_id)
    return _request_json(host, f"/api2/json/nodes/{node}/qemu/{vmid}/status/current")


def proxmox_lxc_status(host_id: str, node: str, vmid: str) -> dict:
    host = _get_host(host_id)
    return _request_json(host, f"/api2/json/nodes/{node}/lxc/{vmid}/status/current")


def _as_out(host: ProxmoxHost) -> ProxmoxHostOut:
    return ProxmoxHostOut(
        id=host.id,
        name=host.name,
        base_url=host.base_url,
        token_hint=_token_hint(host.api_token),
        verify_tls=host.verify_tls,
        created_at=host.created_at,
    )


def build_router(require_token):
    router = APIRouter(prefix="/proxmox", tags=["proxmox"])

    @router.get("/hosts", response_model=list[ProxmoxHostOut])
    def list_hosts():
        return [_as_out(h) for h in _read_hosts()]

    @router.post("/hosts", response_model=ProxmoxHostOut)
    def add_host(payload: ProxmoxHostIn, authorization: str | None = Header(default=None)):
        require_token(authorization)
        hosts = _read_hosts()
        host = ProxmoxHost(
            id=uuid.uuid4().hex,
            name=payload.name.strip(),
            base_url=payload.base_url.strip(),
            api_token=payload.api_token.strip(),
            verify_tls=payload.verify_tls,
            created_at=time.time(),
        )
        test = _request_json(host, "/api2/json/version")
        if "data" not in test:
            raise HTTPException(502, "Proxmox API validation failed")
        hosts.append(host)
        _write_hosts(hosts)
        return _as_out(host)

    @router.delete("/hosts/{host_id}")
    def delete_host(host_id: str, authorization: str | None = Header(default=None)):
        require_token(authorization)
        hosts = [h for h in _read_hosts() if h.id != host_id]
        _write_hosts(hosts)
        return {"ok": True}

    @router.get("/hosts/{host_id}/version")
    def proxmox_version(host_id: str):
        host = _get_host(host_id)
        return _request_json(host, "/api2/json/version")

    @router.get("/hosts/{host_id}/nodes")
    def proxmox_nodes(host_id: str):
        host = _get_host(host_id)
        return _request_json(host, "/api2/json/nodes")

    @router.get("/hosts/{host_id}/nodes/{node}/vms")
    def proxmox_vms(host_id: str, node: str):
        host = _get_host(host_id)
        return _request_json(host, f"/api2/json/nodes/{node}/qemu")

    @router.get("/hosts/{host_id}/nodes/{node}/containers")
    def proxmox_containers(host_id: str, node: str):
        host = _get_host(host_id)
        return _request_json(host, f"/api2/json/nodes/{node}/lxc")

    @router.get("/hosts/{host_id}/nodes/{node}/storage")
    def proxmox_storage(host_id: str, node: str):
        host = _get_host(host_id)
        return _request_json(host, f"/api2/json/nodes/{node}/storage")

    @router.get("/hosts/{host_id}/nodes/{node}/vms/{vmid}/status")
    def proxmox_vm_status_endpoint(host_id: str, node: str, vmid: str):
        return proxmox_vm_status(host_id, node, vmid)

    @router.get("/hosts/{host_id}/nodes/{node}/containers/{vmid}/status")
    def proxmox_lxc_status_endpoint(host_id: str, node: str, vmid: str):
        return proxmox_lxc_status(host_id, node, vmid)

    return router
