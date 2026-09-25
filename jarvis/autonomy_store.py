"""File-based autonomy switch for Jarvis.

The switch is stored as `config/autonomy.json` inside the repository
workspace (gitignored), so both the Jarvis web UI and the coding agent
(OpenHands, which works in the repo clone) see the same value. The agent
reads it from AGENTS.md instructions and must not start autonomous rounds
while it is disabled. Missing file = enabled (default).
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path


def _valid_window(window: str) -> bool:
    return bool(re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d-(?:[01]\d|2[0-3]):[0-5]\d", str(window)))


def default_autonomy_path() -> Path:
    """Repository-root-relative config file, overridable via env."""
    configured = os.getenv("JARVIS_AUTONOMY_FILE")
    if configured:
        return Path(configured)
    # AGENTS.md tells the agent to check this exact relative path.
    here = Path(__file__).resolve()
    repo_root = here.parents[1]
    return repo_root / "config" / "autonomy.json"


class AutonomyStore:
    """Reads/writes the autonomy switch used by the Jarvis web UI."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_autonomy_path()

    def status(self) -> dict:
        data = self._load()
        enabled = data.get("enabled", True)
        return {
            "enabled": enabled,
            "updated_at": data.get("updated_at"),
            "note": data.get("note", ""),
            "max_gpu_hours_per_day": data.get("max_gpu_hours_per_day"),
            "allowed_windows": data.get("allowed_windows", []),
            "max_rounds_per_pod_session": data.get("max_rounds_per_pod_session"),
        }

    def policy(self) -> dict:
        """Budgets/Zeitfenster fuer den Loop (5.3); None/[] = unbegrenzt."""
        data = self._load()
        return {
            "max_gpu_hours_per_day": data.get("max_gpu_hours_per_day"),
            "allowed_windows": data.get("allowed_windows", []),
            "max_rounds_per_pod_session": data.get("max_rounds_per_pod_session"),
        }

    def set_mode(self, enabled: bool, actor: str, note: str = "") -> dict:
        """Persist the switch; returns the new status."""
        data = self._load()
        data.update({
            "enabled": bool(enabled),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "updated_by": actor,
            "note": note,
        })
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return self.status()

    def set_policy(self, *, actor: str, max_gpu_hours_per_day=None,
                   allowed_windows=None, max_rounds_per_pod_session=None) -> dict:
        """Merge budget/window fields; None leaves the current value unchanged."""
        data = self._load()
        if max_gpu_hours_per_day is not None:
            value = float(max_gpu_hours_per_day)
            if value <= 0 or value > 24 * 31:
                raise ValueError("max_gpu_hours_per_day out of range")
            data["max_gpu_hours_per_day"] = value
        if allowed_windows is not None:
            windows = []
            for window in allowed_windows:
                if not _valid_window(window):
                    raise ValueError("allowed_windows must be HH:MM-HH:MM")
                windows.append(window)
            data["allowed_windows"] = windows
        if max_rounds_per_pod_session is not None:
            value = int(max_rounds_per_pod_session)
            if value < 0 or value > 1000:
                raise ValueError("max_rounds_per_pod_session out of range")
            data["max_rounds_per_pod_session"] = value
        data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        data["updated_by"] = actor
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return self.status()

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
