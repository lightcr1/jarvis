"""Tests for the compact agent-context tooling (context budget + test mapping)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


budget = _load("agent_context_budget", "scripts/agent/context_budget.py")
verify_map = _load("agent_verify_map", "scripts/agent/verify_map.py")


def test_context_budget_flags_oversized_area_card(tmp_path):
    area_dir = tmp_path / "docs" / "agent" / "areas"
    area_dir.mkdir(parents=True)
    (tmp_path / "docs" / "agent" / "CONTEXT.md").write_text("x" * 100, encoding="utf-8")
    (area_dir / "big.md").write_text("x" * (600 * 4 + 10), encoding="utf-8")

    violations = budget.check_budget(tmp_path)
    assert len(violations) == 1
    assert violations[0]["path"] == "docs/agent/areas/big.md"


def test_context_budget_ok_for_small_files(tmp_path):
    area_dir = tmp_path / "docs" / "agent" / "areas"
    area_dir.mkdir(parents=True)
    (tmp_path / "docs" / "agent" / "CONTEXT.md").write_text("kurz", encoding="utf-8")
    (area_dir / "small.md").write_text("kurz", encoding="utf-8")
    assert budget.check_budget(tmp_path) == []


def test_token_estimate_rounds_up():
    assert budget.token_estimate("abcd") == 1
    assert budget.token_estimate("abcde") == 2


def _make_tests(tmp_path, names):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        (tests_dir / name).write_text("", encoding="utf-8")


def test_verify_map_maps_jarvis_modules_to_tests(tmp_path):
    _make_tests(tmp_path, [
        "test_tasks.py", "test_home_assistant_api.py",
        "test_files.py", "test_agent_monitor.py", "test_unrelated.py",
    ])
    result = verify_map.tests_for_paths([
        "jarvis/tasks/store.py",
        "jarvis/api_home_assistant.py",
        "jarvis/agent_monitor.py",
    ], tmp_path)
    assert {p.name for p in result} == {
        "test_tasks.py", "test_home_assistant_api.py", "test_agent_monitor.py",
    }


def test_verify_map_keeps_explicit_test_path(tmp_path):
    _make_tests(tmp_path, ["test_x.py"])
    result = verify_map.tests_for_paths(["tests/test_x.py"], tmp_path)
    assert [p.name for p in result] == ["test_x.py"]


def test_verify_map_skips_frontend_and_unknown(tmp_path):
    _make_tests(tmp_path, ["test_files.py"])
    assert verify_map.tests_for_paths(["frontend/src/x.tsx"], tmp_path) == []
    assert verify_map.tests_for_paths(["README.md"], tmp_path) == []


def test_chat_agent_task_keeps_origin_session(tmp_path):
    """7.2: Chat->Aufgabe merkt sich die Session fuer den Rueckkanal."""
    from jarvis.assistant_domain import try_skill
    from jarvis.autonomy_task_store import AutonomyTaskStore

    store = AutonomyTaskStore(tmp_path / "tasks.sqlite3")
    noop = lambda *a, **k: None
    result = try_skill(
        "gib dem agenten die aufgabe: Pruefe die Backups",
        role="admin", token=None, granted_permissions=[],
        emergency_stop_enabled=lambda: False, permission_check=lambda *a: True,
        run_cmd=noop, disk_usage=noop, format_bytes=noop, parse_meminfo=noop,
        parse_ping=noop, tail_lines=noop, ensure_service_allowed=noop,
        proxmox_vm_status=noop, proxmox_lxc_status=noop,
        proxmox_vm_action=noop, proxmox_lxc_action=noop,
        autonomy_task_store=store, session_id="sess-chat-1",
    )
    assert result and result["data"]["route"] == "agent_task"
    task = result["data"]["task"]
    assert task["origin_session_id"] == "sess-chat-1"
    assert store.get_task(task["id"])["origin_session_id"] == "sess-chat-1"
