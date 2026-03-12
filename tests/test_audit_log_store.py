import json
import os
import tempfile
import unittest
from unittest import mock

from jarvis.audit_log_store import AuditLogStore


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

    def test_read_events_limit_tolerates_non_integer_values(self):
        self.store.write("permission_denied", {"role": "standard_user"})
        self.store.write("permission_denied", {"role": "standard_user"})

        events = self.store.read_events(limit="not-a-number")
        self.assertEqual(len(events), 2)

    def test_read_events_limit_none_uses_default(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})

        events = self.store.read_events(limit=None)
        self.assertEqual(len(events), 2)

    def test_read_events_limit_clamps_negative_and_zero_values_to_one(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})

        self.assertEqual(len(self.store.read_events(limit=0)), 1)
        self.assertEqual(len(self.store.read_events(limit=-10)), 1)

    def test_read_events_limit_rejects_boolean_values(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})

        events = self.store.read_events(limit=True)
        self.assertEqual(len(events), 2)

    def test_read_events_limit_rejects_nan_values(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})

        events = self.store.read_events(limit=float("nan"))
        self.assertEqual(len(events), 2)

    def test_read_events_limit_rejects_non_finite_float_values(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})

        events = self.store.read_events(limit=float("inf"))
        self.assertEqual(len(events), 2)

    def test_read_events_limit_rejects_fractional_float_values(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})
        self.store.write("e3", {"role": "standard_user"})

        events = self.store.read_events(limit=1.9)
        self.assertEqual(len(events), 3)

    def test_read_events_limit_clamps_large_values_to_cap(self):
        for i in range(600):
            self.store.write(f"e-{i}", {"role": "standard_user"})

        events = self.store.read_events(limit=10000)
        self.assertEqual(len(events), 500)

    def test_read_events_limit_accepts_integral_string_values(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})
        self.store.write("e3", {"role": "standard_user"})

        events = self.store.read_events(limit="2")
        self.assertEqual(len(events), 2)

    def test_read_events_limit_accepts_whitespace_integral_string(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})
        self.store.write("e3", {"role": "standard_user"})

        events = self.store.read_events(limit=" 2 ")
        self.assertEqual(len(events), 2)

    def test_read_events_limit_clamps_negative_numeric_string_to_one(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})

        events = self.store.read_events(limit="-5")
        self.assertEqual(len(events), 1)

    def test_read_events_limit_accepts_signed_integral_string(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})
        self.store.write("e3", {"role": "standard_user"})
        self.store.write("e4", {"role": "standard_user"})

        events = self.store.read_events(limit="+3")
        self.assertEqual(len(events), 3)

    def test_read_events_limit_clamps_large_numeric_string_to_cap(self):
        for i in range(600):
            self.store.write(f"e-{i}", {"role": "standard_user"})

        events = self.store.read_events(limit="10000")
        self.assertEqual(len(events), 500)

    def test_read_events_limit_clamps_signed_zero_numeric_string_to_one(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})

        events = self.store.read_events(limit="+0")
        self.assertEqual(len(events), 1)

    def test_read_events_limit_clamps_negative_zero_numeric_string_to_one(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})

        events = self.store.read_events(limit="-0")
        self.assertEqual(len(events), 1)

    def test_read_events_limit_clamps_zero_padded_negative_numeric_string_to_one(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})

        events = self.store.read_events(limit="-0002")
        self.assertEqual(len(events), 1)

    def test_read_events_limit_accepts_zero_padded_positive_numeric_string(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})
        self.store.write("e3", {"role": "standard_user"})
        self.store.write("e4", {"role": "standard_user"})

        events = self.store.read_events(limit="0003")
        self.assertEqual(len(events), 3)

    def test_read_events_limit_accepts_signed_zero_padded_positive_numeric_string(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})
        self.store.write("e3", {"role": "standard_user"})
        self.store.write("e4", {"role": "standard_user"})

        events = self.store.read_events(limit="+0003")
        self.assertEqual(len(events), 3)

    def test_read_events_limit_accepts_whitespace_signed_zero_padded_positive_numeric_string(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})
        self.store.write("e3", {"role": "standard_user"})
        self.store.write("e4", {"role": "standard_user"})

        events = self.store.read_events(limit=" +0003 ")
        self.assertEqual(len(events), 3)

    def test_read_events_limit_rejects_non_decimal_numeric_string(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})

        events = self.store.read_events(limit="0x10")
        self.assertEqual(len(events), 2)

    def test_read_events_limit_rejects_underscore_numeric_string(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})

        events = self.store.read_events(limit="1_0")
        self.assertEqual(len(events), 2)

    def test_read_events_limit_rejects_blank_string(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})

        events = self.store.read_events(limit="   ")
        self.assertEqual(len(events), 2)

    def test_read_events_limit_rejects_malformed_signed_string(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})

        events = self.store.read_events(limit="+ 3")
        self.assertEqual(len(events), 2)

    def test_read_events_limit_rejects_scientific_notation_string(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})

        events = self.store.read_events(limit="1e2")
        self.assertEqual(len(events), 2)

    def test_read_events_limit_rejects_decimal_numeric_string(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})

        events = self.store.read_events(limit="3.0")
        self.assertEqual(len(events), 2)

    def test_read_events_limit_rejects_mixed_sign_string(self):
        self.store.write("e1", {"role": "standard_user"})
        self.store.write("e2", {"role": "standard_user"})

        events = self.store.read_events(limit="+-3")
        self.assertEqual(len(events), 2)

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

    def test_non_object_json_lines_are_ignored(self):
        with open(self.audit_path, "w", encoding="utf-8") as f:
            f.write("\"just-a-string\"\n")
            f.write("123\n")
            f.write("[1, 2, 3]\n")
            f.write(json.dumps({"event": "permission_denied", "role": "standard_user"}) + "\n")

        events = self.store.read_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "permission_denied")
        self.assertEqual(self.store.count_events(), 1)
        self.assertEqual(self.store.aggregate_counts(), {"permission_denied": 1})

    def test_read_events_returns_empty_on_read_oserror(self):
        self.store.write("permission_denied", {"role": "standard_user"})
        with mock.patch("pathlib.Path.read_text", side_effect=OSError("boom")):
            self.assertEqual(self.store.read_events(limit=10), [])

    def test_count_and_aggregate_return_zero_on_open_oserror(self):
        self.store.write("permission_denied", {"role": "standard_user"})
        with mock.patch("pathlib.Path.open", side_effect=OSError("boom")):
            self.assertEqual(self.store.count_events(), 0)
            self.assertEqual(self.store.aggregate_counts(), {})

    def test_read_events_returns_empty_on_decode_error(self):
        self.store.write("permission_denied", {"role": "standard_user"})
        with mock.patch("pathlib.Path.read_text", side_effect=UnicodeDecodeError("utf-8", b"x", 0, 1, "boom")):
            self.assertEqual(self.store.read_events(limit=10), [])

    def test_count_and_aggregate_return_zero_on_decode_error(self):
        self.store.write("permission_denied", {"role": "standard_user"})
        with mock.patch("pathlib.Path.open", side_effect=UnicodeDecodeError("utf-8", b"x", 0, 1, "boom")):
            self.assertEqual(self.store.count_events(), 0)
            self.assertEqual(self.store.aggregate_counts(), {})

    def test_query_paths_return_safe_defaults_when_exists_raises_oserror(self):
        self.store.write("permission_denied", {"role": "standard_user"})
        with mock.patch("pathlib.Path.exists", side_effect=OSError("boom")):
            self.assertEqual(self.store.read_events(limit=10), [])
            self.assertEqual(self.store.count_events(), 0)
            self.assertEqual(self.store.aggregate_counts(), {})

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


    def test_non_integer_time_bounds_are_ignored(self):
        self.store.write("permission_denied", {"role": "standard_user"})
        self.store.write("permission_denied", {"role": "standard_user"})

        events = self.store.read_events(since_ts="not-a-number", until_ts=float("nan"))
        self.assertEqual(len(events), 2)

    def test_boolean_time_bounds_are_ignored(self):
        self.store.write("permission_denied", {"role": "standard_user"})
        self.store.write("permission_denied", {"role": "standard_user"})

        events = self.store.read_events(since_ts=True, until_ts=False)
        self.assertEqual(len(events), 2)

    def test_integral_float_time_bounds_are_accepted(self):
        with open(self.audit_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"ts": 100, "event": "permission_denied", "role": "standard_user"}) + "\n")
            f.write(json.dumps({"ts": 200, "event": "permission_denied", "role": "standard_user"}) + "\n")

        events = self.store.read_events(since_ts=150.0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["ts"], 200)

    def test_count_events(self):
        self.store.write("permission_denied", {"role": "standard_user"})
        self.store.write("permission_denied", {"role": "guest_restricted"})
        self.store.write("emergency_stop_blocked", {"role": "standard_user"})

        self.assertEqual(self.store.count_events(), 3)
        self.assertEqual(self.store.count_events(event="permission_denied"), 2)
        self.assertEqual(self.store.count_events(event="missing"), 0)


    def test_read_events_ignores_non_dict_items_from_iterator(self):
        with mock.patch.object(self.store, "_iter_filtered_events", return_value=iter(["bad", {"event": "permission_denied"}])):
            events = self.store.read_events(limit=10)
        self.assertEqual(events, [{"event": "permission_denied"}])

    def test_count_events_ignores_non_dict_items_from_iterator(self):
        with mock.patch.object(self.store, "_iter_filtered_events", return_value=iter(["bad", {"event": "permission_denied"}])):
            count = self.store.count_events()
        self.assertEqual(count, 1)

    def test_aggregate_counts_ignores_non_dict_items_from_iterator(self):
        with mock.patch.object(self.store, "_iter_filtered_events", return_value=iter(["bad", {"event": "permission_denied"}])):
            counts = self.store.aggregate_counts()
        self.assertEqual(counts, {"permission_denied": 1})

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




    def test_aggregate_counts_supports_event_filter(self):
        self.store.write("unlock_issued", {"token_fingerprint": "fp-1"})
        self.store.write("unlock_revoked", {"token_fingerprint": "fp-1"})

        filtered = self.store.aggregate_counts(event="unlock_issued")
        self.assertEqual(filtered, {"unlock_issued": 1})

    def test_filter_by_token_fingerprint(self):
        self.store.write("unlock_issued", {"token_fingerprint": "fp-1"})
        self.store.write("unlock_issued", {"token_fingerprint": "fp-2"})

        events = self.store.read_events(event="unlock_issued", token_fingerprint="fp-1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["token_fingerprint"], "fp-1")

        self.assertEqual(self.store.count_events(event="unlock_issued", token_fingerprint="fp-1"), 1)
        counts = self.store.aggregate_counts(token_fingerprint="fp-1")
        self.assertEqual(counts.get("unlock_issued"), 1)

    def test_filter_by_actor_user_id(self):
        self.store.write("admin_user_created", {"actor_user_id": "usr-admin-1", "actor_role": "admin"})
        self.store.write("admin_user_created", {"actor_user_id": "usr-admin-2", "actor_role": "admin"})

        events = self.store.read_events(actor_user_id="usr-admin-1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["actor_user_id"], "usr-admin-1")

        self.assertEqual(self.store.count_events(actor_user_id="usr-admin-1"), 1)
        counts = self.store.aggregate_counts(actor_user_id="usr-admin-1")
        self.assertEqual(counts.get("admin_user_created"), 1)

    def test_role_filters_match_actor_role_for_admin_events(self):
        self.store.write("admin_user_created", {"actor_role": "admin", "user_id": "u-1"})
        self.store.write("admin_user_created", {"actor_role": "service_system", "user_id": "u-2"})

        events = self.store.read_events(role="admin")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["user_id"], "u-1")

        self.assertEqual(self.store.count_events(role="admin"), 1)

        counts = self.store.aggregate_counts(role="admin")
        self.assertEqual(counts.get("admin_user_created"), 1)

    def test_non_string_falsy_filter_values_do_not_disable_filtering(self):
        self.store.write(0, {"actor_user_id": 0, "actor_role": 0, "token_fingerprint": 0})
        self.store.write(1, {"actor_user_id": 1, "actor_role": 1, "token_fingerprint": 1})

        events = self.store.read_events(event=0, role=0, actor_user_id=0, token_fingerprint=0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], 0)

        self.assertEqual(self.store.count_events(event=0, role=0, actor_user_id=0, token_fingerprint=0), 1)
        self.assertEqual(self.store.aggregate_counts(event=0, role=0, actor_user_id=0, token_fingerprint=0), {"0": 1})

    def test_normalized_text_preserves_non_none_falsy_values(self):
        self.store.write(0, {"actor_role": 0, "token_fingerprint": 0})

        events = self.store.read_events(event="0", role="0", token_fingerprint="0")
        self.assertEqual(len(events), 1)

        self.assertEqual(
            self.store.count_events(event="0", role="0", token_fingerprint="0"),
            1,
        )

        counts = self.store.aggregate_counts(event="0", role="0", token_fingerprint="0")
        self.assertEqual(counts, {"0": 1})

    def test_boolean_timestamp_entries_are_ignored(self):
        with open(self.audit_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"ts": True, "event": "permission_denied", "role": "standard_user"}) + "\n")
            f.write(json.dumps({"ts": 123, "event": "permission_denied", "role": "standard_user"}) + "\n")

        events = self.store.read_events(event="permission_denied")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["ts"], 123)
        self.assertEqual(self.store.count_events(event="permission_denied"), 1)
        self.assertEqual(self.store.aggregate_counts(event="permission_denied"), {"permission_denied": 1})

    def test_non_finite_float_timestamp_entries_are_ignored(self):
        with open(self.audit_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"ts": float("nan"), "event": "permission_denied", "role": "standard_user"}) + "\n")
            f.write(json.dumps({"ts": float("inf"), "event": "permission_denied", "role": "standard_user"}) + "\n")
            f.write(json.dumps({"ts": 125, "event": "permission_denied", "role": "standard_user"}) + "\n")

        events = self.store.read_events(event="permission_denied")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["ts"], 125)
        self.assertEqual(self.store.count_events(event="permission_denied"), 1)
        self.assertEqual(self.store.aggregate_counts(event="permission_denied"), {"permission_denied": 1})

    def test_fractional_float_timestamp_entries_are_ignored(self):
        with open(self.audit_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"ts": 123.75, "event": "permission_denied", "role": "standard_user"}) + "\n")
            f.write(json.dumps({"ts": 124, "event": "permission_denied", "role": "standard_user"}) + "\n")

        events = self.store.read_events(event="permission_denied")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["ts"], 124)
        self.assertEqual(self.store.count_events(event="permission_denied"), 1)
        self.assertEqual(self.store.aggregate_counts(event="permission_denied"), {"permission_denied": 1})

    def test_overflow_timestamp_entries_are_ignored(self):
        with open(self.audit_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"ts": "1e1000000", "event": "permission_denied", "role": "standard_user"}) + "\n")
            f.write(json.dumps({"ts": 123, "event": "permission_denied", "role": "standard_user"}) + "\n")

        events = self.store.read_events(event="permission_denied")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["ts"], 123)
        self.assertEqual(self.store.count_events(event="permission_denied"), 1)
        self.assertEqual(self.store.aggregate_counts(event="permission_denied"), {"permission_denied": 1})

    def test_malformed_timestamp_entries_are_ignored(self):
        with open(self.audit_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"ts": "not-a-number", "event": "permission_denied", "role": "standard_user"}) + "\n")
            f.write(json.dumps({"ts": 123, "event": "permission_denied", "role": "standard_user"}) + "\n")

        events = self.store.read_events(event="permission_denied")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["ts"], 123)

        self.assertEqual(self.store.count_events(event="permission_denied"), 1)
        self.assertEqual(self.store.aggregate_counts(event="permission_denied"), {"permission_denied": 1})

    def test_filters_are_case_insensitive_for_event_role_and_fingerprint(self):
        self.store.write("ADMIN_USER_CREATED", {"actor_role": "ADMIN", "token_fingerprint": "ABCDEF1234567890"})

        events = self.store.read_events(
            event="admin_user_created",
            role="admin",
            token_fingerprint="abcdef1234567890",
        )
        self.assertEqual(len(events), 1)

        self.assertEqual(
            self.store.count_events(
                event="admin_user_created",
                role="admin",
                token_fingerprint="abcdef1234567890",
            ),
            1,
        )

        counts = self.store.aggregate_counts(
            event="admin_user_created",
            role="admin",
            token_fingerprint="abcdef1234567890",
        )
        self.assertEqual(counts.get("admin_user_created"), 1)



if __name__ == "__main__":
    unittest.main()
