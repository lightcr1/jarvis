"""Pod-Start (Verfuegbarkeit, Review-Punkt 2a).

`pod.start` ist **T3**: Jarvis startet den Pod nur nach ausdruecklicher Freigabe
(Push, mit TOTP, falls aktiviert) und nur innerhalb eines Monatsbudgets. Der
Controller (runpod) bietet `POST /api/pod/start`.
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request


class PodError(RuntimeError):
    """Pod-Aktion fehlgeschlagen oder Budget ueberschritten."""


def estimate_cost_chf(cost_per_hour: float, hours: float) -> float:
    return round(max(0.0, float(cost_per_hour or 0) * float(hours or 0)), 2)


def monthly_budget_chf() -> float:
    try:
        return float(os.getenv("JARVIS_POD_MONTHLY_BUDGET_CHF", "0") or 0)
    except ValueError:
        return 0.0


def within_budget(estimated_chf: float, spent_chf: float, cap_chf: float | None = None) -> bool:
    """True nur, wenn ein Budget gesetzt ist und geschaetzt+verbraucht es nicht ueberschreitet."""
    cap = monthly_budget_chf() if cap_chf is None else float(cap_chf)
    if cap <= 0:
        return False
    return float(spent_chf or 0) + float(estimated_chf or 0) <= cap


class PodControl:
    def __init__(self, base_url: str, control_token: str, *, transport=None,
                 ca_file: str = "", timeout: float = 60.0):
        self.base_url = str(base_url).rstrip("/")
        self.control_token = str(control_token)
        self.ca_file = ca_file
        self.timeout = timeout
        self._transport = transport or self._http

    @classmethod
    def from_env(cls, env: dict | None = None) -> "PodControl | None":
        source = os.environ if env is None else env
        url = str(source.get("JARVIS_CONTROLLER_URL", "") or "").strip()
        token = str(source.get("CONTROL_TOKEN", "") or "").strip()
        ca = str(source.get("CONTROLLER_CA_FILE", "") or "").strip()
        if not url or not token:
            return None
        return cls(url, token, ca_file=ca)

    def _http(self, method: str, path: str, body: dict | None):
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(self.base_url + path, data=payload, method=method)
        request.add_header("X-Control-Token", self.control_token)
        if payload is not None:
            request.add_header("Content-Type", "application/json")
        ctx = ssl.create_default_context()
        if self.ca_file and os.path.exists(self.ca_file):
            ctx.load_verify_locations(self.ca_file)
        else:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=ctx) as response:
                raw = response.read().decode("utf-8", errors="replace")
                try:
                    data = json.loads(raw) if raw.strip() else {}
                except json.JSONDecodeError:
                    data = {}
                return response.status, data
        except urllib.error.HTTPError as exc:
            return exc.code, {}
        except Exception as exc:  # noqa: BLE001
            raise PodError(str(exc)) from exc

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        status, data = self._transport(method, path, body)
        if status >= 400:
            raise PodError(f"{method} {path} -> HTTP {status}")
        return data if isinstance(data, dict) else {}

    def start(self, profile: str = "default") -> dict:
        return self._call("POST", "/api/pod/start", {"profile": profile})

    def stop(self) -> dict:
        return self._call("POST", "/api/pod/stop")

    def status(self) -> dict:
        return self._call("GET", "/api/status")
