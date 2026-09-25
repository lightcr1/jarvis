#!/usr/bin/env python3
"""Small reproducible eval harness for the autonomy agent (4.3).

Runs a fixed set of repository tasks through one OpenHands conversation each
and reports success, iterations, tokens and duration. It NEVER starts a pod:
it only talks to an already running OpenHands + controller, so the owner can
compare model/config choices (Qwen3.8 vs coding-max, thinking on/off,
condenser size, 1 vs 2 rounds) with real numbers.

Usage:
    python3 scripts/agent/eval/run_eval.py --config "qwen3.8-thinking" [--limit N] [--out results.json]
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TASKS = Path(__file__).resolve().parent / "tasks.json"

OPENHANDS_BASE = os.getenv("EVAL_OPENHANDS_BASE", "http://10.10.40.100:8001")
CONTROLLER_BASE = os.getenv("EVAL_CONTROLLER_BASE", "https://10.10.40.100:8443")
OPENHANDS_API_KEY = os.getenv("OPENHANDS_API_KEY", "")
EVAL_LLM_MODEL = os.getenv("EVAL_LLM_MODEL", "openai/code")
EVAL_LLM_BASE_URL = os.getenv("EVAL_LLM_BASE_URL", "http://inference-gateway:8080/agent/v1")
EVAL_LLM_API_KEY = os.getenv("EVAL_LLM_API_KEY", "")
EVAL_CONDENSER_MAX_SIZE = int(os.getenv("EVAL_CONDENSER_MAX_SIZE", "60"))
EVAL_CONDENSER_KEEP_FIRST = int(os.getenv("EVAL_CONDENSER_KEEP_FIRST", "2"))
EVAL_MAX_ITERATIONS = int(os.getenv("EVAL_MAX_ITERATIONS", "80"))
EVAL_TIMEOUT_SECONDS = int(os.getenv("EVAL_TIMEOUT_SECONDS", "3600"))
EVAL_WORKSPACE = os.getenv("EVAL_WORKSPACE", "/projects/jarvis")


def load_tasks(path: Path = DEFAULT_TASKS) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    tasks = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("eval tasks file needs a non-empty 'tasks' list")
    result = []
    for task in tasks:
        if not isinstance(task, dict) or not all(
                isinstance(task.get(key), str) and task[key].strip()
                for key in ("id", "prompt", "check")):
            raise ValueError("each eval task needs id, prompt and check")
        result.append({"id": task["id"], "prompt": task["prompt"], "check": task["check"]})
    return result


def _http(method: str, url: str, headers: dict | None = None, body: dict | None = None,
          timeout: float = 20) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=ctx) as response:
            payload = response.read().decode("utf-8", errors="replace")
            return {"status": response.status, "data": json.loads(payload) if payload else {}}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "data": {}}
    except Exception as exc:  # noqa: BLE001
        return {"status": 0, "data": {"error": str(exc)}}


def model_ready() -> bool:
    token = os.getenv("CONTROL_TOKEN", "")
    if not token:
        return True  # ohne Controller-Zugang nicht blockieren
    result = _http("GET", f"{CONTROLLER_BASE}/api/model/ready", headers={"X-Control-Token": token})
    return bool(result.get("data", {}).get("ready"))


def start_conversation(task: dict, config_name: str) -> str | None:
    payload = {
        "workspace": {"working_dir": EVAL_WORKSPACE, "kind": "LocalWorkspace"},
        "worktree": True,
        "tags": {"kind": "eval", "config": config_name},
        "agent": {
            "kind": "Agent",
            "llm": {"model": EVAL_LLM_MODEL, "base_url": EVAL_LLM_BASE_URL,
                    "api_key": EVAL_LLM_API_KEY, "is_subscription": False, "stream": False},
            "condenser": {
                "kind": "LLMSummarizingCondenser",
                "llm": {"model": EVAL_LLM_MODEL, "base_url": EVAL_LLM_BASE_URL,
                        "api_key": EVAL_LLM_API_KEY, "is_subscription": False, "stream": False},
                "max_size": EVAL_CONDENSER_MAX_SIZE,
                "keep_first": EVAL_CONDENSER_KEEP_FIRST,
            },
            "tools": [{"name": "terminal", "params": {}},
                      {"name": "file_editor", "params": {}},
                      {"name": "task_tracker", "params": {}}],
        },
        "max_iterations": EVAL_MAX_ITERATIONS,
        "confirmation_policy": {"kind": "NeverConfirm"},
        "initial_message": {
            "role": "user",
            "content": [{"text": "Eval-Aufgabe (Repo-Jarvis). " + task["prompt"]
                         + " Aendere nur, was fuer die Aufgabe noetig ist, und beende dich danach."}],
            "run": True,
        },
    }
    result = _http("POST", f"{OPENHANDS_BASE}/api/conversations",
                   headers={"X-Session-API-Key": OPENHANDS_API_KEY}, body=payload, timeout=30)
    if result["status"] not in (200, 201):
        return None
    data = result["data"]
    conv_id = data.get("conversation_id") or data.get("id")
    return str(conv_id) if conv_id else None


def wait_for_completion(conv_id: str, timeout_s: int = EVAL_TIMEOUT_SECONDS) -> dict:
    started = time.monotonic()
    terminal = {"finished", "error", "stuck", "terminated"}
    while time.monotonic() - started < timeout_s:
        result = _http("GET", f"{OPENHANDS_BASE}/api/conversations/{conv_id}",
                       headers={"X-Session-API-Key": OPENHANDS_API_KEY})
        if result["status"] == 200 and isinstance(result.get("data"), dict):
            data = result["data"]
            status = str(data.get("execution_status") or data.get("status") or "unknown")
            if status in terminal:
                metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
                return {"status": status, "duration_s": round(time.monotonic() - started, 1),
                        "iterations": int(metrics.get("iterations") or 0),
                        "prompt_tokens": int(metrics.get("prompt_tokens") or 0),
                        "completion_tokens": int(metrics.get("completion_tokens") or 0)}
        time.sleep(10)
    return {"status": "timeout", "duration_s": round(time.monotonic() - started, 1),
            "iterations": 0, "prompt_tokens": 0, "completion_tokens": 0}


def run_check(task: dict) -> bool:
    proc = subprocess.run(task["check"], shell=True, cwd=ROOT, capture_output=True, text=True)
    return proc.returncode == 0


def run_tasks(tasks: list[dict], *, start, wait, check, out=print) -> dict:
    """Pure orchestration; all side effects are injected for testability."""
    results = []
    for task in tasks:
        out(f"==> {task['id']}")
        conv_id = start(task)
        if not conv_id:
            results.append({"id": task["id"], "success": False, "status": "start-failed",
                            "duration_s": 0, "iterations": 0,
                            "prompt_tokens": 0, "completion_tokens": 0})
            continue
        outcome = wait(conv_id)
        passed = False
        if outcome.get("status") == "finished":
            passed = bool(check(task))
        results.append({"id": task["id"], "success": passed, **outcome})
    total = len(results)
    successes = sum(1 for r in results if r["success"])
    tokens = sum(int(r.get("prompt_tokens", 0)) + int(r.get("completion_tokens", 0)) for r in results)
    duration = sum(float(r.get("duration_s", 0)) for r in results)
    return {
        "tasks": total, "successes": successes,
        "success_rate": round(successes / total, 3) if total else 0.0,
        "total_tokens": tokens, "total_duration_s": round(duration, 1),
        "results": results,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Jarvis autonomy eval harness")
    parser.add_argument("--config", default="default", help="Config-Label fuer die Ergebnisse")
    parser.add_argument("--tasks", default=str(DEFAULT_TASKS))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv[1:])

    if not OPENHANDS_API_KEY or not EVAL_LLM_API_KEY:
        print("OPENHANDS_API_KEY und EVAL_LLM_API_KEY muessen gesetzt sein.", file=sys.stderr)
        return 1
    if not model_ready():
        print("Modell ist nicht bereit (Pod nicht gestartet?). Eval startet keinen Pod.", file=sys.stderr)
        return 2

    tasks = load_tasks(Path(args.tasks))
    if args.limit:
        tasks = tasks[: args.limit]
    report = run_tasks(tasks, start=lambda t: start_conversation(t, args.config),
                       wait=wait_for_completion, check=run_check)
    report["config"] = args.config
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
