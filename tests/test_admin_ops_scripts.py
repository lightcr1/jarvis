import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


class TestAdminOpsScripts(unittest.TestCase):
    def _env(self, root: Path) -> dict[str, str]:
        data_dir = root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update(
            {
                "JARVIS_AUDIT_LOG_PATH": str(data_dir / "audit.log"),
                "JARVIS_USER_STORE_PATH": str(data_dir / "users.json"),
                "JARVIS_GROUP_STORE_PATH": str(data_dir / "groups.json"),
                "JARVIS_MEMBERSHIP_STORE_PATH": str(data_dir / "memberships.json"),
                "JARVIS_PERMISSION_STORE_PATH": str(data_dir / "permissions.json"),
            }
        )
        return env

    def test_backup_and_restore_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            env = self._env(root)
            for name in ("audit.log", "users.json", "groups.json", "memberships.json", "permissions.json"):
                (root / "data" / name).write_text(f"{name}-content", encoding="utf-8")

            backup_dir = root / "backups"
            backup_dir.mkdir()

            subprocess.run(
                ["bash", "scripts/backup_admin_data.sh", str(backup_dir)],
                check=True,
                env=env,
            )

            archives = list(backup_dir.glob("jarvis_admin_data_*.tar.gz"))
            self.assertEqual(len(archives), 1)

            for item in (root / "data").iterdir():
                item.unlink()

            subprocess.run(
                ["bash", "scripts/restore_admin_data.sh", str(archives[0])],
                check=True,
                env=env,
            )

            self.assertEqual((root / "data" / "users.json").read_text(encoding="utf-8"), "users.json-content")
            self.assertEqual((root / "data" / "audit.log").read_text(encoding="utf-8"), "audit.log-content")

    def test_restore_rejects_unexpected_archive_entries(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            env = self._env(root)
            archive_path = root / "invalid.tar.gz"
            payload = root / "payload"
            payload.mkdir()
            (payload / "users.json").write_text("ok", encoding="utf-8")
            (payload / "../escape.txt").resolve().write_text("bad", encoding="utf-8")

            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(payload / "users.json", arcname="users.json")
                tar.add((payload / "../escape.txt").resolve(), arcname="escape.txt")

            proc = subprocess.run(
                ["bash", "scripts/restore_admin_data.sh", str(archive_path)],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 3)
            self.assertIn("Refusing to restore unexpected archive entry", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
