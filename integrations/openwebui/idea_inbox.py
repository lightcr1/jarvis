"""Open WebUI tool: forward an explicit idea into the Jarvis idea queue.

This is an optional bridge for Open WebUI users. It only submits the four
explicit idea forms (`Business-Idee:`, `Projektidee:`, `Jarvis-Idee:`,
`Idee:`). Everything else is echoed back without any side effect.

The request-only token must be available via the environment variable
JARVIS_AGENT_REQUEST_TOKEN (never a server/admin token). A submitted idea is
a proposal for the owner to review, never permission to execute anything.

Standard-library only, so it can be pasted into Open WebUI without extra
dependencies and still be import-tested offline.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

GATEWAY_BASE = os.getenv("JARVIS_AGENT_GATEWAY", "http://10.10.40.100:8100")
_IDEA_FORM = re.compile(r"^(Business-Idee|Projektidee|Jarvis-Idee|Idee):\s*(.+)$", re.I | re.S)


def submit_idea(text: str, *, base_url: str = GATEWAY_BASE, token: str | None = None) -> str:
    """Return a human-readable confirmation string (never raises side effects)."""
    token = token if token is not None else os.getenv("JARVIS_AGENT_REQUEST_TOKEN", "")
    match = _IDEA_FORM.match((text or "").strip())
    if not match:
        return ("Nur ausdrueckliche Formulare werden weitergeleitet: "
                "`Business-Idee: ...`, `Projektidee: ...`, `Jarvis-Idee: ...`, `Idee: ...`.")
    if not token:
        return "JARVIS_AGENT_REQUEST_TOKEN ist nicht konfiguriert – Idee nicht gespeichert."
    title = match.group(2).strip()
    if not title or len(title) > 2000:
        return "Bitte beschreibe die Idee in maximal 2000 Zeichen."
    prefix = match.group(1).lower()
    kind = "other_project" if prefix == "projektidee" else "platform" if prefix == "jarvis-idee" else "business"
    payload = {
        "kind": kind, "title": title[:140], "summary": title,
        "benefit": "To be researched", "risks": "To be assessed",
        "next_step": "Research and propose a safe plan",
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/agent/ideas", data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "X-Jarvis-Agent-Request-Token": token, "User-Agent": "Jarvis-OpenWebUI-Bridge"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 201:
                return "Idee konnte nicht gespeichert werden (unerwartete Antwort)."
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        return f"Idee konnte nicht gespeichert werden: {exc}"
    return "Idee notiert. Der Besitzer prueft sie; externe Aktionen brauchen weiterhin Freigaben."


# Open WebUI tool convention: a function on module level. Keep the name short.
def jarvis_idea_inbox(text: str) -> str:
    return submit_idea(text)
