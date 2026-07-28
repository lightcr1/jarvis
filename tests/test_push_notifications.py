from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jarvis.push_store import PushSubscriptionStore
from jarvis.push_service import build_push_payload, fanout_push, _target_user_ids
from jarvis.api_notifications import build_notifications_router
from jarvis.router_dependencies import LiveRef


SUB_A = {"endpoint": "https://push.example.com/a", "keys": {"p256dh": "p256dh-a", "auth": "auth-a"}}
SUB_B = {"endpoint": "https://push.example.com/b", "keys": {"p256dh": "p256dh-b", "auth": "auth-b"}}
FAKE_VAPID = {"public_key": "pub", "private_key": "priv", "subject": "mailto:test@example.com"}


# ---------------------------------------------------------------------------
# PushSubscriptionStore
# ---------------------------------------------------------------------------

class TestPushSubscriptionStore:
    def setup_method(self):
        self._tmp = tempfile.mktemp(suffix=".json")
        os.environ["JARVIS_PUSH_SUBSCRIPTIONS_PATH"] = self._tmp

    def teardown_method(self):
        os.environ.pop("JARVIS_PUSH_SUBSCRIPTIONS_PATH", None)
        try:
            os.unlink(self._tmp)
        except OSError:
            pass

    def test_add_and_list_for_user(self):
        store = PushSubscriptionStore()
        entry = store.add("user-1", SUB_A)
        assert entry["endpoint"] == SUB_A["endpoint"]
        subs = store.list_for_user("user-1")
        assert len(subs) == 1
        assert subs[0]["keys"]["p256dh"] == "p256dh-a"

    def test_add_deduplicates_by_endpoint(self):
        store = PushSubscriptionStore()
        store.add("user-1", SUB_A)
        store.add("user-1", SUB_A)
        assert len(store.list_for_user("user-1")) == 1

    def test_add_requires_endpoint(self):
        store = PushSubscriptionStore()
        with pytest.raises(ValueError):
            store.add("user-1", {"keys": {"p256dh": "x", "auth": "y"}})

    def test_remove(self):
        store = PushSubscriptionStore()
        store.add("user-1", SUB_A)
        removed = store.remove("user-1", SUB_A["endpoint"])
        assert removed is True
        assert store.list_for_user("user-1") == []

    def test_remove_missing_returns_false(self):
        store = PushSubscriptionStore()
        assert store.remove("user-1", "https://nonexistent") is False

    def test_list_all_excludes_empty_users(self):
        store = PushSubscriptionStore()
        store.add("user-1", SUB_A)
        store.add("user-2", SUB_B)
        store.remove("user-2", SUB_B["endpoint"])
        all_subs = store.list_all()
        assert "user-1" in all_subs
        assert "user-2" not in all_subs

    def test_persists_across_instances(self):
        store1 = PushSubscriptionStore()
        store1.add("user-1", SUB_A)
        store2 = PushSubscriptionStore()
        assert len(store2.list_for_user("user-1")) == 1


# ---------------------------------------------------------------------------
# push_service pure helpers
# ---------------------------------------------------------------------------

def test_build_push_payload_alert():
    event = {"type": "alert", "severity": "critical", "message": "Disk is full."}
    payload = build_push_payload(event)
    assert "Critical" in payload["title"]
    assert payload["body"] == "Disk is full."
    assert payload["tag"] == "alert"


def test_build_push_payload_briefing():
    event = {"type": "briefing", "text": "Good morning."}
    payload = build_push_payload(event)
    assert payload["title"] == "Morning Briefing"
    assert payload["body"] == "Good morning."


def test_build_push_payload_suggestion():
    event = {"type": "suggestion", "message": "VM idle for 5 days."}
    payload = build_push_payload(event)
    assert payload["title"] == "Suggestion"


def test_target_user_ids_scoped_to_payload_user():
    payload = {"user_id": "user-1"}
    assert _target_user_ids(payload, ["user-1", "user-2"]) == {"user-1"}


def test_target_user_ids_broadcast_when_no_user_id():
    payload = {"type": "alert"}
    assert _target_user_ids(payload, ["user-1", "user-2"]) == {"user-1", "user-2"}


# ---------------------------------------------------------------------------
# fanout_push
# ---------------------------------------------------------------------------

class _FakeStore:
    def __init__(self, subs: dict[str, list[dict]]):
        self._subs = subs
        self.removed: list[tuple[str, str]] = []

    def list_all(self):
        return self._subs

    def remove_by_endpoint(self, user_id: str, endpoint: str) -> None:
        self.removed.append((user_id, endpoint))


@pytest.mark.asyncio
async def test_fanout_push_sends_to_unconnected_users_only():
    store = _FakeStore({"user-1": [SUB_A], "user-2": [SUB_B]})
    sent: list[dict] = []

    def fake_send(subscription, notification, vapid_keys):
        sent.append(subscription)
        return True

    await fanout_push(
        {"type": "alert", "message": "hi"},
        connected_user_ids={"user-1"},
        push_store=store,
        vapid_keys=FAKE_VAPID,
        send_fn=fake_send,
    )
    assert len(sent) == 1
    assert sent[0]["endpoint"] == SUB_B["endpoint"]


@pytest.mark.asyncio
async def test_fanout_push_skips_when_no_vapid_key():
    store = _FakeStore({"user-1": [SUB_A]})
    calls = []

    def fake_send(subscription, notification, vapid_keys):
        calls.append(subscription)
        return True

    await fanout_push(
        {"type": "alert"},
        connected_user_ids=set(),
        push_store=store,
        vapid_keys={"public_key": "", "private_key": ""},
        send_fn=fake_send,
    )
    assert calls == []


@pytest.mark.asyncio
async def test_fanout_push_removes_gone_subscriptions():
    store = _FakeStore({"user-1": [SUB_A]})

    def fake_send(subscription, notification, vapid_keys):
        return None  # simulates 404/410

    await fanout_push(
        {"type": "alert"},
        connected_user_ids=set(),
        push_store=store,
        vapid_keys=FAKE_VAPID,
        send_fn=fake_send,
    )
    assert store.removed == [("user-1", SUB_A["endpoint"])]


@pytest.mark.asyncio
async def test_fanout_push_scopes_user_events_to_that_user():
    store = _FakeStore({"user-1": [SUB_A], "user-2": [SUB_B]})
    sent: list[dict] = []

    def fake_send(subscription, notification, vapid_keys):
        sent.append(subscription)
        return True

    await fanout_push(
        {"type": "briefing", "user_id": "user-2", "text": "hi"},
        connected_user_ids=set(),
        push_store=store,
        vapid_keys=FAKE_VAPID,
        send_fn=fake_send,
    )
    assert len(sent) == 1
    assert sent[0]["endpoint"] == SUB_B["endpoint"]


# ---------------------------------------------------------------------------
# api_notifications router
# ---------------------------------------------------------------------------

def _build_app(store: PushSubscriptionStore, audit_events: list):
    def require_identity_session(token):
        if token == "valid-session":
            return {"user": {"id": "usr-1", "role": "standard_user"}}
        from fastapi import HTTPException
        raise HTTPException(401, "login required")

    def audit_admin_event(event, actor_user_id, actor_role, payload=None):
        audit_events.append((event, actor_user_id, actor_role, payload))

    deps = {
        "require_identity_session": require_identity_session,
        "push_subscription_store": LiveRef(lambda: store),
        "vapid_keys": FAKE_VAPID,
        "audit_admin_event": audit_admin_event,
    }
    app = FastAPI()
    app.include_router(build_notifications_router(deps))
    return app


class TestNotificationsRouter:
    def setup_method(self):
        self._tmp = tempfile.mktemp(suffix=".json")
        os.environ["JARVIS_PUSH_SUBSCRIPTIONS_PATH"] = self._tmp
        self.store = PushSubscriptionStore()
        self.audit_events: list = []
        self.app = _build_app(self.store, self.audit_events)
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def teardown_method(self):
        os.environ.pop("JARVIS_PUSH_SUBSCRIPTIONS_PATH", None)
        try:
            os.unlink(self._tmp)
        except OSError:
            pass

    def test_vapid_public_key_no_auth_required(self):
        resp = self.client.get("/notifications/vapid-public-key")
        assert resp.status_code == 200
        assert resp.json()["public_key"] == "pub"

    def test_subscribe_requires_session(self):
        resp = self.client.post("/notifications/subscribe", json=SUB_A)
        assert resp.status_code == 401

    def test_subscribe_stores_and_audits(self):
        resp = self.client.post(
            "/notifications/subscribe",
            json=SUB_A,
            headers={"X-Jarvis-Session": "valid-session"},
        )
        assert resp.status_code == 201
        assert len(self.store.list_for_user("usr-1")) == 1
        assert self.audit_events[0][0] == "notifications.subscribed"

    def test_subscribe_rejects_missing_keys(self):
        resp = self.client.post(
            "/notifications/subscribe",
            json={"endpoint": "https://x"},
            headers={"X-Jarvis-Session": "valid-session"},
        )
        assert resp.status_code == 422

    def test_unsubscribe(self):
        self.client.post("/notifications/subscribe", json=SUB_A, headers={"X-Jarvis-Session": "valid-session"})
        resp = self.client.request(
            "DELETE",
            f"/notifications/subscribe?endpoint={SUB_A['endpoint']}",
            headers={"X-Jarvis-Session": "valid-session"},
        )
        assert resp.status_code == 200
        assert self.store.list_for_user("usr-1") == []
        assert self.audit_events[-1][0] == "notifications.unsubscribed"

    def test_unsubscribe_missing_returns_404(self):
        resp = self.client.request(
            "DELETE",
            "/notifications/subscribe?endpoint=https://nope",
            headers={"X-Jarvis-Session": "valid-session"},
        )
        assert resp.status_code == 404
