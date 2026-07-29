import os
import tempfile
import unittest

from fastapi.testclient import TestClient

import jarvisappv4
from jarvis.authz import resolve_effective_permissions
from jarvis.email.service import EmailAccessError, EmailService
from jarvis.email.store import EmailDraftStore, EmailMessageStore
from jarvis.group_store import GroupStore
from jarvis.integration_credentials import IntegrationCredentialStore
from jarvis.jarvis_engine import normalize_role
from jarvis.membership_store import MembershipStore
from jarvis.permission_store import KNOWN_PERMISSIONS
from jarvis.permission_store import PermissionStore
from jarvis.secret_crypto import generate_master_key
from jarvis.user_store import UserStore


class _AuditLogProbe:
    def __init__(self):
        self.events = []

    def write(self, event: str, payload: dict):
        self.events.append({"event": event, **payload})


class FakeImapSmtpClient:
    def __init__(self):
        self.inbox = [
            {"uid": "1", "folder": "INBOX", "subject": "Welcome", "sender": "Alice <alice@example.com>", "date": 1000, "read": False},
            {"uid": "2", "folder": "INBOX", "subject": "Invoice", "sender": "Billing <billing@example.com>", "date": 2000, "read": True},
        ]
        self.bodies = {"1": "Hello and welcome to the service.", "2": "Your invoice is attached."}
        self.marked_read: list[str] = []
        self.sent_messages: list[dict] = []
        self.fail_send = False

    def fetch_recent_messages(self, folder="INBOX", limit=20):
        return [m for m in self.inbox if m["folder"] == folder][:limit]

    def fetch_message_body(self, uid, folder="INBOX"):
        return self.bodies.get(uid)

    def mark_read(self, uid, folder="INBOX"):
        self.marked_read.append(uid)
        return True

    def send_message(self, to, subject, body, in_reply_to=None):
        if self.fail_send:
            return False
        self.sent_messages.append({"to": to, "subject": subject, "body": body, "in_reply_to": in_reply_to})
        return True

    def test_connection(self):
        return True


class EmailStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_EMAIL_STORE_PATH"] = os.path.join(self.tmpdir.name, "email_messages.json")
        os.environ["JARVIS_EMAIL_DRAFTS_STORE_PATH"] = os.path.join(self.tmpdir.name, "email_drafts.json")
        self.messages = EmailMessageStore()
        self.drafts = EmailDraftStore()

    def tearDown(self):
        os.environ.pop("JARVIS_EMAIL_STORE_PATH", None)
        os.environ.pop("JARVIS_EMAIL_DRAFTS_STORE_PATH", None)
        self.tmpdir.cleanup()

    def test_known_permissions_include_email_tuple(self):
        self.assertIn("email.read", KNOWN_PERMISSIONS)
        self.assertIn("email.write", KNOWN_PERMISSIONS)

    def test_upsert_messages_dedupes_by_uid(self):
        fetched = [{"uid": "1", "subject": "Hi", "sender": "a@x.com", "date": 100, "read": False}]
        self.messages.upsert_messages("u1", "INBOX", fetched)
        self.messages.upsert_messages("u1", "INBOX", [{"uid": "1", "subject": "Hi (updated)", "sender": "a@x.com", "date": 100, "read": True}])
        listed = self.messages.list_messages("u1")
        self.assertEqual(1, len(listed))
        self.assertEqual("Hi (updated)", listed[0]["subject"])
        self.assertTrue(listed[0]["read"])

    def test_set_read_and_summary(self):
        entries = self.messages.upsert_messages("u1", "INBOX", [{"uid": "1", "subject": "Hi", "sender": "a@x.com", "date": 100, "read": False}])
        message_id = entries[0]["id"]
        self.messages.set_read(message_id, True)
        self.assertTrue(self.messages.get_message(message_id)["read"])
        self.messages.set_summary(message_id, "A short summary")
        self.assertEqual("A short summary", self.messages.get_message(message_id)["summary"])

    def test_unread_only_filter(self):
        self.messages.upsert_messages("u1", "INBOX", [
            {"uid": "1", "subject": "A", "sender": "a@x.com", "date": 100, "read": False},
            {"uid": "2", "subject": "B", "sender": "b@x.com", "date": 200, "read": True},
        ])
        unread = self.messages.list_messages("u1", unread_only=True)
        self.assertEqual(1, len(unread))
        self.assertEqual("A", unread[0]["subject"])

    def test_draft_add_list_update(self):
        draft = self.drafts.add_draft({"user_id": "u1", "to": "x@y.com", "subject": "Hi", "body": "Body", "status": "pending_approval", "created_at": 1})
        self.assertEqual(1, len(self.drafts.list_drafts("u1")))
        updated = self.drafts.update_draft(draft["id"], {"status": "sent"})
        self.assertEqual("sent", updated["status"])
        self.assertEqual(0, len(self.drafts.list_drafts("u1", status="pending_approval")))

    def test_upsert_messages_scopes_dedup_by_account_id(self):
        fetched = [{"uid": "1", "subject": "Hi", "sender": "a@x.com", "date": 100, "read": False}]
        self.messages.upsert_messages("u1", "INBOX", fetched, account_id="acct-a")
        self.messages.upsert_messages("u1", "INBOX", fetched, account_id="acct-b")
        all_msgs = self.messages.list_messages("u1")
        self.assertEqual(2, len(all_msgs))
        scoped_a = self.messages.list_messages("u1", account_id="acct-a")
        self.assertEqual(1, len(scoped_a))
        self.assertEqual("acct-a", scoped_a[0]["account_id"])

    def test_legacy_message_without_account_id_backfilled_on_load(self):
        self.messages.data["messages"].append({"id": "mail-legacy", "user_id": "u1", "uid": "99", "folder": "INBOX", "subject": "Old", "sender": "x@y.com", "date": 1, "read": False, "summary": None, "synced_at": 1})
        self.messages._save()
        reloaded = EmailMessageStore()
        legacy = reloaded.get_message("mail-legacy")
        self.assertEqual("default", legacy["account_id"])
        # A same-account upsert with the same uid/folder must update in place, not duplicate.
        reloaded.upsert_messages("u1", "INBOX", [{"uid": "99", "subject": "Old (updated)", "sender": "x@y.com", "date": 1, "read": True}], account_id="default")
        self.assertEqual(1, len(reloaded.list_messages("u1")))
        self.assertEqual("Old (updated)", reloaded.list_messages("u1")[0]["subject"])

    def test_list_drafts_filtered_by_account_id(self):
        self.drafts.add_draft({"user_id": "u1", "account_id": "acct-a", "to": "x@y.com", "subject": "A", "body": "B", "status": "pending_approval", "created_at": 1})
        self.drafts.add_draft({"user_id": "u1", "account_id": "acct-b", "to": "x@y.com", "subject": "C", "body": "D", "status": "pending_approval", "created_at": 2})
        self.assertEqual(2, len(self.drafts.list_drafts("u1")))
        self.assertEqual(1, len(self.drafts.list_drafts("u1", account_id="acct-a")))


class EmailServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(base, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_EMAIL_STORE_PATH"] = os.path.join(base, "email_messages.json")
        os.environ["JARVIS_EMAIL_DRAFTS_STORE_PATH"] = os.path.join(base, "email_drafts.json")
        os.environ["JARVIS_SECRET_KEY"] = generate_master_key()
        os.environ["JARVIS_INTEGRATION_CREDENTIALS_PATH"] = os.path.join(base, "creds.json")

        self.user_store = UserStore()
        self.group_store = GroupStore()
        self.membership_store = MembershipStore()
        self.permission_store = PermissionStore()
        self.message_store = EmailMessageStore()
        self.draft_store = EmailDraftStore()
        self.credential_store = IntegrationCredentialStore()
        self.audit_probe = _AuditLogProbe()
        self.fake_client = FakeImapSmtpClient()
        self.service = EmailService(
            message_store=self.message_store,
            draft_store=self.draft_store,
            credential_store=self.credential_store,
            user_store=self.user_store,
            membership_store=self.membership_store,
            permission_store=self.permission_store,
            resolve_effective_permissions=resolve_effective_permissions,
            normalize_role=normalize_role,
            audit_log=self.audit_probe,
            client_factory=lambda creds: self.fake_client,
        )

    def tearDown(self):
        for key in ("JARVIS_EMERGENCY_STOP", "JARVIS_SECRET_KEY", "JARVIS_INTEGRATION_CREDENTIALS_PATH"):
            os.environ.pop(key, None)
        self.tmpdir.cleanup()

    def _configured_user(self, username="alice", perms=("email.read", "email.write")):
        user = self.user_store.create_user(username, role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], list(perms))
        self.service.set_credentials({
            "imap_host": "imap.example.com", "imap_port": "993", "imap_username": "u", "imap_password": "p",
            "smtp_host": "smtp.example.com", "smtp_port": "587", "smtp_username": "u", "smtp_password": "p",
        }, user_id=user["id"], role=user["role"])
        return user

    def test_standard_user_denied_without_permission(self):
        user = self.user_store.create_user("bob", role="standard_user", enabled=True)
        with self.assertRaises(EmailAccessError):
            self.service.list_messages(user_id=user["id"], role=user["role"])

    def test_sync_without_credentials_raises_lookup_error(self):
        user = self.user_store.create_user("carol", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["email.read", "email.write"])
        with self.assertRaises(LookupError):
            self.service.sync_inbox(user_id=user["id"], role=user["role"])

    def test_sync_populates_store_and_unread_filter(self):
        user = self._configured_user()
        result = self.service.sync_inbox(user_id=user["id"], role=user["role"])
        self.assertEqual(2, result["synced_count"])
        unread = self.service.list_messages(user_id=user["id"], role=user["role"], unread_only=True)["messages"]
        self.assertEqual(1, len(unread))
        self.assertEqual("Welcome", unread[0]["subject"])

    def test_fetch_body_live_not_persisted(self):
        user = self._configured_user()
        self.service.sync_inbox(user_id=user["id"], role=user["role"])
        message = self.service.list_messages(user_id=user["id"], role=user["role"])["messages"][0]
        fetched = self.service.fetch_body(message["id"], user_id=user["id"], role=user["role"])
        self.assertIn(fetched["body"], self.fake_client.bodies.values())
        # Body is never written back into the metadata cache.
        stored = self.message_store.get_message(message["id"])
        self.assertNotIn("body", stored)

    def test_mark_read_updates_store_and_calls_client(self):
        user = self._configured_user()
        self.service.sync_inbox(user_id=user["id"], role=user["role"])
        unread = self.service.list_messages(user_id=user["id"], role=user["role"], unread_only=True)["messages"][0]
        self.service.mark_read(unread["id"], user_id=user["id"], role=user["role"])
        self.assertIn(unread["uid"], self.fake_client.marked_read)
        self.assertTrue(self.message_store.get_message(unread["id"])["read"])

    def test_create_draft_requires_to_and_body(self):
        user = self._configured_user()
        with self.assertRaises(ValueError):
            self.service.create_draft({"to": "", "body": "x"}, user_id=user["id"], role=user["role"])

    def test_send_draft_requires_explicit_confirm(self):
        user = self._configured_user()
        draft = self.service.create_draft({"to": "x@y.com", "subject": "Hi", "body": "Body text"}, user_id=user["id"], role=user["role"])["draft"]
        first = self.service.send_draft(draft["id"], user_id=user["id"], role=user["role"], confirm=False)
        self.assertEqual("confirmation_required", first["status"])
        self.assertEqual(0, len(self.fake_client.sent_messages))

        second = self.service.send_draft(draft["id"], user_id=user["id"], role=user["role"], confirm=True)
        self.assertEqual("sent", second["status"])
        self.assertEqual(1, len(self.fake_client.sent_messages))
        self.assertEqual("sent", self.draft_store.get_draft(draft["id"])["status"])

    def test_emergency_stop_blocks_send_even_with_confirm(self):
        user = self._configured_user()
        draft = self.service.create_draft({"to": "x@y.com", "subject": "Hi", "body": "Body text"}, user_id=user["id"], role=user["role"])["draft"]
        os.environ["JARVIS_EMERGENCY_STOP"] = "1"
        with self.assertRaises(PermissionError):
            self.service.send_draft(draft["id"], user_id=user["id"], role=user["role"], confirm=True)
        self.assertEqual(0, len(self.fake_client.sent_messages))

    def test_discard_draft_only_from_pending(self):
        user = self._configured_user()
        draft = self.service.create_draft({"to": "x@y.com", "subject": "Hi", "body": "Body text"}, user_id=user["id"], role=user["role"])["draft"]
        discarded = self.service.discard_draft(draft["id"], user_id=user["id"], role=user["role"])
        self.assertEqual("discarded", discarded["draft"]["status"])
        with self.assertRaises(ValueError):
            self.service.discard_draft(draft["id"], user_id=user["id"], role=user["role"])

    def test_users_isolated_on_messages_and_drafts(self):
        alice = self._configured_user("alice2")
        self.service.sync_inbox(user_id=alice["id"], role=alice["role"])
        bob = self._configured_user("bob2")
        bob_messages = self.service.list_messages(user_id=bob["id"], role=bob["role"])["messages"]
        self.assertEqual(0, len(bob_messages))

        alice_draft = self.service.create_draft({"to": "x@y.com", "subject": "S", "body": "B"}, user_id=alice["id"], role=alice["role"])["draft"]
        with self.assertRaises(LookupError):
            self.service.discard_draft(alice_draft["id"], user_id=bob["id"], role=bob["role"])

    def test_send_failure_raises_runtime_error(self):
        user = self._configured_user()
        self.fake_client.fail_send = True
        draft = self.service.create_draft({"to": "x@y.com", "subject": "Hi", "body": "Body text"}, user_id=user["id"], role=user["role"])["draft"]
        with self.assertRaises(RuntimeError):
            self.service.send_draft(draft["id"], user_id=user["id"], role=user["role"], confirm=True)

    def test_add_account_creates_non_default_account_and_lists_it(self):
        user = self._configured_user()  # already has a "default" primary account
        result = self.service.add_account({
            "imap_host": "imap2.example.com", "imap_port": "993", "imap_username": "u2", "imap_password": "p2",
            "smtp_host": "smtp2.example.com", "smtp_port": "587", "smtp_username": "u2", "smtp_password": "p2",
        }, "Personal", user_id=user["id"], role=user["role"])
        account_id = result["account"]["account_id"]
        self.assertNotEqual("default", account_id)
        accounts = self.service.list_accounts(user_id=user["id"], role=user["role"])["accounts"]
        self.assertEqual(2, len(accounts))
        labels = {a["account_id"]: a["label"] for a in accounts}
        self.assertEqual("Personal", labels[account_id])

    def test_second_account_not_primary_until_promoted(self):
        user = self._configured_user()
        result = self.service.add_account({
            "imap_host": "h", "imap_port": "1", "imap_username": "u", "imap_password": "p",
            "smtp_host": "h", "smtp_port": "1", "smtp_username": "u", "smtp_password": "p",
        }, "Second", user_id=user["id"], role=user["role"])
        account_id = result["account"]["account_id"]
        accounts = {a["account_id"]: a for a in self.service.list_accounts(user_id=user["id"], role=user["role"])["accounts"]}
        self.assertTrue(accounts["default"]["is_primary"])
        self.assertFalse(accounts[account_id]["is_primary"])
        self.service.set_primary_account(account_id, user_id=user["id"], role=user["role"])
        accounts = {a["account_id"]: a for a in self.service.list_accounts(user_id=user["id"], role=user["role"])["accounts"]}
        self.assertTrue(accounts[account_id]["is_primary"])
        self.assertFalse(accounts["default"]["is_primary"])

    def test_sync_inbox_with_explicit_account_id_scopes_upsert(self):
        user = self._configured_user()
        self.service.add_account({
            "imap_host": "h", "imap_port": "1", "imap_username": "u", "imap_password": "p",
            "smtp_host": "h", "smtp_port": "1", "smtp_username": "u", "smtp_password": "p",
        }, "Second", user_id=user["id"], role=user["role"])
        result = self.service.sync_inbox(user_id=user["id"], role=user["role"], account_id="default")
        self.assertEqual("default", result["account_id"])
        messages = self.message_store.list_messages(user["id"], account_id="default")
        self.assertEqual(2, len(messages))

    def test_sync_inbox_default_uses_primary_account(self):
        user = self._configured_user()
        result = self.service.sync_inbox(user_id=user["id"], role=user["role"])
        self.assertEqual("default", result["account_id"])

    def test_fetch_body_uses_message_own_account_not_current_primary(self):
        user = self._configured_user()
        second_client = FakeImapSmtpClient()
        second_client.bodies = {"1": "SECOND ACCOUNT BODY", "2": "SECOND ACCOUNT BODY 2"}

        def factory(creds):
            return second_client if creds.get("imap_username") == "second-user" else self.fake_client

        self.service.client_factory = factory
        added = self.service.add_account({
            "imap_host": "h2", "imap_port": "1", "imap_username": "second-user", "imap_password": "p",
            "smtp_host": "h2", "smtp_port": "1", "smtp_username": "second-user", "smtp_password": "p",
        }, "Second", user_id=user["id"], role=user["role"])
        second_account_id = added["account"]["account_id"]

        self.service.sync_inbox(user_id=user["id"], role=user["role"], account_id=second_account_id)
        self.service.set_primary_account(second_account_id, user_id=user["id"], role=user["role"])
        # Now sync the (no-longer-primary) default account's messages too, then fetch one of ITS messages.
        self.service.sync_inbox(user_id=user["id"], role=user["role"], account_id="default")
        default_message = self.message_store.list_messages(user["id"], account_id="default")[0]

        fetched = self.service.fetch_body(default_message["id"], user_id=user["id"], role=user["role"])
        self.assertIn(fetched["body"], self.fake_client.bodies.values())
        self.assertNotEqual("SECOND ACCOUNT BODY", fetched["body"])

    def test_delete_primary_account_auto_promotes_remaining_account(self):
        user = self._configured_user()
        result = self.service.add_account({
            "imap_host": "h", "imap_port": "1", "imap_username": "u", "imap_password": "p",
            "smtp_host": "h", "smtp_port": "1", "smtp_username": "u", "smtp_password": "p",
        }, "Second", user_id=user["id"], role=user["role"])
        second_id = result["account"]["account_id"]
        self.service.delete_account("default", user_id=user["id"], role=user["role"])
        accounts = self.service.list_accounts(user_id=user["id"], role=user["role"])["accounts"]
        self.assertEqual(1, len(accounts))
        self.assertEqual(second_id, accounts[0]["account_id"])
        self.assertTrue(accounts[0]["is_primary"])

    def test_delete_last_account_leaves_nothing_to_promote(self):
        user = self._configured_user()
        self.service.delete_account("default", user_id=user["id"], role=user["role"])
        accounts = self.service.list_accounts(user_id=user["id"], role=user["role"])["accounts"]
        self.assertEqual(0, len(accounts))

    def test_create_draft_stores_resolved_account_id(self):
        user = self._configured_user()
        draft = self.service.create_draft({"to": "x@y.com", "subject": "S", "body": "B"}, user_id=user["id"], role=user["role"])["draft"]
        self.assertEqual("default", draft["account_id"])

    def test_send_draft_uses_draft_own_account_id(self):
        user = self._configured_user()
        second_client = FakeImapSmtpClient()

        def factory(creds):
            return second_client if creds.get("imap_username") == "second-user" else self.fake_client

        self.service.client_factory = factory
        result = self.service.add_account({
            "imap_host": "h2", "imap_port": "1", "imap_username": "second-user", "imap_password": "p",
            "smtp_host": "h2", "smtp_port": "1", "smtp_username": "second-user", "smtp_password": "p",
        }, "Second", user_id=user["id"], role=user["role"])
        second_id = result["account"]["account_id"]
        self.service.set_primary_account(second_id, user_id=user["id"], role=user["role"])

        # Draft explicitly attached to "default" even though "second" is now primary.
        draft = self.service.create_draft({"to": "x@y.com", "subject": "S", "body": "B", "account_id": "default"}, user_id=user["id"], role=user["role"])["draft"]
        self.service.send_draft(draft["id"], user_id=user["id"], role=user["role"], confirm=True)
        self.assertEqual(1, len(self.fake_client.sent_messages))
        self.assertEqual(0, len(second_client.sent_messages))


class EmailApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(base, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_ADMIN_PASSWORD_STORE_PATH"] = os.path.join(base, "admin_passwords.json")
        os.environ["JARVIS_USER_PREFERENCES_PATH"] = os.path.join(base, "user_preferences.json")
        os.environ["JARVIS_EMAIL_STORE_PATH"] = os.path.join(base, "email_messages.json")
        os.environ["JARVIS_EMAIL_DRAFTS_STORE_PATH"] = os.path.join(base, "email_drafts.json")
        os.environ["JARVIS_SECRET_KEY"] = generate_master_key()
        os.environ["JARVIS_INTEGRATION_CREDENTIALS_PATH"] = os.path.join(base, "creds.json")

        jarvisappv4.user_store = jarvisappv4.UserStore()
        jarvisappv4.group_store = jarvisappv4.GroupStore()
        jarvisappv4.membership_store = jarvisappv4.MembershipStore()
        jarvisappv4.permission_store = jarvisappv4.PermissionStore()
        jarvisappv4.admin_password_store = jarvisappv4.AdminPasswordStore()
        jarvisappv4.user_preferences_store = jarvisappv4.UserPreferencesStore()

        self.fake_client = FakeImapSmtpClient()
        jarvisappv4.email_message_store = jarvisappv4.EmailMessageStore()
        jarvisappv4.email_draft_store = jarvisappv4.EmailDraftStore()
        jarvisappv4.integration_credential_store = jarvisappv4.IntegrationCredentialStore()
        jarvisappv4.email_service = jarvisappv4.EmailService(
            message_store=jarvisappv4.email_message_store,
            draft_store=jarvisappv4.email_draft_store,
            credential_store=jarvisappv4.integration_credential_store,
            user_store=jarvisappv4.user_store,
            membership_store=jarvisappv4.membership_store,
            permission_store=jarvisappv4.permission_store,
            resolve_effective_permissions=jarvisappv4.resolve_effective_permissions,
            normalize_role=jarvisappv4.normalize_role,
            audit_log=jarvisappv4.audit_log,
            client_factory=lambda creds: self.fake_client,
        )
        jarvisappv4._identity_tokens.clear()
        self.client = TestClient(jarvisappv4.app)

    def tearDown(self):
        os.environ.pop("JARVIS_SECRET_KEY", None)
        os.environ.pop("JARVIS_INTEGRATION_CREDENTIALS_PATH", None)
        self.tmpdir.cleanup()

    def _create_user_with_permissions(self, admin_token, admin_id, username, permissions):
        created = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {admin_token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={"username": username, "role": "standard_user", "enabled": True, "password": f"{username}-pass"},
        )
        user_id = created.json()["id"]
        self.client.put(
            f"/admin/permissions/users/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={"permissions": permissions},
        )
        login = self.client.post("/auth/login", json={"username": username, "password": f"{username}-pass"})
        return user_id, login.json()["session_token"]

    def test_full_lifecycle_via_api(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(admin["token"], admin["user_id"], "mailuser", ["email.read", "email.write"])
        headers = {"X-Jarvis-Session": session_token}

        set_creds = self.client.put("/email/credentials", headers=headers, json={
            "imap_host": "imap.example.com", "imap_port": "993", "imap_username": "u", "imap_password": "p",
            "smtp_host": "smtp.example.com", "smtp_port": "587", "smtp_username": "u", "smtp_password": "p",
        })
        self.assertEqual(200, set_creds.status_code)

        synced = self.client.post("/email/sync", headers=headers)
        self.assertEqual(200, synced.status_code)
        self.assertEqual(2, synced.json()["synced_count"])

        listed = self.client.get("/email/messages", headers=headers)
        self.assertEqual(2, len(listed.json()["messages"]))
        message_id = listed.json()["messages"][0]["id"]

        body = self.client.get(f"/email/messages/{message_id}/body", headers=headers)
        self.assertEqual(200, body.status_code)

        draft = self.client.post("/email/drafts", headers=headers, json={"to": "x@y.com", "subject": "Hi", "body": "Body text"})
        self.assertEqual(200, draft.status_code)
        draft_id = draft.json()["draft"]["id"]

        pending_send = self.client.post(f"/email/drafts/{draft_id}/send", headers=headers, json={"confirm": False})
        self.assertEqual(200, pending_send.status_code)
        self.assertEqual("confirmation_required", pending_send.json()["status"])

        confirmed_send = self.client.post(f"/email/drafts/{draft_id}/send", headers=headers, json={"confirm": True})
        self.assertEqual(200, confirmed_send.status_code)
        self.assertEqual("sent", confirmed_send.json()["status"])
        self.assertEqual(1, len(self.fake_client.sent_messages))

    def test_permission_denied_returns_403(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(admin["token"], admin["user_id"], "noperm2", [])
        denied = self.client.get("/email/messages", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(403, denied.status_code)

    def test_sync_without_credentials_returns_409(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(admin["token"], admin["user_id"], "nomailcreds", ["email.read", "email.write"])
        response = self.client.post("/email/sync", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(409, response.status_code)

    def test_emergency_stop_blocks_send_via_api(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(admin["token"], admin["user_id"], "estopuser", ["email.read", "email.write"])
        headers = {"X-Jarvis-Session": session_token}
        self.client.put("/email/credentials", headers=headers, json={
            "imap_host": "imap.example.com", "imap_port": "993", "imap_username": "u", "imap_password": "p",
            "smtp_host": "smtp.example.com", "smtp_port": "587", "smtp_username": "u", "smtp_password": "p",
        })
        draft = self.client.post("/email/drafts", headers=headers, json={"to": "x@y.com", "subject": "Hi", "body": "Body text"}).json()["draft"]
        os.environ["JARVIS_EMERGENCY_STOP"] = "1"
        try:
            response = self.client.post(f"/email/drafts/{draft['id']}/send", headers=headers, json={"confirm": True})
            self.assertEqual(403, response.status_code)
        finally:
            os.environ.pop("JARVIS_EMERGENCY_STOP", None)

    def test_accounts_lifecycle_via_api(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(admin["token"], admin["user_id"], "multiuser", ["email.read", "email.write"])
        headers = {"X-Jarvis-Session": session_token}

        self.client.put("/email/credentials", headers=headers, json={
            "imap_host": "imap.example.com", "imap_port": "993", "imap_username": "u", "imap_password": "p",
            "smtp_host": "smtp.example.com", "smtp_port": "587", "smtp_username": "u", "smtp_password": "p",
        })

        added = self.client.post("/email/accounts", headers=headers, json={
            "label": "Personal",
            "imap_host": "imap2.example.com", "imap_port": "993", "imap_username": "u2", "imap_password": "p2",
            "smtp_host": "smtp2.example.com", "smtp_port": "587", "smtp_username": "u2", "smtp_password": "p2",
        })
        self.assertEqual(200, added.status_code)
        account_id = added.json()["account"]["account_id"]

        listed = self.client.get("/email/accounts", headers=headers)
        self.assertEqual(200, listed.status_code)
        self.assertEqual(2, len(listed.json()["accounts"]))

        updated = self.client.put(f"/email/accounts/{account_id}", headers=headers, json={
            "label": "Personal (updated)",
            "imap_host": "imap3.example.com", "imap_port": "993", "imap_username": "u3", "imap_password": "p3",
            "smtp_host": "smtp3.example.com", "smtp_port": "587", "smtp_username": "u3", "smtp_password": "p3",
        })
        self.assertEqual(200, updated.status_code)

        primary = self.client.post(f"/email/accounts/{account_id}/primary", headers=headers)
        self.assertEqual(200, primary.status_code)
        self.assertEqual(account_id, primary.json()["primary_account_id"])

        deleted = self.client.delete(f"/email/accounts/{account_id}", headers=headers)
        self.assertEqual(200, deleted.status_code)
        self.assertTrue(deleted.json()["deleted"])
        remaining = self.client.get("/email/accounts", headers=headers).json()["accounts"]
        self.assertEqual(1, len(remaining))

    def test_add_account_requires_label_returns_400(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(admin["token"], admin["user_id"], "nolabeluser", ["email.read", "email.write"])
        headers = {"X-Jarvis-Session": session_token}
        response = self.client.post("/email/accounts", headers=headers, json={
            "imap_host": "h", "imap_port": "1", "imap_username": "u", "imap_password": "p",
            "smtp_host": "h", "smtp_port": "1", "smtp_username": "u", "smtp_password": "p",
        })
        self.assertEqual(400, response.status_code)

    def test_update_unknown_account_returns_404(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(admin["token"], admin["user_id"], "unknownacctuser", ["email.read", "email.write"])
        headers = {"X-Jarvis-Session": session_token}
        response = self.client.put("/email/accounts/does-not-exist", headers=headers, json={
            "label": "X",
            "imap_host": "h", "imap_port": "1", "imap_username": "u", "imap_password": "p",
            "smtp_host": "h", "smtp_port": "1", "smtp_username": "u", "smtp_password": "p",
        })
        self.assertEqual(404, response.status_code)

    def test_legacy_credentials_routes_still_operate_on_default_account_after_second_account_added(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(admin["token"], admin["user_id"], "legacyroutesuser", ["email.read", "email.write"])
        headers = {"X-Jarvis-Session": session_token}
        self.client.put("/email/credentials", headers=headers, json={
            "imap_host": "imap.example.com", "imap_port": "993", "imap_username": "u", "imap_password": "p",
            "smtp_host": "smtp.example.com", "smtp_port": "587", "smtp_username": "u", "smtp_password": "p",
        })
        self.client.post("/email/accounts", headers=headers, json={
            "label": "Second",
            "imap_host": "h2", "imap_port": "1", "imap_username": "u2", "imap_password": "p2",
            "smtp_host": "h2", "smtp_port": "1", "smtp_username": "u2", "smtp_password": "p2",
        })
        status = self.client.get("/email/credentials/status", headers=headers)
        self.assertTrue(status.json()["status"]["configured"])
        deleted = self.client.delete("/email/credentials", headers=headers)
        self.assertTrue(deleted.json()["deleted"])
        remaining = self.client.get("/email/accounts", headers=headers).json()["accounts"]
        self.assertEqual(1, len(remaining))
        self.assertEqual("Second", remaining[0]["label"])


if __name__ == "__main__":
    unittest.main()
