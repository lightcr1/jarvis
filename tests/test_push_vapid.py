from __future__ import annotations

import os
import tempfile

from jarvis import push_vapid


class TestVapidKeys:
    def setup_method(self):
        self._tmp = tempfile.mktemp(suffix=".json")
        os.environ["JARVIS_VAPID_KEYS_PATH"] = self._tmp
        os.environ.pop("JARVIS_VAPID_PUBLIC_KEY", None)
        os.environ.pop("JARVIS_VAPID_PRIVATE_KEY", None)
        push_vapid.reset_cache_for_tests()

    def teardown_method(self):
        os.environ.pop("JARVIS_VAPID_KEYS_PATH", None)
        os.environ.pop("JARVIS_VAPID_PUBLIC_KEY", None)
        os.environ.pop("JARVIS_VAPID_PRIVATE_KEY", None)
        push_vapid.reset_cache_for_tests()
        try:
            os.unlink(self._tmp)
        except OSError:
            pass

    def test_generates_and_persists_keys(self):
        keys = push_vapid.get_vapid_keys()
        assert keys["public_key"]
        assert keys["private_key"]
        assert os.path.exists(self._tmp)

    def test_reuses_persisted_keys_across_cache_resets(self):
        first = push_vapid.get_vapid_keys()
        push_vapid.reset_cache_for_tests()
        second = push_vapid.get_vapid_keys()
        assert first["public_key"] == second["public_key"]
        assert first["private_key"] == second["private_key"]

    def test_env_vars_take_priority(self):
        os.environ["JARVIS_VAPID_PUBLIC_KEY"] = "env-public"
        os.environ["JARVIS_VAPID_PRIVATE_KEY"] = "env-private"
        keys = push_vapid.get_vapid_keys()
        assert keys["public_key"] == "env-public"
        assert keys["private_key"] == "env-private"

    def test_result_is_cached(self):
        first = push_vapid.get_vapid_keys()
        second = push_vapid.get_vapid_keys()
        assert first is second
