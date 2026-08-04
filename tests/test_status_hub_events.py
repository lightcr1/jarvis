from __future__ import annotations

import unittest

from jarvis.runtime_state import JarvisStatusHub


class StatusHubEventsTests(unittest.TestCase):
    def setUp(self):
        self.hub = JarvisStatusHub()

    def test_snapshot_has_no_event_by_default(self):
        self.assertIsNone(self.hub.snapshot()["last_event"])

    def test_notify_populates_last_event_and_bumps_version(self):
        before_version = self.hub.snapshot()["version"]
        self.hub.notify("wakeword")
        snap = self.hub.snapshot()
        self.assertEqual("wakeword", snap["last_event"]["kind"])
        self.assertIsInstance(snap["last_event"]["ts"], float)
        self.assertEqual(before_version + 1, snap["version"])

    def test_notify_does_not_disturb_active_recording_state(self):
        token = self.hub.begin("recording", source="orb")
        self.hub.notify("wakeword")
        snap = self.hub.snapshot()
        self.assertEqual("recording", snap["state"])
        self.assertEqual("wakeword", snap["last_event"]["kind"])
        self.hub.end(token)

    def test_begin_and_end_do_not_clobber_last_event(self):
        self.hub.notify("wakeword")
        first_event = self.hub.snapshot()["last_event"]
        token = self.hub.begin("processing")
        self.hub.end(token)
        snap = self.hub.snapshot()
        self.assertEqual(first_event, snap["last_event"])

    def test_second_notify_replaces_last_event(self):
        self.hub.notify("wakeword")
        self.hub.notify("briefing_ready")
        self.assertEqual("briefing_ready", self.hub.snapshot()["last_event"]["kind"])


if __name__ == "__main__":
    unittest.main()
