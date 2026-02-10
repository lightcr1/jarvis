import os
import unittest

from jarvis_engine import JarvisEngine, SecurityPolicy, build_registry


class EngineTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ["ALLOWED_TARGETS"] = "local"
        os.environ["COOLDOWN_RESTART_SECONDS"] = "0"
        os.environ["COOLDOWN_CRITICAL_SECONDS"] = "0"
        self.engine = JarvisEngine(build_registry(), SecurityPolicy())

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


if __name__ == "__main__":
    unittest.main()
