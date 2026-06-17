"""Tests for UsageLogStore — append-only JSONL usage log."""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from jarvis.usage_log_store import UsageLogStore


def _make_store(tmp_path: str) -> UsageLogStore:
    os.environ["JARVIS_USAGE_LOG_PATH"] = str(Path(tmp_path) / "usage.log")
    store = UsageLogStore()
    return store


class UsageLogStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = _make_store(self.tmp)

    def tearDown(self):
        os.environ.pop("JARVIS_USAGE_LOG_PATH", None)

    def _record(self, **kwargs) -> dict:
        base = {
            "user_id": "usr-1",
            "conversation_id": "conv-1",
            "provider": "openrouter",
            "model": "anthropic/claude-haiku-4-5",
            "billing_mode": "system",
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "estimated_cost_usd": 0.0001,
            "estimated_cost_chf": 0.00009,
            "request_status": "ok",
            "error": None,
        }
        base.update(kwargs)
        return base

    def test_log_creates_file(self):
        self.store.log(self._record())
        self.assertTrue(self.store.path.exists())

    def test_log_appends_jsonl(self):
        self.store.log(self._record(user_id="u1"))
        self.store.log(self._record(user_id="u2"))
        lines = [l for l in self.store.path.read_text().splitlines() if l.strip()]
        self.assertEqual(len(lines), 2)
        parsed = [json.loads(l) for l in lines]
        self.assertEqual(parsed[0]["user_id"], "u1")
        self.assertEqual(parsed[1]["user_id"], "u2")

    def test_log_adds_ts(self):
        before = int(time.time())
        self.store.log(self._record())
        after = int(time.time())
        lines = [l for l in self.store.path.read_text().splitlines() if l.strip()]
        parsed = json.loads(lines[0])
        self.assertGreaterEqual(parsed["ts"], before)
        self.assertLessEqual(parsed["ts"], after)

    def test_aggregate_no_filter(self):
        self.store.log(self._record(input_tokens=100, output_tokens=50, estimated_cost_usd=0.001, estimated_cost_chf=0.0009))
        self.store.log(self._record(input_tokens=200, output_tokens=100, estimated_cost_usd=0.002, estimated_cost_chf=0.0018))
        result = self.store.aggregate()
        self.assertEqual(result["request_count"], 2)
        self.assertEqual(result["total_input_tokens"], 300)
        self.assertEqual(result["total_output_tokens"], 150)
        self.assertEqual(result["total_tokens"], 450)
        self.assertAlmostEqual(result["total_cost_usd"], 0.003, places=5)
        self.assertAlmostEqual(result["total_cost_chf"], 0.0027, places=5)

    def test_aggregate_filter_user_id(self):
        self.store.log(self._record(user_id="u1", input_tokens=100))
        self.store.log(self._record(user_id="u2", input_tokens=200))
        result = self.store.aggregate(user_id="u1")
        self.assertEqual(result["request_count"], 1)
        self.assertEqual(result["total_input_tokens"], 100)

    def test_aggregate_filter_provider(self):
        self.store.log(self._record(provider="openrouter"))
        self.store.log(self._record(provider="anthropic"))
        result = self.store.aggregate(provider="anthropic")
        self.assertEqual(result["request_count"], 1)

    def test_aggregate_filter_model(self):
        self.store.log(self._record(model="haiku"))
        self.store.log(self._record(model="sonnet"))
        result = self.store.aggregate(model="haiku")
        self.assertEqual(result["request_count"], 1)

    def test_aggregate_filter_billing_mode(self):
        self.store.log(self._record(billing_mode="system"))
        self.store.log(self._record(billing_mode="credit"))
        result = self.store.aggregate(billing_mode="credit")
        self.assertEqual(result["request_count"], 1)

    def test_aggregate_filter_since_until(self):
        now = int(time.time())
        past = now - 1000
        self.store.log(self._record())
        result = self.store.aggregate(since_ts=now - 60, until_ts=now + 60)
        self.assertEqual(result["request_count"], 1)
        result_none = self.store.aggregate(since_ts=now + 100)
        self.assertEqual(result_none["request_count"], 0)

    def test_aggregate_empty_store(self):
        result = self.store.aggregate()
        self.assertEqual(result["request_count"], 0)
        self.assertEqual(result["total_tokens"], 0)

    def test_recent_returns_newest_first(self):
        self.store.log(self._record(model="first"))
        self.store.log(self._record(model="second"))
        results = self.store.recent(limit=10)
        self.assertEqual(results[0]["model"], "second")
        self.assertEqual(results[1]["model"], "first")

    def test_recent_limit_cap(self):
        for i in range(10):
            self.store.log(self._record(model=f"m{i}"))
        results = self.store.recent(limit=3)
        self.assertEqual(len(results), 3)

    def test_recent_filter_user_id(self):
        self.store.log(self._record(user_id="u1"))
        self.store.log(self._record(user_id="u2"))
        results = self.store.recent(user_id="u1")
        self.assertTrue(all(r["user_id"] == "u1" for r in results))

    def test_daily_buckets_returns_correct_days(self):
        self.store.log(self._record(estimated_cost_chf=0.01))
        self.store.log(self._record(estimated_cost_chf=0.02))
        buckets = self.store.daily_buckets(days=7)
        self.assertEqual(len(buckets), 1)
        self.assertAlmostEqual(buckets[0]["cost_chf"], 0.03, places=5)
        self.assertEqual(buckets[0]["requests"], 2)

    def test_daily_buckets_filter_user(self):
        self.store.log(self._record(user_id="u1", estimated_cost_chf=0.01))
        self.store.log(self._record(user_id="u2", estimated_cost_chf=0.99))
        buckets = self.store.daily_buckets(user_id="u1")
        self.assertEqual(len(buckets), 1)
        self.assertAlmostEqual(buckets[0]["cost_chf"], 0.01, places=5)

    def test_log_is_resilient_to_corrupt_line(self):
        # Write a corrupt line then a valid one
        self.store.path.write_text('{"bad: json\n', encoding="utf-8")
        self.store.log(self._record())
        result = self.store.aggregate()
        self.assertEqual(result["request_count"], 1)


if __name__ == "__main__":
    unittest.main()
