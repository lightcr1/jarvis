"""Tests fuer den Freigabe-Kern (Plan Abschnitt 3)."""
from __future__ import annotations

from jarvis.agent_grants import AgentGrantStore
from jarvis.capabilities import (
    authorize_action,
    digest_params,
    load_capabilities,
    standing_grant_valid,
    tier_for,
)

REGISTRY = {
    "status.read": {"tier": "T0"},
    "task.create": {"tier": "T1"},
    "service.restart": {"tier": "T2"},
    "email.send": {"tier": "T3"},
}


def test_tiers_allow_ask_deny():
    assert authorize_action("status.read", registry=REGISTRY).decision == "allow"
    assert authorize_action("task.create", registry=REGISTRY).decision == "allow"       # T1
    t2 = authorize_action("service.restart", registry=REGISTRY)
    assert t2.decision == "ask" and t2.tier == "T2" and t2.requires_single_confirmation
    t3 = authorize_action("email.send", registry=REGISTRY)
    assert t3.decision == "ask" and t3.tier == "T3"


def test_unknown_capability_defaults_to_t2():
    assert tier_for("totally.unknown", REGISTRY) == "T2"
    assert authorize_action("totally.unknown", registry=REGISTRY).decision == "ask"


def test_standing_grant_allows_t2_only():
    grant = {"capability": "service.restart", "target_pattern": "jarvis*", "tier": "T2", "status": "approved"}
    assert authorize_action("service.restart", target="jarvis-web", registry=REGISTRY,
                            standing_grant=grant).decision == "allow"
    assert authorize_action("service.restart", target="other", registry=REGISTRY,
                            standing_grant=grant).decision == "ask"
    # T3 ist nie per stehender Freigabe erlaubt.
    t3_grant = {"capability": "email.send", "target_pattern": "*", "tier": "T2", "status": "approved"}
    assert authorize_action("email.send", registry=REGISTRY,
                            standing_grant=t3_grant).decision == "ask"


def test_untrusted_context_forces_ask_even_with_grant():
    grant = {"capability": "service.restart", "target_pattern": "*", "tier": "T2", "status": "approved"}
    decision = authorize_action("service.restart", registry=REGISTRY,
                                standing_grant=grant, untrusted_context=True)
    assert decision.decision == "ask" and "untrusted" in decision.reason


def test_emergency_stop_denies_everything_but_read():
    assert authorize_action("status.read", registry=REGISTRY, emergency_stop=True).decision == "allow"
    for cap in ("task.create", "service.restart", "email.send"):
        assert authorize_action(cap, registry=REGISTRY, emergency_stop=True).decision == "deny"


def test_digest_params_is_stable_and_order_independent():
    a = digest_params({"b": 2, "a": 1})
    b = digest_params({"a": 1, "b": 2})
    assert a == b and len(a) == 64
    assert digest_params({"a": 1}) != digest_params({"a": 2})


def test_standing_grant_valid_checks_expiry():
    assert standing_grant_valid({"status": "approved"}, now=1000) is True
    assert standing_grant_valid({"status": "revoked"}, now=1000) is False
    assert standing_grant_valid({"status": "approved", "expires_at": 900}, now=1000) is False
    assert standing_grant_valid({"status": "approved", "expires_at": 1100}, now=1000) is True


def test_store_standing_grants_lifecycle(tmp_path):
    store = AgentGrantStore(tmp_path / "grants.sqlite3", clock=lambda: 1000)
    grant = store.create_standing_grant(capability="service.restart", target_pattern="jarvis*",
                                        tier="T2", actor="owner")
    assert grant["status"] == "approved"
    assert store.match_standing_grant("service.restart", "jarvis-web")["id"] == grant["id"]
    assert store.match_standing_grant("service.restart", "other") is None
    assert store.match_standing_grant("vm.exec", "jarvis-web") is None
    store.consume_standing_grant(grant["id"])
    assert store.get_standing_grant(grant["id"])["uses"] == 1
    assert store.revoke_standing_grant(grant["id"], actor="owner")["status"] == "revoked"
    assert store.match_standing_grant("service.restart", "jarvis-web") is None


def test_store_rejects_t3_and_expires(tmp_path):
    clock = {"now": 1000}
    store = AgentGrantStore(tmp_path / "grants.sqlite3", clock=lambda: clock["now"])
    try:
        store.create_standing_grant(capability="email.send", tier="T3", actor="owner")
    except ValueError:
        pass
    else:
        raise AssertionError("T3 standing grant must be rejected")
    store.create_standing_grant(capability="task.create", tier="T1", duration_seconds=60, actor="owner")
    assert store.match_standing_grant("task.create") is not None
    clock["now"] = 2000
    assert store.match_standing_grant("task.create") is None


def test_bundled_capabilities_config_is_valid():
    registry = load_capabilities()
    assert registry, "config/capabilities.json muss ladbar sein"
    assert tier_for("pod.start", registry) == "T3"
    assert tier_for("service.restart", registry) == "T2"
    assert tier_for("status.read", registry) == "T0"
