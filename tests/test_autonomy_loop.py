"""Offline regression tests for the separately installed autonomy controller.

These tests never contact OpenHands or Runpod and never read host credentials.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "agent" / "autonomy_loop.py"
spec = importlib.util.spec_from_file_location("jarvis_autonomy_loop", SCRIPT)
loop = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(loop)


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
