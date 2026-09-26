"""Docker-Runtime fuer den Executor: spricht mit einem **eingeschraenkten**
Socket-Proxy, nie mit dem rohen ``docker.sock`` (Plan 4.2).

Der Proxy (siehe ``deploy/sandbox/``) erlaubt nur Container-/Image-/Netz-Operationen
und nichts anderes -- so kann der Executor keine bestehenden Dienste
(``runpod-controller``, ``searxng``, ``jarvis-app`` ...) anfassen. Der Transport ist
injizierbar, damit die Logik ohne Docker testbar ist.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request


class DockerError(RuntimeError):
    """Die Docker-API hat einen Fehler geliefert."""


class DockerRuntime:
    def __init__(self, base_url: str, *, transport=None, timeout: float = 30.0):
        self.base_url = str(base_url).rstrip("/")
        self.timeout = timeout
        self._transport = transport or self._http

    # ---- Transport ------------------------------------------------------
    def _http(self, method: str, path: str, body: dict | None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(self.base_url + path, data=data, method=method)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8", errors="replace")
                try:
                    data = json.loads(payload) if payload.strip() else {}
                except json.JSONDecodeError:
                    data = {}  # z.B. roher Exec-Stream: kein Fehler
                return response.status, data
        except urllib.error.HTTPError as exc:
            return exc.code, {}
        except Exception as exc:  # noqa: BLE001
            raise DockerError(str(exc)) from exc

    def _call(self, method: str, path: str, body: dict | None = None, *, ok=(200, 201, 204, 304)):
        status, data = self._transport(method, path, body)
        if status not in ok:
            raise DockerError(f"{method} {path} -> HTTP {status}")
        return data if data is not None else {}

    # ---- SandboxRuntime-Protokoll --------------------------------------
    def list_sandboxes(self, prefix: str) -> list[dict]:
        containers = self._call("GET", "/containers/json?all=1")
        result = []
        for container in containers if isinstance(containers, list) else []:
            names = [str(n).lstrip("/") for n in (container.get("Names") or [])]
            name = next((n for n in names if n.startswith(prefix)), None)
            if not name:
                continue
            result.append({"name": name, "id": container.get("Id"),
                           "image": container.get("Image"), "state": container.get("State")})
        return result

    def create_sandbox(self, spec: dict) -> dict:
        payload = {
            "Image": spec["image"],
            "Labels": dict(spec.get("labels") or {}),
            "HostConfig": self._host_config(spec),
        }
        if spec.get("command"):
            payload["Cmd"] = ["sh", "-lc", str(spec["command"])]
        name = urllib.parse.quote(str(spec["name"]), safe="")
        created = self._call("POST", f"/containers/create?name={name}", payload)
        created = created if isinstance(created, dict) else {}
        container_id = str(created.get("Id") or "")
        self._call("POST", f"/containers/{container_id}/start")
        return {"name": spec["name"], "id": container_id, "image": spec["image"],
                "state": "running"}

    def destroy_sandbox(self, name: str) -> None:
        container = urllib.parse.quote(str(name), safe="")
        self._call("POST", f"/containers/{container}/stop?t=5")
        self._call("DELETE", f"/containers/{container}?force=1")

    def exec_in_sandbox(self, name: str, command: str) -> dict:
        container = urllib.parse.quote(str(name), safe="")
        created = self._call("POST", f"/containers/{container}/exec",
                             {"Cmd": ["sh", "-lc", str(command)],
                              "AttachStdout": True, "AttachStderr": True})
        exec_id = str(created.get("Id") or "")
        # Detached starten (kein roher Multiplex-Stream), dann den Exitcode pollen.
        self._call("POST", f"/exec/{exec_id}/start", {"Detach": True, "Tty": False})
        info: dict = {}
        for _ in range(120):
            info = self._call("GET", f"/exec/{exec_id}/json")
            if not info.get("Running"):
                break
            time.sleep(0.25)
        return {"exit_code": info.get("ExitCode"), "running": bool(info.get("Running"))}

    # ---- Hostconfig aus der Zonen-Spec ---------------------------------
    @staticmethod
    def _host_config(spec: dict) -> dict:
        return {
            "NetworkMode": spec.get("network"),
            "CapDrop": list(spec.get("cap_drop") or ["ALL"]),
            "ReadonlyRootfs": bool(spec.get("read_only")),
            "Memory": int(float(spec.get("memory_mb") or 0)) * 1024 * 1024,
            "NanoCpus": int(float(spec.get("cpus") or 0) * 1_000_000_000),
            "PidsLimit": int(spec.get("pids_limit") or 0),
            "SecurityOpt": ["no-new-privileges"],
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,size=256m"},
            "AutoRemove": False,
        }
