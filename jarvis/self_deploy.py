"""Self-Deploy: Jarvis deployt eigene Aenderungen mit Health-Check + Rollback (5.3).

Deploy auf ein echtes System ist **T2**: der Agent darf es nie selbst
freigeben. Der Besitzer kann es per stehender Freigabe decken oder den
Admin-Endpunkt ausloesen (dann ist der Klick die Freigabe). Kritische Dienste
(``runpod-controller``, ``searxng``) sind gesperrt. Der Befehls-Runner und der
Health-Check sind injizierbar -> ohne echtes Deploy testbar.
"""
from __future__ import annotations

import os
import shlex
import time
import urllib.request
from dataclasses import dataclass, field

from .capabilities import authorize_action
from .zones import authorize_service, load_zones


class DeployError(RuntimeError):
    """Deploy verletzt die Policy oder braucht eine Freigabe."""


@dataclass
class DeployResult:
    ok: bool
    service: str
    steps: list[str] = field(default_factory=list)
    rolled_back: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return {"ok": self.ok, "service": self.service, "rolled_back": self.rolled_back,
                "reason": self.reason, "steps": self.steps}


def _env_command(name: str, default: list[str]) -> list[str]:
    configured = os.getenv(name, "").strip()
    return shlex.split(configured) if configured else list(default)


def default_health_check(url: str, timeout: float = 3.0):
    def check() -> bool:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return 200 <= response.status < 300
        except Exception:  # noqa: BLE001
            return False
    return check


class SelfDeployer:
    def __init__(self, run, *, zones: dict | None = None, health_check=None,
                 deploy_command: list[str] | None = None, rollback_command: list[str] | None = None,
                 attempts: int = 15, delay: float = 2.0, sleep=time.sleep, grant_store=None):
        self.run = run
        self.zones = zones if zones is not None else load_zones()
        self.health_check = health_check or default_health_check(
            os.getenv("JARVIS_HEALTH_URL", "http://127.0.0.1:8100/health"))
        self.deploy_command = deploy_command or _env_command(
            "JARVIS_DEPLOY_COMMAND", ["bash", "scripts/update.sh"])
        self.rollback_command = rollback_command or _env_command(
            "JARVIS_ROLLBACK_COMMAND", ["bash", "scripts/rollback.sh"])
        self.attempts = attempts
        self.delay = delay
        self.sleep = sleep
        self.grant_store = grant_store

    def deploy(self, service: str = "jarvis", *, approved: bool = False,
               standing_grant: dict | None = None, actor: str = "agent") -> DeployResult:
        allowed, info = authorize_service(service, self.zones)
        if not allowed:
            raise DeployError(info)
        if not approved:
            grant = standing_grant
            if grant is None and self.grant_store is not None:
                try:
                    grant = self.grant_store.match_standing_grant("jarvis.deploy", service)
                except Exception:  # noqa: BLE001
                    grant = None
            decision = authorize_action("jarvis.deploy", target=service, standing_grant=grant)
            if decision.decision != "allow":
                raise DeployError(f"Freigabe erforderlich: {decision.reason}")
            if grant is not None and decision.tier == "T2" and self.grant_store is not None:
                try:
                    self.grant_store.consume_standing_grant(grant["id"])
                except Exception:  # noqa: BLE001
                    pass
        steps = [f"authorize jarvis.deploy target={service} by={actor}"]
        rc, _ = self.run(self.deploy_command)
        steps.append(f"deploy rc={int(rc)}")
        if rc != 0:
            return self._rollback(steps, service, "Deploy-Befehl fehlgeschlagen")
        if not self._wait_healthy():
            return self._rollback(steps, service, "Health-Check fehlgeschlagen")
        steps.append("health ok")
        return DeployResult(True, service, steps, False, "ok")

    def _wait_healthy(self) -> bool:
        for _ in range(max(1, self.attempts)):
            if self.health_check():
                return True
            self.sleep(self.delay)
        return False

    def _rollback(self, steps: list[str], service: str, reason: str) -> DeployResult:
        rc, _ = self.run(self.rollback_command)
        steps.append(f"rollback rc={int(rc)}")
        return DeployResult(False, service, steps, True, reason)
