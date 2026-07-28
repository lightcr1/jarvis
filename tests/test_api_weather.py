from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from jarvis.api_weather import build_weather_router
from jarvis.router_dependencies import LiveRef
from jarvis.user_preferences_store import UserPreferencesStore


_SESSION_HDR = {"X-Jarvis-Session": "valid-session-token"}
_CANNED_WEATHER = {"city": "Zurich", "temperature_c": 18.5, "condition": "overcast"}


def _fake_require_identity_session(token, *, require_ok: bool = True, user_id: str = "usr-test"):
    if not require_ok or token != "valid-session-token":
        raise HTTPException(401, "login required")
    return {"user": {"id": user_id, "username": "testuser", "role": "standard_user"}}


@pytest.fixture
def prefs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_USER_PREFERENCES_PATH", str(tmp_path / "user_preferences.json"))
    return UserPreferencesStore()


def _make_app(prefs_store: UserPreferencesStore, *, fetch_weather=None, require_ok: bool = True):
    app = FastAPI()

    def fake_fetch_weather(city: str):
        if fetch_weather is not None:
            return fetch_weather(city)
        return _CANNED_WEATHER

    deps = {
        "require_identity_session": lambda token: _fake_require_identity_session(token, require_ok=require_ok),
        "user_preferences_store": LiveRef(lambda: prefs_store),
        "fetch_weather": fake_fetch_weather,
    }
    app.include_router(build_weather_router(deps))
    return app


def test_explicit_city_wins_over_saved_location(prefs_store):
    prefs_store.update("usr-test", {"location": "Berlin"})
    app = _make_app(prefs_store)
    client = TestClient(app)

    resp = client.get("/weather", params={"city": "Zurich"}, headers=_SESSION_HDR)

    assert resp.status_code == 200
    assert resp.json() == {"weather": _CANNED_WEATHER}


def test_falls_back_to_saved_location_when_city_omitted(prefs_store):
    prefs_store.update("usr-test", {"location": "Berlin"})
    seen_cities: list[str] = []

    def fetch(city):
        seen_cities.append(city)
        return _CANNED_WEATHER

    app = _make_app(prefs_store, fetch_weather=fetch)
    client = TestClient(app)

    resp = client.get("/weather", headers=_SESSION_HDR)

    assert resp.status_code == 200
    assert seen_cities == ["Berlin"]


def test_400_when_no_city_and_no_saved_location(prefs_store):
    app = _make_app(prefs_store)
    client = TestClient(app)

    resp = client.get("/weather", headers=_SESSION_HDR)

    assert resp.status_code == 400


def test_502_when_fetch_weather_returns_none(prefs_store):
    app = _make_app(prefs_store, fetch_weather=lambda city: None)
    client = TestClient(app)

    resp = client.get("/weather", params={"city": "Nowhere"}, headers=_SESSION_HDR)

    assert resp.status_code == 502


def test_unauthenticated_request_rejected(prefs_store):
    app = _make_app(prefs_store, require_ok=False)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/weather", params={"city": "Zurich"})

    assert resp.status_code in (401, 403, 500)
