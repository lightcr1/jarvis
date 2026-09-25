"""Zentraler Freigabe-Kern (Plan JARVIS_ASSISTANT_PLAN, Abschnitt 3).

Jede Aktion -- Chat-Tool, Agent-Gateway oder VM-Executor -- soll dieselbe
Pruefung nutzen. Die Risikostufe gehoert zur *Capability* (vom Besitzer in
``config/capabilities.json`` gepflegt), nicht zum Aufruf; der Agent kann sie
nicht herabsetzen.

Stufen:
- T0 lesen                     -> allow
- T1 reversibel, eigener Bereich -> allow (wird berichtet)
- T2 Wirkung auf echte Systeme  -> ask, ausser eine stehende Freigabe deckt es ab
- T3 kritisch                   -> immer einzeln ask (nie per stehender Freigabe)

Die Funktion ist bewusst rein (keine Seiteneffekte): sie liefert nur eine
Entscheidung. Das Audit-Log schreibt der Aufrufer. Unbekannte Capabilities
fallen sicher auf **T2** zurueck.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

TIERS = ("T0", "T1", "T2", "T3")
DEFAULT_TIER = "T2"


def default_capabilities_path() -> Path:
    configured = os.getenv("JARVIS_CAPABILITIES_FILE")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "config" / "capabilities.json"


def load_capabilities(path: Path | None = None) -> dict[str, dict]:
    """Liest die Capability-Registry (capability -> {tier, description, ...})."""
    target = path or default_capabilities_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    capabilities = data.get("capabilities") if isinstance(data, dict) else None
    if not isinstance(capabilities, dict):
        return {}
    result: dict[str, dict] = {}
    for name, entry in capabilities.items():
        if isinstance(entry, dict):
            result[str(name)] = entry
        elif isinstance(entry, str):
            result[str(name)] = {"tier": entry}
    return result


def tier_for(capability: str, registry: dict[str, dict] | None = None) -> str:
    entry = (registry if registry is not None else load_capabilities()).get(capability) or {}
    tier = str(entry.get("tier") or DEFAULT_TIER).upper()
    return tier if tier in TIERS else DEFAULT_TIER


def digest_params(params: dict | None) -> str:
    """Stabiler SHA256 ueber die Aktionsparameter (fuer digest-gebundene Freigaben)."""
    canonical = json.dumps(params or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _grant_covers(grant: dict | None, capability: str, target: str) -> bool:
    if not isinstance(grant, dict) or grant.get("status") not in (None, "approved"):
        return False
    granted = str(grant.get("capability") or "")
    if granted not in ("*", capability):
        return False
    pattern = str(grant.get("target_pattern") or "*")
    if pattern in ("", "*"):
        return True
    return _glob_match(pattern, target)


def _glob_match(pattern: str, value: str) -> bool:
    import fnmatch
    return fnmatch.fnmatchcase(value, pattern)


@dataclass(frozen=True)
class Decision:
    decision: str          # allow | ask | deny
    tier: str
    reason: str
    requires_single_confirmation: bool = False

    def to_dict(self) -> dict:
        return {
            "decision": self.decision,
            "tier": self.tier,
            "reason": self.reason,
            "requires_single_confirmation": self.requires_single_confirmation,
        }


def authorize_action(capability: str, *, target: str = "", params: dict | None = None,
                     registry: dict[str, dict] | None = None, standing_grant: dict | None = None,
                     untrusted_context: bool = False, emergency_stop: bool = False) -> Decision:
    """Einzige Freigabe-Pruefung. Liefert allow/ask/deny (keine Seiteneffekte)."""
    tier = tier_for(capability, registry)
    if tier == "T0":
        return Decision("allow", "T0", "read-only action")
    if emergency_stop:
        return Decision("deny", tier, "emergency stop active")
    if tier == "T1":
        return Decision("allow", "T1", "reversible, own scope (reported afterwards)")
    if tier == "T3":
        return Decision("ask", "T3", "critical: always requires single confirmation",
                        requires_single_confirmation=True)
    # T2
    if untrusted_context:
        return Decision("ask", "T2", "untrusted context: confirmation required even for T2",
                        requires_single_confirmation=True)
    if _grant_covers(standing_grant, capability, target):
        return Decision("allow", "T2", "covered by standing grant")
    return Decision("ask", "T2", "real-system effect: confirmation required",
                    requires_single_confirmation=True)


def standing_grant_valid(grant: dict | None, *, now: float | None = None) -> bool:
    """Prueft Ablauf/Status einer stehenden Freigabe (T3 ist nie per Freigabe erlaubt)."""
    if not isinstance(grant, dict):
        return False
    if grant.get("status") not in (None, "approved"):
        return False
    expires = grant.get("expires_at")
    if expires is not None:
        current = time.time() if now is None else now
        try:
            if float(expires) <= float(current):
                return False
        except (TypeError, ValueError):
            return False
    return True
