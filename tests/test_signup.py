"""Tests for self-service signup: email verification flow, security invariants, edge cases."""
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import jarvisappv4
from jarvis.pending_signup_store import (
    PendingSignupStore,
    SignupCodeExpired,
    SignupCodeInvalid,
    SignupCodeLocked,
)
from jarvis.admin_password_store import AdminPasswordStore


# ── PendingSignupStore unit tests ─────────────────────────────────────────────

class PendingSignupStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(self.tmpdir.name, "users.json")
        self.store = PendingSignupStore()
        self.cred = AdminPasswordStore.hash_password("s3cur3", rounds=1)

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("JARVIS_USER_STORE_PATH", None)

    def test_generate_code_is_six_digits(self):
        code = PendingSignupStore.generate_code()
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())

    def test_put_and_get(self):
        self.store.put("Test@Example.com", "alice", self.cred, "123456")
        rec = self.store.get("test@example.com")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["username"], "alice")
        self.assertEqual(rec["email"], "test@example.com")

    def test_get_normalizes_email_case(self):
        self.store.put("USER@EXAMPLE.COM", "bob", self.cred, "111111")
        self.assertIsNotNone(self.store.get("user@example.com"))

    def test_no_plaintext_code_stored(self):
        self.store.put("x@y.com", "user", self.cred, "999999")
        rec = self.store.get("x@y.com")
        self.assertNotIn("code", rec)
        self.assertIn("code_hash", rec)
        self.assertNotEqual(rec["code_hash"], "999999")

    def test_no_plaintext_password_stored(self):
        self.store.put("x@y.com", "user", self.cred, "000000")
        rec = self.store.get("x@y.com")
        # cred is the precomputed hash dict, never the raw password string
        self.assertIn("salt", rec["cred"])
        self.assertIn("hash", rec["cred"])
        self.assertNotIn("password", rec)

    def test_verify_code_correct(self):
        code = PendingSignupStore.generate_code()
        self.store.put("a@b.com", "alice", self.cred, code)
        rec = self.store.verify_code("a@b.com", code)
        self.assertEqual(rec["username"], "alice")

    def test_verify_code_wrong_raises(self):
        self.store.put("a@b.com", "alice", self.cred, "123456")
        with self.assertRaises(SignupCodeInvalid):
            self.store.verify_code("a@b.com", "000000")

    def test_wrong_code_increments_attempts(self):
        self.store.put("a@b.com", "alice", self.cred, "123456")
        try:
            self.store.verify_code("a@b.com", "000000")
        except SignupCodeInvalid:
            pass
        rec = self.store.get("a@b.com")
        self.assertEqual(rec["attempts"], 1)

    def test_exceeding_max_attempts_locks(self):
        self.store.put("a@b.com", "alice", self.cred, "123456")
        for _ in range(PendingSignupStore.MAX_ATTEMPTS):
            try:
                self.store.verify_code("a@b.com", "000000")
            except (SignupCodeInvalid, SignupCodeLocked):
                pass
        with self.assertRaises(SignupCodeLocked):
            self.store.verify_code("a@b.com", "123456")

    def test_expired_code_raises(self):
        code = PendingSignupStore.generate_code()
        self.store.put("a@b.com", "alice", self.cred, code)
        self.store.data["a@b.com"]["expires_at"] = int(time.time()) - 1
        with self.assertRaises(SignupCodeExpired):
            self.store.verify_code("a@b.com", code)

    def test_missing_email_raises(self):
        with self.assertRaises(SignupCodeInvalid):
            self.store.verify_code("no@one.com", "000000")

    def test_delete_removes_record(self):
        self.store.put("d@e.com", "dave", self.cred, "111111")
        self.store.delete("d@e.com")
        self.assertIsNone(self.store.get("d@e.com"))

    def test_prune_expired_removes_old_records(self):
        # Add the "live" record first so put() doesn't prune anything yet
        self.store.put("new@x.com", "new", self.cred, "222222")
        # Then inject the expired record directly (bypassing put which would prune it)
        self.store.data["old@x.com"] = {
            "email": "old@x.com", "username": "old", "cred": self.cred,
            "code_hash": "x", "attempts": 0,
            "expires_at": int(time.time()) - 10, "created_at": int(time.time()) - 20,
        }
        pruned = self.store.prune_expired()
        self.assertEqual(pruned, 1)
        self.assertIsNone(self.store.get("old@x.com"))
        self.assertIsNotNone(self.store.get("new@x.com"))


# ── AdminPasswordStore.hash_password + set_record ─────────────────────────────

class AdminPasswordStoreHashTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_ADMIN_PASSWORD_STORE_PATH"] = os.path.join(self.tmpdir.name, "pw.json")
        self.store = AdminPasswordStore()

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("JARVIS_ADMIN_PASSWORD_STORE_PATH", None)

    def test_hash_password_returns_dict(self):
        rec = AdminPasswordStore.hash_password("mypassword", rounds=1)
        self.assertIn("salt", rec)
        self.assertIn("hash", rec)
        self.assertEqual(rec["rounds"], 1)

    def test_set_record_then_verify(self):
        rec = AdminPasswordStore.hash_password("secret99", rounds=1)
        self.store.set_record("usr-abc", rec)
        self.assertTrue(self.store.verify_password("usr-abc", "secret99"))
        self.assertFalse(self.store.verify_password("usr-abc", "wrong"))

    def test_set_password_still_works(self):
        self.store.set_password("usr-xyz", "old-pass", rounds=1)
        self.assertTrue(self.store.verify_password("usr-xyz", "old-pass"))


# ── Signup API endpoint tests ─────────────────────────────────────────────────

def _make_client(tmpdir: str) -> TestClient:
    base = tmpdir
    os.environ["JARVIS_PASSPHRASE"] = "test-pass"
    os.environ["JARVIS_AUDIT_LOG_PATH"] = os.path.join(base, "audit.log")
    os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
    os.environ["JARVIS_ADMIN_PASSWORD_STORE_PATH"] = os.path.join(base, "admin_passwords.json")
    os.environ["JARVIS_USER_PREFERENCES_PATH"] = os.path.join(base, "user_preferences.json")
    os.environ["RESEND_API_KEY"] = "test-key"
    os.environ["JARVIS_EMAIL_FROM"] = "test@jarvis.local"

    from jarvis.audit_log_store import AuditLogStore
    from jarvis.user_store import UserStore
    from jarvis.admin_password_store import AdminPasswordStore as _APS
    from jarvis.user_preferences_store import UserPreferencesStore
    from jarvis.pending_signup_store import PendingSignupStore as _PSS

    jarvisappv4.audit_log = AuditLogStore()
    jarvisappv4.user_store = UserStore()
    jarvisappv4.admin_password_store = _APS()
    jarvisappv4.user_preferences_store = UserPreferencesStore()
    jarvisappv4.pending_signup_store = _PSS()
    jarvisappv4._identity_tokens.clear()

    return TestClient(jarvisappv4.app)


class SignupConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.client = _make_client(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()
        for k in ("RESEND_API_KEY", "JARVIS_EMAIL_FROM", "JARVIS_SIGNUP_ENABLED"):
            os.environ.pop(k, None)

    def test_config_enabled_when_keys_set(self):
        res = self.client.get("/auth/signup/config")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["enabled"])

    def test_config_disabled_when_api_key_missing(self):
        os.environ.pop("RESEND_API_KEY", None)
        res = self.client.get("/auth/signup/config")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["enabled"])

    def test_config_disabled_when_signup_env_off(self):
        os.environ["JARVIS_SIGNUP_ENABLED"] = "0"
        res = self.client.get("/auth/signup/config")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["enabled"])


class SignupHappyPathTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.client = _make_client(self.tmpdir.name)
        self._sent_codes: list[str] = []

        def fake_send(to: str, code: str) -> None:
            self._sent_codes.append(code)

        self.patcher = patch("jarvis.api_auth_chat._send_verification_email", side_effect=fake_send)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmpdir.cleanup()
        for k in ("RESEND_API_KEY", "JARVIS_EMAIL_FROM"):
            os.environ.pop(k, None)

    def _signup(self, username="alice", email="alice@example.com", password="pass1234") -> str:
        res = self.client.post("/auth/signup", json={"username": username, "email": email, "password": password})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["email"], email)
        return email

    def test_signup_request_triggers_email(self):
        self._signup()
        self.assertEqual(len(self._sent_codes), 1)

    def test_verify_correct_code_creates_user(self):
        email = self._signup()
        code = self._sent_codes[-1]
        res = self.client.post("/auth/signup/verify", json={"email": email, "code": code})
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertIn("session_token", body)
        self.assertEqual(body["user"]["username"], "alice")
        self.assertEqual(body["user"]["role"], "standard_user")

    def test_verify_creates_enabled_standard_user(self):
        email = self._signup()
        code = self._sent_codes[-1]
        self.client.post("/auth/signup/verify", json={"email": email, "code": code})
        user = jarvisappv4.user_store.find_by_username("alice")
        self.assertIsNotNone(user)
        self.assertTrue(user["enabled"])
        self.assertEqual(user["role"], "standard_user")
        self.assertEqual(user.get("email"), "alice@example.com")

    def test_verify_password_is_pbkdf2_not_plaintext(self):
        email = self._signup()
        code = self._sent_codes[-1]
        self.client.post("/auth/signup/verify", json={"email": email, "code": code})
        user = jarvisappv4.user_store.find_by_username("alice")
        self.assertTrue(jarvisappv4.admin_password_store.verify_password(user["id"], "pass1234"))
        self.assertFalse(jarvisappv4.admin_password_store.verify_password(user["id"], "wrongpass"))

    def test_session_is_usable_immediately(self):
        email = self._signup()
        code = self._sent_codes[-1]
        body = self.client.post("/auth/signup/verify", json={"email": email, "code": code}).json()
        token = body["session_token"]
        me = self.client.get("/auth/me", headers={"X-Jarvis-Session": token})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"]["username"], "alice")

    def test_pending_record_cleaned_up_after_verify(self):
        email = self._signup()
        code = self._sent_codes[-1]
        self.client.post("/auth/signup/verify", json={"email": email, "code": code})
        self.assertIsNone(jarvisappv4.pending_signup_store.get(email))

    def test_resend_replaces_code(self):
        email = self._signup()
        old_code = self._sent_codes[-1]
        res = self.client.post("/auth/signup/resend", json={"email": email})
        self.assertEqual(res.status_code, 200)
        new_code = self._sent_codes[-1]
        self.assertNotEqual(old_code, new_code)
        # old code should now be invalid
        res2 = self.client.post("/auth/signup/verify", json={"email": email, "code": old_code})
        self.assertIn(res2.status_code, (400, 410, 429))
        # new code works
        res3 = self.client.post("/auth/signup/verify", json={"email": email, "code": new_code})
        self.assertEqual(res3.status_code, 200)


class SignupValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.client = _make_client(self.tmpdir.name)
        self.patcher = patch("jarvis.api_auth_chat._send_verification_email")
        self.mock_send = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmpdir.cleanup()
        for k in ("RESEND_API_KEY", "JARVIS_EMAIL_FROM"):
            os.environ.pop(k, None)

    def test_short_username_rejected(self):
        res = self.client.post("/auth/signup", json={"username": "ab", "email": "x@y.com", "password": "pass1234"})
        self.assertEqual(res.status_code, 422)

    def test_short_password_rejected(self):
        res = self.client.post("/auth/signup", json={"username": "alice", "email": "x@y.com", "password": "12345"})
        self.assertEqual(res.status_code, 422)

    def test_invalid_email_rejected(self):
        res = self.client.post("/auth/signup", json={"username": "alice", "email": "not-an-email", "password": "pass1234"})
        self.assertEqual(res.status_code, 422)

    def test_duplicate_username_rejected(self):
        self.client.post("/auth/signup", json={"username": "alice", "email": "a@x.com", "password": "pass1234"})
        res = self.client.post("/auth/signup", json={"username": "alice", "email": "b@x.com", "password": "pass1234"})
        self.assertEqual(res.status_code, 409)

    def test_duplicate_email_rejected(self):
        self.client.post("/auth/signup", json={"username": "alice", "email": "same@x.com", "password": "pass1234"})
        res = self.client.post("/auth/signup", json={"username": "bob", "email": "same@x.com", "password": "pass1234"})
        self.assertEqual(res.status_code, 409)

    def test_wrong_code_returns_400(self):
        self.client.post("/auth/signup", json={"username": "alice", "email": "a@x.com", "password": "pass1234"})
        res = self.client.post("/auth/signup/verify", json={"email": "a@x.com", "code": "000000"})
        self.assertEqual(res.status_code, 400)

    def test_invalid_code_format_rejected(self):
        res = self.client.post("/auth/signup/verify", json={"email": "a@x.com", "code": "abc123"})
        self.assertEqual(res.status_code, 422)

    def test_expired_code_returns_410(self):
        self.client.post("/auth/signup", json={"username": "alice", "email": "a@x.com", "password": "pass1234"})
        rec = jarvisappv4.pending_signup_store.get("a@x.com")
        code_hash = rec["code_hash"]
        # Patch a known code that matches the hash... instead just inject expired_at
        jarvisappv4.pending_signup_store.data["a@x.com"]["expires_at"] = int(time.time()) - 1
        # We don't know the plaintext code here — just verify the 410 for expired
        # We use a forced path: set the record with a known code
        from jarvis.admin_password_store import AdminPasswordStore
        cred = AdminPasswordStore.hash_password("pass", rounds=1)
        jarvisappv4.pending_signup_store.put("exp@x.com", "expuser", cred, "123456")
        jarvisappv4.pending_signup_store.data["exp@x.com"]["expires_at"] = int(time.time()) - 1
        res = self.client.post("/auth/signup/verify", json={"email": "exp@x.com", "code": "123456"})
        self.assertEqual(res.status_code, 410)

    def test_resend_for_unknown_email_returns_404(self):
        res = self.client.post("/auth/signup/resend", json={"email": "nobody@x.com"})
        self.assertEqual(res.status_code, 404)

    def test_signup_disabled_when_no_api_key(self):
        os.environ.pop("RESEND_API_KEY", None)
        res = self.client.post("/auth/signup", json={"username": "alice", "email": "a@x.com", "password": "pass1234"})
        self.assertEqual(res.status_code, 503)

    def test_already_existing_user_email_rejected(self):
        # Create a real user with that email, then try signing up with it
        jarvisappv4.user_store.create_user("existing", email="taken@x.com")
        res = self.client.post("/auth/signup", json={"username": "newuser", "email": "taken@x.com", "password": "pass1234"})
        self.assertEqual(res.status_code, 409)


if __name__ == "__main__":
    unittest.main()
