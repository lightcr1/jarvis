from __future__ import annotations

import time
import uuid

_DEFAULT_COOLDOWN_SECONDS = 24 * 3600


def detect_repeated_skill_invocations(learned_replies: dict, threshold: int = 5) -> list[dict]:
    """Flags queries whose learned-reply confidence (repeat-success count, tracked by
    LearningStore.record_success) has crossed `threshold` — a proxy for "the user runs
    this exact command over and over," which is worth surfacing as an automation idea.
    """
    suggestions: list[dict] = []
    for query, entry in (learned_replies or {}).items():
        confidence = int((entry or {}).get("confidence", 0))
        if confidence < threshold:
            continue
        skill = (entry or {}).get("skill") or "this command"
        suggestions.append({
            "kind": "repeated_skill",
            "key": query,
            "count": confidence,
            "message": f"You've run '{query}' ({skill}) {confidence} times. "
                       f"Want me to set this up as a recurring automation?",
        })
    return suggestions


def flatten_proxmox_items(health: dict | None) -> list[dict]:
    """Turns proxmox_module.proxmox_health()'s nested hosts/nodes structure into a
    flat list of VM/container dicts, each annotated with host_id/node/resource_type
    so idle-detection can address a specific resource.
    """
    items: list[dict] = []
    if not isinstance(health, dict):
        return items
    for host in health.get("hosts") or []:
        host_id = host.get("id")
        for node in host.get("nodes") or []:
            node_name = node.get("node")
            for vm in node.get("vms") or []:
                items.append({**vm, "host_id": host_id, "node": node_name, "resource_type": "vm"})
            for ct in node.get("containers") or []:
                items.append({**ct, "host_id": host_id, "node": node_name, "resource_type": "container"})
    return items


def detect_backup_failure_streak(log: list[dict], streak_threshold: int = 3) -> dict | None:
    """`log` is the auto-backup outcome log (most recent last), each entry
    `{"ts": int, "ok": bool}`. Returns a suggestion if the last `streak_threshold`
    runs all failed.
    """
    if len(log) < streak_threshold:
        return None
    tail = log[-streak_threshold:]
    if not all(not entry.get("ok") for entry in tail):
        return None
    return {
        "kind": "backup_failures",
        "key": "auto_backup",
        "count": streak_threshold,
        "message": f"The last {streak_threshold} automatic backups failed. "
                   f"Please check backup configuration.",
    }


class IdleResourceTracker:
    """Tracks how long each Proxmox VM/container has stayed at near-zero CPU while
    running, mirroring AlertEngine's threshold-crossed-at pattern so idle duration
    survives repeated `evaluate()` calls without needing a persistent time-series store.
    """

    def __init__(self, idle_cpu_threshold: float = 0.02, idle_days_threshold: float = 3.0) -> None:
        self._idle_cpu_threshold = idle_cpu_threshold
        self._idle_days_threshold = idle_days_threshold
        self._idle_since: dict[str, float] = {}

    def evaluate(self, items: list[dict], now: float) -> list[dict]:
        suggestions: list[dict] = []
        seen_keys: set[str] = set()
        for item in items:
            key = f"{item.get('host_id')}:{item.get('node')}:{item.get('vmid')}"
            seen_keys.add(key)
            status = str(item.get("status", "")).lower()
            cpu = item.get("cpu")
            is_idle = status == "running" and cpu is not None and cpu <= self._idle_cpu_threshold
            if not is_idle:
                self._idle_since.pop(key, None)
                continue
            first_seen = self._idle_since.setdefault(key, now)
            idle_days = (now - first_seen) / 86400
            if idle_days < self._idle_days_threshold:
                continue
            name = item.get("name") or key
            suggestions.append({
                "kind": "idle_resource",
                "key": key,
                "idle_days": round(idle_days, 1),
                "message": f"{name} has been idle for {idle_days:.1f} days. "
                           f"Consider stopping it to free up resources.",
            })
        for stale_key in set(self._idle_since) - seen_keys:
            self._idle_since.pop(stale_key, None)
        return suggestions


class SuggestionEngine:
    """Composes the individual heuristics and rate-limits how often each distinct
    suggestion is re-surfaced (per-key cooldown, same idea as AlertEngine's cooldown).
    """

    def __init__(
        self,
        idle_cpu_threshold: float = 0.02,
        idle_days_threshold: float = 3.0,
        cooldown_seconds: int = _DEFAULT_COOLDOWN_SECONDS,
    ) -> None:
        self._idle_tracker = IdleResourceTracker(idle_cpu_threshold, idle_days_threshold)
        self._cooldown_seconds = cooldown_seconds
        self._last_fired: dict[str, float] = {}

    def _ready(self, key: str, now: float) -> bool:
        if now - self._last_fired.get(key, 0.0) < self._cooldown_seconds:
            return False
        self._last_fired[key] = now
        return True

    def evaluate(
        self,
        *,
        learned_replies: dict,
        proxmox_health: dict | None,
        backup_log: list[dict],
        now: float | None = None,
        skill_threshold: int = 5,
        backup_streak_threshold: int = 3,
    ) -> list[dict]:
        now = time.time() if now is None else now
        candidates: list[dict] = list(detect_repeated_skill_invocations(learned_replies, skill_threshold))
        if proxmox_health:
            candidates.extend(self._idle_tracker.evaluate(flatten_proxmox_items(proxmox_health), now))
        backup_suggestion = detect_backup_failure_streak(backup_log, backup_streak_threshold)
        if backup_suggestion:
            candidates.append(backup_suggestion)

        ready: list[dict] = []
        for candidate in candidates:
            cooldown_key = f"{candidate.get('kind')}:{candidate.get('key')}"
            if not self._ready(cooldown_key, now):
                continue
            ready.append({
                "type": "suggestion",
                "suggestion_id": f"sugg-{uuid.uuid4().hex[:12]}",
                "timestamp": int(now),
                **candidate,
            })
        return ready
