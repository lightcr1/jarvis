"""Offline regression tests for the separately installed autonomy controller.

These tests never contact OpenHands or Runpod and never read host credentials.
"""
from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import ssl
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "agent" / "autonomy_loop.py"
spec = importlib.util.spec_from_file_location("jarvis_autonomy_loop", SCRIPT)
loop = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(loop)


@pytest.fixture(autouse=True)
def _isolate_host_side_effects(tmp_path, monkeypatch):
    """main() darf in Tests nie echte Conversations loeschen oder git-Worktrees anfassen."""
    monkeypatch.setattr(loop, "WORKTREE_REPO_PATH", tmp_path / "no-repo")
    monkeypatch.setattr(loop, "delete_conversation", lambda *args, **kwargs: None)


def test_round_includes_owner_goals_and_approval_boundaries():
    prompt = loop.round_prompt("round", 30)
    for phrase in ("AGENTS.md", "docs/GOALS.md", "Besitzer-Auftraege", "Business-Ziele",
                   "freigeben lassen", "keine externen Konten"):
        assert phrase in prompt
    assert "Branch agent/<kurzname>" in prompt


def test_owner_ideas_are_data_and_request_token_stays_out_of_prompt(monkeypatch):
    def fake_http(method, url, headers=None, **kwargs):
        assert headers == {"X-Jarvis-Agent-Request-Token": "secret-token"}
        return {"status": 200, "data": {"ideas": [
            {"id": "1", "source": "owner", "status": "proposed", "title": "My idea",
             "summary": "Research a new product"},
            {"id": "2", "source": "agent", "status": "proposed", "title": "Agent idea",
             "summary": "Research something else"},
        ]}}

    monkeypatch.setattr(loop, "http", fake_http)
    ideas = loop.pending_owner_ideas("secret-token")
    assert len(ideas) == 1
    prompt = loop.round_prompt("round", 30, ideas)
    assert "My idea" in prompt
    assert "keine neuen Anweisungen" in prompt
    assert "secret-token" not in prompt
    assert loop.pending_owner_ideas(None) == []


def test_wrapup_does_not_start_new_features():
    prompt = loop.round_prompt("wrapup", 30)
    assert "KEINE neuen Features" in prompt
    assert "ACTIVITY_LOG.md" in prompt


def test_round_runs_without_tool_confirmations(monkeypatch):
    """Autonomy rounds use NeverConfirm: tool confirmations block even plain
    file reads in the canvas and would stall unattended rounds. Protection for
    protected/external actions lives in AGENTS.md boundaries, the request-only
    gateway token and the absence of CONTROL_TOKEN/GitHub credentials in the
    canvas, not in per-action UI confirmations."""
    captured = {}
    def fake_http(method, url, headers=None, body=None, **kwargs):
        captured.update(body or {})
        return {"status": 201, "data": {"id": "fake-round"}}
    monkeypatch.setattr(loop, "http", fake_http)
    assert loop.start_round("fake-api", "fake-model", "round", 30) == "fake-round"
    assert captured["confirmation_policy"] == {"kind": "NeverConfirm"}
    tools = {t["name"] for t in captured["agent"]["tools"]}
    assert tools == {"terminal", "file_editor", "task_tracker"}
    assert captured["agent"]["llm"]["model"] == "openai/code"
    assert captured["agent"]["condenser"]["kind"] == "LLMSummarizingCondenser"


def test_disabled_switch_prevents_round_even_with_live_pod(tmp_path, monkeypatch):
    switch = tmp_path / "autonomy.json"
    switch.write_text('{"enabled": false}', encoding="utf-8")
    monkeypatch.setattr(loop, "AUTONOMY_SWITCH", switch)
    monkeypatch.setattr(loop, "ENV_RUNPOD", tmp_path / "empty.env")
    monkeypatch.setattr(loop, "ENV_JARVIS", tmp_path / "empty2.env")
    monkeypatch.setattr(loop, "_parse_env", lambda _: {
        "CONTROL_TOKEN": "fake", "OPENHANDS_API_KEY": "fake", "AGENT_GATEWAY_TOKEN": "fake",
    })
    monkeypatch.setattr(loop, "check_pod", lambda _: (_ for _ in ()).throw(
        AssertionError("pod must not be touched when autonomy is off")))
    monkeypatch.setattr(loop, "start_round", lambda *_: (_ for _ in ()).throw(
        AssertionError("round must not be started")))
    assert loop.main() == 0


def test_owner_activity_blocks_new_round(tmp_path, monkeypatch):
    monkeypatch.setattr(loop, "AUTONOMY_SWITCH", tmp_path / "missing.json")
    monkeypatch.setattr(loop, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(loop, "_parse_env", lambda _: {
        "CONTROL_TOKEN": "fake", "OPENHANDS_API_KEY": "fake", "AGENT_GATEWAY_TOKEN": "fake",
    })
    monkeypatch.setattr(loop, "check_pod", lambda _: (True, "RUNNING", "fake-pod"))
    monkeypatch.setattr(loop, "get_activity", lambda _: {"user_activity_age_s": 0})
    monkeypatch.setattr(loop, "openhands_sessions", lambda _: [])
    monkeypatch.setattr(loop, "start_round", lambda *_: (_ for _ in ()).throw(
        AssertionError("owner is active; background round must wait")))
    assert loop.main() == 0


def test_parallel_focus_switches_between_rounds(monkeypatch):
    """Zweite parallele Runde bekommt den komplementaeren Fokus (ideas),
    wenn bereits eine engineering-Runde laeuft."""
    # Runde 1: engineering (keine laufende Runde -> engineering)
    active_a = {"sess-a": {"kind": "round", "paused": False, "focus": "engineering"}}
    focus_b = "ideas" if "engineering" in {m.get("focus", "engineering") for m in active_a.values()} else "engineering"
    assert focus_b == "ideas"
    # Umgekehrt: laeuft ideas, startet engineering
    active_b = {"sess-b": {"kind": "round", "paused": False, "focus": "ideas"}}
    focus_c = "ideas" if "engineering" in {m.get("focus", "engineering") for m in active_b.values()} else "engineering"
    assert focus_c == "engineering"


def test_round_prompt_contains_focus(monkeypatch):
    prompt_eng = loop.round_prompt("round", 30)
    prompt_ideas = loop.round_prompt("round", 30, focus="ideas")
    assert "Engineering" in prompt_eng
    assert "Ideen" in prompt_ideas
    assert "AGENTS.md" in prompt_eng and "AGENTS.md" in prompt_ideas


def test_check_pod_model_ready_fallback_returns_no_pod_id(monkeypatch):
    """B3: 502 am Status-Endpunkt + ready-Modell -> laufender Pod, pod_id None."""
    def fake_http(method, url, headers=None, **kwargs):
        if url.endswith("/api/status"):
            return {"status": 502, "data": {"error": "bad gateway"}}
        if url.endswith("/api/model/ready"):
            return {"status": 200, "data": {"ready": True}}
        raise AssertionError(f"unerwarteter Aufruf: {url}")

    monkeypatch.setattr(loop, "http", fake_http)
    assert loop.check_pod("token") == (True, "RUNNING(model-ready)", None)


def _write_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state), encoding="utf-8")


def test_model_ready_fallback_keeps_active_sessions_and_heartbeats(tmp_path, monkeypatch):
    """B3: model-ready-Fallback (pod_id=None) darf laufende eigene Runden nicht
    verwerfen; die Runde muss weiter Heartbeats senden."""
    monkeypatch.setattr(loop, "AUTONOMY_SWITCH", tmp_path / "missing.json")
    monkeypatch.setattr(loop, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(loop, "_parse_env", lambda _: {
        "CONTROL_TOKEN": "fake", "OPENHANDS_API_KEY": "fake", "AGENT_GATEWAY_TOKEN": "fake",
    })
    monkeypatch.setattr(loop, "check_pod", lambda _: (True, "RUNNING(model-ready)", None))
    monkeypatch.setattr(loop, "get_activity", lambda _: {"user_activity_age_s": 9999})
    monkeypatch.setattr(loop, "openhands_sessions", lambda _: [{
        "id": "sess-a", "execution_status": "running",
        "tags": {"kind": "autonomy", "focus": "engineering"},
    }])
    monkeypatch.setattr(loop, "MAX_PARALLEL_ROUNDS", 1)
    monkeypatch.setattr(loop, "start_round", lambda *_: (_ for _ in ()).throw(
        AssertionError("laufende Runde belegt den Slot; kein neuer Start")))
    beats: list[int] = []
    monkeypatch.setattr(loop, "heartbeat", lambda _: beats.append(1))
    _write_state(loop.STATE_PATH, {
        "pod_id": "pod-1",
        "active_sessions": {"sess-a": {"kind": "round", "paused": False, "focus": "engineering"}},
        "wrapup_done": False,
    })

    assert loop.main() == 0
    assert beats, "fuer die laufende eigene Runde muss ein Heartbeat gesendet werden"
    state = json.loads(loop.STATE_PATH.read_text(encoding="utf-8"))
    assert "sess-a" in state["active_sessions"]
    assert state["pod_id"] == "pod-1"


def test_tagged_unknown_session_is_adopted_not_foreign(tmp_path, monkeypatch):
    """B3: eine getaggte Autonomie-Session, die dem State unbekannt ist, wird
    adoptiert statt als fremde Aktivitaet gewertet."""
    monkeypatch.setattr(loop, "AUTONOMY_SWITCH", tmp_path / "missing.json")
    monkeypatch.setattr(loop, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(loop, "_parse_env", lambda _: {
        "CONTROL_TOKEN": "fake", "OPENHANDS_API_KEY": "fake", "AGENT_GATEWAY_TOKEN": "fake",
    })
    monkeypatch.setattr(loop, "check_pod", lambda _: (True, "RUNNING", "pod-1"))
    monkeypatch.setattr(loop, "get_activity", lambda _: {"user_activity_age_s": 9999})
    monkeypatch.setattr(loop, "openhands_sessions", lambda _: [{
        "id": "sess-x", "execution_status": "running",
        "tags": ["kind:autonomy", "focus:ideas"],
    }])
    monkeypatch.setattr(loop, "MAX_PARALLEL_ROUNDS", 1)
    monkeypatch.setattr(loop, "heartbeat", lambda _: None)
    monkeypatch.setattr(loop, "start_round", lambda *_: (_ for _ in ()).throw(
        AssertionError("adoptierte Runde belegt den Slot; kein neuer Start")))
    _write_state(loop.STATE_PATH, {"pod_id": "pod-1", "active_sessions": {}, "wrapup_done": False})

    assert loop.main() == 0
    state = json.loads(loop.STATE_PATH.read_text(encoding="utf-8"))
    assert state["active_sessions"]["sess-x"]["focus"] == "ideas"


def test_foreign_session_still_blocks_new_round(tmp_path, monkeypatch):
    """Nicht getaggte, laufende Sessions bleiben fremd und blockieren neue Runden."""
    monkeypatch.setattr(loop, "AUTONOMY_SWITCH", tmp_path / "missing.json")
    monkeypatch.setattr(loop, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(loop, "_parse_env", lambda _: {
        "CONTROL_TOKEN": "fake", "OPENHANDS_API_KEY": "fake", "AGENT_GATEWAY_TOKEN": "fake",
    })
    monkeypatch.setattr(loop, "check_pod", lambda _: (True, "RUNNING", "pod-1"))
    monkeypatch.setattr(loop, "get_activity", lambda _: {"user_activity_age_s": 9999})
    monkeypatch.setattr(loop, "openhands_sessions", lambda _: [
        {"id": "owner-conv", "execution_status": "running", "tags": {}},
    ])
    monkeypatch.setattr(loop, "start_round", lambda *_: (_ for _ in ()).throw(
        AssertionError("fremde Session darf keinen neuen Start zulassen")))
    _write_state(loop.STATE_PATH, {"pod_id": "pod-1", "active_sessions": {}, "wrapup_done": False})

    assert loop.main() == 0
    state = json.loads(loop.STATE_PATH.read_text(encoding="utf-8"))
    assert "owner-conv" not in state["active_sessions"]



# ---------------------------------------------------------------------------
# 1.2 Wrapup + 1.3 Aufraeumen
# ---------------------------------------------------------------------------


def test_wrapup_stops_pod_once_when_wrapup_ends_first(tmp_path, monkeypatch):
    monkeypatch.setattr(loop, "STATE_PATH", tmp_path / "state.json")
    stops: list[int] = []
    monkeypatch.setattr(loop, "stop_pod", lambda _: stops.append(1) or True)
    state = {
        "active_sessions": {"w": {"kind": "wrapup"}, "r": {"kind": "round"}},
        "wrapup_done": True,
    }
    loop.close_round(state, "api", "tok", "w", "wrapup")
    assert stops == [], "Normalrunde laeuft noch, kein Pod-Stop"
    loop.close_round(state, "api", "tok", "r", "round")
    assert stops == [1], "genau ein Pod-Stop nach der letzten Runde"


def test_wrapup_stops_pod_once_when_normal_round_ends_first(tmp_path, monkeypatch):
    monkeypatch.setattr(loop, "STATE_PATH", tmp_path / "state.json")
    stops: list[int] = []
    monkeypatch.setattr(loop, "stop_pod", lambda _: stops.append(1) or True)
    state = {
        "active_sessions": {"w": {"kind": "wrapup"}, "r": {"kind": "round"}},
        "wrapup_done": True,
    }
    loop.close_round(state, "api", "tok", "r", "round")
    assert stops == [], "Wrapup-Runde laeuft noch, kein Pod-Stop"
    loop.close_round(state, "api", "tok", "w", "wrapup")
    assert stops == [1], "genau ein Pod-Stop nach der letzten Runde"


def test_send_message_uses_events_endpoint(monkeypatch):
    captured = {}

    def fake_http(method, url, headers=None, body=None, **kwargs):
        captured.update(method=method, url=url, headers=headers, body=body)
        return {"status": 200, "data": {"success": True}}

    monkeypatch.setattr(loop, "http", fake_http)
    assert loop.send_message("api", "conv-1", "hallo") is True
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/api/conversations/conv-1/events")
    assert captured["headers"] == {"X-Session-API-Key": "api"}
    assert captured["body"]["content"][0] == {"type": "text", "text": "hallo"}
    assert captured["body"]["run"] is False


def test_notify_running_rounds_wrapup_only_active(monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(loop, "send_message",
                        lambda api, cid, text, **kw: sent.append(cid) or True)
    active = {"a": {"kind": "round"}, "b": {"kind": "wrapup"}, "c": {"kind": "round"}}
    sessions_by_id = {
        "a": {"execution_status": "running"},
        "b": {"execution_status": "running"},
        "c": {"execution_status": "finished"},
    }
    loop.notify_running_rounds_wrapup("api", active, sessions_by_id)
    assert sent == ["a"]


def test_cleanup_finished_conversations_keeps_newest_and_skips_active(monkeypatch):
    deleted: list[str] = []
    monkeypatch.setattr(loop, "delete_conversation",
                        lambda api, cid: deleted.append(cid))
    sessions = [
        {"id": "old", "execution_status": "finished", "created_at": "2024-01-01",
         "tags": {"kind": "autonomy"}},
        {"id": "new", "execution_status": "finished", "created_at": "2024-03-01",
         "tags": {"kind": "autonomy"}},
        {"id": "running", "execution_status": "running", "created_at": "2024-01-01",
         "tags": {"kind": "autonomy"}},
        {"id": "foreign", "execution_status": "finished", "created_at": "2024-01-01",
         "tags": {}},
    ]
    active = {"running": {"kind": "round"}}
    removed = loop.cleanup_finished_conversations("api", sessions, active, keep=1)
    assert removed == 1
    assert deleted == ["old"]


class _FakeRun:
    def __init__(self, stdout: str = "", returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode


def test_cleanup_orphan_worktrees_removes_only_old_inactive(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    wt_root = tmp_path / "worktrees"
    old = wt_root / "11111111-1111-1111-1111-111111111111"
    active = wt_root / "22222222-2222-2222-2222-222222222222"
    recent = wt_root / "33333333-3333-3333-3333-333333333333"
    for path in (old, active, recent):
        path.mkdir(parents=True)
    now = 1_000_000.0
    os.utime(old, (now - 7200, now - 7200))
    os.utime(active, (now - 7200, now - 7200))
    os.utime(recent, (now - 100, now - 100))

    calls: list[list[str]] = []

    def runner(cmd, **kwargs):
        calls.append(cmd)
        if cmd[3:5] == ["worktree", "list"]:
            stdout = "\n\n".join(
                f"worktree {p}" for p in (repo, old, active, recent)) + "\n"
            return _FakeRun(stdout=stdout)
        return _FakeRun()

    removed = loop.cleanup_orphan_worktrees(
        repo, {"22222222-2222-2222-2222-222222222222"}, max_age_s=3600,
        runner=runner, now=now)

    assert removed == 1
    remove_calls = [c for c in calls if c[3:5] == ["worktree", "remove"]]
    assert len(remove_calls) == 1
    assert str(old) in remove_calls[0]
    assert [c[3:5] for c in calls].count(["worktree", "prune"]) == 1


def test_cleanup_orphan_worktrees_skips_when_repo_missing(tmp_path):
    def runner(cmd, **kwargs):  # pragma: no cover - darf nicht aufgerufen werden
        raise AssertionError("ohne Repo darf git nicht aufgerufen werden")

    assert loop.cleanup_orphan_worktrees(tmp_path / "missing", set(), runner=runner) == 0


# ---------------------------------------------------------------------------
# 1.5 Konfiguration + 1.6 Versions-Drift
# ---------------------------------------------------------------------------


def test_load_config_defaults_file_and_environment(tmp_path):
    cfg_file = tmp_path / "autonomy-loop.env"
    cfg_file.write_text(
        "# Kommentar\nMAX_ITERATIONS=55\nCONTROLLER_BASE=https://file:1\n",
        encoding="utf-8",
    )
    cfg = loop.load_config(cfg_file, environ={"COOLDOWN_SECONDS": "7"})
    assert cfg["MAX_ITERATIONS"] == "55"
    assert cfg["CONTROLLER_BASE"] == "https://file:1"
    assert cfg["COOLDOWN_SECONDS"] == "7"  # Umgebung schlaegt Datei/Default
    assert cfg["MAX_PARALLEL_ROUNDS"] == loop.DEFAULT_CONFIG["MAX_PARALLEL_ROUNDS"]


def test_load_config_ignores_empty_environment_values(tmp_path):
    cfg = loop.load_config(tmp_path / "missing.env", environ={"CONTROLLER_CA_FILE": ""})
    assert cfg["CONTROLLER_CA_FILE"] == loop.DEFAULT_CONFIG["CONTROLLER_CA_FILE"]


def test_build_ssl_context_fallback_is_insecure():
    ctx = loop.build_ssl_context("")
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False


def test_build_ssl_context_with_ca_verifies():
    ca = "/etc/ssl/certs/ca-certificates.crt"
    if not os.path.exists(ca):
        pytest.skip("System-CA-Bundle nicht vorhanden")
    ctx = loop.build_ssl_context(ca)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_source_sha256_matches_hashlib(tmp_path):
    target = tmp_path / "loop.py"
    target.write_bytes(b"abc")
    assert loop.source_sha256(target) == hashlib.sha256(b"abc").hexdigest()


def test_start_round_uses_configured_condenser(monkeypatch):
    captured = {}

    def fake_http(method, url, headers=None, body=None, **kwargs):
        captured.update(body or {})
        return {"status": 201, "data": {"id": "fake"}}

    monkeypatch.setattr(loop, "http", fake_http)
    monkeypatch.setattr(loop, "CONDENSER_MAX_SIZE", 42)
    monkeypatch.setattr(loop, "CONDENSER_KEEP_FIRST", 3)
    assert loop.start_round("api", "model", "round", 30) == "fake"
    assert captured["agent"]["condenser"]["max_size"] == 42
    assert captured["agent"]["condenser"]["keep_first"] == 3


# ---------------------------------------------------------------------------
# 2.1 / 2.3 kompakter Kontext + stabile Prompt-Reihenfolge
# ---------------------------------------------------------------------------


def test_round_prompt_static_prefix_is_stable_across_focus():
    engineering = loop.round_prompt("round", 30, focus="engineering")
    ideas = loop.round_prompt("round", 30, focus="ideas")
    # Der statische Teil steht zuerst und ist fuer alle Foki identisch
    # (Prefix-Cache), der Fokus kommt erst danach.
    assert engineering[:600] == ideas[:600]
    assert "FOKUS DIESER RUNDE" not in engineering[:600]
    assert "Engineering" not in engineering[:600]
    assert "FOKUS DIESER RUNDE" in engineering
    assert "FOKUS DIESER RUNDE" in ideas


def test_round_prompt_references_compact_context():
    prompt = loop.round_prompt("round", 30)
    assert "docs/agent/CONTEXT.md" in prompt
    assert "docs/agent/areas/" in prompt
    assert "NIEMALS komplett" in prompt


# ---------------------------------------------------------------------------
# 2.2 Condenser- und Iterationsbudget
# ---------------------------------------------------------------------------


def test_iterations_for_size():
    assert loop.iterations_for_size("small") == loop.MAX_ITERATIONS_SMALL
    assert loop.iterations_for_size("medium") == loop.MAX_ITERATIONS_MEDIUM
    assert loop.iterations_for_size(None) == loop.MAX_ITERATIONS
    assert loop.iterations_for_size("unknown") == loop.MAX_ITERATIONS
    assert loop.MAX_ITERATIONS_SMALL < loop.MAX_ITERATIONS_MEDIUM


def test_start_round_accepts_explicit_iteration_budget(monkeypatch):
    captured = {}

    def fake_http(method, url, headers=None, body=None, **kwargs):
        captured.update(body or {})
        return {"status": 201, "data": {"id": "fake"}}

    monkeypatch.setattr(loop, "http", fake_http)
    assert loop.start_round("api", "model", "round", 30, max_iterations=40) == "fake"
    assert captured["max_iterations"] == 40
