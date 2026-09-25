"""Executor-Dienst: die einzige Stelle mit Zugriff auf die Sandbox-Laufzeit (4.2).

Der Agent spricht ausschliesslich ueber diesen Dienst und haelt **keine**
Schluessel. Der Dienst laeuft standardmaessig **deaktiviert**
(``JARVIS_EXECUTOR_ENABLED=1`` zum Scharfschalten) und redet nur mit dem
eingeschraenkten Docker-Socket-Proxy.

Start (im Container):
    uvicorn app:app --host 0.0.0.0 --port 8120
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from jarvis.docker_runtime import DockerError, DockerRuntime
from jarvis.executor import Executor, SandboxError

app = FastAPI(title="jarvis-executor", version="0.1.0")

_EXECUTOR_OVERRIDE: Executor | None = None


def set_executor(executor: Executor | None) -> None:
    """Test-/DI-Hook: ersetzt den aus der Umgebung gebauten Executor."""
    global _EXECUTOR_OVERRIDE
    _EXECUTOR_OVERRIDE = executor


def enabled() -> bool:
    return os.getenv("JARVIS_EXECUTOR_ENABLED", "0").strip() == "1"


def _auth(token: str | None) -> None:
    expected = os.getenv("JARVIS_AGENT_REQUEST_TOKEN", "").strip()
    if not expected or token != expected:
        raise HTTPException(401, "unauthorized")


def get_executor() -> Executor:
    if _EXECUTOR_OVERRIDE is not None:
        return _EXECUTOR_OVERRIDE
    if not enabled():
        raise HTTPException(503, "executor disabled")
    runtime = DockerRuntime(os.getenv("JARVIS_DOCKER_API", "http://docker-socket-proxy:2375"))
    return Executor(runtime,
                    host_cpus=float(os.getenv("JARVIS_HOST_CPUS", "4")),
                    host_memory_mb=float(os.getenv("JARVIS_HOST_MEMORY_MB", "16384")))


class SandboxCreate(BaseModel):
    image: str = Field(max_length=200)
    command: str = Field(default="", max_length=2000)


class SandboxExec(BaseModel):
    command: str = Field(max_length=2000)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "executor", "enabled": enabled()}


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
