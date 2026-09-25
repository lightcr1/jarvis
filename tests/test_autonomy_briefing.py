"""7.4: the morning briefing includes a short agent-round summary."""
from __future__ import annotations

from types import SimpleNamespace

from jarvis.assistant_domain import try_skill


class _FakeStore:
    def daily_summary(self):
        return {"rounds": 3, "outcomes": {"done": 1, "submitted": 1, "blocked": 1},
                "latest": "Fixed the store", "tasks_by_status": {"done": 1}}


def _kwargs(**overrides):
    kwargs = dict(
        role="admin", token=None, granted_permissions=[],
        emergency_stop_enabled=lambda: False,
        permission_check=lambda *a, **k: True,
        run_cmd=lambda *a, **k: "up 5 minutes",
        disk_usage=lambda path: SimpleNamespace(used=50, total=100),
        format_bytes=lambda n: str(n),
        parse_meminfo=lambda: "",
        parse_ping=lambda *a, **k: {},
        tail_lines=lambda *a, **k: [],
        ensure_service_allowed=lambda *a, **k: True,
        proxmox_vm_status=lambda *a, **k: {},
        proxmox_lxc_status=lambda *a, **k: {},
        proxmox_vm_action=lambda *a, **k: {},
        proxmox_lxc_action=lambda *a, **k: {},
    )
    kwargs.update(overrides)
    return kwargs


def test_briefing_includes_agent_summary():
    result = try_skill("briefing", **_kwargs(autonomy_task_store=_FakeStore()))
    assert result is not None
    assert "coding agent finished 3 round" in result["reply"]
    assert "Latest agent note: Fixed the store" in result["reply"]
    assert result["data"]["agent_summary"]["rounds"] == 3


def test_briefing_without_store_unchanged():
    result = try_skill("briefing", **_kwargs())
    assert result is not None
    assert "coding agent finished" not in result["reply"]
    assert "agent_summary" not in result["data"]


def test_briefing_survives_broken_store():
    class _Broken:
        def daily_summary(self):
            raise RuntimeError("store offline")

    result = try_skill("briefing", **_kwargs(autonomy_task_store=_Broken()))
    assert result is not None
    assert "coding agent finished" not in result["reply"]
