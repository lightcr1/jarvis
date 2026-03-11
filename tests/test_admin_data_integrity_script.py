import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class AdminDataIntegrityScriptTests(unittest.TestCase):
    def _env(self, root: Path):
        env = os.environ.copy()
        env.update(
            {
                "JARVIS_AUDIT_LOG_PATH": str(root / "audit.log"),
                "JARVIS_USER_STORE_PATH": str(root / "users.json"),
                "JARVIS_GROUP_STORE_PATH": str(root / "groups.json"),
                "JARVIS_MEMBERSHIP_STORE_PATH": str(root / "memberships.json"),
                "JARVIS_PERMISSION_STORE_PATH": str(root / "permissions.json"),
            }
        )
        return env

    def _seed_valid_files(self, root: Path):
        (root / "users.json").write_text(json.dumps({"users": {}}), encoding="utf-8")
        (root / "groups.json").write_text(json.dumps({"groups": {}}), encoding="utf-8")
        (root / "memberships.json").write_text(json.dumps({"memberships": []}), encoding="utf-8")
        (root / "permissions.json").write_text(json.dumps({"group_permissions": {}, "user_permissions": {}}), encoding="utf-8")
        (root / "audit.log").write_text("", encoding="utf-8")

    def test_integrity_script_passes_on_valid_data(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=self._env(root),
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertIn("Admin data integrity OK", proc.stdout)

    def test_integrity_script_fails_on_invalid_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text("{bad json", encoding="utf-8")
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=self._env(root),
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("Invalid JSON", proc.stdout + proc.stderr)

    def test_integrity_script_fails_on_invalid_role_assignments(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(
                json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "superadmin", "enabled": True}}}),
                encoding="utf-8",
            )
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=self._env(root),
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 4)
            self.assertIn("Invalid role assignments", proc.stdout + proc.stderr)

    def test_integrity_script_fails_on_invalid_permissions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "permissions.json").write_text(
                json.dumps({"group_permissions": {"grp-1": ["permission.unknown"]}, "user_permissions": {}}),
                encoding="utf-8",
            )
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=self._env(root),
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 4)
            self.assertIn("Invalid permission assignments detected", proc.stdout + proc.stderr)

    def test_integrity_script_can_fail_on_duplicate_gate_with_non_dict_membership_entry(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(
                json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "admin", "enabled": True}}}),
                encoding="utf-8",
            )
            (root / "groups.json").write_text(
                json.dumps({"groups": {"grp-1": {"id": "grp-1", "name": "ops"}}}),
                encoding="utf-8",
            )
            (root / "memberships.json").write_text(
                json.dumps({"memberships": ["not-a-membership-object"]}),
                encoding="utf-8",
            )
            env = self._env(root)
            env["JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS"] = "1"
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 8)
            self.assertIn("duplicate or malformed memberships", proc.stdout + proc.stderr)

    def test_integrity_script_can_fail_on_duplicate_gate_with_empty_user_id(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(
                json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "admin", "enabled": True}}}),
                encoding="utf-8",
            )
            (root / "groups.json").write_text(
                json.dumps({"groups": {"grp-1": {"id": "grp-1", "name": "ops"}}}),
                encoding="utf-8",
            )
            (root / "memberships.json").write_text(
                json.dumps({"memberships": [{"user_id": "", "group_id": "grp-1"}]}),
                encoding="utf-8",
            )
            env = self._env(root)
            env["JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS"] = "1"
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 8)
            self.assertIn("duplicate or malformed memberships", proc.stdout + proc.stderr)

    def test_integrity_script_can_fail_on_duplicate_gate_with_none_group_id(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(
                json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "admin", "enabled": True}}}),
                encoding="utf-8",
            )
            (root / "groups.json").write_text(
                json.dumps({"groups": {"grp-1": {"id": "grp-1", "name": "ops"}}}),
                encoding="utf-8",
            )
            (root / "memberships.json").write_text(
                json.dumps({"memberships": [{"user_id": "usr-1", "group_id": None}]}),
                encoding="utf-8",
            )
            env = self._env(root)
            env["JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS"] = "1"
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 8)
            self.assertIn("duplicate or malformed memberships", proc.stdout + proc.stderr)

    def test_integrity_script_can_fail_on_duplicate_gate_with_none_user_id(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(
                json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "admin", "enabled": True}}}),
                encoding="utf-8",
            )
            (root / "groups.json").write_text(
                json.dumps({"groups": {"grp-1": {"id": "grp-1", "name": "ops"}}}),
                encoding="utf-8",
            )
            (root / "memberships.json").write_text(
                json.dumps({"memberships": [{"user_id": None, "group_id": "grp-1"}]}),
                encoding="utf-8",
            )
            env = self._env(root)
            env["JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS"] = "1"
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 8)
            self.assertIn("duplicate or malformed memberships", proc.stdout + proc.stderr)

    def test_integrity_script_can_fail_on_duplicate_gate_with_non_string_group_id(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(
                json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "admin", "enabled": True}}}),
                encoding="utf-8",
            )
            (root / "groups.json").write_text(
                json.dumps({"groups": {"grp-1": {"id": "grp-1", "name": "ops"}}}),
                encoding="utf-8",
            )
            (root / "memberships.json").write_text(
                json.dumps({"memberships": [{"user_id": "usr-1", "group_id": 456}]}),
                encoding="utf-8",
            )
            env = self._env(root)
            env["JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS"] = "1"
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 8)
            self.assertIn("duplicate or malformed memberships", proc.stdout + proc.stderr)

    def test_integrity_script_can_fail_on_duplicate_gate_with_non_string_user_id(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(
                json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "admin", "enabled": True}}}),
                encoding="utf-8",
            )
            (root / "groups.json").write_text(
                json.dumps({"groups": {"grp-1": {"id": "grp-1", "name": "ops"}}}),
                encoding="utf-8",
            )
            (root / "memberships.json").write_text(
                json.dumps({"memberships": [{"user_id": 123, "group_id": "grp-1"}]}),
                encoding="utf-8",
            )
            env = self._env(root)
            env["JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS"] = "1"
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 8)
            self.assertIn("duplicate or malformed memberships", proc.stdout + proc.stderr)

    def test_integrity_script_can_fail_on_duplicate_gate_with_empty_group_id(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(
                json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "admin", "enabled": True}}}),
                encoding="utf-8",
            )
            (root / "groups.json").write_text(
                json.dumps({"groups": {"grp-1": {"id": "grp-1", "name": "ops"}}}),
                encoding="utf-8",
            )
            (root / "memberships.json").write_text(
                json.dumps({"memberships": [{"user_id": "usr-1", "group_id": ""}]}),
                encoding="utf-8",
            )
            env = self._env(root)
            env["JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS"] = "1"
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 8)
            self.assertIn("duplicate or malformed memberships", proc.stdout + proc.stderr)

    def test_integrity_script_can_fail_on_duplicate_gate_with_whitespace_group_id(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(
                json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "admin", "enabled": True}}}),
                encoding="utf-8",
            )
            (root / "groups.json").write_text(
                json.dumps({"groups": {"grp-1": {"id": "grp-1", "name": "ops"}}}),
                encoding="utf-8",
            )
            (root / "memberships.json").write_text(
                json.dumps({"memberships": [{"user_id": "usr-1", "group_id": "   "}]}),
                encoding="utf-8",
            )
            env = self._env(root)
            env["JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS"] = "1"
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 8)
            self.assertIn("duplicate or malformed memberships", proc.stdout + proc.stderr)

    def test_integrity_script_can_fail_on_duplicate_gate_with_whitespace_user_id(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(
                json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "admin", "enabled": True}}}),
                encoding="utf-8",
            )
            (root / "groups.json").write_text(
                json.dumps({"groups": {"grp-1": {"id": "grp-1", "name": "ops"}}}),
                encoding="utf-8",
            )
            (root / "memberships.json").write_text(
                json.dumps({"memberships": [{"user_id": "   ", "group_id": "grp-1"}]}),
                encoding="utf-8",
            )
            env = self._env(root)
            env["JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS"] = "1"
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 8)
            self.assertIn("duplicate or malformed memberships", proc.stdout + proc.stderr)

    def test_integrity_script_can_fail_on_duplicate_gate_with_malformed_membership_shape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(
                json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "admin", "enabled": True}}}),
                encoding="utf-8",
            )
            (root / "groups.json").write_text(
                json.dumps({"groups": {"grp-1": {"id": "grp-1", "name": "ops"}}}),
                encoding="utf-8",
            )
            (root / "memberships.json").write_text(
                json.dumps({"memberships": [{"user_id": "usr-1"}]}),
                encoding="utf-8",
            )
            env = self._env(root)
            env["JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS"] = "1"
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 8)
            self.assertIn("duplicate or malformed memberships", proc.stdout + proc.stderr)

    def test_integrity_script_can_fail_on_duplicate_memberships(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(
                json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "admin", "enabled": True}}}),
                encoding="utf-8",
            )
            (root / "groups.json").write_text(
                json.dumps({"groups": {"grp-1": {"id": "grp-1", "name": "ops"}}}),
                encoding="utf-8",
            )
            (root / "memberships.json").write_text(
                json.dumps({"memberships": [
                    {"user_id": "usr-1", "group_id": "grp-1"},
                    {"user_id": "usr-1", "group_id": "grp-1"}
                ]}),
                encoding="utf-8",
            )
            env = self._env(root)
            env["JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS"] = "1"
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 8)
            self.assertIn("duplicate or malformed memberships", proc.stdout + proc.stderr)

    def test_integrity_script_warns_on_duplicate_memberships(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(
                json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "admin", "enabled": True}}}),
                encoding="utf-8",
            )
            (root / "groups.json").write_text(
                json.dumps({"groups": {"grp-1": {"id": "grp-1", "name": "ops"}}}),
                encoding="utf-8",
            )
            (root / "memberships.json").write_text(
                json.dumps({"memberships": [
                    {"user_id": "usr-1", "group_id": "grp-1"},
                    {"user_id": "usr-1", "group_id": "grp-1"}
                ]}),
                encoding="utf-8",
            )
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=self._env(root),
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertIn("duplicate or malformed memberships", proc.stdout + proc.stderr)

    def test_integrity_script_fallback_constants_when_runtime_imports_unavailable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            script_path = Path("scripts/check_admin_data_integrity.sh").resolve()
            env = self._env(root)
            env["PYTHONPATH"] = str(root)

            proc = subprocess.run(
                ["bash", str(script_path)],
                env=env,
                cwd=root,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertIn("Admin data integrity OK", proc.stdout + proc.stderr)

    def test_integrity_script_warns_on_malformed_membership_records(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(
                json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "admin", "enabled": True}}}),
                encoding="utf-8",
            )
            (root / "groups.json").write_text(
                json.dumps({"groups": {"grp-1": {"id": "grp-1", "name": "ops"}}}),
                encoding="utf-8",
            )
            (root / "memberships.json").write_text(
                json.dumps({"memberships": [
                    {"user_id": "usr-1", "group_id": "grp-1"},
                    "not-a-membership-object"
                ]}),
                encoding="utf-8",
            )
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=self._env(root),
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertIn("duplicate or malformed memberships", proc.stdout + proc.stderr)

    def test_integrity_script_fallback_constants_still_reject_invalid_permission(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            script_path = Path("scripts/check_admin_data_integrity.sh").resolve()
            env = self._env(root)
            env["PYTHONPATH"] = str(root)
            (root / "permissions.json").write_text(
                json.dumps({"group_permissions": {"grp-1": ["permission.unknown"]}, "user_permissions": {}}),
                encoding="utf-8",
            )

            proc = subprocess.run(
                ["bash", str(script_path)],
                env=env,
                cwd=root,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 4)
            self.assertIn("Invalid permission assignments detected", proc.stdout + proc.stderr)

    def test_integrity_script_warns_on_admin_lockout_risk(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(
                json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "admin", "enabled": True}}}),
                encoding="utf-8",
            )
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=self._env(root),
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertIn("WARNING: only one enabled admin user found", proc.stdout + proc.stderr)

    def test_integrity_script_can_fail_on_admin_lockout(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            env = self._env(root)
            env["JARVIS_INTEGRITY_FAIL_ON_ADMIN_LOCKOUT"] = "1"
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 7)
            self.assertIn("WARNING: no enabled admin users found", proc.stdout + proc.stderr)

    def test_integrity_script_warns_on_orphans_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "admin", "enabled": True}}}), encoding="utf-8")
            (root / "groups.json").write_text(json.dumps({"groups": {}}), encoding="utf-8")
            (root / "memberships.json").write_text(json.dumps({"memberships": [{"user_id": "usr-1", "group_id": "grp-missing"}]}), encoding="utf-8")
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=self._env(root),
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertIn("WARNING: orphan admin data references detected", proc.stdout + proc.stderr)

    def test_integrity_script_warns_on_malformed_membership_shape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(
                json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "admin", "enabled": True}}}),
                encoding="utf-8",
            )
            (root / "groups.json").write_text(
                json.dumps({"groups": {"grp-1": {"id": "grp-1", "name": "ops"}}}),
                encoding="utf-8",
            )
            (root / "memberships.json").write_text(
                json.dumps({"memberships": [{"user_id": "usr-1"}]}),
                encoding="utf-8",
            )
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=self._env(root),
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertIn("duplicate or malformed memberships", proc.stdout + proc.stderr)

    def test_integrity_script_can_fail_on_orphans_with_whitespace_group_id(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(
                json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "admin", "enabled": True}}}),
                encoding="utf-8",
            )
            (root / "groups.json").write_text(
                json.dumps({"groups": {"grp-1": {"id": "grp-1", "name": "ops"}}}),
                encoding="utf-8",
            )
            (root / "memberships.json").write_text(
                json.dumps({"memberships": [{"user_id": "usr-1", "group_id": "   "}]}),
                encoding="utf-8",
            )
            env = self._env(root)
            env["JARVIS_INTEGRITY_FAIL_ON_ORPHANS"] = "1"
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 6)
            self.assertIn("WARNING: orphan admin data references detected", proc.stdout + proc.stderr)
            self.assertIn("malformed memberships", proc.stdout + proc.stderr)

    def test_integrity_script_can_fail_on_orphans_with_whitespace_membership_ids(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(
                json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "admin", "enabled": True}}}),
                encoding="utf-8",
            )
            (root / "groups.json").write_text(
                json.dumps({"groups": {"grp-1": {"id": "grp-1", "name": "ops"}}}),
                encoding="utf-8",
            )
            (root / "memberships.json").write_text(
                json.dumps({"memberships": [{"user_id": "   ", "group_id": "grp-1"}]}),
                encoding="utf-8",
            )
            env = self._env(root)
            env["JARVIS_INTEGRITY_FAIL_ON_ORPHANS"] = "1"
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 6)
            self.assertIn("WARNING: orphan admin data references detected", proc.stdout + proc.stderr)
            self.assertIn("malformed memberships", proc.stdout + proc.stderr)

    def test_integrity_script_can_fail_on_orphans_with_empty_membership_ids(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(
                json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "admin", "enabled": True}}}),
                encoding="utf-8",
            )
            (root / "groups.json").write_text(
                json.dumps({"groups": {"grp-1": {"id": "grp-1", "name": "ops"}}}),
                encoding="utf-8",
            )
            (root / "memberships.json").write_text(
                json.dumps({"memberships": [{"user_id": "", "group_id": "grp-1"}]}),
                encoding="utf-8",
            )
            env = self._env(root)
            env["JARVIS_INTEGRITY_FAIL_ON_ORPHANS"] = "1"
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 6)
            self.assertIn("WARNING: orphan admin data references detected", proc.stdout + proc.stderr)
            self.assertIn("malformed memberships", proc.stdout + proc.stderr)

    def test_integrity_script_can_fail_on_orphans_with_malformed_membership_shape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "users.json").write_text(
                json.dumps({"users": {"usr-1": {"id": "usr-1", "role": "admin", "enabled": True}}}),
                encoding="utf-8",
            )
            (root / "groups.json").write_text(
                json.dumps({"groups": {"grp-1": {"id": "grp-1", "name": "ops"}}}),
                encoding="utf-8",
            )
            (root / "memberships.json").write_text(
                json.dumps({"memberships": [{"user_id": "usr-1"}]}),
                encoding="utf-8",
            )
            env = self._env(root)
            env["JARVIS_INTEGRITY_FAIL_ON_ORPHANS"] = "1"
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 6)
            self.assertIn("WARNING: orphan admin data references detected", proc.stdout + proc.stderr)
            self.assertIn("malformed memberships", proc.stdout + proc.stderr)

    def test_integrity_script_can_fail_on_orphans_with_malformed_memberships(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "memberships.json").write_text(
                json.dumps({"memberships": ["not-a-membership-object"]}),
                encoding="utf-8",
            )
            env = self._env(root)
            env["JARVIS_INTEGRITY_FAIL_ON_ORPHANS"] = "1"
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 6)
            self.assertIn("WARNING: orphan admin data references detected", proc.stdout + proc.stderr)
            self.assertIn("malformed memberships", proc.stdout + proc.stderr)

    def test_integrity_script_can_fail_on_orphans(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            (root / "permissions.json").write_text(json.dumps({"group_permissions": {"grp-missing": ["assistant.chat"]}, "user_permissions": {}}), encoding="utf-8")
            env = self._env(root)
            env["JARVIS_INTEGRITY_FAIL_ON_ORPHANS"] = "1"
            proc = subprocess.run(
                ["bash", "scripts/check_admin_data_integrity.sh"],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 6)
            self.assertIn("WARNING: orphan admin data references detected", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
