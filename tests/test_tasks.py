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
from jarvis.tasks.share_store import TaskShareStore
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
        self.assertIn("tasks.share", KNOWN_PERMISSIONS)

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
        os.environ["JARVIS_TASKS_SHARE_STORE_PATH"] = os.path.join(base, "tasks_shares.json")

        self.user_store = UserStore()
        self.group_store = GroupStore()
        self.membership_store = MembershipStore()
        self.permission_store = PermissionStore()
        self.store = TaskStore()
        self.share_store = TaskShareStore()
        self.audit_probe = _AuditLogProbe()
        self.service = TaskService(
            store=self.store,
            user_store=self.user_store,
            membership_store=self.membership_store,
            permission_store=self.permission_store,
            resolve_effective_permissions=resolve_effective_permissions,
            normalize_role=normalize_role,
            share_store=self.share_store,
            group_store=self.group_store,
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

    def test_due_at_round_trips_through_create_and_update(self):
        user = self.user_store.create_user("greta", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["tasks.read", "tasks.write"])
        created = self.service.create_task({"title": "File taxes", "due_at": 1_800_000_000}, user_id=user["id"], role=user["role"])
        self.assertEqual(1_800_000_000, created["task"]["due_at"])
        updated = self.service.update_task(created["task"]["id"], {"due_at": None}, user_id=user["id"], role=user["role"])
        self.assertIsNone(updated["task"]["due_at"])

    def test_invalid_assignee_rejected(self):
        user = self.user_store.create_user("harry", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["tasks.read", "tasks.write"])
        with self.assertRaises(ValueError):
            self.service.create_task({"title": "Assign to nobody", "assignee_user_id": "does-not-exist"}, user_id=user["id"], role=user["role"])

    def test_assignee_sees_task_and_can_complete_but_not_reassign_or_delete(self):
        owner = self.user_store.create_user("owner1", role="standard_user", enabled=True)
        assignee = self.user_store.create_user("assignee1", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(owner["id"], ["tasks.read", "tasks.write", "tasks.manage"])
        self.permission_store.set_user_permissions(assignee["id"], ["tasks.read", "tasks.write"])

        created = self.service.create_task(
            {"title": "Review PR", "assignee_user_id": assignee["id"]}, user_id=owner["id"], role=owner["role"],
        )
        task_id = created["task"]["id"]

        assignee_tasks = self.service.list_tasks(user_id=assignee["id"], role=assignee["role"])["tasks"]
        self.assertEqual(1, len(assignee_tasks))

        completed = self.service.complete_task(task_id, user_id=assignee["id"], role=assignee["role"])
        self.assertEqual("done", completed["task"]["status"])

        with self.assertRaises(TaskAccessError):
            self.service.update_task(task_id, {"assignee_user_id": owner["id"]}, user_id=assignee["id"], role=assignee["role"])
        with self.assertRaises(TaskAccessError):
            self.service.delete_task(task_id, user_id=assignee["id"], role=assignee["role"])

    def test_share_task_read_access_blocks_writes(self):
        owner = self.user_store.create_user("owner2", role="standard_user", enabled=True)
        viewer = self.user_store.create_user("viewer1", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(owner["id"], ["tasks.read", "tasks.write", "tasks.manage", "tasks.share"])
        self.permission_store.set_user_permissions(viewer["id"], ["tasks.read", "tasks.write"])
        group = self.group_store.create_group("viewers")
        self.membership_store.add_membership(viewer["id"], group["id"])

        created = self.service.create_task({"title": "Q3 plan"}, user_id=owner["id"], role=owner["role"])
        task_id = created["task"]["id"]
        self.service.share_task(task_id, group["id"], "read", user_id=owner["id"], role=owner["role"])

        viewed = self.service.get_task(task_id, user_id=viewer["id"], role=viewer["role"])
        self.assertEqual("read", viewed["access"])
        with self.assertRaises(TaskAccessError):
            self.service.update_task(task_id, {"priority": "high"}, user_id=viewer["id"], role=viewer["role"])
        with self.assertRaises(TaskAccessError):
            self.service.complete_task(task_id, user_id=viewer["id"], role=viewer["role"])

        shared = self.service.list_shared_with_me(user_id=viewer["id"], role=viewer["role"])["shared"]
        self.assertEqual(1, len(shared))
        self.assertEqual(task_id, shared[0]["task"]["id"])

    def test_share_task_write_access_allows_updates_but_not_delete_or_reshare(self):
        owner = self.user_store.create_user("owner3", role="standard_user", enabled=True)
        editor = self.user_store.create_user("editor1", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(owner["id"], ["tasks.read", "tasks.write", "tasks.manage", "tasks.share"])
        self.permission_store.set_user_permissions(editor["id"], ["tasks.read", "tasks.write"])
        group = self.group_store.create_group("editors")
        self.membership_store.add_membership(editor["id"], group["id"])

        created = self.service.create_task({"title": "Budget doc"}, user_id=owner["id"], role=owner["role"])
        task_id = created["task"]["id"]
        self.service.share_task(task_id, group["id"], "write", user_id=owner["id"], role=owner["role"])

        updated = self.service.update_task(task_id, {"status": "in_progress"}, user_id=editor["id"], role=editor["role"])
        self.assertEqual("in_progress", updated["task"]["status"])

        with self.assertRaises(TaskAccessError):
            self.service.delete_task(task_id, user_id=editor["id"], role=editor["role"])
        with self.assertRaises(TaskAccessError):
            self.service.share_task(task_id, group["id"], "read", user_id=editor["id"], role=editor["role"])

    def test_only_owner_can_unshare_and_share_id_is_removed_on_delete(self):
        owner = self.user_store.create_user("owner4", role="standard_user", enabled=True)
        other = self.user_store.create_user("other4", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(owner["id"], ["tasks.read", "tasks.write", "tasks.manage", "tasks.share"])
        self.permission_store.set_user_permissions(other["id"], ["tasks.read", "tasks.write", "tasks.share"])
        group = self.group_store.create_group("g4")

        created = self.service.create_task({"title": "Roadmap"}, user_id=owner["id"], role=owner["role"])
        task_id = created["task"]["id"]
        share = self.service.share_task(task_id, group["id"], "read", user_id=owner["id"], role=owner["role"])["share"]

        with self.assertRaises(LookupError):
            self.service.unshare_task(share["id"], user_id=other["id"], role=other["role"])

        self.service.delete_task(task_id, user_id=owner["id"], role=owner["role"])
        self.assertEqual([], self.share_store.list_shares_for_task(task_id))

    def test_list_assignable_users_and_my_groups(self):
        owner = self.user_store.create_user("owner5", role="standard_user", enabled=True)
        self.user_store.create_user("teammate5", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(owner["id"], ["tasks.read", "tasks.write"])
        self.group_store.create_group("alpha")

        users = self.service.list_assignable_users(user_id=owner["id"], role=owner["role"])["users"]
        usernames = {u["username"] for u in users}
        self.assertIn("owner5", usernames)
        self.assertIn("teammate5", usernames)

        groups = self.service.list_my_groups(user_id=owner["id"], role=owner["role"])["groups"]
        self.assertTrue(any(g["name"] == "alpha" for g in groups))


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
        os.environ["JARVIS_TASKS_SHARE_STORE_PATH"] = os.path.join(base, "tasks_shares.json")

        jarvisappv4.user_store = jarvisappv4.UserStore()
        jarvisappv4.group_store = jarvisappv4.GroupStore()
        jarvisappv4.membership_store = jarvisappv4.MembershipStore()
        jarvisappv4.permission_store = jarvisappv4.PermissionStore()
        jarvisappv4.admin_password_store = jarvisappv4.AdminPasswordStore()
        jarvisappv4.user_preferences_store = jarvisappv4.UserPreferencesStore()
        jarvisappv4.task_store = jarvisappv4.TaskStore()
        jarvisappv4.task_share_store = jarvisappv4.TaskShareStore()
        jarvisappv4.task_service = jarvisappv4.TaskService(
            store=jarvisappv4.task_store,
            user_store=jarvisappv4.user_store,
            membership_store=jarvisappv4.membership_store,
            permission_store=jarvisappv4.permission_store,
            resolve_effective_permissions=jarvisappv4.resolve_effective_permissions,
            normalize_role=jarvisappv4.normalize_role,
            share_store=jarvisappv4.task_share_store,
            group_store=jarvisappv4.group_store,
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

    def test_assign_task_to_teammate_via_api(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        owner_id, owner_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "assignowner", ["tasks.read", "tasks.write", "tasks.manage"]
        )
        assignee_id, assignee_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "assignee", ["tasks.read", "tasks.write"]
        )

        assignable = self.client.get("/tasks/assignable-users", headers={"X-Jarvis-Session": owner_token})
        self.assertEqual(200, assignable.status_code)
        usernames = {u["username"] for u in assignable.json()["users"]}
        self.assertIn("assignee", usernames)

        created = self.client.post(
            "/tasks",
            headers={"X-Jarvis-Session": owner_token},
            json={"title": "Fix the bug", "assignee_user_id": assignee_id},
        ).json()["task"]
        self.assertEqual(assignee_id, created["assignee_user_id"])

        assignee_list = self.client.get("/tasks", headers={"X-Jarvis-Session": assignee_token})
        self.assertEqual(1, len(assignee_list.json()["tasks"]))

        completed = self.client.post(f"/tasks/{created['id']}/complete", headers={"X-Jarvis-Session": assignee_token})
        self.assertEqual(200, completed.status_code)
        self.assertEqual("done", completed.json()["task"]["status"])

    def test_share_task_with_group_via_api(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, owner_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "shareowner", ["tasks.read", "tasks.write", "tasks.manage", "tasks.share"]
        )
        _, viewer_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "shareviewer", ["tasks.read", "tasks.write"]
        )

        group = self.client.post(
            "/admin/groups",
            headers={"Authorization": f"Bearer {admin['token']}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin["user_id"]},
            json={"name": "shared-with"},
        ).json()
        users = self.client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {admin['token']}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin["user_id"]},
        ).json()["users"]
        viewer_id = next(u["id"] for u in users if u["username"] == "shareviewer")
        self.client.post(
            "/admin/assignments",
            headers={"Authorization": f"Bearer {admin['token']}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin["user_id"]},
            json={"user_id": viewer_id, "group_id": group["id"]},
        )

        created = self.client.post(
            "/tasks", headers={"X-Jarvis-Session": owner_token}, json={"title": "Shared roadmap"},
        ).json()["task"]

        share = self.client.post(
            f"/tasks/{created['id']}/shares",
            headers={"X-Jarvis-Session": owner_token},
            json={"group_id": group["id"], "permission": "read"},
        )
        self.assertEqual(200, share.status_code)

        shared_with_me = self.client.get("/tasks/shared-with-me", headers={"X-Jarvis-Session": viewer_token})
        self.assertEqual(200, shared_with_me.status_code)
        self.assertEqual(1, len(shared_with_me.json()["shared"]))
        self.assertEqual(created["id"], shared_with_me.json()["shared"][0]["task"]["id"])

        denied_edit = self.client.patch(
            f"/tasks/{created['id']}", headers={"X-Jarvis-Session": viewer_token}, json={"priority": "high"},
        )
        self.assertEqual(403, denied_edit.status_code)

        share_id = share.json()["share"]["id"]
        unshared = self.client.delete(f"/tasks/shares/{share_id}", headers={"X-Jarvis-Session": owner_token})
        self.assertEqual(200, unshared.status_code)
        self.assertTrue(unshared.json()["deleted"])

        after_unshare = self.client.get("/tasks/shared-with-me", headers={"X-Jarvis-Session": viewer_token})
        self.assertEqual(0, len(after_unshare.json()["shared"]))


if __name__ == "__main__":
    unittest.main()
