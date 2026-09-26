"""Executor-Dienst: die einzige Stelle mit Zugriff auf die Sandbox-Laufzeit (4.2).

Der Agent spricht ausschliesslich ueber diesen Dienst und haelt **keine**
Schluessel. Der Dienst laeuft standardmaessig **deaktiviert**
(``JARVIS_EXECUTOR_ENABLED=1`` zum Scharfschalten) und redet nur mit dem
eingeschraenkten Docker-Socket-Proxy.

Sicherheit: Token-Vergleich mit ``compare_digest``, Audit-Log, Not-Aus
(``JARVIS_EMERGENCY_STOP``) und ein Hintergrund-Reaper, der Sandboxen nach ihrer
max. Laufzeit automatisch entfernt.

Start (im Container):
    uvicorn app:app --host 0.0.0.0 --port 8120
"""
from __future__ import annotations

import hmac
import json
import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from jarvis.docker_runtime import DockerError
from jarvis.runtime_factory import build_sandbox_runtime
from jarvis.executor import Executor, SandboxError

app = FastAPI(title="jarvis-executor", version="0.2.0")

_EXECUTOR_OVERRIDE: Executor | None = None
_REAPER_STARTED = False


def set_executor(executor: Executor | None) -> None:
    """Test-/DI-Hook: ersetzt den aus der Umgebung gebauten Executor."""
    global _EXECUTOR_OVERRIDE
    _EXECUTOR_OVERRIDE = executor


def enabled() -> bool:
    return os.getenv("JARVIS_EXECUTOR_ENABLED", "0").strip() == "1"


def _audit(event: str, detail: dict) -> None:
    path = Path(os.getenv("JARVIS_EXECUTOR_AUDIT_LOG", "/var/lib/jarvis/executor-audit.log"))
    line = json.dumps({"ts": int(time.time()), "event": event, "detail": detail},
                      ensure_ascii=False)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:  # noqa: BLE001 - Audit darf die Aktion nie brechen
        pass


def _auth(token: str | None) -> None:
    expected = os.getenv("JARVIS_AGENT_REQUEST_TOKEN", "").strip()
    if not expected or not token or not hmac.compare_digest(str(token), expected):
        raise HTTPException(401, "unauthorized")


def _grant_store():
    """Stehende Freigaben, falls die DB geteilt ist (JARVIS_GRANTS_DB)."""
    path = os.getenv("JARVIS_GRANTS_DB", "").strip()
    if not path:
        return None
    try:
        from jarvis.agent_grants import AgentGrantStore
        return AgentGrantStore(path)
    except Exception:  # noqa: BLE001
        return None


def get_executor() -> Executor:
    if _EXECUTOR_OVERRIDE is not None:
        return _EXECUTOR_OVERRIDE
    if not enabled():
        raise HTTPException(503, "executor disabled")
    runtime = build_sandbox_runtime()
    return Executor(runtime,
                    host_cpus=float(os.getenv("JARVIS_HOST_CPUS", "4")),
                    host_memory_mb=float(os.getenv("JARVIS_HOST_MEMORY_MB", "16384")),
                    audit=_audit, grant_store=_grant_store())


def _reaper_loop() -> None:
    interval = int(os.getenv("JARVIS_EXECUTOR_REAP_SECONDS", "120") or "0")
    if interval <= 0:
        return
    while True:
        time.sleep(interval)
        if not enabled():
            continue
        try:
            get_executor().reap_expired()
        except Exception:  # noqa: BLE001 - Reaper ist best-effort
            pass


@app.on_event("startup")
def _start_reaper() -> None:
    global _REAPER_STARTED
    if _REAPER_STARTED:
        return
    _REAPER_STARTED = True
    threading.Thread(target=_reaper_loop, daemon=True).start()


class SandboxCreate(BaseModel):
    image: str = Field(max_length=200)
    command: str = Field(default="", max_length=2000)


class SandboxExec(BaseModel):
    command: str = Field(max_length=2000)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "executor", "enabled": enabled(),
            "emergency_stop": get_executor().emergency_stop_active() if enabled() else None}


@app.get("/sandboxes")
def list_sandboxes(x_jarvis_agent_request_token: str | None = Header(default=None)) -> dict:
    _auth(x_jarvis_agent_request_token)
    return {"sandboxes": get_executor().list_sandboxes()}


@app.post("/sandboxes", status_code=201)
def create_sandbox(body: SandboxCreate,
                   x_jarvis_agent_request_token: str | None = Header(default=None)) -> dict:
    _auth(x_jarvis_agent_request_token)
    try:
        return get_executor().create(image=body.image, command=body.command)
    except SandboxError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/sandboxes/reap")
def reap_sandboxes(x_jarvis_agent_request_token: str | None = Header(default=None)) -> dict:
    _auth(x_jarvis_agent_request_token)
    return {"reaped": get_executor().reap_expired()}


@app.delete("/sandboxes/{name}")
def destroy_sandbox(name: str,
                    x_jarvis_agent_request_token: str | None = Header(default=None)) -> dict:
    _auth(x_jarvis_agent_request_token)
    try:
        return get_executor().destroy(name)
    except SandboxError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/sandboxes/{name}/exec")
def exec_sandbox(name: str, body: SandboxExec,
                 x_jarvis_agent_request_token: str | None = Header(default=None)) -> dict:
    _auth(x_jarvis_agent_request_token)
    try:
        return get_executor().run(name, body.command)
    except DockerError as exc:
        raise HTTPException(502, str(exc)) from exc
    except SandboxError as exc:
        raise HTTPException(409, str(exc)) from exc
