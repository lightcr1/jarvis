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


def test_chat_assigns_task_to_agent_backlog(tmp_path):
    from jarvis.autonomy_task_store import AutonomyTaskStore
    store = AutonomyTaskStore(tmp_path / "tasks.sqlite3")
    result = try_skill("gib dem Agenten die Aufgabe Tests reparieren",
                       **_kwargs(autonomy_task_store=store))
    assert result is not None
    assert result["data"]["route"] == "agent_task"
    tasks = store.list_tasks()
    assert len(tasks) == 1
    assert tasks[0]["source"] == "owner" and tasks[0]["status"] == "open"
    assert "Tests reparieren" in tasks[0]["title"]


def test_chat_assigns_task_english(tmp_path):
    from jarvis.autonomy_task_store import AutonomyTaskStore
    store = AutonomyTaskStore(tmp_path / "tasks.sqlite3")
    result = try_skill("agent task: fix the failing tests",
                       **_kwargs(autonomy_task_store=store))
    assert result["data"]["task"]["title"] == "fix the failing tests"


def test_chat_task_without_store_falls_through():
    assert try_skill("agent task: fix the failing tests", **_kwargs()) is None


class _TaskSvc:
    def list_tasks(self, **kwargs):
        return {"tasks": [{"title": "Water plants", "status": "open"},
                          {"title": "Done thing", "status": "done"}]}


class _CalSvc:
    def list_events(self, **kwargs):
        return {"events": [{"title": "Standup", "start": 1_700_000_000}]}


class _MailSvc:
    def list_messages(self, **kwargs):
        return {"messages": [{"id": "a"}, {"id": "b"}]}


def test_briefing_includes_tasks_events_and_unread_mail():
    result = try_skill("briefing", **_kwargs(user_id="u", task_service=_TaskSvc(),
                                              calendar_service=_CalSvc(), email_service=_MailSvc()))
    assert "1 open task(s): Water plants" in result["reply"]
    assert "next: Standup at" in result["reply"]
    assert "2 unread email(s)" in result["reply"]
    assert result["data"]["open_tasks"] == 1
    assert result["data"]["events_today"] == 1
    assert result["data"]["unread_emails"] == 2


def test_briefing_survives_broken_task_calendar_email():
    class _Broken:
        def __getattr__(self, name):
            def _boom(*args, **kwargs):
                raise RuntimeError("down")
            return _boom

    result = try_skill("briefing", **_kwargs(user_id="u", task_service=_Broken(),
                                              calendar_service=_Broken(), email_service=_Broken()))
    assert result is not None and result["data"]["route"] == "briefing"
    assert result["data"]["open_tasks"] is None
    assert result["data"]["events_today"] is None
    assert result["data"]["unread_emails"] is None


def test_briefing_omits_services_without_user():
    result = try_skill("briefing", **_kwargs(task_service=_TaskSvc()))
    assert "open_tasks" not in result["data"]
