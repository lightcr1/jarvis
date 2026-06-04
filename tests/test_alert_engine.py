from __future__ import annotations

import asyncio
import time
import unittest

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jarvis.alert_store import AlertRulesStore, _DEFAULT_RULES
from jarvis.alert_engine import (
    AlertEngine,
    _evaluate_condition,
    _build_message,
    _build_alert_event,
)
from jarvis.api_alerts import build_alerts_router, AlertBroadcaster
from jarvis.router_dependencies import LiveRef


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeAudit:
    def __init__(self):
        self.events: list[tuple] = []

    def __call__(self, event, actor_user_id, actor_role, payload=None):
        self.events.append((event, actor_user_id, actor_role, payload))


class _FakeHAService:
    def overview(self, user_id, role):
        return {"alerts": []}

    def health_status(self, user_id, role):
        return {"alerts": {}}


def _make_deps(store: AlertRulesStore, engine: AlertEngine, audit: _FakeAudit):
    from fastapi import HTTPException as _HTTPException
    def require_admin_access(uid, role, auth, *, allow_bootstrap=False):
        if auth == "Bearer valid-admin-token":
            return ("usr-admin", "admin")
        raise _HTTPException(401, "unauthorized")

    def require_identity_session(token):
        if token == "valid-session":
            return {"user": {"id": "usr-admin", "role": "admin"}}
        raise Exception("unauthorized")

    return {
        "require_admin_access": require_admin_access,
        "require_identity_session": require_identity_session,
        "home_assistant_service": _FakeHAService(),
        "alert_rules_store": store,
        "alert_engine": engine,
        "audit_admin_event": audit,
    }


def _build_app(store: AlertRulesStore, engine: AlertEngine, audit: _FakeAudit) -> FastAPI:
    app = FastAPI()
    app.include_router(build_alerts_router(_make_deps(store, engine, audit)))
    return app


_ADMIN_HDR = {"Authorization": "Bearer valid-admin-token"}


# ---------------------------------------------------------------------------
# AlertRulesStore tests
# ---------------------------------------------------------------------------

class TestAlertRulesStore(unittest.TestCase):
    def setUp(self):
        import os, tempfile
        self._tmp = tempfile.mktemp(suffix=".json")
        os.environ["JARVIS_ALERT_RULES_PATH"] = self._tmp

    def tearDown(self):
        import os
        os.environ.pop("JARVIS_ALERT_RULES_PATH", None)
        try:
            os.unlink(self._tmp)
        except OSError:
            pass

    def test_default_rules_seeded(self):
        store = AlertRulesStore()
        rules = store.list_rules()
        assert len(rules) >= 4
        ids = [r["id"] for r in rules]
        assert "default-cpu-warning" in ids

    def test_create_rule(self):
        store = AlertRulesStore()
        rule = store.create_rule({
            "name": "Test CPU",
            "metric": "cpu",
            "condition": "above",
            "threshold": 75.0,
            "duration_seconds": 60,
            "severity": "warning",
            "cooldown_seconds": 300,
        })
        assert rule["name"] == "Test CPU"
        assert rule["metric"] == "cpu"
        assert rule["id"].startswith("rule-")
        all_rules = store.list_rules()
        assert any(r["id"] == rule["id"] for r in all_rules)

    def test_update_rule(self):
        store = AlertRulesStore()
        updated = store.update_rule("default-cpu-warning", {"threshold": 95.0, "enabled": False})
        assert updated is not None
        assert updated["threshold"] == 95.0
        assert updated["enabled"] is False

    def test_update_missing_rule(self):
        store = AlertRulesStore()
        result = store.update_rule("nonexistent-id", {"threshold": 99.0})
        assert result is None

    def test_delete_rule(self):
        store = AlertRulesStore()
        result = store.delete_rule("default-cpu-warning")
        assert result is True
        assert store.get_rule("default-cpu-warning") is None

    def test_delete_missing_rule(self):
        store = AlertRulesStore()
        result = store.delete_rule("does-not-exist")
        assert result is False

    def test_get_rule(self):
        store = AlertRulesStore()
        rule = store.get_rule("default-disk-critical")
        assert rule is not None
        assert rule["severity"] == "critical"


# ---------------------------------------------------------------------------
# Condition evaluation unit tests
# ---------------------------------------------------------------------------

class TestEvaluateCondition(unittest.TestCase):
    def test_above_true(self):
        assert _evaluate_condition(95.0, "above", 90.0) is True

    def test_above_false(self):
        assert _evaluate_condition(85.0, "above", 90.0) is False

    def test_below_true(self):
        assert _evaluate_condition(10.0, "below", 20.0) is True

    def test_below_false(self):
        assert _evaluate_condition(30.0, "below", 20.0) is False

    def test_equals_numeric(self):
        assert _evaluate_condition(42.0, "equals", 42.0) is True
        assert _evaluate_condition(42.0, "equals", 43.0) is False

    def test_equals_string(self):
        assert _evaluate_condition("on", "equals", "on") is True
        assert _evaluate_condition("off", "equals", "on") is False

    def test_contains(self):
        assert _evaluate_condition("temperature is high", "contains", "high") is True
        assert _evaluate_condition("temperature is low", "contains", "high") is False


# ---------------------------------------------------------------------------
# Message building
# ---------------------------------------------------------------------------

class TestBuildMessage(unittest.TestCase):
    def test_template_substitution(self):
        rule = {
            "metric": "cpu",
            "threshold": 90.0,
            "duration_seconds": 300,
            "name": "CPU",
            "message_template": "CPU has been above {threshold}% for {duration}s",
        }
        msg = _build_message(rule, 92.4)
        assert "90.0%" in msg
        assert "300s" in msg

    def test_fallback_on_bad_template(self):
        rule = {
            "metric": "cpu",
            "threshold": 90.0,
            "duration_seconds": 0,
            "name": "CPU",
            "message_template": "No subs here",
        }
        msg = _build_message(rule, 92.4)
        assert "No subs here" in msg


# ---------------------------------------------------------------------------
# AlertEngine logic tests (async)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_engine_fires_alert_when_threshold_exceeded():
    import os, tempfile
    tmp = tempfile.mktemp(suffix=".json")
    os.environ["JARVIS_ALERT_RULES_PATH"] = tmp
    try:
        store = AlertRulesStore()
        store.data["rules"] = []
        store.create_rule({
            "name": "Test immediate",
            "metric": "cpu",
            "condition": "above",
            "threshold": 0.0,
            "duration_seconds": 0,
            "severity": "warning",
            "cooldown_seconds": 60,
        })

        fired: list[dict] = []
        async def fake_broadcast(event):
            fired.append(event)

        audit = _FakeAudit()
        engine = AlertEngine(
            rules_store=store,
            audit_admin_event=audit,
            broadcast_fn=fake_broadcast,
        )

        rules = store.list_rules()
        rule = rules[0]
        now = time.time()
        engine._threshold_crossed_at = {}
        engine._last_fired_at = {}

        # Patch _read_metric to return high value
        engine._read_metric = lambda r: 99.0

        await engine._evaluate_rule(rule, now)
        assert len(fired) == 1
        assert fired[0]["metric"] == "cpu"
        assert fired[0]["severity"] == "warning"
        assert len(audit.events) == 1
    finally:
        os.environ.pop("JARVIS_ALERT_RULES_PATH", None)
        try:
            os.unlink(tmp)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_engine_respects_cooldown():
    import os, tempfile
    tmp = tempfile.mktemp(suffix=".json")
    os.environ["JARVIS_ALERT_RULES_PATH"] = tmp
    try:
        store = AlertRulesStore()
        store.data["rules"] = []
        store.create_rule({
            "name": "Cooldown test",
            "metric": "cpu",
            "condition": "above",
            "threshold": 0.0,
            "duration_seconds": 0,
            "severity": "warning",
            "cooldown_seconds": 600,
        })

        fired: list[dict] = []
        async def fake_broadcast(event):
            fired.append(event)

        audit = _FakeAudit()
        engine = AlertEngine(
            rules_store=store,
            audit_admin_event=audit,
            broadcast_fn=fake_broadcast,
        )
        engine._read_metric = lambda r: 99.0

        rule = store.list_rules()[0]
        rule_id = rule["id"]
        now = time.time()

        await engine._evaluate_rule(rule, now)
        assert len(fired) == 1

        # Second evaluation within cooldown window — should NOT fire
        await engine._evaluate_rule(rule, now + 10)
        assert len(fired) == 1
    finally:
        os.environ.pop("JARVIS_ALERT_RULES_PATH", None)
        try:
            os.unlink(tmp)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_engine_respects_duration():
    import os, tempfile
    tmp = tempfile.mktemp(suffix=".json")
    os.environ["JARVIS_ALERT_RULES_PATH"] = tmp
    try:
        store = AlertRulesStore()
        store.data["rules"] = []
        store.create_rule({
            "name": "Duration test",
            "metric": "cpu",
            "condition": "above",
            "threshold": 0.0,
            "duration_seconds": 300,
            "severity": "warning",
            "cooldown_seconds": 60,
        })

        fired: list[dict] = []
        async def fake_broadcast(event):
            fired.append(event)

        audit = _FakeAudit()
        engine = AlertEngine(
            rules_store=store,
            audit_admin_event=audit,
            broadcast_fn=fake_broadcast,
        )
        engine._read_metric = lambda r: 99.0

        rule = store.list_rules()[0]
        rule_id = rule["id"]
        now = time.time()

        # First evaluation — threshold crossed, but duration not met
        await engine._evaluate_rule(rule, now)
        assert len(fired) == 0

        # 100s later — still not 300s
        await engine._evaluate_rule(rule, now + 100)
        assert len(fired) == 0

        # Threshold drops — state reset
        engine._read_metric = lambda r: None
        await engine._evaluate_rule(rule, now + 150)
        assert len(fired) == 0
        assert rule_id not in engine._threshold_crossed_at

        # Threshold crosses again — timer restarts
        engine._read_metric = lambda r: 99.0
        await engine._evaluate_rule(rule, now + 200)
        assert len(fired) == 0

        # 301s after the second crossing — should fire
        await engine._evaluate_rule(rule, now + 510)
        assert len(fired) == 1
    finally:
        os.environ.pop("JARVIS_ALERT_RULES_PATH", None)
        try:
            os.unlink(tmp)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_engine_skips_ha_entity_when_not_found():
    import os, tempfile
    tmp = tempfile.mktemp(suffix=".json")
    os.environ["JARVIS_ALERT_RULES_PATH"] = tmp
    try:
        store = AlertRulesStore()
        store.data["rules"] = []
        store.create_rule({
            "name": "HA entity test",
            "metric": "ha_entity",
            "condition": "equals",
            "threshold": "on",
            "duration_seconds": 0,
            "severity": "info",
            "cooldown_seconds": 60,
            "ha_entity_id": "switch.nonexistent",
            "ha_attribute": "state",
        })

        fired: list[dict] = []
        async def fake_broadcast(event):
            fired.append(event)

        audit = _FakeAudit()

        class _EmptyHAStore:
            def get_managed_entity(self, entity_id):
                return None

        engine = AlertEngine(
            rules_store=store,
            audit_admin_event=audit,
            ha_store=_EmptyHAStore(),
            broadcast_fn=fake_broadcast,
        )

        rule = store.list_rules()[0]
        await engine._evaluate_rule(rule, time.time())
        # Should not fire — entity not found
        assert len(fired) == 0
    finally:
        os.environ.pop("JARVIS_ALERT_RULES_PATH", None)
        try:
            os.unlink(tmp)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# REST endpoint tests
# ---------------------------------------------------------------------------

class TestAlertsRestEndpoints(unittest.TestCase):
    def setUp(self):
        import os, tempfile
        self._tmp = tempfile.mktemp(suffix=".json")
        os.environ["JARVIS_ALERT_RULES_PATH"] = self._tmp
        self._store = AlertRulesStore()
        self._audit = _FakeAudit()
        self._engine = AlertEngine(
            rules_store=self._store,
            audit_admin_event=self._audit,
        )
        self._app = _build_app(self._store, self._engine, self._audit)
        self._client = TestClient(self._app, raise_server_exceptions=False)

    def tearDown(self):
        import os
        os.environ.pop("JARVIS_ALERT_RULES_PATH", None)
        try:
            os.unlink(self._tmp)
        except OSError:
            pass

    def test_list_rules_requires_auth(self):
        resp = self._client.get("/admin/alerts/rules")
        assert resp.status_code in (401, 403, 500)

    def test_list_rules_with_auth(self):
        resp = self._client.get("/admin/alerts/rules", headers=_ADMIN_HDR)
        assert resp.status_code == 200
        data = resp.json()
        assert "rules" in data
        assert len(data["rules"]) >= 4

    def test_create_rule(self):
        resp = self._client.post(
            "/admin/alerts/rules",
            json={
                "name": "My CPU Rule",
                "metric": "cpu",
                "condition": "above",
                "threshold": 80.0,
                "duration_seconds": 60,
                "severity": "warning",
                "cooldown_seconds": 300,
                "message_template": "CPU is {value}%",
            },
            headers=_ADMIN_HDR,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["rule"]["name"] == "My CPU Rule"
        assert data["rule"]["id"].startswith("rule-")

    def test_create_rule_invalid_metric(self):
        resp = self._client.post(
            "/admin/alerts/rules",
            json={
                "name": "Bad",
                "metric": "foobar",
                "condition": "above",
                "threshold": 80.0,
            },
            headers=_ADMIN_HDR,
        )
        assert resp.status_code == 422

    def test_update_rule(self):
        resp = self._client.patch(
            "/admin/alerts/rules/default-cpu-warning",
            json={"threshold": 95.0},
            headers=_ADMIN_HDR,
        )
        assert resp.status_code == 200
        assert resp.json()["rule"]["threshold"] == 95.0

    def test_update_missing_rule(self):
        resp = self._client.patch(
            "/admin/alerts/rules/nonexistent",
            json={"threshold": 95.0},
            headers=_ADMIN_HDR,
        )
        assert resp.status_code == 404

    def test_delete_rule(self):
        resp = self._client.delete(
            "/admin/alerts/rules/default-cpu-warning",
            headers=_ADMIN_HDR,
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        # Confirm it's gone
        list_resp = self._client.get("/admin/alerts/rules", headers=_ADMIN_HDR)
        ids = [r["id"] for r in list_resp.json()["rules"]]
        assert "default-cpu-warning" not in ids

    def test_delete_missing_rule(self):
        resp = self._client.delete(
            "/admin/alerts/rules/nonexistent",
            headers=_ADMIN_HDR,
        )
        assert resp.status_code == 404

    def test_test_rule_endpoint(self):
        resp = self._client.post(
            "/admin/alerts/rules/default-cpu-warning/test",
            headers=_ADMIN_HDR,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "event" in data
        assert data["event"]["rule_id"] == "default-cpu-warning"

    def test_test_missing_rule(self):
        resp = self._client.post(
            "/admin/alerts/rules/nonexistent/test",
            headers=_ADMIN_HDR,
        )
        assert resp.status_code == 404

    def test_history_endpoint(self):
        # Trigger a test to add to history
        self._client.post("/admin/alerts/rules/default-cpu-warning/test", headers=_ADMIN_HDR)
        resp = self._client.get("/admin/alerts/history", headers=_ADMIN_HDR)
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        assert len(data["alerts"]) >= 1

    def test_audit_events_logged(self):
        self._client.post(
            "/admin/alerts/rules",
            json={"name": "Audit test", "metric": "cpu", "condition": "above", "threshold": 80.0},
            headers=_ADMIN_HDR,
        )
        events = [e[0] for e in self._audit.events]
        assert "alert.rule.created" in events

    def test_create_requires_auth(self):
        resp = self._client.post(
            "/admin/alerts/rules",
            json={"name": "Sneaky", "metric": "cpu", "condition": "above", "threshold": 80.0},
        )
        assert resp.status_code in (401, 403, 500)


# ---------------------------------------------------------------------------
# AlertBroadcaster test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_broadcaster_fanout():
    broadcaster = AlertBroadcaster()
    received: list[dict] = []

    class _FakeWS:
        async def send_json(self, data):
            received.append(data)

    ws1 = _FakeWS()
    ws2 = _FakeWS()
    broadcaster.connect(ws1)  # type: ignore
    broadcaster.connect(ws2)  # type: ignore

    await broadcaster.broadcast({"type": "alert", "message": "hello"})
    assert len(received) == 2

    broadcaster.disconnect(ws1)  # type: ignore
    await broadcaster.broadcast({"type": "alert", "message": "world"})
    assert len(received) == 3  # only ws2 receives
