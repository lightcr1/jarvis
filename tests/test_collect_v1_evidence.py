from pathlib import Path
import subprocess
import tempfile
import unittest


class CollectV1EvidenceTests(unittest.TestCase):
    def test_collect_script_reports_missing_and_present_groups(self):
        with tempfile.TemporaryDirectory() as td:
            evidence_dir = Path(td)
            (evidence_dir / "2026-03-15_deploy_validation.md").write_text("ok", encoding="utf-8")
            (evidence_dir / "2026-03-15_benchmark_report.json").write_text("{}", encoding="utf-8")
            output = evidence_dir / "summary.md"

            proc = subprocess.run(
                [
                    "python3",
                    "scripts/collect_v1_evidence.py",
                    "--evidence-dir",
                    str(evidence_dir),
                    "--output",
                    str(output),
                ],
                cwd="/home/jarvis/jarvis",
                text=True,
                capture_output=True,
            )

            self.assertEqual(0, proc.returncode, msg=proc.stderr)
            self.assertTrue(output.exists())
            content = output.read_text(encoding="utf-8")
            self.assertIn("PASS `deploy_validation`", content)
            self.assertIn("PASS `benchmark_report`", content)
            self.assertIn("MISSING `manual_acceptance`", content)

    def test_collect_script_fails_for_missing_directory(self):
        proc = subprocess.run(
            [
                "python3",
                "scripts/collect_v1_evidence.py",
                "--evidence-dir",
                "/tmp/does-not-exist-jarvis-evidence",
            ],
            cwd="/home/jarvis/jarvis",
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(0, proc.returncode)
        self.assertIn("Evidence directory not found", proc.stderr or proc.stdout)


if __name__ == "__main__":
    unittest.main()
