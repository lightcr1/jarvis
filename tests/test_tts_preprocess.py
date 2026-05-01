import os
import unittest

import jarvisappv4
from jarvis.audio_services import strip_wakeword, tts_preprocess_text, wakeword_enabled, wakeword_phrase


class TTSPreprocessTests(unittest.TestCase):
    def test_status_command_gets_natural_sentence(self):
        out = jarvisappv4.tts_preprocess_text("status jarvis")
        self.assertIn("online and ready", out.lower())

    def test_acronyms_and_punctuation_are_improved(self):
        out = jarvisappv4.tts_preprocess_text("check pve api vmid")
        self.assertIn("P V E", out)
        self.assertIn("A P I", out)
        self.assertIn("V M I D", out)
        self.assertTrue(out.endswith("."))

    def test_health_command_mapped(self):
        out = tts_preprocess_text("health")
        self.assertIn("System health check", out)

    def test_proxmox_health_command_mapped(self):
        out = tts_preprocess_text("proxmox health")
        self.assertIn("Proxmox", out)

    def test_skills_command_mapped(self):
        out = tts_preprocess_text("skills")
        self.assertIn("available skills", out.lower())

    def test_jarvis_acronym_expanded(self):
        out = tts_preprocess_text("Jarvis is ready")
        self.assertIn("J.A.R.V.I.S", out)

    def test_period_added_when_no_terminal_punctuation(self):
        out = tts_preprocess_text("System is up")
        self.assertTrue(out.endswith("."))

    def test_existing_exclamation_not_doubled(self):
        out = tts_preprocess_text("System is up!")
        self.assertTrue(out.endswith("!"))
        self.assertFalse(out.endswith("!."))

    def test_empty_string_returns_empty(self):
        out = tts_preprocess_text("")
        self.assertEqual("", out)

    def test_whitespace_only_cleaned(self):
        out = tts_preprocess_text("   ")
        self.assertIn("", out)


class WakewordTests(unittest.TestCase):
    def setUp(self):
        for k in ["JARVIS_WAKEWORD_ENABLED", "JARVIS_WAKEWORD_PHRASE"]:
            os.environ.pop(k, None)

    def tearDown(self):
        for k in ["JARVIS_WAKEWORD_ENABLED", "JARVIS_WAKEWORD_PHRASE"]:
            os.environ.pop(k, None)

    def test_wakeword_enabled_from_env_true(self):
        os.environ["JARVIS_WAKEWORD_ENABLED"] = "1"
        self.assertTrue(wakeword_enabled(lambda: {}))

    def test_wakeword_enabled_from_env_false(self):
        os.environ["JARVIS_WAKEWORD_ENABLED"] = "0"
        self.assertFalse(wakeword_enabled(lambda: {}))

    def test_wakeword_enabled_from_settings(self):
        self.assertFalse(wakeword_enabled(lambda: {"voice": {"wakeword_enabled": False}}))
        self.assertTrue(wakeword_enabled(lambda: {"voice": {"wakeword_enabled": True}}))

    def test_wakeword_phrase_from_env(self):
        os.environ["JARVIS_WAKEWORD_PHRASE"] = "computer"
        self.assertEqual("computer", wakeword_phrase(lambda: {}))

    def test_wakeword_phrase_from_settings(self):
        self.assertEqual("hey jarvis", wakeword_phrase(lambda: {"voice": {"wakeword_phrase": "hey jarvis"}}))

    def test_wakeword_phrase_default_fallback(self):
        self.assertEqual("hey jarvis", wakeword_phrase(lambda: {}))

    def test_strip_wakeword_exact_match(self):
        cleaned, triggered = strip_wakeword("hey jarvis", "hey jarvis")
        self.assertEqual("status jarvis", cleaned)
        self.assertTrue(triggered)

    def test_strip_wakeword_prefix_match(self):
        cleaned, triggered = strip_wakeword("hey jarvis what time is it", "hey jarvis")
        self.assertEqual("what time is it", cleaned)
        self.assertTrue(triggered)

    def test_strip_wakeword_no_match(self):
        cleaned, triggered = strip_wakeword("what time is it", "hey jarvis")
        self.assertEqual("what time is it", cleaned)
        self.assertFalse(triggered)

    def test_strip_wakeword_empty_input(self):
        cleaned, triggered = strip_wakeword("", "hey jarvis")
        self.assertEqual("", cleaned)
        self.assertFalse(triggered)


if __name__ == "__main__":
    unittest.main()
