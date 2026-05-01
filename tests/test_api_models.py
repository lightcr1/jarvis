import unittest

import pytest
from pydantic import ValidationError

from jarvis.api_models import (
    AdminGroupCreateIn,
    AdminGroupUpdateIn,
    AdminHomeAssistantSettingsIn,
    AdminLoginIn,
    AdminMembershipIn,
    AdminPermissionSetIn,
    AdminSettingsIn,
    AdminUsageLimitsIn,
    AdminUserCreateIn,
    AdminUserUpdateIn,
    AdminVoiceSettingsIn,
    ChatIn,
    ChatMessage,
    ChatOut,
    ChatSessionCreateIn,
    ChatSessionOut,
    ChatSessionUpdateIn,
    HomeAssistantDiscoveryCandidateIn,
    TTSIn,
    UnlockIn,
    UserLoginIn,
    UserPasswordIn,
    UserPreferencesIn,
)


class ChatModelsTests(unittest.TestCase):
    def test_chat_in_minimal(self):
        m = ChatIn(text="hello")
        self.assertEqual("hello", m.text)
        self.assertIsNone(m.session_id)
        self.assertIsNone(m.source)

    def test_chat_in_full(self):
        m = ChatIn(text="hi", session_id="chat-1", source="voice")
        self.assertEqual("chat-1", m.session_id)
        self.assertEqual("voice", m.source)

    def test_chat_out_minimal(self):
        m = ChatOut(reply="OK")
        self.assertEqual("OK", m.reply)
        self.assertIsNone(m.data)
        self.assertIsNone(m.session_id)

    def test_chat_session_create_in_no_title(self):
        m = ChatSessionCreateIn()
        self.assertIsNone(m.title)

    def test_chat_session_create_in_with_title(self):
        m = ChatSessionCreateIn(title="My Chat")
        self.assertEqual("My Chat", m.title)

    def test_chat_session_update_in_requires_title(self):
        with self.assertRaises(ValidationError):
            ChatSessionUpdateIn()

    def test_chat_message_fields(self):
        m = ChatMessage(role="user", text="hi", ts=1234567890)
        self.assertEqual("user", m.role)
        self.assertEqual("hi", m.text)
        self.assertEqual(1234567890, m.ts)

    def test_chat_session_out_defaults(self):
        m = ChatSessionOut(id="chat-1", title="T", updated_at=1000, created_at=900)
        self.assertEqual([], m.messages)

    def test_unlock_in(self):
        m = UnlockIn(passphrase="topsecret")
        self.assertEqual("topsecret", m.passphrase)

    def test_tts_in(self):
        m = TTSIn(text="Hello world")
        self.assertEqual("Hello world", m.text)


class AdminModelsTests(unittest.TestCase):
    def test_admin_login_in(self):
        m = AdminLoginIn(username="admin", password="pass")
        self.assertEqual("admin", m.username)
        self.assertEqual("pass", m.password)

    def test_admin_user_create_in_defaults(self):
        m = AdminUserCreateIn(username="alice")
        self.assertEqual("standard_user", m.role)
        self.assertTrue(m.enabled)
        self.assertIsNone(m.password)

    def test_admin_user_create_in_full(self):
        m = AdminUserCreateIn(username="bob", role="admin", enabled=False, password="pw")
        self.assertEqual("admin", m.role)
        self.assertFalse(m.enabled)
        self.assertEqual("pw", m.password)

    def test_admin_user_update_in_all_optional(self):
        m = AdminUserUpdateIn()
        self.assertIsNone(m.role)
        self.assertIsNone(m.enabled)

    def test_admin_group_create_in_defaults(self):
        m = AdminGroupCreateIn(name="ops")
        self.assertEqual("ops", m.name)
        self.assertEqual("", m.description)

    def test_admin_group_update_in_all_optional(self):
        m = AdminGroupUpdateIn()
        self.assertIsNone(m.name)
        self.assertIsNone(m.description)

    def test_admin_membership_in(self):
        m = AdminMembershipIn(user_id="user:u1", group_id="group:g1")
        self.assertEqual("user:u1", m.user_id)

    def test_admin_permission_set_in_defaults_empty(self):
        m = AdminPermissionSetIn()
        self.assertEqual([], m.permissions)

    def test_admin_permission_set_in_with_perms(self):
        m = AdminPermissionSetIn(permissions=["chat.access", "home_assistant.access"])
        self.assertEqual(2, len(m.permissions))


class AdminSettingsModelsTests(unittest.TestCase):
    def test_usage_limits_defaults(self):
        m = AdminUsageLimitsIn()
        self.assertEqual(20, m.token_ttl_min)
        self.assertEqual(200, m.max_active_tokens)

    def test_usage_limits_min_enforced(self):
        with self.assertRaises(ValidationError):
            AdminUsageLimitsIn(token_ttl_min=0)
        with self.assertRaises(ValidationError):
            AdminUsageLimitsIn(max_active_tokens=0)

    def test_voice_settings_defaults(self):
        m = AdminVoiceSettingsIn()
        self.assertFalse(m.wakeword_enabled)
        self.assertEqual("hey jarvis", m.wakeword_phrase)
        self.assertEqual("local", m.stt_provider)

    def test_voice_settings_gemini_valid(self):
        m = AdminVoiceSettingsIn(stt_provider="gemini")
        self.assertEqual("gemini", m.stt_provider)

    def test_voice_settings_invalid_provider_raises(self):
        with self.assertRaises(ValidationError):
            AdminVoiceSettingsIn(stt_provider="openai")

    def test_voice_settings_empty_phrase_raises(self):
        with self.assertRaises(ValidationError):
            AdminVoiceSettingsIn(wakeword_phrase="")

    def test_ha_settings_defaults(self):
        m = AdminHomeAssistantSettingsIn()
        self.assertEqual(300, m.confirmation_ttl_sec)
        self.assertEqual([], m.remote_allowed_cidrs)

    def test_ha_settings_min_ttl_enforced(self):
        with self.assertRaises(ValidationError):
            AdminHomeAssistantSettingsIn(confirmation_ttl_sec=29)

    def test_ha_settings_ttl_at_minimum(self):
        m = AdminHomeAssistantSettingsIn(confirmation_ttl_sec=30)
        self.assertEqual(30, m.confirmation_ttl_sec)

    def test_admin_settings_in_nested_defaults(self):
        m = AdminSettingsIn()
        self.assertEqual(20, m.usage_limits.token_ttl_min)
        self.assertEqual("local", m.voice.stt_provider)
        self.assertEqual(300, m.home_assistant.confirmation_ttl_sec)


class UserModelsTests(unittest.TestCase):
    def test_user_login_in(self):
        m = UserLoginIn(username="alice", password="pw")
        self.assertEqual("alice", m.username)

    def test_user_password_in_requires_nonempty(self):
        with self.assertRaises(ValidationError):
            UserPasswordIn(password="")

    def test_user_password_in_valid(self):
        m = UserPasswordIn(password="x")
        self.assertEqual("x", m.password)

    def test_user_preferences_in_defaults(self):
        m = UserPreferencesIn()
        self.assertEqual("", m.display_name)
        self.assertEqual("cyan", m.accent_color)
        self.assertTrue(m.auto_play_voice)
        self.assertFalse(m.compact_mode)
        self.assertEqual("high", m.orb_detail)
        self.assertEqual("dark", m.theme)
        self.assertEqual("", m.location)
        self.assertEqual([], m.notes)

    def test_user_preferences_in_custom(self):
        m = UserPreferencesIn(display_name="Lukas", accent_color="blue", theme="light")
        self.assertEqual("Lukas", m.display_name)
        self.assertEqual("blue", m.accent_color)
        self.assertEqual("light", m.theme)


class HomeAssistantDiscoveryTests(unittest.TestCase):
    def test_minimal_valid(self):
        m = HomeAssistantDiscoveryCandidateIn(
            ip_address="192.168.1.100",
            label="Living Room Light",
            suggested_type="light",
        )
        self.assertEqual("manual", m.source)
        self.assertEqual("", m.suggested_area)
        self.assertEqual({}, m.metadata)

    def test_full_payload(self):
        m = HomeAssistantDiscoveryCandidateIn(
            source="scan",
            ip_address="10.0.0.1",
            label="Switch",
            suggested_type="switch",
            suggested_area="kitchen",
            metadata={"vendor": "Sonoff"},
        )
        self.assertEqual("scan", m.source)
        self.assertEqual("kitchen", m.suggested_area)
        self.assertEqual({"vendor": "Sonoff"}, m.metadata)

    def test_empty_ip_raises(self):
        with self.assertRaises(ValidationError):
            HomeAssistantDiscoveryCandidateIn(ip_address="", label="L", suggested_type="light")

    def test_empty_label_raises(self):
        with self.assertRaises(ValidationError):
            HomeAssistantDiscoveryCandidateIn(ip_address="1.2.3.4", label="", suggested_type="light")

    def test_empty_type_raises(self):
        with self.assertRaises(ValidationError):
            HomeAssistantDiscoveryCandidateIn(ip_address="1.2.3.4", label="L", suggested_type="")


if __name__ == "__main__":
    unittest.main()
