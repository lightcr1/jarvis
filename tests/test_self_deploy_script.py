"""Test fuer das containerisierte Self-Deploy-Skript (Dry-Run, ohne Docker)."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "agent" / "self_deploy.sh"


def test_dry_run_prints_plan_without_docker():
    proc = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run"],
        cwd=ROOT, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "SELF_DEPLOY_COMPOSE_FILES": "deploy/docker-compose.yml",
             "SELF_DEPLOY_SERVICE": "jarvis", "SELF_DEPLOY_STATE_FILE": "/tmp/self_deploy_test_state"},
    )
    assert proc.returncode == 0, proc.stderr
    assert "[dry-run]" in proc.stdout and "up -d --no-deps jarvis" in proc.stdout


def test_missing_compose_files_is_rejected():
    proc = subprocess.run(["bash", str(SCRIPT), "--dry-run"], cwd=ROOT,
                          capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    assert proc.returncode == 2
