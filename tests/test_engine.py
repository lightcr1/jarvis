import os
import tempfile
import unittest

from jarvis_engine import JarvisEngine, SecurityPolicy, build_registry


class EngineTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ["ALLOWED_TARGETS"] = "local"
        os.environ["COOLDOWN_RESTART_SECONDS"] = "0"
        os.environ["COOLDOWN_CRITICAL_SECONDS"] = "0"
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_MEMORY_PATH"] = os.path.join(self.tmpdir.name, "memory.json")
        self.engine = JarvisEngine(build_registry(), SecurityPolicy())

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_fuzzy_matching(self):
        response = self.engine.process("statuz jarvis", token=None)
        self.assertIn("Jarvis", response["summary"])

    def test_disambiguation(self):
        response = self.engine.process("service", token=None)
        self.assertEqual(response["summary"], "Need clarification.")

    def test_token_and_confirm_for_critical(self):
        response = self.engine.process("service restart local nginx", token=None)
        self.assertEqual(response["summary"], "Token required.")

        response = self.engine.process("service restart local nginx", token="tok")
        self.assertIn("Confirmation", response["summary"])
        self.assertEqual(response["data"]["confirm"], "YES, proceed")

        response = self.engine.process("YES, proceed", token="tok")
        self.assertIn("not configured", response["summary"])

    def test_scope_allowlist(self):
        response = self.engine.process("service restart web01 nginx", token="tok")
        self.assertEqual(response["summary"], "Target not allowed.")

    def test_rate_limit(self):
        os.environ["COOLDOWN_RESTART_SECONDS"] = "60"
        engine = JarvisEngine(build_registry(), SecurityPolicy())
        engine.process("service restart local nginx", token="tok")
        response = engine.process("service restart local nginx", token="tok")
        self.assertIn("Cooldown", response["summary"])

    def test_feedback_and_alias_learning(self):
        first = self.engine.process("status jarvis", token=None)
        feedback_id = first["data"]["feedback"]["id"]

        saved = self.engine.process(
            f"feedback {feedback_id} bad correct: proxmox health",
            token=None,
        )
        self.assertEqual(saved["summary"], "Feedback gespeichert.")

        learned = self.engine.process("status jarvis", token=None)
        self.assertIn("Proxmox", learned["summary"])

    def test_skill_suggestion_after_repeated_unmatched(self):
        for _ in range(3):
            response = self.engine.process("warum geht web gui nicht", token=None)
        self.assertIn("skill", response["data"]["skill_suggestion"].lower())

    def test_remember_and_memory_show_commands(self):
        set_resp = self.engine.process("remember node pve1 10.0.0.10", token=None)
        self.assertEqual(set_resp["summary"], "Memory updated.")

        mem_resp = self.engine.process("memory show", token=None)
        self.assertEqual(mem_resp["summary"], "Memory snapshot ready.")
        self.assertEqual(mem_resp["data"]["memory"]["nodes"].get("pve1"), "10.0.0.10")


if __name__ == "__main__":
    unittest.main()
