"""Tests for UserLimitsStore — per-user spending and access limits."""

import os
import tempfile
import unittest
from pathlib import Path

from jarvis.user_limits_store import UserLimitsStore, DEFAULT_LIMITS


def _make_store(tmp_path: str) -> UserLimitsStore:
    os.environ["JARVIS_USER_LIMITS_STORE_PATH"] = str(Path(tmp_path) / "user_limits.json")
    return UserLimitsStore()


class UserLimitsStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = _make_store(self.tmp)

    def tearDown(self):
        os.environ.pop("JARVIS_USER_LIMITS_STORE_PATH", None)

    def test_get_returns_defaults_for_unknown_user(self):
        limits = self.store.get("usr-unknown")
        self.assertEqual(limits["chf_per_day"], DEFAULT_LIMITS["chf_per_day"])
        self.assertEqual(limits["requests_per_min"], DEFAULT_LIMITS["requests_per_min"])
        self.assertEqual(limits["allowed_models"], [])

    def test_update_persists_values(self):
        updated = self.store.update("usr-1", {"chf_per_day": 5.0, "requests_per_min": 10})
        self.assertEqual(updated["chf_per_day"], 5.0)
        self.assertEqual(updated["requests_per_min"], 10)

    def test_get_returns_updated_values(self):
        self.store.update("usr-1", {"chf_per_day": 3.0})
        limits = self.store.get("usr-1")
        self.assertEqual(limits["chf_per_day"], 3.0)

    def test_negative_chf_clamped_to_zero(self):
        updated = self.store.update("usr-1", {"chf_per_day": -1.0})
        self.assertEqual(updated["chf_per_day"], 0.0)

    def test_requests_per_min_zero_uses_default(self):
        # 0 is falsy, so `int(raw or 30)` returns the default 30
        updated = self.store.update("usr-1", {"requests_per_min": 0})
        self.assertEqual(updated["requests_per_min"], 30)

    def test_requests_per_min_clamped_max(self):
        updated = self.store.update("usr-1", {"requests_per_min": 9999})
        self.assertEqual(updated["requests_per_min"], 300)

    def test_negative_tokens_per_request_clamped(self):
        updated = self.store.update("usr-1", {"tokens_per_request": -100})
        self.assertEqual(updated["tokens_per_request"], 0)

    def test_allowed_models_list_stored(self):
        updated = self.store.update("usr-1", {"allowed_models": ["haiku", "sonnet"]})
        self.assertEqual(updated["allowed_models"], ["haiku", "sonnet"])

    def test_allowed_models_non_list_coerced_empty(self):
        updated = self.store.update("usr-1", {"allowed_models": "not-a-list"})
        self.assertEqual(updated["allowed_models"], [])

    def test_delete_removes_user(self):
        self.store.update("usr-1", {"chf_per_day": 5.0})
        removed = self.store.delete("usr-1")
        self.assertTrue(removed)
        limits = self.store.get("usr-1")
        self.assertEqual(limits["chf_per_day"], DEFAULT_LIMITS["chf_per_day"])

    def test_delete_nonexistent_returns_false(self):
        self.assertFalse(self.store.delete("usr-ghost"))

    def test_update_merges_not_replaces(self):
        self.store.update("usr-1", {"chf_per_day": 5.0, "requests_per_min": 20})
        self.store.update("usr-1", {"chf_per_day": 10.0})
        limits = self.store.get("usr-1")
        self.assertEqual(limits["chf_per_day"], 10.0)
        self.assertEqual(limits["requests_per_min"], 20)

    def test_multiple_users_independent(self):
        self.store.update("usr-1", {"chf_per_day": 5.0})
        self.store.update("usr-2", {"chf_per_day": 10.0})
        self.assertEqual(self.store.get("usr-1")["chf_per_day"], 5.0)
        self.assertEqual(self.store.get("usr-2")["chf_per_day"], 10.0)

    def test_data_persists_across_instances(self):
        self.store.update("usr-1", {"chf_per_month": 50.0})
        store2 = UserLimitsStore()
        self.assertEqual(store2.get("usr-1")["chf_per_month"], 50.0)

    def test_expensive_models_per_day_clamped(self):
        updated = self.store.update("usr-1", {"expensive_models_per_day": -5})
        self.assertEqual(updated["expensive_models_per_day"], 0)


if __name__ == "__main__":
    unittest.main()
