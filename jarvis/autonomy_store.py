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
import time
from pathlib import Path


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
        }

    def set_mode(self, enabled: bool, actor: str, note: str = "") -> dict:
        """Persist the switch; returns the new status."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "enabled": bool(enabled),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "updated_by": actor,
            "note": note,
        }
        self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return self.status()

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
