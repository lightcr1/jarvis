import unittest
from unittest.mock import Mock

from fastapi import HTTPException

from jarvis.runtime_helpers import (
    chat_owner_key,
    prepare_audit_filters,
    token_fingerprint,
    validate_audit_query,
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

    def test_token_fingerprint_is_16_hex_chars(self):
        fingerprint = token_fingerprint("abc")
        self.assertEqual(16, len(fingerprint))
        self.assertRegex(fingerprint, r"^[0-9a-f]{16}$")

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

    def test_validate_audit_query_rejects_invalid_limit(self):
        with self.assertRaises(HTTPException):
            validate_audit_query(0, None, None)


if __name__ == "__main__":
    unittest.main()
