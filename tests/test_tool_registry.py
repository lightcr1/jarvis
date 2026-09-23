from __future__ import annotations

import os
import tempfile
import unittest

from jarvis.audit_log_store import AuditLogStore
from jarvis.agent_grants import AgentGrantStore
from jarvis.group_store import GroupStore
from jarvis.jarvis_engine import RiskLevel
from jarvis.membership_store import MembershipStore
from jarvis.permission_store import PermissionStore
from jarvis.tool_registry import Tool, ToolExecutionContext, ToolRegistry, execute_tool
from jarvis.user_store import UserStore


def _read_tool(ctx: ToolExecutionContext, args: dict) -> dict:
    return {"reply": "ok", "data": {"route": "dummy_read", "seen_args": args}}


def _write_tool(ctx: ToolExecutionContext, args: dict) -> dict:
    return {"reply": "done", "data": {"route": "dummy_write"}}


def _boom_tool(ctx: ToolExecutionContext, args: dict) -> dict:
    raise ValueError("kaboom")


READ_TOOL = Tool(
    name="dummy_read", description="A dummy read tool", parameters={"type": "object", "properties": {}},
    required_permission="files.read", risk=RiskLevel.READ, handler=_read_tool,
)
WRITE_TOOL = Tool(
    name="dummy_write", description="A dummy write tool", parameters={"type": "object", "properties": {}},
    required_permission="files.write", risk=RiskLevel.WRITE, handler=_write_tool,
)
BOOM_TOOL = Tool(
    name="dummy_boom", description="A dummy tool that raises", parameters={"type": "object", "properties": {}},
    required_permission="files.read", risk=RiskLevel.READ, handler=_boom_tool,
)


class ToolRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(base, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_AUDIT_LOG_PATH"] = os.path.join(base, "audit.log")
        os.environ["JARVIS_EMERGENCY_STOP"] = "0"

        self.users = UserStore()
        self.groups = GroupStore()
        self.memberships = MembershipStore()
        self.permissions = PermissionStore()
        self.audit = AuditLogStore()

        self.registry = ToolRegistry()
        self.registry.register(READ_TOOL)
        self.registry.register(WRITE_TOOL)
        self.registry.register(BOOM_TOOL)

    def tearDown(self):
        self.tmpdir.cleanup()
        for k in [
            "JARVIS_USER_STORE_PATH", "JARVIS_GROUP_STORE_PATH", "JARVIS_MEMBERSHIP_STORE_PATH",
            "JARVIS_PERMISSION_STORE_PATH", "JARVIS_AUDIT_LOG_PATH", "JARVIS_EMERGENCY_STOP",
        ]:
            os.environ.pop(k, None)

    def _ctx(self, user, role) -> ToolExecutionContext:
        return ToolExecutionContext(user_id=user["id"] if user else None, role=role, deps={})

    def test_admin_sees_all_registered_tools(self):
        admin = self.users.create_user("root", role="admin")
        available = self.registry.available_to("admin", admin["id"], self.memberships, self.permissions)
        self.assertEqual({t.name for t in available}, {"dummy_read", "dummy_write", "dummy_boom"})

    def test_guest_restricted_sees_no_pilot_tools_without_grant(self):
        guest = self.users.create_user("guest1", role="guest_restricted")
        available = self.registry.available_to("guest_restricted", guest["id"], self.memberships, self.permissions)
        self.assertEqual(available, [])

    def test_explicit_grant_unlocks_a_tool_for_guest(self):
        guest = self.users.create_user("guest2", role="guest_restricted")
        self.permissions.set_user_permissions(guest["id"], ["files.read"])
        available = self.registry.available_to("guest_restricted", guest["id"], self.memberships, self.permissions)
        self.assertEqual({t.name for t in available}, {"dummy_read", "dummy_boom"})

    def test_execute_tool_denies_without_permission(self):
        guest = self.users.create_user("guest3", role="guest_restricted")
        result = execute_tool(
            READ_TOOL, self._ctx(guest, "guest_restricted"), {},
            audit_log=self.audit, membership_store=self.memberships, permission_store=self.permissions,
        )
        self.assertEqual(result["data"]["error"], "permission_denied")
        self.assertEqual(1, self.audit.count_events(event="tool_permission_denied"))

    def test_execute_tool_runs_handler_when_permitted(self):
        admin = self.users.create_user("root2", role="admin")
        result = execute_tool(
            READ_TOOL, self._ctx(admin, "admin"), {"folder_name": "Reports"},
            audit_log=self.audit, membership_store=self.memberships, permission_store=self.permissions,
        )
        self.assertEqual("dummy_read", result["data"]["route"])
        self.assertEqual({"folder_name": "Reports"}, result["data"]["seen_args"])
        self.assertEqual(1, self.audit.count_events(event="tool_call_completed"))

    def test_emergency_stop_blocks_write_risk_tool(self):
        os.environ["JARVIS_EMERGENCY_STOP"] = "1"
        admin = self.users.create_user("root3", role="admin")
        result = execute_tool(
            WRITE_TOOL, self._ctx(admin, "admin"), {},
            audit_log=self.audit, membership_store=self.memberships, permission_store=self.permissions,
        )
        self.assertEqual(result["data"]["error"], "emergency_stop")
        self.assertEqual(1, self.audit.count_events(event="tool_emergency_stop_blocked"))

    def test_emergency_stop_does_not_block_read_risk_tool(self):
        os.environ["JARVIS_EMERGENCY_STOP"] = "1"
        admin = self.users.create_user("root4", role="admin")
        result = execute_tool(
            READ_TOOL, self._ctx(admin, "admin"), {},
            audit_log=self.audit, membership_store=self.memberships, permission_store=self.permissions,
        )
        self.assertEqual("dummy_read", result["data"]["route"])

    def test_handler_exception_is_caught_and_reported(self):
        admin = self.users.create_user("root5", role="admin")
        result = execute_tool(
            BOOM_TOOL, self._ctx(admin, "admin"), {},
            audit_log=self.audit, membership_store=self.memberships, permission_store=self.permissions,
        )
        self.assertEqual(result["data"]["error"], "kaboom")
        self.assertEqual(1, self.audit.count_events(event="tool_call_error"))

    def test_execute_tool_write_risk_requires_confirmation(self):
        admin = self.users.create_user("root6", role="admin")
        result = execute_tool(
            WRITE_TOOL, self._ctx(admin, "admin"), {"service": "nginx"},
            audit_log=self.audit, membership_store=self.memberships, permission_store=self.permissions,
        )
        self.assertEqual("tool_confirmation_required", result["data"]["route"])
        self.assertEqual("dummy_write", result["data"]["tool"])
        self.assertEqual({"service": "nginx"}, result["data"]["args"])
        self.assertEqual(RiskLevel.WRITE, result["data"]["risk"])
        self.assertEqual(1, self.audit.count_events(event="tool_confirmation_requested"))
        self.assertEqual(0, self.audit.count_events(event="tool_call_completed"))

    def test_execute_tool_write_risk_executes_when_confirmed(self):
        admin = self.users.create_user("root7", role="admin")
        result = execute_tool(
            WRITE_TOOL, self._ctx(admin, "admin"), {}, confirm=True,
            audit_log=self.audit, membership_store=self.memberships, permission_store=self.permissions,
        )
        self.assertEqual("dummy_write", result["data"]["route"])
        self.assertEqual(1, self.audit.count_events(event="tool_call_completed"))

    def test_service_system_requires_scoped_grant_before_write(self):
        service = self.users.create_user("agent", role="service_system")
        self.permissions.set_user_permissions(service["id"], ["tasks.write", "files.write"])
        grant_store = AgentGrantStore(os.path.join(self.tmpdir.name, "grants.sqlite3"))
        task_tool = Tool(
            name="create_task", description="Create a task", parameters={"type": "object", "properties": {}},
            required_permission="tasks.write", risk=RiskLevel.WRITE, handler=_write_tool,
        )
        kwargs = {"audit_log": self.audit, "membership_store": self.memberships,
                  "permission_store": self.permissions, "agent_grant_store": grant_store}
        ctx = self._ctx(service, "service_system")
        self.assertEqual("agent_grant_required", execute_tool(task_tool, ctx, {}, **kwargs)["data"]["error"])
        request = grant_store.request(kind="workspace", target="jarvis:tasks", operation="create_task",
                                      reason="Owner task project", duration_seconds=3600)
        grant_store.decide(request["id"], actor="owner", approve=True)
        self.assertEqual("dummy_write", execute_tool(task_tool, ctx, {}, **kwargs)["data"]["route"])
        # The approval does not authorize a different tool, even with RBAC permissions.
        self.assertEqual("agent_grant_required", execute_tool(WRITE_TOOL, ctx, {}, **kwargs)["data"]["error"])
        grant_store.revoke(request["id"], actor="owner")
        self.assertEqual("agent_grant_required", execute_tool(task_tool, ctx, {}, **kwargs)["data"]["error"])
        os.environ["JARVIS_EMERGENCY_STOP"] = "1"
        self.assertEqual("emergency_stop", execute_tool(task_tool, ctx, {}, **kwargs)["data"]["error"])

    def test_read_risk_tool_never_requires_confirmation(self):
        admin = self.users.create_user("root8", role="admin")
        result = execute_tool(
            READ_TOOL, self._ctx(admin, "admin"), {},
            audit_log=self.audit, membership_store=self.memberships, permission_store=self.permissions,
        )
        self.assertEqual("dummy_read", result["data"]["route"])


if __name__ == "__main__":
    unittest.main()
