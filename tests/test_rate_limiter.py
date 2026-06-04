import os
import threading
import time
import unittest
from unittest.mock import patch


class RateLimiterTests(unittest.TestCase):
    def _make(self):
        from jarvis.rate_limiter import RateLimiter
        return RateLimiter()

    def _patched_env(self):
        env = {k: v for k, v in os.environ.items() if k != "PYTEST_CURRENT_TEST"}
        return patch.dict(os.environ, env, clear=True)

    def test_allows_within_limit(self):
        rl = self._make()
        with self._patched_env():
            for _ in range(5):
                self.assertTrue(rl.allow("k", limit=5, window=60))

    def test_blocks_at_limit_plus_one(self):
        rl = self._make()
        with self._patched_env():
            for _ in range(5):
                rl.allow("k", limit=5, window=60)
            self.assertFalse(rl.allow("k", limit=5, window=60))

    def test_allows_after_window_expires(self):
        rl = self._make()
        t = [100.0]

        def fake_monotonic():
            return t[0]

        with self._patched_env(), patch("jarvis.rate_limiter._time.monotonic", side_effect=fake_monotonic):
            for _ in range(3):
                rl.allow("k", limit=3, window=10)
            self.assertFalse(rl.allow("k", limit=3, window=10))
            t[0] = 115.0
            self.assertTrue(rl.allow("k", limit=3, window=10))

    def test_independent_keys_do_not_interfere(self):
        rl = self._make()
        with self._patched_env():
            for _ in range(3):
                rl.allow("a", limit=3, window=60)
            self.assertFalse(rl.allow("a", limit=3, window=60))
            self.assertTrue(rl.allow("b", limit=3, window=60))

    def test_pytest_env_bypass(self):
        rl = self._make()
        self.assertIn("PYTEST_CURRENT_TEST", os.environ)
        for _ in range(100):
            self.assertTrue(rl.allow("any", limit=1, window=60))

    def test_thread_safety(self):
        rl = self._make()
        results = []
        with self._patched_env():
            def worker():
                for _ in range(20):
                    results.append(rl.allow("shared", limit=10, window=60))

            threads = [threading.Thread(target=worker) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        allowed = results.count(True)
        self.assertEqual(allowed, 10)

    def test_limit_one_allows_only_first(self):
        rl = self._make()
        with self._patched_env():
            self.assertTrue(rl.allow("x", limit=1, window=60))
            self.assertFalse(rl.allow("x", limit=1, window=60))

    def test_sliding_window_partial_expiry(self):
        rl = self._make()
        t = [0.0]

        def fake_monotonic():
            return t[0]

        with self._patched_env(), patch("jarvis.rate_limiter._time.monotonic", side_effect=fake_monotonic):
            rl.allow("k", limit=3, window=10)
            t[0] = 5.0
            rl.allow("k", limit=3, window=10)
            t[0] = 8.0
            rl.allow("k", limit=3, window=10)
            self.assertFalse(rl.allow("k", limit=3, window=10))
            t[0] = 11.0
            self.assertTrue(rl.allow("k", limit=3, window=10))
