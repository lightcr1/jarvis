from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

_CONDITIONS = {"above", "below", "equals", "contains"}


class PolicyStore:
    """Domain-agnostic `IF condition THEN action` rules — HA/Proxmox/system-metrics/
    self-healing policies live here, distinct from `AlertRulesStore` (notify-only) and
    from `HomeAssistantStore.automation_rules` (HA-entity-specific, left untouched).

    No seeded defaults are shipped — unlike CPU/RAM/disk alert thresholds, a sensible
    default self-healing policy can't be guessed without knowing which services the
    user actually runs.
    """

    def __init__(self) -> None:
        configured = os.getenv("JARVIS_POLICY_STORE_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/policies.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"policies": []}

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            merged = {**self._empty(), **content}
            if not isinstance(merged.get("policies"), list):
                merged["policies"] = []
            return merged
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        try:
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def list_policies(self) -> list[dict]:
        return [dict(p) for p in self.data.get("policies", [])]

    def get_policy(self, policy_id: str) -> dict | None:
        for policy in self.data.get("policies", []):
            if policy.get("id") == policy_id:
                return dict(policy)
        return None

    def create_policy(self, payload: dict) -> dict:
        policy = _normalize_policy(payload)
        policy["id"] = f"policy-{uuid.uuid4().hex[:12]}"
        self.data.setdefault("policies", []).append(policy)
        self._save()
        return dict(policy)

    def update_policy(self, policy_id: str, patch: dict) -> dict | None:
        policies = self.data.setdefault("policies", [])
        for idx, policy in enumerate(policies):
            if policy.get("id") != policy_id:
                continue
            merged = {**policy, **patch}
            policies[idx] = _normalize_policy(merged)
            policies[idx]["id"] = policy_id
            self._save()
            return dict(policies[idx])
        return None

    def delete_policy(self, policy_id: str) -> bool:
        policies = self.data.setdefault("policies", [])
        before = len(policies)
        self.data["policies"] = [p for p in policies if p.get("id") != policy_id]
        if len(self.data["policies"]) < before:
            self._save()
            return True
        return False

    def mark_fired(self, policy_id: str, ts: float) -> dict | None:
        """Persists `last_fired_at` so cooldown survives a service restart."""
        return self.update_policy(policy_id, {"last_fired_at": ts})


def _normalize_condition(raw: object) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    comparator = str(raw.get("comparator") or "above").lower()
    if comparator not in _CONDITIONS:
        comparator = "above"
    try:
        threshold: float | str = float(raw.get("threshold", 0))
    except (TypeError, ValueError):
        threshold = str(raw.get("threshold", ""))
    try:
        duration_sec = max(0, int(raw.get("duration_sec", 0)))
    except (TypeError, ValueError):
        duration_sec = 0
    return {
        "metric": str(raw.get("metric") or "").strip(),
        "comparator": comparator,
        "threshold": threshold,
        "duration_sec": duration_sec,
    }


def _normalize_action(raw: object) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    params = raw.get("params")
    return {
        "type": str(raw.get("type") or "").strip(),
        "params": dict(params) if isinstance(params, dict) else {},
    }


def _normalize_policy(payload: dict) -> dict:
    try:
        cooldown_sec = max(60, int(payload.get("cooldown_sec", 300)))
    except (TypeError, ValueError):
        cooldown_sec = 300
    last_fired_at = payload.get("last_fired_at")
    try:
        last_fired_at = float(last_fired_at) if last_fired_at is not None else None
    except (TypeError, ValueError):
        last_fired_at = None
    return {
        "id": str(payload.get("id") or ""),
        "name": str(payload.get("name") or "Unnamed policy").strip() or "Unnamed policy",
        "domain": str(payload.get("domain") or "system").strip() or "system",
        "condition": _normalize_condition(payload.get("condition")),
        "action": _normalize_action(payload.get("action")),
        "enabled": bool(payload.get("enabled", True)),
        "dry_run": bool(payload.get("dry_run", True)),
        "cooldown_sec": cooldown_sec,
        "last_fired_at": last_fired_at,
        "created_at": payload.get("created_at") or int(time.time()),
    }
