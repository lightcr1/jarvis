from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path


_DEFAULT_RULES: list[dict] = [
    {
        "id": "default-cpu-warning",
        "name": "High CPU usage",
        "enabled": True,
        "metric": "cpu",
        "condition": "above",
        "threshold": 90.0,
        "duration_seconds": 300,
        "severity": "warning",
        "cooldown_seconds": 600,
        "ha_entity_id": None,
        "ha_attribute": None,
        "message_template": "CPU utilization has exceeded {threshold}% for {duration} seconds.",
    },
    {
        "id": "default-cpu-critical",
        "name": "Critical CPU usage",
        "enabled": True,
        "metric": "cpu",
        "condition": "above",
        "threshold": 95.0,
        "duration_seconds": 60,
        "severity": "critical",
        "cooldown_seconds": 300,
        "ha_entity_id": None,
        "ha_attribute": None,
        "message_template": "CPU utilization is critically high at {value}%. Immediate attention may be required.",
    },
    {
        "id": "default-ram-warning",
        "name": "High RAM usage",
        "enabled": True,
        "metric": "ram",
        "condition": "above",
        "threshold": 85.0,
        "duration_seconds": 120,
        "severity": "warning",
        "cooldown_seconds": 600,
        "ha_entity_id": None,
        "ha_attribute": None,
        "message_template": "Memory utilization has exceeded {threshold}% for {duration} seconds.",
    },
    {
        "id": "default-disk-critical",
        "name": "Critical disk usage",
        "enabled": True,
        "metric": "disk",
        "condition": "above",
        "threshold": 90.0,
        "duration_seconds": 0,
        "severity": "critical",
        "cooldown_seconds": 3600,
        "ha_entity_id": None,
        "ha_attribute": None,
        "message_template": "Disk capacity on the primary volume is at {value:.0f}%. Attention recommended.",
    },
    {
        "id": "default-ha-unreachable",
        "name": "Home Assistant unreachable",
        "enabled": True,
        "metric": "ha_health",
        "condition": "equals",
        "threshold": "unreachable",
        "duration_seconds": 180,
        "severity": "warning",
        "cooldown_seconds": 600,
        "ha_entity_id": None,
        "ha_attribute": None,
        "message_template": "Home Assistant has been unreachable for {duration} seconds.",
    },
]


class AlertRulesStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_ALERT_RULES_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/alert_rules.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"rules": [], "seeded": False}

    def _load(self) -> dict:
        if not self.path.exists():
            base = self._empty()
            base["rules"] = [dict(r) for r in _DEFAULT_RULES]
            base["seeded"] = True
            self._save_data(base)
            return base
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            merged = {**self._empty(), **content}
            if not isinstance(merged.get("rules"), list):
                merged["rules"] = []
            if not merged.get("seeded"):
                merged["rules"] = [dict(r) for r in _DEFAULT_RULES] + merged["rules"]
                merged["seeded"] = True
                self._save_data(merged)
            return merged
        except (OSError, json.JSONDecodeError):
            base = self._empty()
            base["rules"] = [dict(r) for r in _DEFAULT_RULES]
            base["seeded"] = True
            return base

    def _save_data(self, data: dict) -> None:
        try:
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _save(self) -> None:
        self._save_data(self.data)

    def list_rules(self, owner_user_id: str | None = None) -> list[dict]:
        rules = self.data.get("rules", [])
        if owner_user_id is not None:
            rules = [r for r in rules if r.get("owner_user_id") == owner_user_id]
        return [dict(r) for r in rules]

    def get_rule(self, rule_id: str) -> dict | None:
        for rule in self.data.get("rules", []):
            if rule.get("id") == rule_id:
                return dict(rule)
        return None

    def create_rule(self, payload: dict, owner_user_id: str | None = None) -> dict:
        rule = _normalize_rule(payload)
        rule["id"] = f"rule-{uuid.uuid4().hex[:12]}"
        rule["owner_user_id"] = owner_user_id
        self.data.setdefault("rules", []).append(rule)
        self._save()
        return dict(rule)

    def update_rule(self, rule_id: str, patch: dict) -> dict | None:
        rules = self.data.setdefault("rules", [])
        for idx, rule in enumerate(rules):
            if rule.get("id") != rule_id:
                continue
            merged = {**rule, **{k: v for k, v in patch.items() if v is not None or k in patch}}
            merged["id"] = rule_id
            rules[idx] = _normalize_rule(merged)
            rules[idx]["id"] = rule_id
            self._save()
            return dict(rules[idx])
        return None

    def delete_rule(self, rule_id: str) -> bool:
        rules = self.data.setdefault("rules", [])
        before = len(rules)
        self.data["rules"] = [r for r in rules if r.get("id") != rule_id]
        if len(self.data["rules"]) < before:
            self._save()
            return True
        return False


KNOWN_METRICS = {"cpu", "ram", "disk", "ha_health", "ha_entity", "presence_idle_minutes", "calendar_upcoming_minutes"}


def _normalize_condition_clause(payload: dict) -> dict:
    metric = str(payload.get("metric") or "cpu").lower()
    if metric not in KNOWN_METRICS:
        metric = "cpu"
    condition = str(payload.get("condition") or "above").lower()
    if condition not in {"above", "below", "equals", "contains"}:
        condition = "above"
    try:
        threshold_raw = payload.get("threshold", 80.0)
        threshold: float | str = float(threshold_raw)
    except (TypeError, ValueError):
        threshold = str(payload.get("threshold", ""))
    return {
        "metric": metric,
        "condition": condition,
        "threshold": threshold,
        "ha_entity_id": payload.get("ha_entity_id") or None,
        "ha_attribute": payload.get("ha_attribute") or None,
    }


def _normalize_rule(payload: dict) -> dict:
    severity = str(payload.get("severity") or "warning").lower()
    if severity not in {"info", "warning", "critical"}:
        severity = "warning"
    try:
        duration_seconds = max(0, int(payload.get("duration_seconds", 0)))
    except (TypeError, ValueError):
        duration_seconds = 0
    try:
        cooldown_seconds = max(60, int(payload.get("cooldown_seconds", 300)))
    except (TypeError, ValueError):
        cooldown_seconds = 300

    raw_conditions = payload.get("conditions")
    conditions = [_normalize_condition_clause(c) for c in raw_conditions] if isinstance(raw_conditions, list) and raw_conditions else []
    combinator = str(payload.get("combinator") or "and").lower()
    if combinator not in {"and", "or"}:
        combinator = "and"

    # The single-condition fields stay populated even for a compound rule (defaulted
    # from the first clause when present) — every consumer that only knows the legacy
    # shape (older UI code, message templates, the admin rule list) keeps working
    # unchanged; _evaluate_rule branches on `conditions` being non-empty to pick the
    # compound path instead of relying on these.
    fallback = conditions[0] if conditions else {}
    single = _normalize_condition_clause({**payload, **fallback} if fallback else payload)

    return {
        "id": str(payload.get("id") or ""),
        "owner_user_id": payload.get("owner_user_id") or None,
        "name": str(payload.get("name") or "Unnamed rule").strip() or "Unnamed rule",
        "enabled": bool(payload.get("enabled", True)),
        "metric": single["metric"],
        "condition": single["condition"],
        "threshold": single["threshold"],
        "conditions": conditions,
        "combinator": combinator,
        "duration_seconds": duration_seconds,
        "severity": severity,
        "cooldown_seconds": cooldown_seconds,
        "ha_entity_id": single["ha_entity_id"],
        "ha_attribute": single["ha_attribute"],
        "message_template": str(payload.get("message_template") or "").strip()
            or "Alert: {metric} is {value} (threshold: {threshold})",
    }
