import os
import time
import unittest
from unittest.mock import Mock

from fastapi import HTTPException

from jarvis.runtime_helpers import (
    chat_owner_key,
    env_int,
    normalize_filter,
    prepare_audit_filters,
    prune_identity_tokens,
    token_fingerprint,
    validate_actor_user_id_filter,
    validate_audit_query,
    validate_event_filter,
    validate_role_filter,
    validate_token_fingerprint_filter,
)


class RuntimeHelpersTests(unittest.TestCase):
    def test_chat_owner_key_prefers_user_session(self):
        owner, user_id = chat_owner_key(
            get_identity_session=lambda _token: {"user": {"id": "usr-123"}},
            x_jarvis_session="abc",
            x_jarvis_guest_key="guest-key",
        )
        self.assertEqual("user:usr-123", owner)
        self.assertEqual("usr-123", user_id)

    def test_chat_owner_key_falls_back_to_guest_key(self):
        owner, user_id = chat_owner_key(
            get_identity_session=lambda _token: None,
            x_jarvis_session=None,
            x_jarvis_guest_key="gk-abc",
        )
        self.assertEqual("guest:gk-abc", owner)
        self.assertIsNone(user_id)

    def test_chat_owner_key_anonymous_when_no_session_or_guest(self):
        owner, user_id = chat_owner_key(
            get_identity_session=lambda _token: None,
            x_jarvis_session=None,
            x_jarvis_guest_key=None,
        )
        self.assertEqual("guest:anonymous", owner)
        self.assertIsNone(user_id)

    def test_chat_owner_key_strips_whitespace_guest(self):
        owner, user_id = chat_owner_key(
            get_identity_session=lambda _token: None,
            x_jarvis_session=None,
            x_jarvis_guest_key="   ",
        )
        self.assertEqual("guest:anonymous", owner)

    def test_token_fingerprint_is_16_hex_chars(self):
        fingerprint = token_fingerprint("abc")
        self.assertEqual(16, len(fingerprint))
        self.assertRegex(fingerprint, r"^[0-9a-f]{16}$")

    def test_token_fingerprint_is_deterministic(self):
        self.assertEqual(token_fingerprint("test"), token_fingerprint("test"))

    def test_token_fingerprint_differs_for_different_tokens(self):
        self.assertNotEqual(token_fingerprint("aaa"), token_fingerprint("bbb"))

    def test_prepare_audit_filters_normalizes_and_validates(self):
        result = prepare_audit_filters(
            event=" admin_login ",
            role=" ADMIN ",
            actor_user_id=" usr-123456abcdef ",
            token_fingerprint=" abcdef1234567890 ",
            valid_roles={"admin", "user"},
        )
        self.assertEqual("admin_login", result["event"])
        self.assertEqual("admin", result["role"])
        self.assertEqual("usr-123456abcdef", result["actor_user_id"])

    def test_prepare_audit_filters_none_values_pass_through(self):
        result = prepare_audit_filters(
            event=None, role=None, actor_user_id=None, token_fingerprint=None,
            valid_roles={"admin"},
        )
        self.assertIsNone(result["event"])
        self.assertIsNone(result["role"])
        self.assertIsNone(result["actor_user_id"])

    def test_validate_audit_query_rejects_invalid_limit(self):
        with self.assertRaises(HTTPException):
            validate_audit_query(0, None, None)

    def test_validate_audit_query_rejects_limit_over_500(self):
        with self.assertRaises(HTTPException):
            validate_audit_query(501, None, None)

    def test_validate_audit_query_rejects_negative_since_ts(self):
        with self.assertRaises(HTTPException):
            validate_audit_query(10, -1, None)

    def test_validate_audit_query_rejects_since_greater_than_until(self):
        with self.assertRaises(HTTPException):
            validate_audit_query(10, 1000, 500)

    def test_validate_audit_query_accepts_valid_range(self):
        validate_audit_query(100, 0, 9999)  # should not raise


class ValidatorTests(unittest.TestCase):
    def test_env_int_returns_default_on_missing_var(self):
        os.environ.pop("__TEST_ENV_INT__", None)
        self.assertEqual(42, env_int("__TEST_ENV_INT__", default=42))

    def test_env_int_returns_parsed_value(self):
        os.environ["__TEST_ENV_INT__"] = "99"
        try:
            self.assertEqual(99, env_int("__TEST_ENV_INT__", default=0))
        finally:
            del os.environ["__TEST_ENV_INT__"]

    def test_env_int_returns_default_on_invalid_string(self):
        os.environ["__TEST_ENV_INT__"] = "not-a-number"
        try:
            self.assertEqual(5, env_int("__TEST_ENV_INT__", default=5))
        finally:
            del os.environ["__TEST_ENV_INT__"]

    def test_env_int_enforces_minimum(self):
        os.environ["__TEST_ENV_INT__"] = "1"
        try:
            self.assertEqual(10, env_int("__TEST_ENV_INT__", default=0, minimum=10))
        finally:
            del os.environ["__TEST_ENV_INT__"]

    def test_normalize_filter_strips_whitespace(self):
        self.assertEqual("hello", normalize_filter("  hello  "))

    def test_normalize_filter_returns_none_for_empty(self):
        self.assertIsNone(normalize_filter("   "))

    def test_normalize_filter_returns_none_for_none(self):
        self.assertIsNone(normalize_filter(None))

    def test_validate_token_fingerprint_valid(self):
        validate_token_fingerprint_filter("abcdef0123456789")  # should not raise

    def test_validate_token_fingerprint_invalid(self):
        with self.assertRaises(HTTPException):
            validate_token_fingerprint_filter("UPPERCASE1234567")

    def test_validate_token_fingerprint_too_short(self):
        with self.assertRaises(HTTPException):
            validate_token_fingerprint_filter("abc")

    def test_validate_actor_user_id_valid_format(self):
        validate_actor_user_id_filter("usr-123456abcdef")  # should not raise

    def test_validate_actor_user_id_bootstrap(self):
        validate_actor_user_id_filter("bootstrap")  # special case, should not raise

    def test_validate_actor_user_id_invalid(self):
        with self.assertRaises(HTTPException):
            validate_actor_user_id_filter("bad-format")

    def test_validate_role_filter_valid_role(self):
        validate_role_filter("admin", valid_roles={"admin", "user"})  # should not raise

    def test_validate_role_filter_invalid_role(self):
        with self.assertRaises(HTTPException):
            validate_role_filter("overlord", valid_roles={"admin", "user"})

    def test_validate_event_filter_valid(self):
        validate_event_filter("admin_login")  # should not raise

    def test_validate_event_filter_invalid_chars(self):
        with self.assertRaises(HTTPException):
            validate_event_filter("bad-event!")

    def test_validate_event_filter_too_long(self):
        with self.assertRaises(HTTPException):
            validate_event_filter("a" * 65)


class PruneIdentityTokensTests(unittest.TestCase):
    def test_prune_removes_expired_tokens(self):
        tokens = {
            "expired": {"exp": time.time() - 100},
            "valid": {"exp": time.time() + 3600},
        }
        pruned = prune_identity_tokens(tokens)
        self.assertEqual(1, pruned)
        self.assertNotIn("expired", tokens)
        self.assertIn("valid", tokens)

    def test_prune_returns_zero_when_nothing_expired(self):
        tokens = {"valid": {"exp": time.time() + 3600}}
        pruned = prune_identity_tokens(tokens)
        self.assertEqual(0, pruned)

    def test_prune_empty_dict(self):
        tokens = {}
        self.assertEqual(0, prune_identity_tokens(tokens))


if __name__ == "__main__":
    unittest.main()
