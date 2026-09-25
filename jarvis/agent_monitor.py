"""Agent monitor: live view of OpenHands sessions + owner request queue.

This module lets the Jarvis web UI show what the coding agent (OpenHands)
is currently doing, without the owner having to open the OpenHands canvas.
It only reads metadata (session list, goal status, recent event titles) —
no chat contents are stored or displayed.

Ownership requests: Jarvis files proposals as GitHub issues labelled
`owner-input`. The owner can approve/reject them from the Jarvis UI; the
decision is written back as a GitHub label, which Jarvis picks up in its
next round (see AGENTS.md / docs/GOALS.md).

Configuration (env):
  OPENHANDS_API_BASE  default http://openhands:8000 (or jarvis-openhands:8000)
  OPENHANDS_API_KEY   required for session listing
  GITHUB_TOKEN        optional; without it requests are read-only
  GITHUB_REPO         default lightcr1/jarvis
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

DEFAULT_OPENHANDS_BASE = os.getenv("OPENHANDS_API_BASE", "http://openhands:8000")
DEFAULT_GITHUB_REPO = os.getenv("GITHUB_REPO", "lightcr1/jarvis")


class MonitorError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# OpenHands session listing
# --------------------------------------------------------------------------

def _oh_request(path: str, api_key: str | None = None, method: str = "GET",
               body: dict | None = None) -> dict:
    base = os.getenv("OPENHANDS_API_BASE", DEFAULT_OPENHANDS_BASE)
    key = api_key or os.getenv("OPENHANDS_API_KEY") or os.getenv("OPENHANDS_API_KEY_FILE")
    if key and not api_key and key.startswith("file:"):
        key = open(key[5:]).read().strip()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-Session-API-Key"] = key
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, headers=headers, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        raise MonitorError(f"OpenHands API {exc.code} for {path}") from exc
    except Exception as exc:  # noqa: BLE001 - network errors
        raise MonitorError(f"OpenHands API unerreichbar ({base}): {exc}") from exc


def list_sessions(api_key: str | None = None) -> list[dict]:
    """All sessions/threads the agent currently has (owner- and agent-created)."""
    try:
        data = _oh_request("/api/conversations/search?limit=50", api_key)
    except MonitorError:
        # Fallback: alte API-Pfade für andere Agent-Canvas-Versionen
        try:
            data = _oh_request("/api/conversations?limit=50", api_key)
        except MonitorError as exc:
            raise MonitorError(f"Sessions nicht abrufbar: {exc}") from exc
    items = data.get("items", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return items


def session_status(session: dict) -> dict:
    """Compact status of one session (metadata only). Der Canvas liefert den
    Zustand im Feld `execution_status`; fuer alte Antworten bleiben die
    Fallbacks erhalten."""
    conv_id = session.get("conversation_id") or session.get("id") or ""
    status = (session.get("execution_status")
              or session.get("status") or session.get("state", "unknown"))
    title = session.get("title") or session.get("agent_name") or f"Session {conv_id[:8]}"
    tags = session.get("tags") or {}
    return {
        "id": conv_id,
        "title": str(title)[:120],
        "status": str(status),
        "kind": str(tags.get("kind") or "unspecified"),
        "focus": str(tags.get("focus") or "unspecified"),
        "updated_at": session.get("updated_at") or session.get("created_at") or None,
        "selected_agent": session.get("selected_agent") or "",
        "branch": str((session.get("workspace") or {}).get("working_dir") or ""),
    }


def session_action(api_key: str, conv_id: str, action: str) -> None:
    """Pause/run/interrupt einer Session (nur eigenen Loop-Sessions im Admin-UI)."""
    if action not in ("pause", "run", "interrupt"):
        raise MonitorError(f"Ungueltige Aktion: {action}")
    _oh_request(f"/api/conversations/{conv_id}/{action}", api_key, method="POST", body={})


# --------------------------------------------------------------------------
# Autonomy loop version / drift
# --------------------------------------------------------------------------

def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def loop_version(repo_root: Path | str | None = None,
                 state_path: Path | str | None = None,
                 installed_loop: Path | str | None = None) -> dict:
    """Compare the versioned loop source with the installed/running one.

    The installed hash is read from the loop state file
    (``JARVIS_AUTONOMY_STATE_PATH``, field ``loop_sha256``) or, as a fallback,
    by hashing ``JARVIS_AUTONOMY_LOOP_PATH`` directly. Without either being
    readable the installed hash stays ``None`` and ``drift`` is ``False``
    (unknown, not a warning).
    """
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[1]
    source = root / "scripts" / "agent" / "autonomy_loop.py"
    repo_hash = _sha256_file(source)

    installed_hash: str | None = None
    state_file = Path(state_path) if state_path else os.getenv("JARVIS_AUTONOMY_STATE_PATH")
    if state_file:
        try:
            data = json.loads(Path(state_file).read_text(encoding="utf-8"))
            value = data.get("loop_sha256")
            installed_hash = str(value) if value else None
        except (OSError, json.JSONDecodeError):
            installed_hash = None
    if installed_hash is None:
        loop_file = Path(installed_loop) if installed_loop else os.getenv("JARVIS_AUTONOMY_LOOP_PATH")
        if loop_file:
            installed_hash = _sha256_file(Path(loop_file))

    drift = bool(repo_hash and installed_hash and repo_hash != installed_hash)
    return {
        "repo_sha256": repo_hash,
        "installed_sha256": installed_hash,
        "drift": drift,
        "source": str(source),
    }


# --------------------------------------------------------------------------
# Owner request queue (GitHub issues labelled owner-input)
# --------------------------------------------------------------------------

def _gh_request(method: str, url: str, token: str | None, payload: dict | None = None) -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        raise MonitorError(f"GitHub API {exc.code}") from exc


def list_owner_requests(token: str | None = None,
                        repo: str | None = None) -> dict:
    """Open issues labelled owner-input; read-only when token is missing."""
    repo = repo or DEFAULT_GITHUB_REPO
    url = f"https://api.github.com/repos/{repo}/issues?state=open&labels=owner-input&per_page=50"
    try:
        items = _gh_request("GET", url, token)
    except MonitorError as exc:
        return {"requests": [], "readonly": True, "error": str(exc)}
    requests = []
    for issue in items if isinstance(items, list) else []:
        labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]
        requests.append({
            "number": issue.get("number"),
            "title": issue.get("title", ""),
            "created_at": issue.get("created_at"),
            "labels": labels,
            "url": issue.get("html_url", ""),
        })
    return {"requests": requests, "readonly": not token}


def decide_owner_request(number: int, decision: str, token: str | None = None,
                         repo: str | None = None) -> dict:
    """Apply approved/rejected label to an owner-input issue (needs token)."""
    if decision not in ("approved", "rejected"):
        raise MonitorError(f"Ungueltige Entscheidung: {decision}")
    if not token:
        raise MonitorError("GITHUB_TOKEN fehlt - Entscheidung kann nicht gesetzt werden")
    repo = repo or DEFAULT_GITHUB_REPO
    url = f"https://api.github.com/repos/{repo}/issues/{number}/labels"
    _gh_request("POST", url, token, payload={"labels": [decision]})
    return {"number": number, "decision": decision}
