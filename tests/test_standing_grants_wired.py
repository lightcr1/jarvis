"""Stehende Freigaben wirken in execute_tool, Executor und Self-Deploy (Review #5)."""
from __future__ import annotations

import pytest

from jarvis.agent_grants import AgentGrantStore
from jarvis.executor import Executor, SandboxError
from jarvis.jarvis_engine import RiskLevel
from jarvis.self_deploy import DeployError, SelfDeployer
from jarvis.tool_registry import Tool, ToolExecutionContext, execute_tool
from jarvis.zones import load_zones


class _PS:
    def list_role_permissions(self): return {"admin": ["actions.write.execute"]}
    def list_user_permissions(self): return {}
    def list_group_permissions(self): return {}
class _MS:
    def list_user_groups(self, uid): return []
class _Audit:
    def write(self, *a, **k): pass


def _grant_store(tmp_path):
    return AgentGrantStore(tmp_path / "grants.sqlite3", clock=lambda: 1000)


def _t2_tool():
    return Tool(name="restart_service", description="Restart a service.", parameters={},
                required_permission="actions.write.execute", risk=RiskLevel.WRITE,
                handler=lambda ctx, args: {"reply": "restarted", "data": {"route": "ok"}},
                capability="service.restart")


def test_execute_tool_uses_standing_grant_and_counts(tmp_path):
    store = _grant_store(tmp_path)
    ctx = ToolExecutionContext(user_id="u", role="admin", deps={})
    # ohne Freigabe -> Rueckfrage
    blocked = execute_tool(_t2_tool(), ctx, {"name": "nginx"}, audit_log=_Audit(),
                           membership_store=_MS(), permission_store=_PS(), agent_grant_store=store)
    assert blocked["data"]["route"] == "tool_confirmation_required"
    # Freigabe anlegen -> laeuft, Zaehler hoch
    grant = store.create_standing_grant(capability="service.restart", target_pattern="*", tier="T2")
    result = execute_tool(_t2_tool(), ctx, {"name": "nginx"}, audit_log=_Audit(),
                          membership_store=_MS(), permission_store=_PS(), agent_grant_store=store)
    assert result["data"]["route"] == "ok"
    assert store.get_standing_grant(grant["id"])["uses"] == 1


def test_executor_managed_uses_standing_grant(tmp_path):
    store = _grant_store(tmp_path)
    store.create_standing_grant(capability="service.restart", target_pattern="*", tier="T2")
    executor = Executor(object(), zones=load_zones(), grant_store=store)
    decision = executor.authorize_managed("some-workload", capability="service.restart")
    assert decision.decision == "allow" and decision.reason.startswith("covered")


def test_self_deploy_uses_standing_grant(tmp_path):
    store = _grant_store(tmp_path)
    grant = store.create_standing_grant(capability="jarvis.deploy", target_pattern="*", tier="T2")
    calls = []
    deployer = SelfDeployer(lambda cmd: (calls.append(cmd), (0, ""))[1],
                            zones=load_zones(), health_check=lambda: True,
                            deploy_command=["deploy"], rollback_command=["rollback"],
                            grant_store=store, sleep=lambda _s: None)
    result = deployer.deploy("jarvis")          # kein approved, aber Freigabe
    assert result.ok and calls == [["deploy"]]
    assert store.get_standing_grant(grant["id"])["uses"] == 1


def test_self_deploy_without_grant_asks(tmp_path):
    store = _grant_store(tmp_path)
    deployer = SelfDeployer(lambda cmd: (0, ""), zones=load_zones(), health_check=lambda: True,
                            deploy_command=["deploy"], rollback_command=["rollback"],
                            grant_store=store, sleep=lambda _s: None)
    with pytest.raises(DeployError):
        deployer.deploy("jarvis")
