import unittest

import jarvisappv4


class EntrypointContractTests(unittest.TestCase):
    def test_router_dependency_surface_stays_available(self):
        required_attrs = [
            "audit_log",
            "user_store",
            "group_store",
            "membership_store",
            "permission_store",
            "admin_password_store",
            "admin_settings_store",
            "user_preferences_store",
            "chat_history",
            "rag_store",
            "_tokens",
            "_identity_tokens",
            "_issue_token",
            "_issue_identity_token",
            "_get_identity_session",
            "_chat_owner_key",
            "_prepare_audit_filters",
            "_validate_audit_query",
            "_settings_env_summary",
            "_audit_admin_event",
            "require_admin_access",
            "require_identity_session",
            "require_token",
            "get_stt_provider",
            "wakeword_enabled",
            "wakeword_phrase",
            "strip_wakeword",
            "transcribe_local",
            "transcribe_gemini",
            "synthesize_tts",
            "try_skill",
            "rag_query_from_prompt",
            "select_rag_hits",
            "format_rag_reply",
            "cloud_llm_available",
            "rag_needs_smart_llm",
            "rag_llm_answer",
            "build_permission_context",
            "permission_decision",
            "resolve_effective_permissions",
            "get_active_user_or_raise",
            "SYSTEM_PROMPT",
            "build_context_reply",
            "local_ai_stub_reply",
            "KNOWN_PERMISSIONS",
        ]
        missing = [name for name in required_attrs if not hasattr(jarvisappv4, name)]
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
