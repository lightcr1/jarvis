import unittest

from session_auth import bearer_token_from_header, is_token_active


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


if __name__ == "__main__":
    unittest.main()
