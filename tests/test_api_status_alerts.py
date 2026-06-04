import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from jarvis.api_status import build_status_router
from jarvis.api_alerts import build_alerts_router
from jarvis.runtime_state import JarvisStatusHub


class _FakeHAService:
    def __init__(self, alerts=None, health_alerts=None):
        self._alerts = alerts or []
        self._health_alerts = health_alerts or {}

    def overview(self, *, user_id, role):
        return {"alerts": self._alerts}

    def health_status(self, *, user_id, role):
        return {"alerts": self._health_alerts}


def _make_status_app(hub: JarvisStatusHub) -> FastAPI:
    app = FastAPI()
    app.include_router(build_status_router({"status_hub": hub}))
    return app


def _make_alerts_app(require_session, ha_service) -> FastAPI:
    app = FastAPI()
    app.include_router(build_alerts_router({
        "require_identity_session": require_session,
        "home_assistant_service": ha_service,
    }))
    return app


class StatusWebSocketTests(unittest.TestCase):
    def setUp(self):
        self.hub = JarvisStatusHub()
        self.client = TestClient(_make_status_app(self.hub))

    def test_receives_snapshot_on_connect(self):
        with self.client.websocket_connect("/ws/status") as ws:
            payload = ws.receive_json()
        self.assertIn("state", payload)
        self.assertIn("version", payload)
        self.assertIn("active", payload)

    def test_initial_state_is_idle(self):
        with self.client.websocket_connect("/ws/status") as ws:
            payload = ws.receive_json()
        self.assertEqual("idle", payload["state"])
        self.assertEqual(0, payload["active"])

    def test_receives_updated_snapshot_when_version_changes(self):
        token = self.hub.begin("recording", source="test")
        with self.client.websocket_connect("/ws/status") as ws:
            payload = ws.receive_json()
        self.assertEqual("recording", payload["state"])
        self.hub.end(token)

    def test_version_increments_after_hub_state_change(self):
        with self.client.websocket_connect("/ws/status") as ws:
            before = ws.receive_json()
        self.hub.begin("processing")
        with self.client.websocket_connect("/ws/status") as ws:
            after = ws.receive_json()
        self.assertGreater(int(after["version"]), int(before["version"]))


class AlertsWebSocketTests(unittest.TestCase):
    def _valid_session(self, user_id="usr-1", role="standard_user"):
        def require_session(token):
            if token == "valid-token":
                return {"user": {"id": user_id, "role": role}}
            raise PermissionError("invalid token")
        return require_session

    def test_rejects_missing_session_token(self):
        client = TestClient(_make_alerts_app(self._valid_session(), _FakeHAService()))
        with self.assertRaises((WebSocketDisconnect, Exception)):
            with client.websocket_connect("/ws/alerts") as ws:
                ws.receive_json()

    def test_rejects_invalid_session_token(self):
        client = TestClient(_make_alerts_app(self._valid_session(), _FakeHAService()))
        with self.assertRaises((WebSocketDisconnect, Exception)):
            with client.websocket_connect("/ws/alerts?session=bad-token") as ws:
                ws.receive_json()

    def test_receives_alerts_on_connect(self):
        ha = _FakeHAService(alerts=[
            {"code": "ha_down", "message": "HA is unreachable", "level": "error"},
        ])
        client = TestClient(_make_alerts_app(self._valid_session(), ha))
        with client.websocket_connect("/ws/alerts?session=valid-token") as ws:
            payload = ws.receive_json()
        self.assertEqual("alerts", payload["type"])
        self.assertEqual(1, len(payload["alerts"]))
        self.assertEqual("ha_down", payload["alerts"][0]["code"])

    def test_alert_contains_required_fields(self):
        ha = _FakeHAService(alerts=[
            {"code": "test_alert", "message": "Test message", "level": "warning"},
        ])
        client = TestClient(_make_alerts_app(self._valid_session(), ha))
        with client.websocket_connect("/ws/alerts?session=valid-token") as ws:
            payload = ws.receive_json()
        alert = payload["alerts"][0]
        self.assertIn("id", alert)
        self.assertIn("level", alert)
        self.assertIn("title", alert)
        self.assertIn("message", alert)
        self.assertIn("source", alert)

    def test_unavailable_entity_produces_alert(self):
        ha = _FakeHAService(
            health_alerts={"unavailable_entities": [
                {"entity_id": "light.office", "label": "Office Light"},
            ]}
        )
        client = TestClient(_make_alerts_app(self._valid_session(), ha))
        with client.websocket_connect("/ws/alerts?session=valid-token") as ws:
            payload = ws.receive_json()
        self.assertEqual("alerts", payload["type"])
        ids = [a["id"] for a in payload["alerts"]]
        self.assertIn("entity:light.office", ids)

    def test_no_message_when_no_alerts(self):
        ha = _FakeHAService()
        client = TestClient(_make_alerts_app(self._valid_session(), ha))
        with client.websocket_connect("/ws/alerts?session=valid-token") as ws:
            ws.send_json({"ping": 1})

    def test_permission_error_sends_empty_alerts(self):
        ha = _FakeHAService(alerts=[{"code": "x", "message": "msg", "level": "info"}])

        def require_session(token):
            if token == "valid-token":
                return {"user": {"id": "usr-noperm", "role": "standard_user"}}
            raise PermissionError("no")

        def overview_raises(*, user_id, role):
            raise PermissionError("no ha access")

        ha.overview = overview_raises
        client = TestClient(_make_alerts_app(require_session, ha))
        with client.websocket_connect("/ws/alerts?session=valid-token") as ws:
            ws.send_json({"ping": 1})
