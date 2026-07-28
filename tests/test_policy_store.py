from __future__ import annotations

import os
import tempfile

import pytest

from jarvis.policy_store import PolicyStore


_BASE_PAYLOAD = {
    "name": "Restart nginx if down",
    "domain": "system",
    "condition": {"metric": "service_status", "comparator": "equals", "threshold": "failed", "duration_sec": 30},
    "action": {"type": "restart_service", "params": {"service": "nginx"}},
    "enabled": True,
    "dry_run": True,
    "cooldown_sec": 300,
}


@pytest.fixture
def store():
    tmp = tempfile.mktemp(suffix=".json")
    os.environ["JARVIS_POLICY_STORE_PATH"] = tmp
    yield PolicyStore()
    os.environ.pop("JARVIS_POLICY_STORE_PATH", None)
    try:
        os.unlink(tmp)
    except OSError:
        pass


def test_no_seeded_defaults(store):
    assert store.list_policies() == []


def test_create_policy(store):
    policy = store.create_policy(_BASE_PAYLOAD)
    assert policy["id"].startswith("policy-")
    assert policy["name"] == "Restart nginx if down"
    assert policy["condition"]["metric"] == "service_status"
    assert policy["action"]["params"]["service"] == "nginx"
    assert policy["dry_run"] is True
    assert policy["last_fired_at"] is None
    assert any(p["id"] == policy["id"] for p in store.list_policies())


def test_get_policy(store):
    created = store.create_policy(_BASE_PAYLOAD)
    fetched = store.get_policy(created["id"])
    assert fetched is not None
    assert fetched["name"] == created["name"]


def test_get_missing_policy_returns_none(store):
    assert store.get_policy("does-not-exist") is None


def test_update_policy(store):
    created = store.create_policy(_BASE_PAYLOAD)
    updated = store.update_policy(created["id"], {"enabled": False, "dry_run": False})
    assert updated is not None
    assert updated["enabled"] is False
    assert updated["dry_run"] is False
    # Unrelated fields survive the patch
    assert updated["condition"]["metric"] == "service_status"


def test_update_missing_policy_returns_none(store):
    assert store.update_policy("nope", {"enabled": False}) is None


def test_delete_policy(store):
    created = store.create_policy(_BASE_PAYLOAD)
    assert store.delete_policy(created["id"]) is True
    assert store.get_policy(created["id"]) is None


def test_delete_missing_policy_returns_false(store):
    assert store.delete_policy("nope") is False


def test_mark_fired_persists_timestamp(store):
    created = store.create_policy(_BASE_PAYLOAD)
    store.mark_fired(created["id"], 12345.0)
    assert store.get_policy(created["id"])["last_fired_at"] == 12345.0


def test_normalization_defaults_invalid_comparator(store):
    payload = {**_BASE_PAYLOAD, "condition": {**_BASE_PAYLOAD["condition"], "comparator": "bogus"}}
    policy = store.create_policy(payload)
    assert policy["condition"]["comparator"] == "above"


def test_normalization_enforces_minimum_cooldown(store):
    payload = {**_BASE_PAYLOAD, "cooldown_sec": 1}
    policy = store.create_policy(payload)
    assert policy["cooldown_sec"] == 60


def test_normalization_defaults_dry_run_true(store):
    payload = dict(_BASE_PAYLOAD)
    del payload["dry_run"]
    policy = store.create_policy(payload)
    assert policy["dry_run"] is True  # roadmap-mandated safe default


def test_persists_across_instances(store):
    created = store.create_policy(_BASE_PAYLOAD)
    reloaded = PolicyStore()
    assert reloaded.get_policy(created["id"]) is not None
