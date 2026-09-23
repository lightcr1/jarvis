#!/usr/bin/env python3
"""Preflight: verify agent-gateway environment before enabling autonomy.

Read-only. Never mutates state, never calls external APIs. Exits nonzero when
the active scoped-grant setup cannot be considered configured.

Reads /home/media/jarvis.env itself (robust KEY=VALUE parse; no shell source,
no sudo needed). Values already exported in the environment win over the file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

OK, WARN, FAIL = "+", "-", "X"

DEFAULT_ENV_FILE = "/home/media/jarvis.env"


def load_env_file(path: str | os.PathLike) -> dict[str, str]:
    """Robust KEY=VALUE parse that tolerates values with spaces, <, >, quotes.

    Unlike `source`, this never executes or interprets the content.
    """
    values: dict[str, str] = {}
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        cleaned = value.strip().strip('"').strip("'")
        values[key] = cleaned
    return values


def check_path(path: str | Path) -> Path:
    return Path(path).expanduser()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=os.getenv("JARVIS_ENV_FILE", DEFAULT_ENV_FILE),
                        help="env file to read (default: $JARVIS_ENV_FILE or %(default)s)")
    args = parser.parse_args()

    merged = {**load_env_file(args.env), **os.environ}
    env_file = str(Path(args.env))
    issues: list[tuple[str, str]] = []
    warnings: list[str] = [f"read env file: {env_file}"] if Path(args.env).exists() else [
        f"env file not found: {env_file} (using current environment only)"]

    owner_id = merged.get("JARVIS_OWNER_USER_ID", "").strip()
    if owner_id:
        issues.append((OK, f"JARVIS_OWNER_USER_ID is set ({owner_id[:24]}...)"))
    else:
        issues.append((FAIL, "JARVIS_OWNER_USER_ID is missing: owner approval endpoints are closed (503)"))

    request_token = merged.get("JARVIS_AGENT_REQUEST_TOKEN", "").strip()
    if len(request_token) >= 16:
        issues.append((OK, "JARVIS_AGENT_REQUEST_TOKEN is set"))
    else:
        issues.append((FAIL, "JARVIS_AGENT_REQUEST_TOKEN missing or too short (>=16 chars required)"))

    if request_token and request_token == merged.get("GITHUB_TOKEN", ""):
        issues.append((FAIL, "agent request token must not equal GITHUB_TOKEN"))
    if request_token and request_token == merged.get("JARVIS_GITHUB_WRITE_TOKEN", ""):
        issues.append((FAIL, "agent request token must not equal JARVIS_GITHUB_WRITE_TOKEN"))
    if request_token and merged.get("MODEL_ACCESS_TOKEN") and request_token == merged.get("MODEL_ACCESS_TOKEN", ""):
        issues.append((FAIL, "agent request token must not equal MODEL_ACCESS_TOKEN"))

    grants_path = merged.get("JARVIS_AGENT_GRANTS_PATH", "/var/lib/jarvis/agent_grants.sqlite3")
    try:
        stat = check_path(grants_path).stat()
        issues.append((OK, f"grants store exists ({stat.st_size} bytes)"))
        mode = stat.st_mode & 0o777
        if mode & 0o004:
            warnings.append(f"grants store {grants_path} is world-readable")
    except OSError:
        warnings.append(f"grants store {grants_path} not found (created on first start)")

    gateways = [
        ("JARVIS_GITHUB_WRITE_TOKEN", 40, "agent can still read metadata and request once-bound PRs; writes stay closed"),
        ("JARVIS_BRAVE_SEARCH_TOKEN", 16, "business research search stays closed until configured"),
    ]
    for name, min_len, note in gateways:
        value = merged.get(name, "").strip()
        if len(value) >= min_len:
            issues.append((OK, f"{name} is set"))
        else:
            warnings.append(f"{name} missing ({note})")

    repo_root = check_path(merged.get("JARVIS_REPO_ROOT", Path(__file__).resolve().parents[2]))
    denied = ["private_key", "BEGIN RSA PRIVATE KEY", "RUNPOD_API_KEY=", "CONTROL_TOKEN=",
              "JARVIS_PASSPHRASE=", "OPENHANDS_API_KEY="]
    staged = repo_root / ".git" / "index"
    if staged.exists():
        try:
            text = staged.read_bytes().decode(errors="replace")
            hits = [d for d in denied if d in text]
            if hits:
                issues.append((FAIL, f"possible secret in git index: {', '.join(hits[:3])}"))
            else:
                issues.append((OK, "git index scanned: no obvious secrets"))
        except OSError:
            warnings.append("git index not readable; secret scan skipped")

    if merged.get("RUNPOD_ALLOW_BILLABLE_ACTIONS", "").strip().lower() == "true":
        issues.append((FAIL, "RUNPOD_ALLOW_BILLABLE_ACTIONS=true is set (billable runpod actions permitted)"))

    for flag, text in issues:
        print(f"  [{flag}] {text}")
    for text in warnings:
        print(f"  [?] {text}")

    failures = [t for f, t in issues if f == FAIL]
    if failures:
        print(f"\n{len(failures)} blocking issue(s); agent-gateway environment is NOT configured.", file=sys.stderr)
        return 1
    print("\nPreflight ok (warnings above do not block).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
