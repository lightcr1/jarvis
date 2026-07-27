from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from typing import Callable

from jarvis.alert_engine import SignalSource, _default_signal_sources, _evaluate_condition
from jarvis.infra_actions import read_service_active, restart_service

logger = logging.getLogger("jarvis.policy_engine")

_MAX_HISTORY = 500
_MIN_POLL_INTERVAL = 10
_DEFAULT_POLL_INTERVAL = 30
_DEFAULT_RETRY_WINDOW_SEC = 900
_DEFAULT_ESCALATE_AFTER = 2


def _service_status_source(policy: dict, *, run_cmd: Callable) -> str | None:
    service = ((policy.get("action") or {}).get("params") or {}).get("service")
    if not service:
        return None
    try:
        return read_service_active(str(service), run_cmd=run_cmd)
    except Exception as exc:
        logger.warning("Failed to read service status for policy %r: %s", policy.get("id"), exc)
        return None


class PolicyEngine:
    """Cross-domain `IF condition THEN action` evaluator sitting alongside AlertEngine.

    Deliberately a sibling class, not a merge into AlertEngine — see
    `docs/v2/planning/ROADMAP_V2.md` Phase 4 notes / agent-memory for the reasoning.
    Reuses AlertEngine's pluggable signal-source registry and condition evaluator
    directly (`_default_signal_sources`, `_evaluate_condition`) rather than
    reimplementing metric reading.
    """

    def __init__(
        self,
        policy_store: object,
        run_cmd: Callable,
        ensure_service_allowed: Callable,
        emergency_stop_enabled: Callable[[], bool],
        write_permission_check: Callable[[], bool],
        audit_admin_event: Callable,
        ha_store: object | None = None,
        broadcast_fn: Callable | None = None,
        retry_window_sec: int = _DEFAULT_RETRY_WINDOW_SEC,
        escalate_after_incidents: int = _DEFAULT_ESCALATE_AFTER,
    ) -> None:
        self._store = policy_store
        self._run_cmd = run_cmd
        self._ensure_service_allowed = ensure_service_allowed
        self._emergency_stop_enabled = emergency_stop_enabled
        self._write_permission_check = write_permission_check
        self._audit = audit_admin_event
        self._broadcast_fn = broadcast_fn
        self._retry_window_sec = retry_window_sec
        self._escalate_after = max(1, escalate_after_incidents)

        # Reuses AlertEngine's built-in readers verbatim. `cpu`/`ram`/`disk`/`ha_health`
        # ignore their argument entirely so they work unchanged against a policy dict.
        # `ha_entity` expects `rule["ha_entity_id"]` at the top level (AlertRule shape),
        # which a policy dict doesn't have — it degrades to "always None" (silently
        # skipped, same as an unregistered metric) rather than crashing. Entity-scoped
        # policies aren't a required domain yet; add a custom `register_source()` call
        # reading from `policy["condition"]`/`action.params"` if that's needed later.
        self._sources: dict[str, SignalSource] = _default_signal_sources(ha_store)
        self._sources["service_status"] = lambda policy: _service_status_source(policy, run_cmd=run_cmd)

        self._task: asyncio.Task | None = None
        self._threshold_crossed_at: dict[str, float] = {}
        self._incident_times: dict[str, list[float]] = {}
        self._history: deque[dict] = deque(maxlen=_MAX_HISTORY)

    def register_source(self, metric: str, source: SignalSource) -> None:
        self._sources[metric] = source

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    def get_history(self, limit: int = 100) -> list[dict]:
        items = list(self._history)
        items.reverse()
        return items[:limit]

    def _read_metric(self, policy: dict) -> float | str | None:
        source = self._sources.get(policy.get("condition", {}).get("metric", ""))
        if source is None:
            return None
        try:
            return source(policy)
        except Exception as exc:
            logger.warning("Signal source %r raised: %s", policy.get("condition", {}).get("metric"), exc)
            return None

    async def _broadcast(self, event: dict) -> None:
        if self._broadcast_fn:
            try:
                await self._broadcast_fn(event)
            except Exception as exc:
                logger.warning("Policy broadcast failed: %s", exc)

    def _record_incident(self, policy_id: str, now: float) -> int:
        times = [t for t in self._incident_times.get(policy_id, []) if now - t <= self._retry_window_sec]
        times.append(now)
        self._incident_times[policy_id] = times
        return len(times)

    async def fire_test(self, policy: dict) -> dict:
        """Manually triggers one evaluation cycle for admin "test" UI — bypasses
        duration/cooldown gates but still respects dry_run and emergency-stop, and does
        not mutate cooldown/incident state.
        """
        value = self._read_metric(policy)
        outcome = await self._execute_action(policy, value if value is not None else policy["condition"]["threshold"], now=time.time(), record_incident=False)
        outcome["event"]["message"] = f"[TEST] {outcome['event']['message']}"
        self._history.append(outcome["event"])
        await self._broadcast(outcome["event"])
        return outcome

    async def _execute_action(self, policy: dict, value: float | str, *, now: float, record_incident: bool = True) -> dict:
        action = policy.get("action", {})
        action_type = action.get("type")
        if action_type != "restart_service":
            event = _build_policy_event(policy, value, "policy_action_unsupported", f"Policy {policy.get('name')} has an unsupported action type: {action_type!r}.")
            return {"event": event, "escalated": False}

        service = (action.get("params") or {}).get("service", "")
        if policy.get("dry_run", True):
            event = _build_policy_event(
                policy, value, "policy_dry_run",
                f"[DRY RUN] Would restart {service} — condition met (current: {value}).",
            )
            return {"event": event, "escalated": False}

        if self._emergency_stop_enabled():
            self._audit("policy.blocked_emergency_stop", "system", "system", {"policy_id": policy["id"], "service": service})
            event = _build_policy_event(
                policy, value, "policy_escalation",
                f"Sir, {service} is down but JARVIS_EMERGENCY_STOP is active — I cannot restart it automatically.",
                severity="critical",
            )
            return {"event": event, "escalated": True}

        if not self._write_permission_check():
            self._audit("policy.blocked_permission_denied", "system", "system", {"policy_id": policy["id"], "service": service})
            event = _build_policy_event(
                policy, value, "policy_escalation",
                f"Sir, {service} is down but the self-healing policy is missing write permission.",
                severity="critical",
            )
            return {"event": event, "escalated": True}

        incident_count = self._record_incident(policy["id"], now) if record_incident else 1
        result = {"service": service, "active": "unknown", "healthy": False}
        try:
            result = restart_service(service, run_cmd=self._run_cmd, ensure_service_allowed=self._ensure_service_allowed)
        except Exception as exc:
            logger.warning("Restart action failed for policy %r: %s", policy.get("id"), exc)
        healthy = result.get("healthy", False)

        self._audit(
            "policy.self_heal.restart_attempted", "system", "system",
            {"policy_id": policy["id"], "service": service, "healthy": healthy, "incident_count": incident_count},
        )

        if healthy and incident_count < self._escalate_after:
            event = _build_policy_event(policy, value, "policy_action", f"{service} was down — restarted successfully.")
            return {"event": event, "escalated": False}

        if incident_count >= self._escalate_after:
            self._audit("policy.escalated", "system", "system", {"policy_id": policy["id"], "service": service, "incident_count": incident_count})
            event = _build_policy_event(
                policy, value, "policy_escalation",
                f"Sir, {service} has failed to recover after {incident_count} restart attempts. Manual intervention required.",
                severity="critical",
            )
            return {"event": event, "escalated": True}

        event = _build_policy_event(policy, value, "policy_action", f"Restarted {service}, but it is still {result.get('active', 'unknown')}.")
        return {"event": event, "escalated": False}

    async def _evaluate_policy(self, policy: dict, now: float) -> None:
        policy_id = policy["id"]
        value = await asyncio.get_event_loop().run_in_executor(None, self._read_metric, policy)
        if value is None:
            self._threshold_crossed_at.pop(policy_id, None)
            return
        condition = policy["condition"]
        condition_met = _evaluate_condition(value, condition["comparator"], condition["threshold"])
        if not condition_met:
            self._threshold_crossed_at.pop(policy_id, None)
            return
        first_crossed = self._threshold_crossed_at.setdefault(policy_id, now)
        if now - first_crossed < condition["duration_sec"]:
            return
        last_fired = policy.get("last_fired_at") or 0.0
        if now - last_fired < policy["cooldown_sec"]:
            return

        outcome = await self._execute_action(policy, value, now=now)
        if not policy.get("dry_run", True):
            self._store.mark_fired(policy_id, now)
        self._history.append(outcome["event"])
        await self._broadcast(outcome["event"])
        logger.info("Policy fired: %r type=%r escalated=%r", policy.get("name"), outcome["event"]["type"], outcome["escalated"])

    async def _loop(self) -> None:
        logger.info("Policy engine started.")
        while True:
            try:
                policies = self._store.list_policies()
                now = time.time()
                for policy in policies:
                    if not policy.get("enabled"):
                        continue
                    try:
                        await self._evaluate_policy(policy, now)
                    except Exception as exc:
                        logger.warning("Error evaluating policy %r: %s", policy.get("id"), exc)
            except asyncio.CancelledError:
                logger.info("Policy engine stopped.")
                return
            except Exception as exc:
                logger.warning("Policy engine loop error: %s", exc)
            await asyncio.sleep(_DEFAULT_POLL_INTERVAL)


def _build_policy_event(policy: dict, value: float | str, event_type: str, message: str, severity: str = "info") -> dict:
    return {
        "type": event_type,
        "event_id": f"pol-{uuid.uuid4().hex[:12]}",
        "policy_id": policy["id"],
        "policy_name": policy.get("name", ""),
        "domain": policy.get("domain", ""),
        "severity": severity,
        "current_value": value,
        "message": message,
        "timestamp": int(time.time()),
    }
