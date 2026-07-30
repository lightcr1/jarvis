import os
import tempfile
import unittest

from jarvis.plan_store import PlanStore


class PlanStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_PLAN_STORE_PATH"] = os.path.join(self.tmpdir.name, "plans.json")

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("JARVIS_PLAN_STORE_PATH", None)

    def test_default_plans_seeded(self):
        store = PlanStore()
        plans = store.list_plans()
        names = [p["name"] for p in plans]
        self.assertIn("Free", names)
        self.assertIn("Standard", names)
        self.assertIn("Pro", names)

    def test_list_plans_sorted_by_sort_order(self):
        store = PlanStore()
        plans = store.list_plans()
        orders = [p["sort_order"] for p in plans]
        self.assertEqual(orders, sorted(orders))

    def test_create_plan(self):
        store = PlanStore()
        plan = store.create_plan({
            "name": "Team",
            "price_chf_per_month": 50.0,
            "ai_credit_chf_monthly": 60.0,
            "storage_gb_included": 500.0,
            "sort_order": 3,
        })
        self.assertEqual("Team", plan["name"])
        self.assertTrue(plan["id"].startswith("plan-"))
        self.assertIn(plan["id"], [p["id"] for p in store.list_plans()])

    def test_update_plan(self):
        store = PlanStore()
        updated = store.update_plan("plan-standard", {"price_chf_per_month": 9.0})
        self.assertIsNotNone(updated)
        self.assertEqual(9.0, updated["price_chf_per_month"])

    def test_update_missing_plan_returns_none(self):
        store = PlanStore()
        self.assertIsNone(store.update_plan("nonexistent", {"name": "x"}))

    def test_delete_plan(self):
        store = PlanStore()
        self.assertTrue(store.delete_plan("plan-free"))
        self.assertIsNone(store.get_plan("plan-free"))

    def test_delete_missing_plan_returns_false(self):
        store = PlanStore()
        self.assertFalse(store.delete_plan("nonexistent"))

    def test_negative_prices_are_clamped_to_zero(self):
        store = PlanStore()
        plan = store.create_plan({"name": "Bad", "price_chf_per_month": -5.0, "ai_credit_chf_monthly": -1.0, "storage_gb_included": -2.0})
        self.assertEqual(0.0, plan["price_chf_per_month"])
        self.assertEqual(0.0, plan["ai_credit_chf_monthly"])
        self.assertEqual(0.0, plan["storage_gb_included"])


if __name__ == "__main__":
    unittest.main()
