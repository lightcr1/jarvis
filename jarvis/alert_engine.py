from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections import deque
from typing import Callable

logger = logging.getLogger("jarvis.alert_engine")

_MAX_HISTORY = 500
_MIN_POLL_INTERVAL = 10
_DEFAULT_POLL_INTERVAL = 30


def _poll_interval() -> int:
    try:
        val = int(os.getenv("JARVIS_ALERT_POLL_INTERVAL", "30"))
        return max(_MIN_POLL_INTERVAL, val)
    except (TypeError, ValueError):
        return _DEFAULT_POLL_INTERVAL


def _read_cpu_percent() -> float | None:
    try:
        import psutil
        return psutil.cpu_percent(interval=0.1)
    except ImportError:
        pass
    try:
        with open("/proc/stat") as f:
            line = f.readline()
        fields = [int(x) for x in line.strip().split()[1:]]
        idle = fields[3]
        total = sum(fields)
        return round((1.0 - idle / total) * 100.0, 1) if total else None
    except Exception:
        return None


def _read_ram_percent() -> float | None:
    try:
        from jarvis.skill_utils import parse_meminfo
        info = parse_meminfo()
        if not info:
            return None
        total = info.get("MemTotal", 0)
        available = info.get("MemAvailable", 0)
        if not total:
            return None
        return round((1.0 - available / total) * 100.0, 1)
    except Exception:
        return None


def _read_disk_percent() -> float | None:
    try:
        from jarvis.skill_utils import disk_usage
        usage = disk_usage("/")
        if usage.total == 0:
            return None
        return round(usage.used / usage.total * 100.0, 1)
    except Exception:
        return None


def _read_ha_health(ha_store: object | None) -> str | None:
    """Returns 'ok' when HA is reachable or None if no HA store is configured.

    The store tracks the last known connection state so no live HTTP call is made here.
    """
    if ha_store is None:
        return None
    try:
        status = ha_store.connection_status() if callable(getattr(ha_store, "connection_status", None)) else None
        if status is None:
            return None
        reachable = status.get("connected") or status.get("ok") or False
        return "ok" if reachable else "unreachable"
    except Exception:
        return None


def _read_ha_entity_value(ha_store: object | None, entity_id: str, attribute: str | None) -> str | float | None:
    if ha_store is None:
        return None
    try:
        entity = ha_store.get_managed_entity(entity_id)
        if not entity:
            return None
        attr = attribute or "state"
        if attr == "state":
            return entity.get("state")
        meta = entity.get("metadata") or {}
        return meta.get(attr)
    except Exception:
        return None


def _evaluate_condition(value: float | str, condition: str, threshold: float | str) -> bool:
    if condition == "contains":
        return str(threshold).lower() in str(value).lower()
    if condition == "equals":
        return str(value).strip().lower() == str(threshold).strip().lower()
    try:
        fval = float(value)
        fthr = float(threshold)
    except (TypeError, ValueError):
        return str(value).strip().lower() == str(threshold).strip().lower()
    if condition == "above":
        return fval > fthr
    if condition == "below":
        return fval < fthr
    return False


def _build_message(rule: dict, value: float | str) -> str:
    template = rule.get("message_template") or "Alert: {metric} is {value}"
    duration = rule.get("duration_seconds", 0)
    try:
        return template.format(
            metric=rule.get("metric", ""),
            value=value,
            threshold=rule.get("threshold", ""),
            duration=duration,
            name=rule.get("name", ""),
        )
    except (KeyError, ValueError):
        return template


def _build_alert_event(rule: dict, value: float | str) -> dict:
    return {
        "type": "alert",
        "alert_id": f"alert-{uuid.uuid4().hex[:12]}",
        "rule_id": rule["id"],
        "rule_name": rule.get("name", ""),
        "severity": rule.get("severity", "warning"),
        "metric": rule.get("metric", ""),
        "current_value": value,
        "threshold": rule.get("threshold"),
        "message": _build_message(rule, value),
        "timestamp": int(time.time()),
    }


class AlertEngine:
    def __init__(
        self,
        rules_store: object,
        audit_admin_event: Callable,
        ha_store: object | None = None,
        broadcast_fn: Callable | None = None,
    ) -> None:
        self._rules_store = rules_store
        self._audit = audit_admin_event
        self._ha_store = ha_store
        self._broadcast_fn = broadcast_fn
        self._task: asyncio.Task | None = None
        self._threshold_crossed_at: dict[str, float] = {}
        self._last_fired_at: dict[str, float] = {}
        self._history: deque[dict] = deque(maxlen=_MAX_HISTORY)

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    def reload_rules(self) -> None:
        pass

    def get_history(self, limit: int = 100) -> list[dict]:
        items = list(self._history)
        items.reverse()
        return items[:limit]

    async def fire_test_alert(self, rule: dict) -> dict:
        value: float | str = rule.get("threshold", 0)
        event = _build_alert_event(rule, value)
        event["message"] = f"[TEST] {event['message']}"
        self._history.append(event)
        await self._broadcast(event)
        return event

    async def _broadcast(self, event: dict) -> None:
        if self._broadcast_fn:
            try:
                await self._broadcast_fn(event)
            except Exception as exc:
                logger.warning("Alert broadcast failed: %s", exc)

    def _read_metric(self, rule: dict) -> float | str | None:
        metric = rule.get("metric", "cpu")
        if metric == "cpu":
            return _read_cpu_percent()
        if metric == "ram":
            return _read_ram_percent()
        if metric == "disk":
            return _read_disk_percent()
        if metric == "ha_health":
            return _read_ha_health(self._ha_store)
        if metric == "ha_entity":
            entity_id = rule.get("ha_entity_id")
            if not entity_id:
                return None
            return _read_ha_entity_value(self._ha_store, entity_id, rule.get("ha_attribute"))
        return None

    async def _evaluate_rule(self, rule: dict, now: float) -> None:
        rule_id = rule["id"]
        value = await asyncio.get_event_loop().run_in_executor(None, self._read_metric, rule)
        if value is None:
            if rule.get("metric") == "ha_entity":
                logger.debug("Alert rule %r: HA entity not found, skipping.", rule_id)
            self._threshold_crossed_at.pop(rule_id, None)
            return
        condition_met = _evaluate_condition(value, rule.get("condition", "above"), rule.get("threshold", 0))
        if not condition_met:
            self._threshold_crossed_at.pop(rule_id, None)
            return
        first_crossed = self._threshold_crossed_at.setdefault(rule_id, now)
        duration_required = rule.get("duration_seconds", 0)
        if now - first_crossed < duration_required:
            return
        last_fired = self._last_fired_at.get(rule_id, 0.0)
        cooldown = rule.get("cooldown_seconds", 300)
        if now - last_fired < cooldown:
            return
        event = _build_alert_event(rule, value)
        self._last_fired_at[rule_id] = now
        self._history.append(event)
        await self._broadcast(event)
        try:
            self._audit("alert.fired", "system", "system", {"rule_id": rule_id, "rule_name": rule.get("name"), "severity": rule.get("severity")})
        except Exception as exc:
            logger.warning("Failed to audit alert: %s", exc)
        logger.info("Alert fired: rule=%r severity=%r value=%r", rule.get("name"), rule.get("severity"), value)

    async def _loop(self) -> None:
        logger.info("Alert engine started.")
        while True:
            interval = _poll_interval()
            try:
                rules = self._rules_store.list_rules()
                now = time.time()
                for rule in rules:
                    if not rule.get("enabled"):
                        continue
                    try:
                        await self._evaluate_rule(rule, now)
                    except Exception as exc:
                        logger.warning("Error evaluating rule %r: %s", rule.get("id"), exc)
            except asyncio.CancelledError:
                logger.info("Alert engine stopped.")
                return
            except Exception as exc:
                logger.warning("Alert engine loop error: %s", exc)
            await asyncio.sleep(interval)
