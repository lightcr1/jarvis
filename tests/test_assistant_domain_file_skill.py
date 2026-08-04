from __future__ import annotations

import asyncio
import os
import tempfile
import unittest

from jarvis.admin_settings_store import AdminSettingsStore
from jarvis.assistant_domain import try_skill
from jarvis.authz import resolve_effective_permissions
from jarvis.files.service import FileService
from jarvis.files.store import FileStore
from jarvis.jarvis_engine import normalize_role
from jarvis.membership_store import MembershipStore
from jarvis.permission_store import PermissionStore
from jarvis.user_limits_store import UserLimitsStore
from jarvis.user_store import UserStore


class _BytesReader:
    def __init__(self, data: bytes, chunk_size: int = 64):
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


def _run_skill(text: str, *, file_service, user_id: str) -> dict | None:
    return try_skill(
        text,
        role="standard_user",
        token=None,
        granted_permissions=[],
        emergency_stop_enabled=lambda: False,
        permission_check=lambda *_a, **_k: True,
        run_cmd=lambda *_a, **_k: "active",
        disk_usage=lambda *_a: None,
        format_bytes=lambda v: f"{v}B",
        parse_meminfo=lambda: {},
        parse_ping=lambda _o: {},
        tail_lines=lambda t, max_lines=6: t,
        ensure_service_allowed=lambda _s: None,
        proxmox_vm_status=lambda *_a: {},
        proxmox_lxc_status=lambda *_a: {},
        proxmox_vm_action=lambda *_a: {},
        proxmox_lxc_action=lambda *_a: {},
        user_id=user_id,
        file_service=file_service,
    )


class FileDriveSkillTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_FILES_STORE_PATH"] = os.path.join(base, "files_metadata.json")
        os.environ["JARVIS_USER_FILES_PATH"] = os.path.join(base, "user_files")
        os.environ["JARVIS_USER_LIMITS_STORE_PATH"] = os.path.join(base, "user_limits.json")
        os.environ["JARVIS_ADMIN_SETTINGS_PATH"] = os.path.join(base, "admin_settings.json")

        self.user_store = UserStore()
        self.membership_store = MembershipStore()
        self.permission_store = PermissionStore()
        self.store = FileStore()
        self.user_limits_store = UserLimitsStore()
        self.admin_settings_store = AdminSettingsStore()
        self.service = FileService(
            store=self.store,
            user_store=self.user_store,
            membership_store=self.membership_store,
            permission_store=self.permission_store,
            resolve_effective_permissions=resolve_effective_permissions,
            normalize_role=normalize_role,
            user_limits_store=self.user_limits_store,
            admin_settings_store=self.admin_settings_store,
            audit_log=None,
        )

    def tearDown(self):
        for key in (
            "JARVIS_USER_STORE_PATH", "JARVIS_MEMBERSHIP_STORE_PATH", "JARVIS_PERMISSION_STORE_PATH",
            "JARVIS_FILES_STORE_PATH", "JARVIS_USER_FILES_PATH", "JARVIS_USER_LIMITS_STORE_PATH",
            "JARVIS_ADMIN_SETTINGS_PATH",
        ):
            os.environ.pop(key, None)
        self.tmpdir.cleanup()

    def _rw_user(self, username="alice", extra_perms=()):
        user = self.user_store.create_user(username, role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["files.read", "files.write", *extra_perms])
        return user

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
        )["file"]

    def test_granted_folder_listing_shows_files(self):
        user = self._rw_user()
        folder = self.service.create_folder({"name": "Reports"}, user_id=user["id"], role=user["role"])["folder"]
        self.service.grant_jarvis_folder_access(folder["id"], user_id=user["id"], role=user["role"])
        self._upload(folder_id=folder["id"], filename="q1.txt", content=b"quarterly numbers", user=user)
        self._upload(folder_id=folder["id"], filename="q2.txt", content=b"more numbers", user=user)

        result = _run_skill("what's in my Reports folder", file_service=self.service, user_id=user["id"])
        self.assertIsNotNone(result)
        self.assertEqual("file_drive_list", result["data"]["route"])
        self.assertIn("q1.txt", result["reply"])
        self.assertIn("q2.txt", result["reply"])

    def test_granted_folder_read_returns_text_content(self):
        user = self._rw_user()
        folder = self.service.create_folder({"name": "Reports"}, user_id=user["id"], role=user["role"])["folder"]
        self.service.grant_jarvis_folder_access(folder["id"], user_id=user["id"], role=user["role"])
        self._upload(folder_id=folder["id"], filename="notes.txt", content=b"hello from the file drive", user=user)

        result = _run_skill("read notes.txt in my Reports folder", file_service=self.service, user_id=user["id"])
        self.assertIsNotNone(result)
        self.assertEqual("file_drive_read", result["data"]["route"])
        self.assertIn("hello from the file drive", result["reply"])

    def test_non_granted_folder_returns_denial(self):
        user = self._rw_user()
        self.service.create_folder({"name": "Private"}, user_id=user["id"], role=user["role"])["folder"]

        result = _run_skill("what's in my Private folder", file_service=self.service, user_id=user["id"])
        self.assertIsNotNone(result)
        self.assertEqual("not_granted", result["data"]["error"])
        # try_skill lowercases input before routing, so the folder name echoed
        # back in the denial is lowercase regardless of how it was typed.
        self.assertEqual(
            "I don't have access to a folder called 'private'. You can grant it from the Files screen.",
            result["reply"],
        )

    def test_nonexistent_and_non_granted_denials_are_byte_identical(self):
        # Same folder name in both cases — one user has it (ungranted), the
        # other doesn't have it at all. Security-critical: a chat user must
        # not be able to distinguish "exists but not granted" from "does not
        # exist" via the reply text, since that would let them probe for
        # folder names they can't see.
        owner = self._rw_user("alice")
        self.service.create_folder({"name": "Secret"}, user_id=owner["id"], role=owner["role"])
        non_granted_reply = _run_skill("what's in my Secret folder", file_service=self.service, user_id=owner["id"])["reply"]

        stranger = self._rw_user("bob")
        nonexistent_reply = _run_skill("what's in my Secret folder", file_service=self.service, user_id=stranger["id"])["reply"]

        self.assertEqual(non_granted_reply, nonexistent_reply)

    def test_child_folder_of_granted_parent_is_still_denied(self):
        user = self._rw_user()
        parent = self.service.create_folder({"name": "Parent"}, user_id=user["id"], role=user["role"])["folder"]
        self.service.create_folder({"name": "Child", "parent_id": parent["id"]}, user_id=user["id"], role=user["role"])
        self.service.grant_jarvis_folder_access(parent["id"], user_id=user["id"], role=user["role"])

        result = _run_skill("what's in my Child folder", file_service=self.service, user_id=user["id"])
        self.assertIsNotNone(result)
        self.assertEqual("not_granted", result["data"]["error"])
        self.assertEqual(
            "I don't have access to a folder called 'child'. You can grant it from the Files screen.",
            result["reply"],
        )

    def test_conversational_prefix_still_matches_single_folder_listing(self):
        # Real user report: "okey tell me whats in this Reports folder" — a
        # conversational lead-in plus "this" instead of "my" — used to fall
        # through to the LLM (which hallucinated), since the old patterns
        # were anchored at the very start of the message.
        user = self._rw_user()
        folder = self.service.create_folder({"name": "Reports"}, user_id=user["id"], role=user["role"])["folder"]
        self.service.grant_jarvis_folder_access(folder["id"], user_id=user["id"], role=user["role"])
        self._upload(folder_id=folder["id"], filename="q1.txt", content=b"quarterly numbers", user=user)

        result = _run_skill("okey tell me whats in this Reports folder", file_service=self.service, user_id=user["id"])
        self.assertIsNotNone(result)
        self.assertEqual("file_drive_list", result["data"]["route"])
        self.assertIn("q1.txt", result["reply"])

    def test_list_all_granted_folders(self):
        user = self._rw_user()
        reports = self.service.create_folder({"name": "Reports"}, user_id=user["id"], role=user["role"])["folder"]
        photos = self.service.create_folder({"name": "Photos"}, user_id=user["id"], role=user["role"])["folder"]
        self.service.grant_jarvis_folder_access(reports["id"], user_id=user["id"], role=user["role"])
        self.service.grant_jarvis_folder_access(photos["id"], user_id=user["id"], role=user["role"])
        self._upload(folder_id=reports["id"], filename="q1.txt", content=b"numbers", user=user)

        result = _run_skill("tell me whats in this folders", file_service=self.service, user_id=user["id"])
        self.assertIsNotNone(result)
        self.assertEqual("file_drive_list_all", result["data"]["route"])
        self.assertIn("Reports", result["reply"])
        self.assertIn("Photos", result["reply"])

    def test_list_all_granted_folders_when_none_granted(self):
        user = self._rw_user()
        self.service.create_folder({"name": "Private"}, user_id=user["id"], role=user["role"])

        result = _run_skill("what folders do i have", file_service=self.service, user_id=user["id"])
        self.assertIsNotNone(result)
        self.assertEqual([], result["data"]["folders"])

    def test_binary_file_content_refused_but_listed(self):
        user = self._rw_user()
        folder = self.service.create_folder({"name": "Media"}, user_id=user["id"], role=user["role"])["folder"]
        self.service.grant_jarvis_folder_access(folder["id"], user_id=user["id"], role=user["role"])
        self._upload(
            folder_id=folder["id"], filename="photo.png", content=b"\x89PNG\r\n\x1a\nnot-really-a-png",
            user=user, content_type="image/png",
        )

        listing = _run_skill("what's in my Media folder", file_service=self.service, user_id=user["id"])
        self.assertIn("photo.png", listing["reply"])

        read_result = _run_skill("read photo.png in my Media folder", file_service=self.service, user_id=user["id"])
        self.assertEqual("file_drive_read_refused", read_result["data"]["route"])
        self.assertEqual(
            "I can see that file but can't read its content aloud — it's not a text file.",
            read_result["reply"],
        )


if __name__ == "__main__":
    unittest.main()
