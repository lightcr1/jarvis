import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import jarvisappv4


class AdminSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_PASSPHRASE"] = "test-pass"
        os.environ["JARVIS_AUDIT_LOG_PATH"] = os.path.join(base, "audit.log")
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(base, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_ADMIN_SETTINGS_PATH"] = os.path.join(base, "admin_settings.json")

        jarvisappv4.audit_log = jarvisappv4.AuditLogStore()
        jarvisappv4.user_store = jarvisappv4.UserStore()
        jarvisappv4.group_store = jarvisappv4.GroupStore()
        jarvisappv4.membership_store = jarvisappv4.MembershipStore()
        jarvisappv4.permission_store = jarvisappv4.PermissionStore()
        jarvisappv4.admin_settings_store = jarvisappv4.AdminSettingsStore()
        jarvisappv4._tokens.clear()

        self.client = TestClient(jarvisappv4.app)

    def tearDown(self):
        self.tmpdir.cleanup()
        for key in [
            "JARVIS_PASSPHRASE",
            "JARVIS_AUDIT_LOG_PATH",
            "JARVIS_USER_STORE_PATH",
            "JARVIS_GROUP_STORE_PATH",
            "JARVIS_MEMBERSHIP_STORE_PATH",
            "JARVIS_PERMISSION_STORE_PATH",
            "JARVIS_ADMIN_SETTINGS_PATH",
            "JARVIS_TOKEN_TTL_MIN",
            "JARVIS_MAX_ACTIVE_TOKENS",
            "JARVIS_WAKEWORD_ENABLED",
            "JARVIS_WAKEWORD_PHRASE",
            "STT_PROVIDER",
            "JARVIS_HOME_ASSISTANT_CONFIRMATION_TTL_SEC",
            "JARVIS_HOME_ASSISTANT_REMOTE_ALLOWED_CIDRS",
        ]:
            os.environ.pop(key, None)

    def _unlock(self) -> str:
        res = self.client.post("/unlock", json={"passphrase": "test-pass"})
        self.assertEqual(res.status_code, 200)
        return res.json()["token"]

    def _bootstrap_admin(self) -> tuple[str, str]:
        token = self._unlock()
        create = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin"},
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(create.status_code, 200)
        return token, create.json()["id"]

    def test_admin_settings_defaults_are_available(self):
        token, admin_id = self._bootstrap_admin()
        res = self.client.get(
            "/admin/settings",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["settings"]["usage_limits"]["token_ttl_min"], 20)
        self.assertEqual(body["settings"]["usage_limits"]["max_active_tokens"], 200)
        self.assertEqual(body["settings"]["voice"]["stt_provider"], "local")
        self.assertEqual(body["settings"]["home_assistant"]["confirmation_ttl_sec"], 300)
        self.assertEqual(body["effective"]["voice"]["wakeword_phrase"]["source"], "settings")

    def test_admin_settings_update_persists_and_audits(self):
        token, admin_id = self._bootstrap_admin()
        res = self.client.put(
            "/admin/settings",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={
                "usage_limits": {"token_ttl_min": 45, "max_active_tokens": 7},
                "voice": {"wakeword_enabled": True, "wakeword_phrase": "jarvis now", "stt_provider": "gemini"},
                "home_assistant": {"confirmation_ttl_sec": 420, "remote_allowed_cidrs": ["10.0.0.0/24"]},
            },
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["settings"]["usage_limits"]["token_ttl_min"], 45)
        self.assertEqual(body["settings"]["voice"]["wakeword_phrase"], "jarvis now")
        self.assertEqual(body["settings"]["home_assistant"]["confirmation_ttl_sec"], 420)
        reloaded = jarvisappv4.AdminSettingsStore().get()
        self.assertEqual(reloaded["usage_limits"]["max_active_tokens"], 7)
        self.assertTrue(reloaded["voice"]["wakeword_enabled"])
        self.assertEqual(["10.0.0.0/24"], reloaded["home_assistant"]["remote_allowed_cidrs"])

        events = jarvisappv4.audit_log.read_events(event="admin_settings_updated", actor_user_id=admin_id, limit=5)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["stt_provider"], "gemini")

    def test_unlock_uses_admin_settings_defaults_when_env_unset(self):
        jarvisappv4.admin_settings_store.update(
            {
                "usage_limits": {"token_ttl_min": 1, "max_active_tokens": 1},
                "voice": {"wakeword_enabled": False, "wakeword_phrase": "hey jarvis", "stt_provider": "local"},
            }
        )
        first = self._unlock()
        second = self._unlock()

        blocked = self.client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {first}", "X-Jarvis-Role": "admin"},
        )
        self.assertEqual(blocked.status_code, 401)

        allowed = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {second}", "X-Jarvis-Role": "admin"},
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(allowed.status_code, 200)

    def test_env_overrides_settings_for_effective_values(self):
        token, admin_id = self._bootstrap_admin()
        jarvisappv4.admin_settings_store.update(
            {
                "usage_limits": {"token_ttl_min": 9, "max_active_tokens": 4},
                "voice": {"wakeword_enabled": False, "wakeword_phrase": "jarvis local", "stt_provider": "local"},
                "home_assistant": {"confirmation_ttl_sec": 360, "remote_allowed_cidrs": ["192.168.1.0/24"]},
            }
        )

        with patch.dict(
            os.environ,
            {
                "JARVIS_TOKEN_TTL_MIN": "33",
                "JARVIS_MAX_ACTIVE_TOKENS": "11",
                "JARVIS_WAKEWORD_ENABLED": "1",
                "JARVIS_WAKEWORD_PHRASE": "env jarvis",
                "STT_PROVIDER": "gemini",
                "JARVIS_HOME_ASSISTANT_CONFIRMATION_TTL_SEC": "900",
                "JARVIS_HOME_ASSISTANT_REMOTE_ALLOWED_CIDRS": "10.0.0.0/24,10.0.1.0/24",
            },
            clear=False,
        ):
            res = self.client.get(
                "/admin/settings",
                headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            )
            self.assertEqual(res.status_code, 200)
            effective = res.json()["effective"]
            self.assertEqual(effective["usage_limits"]["token_ttl_min"]["source"], "env")
            self.assertEqual(effective["voice"]["stt_provider"]["value"], "gemini")
            self.assertEqual(effective["home_assistant"]["confirmation_ttl_sec"]["value"], 900)
            self.assertEqual(effective["home_assistant"]["remote_allowed_cidrs"]["source"], "env")
            self.assertEqual(jarvisappv4.get_stt_provider(), "gemini")
            self.assertTrue(jarvisappv4.wakeword_enabled())
            self.assertEqual(jarvisappv4.wakeword_phrase(), "env jarvis")

    def test_status_summary_exposes_settings_effective_metadata(self):
        token, admin_id = self._bootstrap_admin()
        res = self.client.get(
            "/admin/status/summary",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("settings", body)
        self.assertIn("usage_limits", body["settings"])
        self.assertIn("voice", body["settings"])


if __name__ == "__main__":
    unittest.main()
