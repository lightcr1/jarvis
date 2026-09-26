"""Regression checks for personal-assistant plan 0.1."""
import pytest

from jarvis.agent_grants import AgentGrantStore
from jarvis.capabilities import authorize_action, load_capabilities
from jarvis.jarvis_engine import RiskLevel
from jarvis.tool_registry_tools import build_pilot_tool_registry


def test_every_mutating_tool_has_a_registered_capability():
    capabilities = load_capabilities()
    for tool in build_pilot_tool_registry().all():
        if tool.risk != RiskLevel.READ:
            assert tool.capability in capabilities, tool.name
            assert capabilities[tool.capability]["tier"] != "T0", tool.name


def test_email_send_is_critical_and_memory_is_not_read_only():
    registry = build_pilot_tool_registry()
    assert registry.get("send_email_draft").capability == "email.send"
    assert authorize_action(registry.get("send_email_draft").capability).tier == "T3"
    assert registry.get("save_memory_note").risk == RiskLevel.WRITE


@pytest.mark.parametrize("capability", ["*", "unclassified.action"])
def test_blanket_standing_grants_are_rejected(tmp_path, capability):
    store = AgentGrantStore(tmp_path / "grants.sqlite3")
    with pytest.raises(ValueError, match="concrete capability"):
        store.create_standing_grant(capability=capability)


@pytest.mark.parametrize("capability", ["*", "unclassified.action"])
def test_legacy_blanket_grants_are_ignored(tmp_path, capability):
    store = AgentGrantStore(tmp_path / "grants.sqlite3")
    grant = store.create_standing_grant(capability="service.restart")
    with store._connect() as db:
        db.execute("UPDATE standing_grants SET capability=? WHERE id=?", (capability, grant["id"]))
    assert store.match_standing_grant("unclassified.action") is None
    assert store.match_standing_grant("service.restart") is None
    legacy = store.get_standing_grant(grant["id"])
    assert authorize_action("unclassified.action", standing_grant=legacy).decision == "ask"
    assert authorize_action("service.restart", standing_grant=legacy).decision == "ask"
