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
  "metric": "cpu|ram|disk|ha_entity",
  "current_value": 92.4,
  "threshold": 90.0,
  "message": "CPU utilization has exceeded 90%...",
  "timestamp": 1716220800
}
```

**HA alerts** (from existing health check) are still pushed on WebSocket connect and every 30s as a separate polling path. Engine-fired alerts are pushed immediately when they fire.

**Frontend hook:** `useJarvisAlerts()` in `frontend/src/shared/api/alerts.ts` subscribes to `/ws/alerts?session=<token>` and handles both `type: "alerts"` (HA health array) and `type: "alert"` (engine single event) — note: the single-event payload uses `type: "alert"` (singular) but the HA batch uses `type: "alerts"` (plural).
