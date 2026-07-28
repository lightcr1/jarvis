from __future__ import annotations

import os

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from jarvis.api_alerts import AlertBroadcaster
from jarvis.api_device_sync import build_device_sync_router
from jarvis.user_preferences_store import UserPreferencesStore


def _require_identity_session(token: str | None):
    if token == "valid-session":
        return {"user": {"id": "usr-1", "role": "standard_user"}}
    raise HTTPException(401, "unauthorized")


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "user_preferences.json"
    os.environ["JARVIS_USER_PREFERENCES_PATH"] = str(path)
    yield UserPreferencesStore()
    os.environ.pop("JARVIS_USER_PREFERENCES_PATH", None)


class _FakeWS:
    def __init__(self):
        self.received: list[dict] = []

    async def send_json(self, data):
        self.received.append(data)


@pytest.fixture
def broadcaster():
    return AlertBroadcaster()


@pytest.fixture
def app_client(store, broadcaster):
    deps = {
        "require_identity_session": _require_identity_session,
        "user_preferences_store": store,
        "alert_broadcaster": broadcaster,
    }
    app = FastAPI()
    app.include_router(build_device_sync_router(deps))
    client = TestClient(app, raise_server_exceptions=False)
    return client


_SESSION_HDR = {"X-Jarvis-Session": "valid-session"}


def test_briefing_seen_requires_session(app_client):
    resp = app_client.post("/sync/briefing-seen")
    assert resp.status_code == 401


def test_briefing_seen_persists_and_broadcasts(app_client, store, broadcaster):
    ws = _FakeWS()
    broadcaster.connect(ws, user_id="usr-1")  # type: ignore

    resp = app_client.post("/sync/briefing-seen", headers=_SESSION_HDR)
    assert resp.status_code == 200

    body = resp.json()
    ts = body["preferences"]["last_briefing_seen_ts"]
    assert ts > 0

    reread = store.get("usr-1")
    assert reread["last_briefing_seen_ts"] == ts

    assert len(ws.received) == 1
    assert ws.received[0] == {"type": "briefing_seen", "last_briefing_seen_ts": ts}


def test_briefing_seen_does_not_reach_other_users(app_client, broadcaster):
    ws = _FakeWS()
    broadcaster.connect(ws, user_id="usr-2")  # type: ignore

    resp = app_client.post("/sync/briefing-seen", headers=_SESSION_HDR)
    assert resp.status_code == 200
    assert ws.received == []
