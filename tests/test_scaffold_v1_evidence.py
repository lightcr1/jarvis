from pathlib import Path
import subprocess
import tempfile
import unittest


class ScaffoldV1EvidenceTests(unittest.TestCase):
    def test_scaffold_creates_expected_files(self):
        with tempfile.TemporaryDirectory() as td:
            proc = subprocess.run(
                [
                    "python3",
                    "scripts/scaffold_v1_evidence.py",
                    "--output-dir",
                    td,
                    "--date",
                    "2026-03-15",
                ],
                cwd="/home/jarvis/jarvis",
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, proc.returncode, msg=proc.stderr)
            names = sorted(path.name for path in Path(td).iterdir())
            self.assertEqual(
                [
                    "2026-03-15_benchmark_notes.md",
                    "2026-03-15_deploy_validation.md",
                    "2026-03-15_manual_acceptance_notes.md",
                    "2026-03-15_recovery_drill_notes.md",
                ],
                names,
            )

    def test_scaffold_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            cmd = [
                "python3",
                "scripts/scaffold_v1_evidence.py",
                "--output-dir",
                td,
                "--date",
                "2026-03-15",
            ]
            first = subprocess.run(cmd, cwd="/home/jarvis/jarvis", text=True, capture_output=True)
            second = subprocess.run(cmd, cwd="/home/jarvis/jarvis", text=True, capture_output=True)
            self.assertEqual(0, first.returncode, msg=first.stderr)
            self.assertEqual(0, second.returncode, msg=second.stderr)
            self.assertIn("No files created", second.stdout)


if __name__ == "__main__":
    unittest.main()
