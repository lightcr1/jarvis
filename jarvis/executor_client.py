"""Client fuer den Executor-Dienst (Plan 4.2/5.1).

Damit ruft Jarvis Sandbox-Aktionen nicht direkt, sondern ueber den Executor an
(der einzige mit Laufzeit-Zugriff). Ohne ``JARVIS_EXECUTOR_URL``/
``JARVIS_AGENT_REQUEST_TOKEN`` ist kein Client konfiguriert (``from_env`` -> None),
und die Tools melden das freundlich.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class ExecutorError(RuntimeError):
    """Der Executor hat einen Fehler geliefert oder ist nicht erreichbar."""


class ExecutorClient:
    def __init__(self, base_url: str, token: str, *, transport=None, timeout: float = 30.0):
        self.base_url = str(base_url).rstrip("/")
        self.token = str(token)
        self.timeout = timeout
        self._transport = transport or self._http

    @classmethod
    def from_env(cls, env: dict | None = None) -> "ExecutorClient | None":
        source = os.environ if env is None else env
        url = str(source.get("JARVIS_EXECUTOR_URL", "") or "").strip()
        token = str(source.get("JARVIS_AGENT_REQUEST_TOKEN", "") or "").strip()
        if not url or not token:
            return None
        return cls(url, token)

    # ---- Transport ------------------------------------------------------
    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        status, data = self._transport(method, path, body)
        if status >= 400:
            detail = data.get("detail") if isinstance(data, dict) else None
            raise ExecutorError(detail or f"{method} {path} -> HTTP {status}")
        return data if isinstance(data, dict) else {}

    def _http(self, method: str, path: str, body: dict | None):
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(self.base_url + path, data=payload, method=method)
        request.add_header("X-Jarvis-Agent-Request-Token", self.token)
        if payload is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                try:
                    data = json.loads(raw) if raw.strip() else {}
                except json.JSONDecodeError:
                    data = {}
                return response.status, data
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                data = {}
            return exc.code, data
        except Exception as exc:  # noqa: BLE001
            raise ExecutorError(str(exc)) from exc

    # ---- API ------------------------------------------------------------
    def health(self) -> dict:
        return self._call("GET", "/health")

    def list(self) -> list[dict]:
        return list(self._call("GET", "/sandboxes").get("sandboxes") or [])

    def create(self, image: str, command: str = "") -> dict:
        return self._call("POST", "/sandboxes", {"image": image, "command": command})

    def destroy(self, name: str) -> dict:
        return self._call("DELETE", f"/sandboxes/{name}")

    def run(self, name: str, command: str) -> dict:
        return self._call("POST", f"/sandboxes/{name}/exec", {"command": command})

    def reap(self) -> list[str]:
        return list(self._call("POST", "/sandboxes/reap").get("reaped") or [])
