import os
import tempfile
import unittest

from fastapi.testclient import TestClient

import jarvisappv4
from jarvis.authz import resolve_effective_permissions
from jarvis.group_store import GroupStore
from jarvis.jarvis_engine import normalize_role
from jarvis.membership_store import MembershipStore
from jarvis.permission_store import KNOWN_PERMISSIONS, PermissionStore
from jarvis.tasks.service import TaskAccessError, TaskService
from jarvis.tasks.store import TaskStore
from jarvis.user_store import UserStore


class _AuditLogProbe:
    def __init__(self):
        self.events = []

    def write(self, event: str, payload: dict):
        self.events.append({"event": event, **payload})


class TaskStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_TASKS_STORE_PATH"] = os.path.join(self.tmpdir.name, "tasks.json")
        self.store = TaskStore()

    def tearDown(self):
        os.environ.pop("JARVIS_TASKS_STORE_PATH", None)
        self.tmpdir.cleanup()

    def test_known_permissions_include_tasks_tuple(self):
        self.assertIn("tasks.read", KNOWN_PERMISSIONS)
        self.assertIn("tasks.write", KNOWN_PERMISSIONS)
        self.assertIn("tasks.manage", KNOWN_PERMISSIONS)

    def test_add_list_get_update_complete_delete(self):
        task = self.store.add_task({"id": "t1", "owner_user_id": "u1", "title": "Buy milk", "status": "open"})
        self.assertEqual("Buy milk", task["title"])

        self.assertEqual(1, len(self.store.list_tasks("u1")))
        self.assertEqual(0, len(self.store.list_tasks("u2")))
        self.assertEqual("Buy milk", self.store.get_task("t1")["title"])
        self.assertIsNone(self.store.get_task("missing"))

        updated = self.store.update_task("t1", {"title": "Buy oat milk"})
        self.assertEqual("Buy oat milk", updated["title"])
        self.assertIsNone(self.store.update_task("missing", {"title": "x"}))

        completed = self.store.complete_task("t1")
        self.assertEqual("done", completed["status"])

        self.assertTrue(self.store.delete_task("t1"))
        self.assertFalse(self.store.delete_task("t1"))
        self.assertIsNone(self.store.get_task("t1"))

    def test_store_self_heals_on_corrupt_file(self):
        path = os.environ["JARVIS_TASKS_STORE_PATH"]
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{not valid json")
        store = TaskStore()
        self.assertEqual([], store.list_tasks("u1"))


class TaskServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(base, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_TASKS_STORE_PATH"] = os.path.join(base, "tasks.json")

        self.user_store = UserStore()
        self.group_store = GroupStore()
        self.membership_store = MembershipStore()
        self.permission_store = PermissionStore()
        self.store = TaskStore()
        self.audit_probe = _AuditLogProbe()
        self.service = TaskService(
            store=self.store,
            user_store=self.user_store,
            membership_store=self.membership_store,
            permission_store=self.permission_store,
            resolve_effective_permissions=resolve_effective_permissions,
            normalize_role=normalize_role,
            audit_log=self.audit_probe,
        )

    def tearDown(self):
        os.environ.pop("JARVIS_EMERGENCY_STOP", None)
        self.tmpdir.cleanup()

    def test_standard_user_denied_without_tasks_write_then_allowed(self):
        user = self.user_store.create_user("alice", role="standard_user", enabled=True)
        with self.assertRaises(TaskAccessError):
            self.service.create_task({"title": "Buy milk"}, user_id=user["id"], role=user["role"])

        self.permission_store.set_user_permissions(user["id"], ["tasks.read", "tasks.write"])
        result = self.service.create_task({"title": "Buy milk"}, user_id=user["id"], role=user["role"])
        self.assertEqual("Buy milk", result["task"]["title"])
        self.assertEqual("task_created", self.audit_probe.events[-1]["event"])

    def test_admin_role_bypasses_explicit_permission_grant(self):
        admin = self.user_store.create_user("owner", role="admin", enabled=True)
        result = self.service.create_task({"title": "Patch servers"}, user_id=admin["id"], role=admin["role"])
        self.assertEqual("Patch servers", result["task"]["title"])
        listed = self.service.list_tasks(user_id=admin["id"], role=admin["role"])
        self.assertEqual(1, len(listed["tasks"]))

    def test_group_permissions_unlock_task_write(self):
        user = self.user_store.create_user("bob", role="standard_user", enabled=True)
        group = self.group_store.create_group("task-ops")
        self.membership_store.add_membership(user["id"], group["id"])
        self.permission_store.set_group_permissions(group["id"], ["tasks.read", "tasks.write"])
        result = self.service.create_task({"title": "Rotate backups"}, user_id=user["id"], role=user["role"])
        self.assertEqual("Rotate backups", result["task"]["title"])

    def test_emergency_stop_blocks_task_writes(self):
        admin = self.user_store.create_user("owner", role="admin", enabled=True)
        os.environ["JARVIS_EMERGENCY_STOP"] = "1"
        try:
            with self.assertRaises(PermissionError):
                self.service.create_task({"title": "Blocked task"}, user_id=admin["id"], role=admin["role"])
        finally:
            os.environ.pop("JARVIS_EMERGENCY_STOP", None)

    def test_users_cannot_see_or_modify_each_others_tasks(self):
        admin = self.user_store.create_user("owner", role="admin", enabled=True)
        alice = self.user_store.create_user("alice2", role="standard_user", enabled=True)
        bob = self.user_store.create_user("bob2", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(alice["id"], ["tasks.read", "tasks.write"])
        self.permission_store.set_user_permissions(bob["id"], ["tasks.read", "tasks.write", "tasks.manage"])

        created = self.service.create_task({"title": "Alice's task"}, user_id=alice["id"], role=alice["role"])
        task_id = created["task"]["id"]

        self.assertEqual(0, len(self.service.list_tasks(user_id=bob["id"], role=bob["role"])["tasks"]))
        with self.assertRaises(LookupError):
            self.service.get_task(task_id, user_id=bob["id"], role=bob["role"])
        with self.assertRaises(LookupError):
            self.service.delete_task(task_id, user_id=bob["id"], role=bob["role"])

        # Admin can still see/manage any user's tasks.
        admin_view = self.service.get_task(task_id, user_id=admin["id"], role=admin["role"])
        self.assertEqual("Alice's task", admin_view["task"]["title"])

    def test_delete_requires_tasks_manage_not_just_write(self):
        user = self.user_store.create_user("carol", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["tasks.read", "tasks.write"])
        created = self.service.create_task({"title": "Needs manage perm"}, user_id=user["id"], role=user["role"])
        task_id = created["task"]["id"]
        with self.assertRaises(TaskAccessError):
            self.service.delete_task(task_id, user_id=user["id"], role=user["role"])

        self.permission_store.set_user_permissions(user["id"], ["tasks.read", "tasks.write", "tasks.manage"])
        result = self.service.delete_task(task_id, user_id=user["id"], role=user["role"])
        self.assertTrue(result["deleted"])

    def test_update_complete_and_status_filter(self):
        user = self.user_store.create_user("dana", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["tasks.read", "tasks.write"])
        created = self.service.create_task({"title": "Draft report", "priority": "low"}, user_id=user["id"], role=user["role"])
        task_id = created["task"]["id"]

        updated = self.service.update_task(task_id, {"priority": "high", "status": "in_progress"}, user_id=user["id"], role=user["role"])
        self.assertEqual("high", updated["task"]["priority"])
        self.assertEqual("in_progress", updated["task"]["status"])

        in_progress = self.service.list_tasks(user_id=user["id"], role=user["role"], status="in_progress")["tasks"]
        self.assertEqual(1, len(in_progress))

        completed = self.service.complete_task(task_id, user_id=user["id"], role=user["role"])
        self.assertEqual("done", completed["task"]["status"])
        open_tasks = self.service.list_tasks(user_id=user["id"], role=user["role"], status="open")["tasks"]
        self.assertEqual(0, len(open_tasks))

    def test_invalid_status_and_priority_rejected(self):
        user = self.user_store.create_user("erin", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["tasks.read", "tasks.write"])
        with self.assertRaises(ValueError):
            self.service.create_task({"title": "Bad status", "status": "waffling"}, user_id=user["id"], role=user["role"])
        with self.assertRaises(ValueError):
            self.service.create_task({"title": "Bad priority", "priority": "urgent"}, user_id=user["id"], role=user["role"])
        with self.assertRaises(ValueError):
            self.service.create_task({"title": "  "}, user_id=user["id"], role=user["role"])

    def test_set_task_steps_and_find_open_task_by_title(self):
        user = self.user_store.create_user("finn", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["tasks.read", "tasks.write"])
        created = self.service.create_task({"title": "Plan launch party"}, user_id=user["id"], role=user["role"])
        task_id = created["task"]["id"]

        found = self.service.find_open_task_by_title("launch", user_id=user["id"], role=user["role"])
        self.assertIsNotNone(found)
        self.assertEqual(task_id, found["id"])

        updated = self.service.set_task_steps(task_id, ["Book venue", "Send invites"], user_id=user["id"], role=user["role"])
        self.assertEqual(["Book venue", "Send invites"], updated["task"]["steps"])


class TaskApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(base, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_ADMIN_PASSWORD_STORE_PATH"] = os.path.join(base, "admin_passwords.json")
        os.environ["JARVIS_USER_PREFERENCES_PATH"] = os.path.join(base, "user_preferences.json")
        os.environ["JARVIS_TASKS_STORE_PATH"] = os.path.join(base, "tasks.json")

        jarvisappv4.user_store = jarvisappv4.UserStore()
        jarvisappv4.group_store = jarvisappv4.GroupStore()
        jarvisappv4.membership_store = jarvisappv4.MembershipStore()
        jarvisappv4.permission_store = jarvisappv4.PermissionStore()
        jarvisappv4.admin_password_store = jarvisappv4.AdminPasswordStore()
        jarvisappv4.user_preferences_store = jarvisappv4.UserPreferencesStore()
        jarvisappv4.task_store = jarvisappv4.TaskStore()
        jarvisappv4.task_service = jarvisappv4.TaskService(
            store=jarvisappv4.task_store,
            user_store=jarvisappv4.user_store,
            membership_store=jarvisappv4.membership_store,
            permission_store=jarvisappv4.permission_store,
            resolve_effective_permissions=jarvisappv4.resolve_effective_permissions,
            normalize_role=jarvisappv4.normalize_role,
            audit_log=jarvisappv4.audit_log,
        )
        jarvisappv4._identity_tokens.clear()
        self.client = TestClient(jarvisappv4.app)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _create_user_with_permissions(self, admin_token, admin_id, username, permissions):
        created = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
            json={"username": username, "role": "standard_user", "enabled": True, "password": f"{username}-pass"},
        )
        user_id = created.json()["id"]
        self.client.put(
            f"/admin/permissions/users/{user_id}",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
            json={"permissions": permissions},
        )
        login = self.client.post("/auth/login", json={"username": username, "password": f"{username}-pass"})
        return user_id, login.json()["session_token"]

    def test_full_crud_lifecycle_via_api(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "tasksuser", ["tasks.read", "tasks.write", "tasks.manage"]
        )

        created = self.client.post(
            "/tasks",
            headers={"X-Jarvis-Session": session_token},
            json={"title": "Ship release notes", "priority": "high"},
        )
        self.assertEqual(200, created.status_code)
        task = created.json()["task"]
        self.assertEqual("Ship release notes", task["title"])
        self.assertEqual("open", task["status"])

        listed = self.client.get("/tasks", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, listed.status_code)
        self.assertEqual(1, len(listed.json()["tasks"]))

        updated = self.client.patch(
            f"/tasks/{task['id']}",
            headers={"X-Jarvis-Session": session_token},
            json={"description": "Draft and publish", "status": "in_progress"},
        )
        self.assertEqual(200, updated.status_code)
        self.assertEqual("in_progress", updated.json()["task"]["status"])

        completed = self.client.post(f"/tasks/{task['id']}/complete", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, completed.status_code)
        self.assertEqual("done", completed.json()["task"]["status"])

        filtered = self.client.get("/tasks?status=done", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(1, len(filtered.json()["tasks"]))

        deleted = self.client.delete(f"/tasks/{task['id']}", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, deleted.status_code)
        self.assertTrue(deleted.json()["deleted"])

        after_delete = self.client.get("/tasks", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(0, len(after_delete.json()["tasks"]))

    def test_standard_user_without_permissions_gets_403(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(admin["token"], admin["user_id"], "noperm", [])

        denied = self.client.post(
            "/tasks",
            headers={"X-Jarvis-Session": session_token},
            json={"title": "Should be denied"},
        )
        self.assertEqual(403, denied.status_code)

        denied_list = self.client.get("/tasks", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(403, denied_list.status_code)

    def test_write_only_user_cannot_delete_without_manage_permission(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "writeronly", ["tasks.read", "tasks.write"]
        )
        created = self.client.post(
            "/tasks",
            headers={"X-Jarvis-Session": session_token},
            json={"title": "Cannot delete me"},
        ).json()["task"]

        denied = self.client.delete(f"/tasks/{created['id']}", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(403, denied.status_code)

    def test_update_missing_task_returns_404(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "notfound", ["tasks.read", "tasks.write", "tasks.manage"]
        )
        missing = self.client.patch(
            "/tasks/does-not-exist",
            headers={"X-Jarvis-Session": session_token},
            json={"title": "x"},
        )
        self.assertEqual(404, missing.status_code)

    def test_create_task_validation_error_returns_400(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "badinput", ["tasks.read", "tasks.write"]
        )
        bad = self.client.post(
            "/tasks",
            headers={"X-Jarvis-Session": session_token},
            json={"title": ""},
        )
        self.assertEqual(400, bad.status_code)

    def test_users_isolated_across_task_lists(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, alice_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "isoalice", ["tasks.read", "tasks.write"]
        )
        _, bob_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "isobob", ["tasks.read", "tasks.write"]
        )

        self.client.post("/tasks", headers={"X-Jarvis-Session": alice_token}, json={"title": "Alice only"})
        bob_tasks = self.client.get("/tasks", headers={"X-Jarvis-Session": bob_token})
        self.assertEqual(200, bob_tasks.status_code)
        self.assertEqual(0, len(bob_tasks.json()["tasks"]))


if __name__ == "__main__":
    unittest.main()
