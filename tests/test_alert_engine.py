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
# Compound (multi-signal) rule tests
# ---------------------------------------------------------------------------

def _compound_setup(combinator: str):
    import os, tempfile
    tmp = tempfile.mktemp(suffix=".json")
    os.environ["JARVIS_ALERT_RULES_PATH"] = tmp
    store = AlertRulesStore()
    store.data["rules"] = []
    store.create_rule({
        "name": "Compound test",
        "conditions": [
            {"metric": "cpu", "condition": "above", "threshold": 80.0},
            {"metric": "ram", "condition": "above", "threshold": 70.0},
        ],
        "combinator": combinator,
        "duration_seconds": 0,
        "severity": "warning",
        "cooldown_seconds": 60,
    })
    fired: list[dict] = []

    async def fake_broadcast(event):
        fired.append(event)

    engine = AlertEngine(rules_store=store, audit_admin_event=_FakeAudit(), broadcast_fn=fake_broadcast)
    return tmp, store, engine, fired


@pytest.mark.asyncio
async def test_compound_rule_stores_clauses_and_combinator():
    import os
    tmp, store, engine, fired = _compound_setup("and")
    try:
        rule = store.list_rules()[0]
        assert rule["combinator"] == "and"
        assert len(rule["conditions"]) == 2
        assert rule["conditions"][0]["metric"] == "cpu"
        # Single-condition fields mirror clause 0 for any legacy consumer.
        assert rule["metric"] == "cpu"
        assert rule["threshold"] == 80.0
    finally:
        os.environ.pop("JARVIS_ALERT_RULES_PATH", None)
        try:
            os.unlink(tmp)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_compound_and_requires_all_clauses_true():
    import os
    tmp, store, engine, fired = _compound_setup("and")
    try:
        rule = store.list_rules()[0]
        now = time.time()

        engine._evaluate_clauses = lambda r, clauses: [(True, 90.0), (False, 50.0)]
        await engine._evaluate_rule(rule, now)
        assert len(fired) == 0

        engine._evaluate_clauses = lambda r, clauses: [(True, 90.0), (True, 80.0)]
        await engine._evaluate_rule(rule, now + 1)
        assert len(fired) == 1
    finally:
        os.environ.pop("JARVIS_ALERT_RULES_PATH", None)
        try:
            os.unlink(tmp)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_compound_or_fires_when_any_clause_true():
    import os
    tmp, store, engine, fired = _compound_setup("or")
    try:
        rule = store.list_rules()[0]
        now = time.time()

        engine._evaluate_clauses = lambda r, clauses: [(True, 90.0), (False, 50.0)]
        await engine._evaluate_rule(rule, now)
        assert len(fired) == 1
    finally:
        os.environ.pop("JARVIS_ALERT_RULES_PATH", None)
        try:
            os.unlink(tmp)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_compound_or_does_not_fire_when_all_clauses_false():
    import os
    tmp, store, engine, fired = _compound_setup("or")
    try:
        rule = store.list_rules()[0]
        now = time.time()

        engine._evaluate_clauses = lambda r, clauses: [(False, 10.0), (False, 50.0)]
        await engine._evaluate_rule(rule, now)
        assert len(fired) == 0
    finally:
        os.environ.pop("JARVIS_ALERT_RULES_PATH", None)
        try:
            os.unlink(tmp)
        except OSError:
            pass


def test_presence_idle_minutes_signal_source():
    from jarvis.alert_engine import _read_presence_idle_minutes

    class _FakeUserStore:
        def get_user(self, user_id):
            return {"id": user_id, "last_seen_at": time.time() - 900} if user_id == "u1" else None

    assert _read_presence_idle_minutes(None, "u1") is None
    assert _read_presence_idle_minutes(_FakeUserStore(), None) is None
    assert _read_presence_idle_minutes(_FakeUserStore(), "missing") is None
    minutes = _read_presence_idle_minutes(_FakeUserStore(), "u1")
    assert 14.5 < minutes < 15.5

    class _NeverSeenStore:
        def get_user(self, user_id):
            return {"id": user_id}

    assert _read_presence_idle_minutes(_NeverSeenStore(), "u1") == 1_000_000.0


def test_calendar_upcoming_minutes_signal_source():
    from jarvis.alert_engine import _read_calendar_upcoming_minutes

    now = int(time.time())

    class _FakeCalendarService:
        def __init__(self, events):
            self._events = events

        def list_events(self, *, user_id, role, start=None):
            return {"events": self._events}

    assert _read_calendar_upcoming_minutes(None, "u1") is None
    assert _read_calendar_upcoming_minutes(_FakeCalendarService([]), None) is None
    assert _read_calendar_upcoming_minutes(_FakeCalendarService([]), "u1") == 10_000.0

    soon = _FakeCalendarService([{"id": "e1", "start": now + 600, "end": now + 1200}])
    minutes = _read_calendar_upcoming_minutes(soon, "u1")
    assert 9.5 < minutes < 10.5


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

    def test_create_compound_rule_via_rest(self):
        resp = self._client.post(
            "/admin/alerts/rules",
            json={
                "name": "Meeting soon and idle",
                "conditions": [
                    {"metric": "calendar_upcoming_minutes", "condition": "below", "threshold": 10},
                    {"metric": "presence_idle_minutes", "condition": "above", "threshold": 15},
                ],
                "combinator": "and",
                "severity": "info",
                "cooldown_seconds": 300,
            },
            headers=_ADMIN_HDR,
        )
        assert resp.status_code == 201
        rule = resp.json()["rule"]
        assert rule["combinator"] == "and"
        assert len(rule["conditions"]) == 2
        assert rule["conditions"][0]["metric"] == "calendar_upcoming_minutes"
        # Fetching the rule back (GET-side of the CRUD loop) preserves the clauses.
        listed = self._client.get("/admin/alerts/rules", headers=_ADMIN_HDR).json()["rules"]
        persisted = next(r for r in listed if r["id"] == rule["id"])
        assert persisted["combinator"] == "and"
        assert len(persisted["conditions"]) == 2

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
# Self-service /alerts/rules tests (alerts.manage permission, own-rule scoping)
# ---------------------------------------------------------------------------

_OWN_SESSIONS = {
    "admin-session": {"user": {"id": "usr-admin", "role": "admin"}},
    "user-a-session": {"user": {"id": "usr-a", "role": "standard_user"}},
    "user-b-session": {"user": {"id": "usr-b", "role": "standard_user"}},
    "user-noperm-session": {"user": {"id": "usr-noperm", "role": "standard_user"}},
}
_OWN_PERMISSIONS = {
    "usr-admin": {"alerts.manage"},
    "usr-a": {"alerts.manage"},
    "usr-b": {"alerts.manage"},
    "usr-noperm": set(),
}


def _make_own_deps(store: AlertRulesStore, engine: AlertEngine, audit: _FakeAudit):
    def require_identity_session(token):
        if token in _OWN_SESSIONS:
            return _OWN_SESSIONS[token]
        raise Exception("unauthorized")

    def resolve_effective_permissions(role, user_id, membership_store, permission_store):
        return set(_OWN_PERMISSIONS.get(user_id, set()))

    return {
        "require_admin_access": lambda *a, **kw: ("usr-admin", "admin"),
        "require_identity_session": require_identity_session,
        "resolve_effective_permissions": resolve_effective_permissions,
        "membership_store": None,
        "permission_store": None,
        "home_assistant_service": _FakeHAService(),
        "alert_rules_store": store,
        "alert_engine": engine,
        "audit_admin_event": audit,
    }


class TestOwnAlertRulesRestEndpoints(unittest.TestCase):
    def setUp(self):
        import os, tempfile
        self._tmp = tempfile.mktemp(suffix=".json")
        os.environ["JARVIS_ALERT_RULES_PATH"] = self._tmp
        self._store = AlertRulesStore()
        self._audit = _FakeAudit()
        self._engine = AlertEngine(rules_store=self._store, audit_admin_event=self._audit)
        app = FastAPI()
        app.include_router(build_alerts_router(_make_own_deps(self._store, self._engine, self._audit)))
        self._client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        import os
        os.environ.pop("JARVIS_ALERT_RULES_PATH", None)
        try:
            os.unlink(self._tmp)
        except OSError:
            pass

    def _rule_payload(self, name="My rule"):
        return {
            "name": name,
            "metric": "cpu",
            "condition": "above",
            "threshold": 80.0,
            "duration_seconds": 0,
            "severity": "warning",
            "cooldown_seconds": 300,
        }

    def test_list_requires_session(self):
        resp = self._client.get("/alerts/rules")
        assert resp.status_code in (401, 403, 500)

    def test_denied_without_alerts_manage_permission(self):
        resp = self._client.get("/alerts/rules", headers={"X-Jarvis-Session": "user-noperm-session"})
        assert resp.status_code == 403

    def test_create_and_list_own_rule(self):
        created = self._client.post(
            "/alerts/rules", json=self._rule_payload(), headers={"X-Jarvis-Session": "user-a-session"}
        )
        assert created.status_code == 201
        rule = created.json()["rule"]
        assert rule["owner_user_id"] == "usr-a"

        listed = self._client.get("/alerts/rules", headers={"X-Jarvis-Session": "user-a-session"})
        assert listed.status_code == 200
        ids = [r["id"] for r in listed.json()["rules"]]
        assert rule["id"] in ids
        # Default system rules (owner_user_id=None) must not leak into a user's own list.
        assert "default-cpu-warning" not in ids

    def test_user_cannot_see_or_modify_another_users_rule(self):
        created = self._client.post(
            "/alerts/rules", json=self._rule_payload(), headers={"X-Jarvis-Session": "user-a-session"}
        ).json()["rule"]

        other_list = self._client.get("/alerts/rules", headers={"X-Jarvis-Session": "user-b-session"})
        assert created["id"] not in [r["id"] for r in other_list.json()["rules"]]

        denied_update = self._client.patch(
            f"/alerts/rules/{created['id']}", json={"threshold": 50.0}, headers={"X-Jarvis-Session": "user-b-session"}
        )
        assert denied_update.status_code == 404

        denied_delete = self._client.delete(
            f"/alerts/rules/{created['id']}", headers={"X-Jarvis-Session": "user-b-session"}
        )
        assert denied_delete.status_code == 404

        denied_test = self._client.post(
            f"/alerts/rules/{created['id']}/test", headers={"X-Jarvis-Session": "user-b-session"}
        )
        assert denied_test.status_code == 404

    def test_owner_can_update_and_delete_own_rule(self):
        created = self._client.post(
            "/alerts/rules", json=self._rule_payload(), headers={"X-Jarvis-Session": "user-a-session"}
        ).json()["rule"]

        updated = self._client.patch(
            f"/alerts/rules/{created['id']}", json={"threshold": 55.0}, headers={"X-Jarvis-Session": "user-a-session"}
        )
        assert updated.status_code == 200
        assert updated.json()["rule"]["threshold"] == 55.0

        tested = self._client.post(
            f"/alerts/rules/{created['id']}/test", headers={"X-Jarvis-Session": "user-a-session"}
        )
        assert tested.status_code == 200

        deleted = self._client.delete(
            f"/alerts/rules/{created['id']}", headers={"X-Jarvis-Session": "user-a-session"}
        )
        assert deleted.status_code == 200

    def test_admin_own_rule_does_not_leak_into_other_users_list(self):
        admin_rule = self._client.post(
            "/alerts/rules", json=self._rule_payload("Admin personal rule"), headers={"X-Jarvis-Session": "admin-session"}
        ).json()["rule"]
        assert admin_rule["owner_user_id"] == "usr-admin"

        user_list = self._client.get("/alerts/rules", headers={"X-Jarvis-Session": "user-a-session"})
        assert admin_rule["id"] not in [r["id"] for r in user_list.json()["rules"]]

    def test_admin_dashboard_listing_still_sees_all_rules_including_user_owned(self):
        own_rule = self._client.post(
            "/alerts/rules", json=self._rule_payload(), headers={"X-Jarvis-Session": "user-a-session"}
        ).json()["rule"]

        admin_list = self._client.get("/admin/alerts/rules", headers=_ADMIN_HDR)
        assert admin_list.status_code == 200
        ids = [r["id"] for r in admin_list.json()["rules"]]
        assert own_rule["id"] in ids
        assert "default-cpu-warning" in ids

    def test_own_history_scoped_to_owner(self):
        own_rule = self._client.post(
            "/alerts/rules", json=self._rule_payload(), headers={"X-Jarvis-Session": "user-a-session"}
        ).json()["rule"]
        self._client.post(f"/alerts/rules/{own_rule['id']}/test", headers={"X-Jarvis-Session": "user-a-session"})
        self._client.post("/admin/alerts/rules/default-cpu-warning/test", headers=_ADMIN_HDR)

        own_history = self._client.get("/alerts/history", headers={"X-Jarvis-Session": "user-a-session"})
        assert own_history.status_code == 200
        rule_ids = [a["rule_id"] for a in own_history.json()["alerts"]]
        assert own_rule["id"] in rule_ids
        assert "default-cpu-warning" not in rule_ids


# ---------------------------------------------------------------------------
# Pluggable signal source tests (Phase 0 refactor)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_custom_signal_source_registered_and_evaluated():
    audit = _FakeAudit()
    fired: list[dict] = []

    async def fake_broadcast(event):
        fired.append(event)

    class _DummyStore:
        def list_rules(self):
            return []

    engine = AlertEngine(rules_store=_DummyStore(), audit_admin_event=audit, broadcast_fn=fake_broadcast)
    engine.register_source("proxmox.idle_vms", lambda rule: 3)

    rule = {
        "id": "rule-custom",
        "name": "Idle VMs",
        "enabled": True,
        "metric": "proxmox.idle_vms",
        "condition": "above",
        "threshold": 0,
        "duration_seconds": 0,
        "severity": "info",
        "cooldown_seconds": 60,
    }

    await engine._evaluate_rule(rule, time.time())
    assert len(fired) == 1
    assert fired[0]["metric"] == "proxmox.idle_vms"
    assert fired[0]["current_value"] == 3


@pytest.mark.asyncio
async def test_unregistered_metric_source_is_skipped_not_crashed():
    audit = _FakeAudit()
    fired: list[dict] = []

    async def fake_broadcast(event):
        fired.append(event)

    class _DummyStore:
        def list_rules(self):
            return []

    engine = AlertEngine(rules_store=_DummyStore(), audit_admin_event=audit, broadcast_fn=fake_broadcast)
    rule = {
        "id": "rule-unknown",
        "name": "Unknown metric",
        "enabled": True,
        "metric": "not_a_real_metric",
        "condition": "above",
        "threshold": 0,
        "duration_seconds": 0,
        "severity": "info",
        "cooldown_seconds": 60,
    }
    await engine._evaluate_rule(rule, time.time())
    assert fired == []


def test_default_signal_sources_cover_builtin_metrics():
    from jarvis.alert_engine import _default_signal_sources
    sources = _default_signal_sources(ha_store=None)
    assert set(sources.keys()) == {"cpu", "ram", "disk", "ha_health", "ha_entity", "presence_idle_minutes", "calendar_upcoming_minutes"}


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


@pytest.mark.asyncio
async def test_broadcaster_tracks_connected_user_ids():
    broadcaster = AlertBroadcaster()

    class _FakeWS:
        async def send_json(self, data):
            pass

    ws1, ws2 = _FakeWS(), _FakeWS()
    broadcaster.connect(ws1, user_id="user-1")  # type: ignore
    broadcaster.connect(ws2, user_id="user-2")  # type: ignore
    assert broadcaster.connected_user_ids() == {"user-1", "user-2"}

    broadcaster.disconnect(ws1)  # type: ignore
    assert broadcaster.connected_user_ids() == {"user-2"}


@pytest.mark.asyncio
async def test_broadcaster_invokes_configured_push_fanout():
    broadcaster = AlertBroadcaster()
    calls: list[tuple[dict, set]] = []

    async def fake_fanout(payload, connected_user_ids):
        calls.append((payload, connected_user_ids))

    broadcaster.configure_push_fanout(fake_fanout)
    await broadcaster.broadcast({"type": "alert", "message": "hi"})
    assert len(calls) == 1
    assert calls[0][0]["message"] == "hi"


@pytest.mark.asyncio
async def test_broadcaster_push_fanout_failure_does_not_crash_broadcast():
    broadcaster = AlertBroadcaster()

    async def failing_fanout(payload, connected_user_ids):
        raise RuntimeError("boom")

    broadcaster.configure_push_fanout(failing_fanout)
    # Should not raise even though the fanout callback fails.
    await broadcaster.broadcast({"type": "alert", "message": "hi"})


@pytest.mark.asyncio
async def test_broadcast_to_user_only_reaches_target():
    broadcaster = AlertBroadcaster()
    received: list[dict] = []

    class _FakeWS:
        async def send_json(self, data):
            received.append(data)

    ws1 = _FakeWS()
    ws2 = _FakeWS()
    broadcaster.connect(ws1, user_id="user-1")  # type: ignore
    broadcaster.connect(ws2, user_id="user-1")  # type: ignore

    await broadcaster.broadcast_to_user("user-1", {"type": "briefing_seen", "last_briefing_seen_ts": 123})
    assert len(received) == 2
    assert all(payload["type"] == "briefing_seen" for payload in received)


@pytest.mark.asyncio
async def test_broadcast_to_user_ignores_other_users():
    broadcaster = AlertBroadcaster()
    received: list[dict] = []

    class _FakeWS:
        async def send_json(self, data):
            received.append(data)

    ws1 = _FakeWS()
    ws2 = _FakeWS()
    broadcaster.connect(ws1, user_id="user-1")  # type: ignore
    broadcaster.connect(ws2, user_id="user-2")  # type: ignore

    await broadcaster.broadcast_to_user("user-1", {"type": "briefing_seen", "last_briefing_seen_ts": 456})
    assert len(received) == 1


@pytest.mark.asyncio
async def test_broadcast_to_user_does_not_trigger_push_fanout():
    broadcaster = AlertBroadcaster()
    calls: list[tuple[dict, set]] = []

    class _FakeWS:
        async def send_json(self, data):
            pass

    async def fake_fanout(payload, connected_user_ids):
        calls.append((payload, connected_user_ids))

    broadcaster.configure_push_fanout(fake_fanout)
    broadcaster.connect(_FakeWS(), user_id="user-1")  # type: ignore
    await broadcaster.broadcast_to_user("user-1", {"type": "briefing_seen", "last_briefing_seen_ts": 1})
    assert calls == []


@pytest.mark.asyncio
async def test_notify_user_reaches_target_and_triggers_push_fanout():
    broadcaster = AlertBroadcaster()
    received: list[dict] = []
    calls: list[tuple[dict, set]] = []

    class _FakeWS:
        async def send_json(self, data):
            received.append(data)

    async def fake_fanout(payload, connected_user_ids):
        calls.append((payload, connected_user_ids))

    broadcaster.configure_push_fanout(fake_fanout)
    ws1 = _FakeWS()
    ws2 = _FakeWS()
    broadcaster.connect(ws1, user_id="user-1")  # type: ignore
    broadcaster.connect(ws2, user_id="user-2")  # type: ignore

    await broadcaster.notify_user("user-1", {"type": "briefing", "user_id": "user-1", "text": "hi"})
    assert len(received) == 1
    assert len(calls) == 1
    assert calls[0][0]["user_id"] == "user-1"


@pytest.mark.asyncio
async def test_broadcast_to_admins_reaches_only_admin_role_sockets():
    broadcaster = AlertBroadcaster()
    received: list[dict] = []

    class _FakeWS:
        async def send_json(self, data):
            received.append(data)

    admin_ws = _FakeWS()
    user_ws = _FakeWS()
    broadcaster.connect(admin_ws, user_id="usr-admin", role="admin")  # type: ignore
    broadcaster.connect(user_ws, user_id="usr-1", role="standard_user")  # type: ignore

    await broadcaster.broadcast_to_admins({"type": "policy_escalation", "message": "restart storm"})
    assert len(received) == 1


@pytest.mark.asyncio
async def test_broadcast_to_admins_does_not_trigger_push_fanout():
    broadcaster = AlertBroadcaster()
    calls: list[tuple[dict, set]] = []

    class _FakeWS:
        async def send_json(self, data):
            pass

    async def fake_fanout(payload, connected_user_ids):
        calls.append((payload, connected_user_ids))

    broadcaster.configure_push_fanout(fake_fanout)
    broadcaster.connect(_FakeWS(), user_id="usr-admin", role="admin")  # type: ignore
    await broadcaster.broadcast_to_admins({"type": "policy_escalation", "message": "restart storm"})
    assert calls == []


@pytest.mark.asyncio
async def test_broadcast_to_admins_ignores_sockets_without_role():
    broadcaster = AlertBroadcaster()
    received: list[dict] = []

    class _FakeWS:
        async def send_json(self, data):
            received.append(data)

    broadcaster.connect(_FakeWS())  # type: ignore  # no user_id/role, e.g. legacy connect()
    await broadcaster.broadcast_to_admins({"type": "policy_escalation", "message": "hi"})
    assert received == []
