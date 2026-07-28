from __future__ import annotations

from typing import Callable

# Shared by PolicyEngine (self-healing) and PlaybookExecutor (maintenance steps) so the
# actual restart mechanics exist in exactly one place — the same systemctl invocations
# already used by assistant_domain.py's `restart <svc>` / `status <svc>` chat skills.

RunCmd = Callable[..., str]
EnsureServiceAllowed = Callable[[str], None]


def read_service_active(service: str, *, run_cmd: RunCmd) -> str:
    """Mirrors the `is-active` check already used by the restart/status chat skills."""
    return run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8).strip()


def restart_service(service: str, *, run_cmd: RunCmd, ensure_service_allowed: EnsureServiceAllowed) -> dict:
    """Restarts `service` via systemctl and reports its resulting active-state.

    Raises whatever `ensure_service_allowed` raises (HTTPException(400/403) in practice)
    if the service name is invalid or not on the configured allowlist — callers must not
    swallow that silently, since it's the same allowlist gate the interactive chat skill
    relies on.
    """
    ensure_service_allowed(service)
    run_cmd(["/usr/bin/sudo", "/bin/systemctl", "restart", service], timeout=15)
    active = read_service_active(service, run_cmd=run_cmd)
    return {"service": service, "active": active, "healthy": active == "active"}
