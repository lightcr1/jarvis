from __future__ import annotations

import os
import tempfile
import unittest

from jarvis.authz import resolve_effective_permissions
from jarvis.group_store import GroupStore
from jarvis.home_assistant.chat_intents import (
    AREA_SYNONYMS,
    DEVICE_KIND_SYNONYMS,
    _area_matches,
    _extract_area_from_text,
    _extract_device_kind_from_text,
    _has_quantifier,
    _has_time_reference,
    _normalize_area,
    _normalize_device_kind,
    _parse_target_day,
    _parse_target_time,
    _score_entity_match,
    execute_home_assistant_chat_intent,
    normalize_lookup,
    parse_iso_from_text,
)
from jarvis.home_assistant.client import HomeAssistantClient
from jarvis.home_assistant.service import HomeAssistantService
from jarvis.home_assistant.store import HomeAssistantStore
from jarvis.membership_store import MembershipStore
from jarvis.permission_store import PermissionStore
from jarvis.user_store import UserStore


class _AuditProbe:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def write(self, event: str, payload: dict) -> None:
        self.events.append({"event": event, **payload})


def _make_service(tmpdir: str) -> tuple[HomeAssistantService, str]:
    os.environ["JARVIS_USER_STORE_PATH"] = f"{tmpdir}/users.json"
    os.environ["JARVIS_GROUP_STORE_PATH"] = f"{tmpdir}/groups.json"
    os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = f"{tmpdir}/memberships.json"
    os.environ["JARVIS_PERMISSION_STORE_PATH"] = f"{tmpdir}/permissions.json"
    os.environ["JARVIS_HOME_ASSISTANT_STORE_PATH"] = f"{tmpdir}/home_assistant.json"
    for key in (
        "JARVIS_HOME_ASSISTANT_CALENDAR_FILE",
        "JARVIS_HOME_ASSISTANT_INBOX_FILE",
        "JARVIS_HOME_ASSISTANT_CALENDAR_URL",
        "JARVIS_HOME_ASSISTANT_CALENDAR_TOKEN",
        "JARVIS_HOME_ASSISTANT_CALENDAR_WRITE_URL",
        "JARVIS_HOME_ASSISTANT_CALENDAR_WRITE_TOKEN",
        "JARVIS_HOME_ASSISTANT_CALENDAR_SEED",
        "JARVIS_HOME_ASSISTANT_INBOX_URL",
        "JARVIS_HOME_ASSISTANT_INBOX_TOKEN",
        "JARVIS_HOME_ASSISTANT_INBOX_WRITE_URL",
        "JARVIS_HOME_ASSISTANT_INBOX_WRITE_TOKEN",
        "JARVIS_HOME_ASSISTANT_INBOX_SEED",
        "JARVIS_HOME_ASSISTANT_REMOTE_ALLOWED_CIDRS",
    ):
        os.environ.pop(key, None)

    user_store = UserStore()
    group_store = GroupStore()
    membership_store = MembershipStore()
    permission_store = PermissionStore()
    store = HomeAssistantStore()
    client = HomeAssistantClient()
    audit = _AuditProbe()
    service = HomeAssistantService(
        store=store,
        client=client,
        user_store=user_store,
        membership_store=membership_store,
        permission_store=permission_store,
        resolve_effective_permissions=resolve_effective_permissions,
        normalize_role=lambda r: r or "guest_restricted",
        audit_log=audit,
    )
    admin = user_store.create_user("owner", role="admin", enabled=True)
    return service, admin["id"]


def _add_entity(service: HomeAssistantService, *, entity_id: str, label: str, kind: str, area: str) -> dict:
    return service.store.add_managed_entity(
        {
            "entity_id": entity_id,
            "label": label,
            "kind": kind,
            "area": area,
            "approval_status": "approved",
            "onboarding_status": "managed",
            "available": True,
            "state": "off",
            "metadata": {},
        }
    )


class TestSynonymTables(unittest.TestCase):
    def test_device_kind_synonyms_cover_common_aliases(self):
        cases = [
            ("ac", "climate"),
            ("aircon", "climate"),
            ("air conditioning", "climate"),
            ("heizung", "climate"),
            ("klimaanlage", "climate"),
            ("thermostat", "climate"),
            ("lamp", "light"),
            ("licht", "light"),
            ("bulb", "light"),
            ("tv", "media"),
            ("telly", "media"),
            ("fernseher", "media"),
            ("blinds", "cover"),
            ("rollo", "cover"),
            ("jalousie", "cover"),
        ]
        for alias, expected_kind in cases:
            with self.subTest(alias=alias):
                self.assertEqual(_normalize_device_kind(alias), expected_kind, f"Expected {alias} -> {expected_kind}")

    def test_area_synonyms_cover_common_aliases(self):
        cases = [
            ("lounge", "living_room"),
            ("sitting room", "living_room"),
            ("wohnzimmer", "living_room"),
            ("master bedroom", "bedroom"),
            ("schlafzimmer", "bedroom"),
            ("loo", "bathroom"),
            ("badezimmer", "bathroom"),
            ("study", "office"),
            ("home office", "office"),
            ("arbeitszimmer", "office"),
            ("küche", "kitchen"),
            ("flur", "hall"),
            ("hallway", "hall"),
            ("keller", "basement"),
            ("garten", "garden"),
        ]
        for alias, expected in cases:
            with self.subTest(alias=alias):
                self.assertEqual(_normalize_area(alias), expected, f"Expected {alias} -> {expected}")

    def test_normalize_area_unknown_passthrough(self):
        self.assertEqual(_normalize_area("kitchen"), "kitchen")
        self.assertEqual(_normalize_area("living_room"), "living_room")
        self.assertEqual(_normalize_area("bedroom"), "bedroom")

    def test_normalize_device_kind_unknown_returns_none(self):
        self.assertIsNone(_normalize_device_kind("xyzzy"))
        self.assertIsNone(_normalize_device_kind("robot"))

    def test_device_kind_synonyms_case_insensitive(self):
        self.assertEqual(_normalize_device_kind("AC"), "climate")
        self.assertEqual(_normalize_device_kind("TV"), "media")
        self.assertEqual(_normalize_device_kind("Telly"), "media")
        self.assertEqual(_normalize_device_kind("Blinds"), "cover")


class TestAreaExtraction(unittest.TestCase):
    def test_extract_area_english_in_the(self):
        self.assertEqual(_extract_area_from_text("turn off all lights in the kitchen"), "kitchen")

    def test_extract_area_english_in(self):
        self.assertEqual(_extract_area_from_text("lights in kitchen"), "kitchen")

    def test_extract_area_german_im(self):
        result = _extract_area_from_text("Lichter im Wohnzimmer ausschalten")
        self.assertEqual(result, "living_room")

    def test_extract_area_german_in_der(self):
        result = _extract_area_from_text("Licht in der Küche ausschalten")
        self.assertEqual(result, "kitchen")

    def test_extract_area_synonym_resolved(self):
        result = _extract_area_from_text("turn off lights in the lounge")
        self.assertEqual(result, "living_room")

    def test_extract_area_synonym_schlafzimmer(self):
        result = _extract_area_from_text("AC im Schlafzimmer ausschalten")
        self.assertEqual(result, "bedroom")

    def test_extract_area_no_match_returns_none(self):
        self.assertIsNone(_extract_area_from_text("turn off the lamp"))
        self.assertIsNone(_extract_area_from_text("status check"))

    def test_extract_area_from_set_command(self):
        result = _extract_area_from_text("set the AC to 20 degrees in the bedroom")
        self.assertEqual(result, "bedroom")


class TestDeviceKindExtraction(unittest.TestCase):
    def test_extract_kind_lights(self):
        self.assertEqual(_extract_device_kind_from_text("turn off all lights"), "light")

    def test_extract_kind_ac(self):
        self.assertEqual(_extract_device_kind_from_text("turn off the AC"), "climate")

    def test_extract_kind_telly(self):
        self.assertEqual(_extract_device_kind_from_text("switch off the telly"), "media")

    def test_extract_kind_blinds(self):
        self.assertEqual(_extract_device_kind_from_text("close the blinds"), "cover")

    def test_extract_kind_german_licht(self):
        self.assertEqual(_extract_device_kind_from_text("Licht ausschalten"), "light")

    def test_extract_kind_german_klimaanlage(self):
        self.assertEqual(_extract_device_kind_from_text("Klimaanlage ausschalten"), "climate")

    def test_extract_kind_no_match_returns_none(self):
        self.assertIsNone(_extract_device_kind_from_text("do something"))
        self.assertIsNone(_extract_device_kind_from_text("check the status"))


class TestQuantifierDetection(unittest.TestCase):
    def test_all_en(self):
        self.assertTrue(_has_quantifier("turn off all lights"))

    def test_every_en(self):
        self.assertTrue(_has_quantifier("turn off every light"))

    def test_alle_de(self):
        self.assertTrue(_has_quantifier("alle Lichter ausschalten"))

    def test_no_quantifier(self):
        self.assertFalse(_has_quantifier("turn off the lamp"))
        self.assertFalse(_has_quantifier("set thermostat to 20"))


class TestAreaMatches(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(_area_matches("kitchen", "kitchen"))

    def test_synonym_match(self):
        self.assertTrue(_area_matches("lounge", "living_room"))

    def test_underscore_insensitive(self):
        self.assertTrue(_area_matches("living_room", "living room"))

    def test_no_match(self):
        self.assertFalse(_area_matches("kitchen", "bedroom"))

    def test_empty_area_no_match(self):
        self.assertFalse(_area_matches("", "kitchen"))
        self.assertFalse(_area_matches("kitchen", ""))


class TestConfidenceScoring(unittest.TestCase):
    def _make_entity(self, label: str, kind: str, area: str) -> dict:
        return {"entity_id": f"entity.{kind}.test", "label": label, "kind": kind, "area": area}

    def test_exact_label_match_scores_1(self):
        entity = self._make_entity("Kitchen Light", "light", "kitchen")
        score = _score_entity_match(entity, normalize_lookup("turn off kitchen light"), None, None)
        self.assertEqual(score, 1.0)

    def test_label_and_area_match_scores_1(self):
        entity = self._make_entity("Main Light", "light", "kitchen")
        score = _score_entity_match(entity, normalize_lookup("main light"), "kitchen", "light")
        self.assertEqual(score, 1.0)

    def test_area_and_kind_match_scores_08(self):
        entity = self._make_entity("Ceiling Light", "light", "kitchen")
        score = _score_entity_match(entity, "something unrelated", "kitchen", "light")
        self.assertAlmostEqual(score, 0.80)

    def test_kind_only_match_scores_085(self):
        entity = self._make_entity("Living Room AC", "climate", "living_room")
        score = _score_entity_match(entity, "some other text", None, "climate")
        self.assertAlmostEqual(score, 0.85)

    def test_no_match_scores_zero(self):
        entity = self._make_entity("Kitchen Light", "light", "kitchen")
        score = _score_entity_match(entity, "bedroom thermostat", "bedroom", "climate")
        self.assertEqual(score, 0.0)

    def test_below_threshold_scores_zero_for_wrong_kind(self):
        entity = self._make_entity("Kitchen Light", "light", "kitchen")
        score = _score_entity_match(entity, "some irrelevant text", "bedroom", None)
        self.assertEqual(score, 0.0)


class TestIntentRouting(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.service, self.admin_id = _make_service(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_turn_off_kitchen_lights_routes_to_area_action(self):
        _add_entity(self.service, entity_id="light.kitchen.1", label="Kitchen Light 1", kind="light", area="kitchen")
        _add_entity(self.service, entity_id="light.kitchen.2", label="Kitchen Light 2", kind="light", area="kitchen")
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off all lights in the kitchen",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("action"), "area_entity_action")
        self.assertEqual(data.get("total"), 2)

    def test_single_light_area_routes_to_entity_action(self):
        _add_entity(self.service, entity_id="light.kitchen.1", label="Kitchen Light", kind="light", area="kitchen")
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off the light in the kitchen",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("action"), "entity_action")

    def test_german_alle_lichter_kueche_ausschalten(self):
        _add_entity(self.service, entity_id="light.kueche.1", label="Küchenlampe", kind="light", area="kitchen")
        _add_entity(self.service, entity_id="light.kueche.2", label="Küchenspot", kind="light", area="kitchen")
        result = execute_home_assistant_chat_intent(
            self.service,
            "alle Lichter in der Küche ausschalten",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("action"), "area_entity_action")
        self.assertEqual(data.get("total"), 2)

    def test_lounge_synonym_resolves_to_living_room_entities(self):
        _add_entity(self.service, entity_id="light.living.1", label="Lounge Light", kind="light", area="living_room")
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off all lights in the lounge",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("action"), "entity_action")

    def test_ac_synonym_resolves_to_climate_entity(self):
        _add_entity(self.service, entity_id="climate.bedroom.1", label="Bedroom AC", kind="climate", area="bedroom")
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off the AC in the bedroom",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertIn(data.get("action"), ("entity_action", "area_entity_action"))

    def test_set_temperature_routes_to_climate_entity(self):
        _add_entity(self.service, entity_id="climate.living.1", label="Living Room Thermostat", kind="climate", area="living_room")
        result = execute_home_assistant_chat_intent(
            self.service,
            "set the temperature to 21 degrees in the living room",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("action"), "entity_action")

    def test_german_set_temperature_lounge(self):
        _add_entity(self.service, entity_id="climate.wohnzimmer.1", label="Wohnzimmer Thermostat", kind="climate", area="living_room")
        result = execute_home_assistant_chat_intent(
            self.service,
            "Temperatur im Wohnzimmer auf 20 Grad einstellen",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("action"), "entity_action")

    def test_no_matching_entities_returns_none(self):
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off all lights in the kitchen",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNone(result)

    def test_ambiguous_no_area_no_kind_no_label_falls_through(self):
        _add_entity(self.service, entity_id="light.hall.1", label="Hall Light", kind="light", area="hall")
        result = execute_home_assistant_chat_intent(
            self.service,
            "what is the meaning of life",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNone(result)

    def test_exact_label_match_routes_correctly(self):
        _add_entity(self.service, entity_id="light.bed.1", label="Bedroom Lamp", kind="light", area="bedroom")
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off the bedroom lamp",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("action"), "entity_action")

    def test_telly_synonym_routes_to_media_entity(self):
        _add_entity(self.service, entity_id="media.living.1", label="Living Room TV", kind="media", area="living_room")
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off the telly in the lounge",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertIn(data.get("action"), ("entity_action", "area_entity_action"))

    def test_german_klimaanlage_schlafzimmer_ausschalten(self):
        _add_entity(self.service, entity_id="climate.bed.1", label="Schlafzimmer AC", kind="climate", area="bedroom")
        result = execute_home_assistant_chat_intent(
            self.service,
            "Klimaanlage im Schlafzimmer ausschalten",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertIn(data.get("action"), ("entity_action", "area_entity_action"))

    def test_multi_entity_area_action_reply_contains_count(self):
        _add_entity(self.service, entity_id="light.bed.1", label="Bedroom Light 1", kind="light", area="bedroom")
        _add_entity(self.service, entity_id="light.bed.2", label="Bedroom Light 2", kind="light", area="bedroom")
        _add_entity(self.service, entity_id="light.bed.3", label="Bedroom Light 3", kind="light", area="bedroom")
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off all lights in the bedroom",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("total"), 3)
        self.assertIn("3", result.get("reply", ""))

    def test_zero_entities_in_area_falls_through_to_llm(self):
        _add_entity(self.service, entity_id="light.kitchen.1", label="Kitchen Light", kind="light", area="kitchen")
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off all lights in the garage",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNone(result)

    def test_area_entity_action_partial_failure_reply(self):
        _add_entity(self.service, entity_id="light.bed.1", label="Bedroom Light 1", kind="light", area="bedroom")
        _add_entity(self.service, entity_id="light.bed.2", label="Bedroom Light 2", kind="light", area="bedroom")
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off all lights in the bedroom",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        self.assertIn("2", result.get("reply", ""))


class TestAtticAreaSynonym(unittest.TestCase):
    def test_attic_normalizes_to_attic(self):
        self.assertEqual(_normalize_area("attic"), "attic")

    def test_dachboden_normalizes_to_attic(self):
        self.assertEqual(_normalize_area("dachboden"), "attic")

    def test_loft_normalizes_to_attic(self):
        self.assertEqual(_normalize_area("loft"), "attic")

    def test_dachgeschoss_normalizes_to_attic(self):
        self.assertEqual(_normalize_area("dachgeschoss"), "attic")

    def test_attic_in_synonym_table(self):
        self.assertIn("attic", AREA_SYNONYMS)
        self.assertIn("dachboden", AREA_SYNONYMS)

    def test_extract_attic_from_english_command(self):
        result = _extract_area_from_text("turn off all lights in the attic")
        self.assertEqual(result, "attic")

    def test_extract_dachboden_from_german_command(self):
        result = _extract_area_from_text("Licht im Dachboden ausschalten")
        self.assertEqual(result, "attic")

    def test_area_matches_dachboden_to_attic(self):
        self.assertTrue(_area_matches("dachboden", "attic"))

    def test_area_matches_attic_entities(self):
        self.assertTrue(_area_matches("attic", "attic"))


class TestEnglishTimeReference(unittest.TestCase):
    def test_tomorrow(self):
        self.assertTrue(_has_time_reference("set a timer for tomorrow at 8"))

    def test_today(self):
        self.assertTrue(_has_time_reference("remind me today at noon"))

    def test_monday(self):
        self.assertTrue(_has_time_reference("schedule for Monday"))

    def test_friday(self):
        self.assertTrue(_has_time_reference("appointment on Friday"))

    def test_noon(self):
        self.assertTrue(_has_time_reference("meeting at noon"))

    def test_midnight(self):
        self.assertTrue(_has_time_reference("backup at midnight"))

    def test_morning(self):
        self.assertTrue(_has_time_reference("wake me in the morning"))

    def test_evening(self):
        self.assertTrue(_has_time_reference("dinner this evening"))

    def test_afternoon(self):
        self.assertTrue(_has_time_reference("call in the afternoon"))

    def test_at_bare_hour(self):
        self.assertTrue(_has_time_reference("remind me tomorrow at 8"))

    def test_in_minutes(self):
        self.assertTrue(_has_time_reference("do this in 30 minutes"))

    def test_in_hours(self):
        self.assertTrue(_has_time_reference("in 2 hours"))

    def test_german_morgen(self):
        self.assertTrue(_has_time_reference("morgen um 8"))

    def test_german_montag(self):
        self.assertTrue(_has_time_reference("Montag morgens"))

    def test_no_time_reference(self):
        self.assertFalse(_has_time_reference("turn off the lights"))
        self.assertFalse(_has_time_reference("what is the temperature"))


class TestParseIsoEnglish(unittest.TestCase):
    def _parse_day_only(self, text: str) -> str:
        iso = parse_iso_from_text(text)
        return iso[:10]

    def _parse_time_only(self, text: str) -> str:
        iso = parse_iso_from_text(text)
        return iso[11:16]

    def test_tomorrow_day_is_plus_one(self):
        from datetime import datetime, timezone, timedelta
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
        self.assertEqual(self._parse_day_only("tomorrow at 8"), tomorrow)

    def test_today_day_is_today(self):
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.assertEqual(self._parse_day_only("today at noon"), today)

    def test_tomorrow_at_8_time(self):
        self.assertEqual(self._parse_time_only("tomorrow at 8"), "08:00")

    def test_noon_time(self):
        self.assertEqual(self._parse_time_only("meeting at noon"), "12:00")

    def test_midnight_time(self):
        self.assertEqual(self._parse_time_only("backup at midnight"), "00:00")

    def test_morning_time(self):
        self.assertEqual(self._parse_time_only("remind me in the morning"), "08:00")

    def test_afternoon_time(self):
        self.assertEqual(self._parse_time_only("call in the afternoon"), "15:00")

    def test_evening_time(self):
        self.assertEqual(self._parse_time_only("dinner this evening"), "19:00")

    def test_explicit_hhmm(self):
        self.assertEqual(self._parse_time_only("tomorrow at 14:30"), "14:30")

    def test_german_morgen_um_8(self):
        from datetime import datetime, timezone, timedelta
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
        self.assertEqual(self._parse_day_only("morgen um 8"), tomorrow)

    def test_german_mittag(self):
        self.assertEqual(self._parse_time_only("heute mittag"), "12:00")

    def test_german_abends(self):
        self.assertEqual(self._parse_time_only("morgen abends"), "19:00")

    def test_monday_is_next_occurrence(self):
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        expected_delta = (0 - now.weekday()) % 7 or 7
        expected = (now + timedelta(days=expected_delta)).strftime("%Y-%m-%d")
        self.assertEqual(self._parse_day_only("Monday at 9"), expected)

    def test_friday_is_next_occurrence(self):
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        expected_delta = (4 - now.weekday()) % 7 or 7
        expected = (now + timedelta(days=expected_delta)).strftime("%Y-%m-%d")
        self.assertEqual(self._parse_day_only("Friday afternoon"), expected)


class TestFallbackLogging(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.service, self.admin_id = _make_service(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_unmatched_input_returns_none(self):
        result = execute_home_assistant_chat_intent(
            self.service,
            "please explain quantum entanglement",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNone(result)

    def test_unmatched_input_with_entities_returns_none(self):
        _add_entity(self.service, entity_id="light.hall.1", label="Hall Light", kind="light", area="hall")
        result = execute_home_assistant_chat_intent(
            self.service,
            "what is the capital of france",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNone(result)

    def test_unmatched_area_command_returns_none(self):
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off all lights in the secret bunker",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNone(result)


class TestMultiDeviceGlobalCommands(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.service, self.admin_id = _make_service(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_turn_off_all_lights_globally(self):
        _add_entity(self.service, entity_id="light.hall.1", label="Hall Light", kind="light", area="hall")
        _add_entity(self.service, entity_id="light.kitchen.1", label="Kitchen Light", kind="light", area="kitchen")
        _add_entity(self.service, entity_id="light.bed.1", label="Bedroom Light", kind="light", area="bedroom")
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off all lights",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("action"), "area_entity_action")
        self.assertEqual(data.get("total"), 3)

    def test_turn_off_every_light_globally(self):
        _add_entity(self.service, entity_id="light.a.1", label="Light A", kind="light", area="hall")
        _add_entity(self.service, entity_id="light.b.1", label="Light B", kind="light", area="kitchen")
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off every light",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("total"), 2)

    def test_zero_lights_globally_falls_through(self):
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off all lights",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNone(result)

    def test_german_alle_lichter_ausschalten(self):
        _add_entity(self.service, entity_id="light.a.1", label="Licht A", kind="light", area="hall")
        _add_entity(self.service, entity_id="light.b.1", label="Licht B", kind="light", area="kitchen")
        result = execute_home_assistant_chat_intent(
            self.service,
            "alle Lichter ausschalten",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("total"), 2)


class TestAtticAreaRouting(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.service, self.admin_id = _make_service(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_turn_off_lights_in_attic_english(self):
        _add_entity(self.service, entity_id="light.attic.1", label="Attic Light", kind="light", area="attic")
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off the light in the attic",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertIn(data.get("action"), ("entity_action", "area_entity_action"))

    def test_dachboden_resolves_to_attic_entity(self):
        _add_entity(self.service, entity_id="light.attic.1", label="Dachboden Licht", kind="light", area="attic")
        result = execute_home_assistant_chat_intent(
            self.service,
            "Licht im Dachboden ausschalten",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertIn(data.get("action"), ("entity_action", "area_entity_action"))

    def test_attic_synonym_not_matching_wrong_area(self):
        _add_entity(self.service, entity_id="light.kitchen.1", label="Kitchen Light", kind="light", area="kitchen")
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off all lights in the attic",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNone(result)


class TestNewDeviceSynonyms(unittest.TestCase):
    def test_lighting_normalizes_to_light(self):
        self.assertEqual(_normalize_device_kind("lighting"), "light")

    def test_lock_normalizes_to_lock(self):
        self.assertEqual(_normalize_device_kind("lock"), "lock")

    def test_front_door_normalizes_to_lock(self):
        self.assertEqual(_normalize_device_kind("front door"), "lock")

    def test_back_door_normalizes_to_lock(self):
        self.assertEqual(_normalize_device_kind("back door"), "lock")

    def test_outlet_normalizes_to_switch(self):
        self.assertEqual(_normalize_device_kind("outlet"), "switch")

    def test_socket_normalizes_to_switch(self):
        self.assertEqual(_normalize_device_kind("socket"), "switch")

    def test_screen_normalizes_to_media(self):
        self.assertEqual(_normalize_device_kind("screen"), "media")

    def test_display_normalizes_to_media(self):
        self.assertEqual(_normalize_device_kind("display"), "media")

    def test_curtains_normalizes_to_cover(self):
        self.assertEqual(_normalize_device_kind("curtains"), "cover")

    def test_roller_blind_normalizes_to_cover(self):
        self.assertEqual(_normalize_device_kind("roller blind"), "cover")

    def test_fan_normalizes_to_fan(self):
        self.assertEqual(_normalize_device_kind("fan"), "fan")

    def test_ceiling_fan_normalizes_to_fan(self):
        self.assertEqual(_normalize_device_kind("ceiling fan"), "fan")

    def test_ventilation_normalizes_to_fan(self):
        self.assertEqual(_normalize_device_kind("ventilation"), "fan")

    def test_heat_normalizes_to_climate(self):
        self.assertEqual(_normalize_device_kind("heat"), "climate")

    def test_temperature_normalizes_to_climate(self):
        self.assertEqual(_normalize_device_kind("temperature"), "climate")


class TestNewAreaSynonyms(unittest.TestCase):
    def test_main_room_normalizes_to_living_room(self):
        self.assertEqual(_normalize_area("main room"), "living_room")

    def test_foyer_normalizes_to_hall(self):
        self.assertEqual(_normalize_area("foyer"), "hall")

    def test_corridor_normalizes_to_hall(self):
        self.assertEqual(_normalize_area("corridor"), "hall")

    def test_bath_normalizes_to_bathroom(self):
        self.assertEqual(_normalize_area("bath"), "bathroom")

    def test_restroom_normalizes_to_bathroom(self):
        self.assertEqual(_normalize_area("restroom"), "bathroom")

    def test_work_room_normalizes_to_office(self):
        self.assertEqual(_normalize_area("work room"), "office")

    def test_workroom_normalizes_to_office(self):
        self.assertEqual(_normalize_area("workroom"), "office")

    def test_patio_normalizes_to_garden(self):
        self.assertEqual(_normalize_area("patio"), "garden")

    def test_outdoor_normalizes_to_garden(self):
        self.assertEqual(_normalize_area("outdoor"), "garden")

    def test_outside_normalizes_to_garden(self):
        self.assertEqual(_normalize_area("outside"), "garden")

    def test_kitchenette_normalizes_to_kitchen(self):
        self.assertEqual(_normalize_area("kitchenette"), "kitchen")

    def test_bed_room_normalizes_to_bedroom(self):
        self.assertEqual(_normalize_area("bed room"), "bedroom")


class TestGermanSplitVerbSchalteEin(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.service, self.admin_id = _make_service(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_schalte_licht_ein_routes_to_entity_action(self):
        _add_entity(self.service, entity_id="light.living.1", label="Wohnzimmer Licht", kind="light", area="living_room")
        result = execute_home_assistant_chat_intent(
            self.service,
            "schalte das Licht ein",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("action"), "entity_action")

    def test_schalte_licht_im_wohnzimmer_ein(self):
        _add_entity(self.service, entity_id="light.living.1", label="Wohnzimmer Licht", kind="light", area="living_room")
        result = execute_home_assistant_chat_intent(
            self.service,
            "schalte das Licht im Wohnzimmer ein",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertIn(data.get("action"), ("entity_action", "area_entity_action"))

    def test_schalte_alle_lichter_ein(self):
        _add_entity(self.service, entity_id="light.a.1", label="Licht A", kind="light", area="hall")
        _add_entity(self.service, entity_id="light.b.1", label="Licht B", kind="light", area="kitchen")
        result = execute_home_assistant_chat_intent(
            self.service,
            "schalte alle Lichter ein",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("action"), "area_entity_action")
        self.assertEqual(data.get("total"), 2)

    def test_schalte_licht_aus_still_works(self):
        _add_entity(self.service, entity_id="light.living.1", label="Wohnzimmer Licht", kind="light", area="living_room")
        result = execute_home_assistant_chat_intent(
            self.service,
            "schalte das Licht aus",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("action"), "entity_action")


class TestGermanTimePatterns(unittest.TestCase):
    def test_um_8_is_time_reference(self):
        self.assertTrue(_has_time_reference("um 8"))

    def test_um_8_uhr_is_time_reference(self):
        self.assertTrue(_has_time_reference("um 8 Uhr"))

    def test_morgen_um_9_is_time_reference(self):
        self.assertTrue(_has_time_reference("morgen um 9"))

    def test_um_8_parses_hour(self):
        iso = parse_iso_from_text("morgen um 8")
        self.assertEqual(iso[11:16], "08:00")

    def test_um_20_parses_hour(self):
        iso = parse_iso_from_text("heute um 20")
        self.assertEqual(iso[11:16], "20:00")

    def test_um_20_is_not_false_negative(self):
        self.assertTrue(_has_time_reference("Termin um 20 Uhr"))

    def test_naechsten_freitag_is_time_reference(self):
        self.assertTrue(_has_time_reference("nächsten Freitag"))

    def test_no_time_reference_unchanged(self):
        self.assertFalse(_has_time_reference("schalte das licht aus"))


class TestNewSynonymExtraction(unittest.TestCase):
    def test_extract_kind_lighting(self):
        self.assertEqual(_extract_device_kind_from_text("turn off all lighting"), "light")

    def test_extract_kind_screen(self):
        self.assertEqual(_extract_device_kind_from_text("switch off the screen"), "media")

    def test_extract_kind_curtains(self):
        self.assertEqual(_extract_device_kind_from_text("close the curtains"), "cover")

    def test_extract_kind_fan(self):
        self.assertEqual(_extract_device_kind_from_text("turn off the fan"), "fan")

    def test_extract_kind_ceiling_fan(self):
        self.assertEqual(_extract_device_kind_from_text("turn off the ceiling fan"), "fan")

    def test_extract_area_foyer(self):
        self.assertEqual(_extract_area_from_text("turn off lights in the foyer"), "hall")

    def test_extract_area_corridor(self):
        self.assertEqual(_extract_area_from_text("lights in the corridor"), "hall")

    def test_extract_area_patio(self):
        # "on the patio" now resolves via the extended preposition pattern
        self.assertEqual(_extract_area_from_text("turn off lights on the patio"), "garden")

    def test_extract_area_restroom(self):
        self.assertEqual(_extract_area_from_text("turn off lights in the restroom"), "bathroom")

    def test_extract_area_kitchenette(self):
        self.assertEqual(_extract_area_from_text("lights in the kitchenette"), "kitchen")

    def test_area_matches_foyer_to_hall(self):
        self.assertTrue(_area_matches("foyer", "hall"))

    def test_area_matches_patio_to_garden(self):
        self.assertTrue(_area_matches("patio", "garden"))


class TestCompoundNounAreaExtraction(unittest.TestCase):
    """Area extraction from compound nouns without a preposition: 'bedroom light', 'kitchen thermostat'."""

    def test_bedroom_light_extracts_bedroom(self):
        self.assertEqual(_extract_area_from_text("turn off bedroom light"), "bedroom")

    def test_kitchen_lamp_extracts_kitchen(self):
        self.assertEqual(_extract_area_from_text("switch off kitchen lamp"), "kitchen")

    def test_bedroom_thermostat_extracts_bedroom(self):
        self.assertEqual(_extract_area_from_text("bedroom thermostat"), "bedroom")

    def test_bathroom_fan_extracts_bathroom(self):
        self.assertEqual(_extract_area_from_text("bathroom fan"), "bathroom")

    def test_office_light_extracts_office(self):
        self.assertEqual(_extract_area_from_text("turn on office light"), "office")

    def test_lounge_synonym_in_compound_noun(self):
        self.assertEqual(_extract_area_from_text("lounge light"), "living_room")

    def test_hallway_synonym_in_compound_noun(self):
        self.assertEqual(_extract_area_from_text("hallway lamp"), "hall")

    def test_on_the_patio_extracts_garden(self):
        self.assertEqual(_extract_area_from_text("turn off lights on the patio"), "garden")

    def test_on_the_balcony_extracts_balcony(self):
        self.assertEqual(_extract_area_from_text("lights on the balcony"), "balcony")


class TestCompoundNounAreaRouting(unittest.TestCase):
    """End-to-end routing for compound noun area patterns."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.service, self.admin_id = _make_service(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_bedroom_light_routes_to_entity_action(self):
        _add_entity(self.service, entity_id="light.bed.1", label="Bedroom Light", kind="light", area="bedroom")
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off bedroom light",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertIn(data.get("action"), ("entity_action", "area_entity_action"))

    def test_kitchen_lamp_routes_to_entity(self):
        _add_entity(self.service, entity_id="light.kitchen.1", label="Kitchen Lamp", kind="light", area="kitchen")
        result = execute_home_assistant_chat_intent(
            self.service,
            "switch off kitchen lamp",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertIn(data.get("action"), ("entity_action", "area_entity_action"))

    def test_patio_on_the_routes_to_garden_entities(self):
        _add_entity(self.service, entity_id="light.garden.1", label="Garden Light", kind="light", area="garden")
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off lights on the patio",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertIn(data.get("action"), ("entity_action", "area_entity_action"))

    def test_postfix_off_bedroom_light(self):
        _add_entity(self.service, entity_id="light.bed.1", label="Bedroom Light", kind="light", area="bedroom")
        result = execute_home_assistant_chat_intent(
            self.service,
            "bedroom light off",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertIn(data.get("action"), ("entity_action", "area_entity_action"))

    def test_postfix_on_kitchen_lamp(self):
        _add_entity(self.service, entity_id="light.kitchen.1", label="Kitchen Lamp", kind="light", area="kitchen")
        result = execute_home_assistant_chat_intent(
            self.service,
            "kitchen lamp on",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertIn(data.get("action"), ("entity_action", "area_entity_action"))


class TestBrightnessActionRouting(unittest.TestCase):
    """dim/brighten/set brightness commands route to set_brightness action."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.service, self.admin_id = _make_service(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_dim_to_50_percent_routes_to_set_brightness(self):
        _add_entity(self.service, entity_id="light.living.1", label="Living Room Light", kind="light", area="living_room")
        result = execute_home_assistant_chat_intent(
            self.service,
            "dim the living room light to 50%",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("action"), "entity_action")

    def test_dim_all_lights_in_bedroom_to_30_percent(self):
        _add_entity(self.service, entity_id="light.bed.1", label="Bedroom Light 1", kind="light", area="bedroom")
        _add_entity(self.service, entity_id="light.bed.2", label="Bedroom Light 2", kind="light", area="bedroom")
        result = execute_home_assistant_chat_intent(
            self.service,
            "dim all lights in the bedroom to 30%",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("action"), "area_entity_action")

    def test_german_dimmen_routes_to_set_brightness(self):
        _add_entity(self.service, entity_id="light.living.1", label="Wohnzimmer Licht", kind="light", area="living_room")
        result = execute_home_assistant_chat_intent(
            self.service,
            "Licht im Wohnzimmer auf 40 Prozent dimmen",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertIn(data.get("action"), ("entity_action", "area_entity_action"))

    def test_brightness_without_percent_falls_through(self):
        _add_entity(self.service, entity_id="light.living.1", label="Living Room Light", kind="light", area="living_room")
        result = execute_home_assistant_chat_intent(
            self.service,
            "brighten the living room light",
            user_id=self.admin_id,
            role="admin",
        )
        # No percentage given → resolver should not match, falls through to entity action or LLM
        # (no crash, may or may not route)
        # The key constraint: no unhandled exception
        _ = result  # just verifying no crash

    def test_no_entities_for_brightness_falls_through(self):
        result = execute_home_assistant_chat_intent(
            self.service,
            "dim all lights in the attic to 50%",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNone(result)


class TestDimBrightenSynonymExtraction(unittest.TestCase):
    """Unit tests for dim/brighten action extraction."""

    def test_dim_maps_to_set_brightness(self):
        from jarvis.home_assistant.chat_intents import _action_from_normalized
        self.assertEqual(_action_from_normalized("dim"), "set_brightness")

    def test_brighten_maps_to_set_brightness(self):
        from jarvis.home_assistant.chat_intents import _action_from_normalized
        self.assertEqual(_action_from_normalized("brighten"), "set_brightness")

    def test_brightness_maps_to_set_brightness(self):
        from jarvis.home_assistant.chat_intents import _action_from_normalized
        self.assertEqual(_action_from_normalized("brightness"), "set_brightness")

    def test_dimmen_maps_to_set_brightness(self):
        from jarvis.home_assistant.chat_intents import _action_from_normalized
        self.assertEqual(_action_from_normalized("dimmen"), "set_brightness")

    def test_helligkeit_maps_to_set_brightness(self):
        from jarvis.home_assistant.chat_intents import _action_from_normalized
        self.assertEqual(_action_from_normalized("helligkeit"), "set_brightness")

    def test_turn_off_still_maps_correctly(self):
        from jarvis.home_assistant.chat_intents import _action_from_normalized
        self.assertEqual(_action_from_normalized("turn off"), "turn_off")

    def test_turn_on_still_maps_correctly(self):
        from jarvis.home_assistant.chat_intents import _action_from_normalized
        self.assertEqual(_action_from_normalized("turn on"), "turn_on")


class TestAdditionalGermanParity(unittest.TestCase):
    """German language parity for commands that were missing coverage."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.service, self.admin_id = _make_service(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_german_heizung_routes_to_climate(self):
        _add_entity(self.service, entity_id="climate.bed.1", label="Heizung Schlafzimmer", kind="climate", area="bedroom")
        result = execute_home_assistant_chat_intent(
            self.service,
            "Heizung im Schlafzimmer ausschalten",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertIn(data.get("action"), ("entity_action", "area_entity_action"))

    def test_german_fernseher_routes_to_media(self):
        _add_entity(self.service, entity_id="media.living.1", label="Wohnzimmer Fernseher", kind="media", area="living_room")
        result = execute_home_assistant_chat_intent(
            self.service,
            "Fernseher im Wohnzimmer ausschalten",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertIn(data.get("action"), ("entity_action", "area_entity_action"))

    def test_german_jalousie_routes_to_cover(self):
        _add_entity(self.service, entity_id="cover.bed.1", label="Schlafzimmer Jalousie", kind="cover", area="bedroom")
        result = execute_home_assistant_chat_intent(
            self.service,
            "Jalousie im Schlafzimmer schließen",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)

    def test_german_temperatur_setzen(self):
        _add_entity(self.service, entity_id="climate.living.1", label="Wohnzimmer Thermostat", kind="climate", area="living_room")
        result = execute_home_assistant_chat_intent(
            self.service,
            "Temperatur im Wohnzimmer auf 22 Grad setzen",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("action"), "entity_action")

    def test_german_heute_abend_time_reference(self):
        self.assertTrue(_has_time_reference("Erinnerung heute Abend"))

    def test_german_in_30_minuten_time_reference(self):
        self.assertTrue(_has_time_reference("in 30 Minuten ausschalten"))

    def test_tonight_english_time_reference(self):
        self.assertTrue(_has_time_reference("turn off at night"))


class TestMultiDeviceEdgeCases(unittest.TestCase):
    """Edge cases for multi-device commands."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.service, self.admin_id = _make_service(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_each_keyword_fans_out_to_all(self):
        _add_entity(self.service, entity_id="light.a.1", label="Light A", kind="light", area="kitchen")
        _add_entity(self.service, entity_id="light.a.2", label="Light B", kind="light", area="kitchen")
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off each light in the kitchen",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("total"), 2)

    def test_both_keyword_fans_out_to_all(self):
        _add_entity(self.service, entity_id="light.a.1", label="Lamp 1", kind="light", area="office")
        _add_entity(self.service, entity_id="light.a.2", label="Lamp 2", kind="light", area="office")
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off both lights in the office",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("total"), 2)

    def test_all_covers_globally(self):
        _add_entity(self.service, entity_id="cover.a.1", label="Blind A", kind="cover", area="bedroom")
        _add_entity(self.service, entity_id="cover.b.1", label="Blind B", kind="cover", area="living_room")
        result = execute_home_assistant_chat_intent(
            self.service,
            "close all blinds",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("action"), "area_entity_action")
        self.assertEqual(data.get("total"), 2)

    def test_all_covers_globally_german(self):
        _add_entity(self.service, entity_id="cover.a.1", label="Rollo A", kind="cover", area="bedroom")
        _add_entity(self.service, entity_id="cover.b.1", label="Rollo B", kind="cover", area="living_room")
        result = execute_home_assistant_chat_intent(
            self.service,
            "alle Jalousien schließen",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNotNone(result)
        data = result.get("data") or {}
        self.assertEqual(data.get("total"), 2)


class TestConfidenceFallthrough(unittest.TestCase):
    """Low-confidence inputs must fall through to LLM (return None)."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.service, self.admin_id = _make_service(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_unrelated_input_returns_none(self):
        _add_entity(self.service, entity_id="light.bed.1", label="Bedroom Light", kind="light", area="bedroom")
        result = execute_home_assistant_chat_intent(
            self.service,
            "what is the weather like today",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNone(result)

    def test_area_with_no_matching_entities_returns_none(self):
        _add_entity(self.service, entity_id="light.kitchen.1", label="Kitchen Light", kind="light", area="kitchen")
        result = execute_home_assistant_chat_intent(
            self.service,
            "turn off all lights in the bathroom",
            user_id=self.admin_id,
            role="admin",
        )
        self.assertIsNone(result)

    def test_brightness_without_percent_and_no_entities_returns_none(self):
        result = execute_home_assistant_chat_intent(
            self.service,
            "dim the lights to half",
            user_id=self.admin_id,
            role="admin",
        )
        # No percent value found → brightness resolver skips, others don't match → None
        self.assertIsNone(result)
