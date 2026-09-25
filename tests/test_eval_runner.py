"""Tests for the eval harness orchestration (4.3, offline)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "agent" / "eval" / "run_eval.py"
spec = importlib.util.spec_from_file_location("jarvis_eval_runner", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_bundled_tasks_are_valid():
    tasks = module.load_tasks(ROOT / "scripts" / "agent" / "eval" / "tasks.json")
    assert len(tasks) >= 6
    assert all({"id", "prompt", "check"} <= set(task) for task in tasks)


def test_load_tasks_rejects_incomplete(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps({"tasks": [{"id": "x", "prompt": "do"}]}), encoding="utf-8")
    try:
        module.load_tasks(path)
    except ValueError as exc:
        assert "check" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("incomplete task must be rejected")


def test_run_tasks_aggregates_results():
    tasks = [{"id": "a", "prompt": "p", "check": "true"},
             {"id": "b", "prompt": "p", "check": "true"}]
    waits = {
        "c-a": {"status": "finished", "duration_s": 10, "iterations": 3,
                "prompt_tokens": 100, "completion_tokens": 20},
        "c-b": {"status": "finished", "duration_s": 20, "iterations": 5,
                "prompt_tokens": 50, "completion_tokens": 10},
    }
    report = module.run_tasks(
        tasks,
        start=lambda task: "c-" + task["id"],
        wait=lambda conv_id: waits[conv_id],
        check=lambda task: task["id"] == "a",
        out=lambda *_: None,
    )
    assert report["tasks"] == 2
    assert report["successes"] == 1
    assert report["success_rate"] == 0.5
    assert report["total_tokens"] == 180
    assert report["total_duration_s"] == 30.0


def test_run_tasks_handles_start_failure():
    tasks = [{"id": "a", "prompt": "p", "check": "true"}]
    report = module.run_tasks(
        tasks,
        start=lambda task: None,
        wait=lambda conv_id: {"status": "finished", "duration_s": 1},
        check=lambda task: True,
        out=lambda *_: None,
    )
    assert report["successes"] == 0
    assert report["results"][0]["status"] == "start-failed"


def test_run_tasks_skips_check_for_unfinished_round():
    tasks = [{"id": "a", "prompt": "p", "check": "true"}]
    checked = []
    report = module.run_tasks(
        tasks,
        start=lambda task: "c1",
        wait=lambda conv_id: {"status": "timeout", "duration_s": 5},
        check=lambda task: checked.append(task) or True,
        out=lambda *_: None,
    )
    assert report["successes"] == 0
    assert checked == []
