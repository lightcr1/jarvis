---
name: alert-engine-architecture
description: How the AlertEngine background task integrates with JARVIS — startup, deps, wiring
metadata:
  type: project
---

The alert engine is implemented across four new/modified files:

- `jarvis/alert_store.py` — `AlertRulesStore` for JSON persistence of rules at `/var/lib/jarvis/alert_rules.json` (env `JARVIS_ALERT_RULES_PATH`). Seeds 4 default rules on first run.
- `jarvis/alert_engine.py` — `AlertEngine` class with `start()`, `stop()`, `reload_rules()` methods. Runs as an asyncio background task polling metrics every 30s (env `JARVIS_ALERT_POLL_INTERVAL`, min 10s). Holds in-memory history (deque, max 500) and per-rule cooldown/duration state.
- `jarvis/api_alerts.py` — `AlertBroadcaster` (module-level singleton, thread-safe) + REST CRUD endpoints under `/admin/alerts/*`. The WebSocket `/ws/alerts` accepts the broadcaster for push delivery.
- `jarvisappv4.py` — Instantiates `AlertRulesStore`, `AlertEngine`, calls `alert_engine.start()` in lifespan and `alert_engine.stop()` on shutdown.

**Wiring in jarvisappv4.py:**
```python
alert_rules_store = AlertRulesStore()
alert_engine = AlertEngine(
    rules_store=alert_rules_store,
    audit_admin_event=_audit_admin_event,
    ha_store=home_assistant_store,
    broadcast_fn=get_alert_broadcaster().broadcast,
)
```

Lifespan: `alert_engine.start()` before yield, `alert_engine.stop()` after.

**Dependency injection:** `build_alerts_deps()` in `router_dependencies.py` now includes `alert_rules_store`, `alert_engine`, `require_admin_access`, and `audit_admin_event`.

**Metric reading:** CPU via psutil (with `/proc/stat` fallback — psutil is in requirements.txt), RAM via `jarvis.skill_utils.parse_meminfo`, disk via `jarvis.skill_utils.disk_usage`. HA entity state via `HomeAssistantStore.get_managed_entity()`. HA health via `HomeAssistantStore.connection_status()` returning "ok" or "unreachable".

**Why:** Deferred items — HA WebSocket subscription vs polling decision: currently polls the cached store (no new HTTP). If HA store is empty or entity missing, rule is silently skipped with a debug log.
