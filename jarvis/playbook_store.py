from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

_STEP_STATUSES = {"pending", "running", "succeeded", "failed", "skipped", "would_execute"}
_RUN_STATUSES = {"running", "completed", "failed", "awaiting_confirmation", "cancelled"}


class PlaybookStore:
    """Named maintenance playbooks (ordered steps) plus their run/checkpoint history —
    one JSON file, two top-level collections, same self-healing JSON-store pattern as
    `alert_store.py` / `policy_store.py`. Run records persist per-step progress so a
    restart mid-playbook can resume from the first non-terminal step.
    """

    def __init__(self) -> None:
        configured = os.getenv("JARVIS_PLAYBOOK_STORE_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/playbooks.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"playbooks": [], "runs": []}

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            merged = {**self._empty(), **content}
            if not isinstance(merged.get("playbooks"), list):
                merged["playbooks"] = []
            if not isinstance(merged.get("runs"), list):
                merged["runs"] = []
            return merged
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        try:
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    # ---------------------------------------------------------------
    # Playbook definitions
    # ---------------------------------------------------------------
    def list_playbooks(self) -> list[dict]:
        return [dict(p) for p in self.data.get("playbooks", [])]

    def get_playbook(self, playbook_id: str) -> dict | None:
        for pb in self.data.get("playbooks", []):
            if pb.get("id") == playbook_id:
                return dict(pb)
        return None

    def create_playbook(self, payload: dict) -> dict:
        playbook = _normalize_playbook(payload)
        playbook["id"] = f"playbook-{uuid.uuid4().hex[:12]}"
        self.data.setdefault("playbooks", []).append(playbook)
        self._save()
        return dict(playbook)

    def update_playbook(self, playbook_id: str, patch: dict) -> dict | None:
        playbooks = self.data.setdefault("playbooks", [])
        for idx, pb in enumerate(playbooks):
            if pb.get("id") != playbook_id:
                continue
            merged = {**pb, **patch}
            playbooks[idx] = _normalize_playbook(merged)
            playbooks[idx]["id"] = playbook_id
            self._save()
            return dict(playbooks[idx])
        return None

    def delete_playbook(self, playbook_id: str) -> bool:
        playbooks = self.data.setdefault("playbooks", [])
        before = len(playbooks)
        self.data["playbooks"] = [p for p in playbooks if p.get("id") != playbook_id]
        if len(self.data["playbooks"]) < before:
            self._save()
            return True
        return False

    # ---------------------------------------------------------------
    # Runs (checkpointed execution progress)
    # ---------------------------------------------------------------
    def list_runs(self, playbook_id: str | None = None) -> list[dict]:
        runs = self.data.get("runs", [])
        if playbook_id:
            runs = [r for r in runs if r.get("playbook_id") == playbook_id]
        return [dict(r) for r in runs]

    def get_run(self, run_id: str) -> dict | None:
        for run in self.data.get("runs", []):
            if run.get("id") == run_id:
                return dict(run)
        return None

    def start_run(self, playbook: dict, dry_run: bool) -> dict:
        run = {
            "id": f"run-{uuid.uuid4().hex[:12]}",
            "playbook_id": playbook["id"],
            "playbook_name": playbook.get("name", ""),
            "dry_run": dry_run,
            "status": "running",
            "started_at": int(time.time()),
            "finished_at": None,
            "steps": [
                {
                    "step_id": step["step_id"],
                    "status": "pending",
                    "started_at": None,
                    "finished_at": None,
                    "output": None,
                    "error": None,
                }
                for step in playbook.get("steps", [])
            ],
        }
        self.data.setdefault("runs", []).append(run)
        self._save()
        return dict(run)

    def update_run(self, run_id: str, patch: dict) -> dict | None:
        runs = self.data.setdefault("runs", [])
        for idx, run in enumerate(runs):
            if run.get("id") != run_id:
                continue
            runs[idx] = {**run, **patch}
            self._save()
            return dict(runs[idx])
        return None

    def update_step(self, run_id: str, step_id: str, patch: dict) -> dict | None:
        runs = self.data.setdefault("runs", [])
        for run in runs:
            if run.get("id") != run_id:
                continue
            for idx, step in enumerate(run.get("steps", [])):
                if step.get("step_id") != step_id:
                    continue
                run["steps"][idx] = {**step, **patch}
                self._save()
                return dict(run)
        return None


def _normalize_step(raw: object, index: int) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    action = raw.get("action")
    return {
        "step_id": str(raw.get("step_id") or f"step-{index + 1}"),
        "description": str(raw.get("description") or "").strip(),
        "action": {
            "type": str((action or {}).get("type") or "noop"),
            "params": dict((action or {}).get("params") or {}) if isinstance(action, dict) else {},
        },
        "requires_confirmation": bool(raw.get("requires_confirmation", False)),
    }


def _normalize_playbook(payload: dict) -> dict:
    raw_steps = payload.get("steps")
    steps = [_normalize_step(s, i) for i, s in enumerate(raw_steps)] if isinstance(raw_steps, list) else []
    return {
        "id": str(payload.get("id") or ""),
        "name": str(payload.get("name") or "Unnamed playbook").strip() or "Unnamed playbook",
        "description": str(payload.get("description") or "").strip(),
        "dry_run": bool(payload.get("dry_run", True)),
        "steps": steps,
        "created_at": payload.get("created_at") or int(time.time()),
    }
