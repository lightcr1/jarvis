"""Tests for CreditStore — per-user CHF credit balance + ledger."""

import os
import tempfile
import unittest
from pathlib import Path

from jarvis.credit_store import CreditStore


def _make_store(tmp_path: str) -> CreditStore:
    os.environ["JARVIS_CREDIT_STORE_PATH"] = str(Path(tmp_path) / "credits.json")
    return CreditStore()


class CreditStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = _make_store(self.tmp)

    def tearDown(self):
        os.environ.pop("JARVIS_CREDIT_STORE_PATH", None)

    def test_initial_balance_zero(self):
        self.assertEqual(self.store.get_balance("usr-1"), 0.0)

    def test_top_up_increases_balance(self):
        entry = self.store.top_up("usr-1", 5.00, note="initial load", actor="admin")
        self.assertEqual(self.store.get_balance("usr-1"), 5.00)
        self.assertEqual(entry["type"], "topup")
        self.assertEqual(entry["amount_chf"], 5.00)
        self.assertEqual(entry["balance_after"], 5.00)
        self.assertTrue(entry["id"].startswith("cr-"))

    def test_top_up_invalid_amount_raises(self):
        with self.assertRaises(ValueError):
            self.store.top_up("usr-1", 0.0)
        with self.assertRaises(ValueError):
            self.store.top_up("usr-1", -1.0)

    def test_deduct_reduces_balance(self):
        self.store.top_up("usr-1", 10.00)
        ok, new_balance = self.store.deduct("usr-1", 3.00, note="usage")
        self.assertTrue(ok)
        self.assertAlmostEqual(new_balance, 7.00, places=5)
        self.assertAlmostEqual(self.store.get_balance("usr-1"), 7.00, places=5)

    def test_deduct_refuses_negative_balance(self):
        self.store.top_up("usr-1", 2.00)
        ok, balance = self.store.deduct("usr-1", 5.00)
        self.assertFalse(ok)
        self.assertAlmostEqual(balance, 2.00, places=5)
        self.assertAlmostEqual(self.store.get_balance("usr-1"), 2.00, places=5)

    def test_deduct_exact_zero_balance_allowed(self):
        self.store.top_up("usr-1", 1.00)
        ok, balance = self.store.deduct("usr-1", 1.00)
        self.assertTrue(ok)
        self.assertAlmostEqual(balance, 0.0, places=5)

    def test_deduct_from_zero_balance_blocked(self):
        ok, balance = self.store.deduct("usr-1", 0.01)
        self.assertFalse(ok)
        self.assertEqual(balance, 0.0)

    def test_ledger_entries_created(self):
        self.store.top_up("usr-1", 5.00, note="load")
        self.store.deduct("usr-1", 1.00, note="use")
        ledger = self.store.list_ledger("usr-1")
        self.assertEqual(len(ledger), 2)
        # Newest first
        self.assertEqual(ledger[0]["type"], "deduction")
        self.assertEqual(ledger[1]["type"], "topup")

    def test_ledger_scoped_to_user(self):
        self.store.top_up("usr-1", 5.00)
        self.store.top_up("usr-2", 10.00)
        self.assertEqual(len(self.store.list_ledger("usr-1")), 1)
        self.assertEqual(len(self.store.list_ledger("usr-2")), 1)

    def test_ledger_limit_capped(self):
        self.store.top_up("usr-1", 100.00)
        for _ in range(10):
            self.store.deduct("usr-1", 0.01)
        ledger = self.store.list_ledger("usr-1", limit=3)
        self.assertEqual(len(ledger), 3)

    def test_multiple_users_independent(self):
        self.store.top_up("usr-1", 5.00)
        self.store.top_up("usr-2", 20.00)
        self.assertAlmostEqual(self.store.get_balance("usr-1"), 5.00)
        self.assertAlmostEqual(self.store.get_balance("usr-2"), 20.00)

    def test_data_persists_across_instances(self):
        self.store.top_up("usr-1", 7.50)
        # Re-create from same path
        store2 = CreditStore()
        self.assertAlmostEqual(store2.get_balance("usr-1"), 7.50)

    def test_top_up_creates_ledger_entry_with_actor(self):
        entry = self.store.top_up("usr-1", 5.00, note="gift", actor="mgr-1")
        self.assertEqual(entry["actor"], "mgr-1")
        self.assertEqual(entry["note"], "gift")

    def test_balance_after_tracked_in_ledger(self):
        self.store.top_up("usr-1", 10.00)
        self.store.deduct("usr-1", 3.00)
        ledger = self.store.list_ledger("usr-1")
        deduction = next(e for e in ledger if e["type"] == "deduction")
        self.assertAlmostEqual(deduction["balance_after"], 7.00, places=5)


if __name__ == "__main__":
    unittest.main()
