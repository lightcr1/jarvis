from pathlib import Path
import subprocess
import tempfile
import unittest


class OpsPreparationAssetsTests(unittest.TestCase):
    def test_env_templates_exist_and_are_isolated(self):
        dev = Path("config/env/dev.env.example").read_text(encoding="utf-8")
        test = Path("config/env/test.env.example").read_text(encoding="utf-8")
        prod = Path("config/env/prod.env.example").read_text(encoding="utf-8")
        self.assertIn("JARVIS_ENV=dev", dev)
        self.assertIn("JARVIS_ENV=test", test)
        self.assertIn("JARVIS_ENV=prod", prod)
        self.assertIn("/var/lib/jarvis-dev/", dev)
        self.assertIn("/var/lib/jarvis-test/", test)
        self.assertIn("/var/lib/jarvis/", prod)
        self.assertIn("JARVIS_WIKIJS_ENABLED=0", prod)

    def test_benchmark_script_writes_report(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "benchmark.json"
            proc = subprocess.run(
                [
                    "python3",
                    "scripts/benchmark_local.py",
                    "--base-url",
                    "http://127.0.0.1:9",
                    "--iterations",
                    "1",
                    "--output",
                    str(report),
                ],
                cwd="/home/jarvis/jarvis",
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 1)
            self.assertTrue(report.exists())
            content = report.read_text(encoding="utf-8")
            self.assertIn('"status": "degraded"', content)
            self.assertIn('"failures"', content)

    def test_recovery_drill_script_has_required_controls(self):
        content = Path("scripts/recovery_drill.sh").read_text(encoding="utf-8")
        self.assertIn('HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"', content)
        self.assertIn('RESTART_COMMAND="${RESTART_COMMAND:-systemctl restart jarvis.service}"', content)
        self.assertIn("Recovery Drill Report", content)

    def test_user_runbook_mentions_remaining_user_actions(self):
        content = Path("USER_EXECUTION_RUNBOOK_V1.md").read_text(encoding="utf-8")
        self.assertIn("One-Command Deploy Validation", content)
        self.assertIn("Lower-End Hardware Performance Check", content)
        self.assertIn("Failure Recovery Execution", content)
        self.assertIn("WikiJS V1 Scope Confirmation", content)


if __name__ == "__main__":
    unittest.main()
