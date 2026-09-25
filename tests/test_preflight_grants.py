"""Offline regression tests for the grants preflight."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "agent" / "preflight_grants.py"


def _write_env(tmp_path: Path, values: dict[str, str]) -> Path:
    path = tmp_path / "jarvis.env"
    path.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n", encoding="utf-8")
    return path


def _run(env_file: Path) -> subprocess.CompletedProcess:
    # Nur eine minimale Umgebung mitgeben: sonst ueberschreiben zufaellig
    # exportierte Variablen (z. B. GITHUB_TOKEN) die Testdatei (Umgebung schlaegt Datei).
    base = subprocess.os.environ
    env = {"JARVIS_REPO_ROOT": str(SCRIPT.parents[2])}
    if base.get("PATH"):
        env["PATH"] = base["PATH"]
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--env", str(env_file)],
        env=env, capture_output=True, text=True, check=False,
    )


def test_preflight_fails_without_owner_and_request_token(tmp_path):
    result = _run(_write_env(tmp_path, {}))
    assert result.returncode != 0
    assert "JARVIS_OWNER_USER_ID is missing" in result.stdout
    assert "JARVIS_AGENT_REQUEST_TOKEN missing" in result.stdout


def test_preflight_rejects_shared_tokens(tmp_path):
    result = _run(_write_env(tmp_path, {"JARVIS_OWNER_USER_ID": "owner",
                                        "JARVIS_AGENT_REQUEST_TOKEN": "x" * 24,
                                        "GITHUB_TOKEN": "x" * 24}))
    assert result.returncode != 0
    assert "must not equal" in result.stdout


def test_preflight_passes_with_minimal_valid_config(tmp_path):
    result = _run(_write_env(tmp_path, {"JARVIS_OWNER_USER_ID": "owner",
                                        "JARVIS_AGENT_REQUEST_TOKEN": "a" * 24,
                                        "RUNPOD_ALLOW_BILLABLE_ACTIONS": "false"}))
    assert result.returncode == 0
    assert "Preflight ok" in result.stdout


def test_env_file_with_shell_fragile_values_is_parsed_safely(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("preflight_grants", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    parsed = module.load_env_file(_write_env(tmp_path, {
        "JARVIS_EMAIL_FROM": "JARVIS <signup@jarvis.com>",
        "WEIRD": 'a "b c" <x> $HOME `touch /tmp/x`',
        "JARVIS_OWNER_USER_ID": "usr-2e4dd47d32cf",
    }))
    assert parsed["JARVIS_EMAIL_FROM"] == "JARVIS <signup@jarvis.com>"
    assert "`touch" in parsed["WEIRD"] and parsed["WEIRD"] == 'a "b c" <x> $HOME `touch /tmp/x`'
    assert parsed["JARVIS_OWNER_USER_ID"] == "usr-2e4dd47d32cf"


def test_preflight_succeeds_even_with_email_line_in_env(tmp_path):
    result = _run(_write_env(tmp_path, {
        "JARVIS_EMAIL_FROM": "JARVIS <signup@jarvis.com>",
        "JARVIS_OWNER_USER_ID": "owner",
        "JARVIS_AGENT_REQUEST_TOKEN": "b" * 24,
        "RUNPOD_ALLOW_BILLABLE_ACTIONS": "false",
    }))
    assert result.returncode == 0
    assert "Preflight ok" in result.stdout
