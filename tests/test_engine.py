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


if __name__ == "__main__":
    unittest.main()
