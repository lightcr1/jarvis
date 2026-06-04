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


if __name__ == "__main__":
    unittest.main()
