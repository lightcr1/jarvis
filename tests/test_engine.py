import os
import tempfile
import unittest

from jarvis.jarvis_engine import JarvisEngine, SecurityPolicy, build_registry, SkillRegistry, Skill, RiskLevel, ActionPlan


class EngineTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ["ALLOWED_TARGETS"] = "local"
        os.environ["COOLDOWN_RESTART_SECONDS"] = "0"
        os.environ["COOLDOWN_CRITICAL_SECONDS"] = "0"
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_MEMORY_PATH"] = os.path.join(self.tmpdir.name, "memory.json")
        self.engine = JarvisEngine(build_registry(), SecurityPolicy())

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_fuzzy_matching(self):
        response = self.engine.process("statuz jarvis", token=None)
        self.assertIn("Jarvis", response["summary"])

    def test_disambiguation(self):
        response = self.engine.process("service", token=None)
        self.assertEqual(response["summary"], "Need clarification.")

    def test_token_and_confirm_for_critical(self):
        response = self.engine.process("service restart local nginx", token=None, role="admin")
        self.assertEqual(response["summary"], "Token required.")

        response = self.engine.process("service restart local nginx", token="tok", role="admin")
        self.assertIn("Confirmation", response["summary"])
        self.assertEqual(response["data"]["confirm"], "YES, proceed")

        response = self.engine.process("YES, proceed", token="tok", role="admin")
        self.assertIn("not configured", response["summary"])

    def test_scope_allowlist(self):
        response = self.engine.process("service restart web01 nginx", token="tok", role="admin")
        self.assertEqual(response["summary"], "Target not allowed.")

    def test_rate_limit(self):
        os.environ["COOLDOWN_RESTART_SECONDS"] = "60"
        engine = JarvisEngine(build_registry(), SecurityPolicy())
        engine.process("service restart local nginx", token="tok", role="admin")
        response = engine.process("service restart local nginx", token="tok", role="admin")
        self.assertIn("Cooldown", response["summary"])

    def test_feedback_and_alias_learning(self):
        first = self.engine.process("status jarvis", token=None)
        feedback_id = first["data"]["feedback"]["id"]

        saved = self.engine.process(
            f"feedback {feedback_id} bad correct: proxmox health",
            token=None,
        )
        self.assertEqual(saved["summary"], "Feedback gespeichert.")

        learned = self.engine.process("status jarvis", token=None)
        self.assertIn("Proxmox", learned["summary"])

    def test_skill_suggestion_after_repeated_unmatched(self):
        for _ in range(3):
            response = self.engine.process("warum geht web gui nicht", token=None)
        self.assertIn("skill", response["data"]["skill_suggestion"].lower())

    def test_remember_and_memory_show_commands(self):
        set_resp = self.engine.process("remember node pve1 10.0.0.10", token=None)
        self.assertEqual(set_resp["summary"], "Memory updated.")

        mem_resp = self.engine.process("memory show", token=None)
        self.assertEqual(mem_resp["summary"], "Memory snapshot ready.")
        self.assertEqual(mem_resp["data"]["memory"]["nodes"].get("pve1"), "10.0.0.10")

    def test_smalltalk_skill(self):
        response = self.engine.process("how are you", token=None)
        self.assertIn("ready to help", response["summary"].lower())


    def test_wake_word_does_not_require_clarification(self):
        os.environ["JARVIS_WAKEWORD_ENABLED"] = "1"
        engine = JarvisEngine(build_registry(), SecurityPolicy())
        response = engine.process("jarvis", token=None)
        self.assertIn("J.A.R.V.I.S", response["summary"])


    def test_learning_requires_reinforcement_before_generalizing(self):
        self.engine.process("memory show", token=None)
        not_yet = self.engine.process("memory shwo", token=None)
        self.assertNotEqual(not_yet.get("data", {}).get("route"), "learned_memory")

    def test_autonomous_learning_reuses_previous_reply(self):
        first = self.engine.process("memory show", token=None)
        self.assertEqual(first["summary"], "Memory snapshot ready.")

        # strengthen confidence with repeated successful usage
        self.engine.process("memory show", token=None)
        learned = self.engine.process("memory shwo", token=None)
        self.assertEqual(learned["summary"], "Memory snapshot ready.")
        self.assertEqual(learned["data"]["route"], "learned_memory")



    def test_unknown_role_falls_back_to_standard_user_permissions(self):
        response = self.engine.process("service restart local nginx", token="tok", role="not_a_real_role")
        self.assertEqual(response["summary"], "Permission denied.")
        self.assertEqual(response["data"]["permission"], "actions.dangerous.execute")
        self.assertEqual(response["data"]["role"], "standard_user")

    def test_standard_user_cannot_run_critical_skill(self):
        response = self.engine.process("service restart local nginx", token="tok", role="standard_user")
        self.assertEqual(response["summary"], "Permission denied.")
        self.assertEqual(response["data"]["permission"], "actions.dangerous.execute")

    def test_guest_voice_permission_denied_when_removed(self):
        from jarvis.jarvis_engine import ROLE_PERMISSIONS

        saved = set(ROLE_PERMISSIONS["guest_restricted"])
        try:
            ROLE_PERMISSIONS["guest_restricted"].discard("voice.use")
            response = self.engine.process("status jarvis", token=None, role="guest_restricted", source="voice")
            self.assertEqual(response["summary"], "Permission denied.")
            self.assertEqual(response["data"]["permission"], "voice.use")
        finally:
            ROLE_PERMISSIONS["guest_restricted"] = saved


    def test_emergency_stop_blocks_critical_action(self):
        os.environ["JARVIS_EMERGENCY_STOP"] = "1"
        try:
            response = self.engine.process("service restart local nginx", token="tok", role="admin")
            self.assertEqual(response["summary"], "Emergency stop active.")
            self.assertEqual(response["data"]["error"], "emergency_stop")
        finally:
            os.environ.pop("JARVIS_EMERGENCY_STOP", None)

    def test_emergency_stop_blocks_confirmed_pending_action(self):
        first = self.engine.process("service restart local nginx", token="tok", role="admin")
        self.assertIn("Confirmation", first["summary"])

        os.environ["JARVIS_EMERGENCY_STOP"] = "1"
        try:
            confirmed = self.engine.process("YES, proceed", token="tok", role="admin")
            self.assertEqual(confirmed["summary"], "Emergency stop active.")
            self.assertEqual(confirmed["data"]["error"], "emergency_stop")
        finally:
            os.environ.pop("JARVIS_EMERGENCY_STOP", None)


    def test_standard_user_cannot_run_write_plan_skill(self):
        registry = SkillRegistry()

        def write_handler(_ctx):
            return ActionPlan(
                summary="Write op",
                steps=["do write"],
                risk=RiskLevel.WRITE,
                target="local",
                execute=lambda: {"summary": "write done", "data": {"ok": True}},
            )

        registry.register(
            Skill(
                name="write-test",
                description="write test",
                risk=RiskLevel.WRITE,
                triggers=["write test"],
                examples=["write test"],
                handler=write_handler,
            )
        )

        engine = JarvisEngine(registry, SecurityPolicy())
        response = engine.process("write test", token="tok", role="standard_user")
        self.assertEqual(response["summary"], "Permission denied.")
        self.assertEqual(response["data"]["permission"], "actions.write.execute")

    def test_admin_can_receive_write_confirmation(self):
        registry = SkillRegistry()

        def write_handler(_ctx):
            return ActionPlan(
                summary="Write op",
                steps=["do write"],
                risk=RiskLevel.WRITE,
                target="local",
                execute=lambda: {"summary": "write done", "data": {"ok": True}},
            )

        registry.register(
            Skill(
                name="write-test",
                description="write test",
                risk=RiskLevel.WRITE,
                triggers=["write test"],
                examples=["write test"],
                handler=write_handler,
            )
        )

        engine = JarvisEngine(registry, SecurityPolicy())
        response = engine.process("write test", token="tok", role="admin")
        self.assertIn("Confirmation", response["summary"])
        self.assertEqual(response["data"]["confirm"], "YES")


    def test_granted_permissions_allow_write_for_standard_user(self):
        registry = SkillRegistry()

        def write_handler(_ctx):
            return ActionPlan(
                summary="Write op",
                steps=["do write"],
                risk=RiskLevel.WRITE,
                target="local",
                execute=lambda: {"summary": "write done", "data": {"ok": True}},
            )

        registry.register(
            Skill(
                name="write-test",
                description="write test",
                risk=RiskLevel.WRITE,
                triggers=["write test"],
                examples=["write test"],
                handler=write_handler,
            )
        )

        engine = JarvisEngine(registry, SecurityPolicy())
        response = engine.process(
            "write test",
            token="tok",
            role="standard_user",
            granted_permissions=["actions.write.execute"],
        )
        self.assertIn("Confirmation", response["summary"])

    def test_granted_permissions_allow_voice_for_service_role(self):
        response = self.engine.process(
            "status jarvis",
            token=None,
            role="service_system",
            source="voice",
            granted_permissions=["voice.use"],
        )
        self.assertNotEqual(response["summary"], "Permission denied.")


class LearningStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_MEMORY_PATH"] = os.path.join(self.tmpdir.name, "mem.json")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_remember_vmid_kind(self):
        from jarvis.jarvis_engine import JarvisEngine, build_registry, SecurityPolicy
        os.environ["ALLOWED_TARGETS"] = "local"
        os.environ["COOLDOWN_RESTART_SECONDS"] = "0"
        os.environ["COOLDOWN_CRITICAL_SECONDS"] = "0"
        engine = JarvisEngine(build_registry(), SecurityPolicy())
        resp = engine.process("remember vmid vm101 192.168.1.50", token=None)
        self.assertEqual(resp["summary"], "Memory updated.")
        self.assertEqual(resp["data"]["stored"]["type"], "vmid")

        snap = engine.process("memory show", token=None)
        self.assertEqual(snap["data"]["memory"]["vmids"].get("vm101"), "192.168.1.50")

    def test_remember_default_kind(self):
        from jarvis.jarvis_engine import JarvisEngine, build_registry, SecurityPolicy
        os.environ["ALLOWED_TARGETS"] = "local"
        os.environ["COOLDOWN_RESTART_SECONDS"] = "0"
        os.environ["COOLDOWN_CRITICAL_SECONDS"] = "0"
        engine = JarvisEngine(build_registry(), SecurityPolicy())
        resp = engine.process("remember default timeout 30", token=None)
        self.assertEqual(resp["summary"], "Memory updated.")

        snap = engine.process("memory show", token=None)
        self.assertEqual(snap["data"]["memory"]["defaults"].get("timeout"), "30")

    def test_snapshot_counts_feedback_entries(self):
        from jarvis.jarvis_engine import JarvisEngine, build_registry, SecurityPolicy
        os.environ["ALLOWED_TARGETS"] = "local"
        os.environ["COOLDOWN_RESTART_SECONDS"] = "0"
        os.environ["COOLDOWN_CRITICAL_SECONDS"] = "0"
        engine = JarvisEngine(build_registry(), SecurityPolicy())
        engine.process("status jarvis", token=None)
        snap = engine.process("memory show", token=None)
        self.assertGreaterEqual(snap["data"]["memory"]["feedback_entries"], 1)

    def test_feedback_ok_verdict_without_correction(self):
        from jarvis.jarvis_engine import JarvisEngine, build_registry, SecurityPolicy
        os.environ["ALLOWED_TARGETS"] = "local"
        os.environ["COOLDOWN_RESTART_SECONDS"] = "0"
        os.environ["COOLDOWN_CRITICAL_SECONDS"] = "0"
        engine = JarvisEngine(build_registry(), SecurityPolicy())
        first = engine.process("status jarvis", token=None)
        fid = first["data"]["feedback"]["id"]
        resp = engine.process(f"feedback {fid} ok", token=None)
        self.assertEqual(resp["summary"], "Feedback gespeichert.")
        self.assertEqual(resp["data"]["verdict"], "ok")

    def test_feedback_unknown_id_returns_error(self):
        from jarvis.jarvis_engine import JarvisEngine, build_registry, SecurityPolicy
        os.environ["ALLOWED_TARGETS"] = "local"
        os.environ["COOLDOWN_RESTART_SECONDS"] = "0"
        os.environ["COOLDOWN_CRITICAL_SECONDS"] = "0"
        engine = JarvisEngine(build_registry(), SecurityPolicy())
        resp = engine.process("feedback fb-000000 ok", token=None)
        self.assertEqual(resp["summary"], "Feedback ID unknown.")
        self.assertEqual(resp["data"]["error"], "feedback_not_found")

    def test_learning_show_alias(self):
        from jarvis.jarvis_engine import JarvisEngine, build_registry, SecurityPolicy
        os.environ["ALLOWED_TARGETS"] = "local"
        os.environ["COOLDOWN_RESTART_SECONDS"] = "0"
        os.environ["COOLDOWN_CRITICAL_SECONDS"] = "0"
        engine = JarvisEngine(build_registry(), SecurityPolicy())
        resp = engine.process("learning show", token=None)
        self.assertEqual(resp["summary"], "Memory snapshot ready.")


class EngineFallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("OPENROUTER_API_KEY", None)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ["JARVIS_USE_AI_ROUTER"] = "0"
        os.environ["ALLOWED_TARGETS"] = "local"
        os.environ["COOLDOWN_RESTART_SECONDS"] = "0"
        os.environ["COOLDOWN_CRITICAL_SECONDS"] = "0"
        os.environ["JARVIS_MEMORY_PATH"] = os.path.join(self.tmpdir.name, "mem.json")
        self.engine = JarvisEngine(build_registry(), SecurityPolicy())

    def tearDown(self):
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("OPENROUTER_API_KEY", None)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("JARVIS_USE_AI_ROUTER", None)
        self.tmpdir.cleanup()

    def test_fallback_offline_when_no_cloud(self):
        resp = self.engine.process("qwerty nonsense phrase xyz123", token=None)
        self.assertEqual(resp["data"]["route"], "offline")
        self.assertTrue(resp["data"]["offline"])

    def test_fallback_cloud_routing_when_openai_set(self):
        os.environ["OPENAI_API_KEY"] = "sk-test-dummy"
        resp = self.engine.process("qwerty nonsense phrase xyz123", token=None)
        self.assertEqual(resp["data"]["route"], "cloud")
        self.assertFalse(resp["data"]["offline"])

    def test_fallback_cloud_routing_when_gemini_set(self):
        os.environ["GEMINI_API_KEY"] = "gemini-test-key"
        resp = self.engine.process("qwerty nonsense phrase xyz123", token=None)
        self.assertEqual(resp["data"]["route"], "cloud")

    def test_handle_confirm_without_token_returns_token_required(self):
        resp = self.engine.process("YES, proceed", token=None)
        self.assertEqual(resp["summary"], "Token required.")
        self.assertEqual(resp["data"]["error"], "missing_token")

    def test_handle_write_confirm_without_token_returns_token_required(self):
        resp = self.engine.process("YES", token=None)
        self.assertEqual(resp["summary"], "Token required.")

    def test_confirm_with_no_pending_action(self):
        resp = self.engine.process("YES, proceed", token="some-token")
        self.assertEqual(resp["summary"], "Nothing pending.")
        self.assertEqual(resp["data"]["error"], "no_pending_action")

    def test_verbose_flag_adds_details_to_data(self):
        resp = self.engine.process("status jarvis --verbose", token=None)
        self.assertIn("details", resp["data"])

    def test_verbose_flag_dash_v(self):
        resp = self.engine.process("status jarvis -v", token=None)
        self.assertIn("details", resp["data"])

    def test_read_plan_executes_without_confirmation(self):
        registry = SkillRegistry()

        def read_handler(_ctx):
            return ActionPlan(
                summary="Read op",
                steps=["do read"],
                risk=RiskLevel.READ,
                target=None,
                execute=lambda: {"summary": "read done", "data": {"ok": True}},
            )

        registry.register(
            Skill(
                name="read-test",
                description="read test",
                risk=RiskLevel.READ,
                triggers=["read test"],
                examples=["read test"],
                handler=read_handler,
            )
        )
        engine = JarvisEngine(registry, SecurityPolicy())
        resp = engine.process("read test", token=None, role="standard_user")
        self.assertEqual(resp["summary"], "read done")

    def test_normalize_utility(self):
        from jarvis.jarvis_engine import normalize
        self.assertEqual("hello world", normalize("  Hello   World  "))
        self.assertEqual("abc def", normalize("ABC DEF"))

    def test_strip_verbose_removes_flag(self):
        from jarvis.jarvis_engine import strip_verbose
        cleaned, verbose = strip_verbose("status jarvis --verbose")
        self.assertEqual("status jarvis", cleaned)
        self.assertTrue(verbose)

    def test_strip_verbose_no_flag(self):
        from jarvis.jarvis_engine import strip_verbose
        cleaned, verbose = strip_verbose("status jarvis")
        self.assertEqual("status jarvis", cleaned)
        self.assertFalse(verbose)

    def test_masked_utility(self):
        from jarvis.jarvis_engine import masked
        self.assertEqual("abcd***", masked("abcdefgh", keep=4))
        self.assertEqual("****", masked("abcd", keep=4))
        self.assertEqual("", masked(""))

    def test_wakeword_phrases_includes_custom(self):
        from jarvis.jarvis_engine import wakeword_phrases
        os.environ["JARVIS_WAKEWORD_PHRASE"] = "computer"
        phrases = wakeword_phrases()
        self.assertIn("computer", phrases)
        self.assertIn("jarvis", phrases)
        del os.environ["JARVIS_WAKEWORD_PHRASE"]

    def test_wakeword_not_triggered_when_disabled(self):
        os.environ.pop("JARVIS_WAKEWORD_ENABLED", None)
        engine = JarvisEngine(build_registry(), SecurityPolicy())
        resp = engine.process("jarvis", token=None)
        self.assertNotIn("wakeword", resp.get("data", {}))

    def test_closest_learned_phrase_gives_clarification(self):
        from jarvis.jarvis_engine import LearningStore
        import difflib
        store = LearningStore()
        store.data["learned_replies"]["proxmox health check"] = {
            "summary": "Proxmox healthy.",
            "skill": "proxmox-health",
            "confidence": 3,
            "updated_at": 1,
        }
        # find a query that scores 0.62–0.80 against "proxmox health check"
        query = "check proxmox health"
        ratio = difflib.SequenceMatcher(None, query, "proxmox health check").ratio()
        # verify the test assumption holds
        self.assertGreater(ratio, 0.62)
        self.assertLess(ratio, 0.80)
        result = store.closest_learned_phrase(query)
        self.assertIsNotNone(result)
        self.assertEqual("proxmox health check", result["source"])


if __name__ == "__main__":
    unittest.main()
