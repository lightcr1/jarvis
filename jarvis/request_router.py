"""Anliegen-Router (Plan Abschnitt 2.1).

Entscheidet je Besitzer-Nachricht den Weg -- vollstaendig deterministisch und
ohne Modellaufruf, damit die Entscheidung testbar und guenstig ist:

- ``answer``  -- vorhandenes Chat-Tool/Skill/Modell reicht (sofort)
- ``task``    -- mehrere Schritte / laenger als ein Chat-Turn -> Autonomy-Task
- ``build``   -- es fehlt eine Faehigkeit -> Agent baut ein Tool/Plugin
- ``infra``   -- Aktion auf VM/Host -> Executor (mit Freigabe)

Die Feinklassifikation kann spaeter ein Modell verfeinern; diese Basis bleibt
der sichere Default.
"""
from __future__ import annotations

import re

ROUTES = ("answer", "task", "build", "infra")

_BUILD = re.compile(
    r"\b(baue|bau|erstelle|entwickle|implementiere|integriere|plugin|erweitere)\b", re.I)
_INFRA = re.compile(
    r"\b(vm|lxc|proxmox|container|dienst|service|server|host|neustart|restart|reboot|"
    r"firewall|netz(?:werk)?|backup|snapshot|pod)\b", re.I)
_TASK = re.compile(
    r"\b(erledige|kümmere|kummere|plane|organisiere|recherchiere|prüfe|pruefe|analysiere|"
    r"überarbeite|ueberarbeite|fixe|behebe|teste|untersuche|bericht)\b", re.I)
_LONG = 280


def route_request(text: str, *, has_tool: bool = False) -> dict:
    """Liefert {route, reason}. ``has_tool`` = ein passendes Chat-Tool existiert."""
    message = (text or "").strip()
    if not message:
        return {"route": "answer", "reason": "leer"}
    if has_tool:
        return {"route": "answer", "reason": "vorhandenes Tool/Skill reicht"}
    if _BUILD.search(message):
        return {"route": "build", "reason": "Faehigkeit fehlt -> bauen"}
    if _INFRA.search(message):
        return {"route": "infra", "reason": "Infrastruktur-Aktion -> Executor"}
    if _TASK.search(message) or len(message) > _LONG:
        return {"route": "task", "reason": "mehrschrittige Arbeit"}
    return {"route": "answer", "reason": "einfache Frage"}
