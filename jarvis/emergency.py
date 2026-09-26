"""Zentraler Not-Aus (Review: "Not-Aus an einer zentralen Stelle").

Ein Schalter gilt ueberall: die Env-Variable ``JARVIS_EMERGENCY_STOP`` **oder**
eine Stop-Datei ``JARVIS_EMERGENCY_STOP_FILE`` (Default
``/var/lib/jarvis/emergency_stop``). App, Executor und Autonomy-Loop pruefen
dieselbe Quelle.
"""
from __future__ import annotations

import os
from pathlib import Path

_TRUTHY = {"1", "true", "yes", "on"}


def stop_file() -> Path:
    return Path(os.getenv("JARVIS_EMERGENCY_STOP_FILE") or "/var/lib/jarvis/emergency_stop")


def _env_active() -> bool:
    return (os.getenv("JARVIS_EMERGENCY_STOP") or "0").strip().lower() in _TRUTHY


def is_active() -> bool:
    if _env_active():
        return True
    try:
        return stop_file().exists()
    except OSError:
        return False


def set_active(active: bool) -> bool:
    """Setzt/entfernt die Stop-Datei (zentraler Schalter). True bei Erfolg."""
    path = stop_file()
    try:
        if active:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("stopped\n", encoding="utf-8")
        elif path.exists():
            path.unlink()
        return True
    except OSError:
        return False
