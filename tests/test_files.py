import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import jarvisappv4
from jarvis.admin_settings_store import AdminSettingsStore
from jarvis.authz import resolve_effective_permissions
from jarvis.files.path_safety import PathSafetyError, resolve_within_root, sanitize_segment
from jarvis.files.service import FileAccessError, FileService
from jarvis.files.share_store import FolderShareStore
from jarvis.files.store import FileStore
from jarvis.group_store import GroupStore
from jarvis.jarvis_engine import normalize_role
from jarvis.membership_store import MembershipStore
from jarvis.permission_store import KNOWN_PERMISSIONS, PermissionStore
from jarvis.user_limits_store import UserLimitsStore
from jarvis.user_store import UserStore


class _AuditLogProbe:
    def __init__(self):
        self.events = []

    def write(self, event: str, payload: dict):
        self.events.append({"event": event, **payload})


class _BytesReader:
    """Minimal async chunked reader mimicking FastAPI's UploadFile.read()."""

    def __init__(self, data: bytes, chunk_size: int = 3):
        self._data = data
        self._pos = 0
        self._chunk_size = chunk_size

    async def read(self, size: int = -1) -> bytes:
        want = size if size and size > 0 else self._chunk_size
        chunk = self._data[self._pos:self._pos + want]
        self._pos += len(chunk)
        return chunk


def _run(coro):
    return asyncio.run(coro)


# ----------------------------------------------------------------------
# Path safety — this is the module the whole feature's security rests on.
# ----------------------------------------------------------------------


class PathSafetyTests(unittest.TestCase):
    def test_sanitize_segment_accepts_normal_names(self):
        self.assertEqual("Project Alpha", sanitize_segment("Project Alpha"))
        self.assertEqual("report.pdf", sanitize_segment("report.pdf"))
        self.assertEqual(".hidden", sanitize_segment(".hidden"))
        self.assertEqual("résumé.docx", sanitize_segment("résumé.docx"))

    def test_sanitize_segment_strips_surrounding_whitespace(self):
        self.assertEqual("notes", sanitize_segment("  notes  "))

    def test_sanitize_segment_rejects_none(self):
        with self.assertRaises(PathSafetyError):
            sanitize_segment(None)

    def test_sanitize_segment_rejects_empty_and_whitespace(self):
        with self.assertRaises(PathSafetyError):
            sanitize_segment("")
        with self.assertRaises(PathSafetyError):
            sanitize_segment("   ")

    def test_sanitize_segment_rejects_dot_and_dotdot(self):
        with self.assertRaises(PathSafetyError):
            sanitize_segment(".")
        with self.assertRaises(PathSafetyError):
            sanitize_segment("..")

    def test_sanitize_segment_rejects_forward_slash_traversal(self):
        with self.assertRaises(PathSafetyError):
            sanitize_segment("../../etc/passwd")
        with self.assertRaises(PathSafetyError):
            sanitize_segment("../secret")
        with self.assertRaises(PathSafetyError):
            sanitize_segment("a/b")

    def test_sanitize_segment_rejects_backslash_traversal(self):
        with self.assertRaises(PathSafetyError):
            sanitize_segment("..\\..\\windows\\system32")
        with self.assertRaises(PathSafetyError):
            sanitize_segment("a\\b")

    def test_sanitize_segment_rejects_absolute_unix_path(self):
        with self.assertRaises(PathSafetyError):
            sanitize_segment("/etc/passwd")

    def test_sanitize_segment_rejects_absolute_windows_path(self):
        with self.assertRaises(PathSafetyError):
            sanitize_segment("C:\\Windows\\System32")

    def test_sanitize_segment_rejects_null_byte(self):
        with self.assertRaises(PathSafetyError):
            sanitize_segment("evil\x00.txt")
        with self.assertRaises(PathSafetyError):
            sanitize_segment("../../etc/passwd\x00.png")

    def test_sanitize_segment_rejects_control_characters(self):
        with self.assertRaises(PathSafetyError):
            sanitize_segment("evil\nname")
        with self.assertRaises(PathSafetyError):
            sanitize_segment("evil\rname")
        with self.assertRaises(PathSafetyError):
            sanitize_segment("evil\tname")

    def test_sanitize_segment_rejects_too_long(self):
        with self.assertRaises(PathSafetyError):
            sanitize_segment("a" * 256)
        sanitize_segment("a" * 255)  # exactly at the limit is fine

    def test_resolve_within_root_happy_path(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            resolved = resolve_within_root(root, "Documents", "report.pdf")
            self.assertEqual(root.resolve() / "Documents" / "report.pdf", resolved)

    def test_resolve_within_root_rejects_traversal_segment(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            with self.assertRaises(PathSafetyError):
                resolve_within_root(root, "..", "etc", "passwd")

    def test_resolve_within_root_rejects_absolute_path_component(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            with self.assertRaises(PathSafetyError):
                resolve_within_root(root, "/etc/passwd")

    def test_resolve_within_root_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as outside, tempfile.TemporaryDirectory() as base:
            root = Path(base) / "user-root"
            root.mkdir()
            secret_dir = Path(outside)
            (secret_dir / "secret.txt").write_text("top secret")
            link = root / "escape-link"
            link.symlink_to(secret_dir)
            with self.assertRaises(PathSafetyError):
                resolve_within_root(root, "escape-link", "secret.txt")

    def test_resolve_within_root_rejects_no_segments_pointing_at_root_itself(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            # A folder record with an empty ancestor chain would resolve to
            # root itself; callers must never treat root as an addressable
            # child object.
            with self.assertRaises(PathSafetyError):
                resolve_within_root(root, "")


# ----------------------------------------------------------------------
# FileStore — metadata + disk path resolution, against a real filesystem.
# ----------------------------------------------------------------------


class FileStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_FILES_STORE_PATH"] = os.path.join(base, "files_metadata.json")
        os.environ["JARVIS_USER_FILES_PATH"] = os.path.join(base, "user_files")
        self.store = FileStore()

    def tearDown(self):
        os.environ.pop("JARVIS_FILES_STORE_PATH", None)
        os.environ.pop("JARVIS_USER_FILES_PATH", None)
        self.tmpdir.cleanup()

    def test_known_permissions_include_files_tuple(self):
        self.assertIn("files.read", KNOWN_PERMISSIONS)
        self.assertIn("files.write", KNOWN_PERMISSIONS)
        self.assertIn("files.manage", KNOWN_PERMISSIONS)

    def test_user_root_path_created_on_disk(self):
        root = self.store.user_root_path("usr-1")
        self.assertTrue(root.is_dir())
        self.assertTrue(str(root).startswith(os.environ["JARVIS_USER_FILES_PATH"]))

    def test_folder_crud(self):
        folder = self.store.add_folder({"id": "f1", "parent_id": None, "name": "Docs", "owner_user_id": "u1", "jarvis_access_granted": False})
        self.assertEqual("Docs", folder["name"])
        self.assertEqual(1, len(self.store.list_child_folders("u1", None)))
        self.assertEqual("Docs", self.store.get_folder("f1")["name"])
        self.assertIsNone(self.store.get_folder("missing"))

        updated = self.store.update_folder("f1", {"name": "Documents"})
        self.assertEqual("Documents", updated["name"])

        self.assertTrue(self.store.delete_folder("f1"))
        self.assertFalse(self.store.delete_folder("f1"))

    def test_file_crud(self):
        file_meta = self.store.add_file({"id": "file-1", "folder_id": None, "filename": "a.txt", "owner_user_id": "u1", "size_bytes": 5})
        self.assertEqual("a.txt", file_meta["filename"])
        self.assertEqual(1, len(self.store.list_files_in_folder("u1", None)))
        self.assertTrue(self.store.delete_file("file-1"))
        self.assertFalse(self.store.delete_file("file-1"))

    def test_quota_usage_tracks_running_total(self):
        self.assertEqual(0, self.store.get_quota_usage_bytes("u1"))
        self.assertEqual(100, self.store.adjust_quota_usage_bytes("u1", 100))
        self.assertEqual(150, self.store.adjust_quota_usage_bytes("u1", 50))
        self.assertEqual(0, self.store.adjust_quota_usage_bytes("u1", -1000))  # clamped at zero

    def test_folder_disk_path_walks_ancestor_chain(self):
        self.store.add_folder({"id": "f1", "parent_id": None, "name": "Project", "owner_user_id": "u1", "jarvis_access_granted": False})
        self.store.add_folder({"id": "f2", "parent_id": "f1", "name": "Sub", "owner_user_id": "u1", "jarvis_access_granted": False})
        path = self.store.folder_disk_path("u1", "f2")
        self.assertTrue(str(path).endswith(os.path.join("Project", "Sub")))

    def test_folder_disk_path_rejects_cross_user_lookup(self):
        self.store.add_folder({"id": "f1", "parent_id": None, "name": "Private", "owner_user_id": "owner", "jarvis_access_granted": False})
        with self.assertRaises(LookupError):
            self.store.folder_disk_path("attacker", "f1")

    def test_store_self_heals_on_corrupt_metadata(self):
        path = os.environ["JARVIS_FILES_STORE_PATH"]
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{not valid json")
        store = FileStore()
        self.assertEqual([], store.list_child_folders("u1", None))


# ----------------------------------------------------------------------
# FileService — permissions, quota, ownership, and path safety end to end.
# ----------------------------------------------------------------------


class FileServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(base, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_FILES_STORE_PATH"] = os.path.join(base, "files_metadata.json")
        os.environ["JARVIS_USER_FILES_PATH"] = os.path.join(base, "user_files")
        os.environ["JARVIS_USER_LIMITS_STORE_PATH"] = os.path.join(base, "user_limits.json")
        os.environ["JARVIS_ADMIN_SETTINGS_PATH"] = os.path.join(base, "admin_settings.json")
        os.environ["JARVIS_FILES_SHARE_STORE_PATH"] = os.path.join(base, "files_shares.json")

        self.user_store = UserStore()
        self.group_store = GroupStore()
        self.membership_store = MembershipStore()
        self.permission_store = PermissionStore()
        self.store = FileStore()
        self.share_store = FolderShareStore()
        self.user_limits_store = UserLimitsStore()
        self.admin_settings_store = AdminSettingsStore()
        self.audit_probe = _AuditLogProbe()
        self.service = FileService(
            store=self.store,
            user_store=self.user_store,
            membership_store=self.membership_store,
            permission_store=self.permission_store,
            resolve_effective_permissions=resolve_effective_permissions,
            normalize_role=normalize_role,
            user_limits_store=self.user_limits_store,
            admin_settings_store=self.admin_settings_store,
            share_store=self.share_store,
            group_store=self.group_store,
            audit_log=self.audit_probe,
        )

    def tearDown(self):
        for key in (
            "JARVIS_USER_STORE_PATH", "JARVIS_GROUP_STORE_PATH", "JARVIS_MEMBERSHIP_STORE_PATH",
            "JARVIS_PERMISSION_STORE_PATH", "JARVIS_FILES_STORE_PATH", "JARVIS_USER_FILES_PATH",
            "JARVIS_USER_LIMITS_STORE_PATH", "JARVIS_ADMIN_SETTINGS_PATH", "JARVIS_EMERGENCY_STOP",
            "JARVIS_FILES_MAX_UPLOAD_MB", "JARVIS_FILES_SHARE_STORE_PATH",
        ):
            os.environ.pop(key, None)
        self.tmpdir.cleanup()

    def _rw_user(self, username="alice", extra_perms=()):
        user = self.user_store.create_user(username, role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["files.read", "files.write", *extra_perms])
        return user

    def _rwm_user(self, username="alice"):
        return self._rw_user(username, extra_perms=["files.manage"])

    def _upload(self, *, folder_id, filename, content: bytes, user, content_type="text/plain"):
        return _run(
            self.service.upload_file(
                folder_id=folder_id,
                filename=filename,
                reader=_BytesReader(content),
                content_type=content_type,
                user_id=user["id"],
                role=user["role"],
            )
        )

    # -- permissions -----------------------------------------------------

    def test_standard_user_denied_without_files_read(self):
        user = self.user_store.create_user("nobody", role="standard_user", enabled=True)
        with self.assertRaises(FileAccessError):
            self.service.browse(None, user_id=user["id"], role=user["role"])

    def test_standard_user_denied_without_files_write(self):
        user = self.user_store.create_user("readonly", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["files.read"])
        with self.assertRaises(FileAccessError):
            self.service.create_folder({"name": "Docs"}, user_id=user["id"], role=user["role"])

    def test_admin_bypasses_explicit_permission_grant(self):
        admin = self.user_store.create_user("owner", role="admin", enabled=True)
        result = self.service.create_folder({"name": "Ops"}, user_id=admin["id"], role=admin["role"])
        self.assertEqual("Ops", result["folder"]["name"])

    def test_group_permissions_unlock_files_write(self):
        user = self.user_store.create_user("bob", role="standard_user", enabled=True)
        group = self.group_store.create_group("files-ops")
        self.membership_store.add_membership(user["id"], group["id"])
        self.permission_store.set_group_permissions(group["id"], ["files.read", "files.write"])
        result = self.service.create_folder({"name": "Shared"}, user_id=user["id"], role=user["role"])
        self.assertEqual("Shared", result["folder"]["name"])

    def test_delete_requires_files_manage_not_just_write(self):
        user = self._rw_user()
        folder = self.service.create_folder({"name": "Temp"}, user_id=user["id"], role=user["role"])["folder"]
        with self.assertRaises(FileAccessError):
            self.service.delete_folder(folder["id"], user_id=user["id"], role=user["role"])
        self.permission_store.set_user_permissions(user["id"], ["files.read", "files.write", "files.manage"])
        result = self.service.delete_folder(folder["id"], user_id=user["id"], role=user["role"])
        self.assertTrue(result["deleted"])

    # -- folder / file CRUD -----------------------------------------------

    def test_create_folder_creates_real_directory_on_disk(self):
        user = self._rw_user()
        folder = self.service.create_folder({"name": "Project Alpha"}, user_id=user["id"], role=user["role"])["folder"]
        disk_path = self.store.folder_disk_path(user["id"], folder["id"])
        self.assertTrue(disk_path.is_dir())

    def test_nested_folder_creates_real_nested_directory(self):
        user = self._rw_user()
        parent = self.service.create_folder({"name": "Project"}, user_id=user["id"], role=user["role"])["folder"]
        child = self.service.create_folder({"name": "Sub", "parent_id": parent["id"]}, user_id=user["id"], role=user["role"])["folder"]
        disk_path = self.store.folder_disk_path(user["id"], child["id"])
        self.assertTrue(disk_path.is_dir())
        self.assertEqual(parent["id"], child["parent_id"])

    def test_duplicate_folder_name_in_same_parent_rejected(self):
        user = self._rw_user()
        self.service.create_folder({"name": "Docs"}, user_id=user["id"], role=user["role"])
        with self.assertRaises(ValueError):
            self.service.create_folder({"name": "Docs"}, user_id=user["id"], role=user["role"])

    def test_upload_creates_real_file_with_correct_bytes(self):
        user = self._rw_user()
        content = b"hello jarvis, this is a test upload"
        result = self._upload(folder_id=None, filename="hello.txt", content=content, user=user)
        file_meta = result["file"]
        self.assertEqual(len(content), file_meta["size_bytes"])
        disk_path = self.store.file_disk_path(file_meta)
        self.assertEqual(content, disk_path.read_bytes())

    def test_upload_into_nested_folder(self):
        user = self._rw_user()
        folder = self.service.create_folder({"name": "Reports"}, user_id=user["id"], role=user["role"])["folder"]
        content = b"quarterly numbers"
        result = self._upload(folder_id=folder["id"], filename="q1.txt", content=content, user=user)
        disk_path = self.store.file_disk_path(result["file"])
        self.assertEqual(content, disk_path.read_bytes())

    def test_upload_updates_quota_usage(self):
        user = self._rw_user()
        content = b"x" * 1000
        self._upload(folder_id=None, filename="big.bin", content=content, user=user)
        self.assertEqual(1000, self.store.get_quota_usage_bytes(user["id"]))

    def test_duplicate_filename_rejected(self):
        user = self._rw_user()
        self._upload(folder_id=None, filename="dup.txt", content=b"one", user=user)
        with self.assertRaises(ValueError):
            self._upload(folder_id=None, filename="dup.txt", content=b"two", user=user)

    def test_rename_folder_moves_directory_on_disk(self):
        user = self._rw_user()
        folder = self.service.create_folder({"name": "Old"}, user_id=user["id"], role=user["role"])["folder"]
        old_path = self.store.folder_disk_path(user["id"], folder["id"])
        updated = self.service.update_folder(folder["id"], {"name": "New"}, user_id=user["id"], role=user["role"])["folder"]
        new_path = self.store.folder_disk_path(user["id"], updated["id"])
        self.assertFalse(old_path.exists())
        self.assertTrue(new_path.exists())

    def test_move_folder_into_another_folder(self):
        user = self._rw_user()
        a = self.service.create_folder({"name": "A"}, user_id=user["id"], role=user["role"])["folder"]
        b = self.service.create_folder({"name": "B"}, user_id=user["id"], role=user["role"])["folder"]
        moved = self.service.update_folder(b["id"], {"parent_id": a["id"]}, user_id=user["id"], role=user["role"])["folder"]
        self.assertEqual(a["id"], moved["parent_id"])
        disk_path = self.store.folder_disk_path(user["id"], b["id"])
        self.assertTrue(str(disk_path).endswith(os.path.join("A", "B")))

    def test_move_folder_into_own_descendant_rejected(self):
        user = self._rw_user()
        parent = self.service.create_folder({"name": "Parent"}, user_id=user["id"], role=user["role"])["folder"]
        child = self.service.create_folder({"name": "Child", "parent_id": parent["id"]}, user_id=user["id"], role=user["role"])["folder"]
        with self.assertRaises(ValueError):
            self.service.update_folder(parent["id"], {"parent_id": child["id"]}, user_id=user["id"], role=user["role"])

    def test_move_folder_into_itself_rejected(self):
        user = self._rw_user()
        folder = self.service.create_folder({"name": "Loop"}, user_id=user["id"], role=user["role"])["folder"]
        with self.assertRaises(ValueError):
            self.service.update_folder(folder["id"], {"parent_id": folder["id"]}, user_id=user["id"], role=user["role"])

    def test_move_file_between_folders(self):
        user = self._rw_user()
        a = self.service.create_folder({"name": "A"}, user_id=user["id"], role=user["role"])["folder"]
        b = self.service.create_folder({"name": "B"}, user_id=user["id"], role=user["role"])["folder"]
        uploaded = self._upload(folder_id=a["id"], filename="doc.txt", content=b"data", user=user)["file"]
        moved = self.service.update_file(uploaded["id"], {"folder_id": b["id"]}, user_id=user["id"], role=user["role"])["file"]
        self.assertEqual(b["id"], moved["folder_id"])
        disk_path = self.store.file_disk_path(moved)
        self.assertTrue(disk_path.exists())
        self.assertEqual(b"data", disk_path.read_bytes())

    def test_rename_file(self):
        user = self._rw_user()
        uploaded = self._upload(folder_id=None, filename="a.txt", content=b"data", user=user)["file"]
        renamed = self.service.update_file(uploaded["id"], {"filename": "b.txt"}, user_id=user["id"], role=user["role"])["file"]
        self.assertEqual("b.txt", renamed["filename"])
        self.assertTrue(self.store.file_disk_path(renamed).exists())

    def test_delete_file_removes_disk_bytes_and_frees_quota(self):
        user = self._rwm_user()
        uploaded = self._upload(folder_id=None, filename="a.txt", content=b"x" * 500, user=user)["file"]
        disk_path = self.store.file_disk_path(uploaded)
        self.assertTrue(disk_path.exists())
        self.service.delete_file(uploaded["id"], user_id=user["id"], role=user["role"])
        self.assertFalse(disk_path.exists())
        self.assertEqual(0, self.store.get_quota_usage_bytes(user["id"]))

    def test_delete_folder_recursively_removes_descendants_and_frees_quota(self):
        user = self._rwm_user()
        parent = self.service.create_folder({"name": "Parent"}, user_id=user["id"], role=user["role"])["folder"]
        child = self.service.create_folder({"name": "Child", "parent_id": parent["id"]}, user_id=user["id"], role=user["role"])["folder"]
        self._upload(folder_id=child["id"], filename="a.txt", content=b"x" * 250, user=user)
        self._upload(folder_id=parent["id"], filename="b.txt", content=b"y" * 250, user=user)
        parent_disk = self.store.folder_disk_path(user["id"], parent["id"])

        result = self.service.delete_folder(parent["id"], user_id=user["id"], role=user["role"])
        self.assertTrue(result["deleted"])
        self.assertEqual(500, result["freed_bytes"])
        self.assertFalse(parent_disk.exists())
        self.assertEqual(0, self.store.get_quota_usage_bytes(user["id"]))
        self.assertIsNone(self.store.get_folder(child["id"]))

    # -- quota enforcement -------------------------------------------------

    def test_upload_rejected_when_exceeding_quota(self):
        user = self._rw_user()
        self.user_limits_store.update(user["id"], {"storage_quota_mb": 0})  # use global default
        self.admin_settings_store.update({"files": {"default_storage_quota_mb": 1}})  # 1MB quota
        with self.assertRaises(ValueError):
            self._upload(folder_id=None, filename="huge.bin", content=b"x" * (2 * 1024 * 1024), user=user)

    def test_upload_rejected_when_quota_already_exhausted(self):
        user = self._rw_user()
        self.admin_settings_store.update({"files": {"default_storage_quota_mb": 1}})
        self._upload(folder_id=None, filename="first.bin", content=b"x" * (900 * 1024), user=user)
        with self.assertRaises(ValueError):
            self._upload(folder_id=None, filename="second.bin", content=b"y" * (200 * 1024), user=user)

    def test_per_user_quota_override_takes_precedence_over_default(self):
        user = self._rw_user()
        self.admin_settings_store.update({"files": {"default_storage_quota_mb": 1}})
        self.user_limits_store.update(user["id"], {"storage_quota_mb": 10})  # 10MB override
        # This would exceed the 1MB default but fits comfortably under the 10MB override.
        content = b"x" * (3 * 1024 * 1024)
        result = self._upload(folder_id=None, filename="ok.bin", content=content, user=user)
        self.assertEqual(len(content), result["file"]["size_bytes"])

    def test_upload_rejected_when_exceeding_max_upload_size(self):
        user = self._rw_user()
        os.environ["JARVIS_FILES_MAX_UPLOAD_MB"] = "1"
        self.admin_settings_store.update({"files": {"default_storage_quota_mb": 100}})
        with self.assertRaises(ValueError):
            self._upload(folder_id=None, filename="toobig.bin", content=b"x" * (2 * 1024 * 1024), user=user)

    def test_failed_upload_does_not_leave_partial_file_or_charge_quota(self):
        user = self._rw_user()
        os.environ["JARVIS_FILES_MAX_UPLOAD_MB"] = "1"
        self.admin_settings_store.update({"files": {"default_storage_quota_mb": 100}})
        with self.assertRaises(ValueError):
            self._upload(folder_id=None, filename="toobig.bin", content=b"x" * (2 * 1024 * 1024), user=user)
        self.assertEqual(0, self.store.get_quota_usage_bytes(user["id"]))
        root = self.store.user_root_path(user["id"])
        leftovers = [p for p in root.iterdir() if p.name != "toobig.bin"]
        self.assertEqual([], leftovers, "temp upload file should be cleaned up on failure")
        self.assertFalse((root / "toobig.bin").exists())

    def test_quota_status_reports_used_and_total(self):
        user = self._rw_user()
        self.admin_settings_store.update({"files": {"default_storage_quota_mb": 5}})
        self._upload(folder_id=None, filename="a.bin", content=b"x" * 1000, user=user)
        status = self.service.quota_status(user_id=user["id"], role=user["role"])
        self.assertEqual(1000, status["used_bytes"])
        self.assertEqual(5 * 1024 * 1024, status["quota_bytes"])

    # -- path traversal via the service (the most important battery) ------

    def test_create_folder_rejects_traversal_name(self):
        user = self._rw_user()
        with self.assertRaises(ValueError):
            self.service.create_folder({"name": "../../etc/passwd"}, user_id=user["id"], role=user["role"])
        # nothing was created outside the user's storage root
        outside = Path(self.store.storage_root).parent / "etc"
        self.assertFalse(outside.exists())

    def test_create_folder_rejects_absolute_path_name(self):
        user = self._rw_user()
        with self.assertRaises(ValueError):
            self.service.create_folder({"name": "/etc/passwd"}, user_id=user["id"], role=user["role"])

    def test_create_folder_rejects_null_byte_name(self):
        user = self._rw_user()
        with self.assertRaises(ValueError):
            self.service.create_folder({"name": "evil\x00.txt"}, user_id=user["id"], role=user["role"])

    def test_create_folder_rejects_dotdot_only_name(self):
        user = self._rw_user()
        with self.assertRaises(ValueError):
            self.service.create_folder({"name": ".."}, user_id=user["id"], role=user["role"])

    def test_create_folder_rejects_windows_absolute_name(self):
        user = self._rw_user()
        with self.assertRaises(ValueError):
            self.service.create_folder({"name": "C:\\Windows\\System32"}, user_id=user["id"], role=user["role"])

    def test_upload_rejects_traversal_filename(self):
        user = self._rw_user()
        with self.assertRaises(ValueError):
            self._upload(folder_id=None, filename="../../etc/passwd", content=b"pwned", user=user)
        etc_dir = Path(self.store.storage_root).parent / "etc"
        self.assertFalse(etc_dir.exists())

    def test_upload_rejects_absolute_filename(self):
        user = self._rw_user()
        with self.assertRaises(ValueError):
            self._upload(folder_id=None, filename="/etc/passwd", content=b"pwned", user=user)

    def test_upload_rejects_null_byte_filename(self):
        user = self._rw_user()
        with self.assertRaises(ValueError):
            self._upload(folder_id=None, filename="../../etc/passwd\x00.png", content=b"pwned", user=user)

    def test_rename_folder_rejects_traversal_name(self):
        user = self._rw_user()
        folder = self.service.create_folder({"name": "Safe"}, user_id=user["id"], role=user["role"])["folder"]
        with self.assertRaises(ValueError):
            self.service.update_folder(folder["id"], {"name": "../../etc"}, user_id=user["id"], role=user["role"])
        # original directory must still be intact and untouched
        self.assertTrue(self.store.folder_disk_path(user["id"], folder["id"]).is_dir())

    def test_rename_file_rejects_traversal_name(self):
        user = self._rw_user()
        uploaded = self._upload(folder_id=None, filename="ok.txt", content=b"data", user=user)["file"]
        with self.assertRaises(ValueError):
            self.service.update_file(uploaded["id"], {"filename": "../../etc/passwd"}, user_id=user["id"], role=user["role"])
        self.assertTrue(self.store.file_disk_path(self.store.get_file(uploaded["id"])).exists())

    def test_move_folder_rejects_forged_parent_path_string(self):
        # parent_id is an opaque id, never a path — feeding it a path-like
        # string must be treated as "no such folder", not interpreted as a path.
        user = self._rw_user()
        folder = self.service.create_folder({"name": "Safe"}, user_id=user["id"], role=user["role"])["folder"]
        with self.assertRaises(LookupError):
            self.service.update_folder(folder["id"], {"parent_id": "../../etc"}, user_id=user["id"], role=user["role"])

    def test_download_path_always_resolves_inside_user_root(self):
        user = self._rw_user()
        uploaded = self._upload(folder_id=None, filename="secret.txt", content=b"classified", user=user)["file"]
        result = self.service.resolve_download(uploaded["id"], user_id=user["id"], role=user["role"])
        disk_path = result["disk_path"]
        user_root = self.store.user_root_path(user["id"]).resolve()
        self.assertTrue(str(disk_path.resolve()).startswith(str(user_root)))

    # -- cross-user isolation ----------------------------------------------

    def test_users_cannot_list_each_others_root(self):
        alice = self._rw_user("alice3")
        bob = self._rw_user("bob3")
        self.service.create_folder({"name": "AlicesSecrets"}, user_id=alice["id"], role=alice["role"])
        bob_listing = self.service.browse(None, user_id=bob["id"], role=bob["role"])
        self.assertEqual([], bob_listing["folders"])

    def test_users_cannot_reach_each_others_folder_by_crafted_id(self):
        alice = self._rw_user("alice4")
        bob = self._rwm_user("bob4")
        folder = self.service.create_folder({"name": "Private"}, user_id=alice["id"], role=alice["role"])["folder"]
        with self.assertRaises(LookupError):
            self.service.browse(folder["id"], user_id=bob["id"], role=bob["role"])
        with self.assertRaises(LookupError):
            self.service.update_folder(folder["id"], {"name": "Hijacked"}, user_id=bob["id"], role=bob["role"])
        with self.assertRaises(LookupError):
            self.service.delete_folder(folder["id"], user_id=bob["id"], role=bob["role"])

    def test_users_cannot_reach_each_others_file_by_crafted_id(self):
        alice = self._rw_user("alice5")
        bob = self._rwm_user("bob5")
        uploaded = self._upload(folder_id=None, filename="secret.txt", content=b"classified", user=alice)["file"]
        with self.assertRaises(LookupError):
            self.service.resolve_download(uploaded["id"], user_id=bob["id"], role=bob["role"])
        with self.assertRaises(LookupError):
            self.service.update_file(uploaded["id"], {"filename": "stolen.txt"}, user_id=bob["id"], role=bob["role"])
        with self.assertRaises(LookupError):
            self.service.delete_file(uploaded["id"], user_id=bob["id"], role=bob["role"])

    def test_users_cannot_upload_into_each_others_folder(self):
        alice = self._rw_user("alice6")
        bob = self._rw_user("bob6")
        folder = self.service.create_folder({"name": "AlicesFolder"}, user_id=alice["id"], role=alice["role"])["folder"]
        with self.assertRaises(LookupError):
            self._upload(folder_id=folder["id"], filename="intrusion.txt", content=b"x", user=bob)

    def test_admin_can_still_access_any_users_folder(self):
        admin = self.user_store.create_user("root-admin", role="admin", enabled=True)
        alice = self._rw_user("alice7")
        folder = self.service.create_folder({"name": "Private"}, user_id=alice["id"], role=alice["role"])["folder"]
        result = self.service.browse(folder["id"], user_id=admin["id"], role=admin["role"])
        self.assertEqual(folder["id"], result["parent_id"])

    # -- JARVIS per-folder access grant -------------------------------------

    def test_jarvis_access_defaults_to_false(self):
        user = self._rw_user()
        folder = self.service.create_folder({"name": "Project"}, user_id=user["id"], role=user["role"])["folder"]
        self.assertFalse(self.service.jarvis_can_access_folder(folder["id"]))

    def test_owner_can_grant_and_revoke_jarvis_access(self):
        user = self._rw_user()
        folder = self.service.create_folder({"name": "Project"}, user_id=user["id"], role=user["role"])["folder"]
        self.service.grant_jarvis_folder_access(folder["id"], user_id=user["id"], role=user["role"])
        self.assertTrue(self.service.jarvis_can_access_folder(folder["id"]))
        self.assertEqual("file_jarvis_access_granted", self.audit_probe.events[-1]["event"])

        self.service.revoke_jarvis_folder_access(folder["id"], user_id=user["id"], role=user["role"])
        self.assertFalse(self.service.jarvis_can_access_folder(folder["id"]))
        self.assertEqual("file_jarvis_access_revoked", self.audit_probe.events[-1]["event"])

    def test_other_user_cannot_toggle_jarvis_access(self):
        alice = self._rw_user("alice8")
        bob = self._rw_user("bob8")
        folder = self.service.create_folder({"name": "Project"}, user_id=alice["id"], role=alice["role"])["folder"]
        with self.assertRaises(LookupError):
            self.service.grant_jarvis_folder_access(folder["id"], user_id=bob["id"], role=bob["role"])
        self.assertFalse(self.service.jarvis_can_access_folder(folder["id"]))

    def test_admin_can_toggle_jarvis_access_on_behalf_of_user(self):
        admin = self.user_store.create_user("root-admin2", role="admin", enabled=True)
        alice = self._rw_user("alice9")
        folder = self.service.create_folder({"name": "Project"}, user_id=alice["id"], role=alice["role"])["folder"]
        self.service.grant_jarvis_folder_access(folder["id"], user_id=admin["id"], role=admin["role"])
        self.assertTrue(self.service.jarvis_can_access_folder(folder["id"]))

    def test_jarvis_access_is_per_folder_not_inherited(self):
        user = self._rw_user()
        parent = self.service.create_folder({"name": "Parent"}, user_id=user["id"], role=user["role"])["folder"]
        child = self.service.create_folder({"name": "Child", "parent_id": parent["id"]}, user_id=user["id"], role=user["role"])["folder"]
        self.service.grant_jarvis_folder_access(parent["id"], user_id=user["id"], role=user["role"])
        self.assertTrue(self.service.jarvis_can_access_folder(parent["id"]))
        self.assertFalse(self.service.jarvis_can_access_folder(child["id"]))

    # -- folder sharing via groups --------------------------------------

    def _share_via_group(self, owner, member_username, folder_id, permission):
        group = self.group_store.create_group(f"grp-{member_username}")
        member = self._rw_user(member_username)
        self.membership_store.add_membership(member["id"], group["id"])
        self.permission_store.set_user_permissions(owner["id"], ["files.read", "files.write", "files.manage", "files.share"])
        self.service.share_folder(folder_id, group["id"], permission, user_id=owner["id"], role=owner["role"])
        return member, group

    def test_folder_share_store_crud_and_duplicate_rejection(self):
        share = self.share_store.add_share("folder-1", "group-1", "read", "user-1")
        self.assertEqual([share], self.share_store.list_shares_for_folder("folder-1"))
        self.assertEqual([share], self.share_store.list_shares_for_group("group-1"))
        with self.assertRaises(ValueError):
            self.share_store.add_share("folder-1", "group-1", "write", "user-1")
        self.assertTrue(self.share_store.remove_share(share["id"]))
        self.assertEqual([], self.share_store.list_shares_for_folder("folder-1"))

    def test_membership_store_list_group_members_mirrors_list_user_groups(self):
        group = self.group_store.create_group("mirror-test")
        alice = self.user_store.create_user("mirror-alice", role="standard_user", enabled=True)
        bob = self.user_store.create_user("mirror-bob", role="standard_user", enabled=True)
        self.membership_store.add_membership(alice["id"], group["id"])
        self.membership_store.add_membership(bob["id"], group["id"])
        self.assertEqual({alice["id"], bob["id"]}, set(self.membership_store.list_group_members(group["id"])))

    def test_share_is_cascading_unlike_jarvis_grant(self):
        # Deliberate divergence from test_jarvis_access_is_per_folder_not_inherited above:
        # human-to-human folder sharing cascades to subfolders, the AI-agent grant does not.
        owner = self._rw_user("cascade-owner")
        parent = self.service.create_folder({"name": "Parent"}, user_id=owner["id"], role=owner["role"])["folder"]
        child = self.service.create_folder({"name": "Child", "parent_id": parent["id"]}, user_id=owner["id"], role=owner["role"])["folder"]
        member, _ = self._share_via_group(owner, "cascade-member", parent["id"], "read")
        result = self.service.browse(child["id"], user_id=member["id"], role=member["role"])
        self.assertEqual(child["id"], result["parent_id"])
        self.assertEqual("read", result["access"])

    def test_read_share_can_browse_and_download_but_not_write(self):
        owner = self._rw_user("read-owner")
        folder = self.service.create_folder({"name": "Docs"}, user_id=owner["id"], role=owner["role"])["folder"]
        uploaded = self._upload(folder_id=folder["id"], filename="a.txt", content=b"hi", user=owner)["file"]
        member, _ = self._share_via_group(owner, "read-member", folder["id"], "read")

        browsed = self.service.browse(folder["id"], user_id=member["id"], role=member["role"])
        self.assertEqual(1, len(browsed["files"]))
        download = self.service.resolve_download(uploaded["id"], user_id=member["id"], role=member["role"])
        self.assertTrue(download["disk_path"].is_file())

        with self.assertRaises(FileAccessError):
            self.service.create_folder({"name": "New", "parent_id": folder["id"]}, user_id=member["id"], role=member["role"])
        with self.assertRaises(FileAccessError):
            self._upload(folder_id=folder["id"], filename="intrusion.txt", content=b"x", user=member)
        with self.assertRaises(LookupError):
            self.service.update_folder(folder["id"], {"name": "Hijacked"}, user_id=member["id"], role=member["role"])
        # Grant files.manage too, so this specifically isolates the ownership check
        # (a write/read share never grants delete rights, regardless of global permission strings).
        self.permission_store.set_user_permissions(member["id"], ["files.read", "files.write", "files.manage"])
        with self.assertRaises(LookupError):
            self.service.delete_folder(folder["id"], user_id=member["id"], role=member["role"])

    def test_write_share_can_upload_and_create_subfolder_charged_to_owner(self):
        owner = self._rw_user("write-owner")
        folder = self.service.create_folder({"name": "Drop"}, user_id=owner["id"], role=owner["role"])["folder"]
        member, _ = self._share_via_group(owner, "write-member", folder["id"], "write")

        sub = self.service.create_folder({"name": "New", "parent_id": folder["id"]}, user_id=member["id"], role=member["role"])["folder"]
        self.assertEqual(owner["id"], sub["owner_user_id"])

        content = b"y" * 500
        uploaded = self._upload(folder_id=folder["id"], filename="dropped.txt", content=content, user=member)["file"]
        self.assertEqual(owner["id"], uploaded["owner_user_id"])
        self.assertEqual(500, self.store.get_quota_usage_bytes(owner["id"]))
        self.assertEqual(0, self.store.get_quota_usage_bytes(member["id"]))

    def test_user_in_no_relevant_group_gets_404_not_403(self):
        owner = self._rw_user("hidden-owner")
        outsider = self._rw_user("outsider")
        folder = self.service.create_folder({"name": "Secret"}, user_id=owner["id"], role=owner["role"])["folder"]
        with self.assertRaises(LookupError):
            self.service.browse(folder["id"], user_id=outsider["id"], role=outsider["role"])

    def test_only_owner_or_admin_can_manage_shares(self):
        owner = self._rw_user("share-owner")
        folder = self.service.create_folder({"name": "Team"}, user_id=owner["id"], role=owner["role"])["folder"]
        member, group = self._share_via_group(owner, "manage-member", folder["id"], "write")
        self.permission_store.set_user_permissions(member["id"], ["files.read", "files.write", "files.share"])
        other_group = self.group_store.create_group("re-share-target")
        with self.assertRaises(LookupError):
            self.service.share_folder(folder["id"], other_group["id"], "read", user_id=member["id"], role=member["role"])

    def test_delete_folder_cleans_up_share_rows_for_itself_and_descendants(self):
        owner = self._rw_user("cleanup-owner")
        parent = self.service.create_folder({"name": "Parent"}, user_id=owner["id"], role=owner["role"])["folder"]
        child = self.service.create_folder({"name": "Child", "parent_id": parent["id"]}, user_id=owner["id"], role=owner["role"])["folder"]
        self.permission_store.set_user_permissions(owner["id"], ["files.read", "files.write", "files.manage", "files.share"])
        group = self.group_store.create_group("cleanup-group")
        self.service.share_folder(parent["id"], group["id"], "read", user_id=owner["id"], role=owner["role"])
        self.service.share_folder(child["id"], group["id"], "write", user_id=owner["id"], role=owner["role"])

        self.service.delete_folder(parent["id"], user_id=owner["id"], role=owner["role"])
        self.assertEqual([], self.share_store.list_shares_for_folder(parent["id"]))
        self.assertEqual([], self.share_store.list_shares_for_folder(child["id"]))

    def test_files_share_permission_gate(self):
        owner = self._rw_user("gate-owner")
        folder = self.service.create_folder({"name": "Gated"}, user_id=owner["id"], role=owner["role"])["folder"]
        group = self.group_store.create_group("gate-group")
        with self.assertRaises(FileAccessError):
            self.service.share_folder(folder["id"], group["id"], "read", user_id=owner["id"], role=owner["role"])

    def test_receiving_end_of_share_only_needs_files_read(self):
        owner = self._rw_user("recv-owner")
        folder = self.service.create_folder({"name": "Recv"}, user_id=owner["id"], role=owner["role"])["folder"]
        group = self.group_store.create_group("recv-group")
        member = self.user_store.create_user("recv-member", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(member["id"], ["files.read"])
        self.membership_store.add_membership(member["id"], group["id"])
        self.permission_store.set_user_permissions(owner["id"], ["files.read", "files.write", "files.share"])
        self.service.share_folder(folder["id"], group["id"], "read", user_id=owner["id"], role=owner["role"])
        result = self.service.browse(folder["id"], user_id=member["id"], role=member["role"])
        self.assertEqual("read", result["access"])

    def test_list_my_groups_lists_every_group_not_just_own_memberships(self):
        # The share picker needs every group that exists — an owner can share with
        # a group they administer but aren't a member of (e.g. a "Kids" group).
        # Membership itself stays private; only id/name are ever returned.
        alice = self._rw_user("groups-alice")
        bob = self._rw_user("groups-bob")
        g1 = self.group_store.create_group("alice-group")
        g2 = self.group_store.create_group("bob-group")
        self.membership_store.add_membership(alice["id"], g1["id"])
        self.membership_store.add_membership(bob["id"], g2["id"])
        result = self.service.list_my_groups(user_id=alice["id"], role=alice["role"])
        self.assertEqual({"alice-group", "bob-group"}, {g["name"] for g in result["groups"]})
        self.assertEqual({"id", "name"}, set(result["groups"][0].keys()))

    def test_list_shared_with_me_only_shows_my_shares(self):
        owner = self._rw_user("visible-owner")
        folder = self.service.create_folder({"name": "Visible"}, user_id=owner["id"], role=owner["role"])["folder"]
        member, _ = self._share_via_group(owner, "visible-member", folder["id"], "read")
        outsider = self._rw_user("invisible-outsider")

        member_view = self.service.list_shared_with_me(user_id=member["id"], role=member["role"])
        self.assertEqual(1, len(member_view["shared"]))
        self.assertEqual("Visible", member_view["shared"][0]["folder"]["name"])
        self.assertEqual(owner["username"], member_view["shared"][0]["owner_username"])

        outsider_view = self.service.list_shared_with_me(user_id=outsider["id"], role=outsider["role"])
        self.assertEqual([], outsider_view["shared"])

    def test_unshare_removes_access_immediately(self):
        owner = self._rw_user("unshare-owner")
        folder = self.service.create_folder({"name": "Temp"}, user_id=owner["id"], role=owner["role"])["folder"]
        member, _ = self._share_via_group(owner, "unshare-member", folder["id"], "read")
        share_id = self.share_store.list_shares_for_folder(folder["id"])[0]["id"]

        self.service.browse(folder["id"], user_id=member["id"], role=member["role"])
        self.service.unshare_folder(share_id, user_id=owner["id"], role=owner["role"])
        with self.assertRaises(LookupError):
            self.service.browse(folder["id"], user_id=member["id"], role=member["role"])

    # -- emergency stop ------------------------------------------------------

    def test_emergency_stop_blocks_folder_creation(self):
        user = self._rw_user()
        os.environ["JARVIS_EMERGENCY_STOP"] = "1"
        with self.assertRaises(PermissionError):
            self.service.create_folder({"name": "Blocked"}, user_id=user["id"], role=user["role"])

    def test_emergency_stop_blocks_upload(self):
        user = self._rw_user()
        os.environ["JARVIS_EMERGENCY_STOP"] = "1"
        with self.assertRaises(PermissionError):
            self._upload(folder_id=None, filename="blocked.txt", content=b"x", user=user)

    def test_emergency_stop_blocks_delete(self):
        user = self._rwm_user()
        folder = self.service.create_folder({"name": "Temp"}, user_id=user["id"], role=user["role"])["folder"]
        os.environ["JARVIS_EMERGENCY_STOP"] = "1"
        with self.assertRaises(PermissionError):
            self.service.delete_folder(folder["id"], user_id=user["id"], role=user["role"])

    def test_emergency_stop_blocks_jarvis_grant(self):
        user = self._rw_user()
        folder = self.service.create_folder({"name": "Temp"}, user_id=user["id"], role=user["role"])["folder"]
        os.environ["JARVIS_EMERGENCY_STOP"] = "1"
        with self.assertRaises(PermissionError):
            self.service.grant_jarvis_folder_access(folder["id"], user_id=user["id"], role=user["role"])

    def test_emergency_stop_does_not_block_reads(self):
        user = self._rw_user()
        folder = self.service.create_folder({"name": "Readable"}, user_id=user["id"], role=user["role"])["folder"]
        os.environ["JARVIS_EMERGENCY_STOP"] = "1"
        result = self.service.browse(None, user_id=user["id"], role=user["role"])
        self.assertEqual(1, len(result["folders"]))


# ----------------------------------------------------------------------
# API-level tests via TestClient
# ----------------------------------------------------------------------


class FileApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(base, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_ADMIN_PASSWORD_STORE_PATH"] = os.path.join(base, "admin_passwords.json")
        os.environ["JARVIS_USER_PREFERENCES_PATH"] = os.path.join(base, "user_preferences.json")
        os.environ["JARVIS_FILES_STORE_PATH"] = os.path.join(base, "files_metadata.json")
        os.environ["JARVIS_USER_FILES_PATH"] = os.path.join(base, "user_files")
        os.environ["JARVIS_USER_LIMITS_STORE_PATH"] = os.path.join(base, "user_limits.json")
        os.environ["JARVIS_ADMIN_SETTINGS_PATH"] = os.path.join(base, "admin_settings.json")
        os.environ["JARVIS_FILES_SHARE_STORE_PATH"] = os.path.join(base, "files_shares.json")

        jarvisappv4.user_store = jarvisappv4.UserStore()
        jarvisappv4.group_store = jarvisappv4.GroupStore()
        jarvisappv4.membership_store = jarvisappv4.MembershipStore()
        jarvisappv4.permission_store = jarvisappv4.PermissionStore()
        jarvisappv4.admin_password_store = jarvisappv4.AdminPasswordStore()
        jarvisappv4.user_preferences_store = jarvisappv4.UserPreferencesStore()
        jarvisappv4.user_limits_store = jarvisappv4.UserLimitsStore()
        jarvisappv4.admin_settings_store = jarvisappv4.AdminSettingsStore()
        jarvisappv4.file_store = jarvisappv4.FileStore()
        jarvisappv4.folder_share_store = jarvisappv4.FolderShareStore()
        jarvisappv4.file_service = jarvisappv4.FileService(
            store=jarvisappv4.file_store,
            user_store=jarvisappv4.user_store,
            membership_store=jarvisappv4.membership_store,
            permission_store=jarvisappv4.permission_store,
            resolve_effective_permissions=jarvisappv4.resolve_effective_permissions,
            normalize_role=jarvisappv4.normalize_role,
            user_limits_store=jarvisappv4.user_limits_store,
            admin_settings_store=jarvisappv4.admin_settings_store,
            share_store=jarvisappv4.folder_share_store,
            group_store=jarvisappv4.group_store,
            audit_log=jarvisappv4.audit_log,
        )
        jarvisappv4._identity_tokens.clear()
        self.client = TestClient(jarvisappv4.app)

    def tearDown(self):
        os.environ.pop("JARVIS_FILES_SHARE_STORE_PATH", None)
        self.tmpdir.cleanup()

    def _create_user_with_permissions(self, admin_token, admin_id, username, permissions):
        created = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {admin_token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={"username": username, "role": "standard_user", "enabled": True, "password": f"{username}-pass"},
        )
        user_id = created.json()["id"]
        self.client.put(
            f"/admin/permissions/users/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={"permissions": permissions},
        )
        login = self.client.post("/auth/login", json={"username": username, "password": f"{username}-pass"})
        return user_id, login.json()["session_token"]

    def test_full_lifecycle_via_api(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "filesuser", ["files.read", "files.write", "files.manage"]
        )
        headers = {"X-Jarvis-Session": session_token}

        created = self.client.post("/files/folders", headers=headers, json={"name": "Documents"})
        self.assertEqual(200, created.status_code)
        folder = created.json()["folder"]

        upload = self.client.post(
            "/files/upload", headers=headers,
            files={"file": ("notes.txt", b"hello from jarvis", "text/plain")},
            data={"folder_id": folder["id"]},
        )
        self.assertEqual(200, upload.status_code)
        file_meta = upload.json()["file"]
        self.assertEqual("notes.txt", file_meta["filename"])
        self.assertEqual(17, file_meta["size_bytes"])

        browsed = self.client.get(f"/files/browse?parent_id={folder['id']}", headers=headers)
        self.assertEqual(200, browsed.status_code)
        self.assertEqual(1, len(browsed.json()["files"]))

        download = self.client.get(f"/files/{file_meta['id']}/download", headers=headers)
        self.assertEqual(200, download.status_code)
        self.assertEqual(b"hello from jarvis", download.content)

        renamed = self.client.patch(f"/files/{file_meta['id']}", headers=headers, json={"filename": "renamed.txt"})
        self.assertEqual(200, renamed.status_code)
        self.assertEqual("renamed.txt", renamed.json()["file"]["filename"])

        quota = self.client.get("/files/quota", headers=headers)
        self.assertEqual(200, quota.status_code)
        self.assertEqual(17, quota.json()["used_bytes"])

        grant = self.client.put(f"/files/folders/{folder['id']}/jarvis-access", headers=headers, json={"granted": True})
        self.assertEqual(200, grant.status_code)
        self.assertTrue(grant.json()["folder"]["jarvis_access_granted"])

        deleted_file = self.client.delete(f"/files/{file_meta['id']}", headers=headers)
        self.assertEqual(200, deleted_file.status_code)

        deleted_folder = self.client.delete(f"/files/folders/{folder['id']}", headers=headers)
        self.assertEqual(200, deleted_folder.status_code)
        self.assertTrue(deleted_folder.json()["deleted"])

    def test_permission_denied_returns_403(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(admin["token"], admin["user_id"], "noperm", [])
        denied = self.client.get("/files/browse", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(403, denied.status_code)

    def test_path_traversal_folder_name_returns_400(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "attacker", ["files.read", "files.write"]
        )
        headers = {"X-Jarvis-Session": session_token}
        response = self.client.post("/files/folders", headers=headers, json={"name": "../../etc/passwd"})
        self.assertEqual(400, response.status_code)

    def test_path_traversal_upload_filename_returns_400(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "attacker2", ["files.read", "files.write"]
        )
        headers = {"X-Jarvis-Session": session_token}
        response = self.client.post(
            "/files/upload", headers=headers,
            files={"file": ("../../etc/passwd", b"pwned", "text/plain")},
        )
        self.assertEqual(400, response.status_code)

    def test_cross_user_download_returns_404(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, alice_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "isoalice2", ["files.read", "files.write"]
        )
        _, bob_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "isobob2", ["files.read", "files.write"]
        )
        upload = self.client.post(
            "/files/upload", headers={"X-Jarvis-Session": alice_token},
            files={"file": ("secret.txt", b"alice only", "text/plain")},
        )
        file_id = upload.json()["file"]["id"]

        denied = self.client.get(f"/files/{file_id}/download", headers={"X-Jarvis-Session": bob_token})
        self.assertEqual(404, denied.status_code)

        bob_listing = self.client.get("/files/browse", headers={"X-Jarvis-Session": bob_token})
        self.assertEqual(0, len(bob_listing.json()["files"]))

    def test_admin_can_configure_default_quota_and_per_user_override(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        admin_headers = {"Authorization": f"Bearer {admin['token']}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin["user_id"]}

        settings_update = self.client.put("/admin/settings", headers=admin_headers, json={"files": {"default_storage_quota_mb": 42}})
        self.assertEqual(200, settings_update.status_code)
        self.assertEqual(42, settings_update.json()["settings"]["files"]["default_storage_quota_mb"])

        user_id, session_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "quotauser", ["files.read", "files.write"]
        )
        limits_update = self.client.put(f"/admin/users/{user_id}/limits", headers=admin_headers, json={"storage_quota_mb": 7})
        self.assertEqual(200, limits_update.status_code)
        self.assertEqual(7, limits_update.json()["storage_quota_mb"])

        quota = self.client.get("/files/quota", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, quota.status_code)
        self.assertEqual(7 * 1024 * 1024, quota.json()["quota_bytes"])

    def test_chat_skill_reads_granted_folder_via_real_http_request(self):
        # End-to-end regression test for the /chat -> try_skill(user_id=...) wiring.
        # Before that fix, effective_user_id was resolved in the chat handler but
        # never forwarded into try_skill(), so a per-user skill like this one could
        # never resolve "my" folders through the real HTTP path — only a direct,
        # unit-level try_skill() call (with user_id passed by hand) would work.
        # This test goes through the real app + a real session token instead.
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "chatfilesuser", ["files.read", "files.write"]
        )
        headers = {"X-Jarvis-Session": session_token}

        created = self.client.post("/files/folders", headers=headers, json={"name": "Reports"})
        self.assertEqual(200, created.status_code)
        folder = created.json()["folder"]

        upload = self.client.post(
            "/files/upload", headers=headers,
            files={"file": ("q1.txt", b"quarterly numbers", "text/plain")},
            data={"folder_id": folder["id"]},
        )
        self.assertEqual(200, upload.status_code)

        grant = self.client.put(f"/files/folders/{folder['id']}/jarvis-access", headers=headers, json={"granted": True})
        self.assertEqual(200, grant.status_code)
        self.assertTrue(grant.json()["folder"]["jarvis_access_granted"])

        chat = self.client.post("/chat", headers=headers, json={"text": "what's in my Reports folder"})
        self.assertEqual(200, chat.status_code)
        body = chat.json()
        self.assertEqual("file_drive_list", body["data"]["route"])
        self.assertIn("q1.txt", body["reply"])

    def _create_group(self, admin_token, admin_id, name):
        resp = self.client.post(
            "/admin/groups",
            headers={"Authorization": f"Bearer {admin_token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={"name": name},
        )
        self.assertEqual(200, resp.status_code, resp.text)
        return resp.json()["id"]

    def _assign_group(self, admin_token, admin_id, user_id, group_id):
        resp = self.client.post(
            "/admin/assignments",
            headers={"Authorization": f"Bearer {admin_token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={"user_id": user_id, "group_id": group_id},
        )
        self.assertEqual(200, resp.status_code, resp.text)

    def test_share_folder_lifecycle_via_api(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        admin_token, admin_id = admin["token"], admin["user_id"]

        owner_id, owner_token = self._create_user_with_permissions(
            admin_token, admin_id, "api-owner", ["files.read", "files.write", "files.share"]
        )
        member_id, member_token = self._create_user_with_permissions(
            admin_token, admin_id, "api-member", ["files.read", "files.write"]
        )
        group_id = self._create_group(admin_token, admin_id, "api-team")
        self._assign_group(admin_token, admin_id, member_id, group_id)

        owner_headers = {"X-Jarvis-Session": owner_token}
        member_headers = {"X-Jarvis-Session": member_token}

        folder = self.client.post("/files/folders", headers=owner_headers, json={"name": "Team Drop"}).json()["folder"]

        my_groups = self.client.get("/files/my-groups", headers=member_headers)
        self.assertEqual(200, my_groups.status_code)
        self.assertEqual(["api-team"], [g["name"] for g in my_groups.json()["groups"]])

        share = self.client.post(
            f"/files/folders/{folder['id']}/shares", headers=owner_headers,
            json={"group_id": group_id, "permission": "write"},
        )
        self.assertEqual(200, share.status_code, share.text)
        share_id = share.json()["share"]["id"]

        shared_with_me = self.client.get("/files/shared-with-me", headers=member_headers)
        self.assertEqual(200, shared_with_me.status_code)
        self.assertEqual(1, len(shared_with_me.json()["shared"]))
        self.assertEqual("write", shared_with_me.json()["shared"][0]["access"])

        browse_as_member = self.client.get(f"/files/browse?parent_id={folder['id']}", headers=member_headers)
        self.assertEqual(200, browse_as_member.status_code)
        self.assertEqual("write", browse_as_member.json()["access"])
        self.assertEqual("api-owner", browse_as_member.json()["owner_username"])

        upload = self.client.post(
            "/files/upload", headers=member_headers,
            files={"file": ("notes.txt", b"team notes", "text/plain")},
            data={"folder_id": folder["id"]},
        )
        self.assertEqual(200, upload.status_code, upload.text)
        self.assertEqual(owner_id, upload.json()["file"]["owner_user_id"])

        shares_list = self.client.get(f"/files/folders/{folder['id']}/shares", headers=owner_headers)
        self.assertEqual(200, shares_list.status_code)
        self.assertEqual(1, len(shares_list.json()["shares"]))
        self.assertEqual("api-team", shares_list.json()["shares"][0]["group_name"])

        unshare = self.client.delete(f"/files/shares/{share_id}", headers=owner_headers)
        self.assertEqual(200, unshare.status_code)

        after_unshare = self.client.get(f"/files/browse?parent_id={folder['id']}", headers=member_headers)
        self.assertEqual(404, after_unshare.status_code)

    def test_non_owner_cannot_manage_shares_via_api(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        admin_token, admin_id = admin["token"], admin["user_id"]
        owner_id, owner_token = self._create_user_with_permissions(
            admin_token, admin_id, "own-owner", ["files.read", "files.write", "files.share"]
        )
        outsider_id, outsider_token = self._create_user_with_permissions(
            admin_token, admin_id, "own-outsider", ["files.read", "files.write", "files.share"]
        )
        folder = self.client.post("/files/folders", headers={"X-Jarvis-Session": owner_token}, json={"name": "Mine"}).json()["folder"]
        group_id = self._create_group(admin_token, admin_id, "own-group")

        resp = self.client.post(
            f"/files/folders/{folder['id']}/shares", headers={"X-Jarvis-Session": outsider_token},
            json={"group_id": group_id, "permission": "read"},
        )
        self.assertEqual(404, resp.status_code)


if __name__ == "__main__":
    unittest.main()
