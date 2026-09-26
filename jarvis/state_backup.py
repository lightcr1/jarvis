"""Backup/Restore des kompletten Jarvis-Zustands (Review-Punkt 3).

Ergaenzt den Benutzer-Backup-Export um die Datenbanken (Freigaben, Aufgaben,
Rundenberichte, Patch-Reviews), die Live-Konfiguration (capabilities.json,
zones.json) und das Executor-Audit-Log. Restore schreibt **nur** an die aktuell
konfigurierten Pfade (nie an einen Pfad aus der Backup-Datei).
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# (Name, Env-Variable, Default-Pfad)
DB_TARGETS = (
    ("agent_grants", "JARVIS_AGENT_GRANTS_PATH", "/var/lib/jarvis/agent_grants.sqlite3"),
    ("autonomy_tasks", "JARVIS_AUTONOMY_TASKS_PATH", "/var/lib/jarvis/autonomy_tasks.sqlite3"),
    ("patch_review", "JARVIS_PATCH_REVIEW_PATH", "/var/lib/jarvis/patch_review.sqlite3"),
)
CONFIG_TARGETS = (
    ("capabilities", "JARVIS_CAPABILITIES_FILE", "config/capabilities.json"),
    ("zones", "JARVIS_ZONES_FILE", "config/zones.json"),
)


def _db_path(env: str, default: str) -> Path:
    return Path(os.getenv(env) or default)


def _config_path(env: str, default: str) -> Path:
    configured = os.getenv(env)
    return Path(configured) if configured else _REPO_ROOT / default


def collect_state() -> dict:
    """Sammelt DBs (base64), Live-Configs (Text) und Executor-Audit-Log."""
    databases: dict[str, dict] = {}
    for name, env, default in DB_TARGETS:
        path = _db_path(env, default)
        try:
            if path.is_file():
                databases[name] = {"data": base64.b64encode(path.read_bytes()).decode("ascii")}
        except OSError:  # unlesbar/nicht erlaubt -> ueberspringen
            continue
    configs: dict[str, dict] = {}
    for name, env, default in CONFIG_TARGETS:
        path = _config_path(env, default)
        try:
            if path.is_file():
                configs[name] = {"text": path.read_text(encoding="utf-8")}
        except OSError:
            continue
    audit = None
    audit_path = os.getenv("JARVIS_EXECUTOR_AUDIT_LOG", "").strip()
    try:
        if audit_path and Path(audit_path).is_file():
            audit = {"text": Path(audit_path).read_text(encoding="utf-8")}
    except OSError:
        audit = None
    return {"databases": databases, "configs": configs, "executor_audit": audit}


def restore_state(state: dict) -> dict:
    """Schreibt DBs und Configs an die **aktuell konfigurierten** Pfade zurueck."""
    restored: dict[str, str] = {}
    databases = state.get("databases") if isinstance(state, dict) else None
    for name, entry in (databases or {}).items():
        target = next((_db_path(env, default) for n, env, default in DB_TARGETS if n == name), None)
        if target is None or not isinstance(entry, dict) or "data" not in entry:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(target) + suffix)
            if sidecar.exists():
                sidecar.unlink()
        target.write_bytes(base64.b64decode(entry["data"]))
        restored[name] = str(target)
    configs = state.get("configs") if isinstance(state, dict) else None
    for name, entry in (configs or {}).items():
        target = next((_config_path(env, default) for n, env, default in CONFIG_TARGETS if n == name), None)
        if target is None or not isinstance(entry, dict) or "text" not in entry:
            continue
        target.write_text(str(entry["text"]), encoding="utf-8")
        restored[name] = str(target)
    audit = state.get("executor_audit") if isinstance(state, dict) else None
    audit_path = os.getenv("JARVIS_EXECUTOR_AUDIT_LOG", "").strip()
    if audit_path and isinstance(audit, dict) and "text" in audit:
        Path(audit_path).write_text(str(audit["text"]), encoding="utf-8")
        restored["executor_audit"] = audit_path
    return restored
