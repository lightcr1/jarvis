import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class AdminBackupRestoreDrillScriptTests(unittest.TestCase):
    def _seed_valid_files(self, root: Path) -> None:
        (root / "audit.log").write_text("", encoding="utf-8")
        (root / "users.json").write_text(
            json.dumps({"users": {"usr-1": {"id": "usr-1", "username": "owner", "role": "admin", "enabled": True}}}),
            encoding="utf-8",
        )
        (root / "groups.json").write_text(json.dumps({"groups": {"grp-1": {"id": "grp-1", "name": "ops"}}}), encoding="utf-8")
        (root / "memberships.json").write_text(
            json.dumps({"memberships": [{"user_id": "usr-1", "group_id": "grp-1"}]}),
            encoding="utf-8",
        )
        (root / "permissions.json").write_text(
            json.dumps({"group_permissions": {"grp-1": ["assistant.chat"]}, "user_permissions": {"usr-1": ["audit.read"]}}),
            encoding="utf-8",
        )
        (root / "admin_settings.json").write_text(
            json.dumps(
                {
                    "usage_limits": {"token_ttl_min": 20, "max_active_tokens": 200},
                    "voice": {"wakeword_enabled": False, "wakeword_phrase": "hey jarvis", "stt_provider": "local"},
                }
            ),
            encoding="utf-8",
        )

    def test_drill_script_generates_report_without_mutating_live_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._seed_valid_files(root)
            report_path = root / "report.md"

            env = os.environ.copy()
            env.update(
                {
                    "JARVIS_AUDIT_LOG_PATH": str(root / "audit.log"),
                    "JARVIS_USER_STORE_PATH": str(root / "users.json"),
                    "JARVIS_GROUP_STORE_PATH": str(root / "groups.json"),
                    "JARVIS_MEMBERSHIP_STORE_PATH": str(root / "memberships.json"),
                    "JARVIS_PERMISSION_STORE_PATH": str(root / "permissions.json"),
                    "JARVIS_ADMIN_SETTINGS_PATH": str(root / "admin_settings.json"),
                }
            )

            before = {
                name: (root / name).read_text(encoding="utf-8")
                for name in ("audit.log", "users.json", "groups.json", "memberships.json", "permissions.json", "admin_settings.json")
            }

            proc = subprocess.run(
                ["bash", "scripts/admin_backup_restore_drill.sh", str(report_path)],
                cwd="/home/jarvis/jarvis",
                env=env,
                text=True,
                capture_output=True,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            self.assertTrue(report_path.exists())
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("PASS `backup-created`", report)
            self.assertIn("PASS `restore-completed`", report)
            self.assertIn("PASS `files-restored`", report)
            self.assertIn("PASS `integrity-check`", report)

            after = {
                name: (root / name).read_text(encoding="utf-8")
                for name in ("audit.log", "users.json", "groups.json", "memberships.json", "permissions.json", "admin_settings.json")
            }
            self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
