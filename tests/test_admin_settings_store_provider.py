"""Tests for AdminSettingsStore provider section — Phase 3 guard."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from jarvis.admin_settings_store import AdminSettingsStore


def _make_store(tmp_path: str) -> AdminSettingsStore:
    os.environ["JARVIS_ADMIN_SETTINGS_PATH"] = str(Path(tmp_path) / "admin_settings.json")
    return AdminSettingsStore()


class AdminSettingsStoreProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = _make_store(self.tmp)

    def tearDown(self):
        os.environ.pop("JARVIS_ADMIN_SETTINGS_PATH", None)

    def test_provider_section_present_by_default(self):
        s = self.store.get()
        self.assertIn("provider", s)
        prov = s["provider"]
        self.assertIn("default_provider", prov)
        self.assertIn("usd_to_chf_rate", prov)
        self.assertIn("model_prices", prov)
        self.assertIn("kill_switch", prov)

    def test_default_provider_is_openrouter(self):
        s = self.store.get()
        self.assertEqual(s["provider"]["default_provider"], "openrouter")

    def test_update_default_provider(self):
        updated = self.store.update({"provider": {"default_provider": "anthropic"}})
        self.assertEqual(updated["provider"]["default_provider"], "anthropic")

    def test_unknown_provider_falls_back_to_default(self):
        updated = self.store.update({"provider": {"default_provider": "unknownprovider"}})
        self.assertEqual(updated["provider"]["default_provider"], "openrouter")

    def test_usd_to_chf_rate_update(self):
        updated = self.store.update({"provider": {"usd_to_chf_rate": 0.85}})
        self.assertAlmostEqual(updated["provider"]["usd_to_chf_rate"], 0.85)

    def test_usd_to_chf_rate_nonpositive_clamped(self):
        updated = self.store.update({"provider": {"usd_to_chf_rate": 0.0}})
        self.assertGreater(updated["provider"]["usd_to_chf_rate"], 0)

    def test_model_prices_round_trip(self):
        prices = {
            "anthropic/claude-haiku-4-5": {"in": 1.0, "out": 5.0, "tier": "simple", "expensive": False}
        }
        updated = self.store.update({"provider": {"model_prices": prices}})
        mp = updated["provider"]["model_prices"]
        self.assertIn("anthropic/claude-haiku-4-5", mp)
        self.assertAlmostEqual(mp["anthropic/claude-haiku-4-5"]["in"], 1.0)
        self.assertAlmostEqual(mp["anthropic/claude-haiku-4-5"]["out"], 5.0)

    def test_model_prices_invalid_values_skipped(self):
        prices = {
            "good-model": {"in": 1.0, "out": 5.0, "tier": "simple", "expensive": False},
            "bad-model": "not-a-dict",
        }
        updated = self.store.update({"provider": {"model_prices": prices}})
        mp = updated["provider"]["model_prices"]
        self.assertIn("good-model", mp)
        self.assertNotIn("bad-model", mp)

    def test_model_prices_negative_price_clamped_to_zero(self):
        prices = {"m": {"in": -5.0, "out": -1.0, "tier": "simple", "expensive": False}}
        updated = self.store.update({"provider": {"model_prices": prices}})
        mp = updated["provider"]["model_prices"]
        self.assertEqual(mp["m"]["in"], 0.0)
        self.assertEqual(mp["m"]["out"], 0.0)

    def test_kill_switch_update(self):
        updated = self.store.update({"provider": {"kill_switch": True}})
        self.assertTrue(updated["provider"]["kill_switch"])

    def test_disable_expensive_models_update(self):
        updated = self.store.update({"provider": {"disable_expensive_models": True}})
        self.assertTrue(updated["provider"]["disable_expensive_models"])

    def test_expensive_threshold_update(self):
        updated = self.store.update({"provider": {"expensive_threshold_chf": 0.50}})
        self.assertAlmostEqual(updated["provider"]["expensive_threshold_chf"], 0.50)

    def test_global_daily_budget_update(self):
        updated = self.store.update({"provider": {"global_daily_budget_chf": 10.0}})
        self.assertAlmostEqual(updated["provider"]["global_daily_budget_chf"], 10.0)

    def test_global_monthly_budget_update(self):
        updated = self.store.update({"provider": {"global_monthly_budget_chf": 100.0}})
        self.assertAlmostEqual(updated["provider"]["global_monthly_budget_chf"], 100.0)

    def test_provider_section_persists_to_disk(self):
        self.store.update({"provider": {"kill_switch": True, "usd_to_chf_rate": 0.91}})
        store2 = AdminSettingsStore()
        s = store2.get()
        self.assertTrue(s["provider"]["kill_switch"])
        self.assertAlmostEqual(s["provider"]["usd_to_chf_rate"], 0.91)

    def test_update_provider_does_not_clobber_other_sections(self):
        self.store.update({"voice": {"wakeword_enabled": True}})
        self.store.update({"provider": {"kill_switch": True}})
        s = self.store.get()
        self.assertTrue(s["voice"]["wakeword_enabled"])
        self.assertTrue(s["provider"]["kill_switch"])

    def test_normalize_handles_missing_provider_key(self):
        # Store without provider section in file
        path = Path(self.tmp) / "admin_settings.json"
        path.write_text(json.dumps({"usage_limits": {}, "voice": {}, "home_assistant": {}}), encoding="utf-8")
        store = AdminSettingsStore()
        s = store.get()
        self.assertIn("provider", s)
        self.assertEqual(s["provider"]["default_provider"], "openrouter")

    def test_openrouter_enabled_default_true(self):
        s = self.store.get()
        self.assertTrue(s["provider"]["openrouter_enabled"])

    def test_openrouter_enabled_can_be_disabled(self):
        updated = self.store.update({"provider": {"openrouter_enabled": False}})
        self.assertFalse(updated["provider"]["openrouter_enabled"])


if __name__ == "__main__":
    unittest.main()
