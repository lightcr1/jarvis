"""Tests fuer die konservative Verdrahtung von execute_tool mit dem Freigabe-Kern."""
from __future__ import annotations

import pytest

from jarvis.jarvis_engine import RiskLevel
from jarvis.tool_registry import Tool, ToolExecutionContext, execute_tool
import jarvis.tool_registry as tr


@pytest.fixture(autouse=True)
def _allow(monkeypatch):
    monkeypatch.setattr(tr, "permission_decision", lambda *a, **k: {"allowed": True})
    monkeypatch.setattr(tr, "emergency_stop_enabled", lambda: False)


class _Audit:
    def __init__(self):
        self.events = []
    def write(self, name, data=None):
        self.events.append(name)


def _tool(risk, capability=None, name="demo"):
    return Tool(name=name, description="do the thing", parameters={},
                required_permission="p", handler=lambda ctx, args: {"ok": True, "data": {}},
                risk=risk, capability=capability)


def _ctx(role="admin"):
    return ToolExecutionContext(user_id="u", role=role, deps={})


def test_read_tool_runs():
    result = execute_tool(_tool(RiskLevel.READ), _ctx(), {}, audit_log=_Audit(),
                          membership_store=None, permission_store=None)
    assert result.get("ok") is True


def test_unannotated_write_tool_still_requires_confirmation():
    result = execute_tool(_tool(RiskLevel.WRITE), _ctx(), {}, audit_log=_Audit(),
                          membership_store=None, permission_store=None)
    assert result["data"]["route"] == "tool_confirmation_required"


def test_t1_capability_tool_runs_without_confirmation():
    result = execute_tool(_tool(RiskLevel.WRITE, capability="task.create"), _ctx(), {},
                          audit_log=_Audit(), membership_store=None, permission_store=None)
    assert result.get("ok") is True


def test_t2_capability_tool_requires_confirmation_then_runs():
    tool = _tool(RiskLevel.WRITE, capability="service.restart")
    assert execute_tool(tool, _ctx(), {}, audit_log=_Audit(),
                        membership_store=None, permission_store=None)["data"]["route"] == "tool_confirmation_required"
    assert execute_tool(tool, _ctx(), {}, audit_log=_Audit(),
                        membership_store=None, permission_store=None, confirm=True).get("ok") is True


def test_t3_capability_ignores_agent_grant():
    class _Grant:
        def authorize(self, **kwargs):
            return True
        def claim_tool_approval(self, **kwargs):
            raise ValueError("no approved request")

    tool = _tool(RiskLevel.WRITE, capability="email.send", name="create_task")
    result = execute_tool(tool, _ctx(role="service_system"), {}, audit_log=_Audit(),
                          membership_store=None, permission_store=None, agent_grant_store=_Grant())
    assert result["data"]["route"] == "tool_denied"


def test_untrusted_context_escalates_t2_not_t1():
    t2 = _tool(RiskLevel.WRITE, capability="service.restart")
    ctx = ToolExecutionContext(user_id="u", role="admin", deps={"untrusted_context": True})
    result = execute_tool(t2, ctx, {}, audit_log=_Audit(),
                          membership_store=None, permission_store=None)
    assert result["data"]["route"] == "tool_confirmation_required"
    t1 = _tool(RiskLevel.WRITE, capability="task.create")
    assert execute_tool(t1, ctx, {}, audit_log=_Audit(),
                        membership_store=None, permission_store=None).get("ok") is True
