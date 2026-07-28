---
name: websocket-fanout
description: How AlertBroadcaster fans out engine-fired alerts to all connected /ws/alerts WebSocket clients
metadata:
  type: project
---

`AlertBroadcaster` is a module-level singleton in `jarvis/api_alerts.py`, exported via `get_alert_broadcaster()`.

**Pattern:**
- Thread-safe `set[WebSocket]` protected by `threading.Lock`
- `connect(ws)` / `disconnect(ws)` called from the `/ws/alerts` WebSocket handler
- `broadcast(payload: dict)` async method iterates all clients, calls `ws.send_json(payload)`, discards any client that raises (handles disconnected clients atomically)
- `AlertEngine` holds a reference to `get_alert_broadcaster().broadcast` as `broadcast_fn`

**Integration:** When `AlertEngine._evaluate_rule()` determines an alert should fire, it calls `await self._broadcast(event)` which calls `broadcast_fn(event)` — the broadcaster fans out to all live WebSocket clients.

**Alert payload structure:**
```json
{
  "type": "alert",
  "alert_id": "alert-<uuid12>",
  "rule_id": "rule-<uuid12>",
  "rule_name": "High CPU",
  "severity": "warning|info|critical",
  "metric": "cpu|ram|disk|ha_health|ha_entity",
  "current_value": 92.4,
  "threshold": 90.0,
  "message": "CPU utilization has exceeded 90%...",
  "timestamp": 1716220800
}
```

**HA alerts** (from existing health check) are still pushed on WebSocket connect and every 30s as a separate polling path. Engine-fired alerts are pushed immediately when they fire.

**Frontend hook:** `useJarvisAlerts()` in `frontend/src/shared/api/alerts.ts` subscribes to `/ws/alerts?session=<token>` and handles both `type: "alerts"` (HA health array) and `type: "alert"` (engine single event) — note: the single-event payload uses `type: "alert"` (singular) but the HA batch uses `type: "alerts"` (plural).

**2026-07-27 update — user_id tracking + push fanout (V2 Phase 0/1):** `AlertBroadcaster._clients` changed from `set[WebSocket]` to `dict[WebSocket, str | None]` mapping socket -> user_id. `connect(ws, user_id=None)` (backward compatible, user_id optional) and new `connected_user_ids() -> set[str]`. The `/ws/alerts` handler in `api_alerts.py` now calls `_broadcaster.connect(websocket, user_id=session["user"]["id"])`. New `configure_push_fanout(fn: Callable[[dict, set[str]], Awaitable[None]])` lets `jarvisappv4.py` register a callback that `broadcast()` invokes after the WS fan-out, passing the payload and the currently-connected user_ids — this is how webpush delivery (see [[push-notifications-architecture]]) reaches users who are subscribed but not live on `/ws/alerts`, for every broadcast type (alert, briefing, weekly_digest, nightly_summary, suggestion) since they all funnel through this same broadcaster. Push-fanout failures are caught and logged, never crash `broadcast()`.

**Broadcast types now flowing through this single broadcaster** (all with a `type` field the frontend hook switches on): `alert` (engine-fired), `alerts` (HA health batch, on connect + 30s poll), `briefing` (morning briefing, has `user_id`), `weekly_digest` (has `user_id`), `nightly_summary` (has `user_id`), `suggestion` (system-wide, no `user_id`). See [[proactive-intelligence-v2]] for the last three.
