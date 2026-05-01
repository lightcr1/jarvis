import os
import tempfile
import unittest

from jarvis.admin_settings_store import AdminSettingsStore


class AdminSettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_ADMIN_SETTINGS_PATH"] = os.path.join(self.tmpdir.name, "admin_settings.json")
        self.store = AdminSettingsStore()

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("JARVIS_ADMIN_SETTINGS_PATH", None)

    def test_defaults_are_sane(self):
        settings = self.store.get()
        self.assertEqual(20, settings["usage_limits"]["token_ttl_min"])
        self.assertEqual(200, settings["usage_limits"]["max_active_tokens"])
        self.assertFalse(settings["voice"]["wakeword_enabled"])
        self.assertEqual("hey jarvis", settings["voice"]["wakeword_phrase"])
        self.assertEqual("local", settings["voice"]["stt_provider"])
        self.assertEqual(300, settings["home_assistant"]["confirmation_ttl_sec"])
        self.assertEqual([], settings["home_assistant"]["remote_allowed_cidrs"])

    def test_update_token_ttl(self):
        self.store.update({"usage_limits": {"token_ttl_min": 60}})
        self.assertEqual(60, self.store.get()["usage_limits"]["token_ttl_min"])

    def test_token_ttl_minimum_enforced_at_one(self):
        self.store.update({"usage_limits": {"token_ttl_min": 0}})
        self.assertEqual(1, self.store.get()["usage_limits"]["token_ttl_min"])

    def test_max_active_tokens_minimum_enforced_at_one(self):
        self.store.update({"usage_limits": {"max_active_tokens": -5}})
        self.assertEqual(1, self.store.get()["usage_limits"]["max_active_tokens"])

    def test_update_wakeword_enabled(self):
        self.store.update({"voice": {"wakeword_enabled": True}})
        self.assertTrue(self.store.get()["voice"]["wakeword_enabled"])

    def test_update_wakeword_phrase(self):
        self.store.update({"voice": {"wakeword_phrase": "computer"}})
        self.assertEqual("computer", self.store.get()["voice"]["wakeword_phrase"])

    def test_wakeword_phrase_empty_resets_to_default(self):
        self.store.update({"voice": {"wakeword_phrase": ""}})
        self.assertEqual("hey jarvis", self.store.get()["voice"]["wakeword_phrase"])

    def test_stt_provider_gemini_allowed(self):
        self.store.update({"voice": {"stt_provider": "gemini"}})
        self.assertEqual("gemini", self.store.get()["voice"]["stt_provider"])

    def test_stt_provider_invalid_resets_to_local(self):
        self.store.update({"voice": {"stt_provider": "openai"}})
        self.assertEqual("local", self.store.get()["voice"]["stt_provider"])

    def test_confirmation_ttl_minimum_30(self):
        self.store.update({"home_assistant": {"confirmation_ttl_sec": 10}})
        self.assertEqual(30, self.store.get()["home_assistant"]["confirmation_ttl_sec"])

    def test_confirmation_ttl_custom(self):
        self.store.update({"home_assistant": {"confirmation_ttl_sec": 120}})
        self.assertEqual(120, self.store.get()["home_assistant"]["confirmation_ttl_sec"])

    def test_remote_allowed_cidrs_stored(self):
        self.store.update({"home_assistant": {"remote_allowed_cidrs": ["10.0.0.0/8", "192.168.1.0/24"]}})
        cidrs = self.store.get()["home_assistant"]["remote_allowed_cidrs"]
        self.assertIn("10.0.0.0/8", cidrs)
        self.assertIn("192.168.1.0/24", cidrs)

    def test_remote_allowed_cidrs_deduplicated(self):
        self.store.update({"home_assistant": {"remote_allowed_cidrs": ["10.0.0.0/8", "10.0.0.0/8"]}})
        cidrs = self.store.get()["home_assistant"]["remote_allowed_cidrs"]
        self.assertEqual(1, cidrs.count("10.0.0.0/8"))

    def test_remote_allowed_cidrs_non_list_ignored(self):
        self.store.update({"home_assistant": {"remote_allowed_cidrs": "not-a-list"}})
        self.assertEqual([], self.store.get()["home_assistant"]["remote_allowed_cidrs"])

    def test_invalid_token_ttl_string_uses_default(self):
        self.store.update({"usage_limits": {"token_ttl_min": "not-a-number"}})
        self.assertEqual(20, self.store.get()["usage_limits"]["token_ttl_min"])

    def test_invalid_confirmation_ttl_string_uses_default(self):
        self.store.update({"home_assistant": {"confirmation_ttl_sec": "bad"}})
        self.assertEqual(300, self.store.get()["home_assistant"]["confirmation_ttl_sec"])

    def test_non_dict_payload_sections_are_ignored(self):
        self.store.update({"usage_limits": "not-a-dict", "voice": None})
        settings = self.store.get()
        self.assertEqual(20, settings["usage_limits"]["token_ttl_min"])

    def test_persists_across_reload(self):
        self.store.update({"voice": {"wakeword_phrase": "computer", "wakeword_enabled": True}})
        store2 = AdminSettingsStore()
        self.assertEqual("computer", store2.get()["voice"]["wakeword_phrase"])
        self.assertTrue(store2.get()["voice"]["wakeword_enabled"])

    def test_get_returns_normalized_view(self):
        self.store.data["voice"]["stt_provider"] = "invalid-provider"
        settings = self.store.get()
        self.assertEqual("local", settings["voice"]["stt_provider"])


if __name__ == "__main__":
    unittest.main()
