import unittest

import jarvisappv4


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


if __name__ == "__main__":
    unittest.main()
