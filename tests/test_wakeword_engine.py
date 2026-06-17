import os
import sys
import tempfile
import unittest
from unittest.mock import patch


class TestCreateEngineFactory(unittest.TestCase):
    def setUp(self):
        for var in ["JARVIS_WAKEWORD_ENABLED", "JARVIS_WAKEWORD_ENGINE", "JARVIS_WAKEWORD_PHRASE",
                    "JARVIS_WAKEWORD_SENSITIVITY"]:
            os.environ.pop(var, None)

    def tearDown(self):
        for var in ["JARVIS_WAKEWORD_ENABLED", "JARVIS_WAKEWORD_ENGINE", "JARVIS_WAKEWORD_PHRASE",
                    "JARVIS_WAKEWORD_SENSITIVITY"]:
            os.environ.pop(var, None)

    def _factory(self, settings: dict | None = None):
        from jarvis.wakeword_engine import create_wakeword_engine
        return create_wakeword_engine(settings or {})

    def test_create_engine_software_mode(self):
        os.environ["JARVIS_WAKEWORD_ENGINE"] = "software"
        from jarvis.wakeword_engine import SoftwareWakewordEngine
        engine = self._factory()
        self.assertIsInstance(engine, SoftwareWakewordEngine)

    def test_create_engine_null_mode_via_env(self):
        os.environ["JARVIS_WAKEWORD_ENGINE"] = "none"
        from jarvis.wakeword_engine import NullWakewordEngine
        engine = self._factory()
        self.assertIsInstance(engine, NullWakewordEngine)

    def test_create_engine_null_mode_when_disabled(self):
        os.environ["JARVIS_WAKEWORD_ENABLED"] = "false"
        from jarvis.wakeword_engine import NullWakewordEngine
        engine = self._factory()
        self.assertIsInstance(engine, NullWakewordEngine)

    def test_create_engine_null_mode_when_disabled_zero(self):
        os.environ["JARVIS_WAKEWORD_ENABLED"] = "0"
        from jarvis.wakeword_engine import NullWakewordEngine
        engine = self._factory()
        self.assertIsInstance(engine, NullWakewordEngine)

    def test_create_engine_fallback_when_openwakeword_missing(self):
        os.environ["JARVIS_WAKEWORD_ENGINE"] = "openwakeword"
        with patch.dict(sys.modules, {"openwakeword": None}):
            from importlib import reload
            import jarvis.wakeword_engine as ww_mod
            reload(ww_mod)
            engine = ww_mod.create_wakeword_engine({})
            self.assertIsInstance(engine, ww_mod.SoftwareWakewordEngine)

    def test_create_engine_settings_engine_field(self):
        settings = {"voice": {"wakeword_engine": "software", "wakeword_sensitivity": 0.5}}
        from jarvis.wakeword_engine import SoftwareWakewordEngine
        engine = self._factory(settings)
        self.assertIsInstance(engine, SoftwareWakewordEngine)

    def test_create_engine_unknown_engine_falls_back_to_software(self):
        os.environ["JARVIS_WAKEWORD_ENGINE"] = "porcupine"
        from jarvis.wakeword_engine import SoftwareWakewordEngine
        engine = self._factory()
        self.assertIsInstance(engine, SoftwareWakewordEngine)


class TestSoftwareWakewordEngine(unittest.TestCase):
    def _engine(self, phrase: str = "hey jarvis"):
        from jarvis.wakeword_engine import SoftwareWakewordEngine
        return SoftwareWakewordEngine(phrase=phrase)

    def test_strips_phrase_prefix(self):
        eng = self._engine()
        result, detected = eng.strip("hey jarvis turn on the lights")
        self.assertEqual(result, "turn on the lights")
        self.assertTrue(detected)

    def test_exact_phrase_returns_status(self):
        eng = self._engine()
        result, detected = eng.strip("hey jarvis")
        self.assertEqual(result, "status jarvis")
        self.assertTrue(detected)

    def test_no_phrase_unchanged(self):
        eng = self._engine()
        result, detected = eng.strip("play some music")
        self.assertEqual(result, "play some music")
        self.assertFalse(detected)

    def test_case_insensitive_match(self):
        eng = self._engine()
        result, detected = eng.strip("HEY JARVIS what is the time")
        self.assertTrue(detected)
        self.assertEqual(result, "what is the time")

    def test_start_stop_lifecycle(self):
        import asyncio
        eng = self._engine()
        self.assertFalse(eng.is_running())
        loop = asyncio.new_event_loop()
        eng.start(loop, lambda: None)
        self.assertTrue(eng.is_running())
        eng.stop()
        self.assertFalse(eng.is_running())
        loop.close()


class TestNullWakewordEngine(unittest.TestCase):
    def test_never_running(self):
        from jarvis.wakeword_engine import NullWakewordEngine
        eng = NullWakewordEngine()
        self.assertFalse(eng.is_running())
        import asyncio
        loop = asyncio.new_event_loop()
        eng.start(loop, lambda: None)
        self.assertFalse(eng.is_running())
        eng.stop()
        self.assertFalse(eng.is_running())
        loop.close()


class TestOpenWakeWordEngineSensitivity(unittest.TestCase):
    def test_sensitivity_settable_and_clamped(self):
        from jarvis.wakeword_engine import OpenWakeWordEngine
        eng = OpenWakeWordEngine(sensitivity=0.5)
        self.assertAlmostEqual(eng.sensitivity, 0.5)
        eng.sensitivity = 0.8
        self.assertAlmostEqual(eng.sensitivity, 0.8)
        eng.sensitivity = 1.5  # clamped to 1.0
        self.assertAlmostEqual(eng.sensitivity, 1.0)
        eng.sensitivity = -0.1  # clamped to 0.0
        self.assertAlmostEqual(eng.sensitivity, 0.0)


class TestSettingsStoreWakewordFields(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_ADMIN_SETTINGS_PATH"] = os.path.join(self.tmpdir.name, "settings.json")

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("JARVIS_ADMIN_SETTINGS_PATH", None)

    def test_settings_include_wakeword_engine(self):
        from jarvis.admin_settings_store import AdminSettingsStore
        store = AdminSettingsStore()
        settings = store.get()
        self.assertIn("wakeword_engine", settings["voice"])
        self.assertEqual(settings["voice"]["wakeword_engine"], "software")

    def test_settings_include_wakeword_sensitivity(self):
        from jarvis.admin_settings_store import AdminSettingsStore
        store = AdminSettingsStore()
        settings = store.get()
        self.assertIn("wakeword_sensitivity", settings["voice"])
        self.assertAlmostEqual(settings["voice"]["wakeword_sensitivity"], 0.5)

    def test_wakeword_engine_update_and_persist(self):
        from jarvis.admin_settings_store import AdminSettingsStore
        store = AdminSettingsStore()
        store.update({"voice": {"wakeword_engine": "openwakeword"}})
        self.assertEqual(store.get()["voice"]["wakeword_engine"], "openwakeword")

    def test_wakeword_sensitivity_update_and_clamp(self):
        from jarvis.admin_settings_store import AdminSettingsStore
        store = AdminSettingsStore()
        store.update({"voice": {"wakeword_sensitivity": 0.75}})
        self.assertAlmostEqual(store.get()["voice"]["wakeword_sensitivity"], 0.75)
        store.update({"voice": {"wakeword_sensitivity": 2.0}})
        self.assertAlmostEqual(store.get()["voice"]["wakeword_sensitivity"], 1.0)

    def test_wakeword_engine_invalid_resets_to_software(self):
        from jarvis.admin_settings_store import AdminSettingsStore
        store = AdminSettingsStore()
        store.update({"voice": {"wakeword_engine": "badvalue"}})
        self.assertEqual(store.get()["voice"]["wakeword_engine"], "software")


class TestAdminWakewordStatusEndpoint(unittest.TestCase):
    def _build_client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from jarvis.api_admin import build_admin_router
        from jarvis.admin_settings_store import AdminSettingsStore
        from jarvis.user_store import UserStore
        from jarvis.audit_log_store import AuditLogStore
        from jarvis.group_store import GroupStore
        from jarvis.membership_store import MembershipStore
        from jarvis.permission_store import PermissionStore, KNOWN_PERMISSIONS
        from jarvis.admin_password_store import AdminPasswordStore
        from jarvis.user_preferences_store import UserPreferencesStore

        import uuid as _uuid
        tmpdir = tempfile.mkdtemp()
        os.environ["JARVIS_ADMIN_SETTINGS_PATH"] = os.path.join(tmpdir, "settings.json")
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(tmpdir, "users.json")
        tokens: dict = {"valid-admin-tok": float("inf")}
        user_store = UserStore()
        admin_user = user_store.create_user(f"ww_admin_{_uuid.uuid4().hex[:8]}", role="admin", enabled=True)

        def _require_admin(uid, role, auth, *, allow_bootstrap=False):
            from jarvis.session_auth import bearer_token_from_header
            from fastapi import HTTPException
            tok = bearer_token_from_header(auth)
            if tok not in tokens:
                raise HTTPException(401, "admin token required")
            if not uid:
                raise HTTPException(401, "admin user required")
            return uid, "admin"

        app = FastAPI()
        app.include_router(build_admin_router({
            "require_admin_access": _require_admin,
            "prepare_audit_filters": lambda *a, **kw: {"event": None, "role": None, "actor_user_id": None, "token_fingerprint": None},
            "validate_audit_query": lambda *a: None,
            "normalize_role": lambda r: r or "admin",
            "audit_admin_event": lambda *a, **kw: None,
            "known_permissions": KNOWN_PERMISSIONS,
            "get_active_user_or_raise": lambda store, uid: store.get_user(uid),
            "build_permission_context": lambda *a: {},
            "permission_decision": lambda *a: {"allowed": True},
            "settings_env_summary": lambda: {},
            "admin_settings_store": AdminSettingsStore(),
            "identity_tokens": tokens,
            "user_store": user_store,
            "group_store": GroupStore(),
            "membership_store": MembershipStore(),
            "permission_store": PermissionStore(),
            "audit_log": AuditLogStore(),
            "admin_password_store": AdminPasswordStore(),
            "user_preferences_store": UserPreferencesStore(),
            "chat_history": type("CH", (), {"delete_all_sessions": lambda s, k: 0})(),
            "usage_log_store": type("UL", (), {"aggregate": lambda *a, **kw: {}, "daily_buckets": lambda *a, **kw: [], "recent": lambda *a, **kw: []})(),
            "credit_store": type("CS", (), {"top_up": lambda *a, **kw: {}, "get_balance": lambda *a: 0, "list_ledger": lambda *a, **kw: [], "data": {}})(),
            "user_limits_store": type("ULS", (), {"update": lambda *a, **kw: {}, "data": {}})(),
            "byok_store": type("BK", (), {"list_keys": lambda *a: []})(),
        }))
        return TestClient(app), admin_user["id"]

    def setUp(self):
        self._orig_settings_path = os.environ.get("JARVIS_ADMIN_SETTINGS_PATH")
        for var in ["JARVIS_WAKEWORD_ENABLED", "JARVIS_WAKEWORD_ENGINE", "JARVIS_WAKEWORD_PHRASE"]:
            os.environ.pop(var, None)

    def tearDown(self):
        if self._orig_settings_path is not None:
            os.environ["JARVIS_ADMIN_SETTINGS_PATH"] = self._orig_settings_path
        else:
            os.environ.pop("JARVIS_ADMIN_SETTINGS_PATH", None)
        os.environ.pop("JARVIS_USER_STORE_PATH", None)

    def test_wakeword_status_requires_auth(self):
        client, _ = self._build_client()
        resp = client.get("/admin/wakeword/status")
        self.assertIn(resp.status_code, (401, 403))

    def test_wakeword_status_returns_structure(self):
        client, admin_id = self._build_client()
        headers = {
            "Authorization": "Bearer valid-admin-tok",
            "X-Jarvis-User-Id": admin_id,
            "X-Jarvis-Role": "admin",
        }
        resp = client.get("/admin/wakeword/status", headers=headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("enabled", data)
        self.assertIn("engine", data)
        self.assertIn("phrase", data)
        self.assertIn("openwakeword_available", data)
        self.assertIsInstance(data["openwakeword_available"], bool)
        self.assertIn("sensitivity", data)
        self.assertIn("engine_source", data)


class TestIsOpenwakewordAvailable(unittest.TestCase):
    def test_returns_bool(self):
        from jarvis.wakeword_engine import _is_openwakeword_available
        result = _is_openwakeword_available()
        self.assertIsInstance(result, bool)

    def test_returns_false_when_not_installed(self):
        with patch.dict(sys.modules, {"openwakeword": None}):
            from importlib import reload
            import jarvis.wakeword_engine as ww_mod
            reload(ww_mod)
            self.assertFalse(ww_mod._is_openwakeword_available())


if __name__ == "__main__":
    unittest.main()
