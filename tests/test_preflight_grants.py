"""Offline regression tests for the grants preflight."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "agent" / "preflight_grants.py"


def _run(env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        env={**env, "JARVIS_REPO_ROOT": str(SCRIPT.parents[2])},
        capture_output=True, text=True, check=False,
    )


def test_preflight_fails_without_owner_and_request_token(tmp_path):
    result = _run({"JARVIS_OWNER_USER_ID": "", "JARVIS_AGENT_REQUEST_TOKEN": ""})
    assert result.returncode != 0
    assert "JARVIS_OWNER_USER_ID is missing" in result.stdout
    assert "JARVIS_AGENT_REQUEST_TOKEN missing" in result.stdout


def test_preflight_rejects_shared_tokens(tmp_path):
    result = _run({"JARVIS_OWNER_USER_ID": "owner", "JARVIS_AGENT_REQUEST_TOKEN": "x" * 24,
                   "GITHUB_TOKEN": "x" * 24})
    assert result.returncode != 0
    assert "must not equal" in result.stdout


def test_preflight_passes_with_minimal_valid_config(tmp_path):
    result = _run({"JARVIS_OWNER_USER_ID": "owner", "JARVIS_AGENT_REQUEST_TOKEN": "a" * 24,
                   "RUNPOD_ALLOW_BILLABLE_ACTIONS": "false"})
    assert result.returncode == 0
    assert "Preflight ok" in result.stdout
