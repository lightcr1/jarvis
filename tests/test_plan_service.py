import os
import tempfile
import time
import unittest

from jarvis.credit_store import CreditStore
from jarvis.plan_service import assign_plan, ensure_monthly_grant, _current_ym
from jarvis.plan_store import PlanStore
from jarvis.user_limits_store import UserLimitsStore


class PlanServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_PLAN_STORE_PATH"] = os.path.join(base, "plans.json")
        os.environ["JARVIS_USER_LIMITS_STORE_PATH"] = os.path.join(base, "user_limits.json")
        os.environ["JARVIS_CREDIT_STORE_PATH"] = os.path.join(base, "credits.json")
        self.plans = PlanStore()
        self.limits = UserLimitsStore()
        self.credits = CreditStore()

    def tearDown(self):
        self.tmpdir.cleanup()
        for k in ["JARVIS_PLAN_STORE_PATH", "JARVIS_USER_LIMITS_STORE_PATH", "JARVIS_CREDIT_STORE_PATH"]:
            os.environ.pop(k, None)

    def test_assign_plan_grants_credit_and_sets_storage_quota(self):
        updated = assign_plan("usr-1", "plan-standard", plan_store=self.plans, user_limits_store=self.limits, credit_store=self.credits)
        self.assertEqual("plan-standard", updated["plan_id"])
        self.assertEqual(20 * 1024, updated["storage_quota_mb"])
        self.assertEqual(10.0, self.credits.get_balance("usr-1"))
        self.assertEqual(_current_ym(), updated["plan_last_grant_ym"])

    def test_assign_free_plan_grants_no_credit_when_zero(self):
        self.plans.update_plan("plan-free", {"ai_credit_chf_monthly": 0.0})
        assign_plan("usr-2", "plan-free", plan_store=self.plans, user_limits_store=self.limits, credit_store=self.credits)
        self.assertEqual(0.0, self.credits.get_balance("usr-2"))

    def test_assign_unknown_plan_raises(self):
        with self.assertRaises(ValueError):
            assign_plan("usr-3", "plan-does-not-exist", plan_store=self.plans, user_limits_store=self.limits, credit_store=self.credits)

    def test_assign_empty_plan_clears_assignment(self):
        assign_plan("usr-4", "plan-pro", plan_store=self.plans, user_limits_store=self.limits, credit_store=self.credits)
        cleared = assign_plan("usr-4", "", plan_store=self.plans, user_limits_store=self.limits, credit_store=self.credits)
        self.assertEqual("", cleared["plan_id"])
        self.assertEqual(0, cleared["storage_quota_mb"])

    def test_ensure_monthly_grant_noop_without_plan(self):
        granted = ensure_monthly_grant("usr-5", plan_store=self.plans, user_limits_store=self.limits, credit_store=self.credits)
        self.assertFalse(granted)
        self.assertEqual(0.0, self.credits.get_balance("usr-5"))

    def test_ensure_monthly_grant_noop_same_month_after_assign(self):
        assign_plan("usr-6", "plan-standard", plan_store=self.plans, user_limits_store=self.limits, credit_store=self.credits)
        balance_after_assign = self.credits.get_balance("usr-6")
        granted = ensure_monthly_grant("usr-6", plan_store=self.plans, user_limits_store=self.limits, credit_store=self.credits)
        self.assertFalse(granted)
        self.assertEqual(balance_after_assign, self.credits.get_balance("usr-6"))

    def test_ensure_monthly_grant_grants_when_month_rolled_over(self):
        assign_plan("usr-7", "plan-standard", plan_store=self.plans, user_limits_store=self.limits, credit_store=self.credits)
        # Simulate a stale last-grant month so the rollover branch fires.
        self.limits.update("usr-7", {"plan_last_grant_ym": "2000-01"})
        granted = ensure_monthly_grant("usr-7", plan_store=self.plans, user_limits_store=self.limits, credit_store=self.credits)
        self.assertTrue(granted)
        self.assertEqual(20.0, self.credits.get_balance("usr-7"))
        self.assertEqual(_current_ym(), self.limits.get("usr-7")["plan_last_grant_ym"])

    def test_ensure_monthly_grant_noop_if_plan_deleted(self):
        assign_plan("usr-8", "plan-standard", plan_store=self.plans, user_limits_store=self.limits, credit_store=self.credits)
        self.plans.delete_plan("plan-standard")
        self.limits.update("usr-8", {"plan_last_grant_ym": "2000-01"})
        granted = ensure_monthly_grant("usr-8", plan_store=self.plans, user_limits_store=self.limits, credit_store=self.credits)
        self.assertFalse(granted)


if __name__ == "__main__":
    unittest.main()
