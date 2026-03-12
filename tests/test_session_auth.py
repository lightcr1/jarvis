import unittest

from session_auth import bearer_token_from_header, enforce_token_capacity, is_token_active, prune_expired_tokens


class SessionAuthTests(unittest.TestCase):
    def test_bearer_token_parse(self):
        self.assertEqual(bearer_token_from_header("Bearer abc"), "abc")
        self.assertEqual(bearer_token_from_header("bearer xyz"), "xyz")
        self.assertIsNone(bearer_token_from_header("Token abc"))
        self.assertIsNone(bearer_token_from_header(None))

    def test_token_active_validation(self):
        tokens = {"tok": 200.0}
        self.assertTrue(is_token_active(tokens, "tok", now=100.0))
        self.assertTrue(is_token_active(tokens, "tok", now=200.0))
        self.assertFalse(is_token_active(tokens, "tok", now=201.0))
        self.assertFalse(is_token_active(tokens, None, now=100.0))
        self.assertFalse(is_token_active(tokens, "missing", now=100.0))

    def test_token_active_allows_empty_string_token_key_if_present(self):
        tokens = {"": 200.0}
        self.assertTrue(is_token_active(tokens, "", now=100.0))


    def test_token_active_accepts_zero_epoch_expiry_when_now_is_before_expiry(self):
        tokens = {"tok": 0.0}
        self.assertTrue(is_token_active(tokens, "tok", now=-1.0))
        self.assertTrue(is_token_active(tokens, "tok", now=0.0))


    def test_enforce_token_capacity_evicts_earliest_expiry_first(self):
        tokens = {
            "late": 300.0,
            "early": 100.0,
            "mid": 200.0,
        }

        removed = enforce_token_capacity(tokens, max_active=2)
        self.assertEqual(removed, 1)
        self.assertEqual(tokens, {"late": 300.0, "mid": 200.0})

    def test_enforce_token_capacity_clears_all_when_max_less_than_one(self):
        tokens = {"a": 1.0, "b": 2.0}
        removed = enforce_token_capacity(tokens, max_active=0)
        self.assertEqual(removed, 2)
        self.assertEqual(tokens, {})

    def test_prune_expired_tokens(self):
        tokens = {
            "expired-1": 99.0,
            "active": 101.0,
            "expired-2": 50.0,
        }
        removed = prune_expired_tokens(tokens, now=100.0)
        self.assertEqual(removed, 2)
        self.assertEqual(tokens, {"active": 101.0})


if __name__ == "__main__":
    unittest.main()
