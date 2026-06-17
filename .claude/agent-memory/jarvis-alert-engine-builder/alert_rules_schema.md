---
name: alert-rules-schema
description: AlertRule schema, storage path, default rules, and normalization logic
metadata:
  type: project
---

Alert rules are stored in `alert_rules.json` (default `/var/lib/jarvis/alert_rules.json`, env `JARVIS_ALERT_RULES_PATH`), managed by `AlertRulesStore` in `jarvis/alert_store.py`.

**Schema per rule:**
```json
{
  "id": "rule-<uuid12>",
  "name": "string",
  "enabled": true,
  "metric": "cpu|ram|disk|ha_health|ha_entity",
  "condition": "above|below|equals|contains",
  "threshold": 90.0,
  "duration_seconds": 300,
  "severity": "info|warning|critical",
  "cooldown_seconds": 300,
  "ha_entity_id": null,
  "ha_attribute": null,
  "message_template": "CPU has been above {threshold}% for {duration}s"
}
```

Template variables: `{metric}`, `{value}`, `{threshold}`, `{duration}`, `{name}`.

**Default rules (inserted once on first run, seeded=True flag prevents re-seeding):**
- `default-cpu-warning`: CPU > 90% for 300s → warning
- `default-cpu-critical`: CPU > 95% for 60s → critical
- `default-ram-warning`: RAM > 85% for 120s → warning
- `default-disk-critical`: Disk > 90% (no duration) → critical
- `default-ha-unreachable`: HA health equals "unreachable" for 180s → warning

**Pydantic models** in `jarvis/api_models.py`: `AlertRuleCreate`, `AlertRuleUpdate`.

**Permission** added to `KNOWN_PERMISSIONS` in `permission_store.py`: `alerts.manage`.

**REST endpoints** (all require admin auth):
- `GET /admin/alerts/rules`
- `POST /admin/alerts/rules`
- `PATCH /admin/alerts/rules/{rule_id}`
- `DELETE /admin/alerts/rules/{rule_id}`
- `POST /admin/alerts/rules/{rule_id}/test`
- `GET /admin/alerts/history`
