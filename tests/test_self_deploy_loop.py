"""Tests fuer den host-seitigen Self-Deploy-Loop (Marker-Logik, ohne Docker)."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOOP = ROOT / "scripts" / "agent" / "self_deploy_loop.sh"


def _run(marker: Path, env_extra: dict | None = None):
    env = {"PATH": "/usr/bin:/bin", "SELF_DEPLOY_MARKER": str(marker),
           "SELF_DEPLOY_ENV": str(marker.parent / "does-not-exist.env")}
    env.update(env_extra or {})
    return subprocess.run(["bash", str(LOOP)], cwd=ROOT, capture_output=True, text=True, env=env)


def test_without_marker_is_a_noop(tmp_path):
    proc = _run(tmp_path / "missing-marker")
    assert proc.returncode == 0
    assert "nichts zu tun" in proc.stdout


def test_marker_without_config_fails_safely_and_clears_marker(tmp_path):
    marker = tmp_path / "self-deploy-requested"
    marker.write_text("", encoding="utf-8")
    proc = _run(marker)
    # Ohne Compose-Konfiguration schlaegt der Deploy fehl -> Rollback -> rc 1.
    assert proc.returncode == 1
    assert not marker.exists()          # Marker wird immer aufgeraeumt
