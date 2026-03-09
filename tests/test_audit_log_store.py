import json
import os
import tempfile
import unittest

from audit_log_store import AuditLogStore


class AuditLogStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.audit_path = os.path.join(self.tmpdir.name, "audit.log")
        os.environ["JARVIS_AUDIT_LOG_PATH"] = self.audit_path
        self.store = AuditLogStore()

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("JARVIS_AUDIT_LOG_PATH", None)

    def test_write_and_read_newest_first(self):
        self.store.write("permission_denied", {"role": "standard_user"})
        self.store.write("dangerous_action_confirmation_requested", {"role": "admin"})

        events = self.store.read_events(limit=10)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["event"], "dangerous_action_confirmation_requested")
        self.assertEqual(events[1]["event"], "permission_denied")

    def test_filter_by_event_and_role(self):
        self.store.write("permission_denied", {"role": "standard_user"})
        self.store.write("permission_denied", {"role": "guest_restricted"})
        self.store.write("emergency_stop_blocked", {"role": "standard_user"})

        by_event = self.store.read_events(event="permission_denied")
        self.assertEqual(len(by_event), 2)

        by_role = self.store.read_events(role="standard_user")
        self.assertEqual(len(by_role), 2)

        both = self.store.read_events(event="permission_denied", role="guest_restricted")
        self.assertEqual(len(both), 1)
        self.assertEqual(both[0]["role"], "guest_restricted")

    def test_ignores_invalid_json_lines(self):
        with open(self.audit_path, "w", encoding="utf-8") as f:
            f.write("not-json\n")
            f.write(json.dumps({"event": "permission_denied", "role": "standard_user"}) + "\n")

        events = self.store.read_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "permission_denied")


    def test_filter_by_time_range(self):
        self.store.write("permission_denied", {"role": "standard_user"})
        self.store.write("permission_denied", {"role": "standard_user"})
        self.store.write("permission_denied", {"role": "standard_user"})

        events = self.store.read_events(limit=10)
        middle_ts = events[1]["ts"]

        newer_or_equal = self.store.read_events(limit=10, since_ts=middle_ts)
        self.assertTrue(all(e["ts"] >= middle_ts for e in newer_or_equal))

        older_or_equal = self.store.read_events(limit=10, until_ts=middle_ts)
        self.assertTrue(all(e["ts"] <= middle_ts for e in older_or_equal))


    def test_count_events(self):
        self.store.write("permission_denied", {"role": "standard_user"})
        self.store.write("permission_denied", {"role": "guest_restricted"})
        self.store.write("emergency_stop_blocked", {"role": "standard_user"})

        self.assertEqual(self.store.count_events(), 3)
        self.assertEqual(self.store.count_events(event="permission_denied"), 2)
        self.assertEqual(self.store.count_events(event="missing"), 0)


    def test_aggregate_counts_with_filters(self):
        self.store.write("permission_denied", {"role": "standard_user"})
        self.store.write("permission_denied", {"role": "guest_restricted"})
        self.store.write("emergency_stop_blocked", {"role": "standard_user"})

        counts_all = self.store.aggregate_counts()
        self.assertEqual(counts_all.get("permission_denied"), 2)
        self.assertEqual(counts_all.get("emergency_stop_blocked"), 1)

        counts_role = self.store.aggregate_counts(role="standard_user")
        self.assertEqual(counts_role.get("permission_denied"), 1)
        self.assertEqual(counts_role.get("emergency_stop_blocked"), 1)


if __name__ == "__main__":
    unittest.main()
