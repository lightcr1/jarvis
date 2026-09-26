"""Tests fuer den erweiterten Zustands-Backup (Review-Punkt 3)."""
from __future__ import annotations

import base64

import pytest

from jarvis.agent_grants import AgentGrantStore
from jarvis.state_backup import collect_state, restore_state


def _env(tmp_path, monkeypatch):
    db = tmp_path / "agent_grants.sqlite3"; db.write_bytes(b"SQLITEDB")
    cfg = tmp_path / "zones.json"; cfg.write_text('{"z": 1}', encoding="utf-8")
    audit = tmp_path / "audit.log"; audit.write_text("line1\n", encoding="utf-8")
    monkeypatch.setenv("JARVIS_AGENT_GRANTS_PATH", str(db))
    monkeypatch.setenv("JARVIS_ZONES_FILE", str(cfg))
    monkeypatch.setenv("JARVIS_EXECUTOR_AUDIT_LOG", str(audit))
    monkeypatch.delenv("JARVIS_AUTONOMY_TASKS_PATH", raising=False)
    monkeypatch.delenv("JARVIS_PATCH_REVIEW_PATH", raising=False)
    monkeypatch.delenv("JARVIS_CAPABILITIES_FILE", raising=False)
    return db, cfg, audit


def test_collect_includes_db_config_and_audit(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    state = collect_state()
    assert state["databases"]["agent_grants"]["data"] == base64.b64encode(b"SQLITEDB").decode()
    assert state["configs"]["zones"]["text"] == '{"z": 1}'
    assert state["executor_audit"]["text"] == "line1\n"


def test_restore_roundtrip_and_ignores_payload_path(tmp_path, monkeypatch):
    db, cfg, audit = _env(tmp_path, monkeypatch)
    state = collect_state()
    state["databases"]["agent_grants"]["path"] = "/tmp/evil"   # darf ignoriert werden
    db.write_bytes(b"CHANGED"); cfg.write_text("{}", encoding="utf-8"); audit.write_text("", encoding="utf-8")
    restore_state(state)
    assert db.read_bytes() == b"SQLITEDB"
    assert cfg.read_text(encoding="utf-8") == '{"z": 1}'
    assert audit.read_text(encoding="utf-8") == "line1\n"


def test_wildcard_standing_grant_is_rejected_and_ignored(tmp_path):
    store = AgentGrantStore(tmp_path / "g.sqlite3", clock=lambda: 1000)
    with pytest.raises(ValueError):
        store.create_standing_grant(capability="*", target_pattern="*", tier="T2")
    # Direkt eingefuegte Wildcard-Freigabe wird beim Matching ignoriert.
    with store._connect() as db:
        db.execute("INSERT INTO standing_grants (id,capability,target_pattern,tier,status,created_at,decided_by,uses)"
                   " VALUES ('x','*','*','T2','approved',?, 'owner', 0)", (1000,))
    assert store.match_standing_grant("service.restart", "nginx") is None
