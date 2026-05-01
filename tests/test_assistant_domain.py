import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from jarvis.assistant_domain import (
    _do_convert,
    _resolve_event_date,
    _safe_eval,
    block_write_if_unauthorized,
    format_rag_reply,
    rag_query_from_prompt,
    select_rag_hits,
    try_skill,
)


def _deps(**overrides):
    base = dict(
        role="admin", token=None, granted_permissions=None,
        emergency_stop_enabled=lambda: False,
        permission_check=lambda *_a: True,
        run_cmd=lambda *_a, **_k: "",
        disk_usage=lambda *_a, **_k: Mock(total=100, used=40, free=60),
        format_bytes=lambda v: f"{v}B",
        parse_meminfo=lambda: {"MemTotal": 8000000, "MemAvailable": 4000000},
        parse_ping=lambda _o: {"packet_loss": "0%"},
        tail_lines=lambda t, max_lines=6: t,
        ensure_service_allowed=lambda _s: None,
        proxmox_vm_status=lambda *_a: {},
        proxmox_lxc_status=lambda *_a: {},
        proxmox_vm_action=lambda *_a: {},
        proxmox_lxc_action=lambda *_a: {},
    )
    base.update(overrides)
    return base


class AssistantDomainTests(unittest.TestCase):
    def test_block_write_if_unauthorized_requires_token(self):
        result = block_write_if_unauthorized(
            "admin",
            None,
            granted_permissions=None,
            emergency_stop_enabled=lambda: False,
            permission_check=lambda *_args: True,
        )
        self.assertEqual("missing_token", result["data"]["error"])

    def test_rag_query_from_prompt_detects_tasks_mode(self):
        result = rag_query_from_prompt("zeige mir die taskliste")
        self.assertEqual("tasks", result["mode"])
        self.assertEqual("wikijs", result["source"])

    def test_select_rag_hits_filters_source_and_title(self):
        rag_store = Mock()
        rag_store.search.return_value = [
            {"source": "github", "title": "other", "text": "nope"},
            {"source": "wikijs", "title": "Target", "text": "match"},
            {"source": "wikijs", "title": "other", "text": "later"},
        ]
        hits = select_rag_hits(
            {"query": "target", "source": "wikijs", "title": "target"},
            rag_store=rag_store,
            limit=2,
        )
        self.assertEqual(["Target", "other"], [hit["title"] for hit in hits])

    def test_format_rag_reply_formats_tasks(self):
        reply = format_rag_reply(
            {"mode": "tasks"},
            [{"title": "Task A", "text": "Do the important thing"}],
        )
        self.assertIn("Current tasks from wiki", reply)
        self.assertIn("Task A", reply)

    def test_try_skill_rejects_invalid_ping_host(self):
        with self.assertRaises(HTTPException):
            try_skill(
                "ping invalid host!",
                role="admin",
                token="tok",
                granted_permissions=None,
                emergency_stop_enabled=lambda: False,
                permission_check=lambda *_args: True,
                run_cmd=lambda *_args, **_kwargs: "",
                disk_usage=lambda *_args, **_kwargs: None,
                format_bytes=lambda value: str(value),
                parse_meminfo=lambda: {},
                parse_ping=lambda _out: {},
                tail_lines=lambda text, max_lines=6: text,
                ensure_service_allowed=lambda _service: None,
                proxmox_vm_status=lambda *_args: {},
                proxmox_lxc_status=lambda *_args: {},
                proxmox_vm_action=lambda *_args: {},
                proxmox_lxc_action=lambda *_args: {},
            )

    def test_try_skill_can_queue_proxmox_vm_start(self):
        result = try_skill(
            "pve start vm home-pve pve 100",
            role="admin",
            token="tok",
            granted_permissions=["actions.write.execute"],
            emergency_stop_enabled=lambda: False,
            permission_check=lambda *_args: True,
            run_cmd=lambda *_args, **_kwargs: "",
            disk_usage=lambda *_args, **_kwargs: None,
            format_bytes=lambda value: str(value),
            parse_meminfo=lambda: {},
            parse_ping=lambda _out: {},
            tail_lines=lambda text, max_lines=6: text,
            ensure_service_allowed=lambda _service: None,
            proxmox_vm_status=lambda *_args: {},
            proxmox_lxc_status=lambda *_args: {},
            proxmox_vm_action=lambda *_args: {"data": "UPID:node:task"},
            proxmox_lxc_action=lambda *_args: {},
        )

        self.assertEqual("proxmox", result["data"]["provider"])
        self.assertEqual("start", result["data"]["action"])
        self.assertEqual("vm", result["data"]["resource"])


class SafeEvalTests(unittest.TestCase):
    def test_basic_arithmetic(self):
        self.assertEqual(15.0, _safe_eval("5 * 3"))
        self.assertEqual(7.0,  _safe_eval("10 - 3"))
        self.assertEqual(2.5,  _safe_eval("5 / 2"))
        self.assertEqual(8.0,  _safe_eval("2 ** 3"))

    def test_order_of_operations(self):
        self.assertEqual(14.0, _safe_eval("2 + 3 * 4"))
        self.assertEqual(20.0, _safe_eval("(2 + 3) * 4"))

    def test_rejects_non_math(self):
        self.assertIsNone(_safe_eval("das datum"))
        self.assertIsNone(_safe_eval("__import__('os')"))
        self.assertIsNone(_safe_eval("hello world"))

    def test_rejects_division_by_zero(self):
        self.assertIsNone(_safe_eval("1 / 0"))

    def test_negative_numbers(self):
        self.assertEqual(-5.0, _safe_eval("-5"))
        self.assertEqual(3.0,  _safe_eval("-2 + 5"))


class UnitConvertTests(unittest.TestCase):
    def test_km_to_miles(self):
        result, unit = _do_convert(100, "km", "miles")
        self.assertAlmostEqual(result, 62.137, places=2)
        self.assertEqual("miles", unit)

    def test_celsius_to_fahrenheit(self):
        result, unit = _do_convert(0, "celsius", "fahrenheit")
        self.assertAlmostEqual(result, 32.0, places=1)
        self.assertEqual("°F", unit)

    def test_celsius_to_kelvin(self):
        result, unit = _do_convert(0, "c", "k")
        self.assertAlmostEqual(result, 273.15, places=1)

    def test_kg_to_lbs(self):
        result, unit = _do_convert(1, "kg", "lb")
        self.assertAlmostEqual(result, 2.2046, places=2)

    def test_same_unit_returns_none(self):
        self.assertIsNone(_do_convert(100, "km", "km"))

    def test_incompatible_units_returns_none(self):
        self.assertIsNone(_do_convert(100, "km", "kg"))

    def test_unknown_unit_returns_none(self):
        self.assertIsNone(_do_convert(100, "parsecs", "km"))


class CalculatorSkillTests(unittest.TestCase):
    def test_calculate_prefix(self):
        result = try_skill("calculate 15 * 7", **_deps())
        self.assertIsNotNone(result)
        self.assertIn("105", result["reply"])
        self.assertEqual("calc", result["data"]["route"])

    def test_german_was_ist_with_number(self):
        result = try_skill("was ist 100 / 4", **_deps())
        self.assertIsNotNone(result)
        self.assertIn("25", result["reply"])

    def test_german_word_operators(self):
        result = try_skill("berechne 5 mal 6", **_deps())
        self.assertIsNotNone(result)
        self.assertIn("30", result["reply"])

    def test_was_ist_das_datum_falls_through(self):
        result = try_skill("was ist das datum", **_deps())
        self.assertIsNotNone(result)
        self.assertNotIn("calc", (result.get("data") or {}).get("route", ""))

    def test_was_ist_das_wetter_falls_through_to_weather(self):
        result = try_skill("was ist das wetter", **_deps(), user_prefs={"location": ""})
        self.assertIsNotNone(result)
        route = (result.get("data") or {}).get("route", "")
        self.assertEqual("weather", route)


class UnitConverterSkillTests(unittest.TestCase):
    def test_100_km_to_miles(self):
        result = try_skill("100 km to miles", **_deps())
        self.assertIsNotNone(result)
        self.assertIn("miles", result["reply"].lower())
        self.assertEqual("convert", result["data"]["route"])

    def test_30_celsius_to_fahrenheit(self):
        result = try_skill("convert 30 celsius to fahrenheit", **_deps())
        self.assertIsNotNone(result)
        self.assertIn("°F", result["reply"])

    def test_unknown_units_returns_none(self):
        result = try_skill("100 parsecs to cubits", **_deps())
        self.assertIsNone(result)


class NotesSkillTests(unittest.TestCase):
    def test_remember_saves_note(self):
        result = try_skill("remember that the server password is in vault", **_deps(), user_prefs={})
        self.assertIsNotNone(result)
        self.assertIn("save_to_prefs", result["data"])
        notes = result["data"]["save_to_prefs"]["notes"]
        self.assertEqual(1, len(notes))
        self.assertIn("server password", notes[0])

    def test_remember_appends_to_existing(self):
        result = try_skill("remember that dinner at 7pm", **_deps(), user_prefs={"notes": ["existing note"]})
        notes = result["data"]["save_to_prefs"]["notes"]
        self.assertEqual(2, len(notes))

    def test_recall_with_notes(self):
        result = try_skill("what do you remember", **_deps(), user_prefs={"notes": ["buy milk", "call doctor"]})
        self.assertIsNotNone(result)
        self.assertIn("buy milk", result["reply"])
        self.assertIn("call doctor", result["reply"])

    def test_recall_empty(self):
        result = try_skill("what do you remember", **_deps(), user_prefs={})
        self.assertIn("No notes", result["reply"])

    def test_forget_removes_matching(self):
        result = try_skill("forget milk", **_deps(), user_prefs={"notes": ["buy milk", "call doctor"]})
        remaining = result["data"]["save_to_prefs"]["notes"]
        self.assertEqual(["call doctor"], remaining)

    def test_forget_no_match(self):
        result = try_skill("forget dentist", **_deps(), user_prefs={"notes": ["buy milk"]})
        self.assertEqual(0, result["data"]["removed"])


class SystemSkillTests(unittest.TestCase):
    def test_cpu_skill(self):
        result = try_skill("cpu", **_deps())
        self.assertIsNotNone(result)
        self.assertIn("load", result["reply"].lower())
        self.assertIn("load1", result["data"])

    def test_ip_skill_parses_addresses(self):
        result = try_skill("ip", **_deps(run_cmd=lambda *_a, **_k: "inet 192.168.1.10/24 brd 192.168.1.255"))
        self.assertIsNotNone(result)
        self.assertIn("192.168.1.10/24", result["reply"])

    def test_whoami_shows_display_name(self):
        result = try_skill("whoami", **_deps(), user_prefs={"display_name": "Lukas", "location": "Munich", "notes": ["x", "y"]})
        self.assertIn("Lukas", result["reply"])
        self.assertIn("Munich", result["reply"])
        self.assertIn("2 saved note(s)", result["reply"])

    def test_time_reply_has_day_format(self):
        result = try_skill("time", **_deps())
        self.assertIsNotNone(result)
        self.assertIn("It is", result["reply"])
        self.assertIn("iso", result["data"])

    def test_natural_language_memory_query(self):
        result = try_skill("how much memory", **_deps())
        self.assertIsNotNone(result)
        self.assertIn("free", result["reply"].lower())

    def test_natural_language_disk_query(self):
        result = try_skill("how much disk space", **_deps())
        self.assertIsNotNone(result)
        self.assertIn("/", result["reply"])


class NameSettingSkillTests(unittest.TestCase):
    def test_my_name_is_saves_display_name(self):
        result = try_skill("my name is Lukas", **_deps(), user_prefs={})
        self.assertIsNotNone(result)
        self.assertEqual("Lukas", result["data"]["display_name"])
        self.assertEqual("Lukas", result["data"]["save_to_prefs"]["display_name"])

    def test_call_me_saves_display_name(self):
        result = try_skill("call me Alice", **_deps(), user_prefs={})
        self.assertIsNotNone(result)
        self.assertEqual("Alice", result["data"]["display_name"])

    def test_name_filter_ignores_short_preposition(self):
        result = try_skill("I'm in Berlin", **_deps(), user_prefs={})
        # Should match location, not name
        if result:
            self.assertNotEqual("Berlin", result.get("data", {}).get("display_name"))


class LocationSkillTests(unittest.TestCase):
    def test_set_location_english(self):
        result = try_skill("I'm in Berlin", **_deps(), user_prefs={})
        self.assertIsNotNone(result)
        self.assertEqual("Berlin", result["data"]["location"])
        self.assertEqual("Berlin", result["data"]["save_to_prefs"]["location"])

    def test_set_location_german(self):
        result = try_skill("ich bin in München", **_deps(), user_prefs={})
        self.assertIsNotNone(result)
        self.assertIn("München", result["data"]["location"])


class TimerSkillTests(unittest.TestCase):
    def test_timer_minutes(self):
        result = try_skill("timer for 5 minutes", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("reminder", result["data"]["route"])
        self.assertEqual(300_000, result["data"]["delay_ms"])
        self.assertIn("5 minute", result["reply"])

    def test_timer_seconds(self):
        result = try_skill("set a timer for 30 seconds", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual(30_000, result["data"]["delay_ms"])
        self.assertIn("second", result["reply"])

    def test_timer_hours(self):
        result = try_skill("timer for 2 hours", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual(7_200_000, result["data"]["delay_ms"])

    def test_remind_me_in_with_task(self):
        result = try_skill("remind me in 10 minutes to check the oven", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("reminder", result["data"]["route"])
        self.assertEqual(600_000, result["data"]["delay_ms"])
        self.assertIn("check the oven", result["data"]["label"])
        self.assertIn("check the oven", result["reply"])

    def test_remind_me_single_minute(self):
        result = try_skill("remind me in 1 minute to take medication", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual(60_000, result["data"]["delay_ms"])
        # singular "minute" not "minutes"
        self.assertIn("1 minute", result["reply"])

    def test_timer_short_unit_alias(self):
        result = try_skill("timer for 90 sec", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual(90_000, result["data"]["delay_ms"])


class SystemSkillExtraTests(unittest.TestCase):
    def test_processes_returns_list(self):
        fake_ps = (
            "USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND\n"
            "root  1   0.1  0.5  100  50  ?   S    00:00 0:01 /sbin/init\n"
            "www   99  5.2  1.2  200 100  ?   S    00:00 0:05 nginx: worker process\n"
        )
        result = try_skill("processes", **_deps(run_cmd=lambda *_a, **_k: fake_ps))
        self.assertIsNotNone(result)
        self.assertIn("processes", result["data"])

    def test_ip_empty_output_returns_gracefully(self):
        result = try_skill("ip", **_deps(run_cmd=lambda *_a, **_k: ""))
        self.assertIsNotNone(result)
        self.assertEqual([], result["data"]["addresses"])

    def test_whoami_no_prefs(self):
        result = try_skill("whoami", **_deps(), user_prefs={})
        self.assertIsNotNone(result)
        self.assertIn("authenticated user", result["reply"])

    def test_hostname_returns_hostname(self):
        result = try_skill("hostname", **_deps())
        self.assertIsNotNone(result)
        self.assertIn("hostname", result["data"])

    def test_system_status_returns_health_metrics(self):
        result = try_skill("system status", **_deps())
        self.assertIsNotNone(result)
        self.assertIn("load", result["data"])
        self.assertIn("memory", result["data"])
        self.assertIn("disk", result["data"])

    def test_help_lists_skills(self):
        result = try_skill("help", **_deps())
        self.assertIsNotNone(result)
        self.assertIn("skills", result["data"])
        self.assertGreater(len(result["data"]["skills"]), 5)

    def test_jarvis_identity(self):
        result = try_skill("who are you", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("identity", result["data"]["route"])
        self.assertIn("J.A.R.V.I.S.", result["reply"])

    def test_docker_parses_rows(self):
        fake = "nginx\tUp 2 hours\tnginx:latest\nredis\tUp 1 day\tredis:7\n"
        result = try_skill("docker", **_deps(run_cmd=lambda *_a, **_k: fake))
        self.assertIsNotNone(result)
        self.assertEqual(2, len(result["data"]["containers"]))
        self.assertEqual("nginx", result["data"]["containers"][0]["name"])

    def test_health_skill(self):
        result = try_skill("health", **_deps())
        self.assertIsNotNone(result)
        self.assertTrue(result["data"]["ok"])

    def test_sysinfo_returns_all_fields(self):
        result = try_skill("sysinfo", **_deps())
        self.assertIsNotNone(result)
        d = result["data"]
        self.assertIn("hostname", d)
        self.assertIn("os", d)
        self.assertIn("cpu_cores", d)
        self.assertIn("load", d)
        self.assertIn("ram_total", d)
        self.assertIn("disk_total", d)
        self.assertIn("uptime", d)

    def test_sysinfo_aliases(self):
        for phrase in ("system info", "system information", "about this system", "os info"):
            result = try_skill(phrase, **_deps())
            self.assertIsNotNone(result, f"sysinfo not triggered for: {phrase}")
            self.assertIn("hostname", result["data"])


class WhoSkillTests(unittest.TestCase):
    def test_who_parses_output(self):
        fake_who = (
            "lukas   pts/0        2026-04-30 10:00 (192.168.1.10)\n"
            "root    pts/1        2026-04-30 09:00 (192.168.1.1)\n"
        )
        result = try_skill("who", **_deps(run_cmd=lambda *_a, **_k: fake_who))
        self.assertIsNotNone(result)
        self.assertEqual(2, len(result["data"]["users"]))
        self.assertIn("lukas", result["reply"])

    def test_who_empty_returns_gracefully(self):
        result = try_skill("who", **_deps(run_cmd=lambda *_a, **_k: ""))
        self.assertIsNotNone(result)
        self.assertEqual([], result["data"]["users"])

    def test_who_aliases(self):
        for phrase in ("who is logged in", "logged in users", "w"):
            result = try_skill(phrase, **_deps(run_cmd=lambda *_a, **_k: ""))
            self.assertIsNotNone(result, f"who not triggered for: {phrase}")


class KernelAndLoginSkillTests(unittest.TestCase):
    def test_kernel_skill(self):
        result = try_skill("kernel", **_deps(run_cmd=lambda *_a, **_k: "5.15.0-101-generic"))
        self.assertIsNotNone(result)
        self.assertIn("kernel", result["data"])
        self.assertIn("5.15.0", result["reply"])

    def test_uname_alias(self):
        result = try_skill("uname -r", **_deps(run_cmd=lambda *_a, **_k: "6.1.0-server"))
        self.assertIsNotNone(result)
        self.assertIn("6.1.0", result["reply"])

    def test_last_logins_parses_output(self):
        fake_last = (
            "root  pts/0  192.168.1.10  Thu Apr 30 10:00:00 2026  still logged in\n"
            "admin pts/1  192.168.1.11  Wed Apr 29 09:15:23 2026 - Wed Apr 29 09:45:00 2026\n"
            "wtmp begins Mon Apr 27 00:00:00 2026\n"
        )
        result = try_skill("last", **_deps(run_cmd=lambda *_a, **_k: fake_last))
        self.assertIsNotNone(result)
        self.assertGreater(len(result["data"]["logins"]), 0)
        self.assertIn("root", result["reply"])

    def test_last_empty_output(self):
        result = try_skill("last logins", **_deps(run_cmd=lambda *_a, **_k: ""))
        self.assertIsNotNone(result)
        self.assertEqual([], result["data"]["logins"])


class NetworkSkillTests(unittest.TestCase):
    def test_ports_parses_ss_output(self):
        fake_ss = (
            "Netid State   Recv-Q Send-Q  Local Address:Port\n"
            "tcp   LISTEN  0      128     0.0.0.0:22\n"
            "tcp   LISTEN  0      5       127.0.0.1:8080\n"
            "udp   UNCONN  0      0       0.0.0.0:53\n"
        )
        result = try_skill("ports", **_deps(run_cmd=lambda *_a, **_k: fake_ss))
        self.assertIsNotNone(result)
        self.assertEqual(3, len(result["data"]["listening"]))
        self.assertIn("22", result["reply"])

    def test_ports_empty_returns_gracefully(self):
        result = try_skill("ports", **_deps(run_cmd=lambda *_a, **_k: "Netid State Recv-Q Send-Q Local\n"))
        self.assertIsNotNone(result)
        self.assertEqual(0, len(result["data"]["listening"]))

    def test_open_ports_nlp(self):
        result = try_skill("what open ports are there", **_deps(run_cmd=lambda *_a, **_k: ""))
        self.assertIsNotNone(result)
        self.assertIn("ports", result["data"])


class DateCalcSkillTests(unittest.TestCase):
    def test_days_until_christmas(self):
        result = try_skill("days until christmas", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("date_calc", result["data"]["route"])
        self.assertGreater(result["data"]["days"], 0)
        self.assertIn("December", result["reply"])

    def test_days_until_halloween(self):
        result = try_skill("days until halloween", **_deps())
        self.assertIsNotNone(result)
        self.assertGreater(result["data"]["days"], 0)

    def test_days_until_iso_date(self):
        result = try_skill("days until 2027-01-01", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("2027-01-01", result["data"]["target"])

    def test_days_since_january_1_returns_past_date(self):
        result = try_skill("days since january 1", **_deps())
        self.assertIsNotNone(result)
        self.assertGreater(result["data"]["days"], 0)
        self.assertIn("2026", result["reply"])

    def test_what_day_is_n_days_from_now(self):
        result = try_skill("what day is 7 days from now", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("date_calc", result["data"]["route"])
        self.assertEqual(7, result["data"]["days_offset"])

    def test_what_day_is_n_weeks_from_now(self):
        result = try_skill("what day is 2 weeks from now", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual(14, result["data"]["days_offset"])

    def test_resolve_event_date_christmas(self):
        d = _resolve_event_date("christmas")
        self.assertIsNotNone(d)
        self.assertEqual(12, d.month)
        self.assertEqual(25, d.day)

    def test_resolve_event_date_with_punctuation(self):
        d = _resolve_event_date("christmas!")
        self.assertIsNotNone(d)
        self.assertEqual(12, d.month)

    def test_resolve_event_date_named_month_day(self):
        from datetime import date as dt
        d = _resolve_event_date("december 25")
        self.assertIsNotNone(d)
        self.assertEqual(12, d.month)
        self.assertEqual(25, d.day)

    def test_resolve_event_date_forward_only_false(self):
        from datetime import date as dt
        d = _resolve_event_date("january 1", forward_only=False)
        self.assertIsNotNone(d)
        self.assertEqual(2026, d.year)


class TimezoneSkillTests(unittest.TestCase):
    def test_time_in_tokyo(self):
        result = try_skill("time in tokyo", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("timezone", result["data"]["route"])
        self.assertEqual("Asia/Tokyo", result["data"]["tz"])
        self.assertIn("Tokyo", result["reply"])
        self.assertIn("time", result["data"])

    def test_time_in_new_york(self):
        result = try_skill("time in new york", **_deps())
        self.assertIsNotNone(result)
        self.assertIn("New York", result["reply"])

    def test_what_is_the_time_in_london(self):
        result = try_skill("what is the time in london", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("timezone", result["data"]["route"])
        self.assertIn("London", result["reply"])

    def test_unknown_city_falls_through(self):
        result = try_skill("time in atlantis", **_deps())
        self.assertIsNone(result)

    def test_time_in_utc(self):
        result = try_skill("time in utc", **_deps())
        self.assertIsNotNone(result)
        self.assertIn("UTC", result["reply"])


class NotesExtendedTests(unittest.TestCase):
    def test_clear_notes(self):
        result = try_skill("clear all notes", **_deps(), user_prefs={"notes": ["one", "two"]})
        self.assertIsNotNone(result)
        self.assertEqual([], result["data"]["save_to_prefs"]["notes"])
        self.assertEqual("notes_cleared", result["data"]["route"])

    def test_clear_notes_alias(self):
        result = try_skill("delete all notes", **_deps(), user_prefs={"notes": ["x"]})
        self.assertIsNotNone(result)
        self.assertEqual("notes_cleared", result["data"]["route"])

    def test_erase_notes(self):
        result = try_skill("erase notes", **_deps(), user_prefs={})
        self.assertIsNotNone(result)
        self.assertEqual("notes_cleared", result["data"]["route"])


class LoadAverageSkillTests(unittest.TestCase):
    def test_load_command(self):
        result = try_skill("load", **_deps())
        self.assertIsNotNone(result)
        self.assertIn("load1", result["data"])
        self.assertIn("pct", result["data"])

    def test_load_average_alias(self):
        result = try_skill("load average", **_deps())
        self.assertIsNotNone(result)
        self.assertIn("Load average", result["reply"])

    def test_server_load(self):
        result = try_skill("server load", **_deps())
        self.assertIsNotNone(result)
        self.assertIn("load1", result["data"])


class TimerSkillEdgeCaseTests(unittest.TestCase):
    def test_timer_label_default_when_no_task(self):
        result = try_skill("timer for 5 minutes", **_deps())
        self.assertIsNotNone(result)
        self.assertIn("Timer", result["data"]["label"])

    def test_remind_german_preposition_dass(self):
        result = try_skill("remind me in 2 minutes that dinner is ready", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("reminder", result["data"]["route"])
        self.assertEqual(120_000, result["data"]["delay_ms"])


class DevUtilSkillTests(unittest.TestCase):
    def test_base64_encode(self):
        import base64 as _b64
        result = try_skill("base64 encode hello world", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("encode", result["data"]["op"])
        expected = _b64.b64encode(b"hello world").decode()
        self.assertEqual(expected, result["data"]["result"])

    def test_base64_decode(self):
        result = try_skill("base64 decode aGVsbG8=", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("decode", result["data"]["op"])
        self.assertEqual("hello", result["data"]["result"])

    def test_base64_decode_invalid(self):
        result = try_skill("base64 decode not!!!valid", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("invalid", result["data"]["error"])

    def test_sha256_hash(self):
        import hashlib
        result = try_skill("sha256 hello", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("sha256", result["data"]["algo"])
        expected = hashlib.sha256(b"hello").hexdigest()
        self.assertEqual(expected, result["data"]["result"])

    def test_md5_hash(self):
        import hashlib
        result = try_skill("md5 test", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("md5", result["data"]["algo"])
        expected = hashlib.md5(b"test").hexdigest()
        self.assertEqual(expected, result["data"]["result"])

    def test_hash_alias(self):
        import hashlib
        result = try_skill("hash mydata", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("sha256", result["data"]["algo"])
        expected = hashlib.sha256(b"mydata").hexdigest()
        self.assertEqual(expected, result["data"]["result"])

    def test_url_encode(self):
        result = try_skill("url encode hello world & more", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("encode", result["data"]["op"])
        self.assertIn("%20", result["data"]["result"])

    def test_url_decode(self):
        result = try_skill("url decode hello%20world", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("decode", result["data"]["op"])
        self.assertEqual("hello world", result["data"]["result"])

    def test_hex_conversion(self):
        result = try_skill("hex 255", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("hex", result["data"]["base"])
        self.assertEqual("0xff", result["data"]["result"])

    def test_bin_conversion(self):
        result = try_skill("bin 10", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("bin", result["data"]["base"])
        self.assertEqual("0b1010", result["data"]["result"])

    def test_oct_conversion(self):
        result = try_skill("oct 8", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("oct", result["data"]["base"])
        self.assertEqual("0o10", result["data"]["result"])

    def test_generate_password_default_length(self):
        result = try_skill("generate password", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("password", result["data"]["route"])
        self.assertEqual(20, result["data"]["length"])
        pw = result["data"]["password"]
        self.assertEqual(20, len(pw))

    def test_generate_password_custom_length(self):
        result = try_skill("generate password 32", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual(32, result["data"]["length"])
        self.assertEqual(32, len(result["data"]["password"]))

    def test_generate_password_aliases(self):
        for phrase in ["random password", "gen password", "create a password"]:
            with self.subTest(phrase=phrase):
                result = try_skill(phrase, **_deps())
                self.assertIsNotNone(result)
                self.assertEqual("password", result["data"]["route"])

    def test_generate_password_too_short_clamped(self):
        result = try_skill("generate password 2", **_deps())
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result["data"]["length"], 8)

    def test_generate_password_too_long_clamped(self):
        result = try_skill("generate password 200", **_deps())
        self.assertIsNotNone(result)
        self.assertLessEqual(result["data"]["length"], 64)


class MathSkillTests(unittest.TestCase):
    def test_prime_check_true(self):
        result = try_skill("is 7 prime", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("prime", result["data"]["route"])
        self.assertTrue(result["data"]["is_prime"])
        self.assertEqual(7, result["data"]["n"])

    def test_prime_check_false(self):
        result = try_skill("is 9 prime", **_deps())
        self.assertIsNotNone(result)
        self.assertFalse(result["data"]["is_prime"])

    def test_prime_check_two(self):
        result = try_skill("is 2 prime", **_deps())
        self.assertIsNotNone(result)
        self.assertTrue(result["data"]["is_prime"])

    def test_prime_check_one_is_not_prime(self):
        result = try_skill("is 1 prime", **_deps())
        self.assertIsNotNone(result)
        self.assertFalse(result["data"]["is_prime"])

    def test_prime_check_zero_is_not_prime(self):
        result = try_skill("is 0 prime", **_deps())
        self.assertIsNotNone(result)
        self.assertFalse(result["data"]["is_prime"])

    def test_prime_check_alias(self):
        result = try_skill("prime 13", **_deps())
        self.assertIsNotNone(result)
        self.assertTrue(result["data"]["is_prime"])

    def test_prime_large(self):
        result = try_skill("is 97 prime", **_deps())
        self.assertIsNotNone(result)
        self.assertTrue(result["data"]["is_prime"])

    def test_factorial_basic(self):
        result = try_skill("factorial 5", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("factorial", result["data"]["route"])
        self.assertEqual(120, result["data"]["result"])

    def test_factorial_zero(self):
        result = try_skill("factorial 0", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual(1, result["data"]["result"])

    def test_factorial_one(self):
        result = try_skill("fact 1", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual(1, result["data"]["result"])

    def test_factorial_too_large(self):
        result = try_skill("factorial 25", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("too_large", result["data"]["error"])

    def test_factorial_exclamation_syntax(self):
        result = try_skill("6!", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual(720, result["data"]["result"])

    def test_fibonacci_basic(self):
        result = try_skill("fibonacci 5", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("fibonacci", result["data"]["route"])
        self.assertEqual([0, 1, 1, 2, 3], result["data"]["sequence"][:5])

    def test_fibonacci_alias_fib(self):
        result = try_skill("fib 7", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual(7, result["data"]["n"])

    def test_fibonacci_capped_at_30(self):
        result = try_skill("fibonacci 100", **_deps())
        self.assertIsNotNone(result)
        self.assertLessEqual(len(result["data"]["sequence"]), 30)

    def test_fibonacci_first_is_zero(self):
        result = try_skill("fibonacci 3", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual(0, result["data"]["sequence"][0])


class ColorWordCountSkillTests(unittest.TestCase):
    def test_hex_to_rgb_long(self):
        result = try_skill("hex to rgb #ff8800", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("color", result["data"]["route"])
        self.assertEqual(255, result["data"]["r"])
        self.assertEqual(136, result["data"]["g"])
        self.assertEqual(0, result["data"]["b"])
        self.assertEqual("#FF8800", result["data"]["hex"])

    def test_hex_to_rgb_without_hash(self):
        result = try_skill("hex to rgb ff0000", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual(255, result["data"]["r"])
        self.assertEqual(0, result["data"]["g"])
        self.assertEqual(0, result["data"]["b"])

    def test_hex_to_rgb_short_form(self):
        result = try_skill("color #f00", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("color", result["data"]["route"])
        self.assertEqual(255, result["data"]["r"])
        self.assertEqual(0, result["data"]["g"])
        self.assertEqual(0, result["data"]["b"])

    def test_rgb_to_hex(self):
        result = try_skill("rgb to hex 255 136 0", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("color", result["data"]["route"])
        self.assertEqual("#FF8800", result["data"]["hex"])

    def test_rgb_to_hex_with_commas(self):
        result = try_skill("rgb 0, 0, 255", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("#0000FF", result["data"]["hex"])

    def test_word_count_basic(self):
        result = try_skill("word count hello world foo", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("word_count", result["data"]["route"])
        self.assertEqual(3, result["data"]["words"])

    def test_word_count_alias_wc(self):
        result = try_skill("wc the quick brown fox", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("word_count", result["data"]["route"])
        self.assertEqual(4, result["data"]["words"])

    def test_word_count_chars(self):
        result = try_skill("word count hello", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual(5, result["data"]["chars"])
        self.assertEqual(5, result["data"]["chars_no_spaces"])

    def test_count_words_alias(self):
        result = try_skill("count words one two three", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual(3, result["data"]["words"])


class UuidTimestampDnsSkillTests(unittest.TestCase):
    def test_uuid_returns_valid_uuid(self):
        import uuid as _uuid_lib
        result = try_skill("uuid", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("uuid", result["data"]["route"])
        uid = result["data"]["uuid"]
        parsed = _uuid_lib.UUID(uid)
        self.assertEqual(parsed.version, 4)

    def test_uuid_aliases(self):
        for phrase in ["generate uuid", "new uuid", "uuid4", "random uuid", "create uuid"]:
            with self.subTest(phrase=phrase):
                result = try_skill(phrase, **_deps())
                self.assertIsNotNone(result)
                self.assertEqual("uuid", result["data"]["route"])

    def test_uuid_each_call_unique(self):
        r1 = try_skill("uuid", **_deps())
        r2 = try_skill("uuid", **_deps())
        self.assertNotEqual(r1["data"]["uuid"], r2["data"]["uuid"])

    def test_timestamp_returns_unix_integer(self):
        import time as _t
        before = int(_t.time())
        result = try_skill("timestamp", **_deps())
        after = int(_t.time())
        self.assertIsNotNone(result)
        self.assertEqual("timestamp", result["data"]["route"])
        ts = result["data"]["unix"]
        self.assertGreaterEqual(ts, before)
        self.assertLessEqual(ts, after)

    def test_timestamp_aliases(self):
        for phrase in ["unix timestamp", "unix time", "epoch", "current timestamp", "unixtime"]:
            with self.subTest(phrase=phrase):
                result = try_skill(phrase, **_deps())
                self.assertIsNotNone(result)
                self.assertEqual("timestamp", result["data"]["route"])

    def test_timestamp_has_iso_field(self):
        result = try_skill("timestamp", **_deps())
        iso = result["data"]["iso"]
        self.assertRegex(iso, r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

    def test_dns_resolves_localhost(self):
        result = try_skill("dns localhost", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("dns", result["data"]["route"])
        self.assertIn("localhost", result["data"]["host"])
        self.assertGreater(len(result["data"]["addresses"]), 0)

    def test_dns_aliases(self):
        for prefix in ["resolve", "lookup", "nslookup", "dig"]:
            with self.subTest(prefix=prefix):
                result = try_skill(f"{prefix} localhost", **_deps())
                self.assertIsNotNone(result)
                self.assertEqual("dns", result["data"]["route"])

    def test_dns_nxdomain_returns_error(self):
        result = try_skill("dns this.domain.does.not.exist.invalid", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("dns", result["data"]["route"])
        self.assertEqual([], result["data"]["addresses"])
        self.assertEqual("nxdomain", result["data"]["error"])


class BriefingSkillTests(unittest.TestCase):
    def test_briefing_returns_route(self):
        result = try_skill("briefing", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("briefing", result["data"]["route"])

    def test_briefing_aliases(self):
        for phrase in ["morning briefing", "status briefing", "daily briefing",
                       "give me a briefing", "status report", "good morning", "sitrep"]:
            with self.subTest(phrase=phrase):
                result = try_skill(phrase, **_deps())
                self.assertIsNotNone(result)
                self.assertEqual("briefing", result["data"]["route"])

    def test_briefing_reply_starts_with_salutation(self):
        result = try_skill("briefing", **_deps())
        # Reply starts with a time-of-day salutation
        self.assertTrue(
            result["reply"].startswith("Good") or result["reply"].startswith("Sir"),
            f"Expected salutation, got: {result['reply'][:40]}",
        )

    def test_briefing_contains_time_and_date(self):
        result = try_skill("briefing", **_deps())
        self.assertIn("date", result["data"])
        self.assertIn("time", result["data"])

    def test_briefing_contains_system_metrics(self):
        result = try_skill("briefing", **_deps())
        d = result["data"]
        self.assertIn("load1", d)
        self.assertIn("mem_pct", d)
        self.assertIn("disk_pct", d)

    def test_briefing_with_location_mentions_location(self):
        result = try_skill("briefing", **_deps(user_prefs={"location": "Berlin", "notes": []}))
        self.assertIn("Berlin", result["reply"])

    def test_briefing_with_notes_reports_count(self):
        result = try_skill("briefing", **_deps(user_prefs={"notes": ["note1", "note2"], "location": ""}))
        self.assertIn("2", result["reply"])

    def test_briefing_salutation_in_data(self):
        result = try_skill("briefing", **_deps())
        self.assertIn("salutation", result["data"])
        self.assertTrue(result["data"]["salutation"].startswith("Good") or
                        result["data"]["salutation"].startswith("Sir"))

    def test_briefing_good_morning_alias(self):
        result = try_skill("good morning", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("briefing", result["data"]["route"])

    def test_briefing_no_notes_no_location_does_not_crash(self):
        result = try_skill("briefing", **_deps(user_prefs=None))
        self.assertIsNotNone(result)
        self.assertEqual("briefing", result["data"]["route"])


class HttpSslSkillTests(unittest.TestCase):
    def test_http_check_200(self):
        import http.client
        mock_resp = Mock()
        mock_resp.status = 200
        mock_conn = Mock()
        mock_conn.getresponse.return_value = mock_resp
        with patch("http.client.HTTPSConnection", return_value=mock_conn):
            result = try_skill("http status https://example.com", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("http_check", result["data"]["route"])
        self.assertEqual(200, result["data"]["status_code"])
        self.assertTrue(result["data"]["ok"])

    def test_http_check_404_not_ok(self):
        mock_resp = Mock()
        mock_resp.status = 404
        mock_conn = Mock()
        mock_conn.getresponse.return_value = mock_resp
        with patch("http.client.HTTPSConnection", return_value=mock_conn):
            result = try_skill("http status https://example.com/missing", **_deps())
        self.assertIsNotNone(result)
        self.assertFalse(result["data"]["ok"])

    def test_http_check_connection_error(self):
        with patch("http.client.HTTPSConnection", side_effect=OSError("refused")):
            result = try_skill("http status https://unreachable.invalid", **_deps())
        self.assertIsNotNone(result)
        self.assertFalse(result["data"]["ok"])
        self.assertIn("error", result["data"])

    def test_http_check_aliases(self):
        mock_resp = Mock()
        mock_resp.status = 200
        mock_conn = Mock()
        mock_conn.getresponse.return_value = mock_resp
        for phrase in ["check url https://example.com", "check site https://example.com",
                       "check endpoint https://example.com", "http check https://example.com"]:
            with self.subTest(phrase=phrase):
                with patch("http.client.HTTPSConnection", return_value=mock_conn):
                    result = try_skill(phrase, **_deps())
                self.assertIsNotNone(result)
                self.assertEqual("http_check", result["data"]["route"])

    def test_ssl_check_valid_cert(self):
        import ssl as _ssl_mod
        from datetime import datetime, timezone
        future = datetime(2099, 12, 31, 0, 0, 0, tzinfo=timezone.utc)
        mock_cert = {"notAfter": future.strftime("%b %d %H:%M:%S %Y GMT")}
        mock_sock = Mock()
        mock_sock.__enter__ = Mock(return_value=mock_sock)
        mock_sock.__exit__ = Mock(return_value=False)
        mock_sock.getpeercert.return_value = mock_cert
        with patch("ssl.create_default_context") as mock_ctx, \
             patch("socket.create_connection"):
            mock_ctx.return_value.wrap_socket.return_value = mock_sock
            result = try_skill("ssl example.com", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("ssl_check", result["data"]["route"])
        self.assertEqual("example.com", result["data"]["host"])

    def test_ssl_check_connection_error(self):
        import ssl as _ssl_mod
        with patch("ssl.create_default_context") as mock_ctx, \
             patch("socket.create_connection", side_effect=OSError("refused")):
            result = try_skill("ssl unreachable.invalid", **_deps())
        self.assertIsNotNone(result)
        self.assertFalse(result["data"]["valid"])
        self.assertIn("error", result["data"])

    def test_ssl_check_aliases(self):
        import ssl as _ssl_mod
        from datetime import datetime, timezone
        future = datetime(2099, 12, 31, 0, 0, 0, tzinfo=timezone.utc)
        mock_cert = {"notAfter": future.strftime("%b %d %H:%M:%S %Y GMT")}
        mock_sock = Mock()
        mock_sock.__enter__ = Mock(return_value=mock_sock)
        mock_sock.__exit__ = Mock(return_value=False)
        mock_sock.getpeercert.return_value = mock_cert
        for phrase in ["tls example.com", "cert check example.com", "certificate example.com"]:
            with self.subTest(phrase=phrase):
                with patch("ssl.create_default_context") as mock_ctx, \
                     patch("socket.create_connection"):
                    mock_ctx.return_value.wrap_socket.return_value = mock_sock
                    result = try_skill(phrase, **_deps())
                self.assertIsNotNone(result)
                self.assertEqual("ssl_check", result["data"]["route"])


class SystemControlSkillTests(unittest.TestCase):
    """Write commands require a non-None token in addition to admin role."""

    def _admin(self, **extra):
        return _deps(token="test-tok", **extra)

    def test_reboot_admin_executes(self):
        cmds = []
        result = try_skill("reboot", **self._admin(run_cmd=lambda c, **_k: cmds.append(c) or ""))
        self.assertIsNotNone(result)
        self.assertEqual("system_control", result["data"]["route"])
        self.assertEqual("reboot", result["data"]["action"])
        self.assertTrue(any("-r" in str(c) for c in cmds))

    def test_reboot_aliases(self):
        for phrase in ["restart system", "restart the server", "system reboot", "restart server"]:
            with self.subTest(phrase=phrase):
                result = try_skill(phrase, **self._admin())
                self.assertIsNotNone(result)
                self.assertEqual("reboot", result["data"]["action"])

    def test_shutdown_default_1_min(self):
        result = try_skill("shutdown", **self._admin())
        self.assertIsNotNone(result)
        self.assertEqual("shutdown", result["data"]["action"])
        self.assertEqual(1, result["data"]["delay_min"])

    def test_shutdown_custom_delay(self):
        result = try_skill("shutdown in 5 minutes", **self._admin())
        self.assertIsNotNone(result)
        self.assertEqual(5, result["data"]["delay_min"])

    def test_shutdown_delay_clamped_at_60(self):
        result = try_skill("shutdown in 999 minutes", **self._admin())
        self.assertIsNotNone(result)
        self.assertEqual(60, result["data"]["delay_min"])

    def test_cancel_shutdown(self):
        result = try_skill("cancel shutdown", **self._admin())
        self.assertIsNotNone(result)
        self.assertEqual("cancel", result["data"]["action"])

    def test_abort_reboot(self):
        result = try_skill("abort reboot", **self._admin())
        self.assertIsNotNone(result)
        self.assertEqual("cancel", result["data"]["action"])

    def test_shutdown_blocked_without_token(self):
        result = try_skill("shutdown", **_deps(token=None))
        self.assertIsNotNone(result)
        self.assertEqual("missing_token", result["data"].get("error"))

    def test_shutdown_blocked_for_guest(self):
        result = try_skill(
            "shutdown",
            **_deps(
                role="guest_restricted",
                token="tok",
                permission_check=lambda *_a: False,
            ),
        )
        self.assertIsNotNone(result)
        self.assertNotEqual("system_control", result["data"].get("route"))


class CoinFlipDiceSkillTests(unittest.TestCase):
    def test_coin_flip_returns_heads_or_tails(self):
        result = try_skill("flip a coin", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("coin_flip", result["data"]["route"])
        self.assertIn(result["data"]["result"], ["Heads", "Tails"])

    def test_coin_flip_aliases(self):
        for phrase in ["coin flip", "heads or tails", "toss a coin", "flip coin"]:
            with self.subTest(phrase=phrase):
                result = try_skill(phrase, **_deps())
                self.assertIsNotNone(result)
                self.assertEqual("coin_flip", result["data"]["route"])

    def test_coin_flip_reply_matches_result(self):
        result = try_skill("flip a coin", **_deps())
        self.assertIn(result["data"]["result"], result["reply"])

    def test_dice_roll_default_d6(self):
        result = try_skill("roll a dice", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("dice", result["data"]["route"])
        self.assertEqual(6, result["data"]["sides"])
        self.assertEqual(1, result["data"]["count"])
        self.assertEqual(1, len(result["data"]["rolls"]))
        self.assertIn(result["data"]["rolls"][0], range(1, 7))

    def test_dice_roll_nd_syntax(self):
        result = try_skill("roll 2d6", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual(2, result["data"]["count"])
        self.assertEqual(6, result["data"]["sides"])
        self.assertEqual(2, len(result["data"]["rolls"]))
        self.assertEqual(sum(result["data"]["rolls"]), result["data"]["total"])

    def test_dice_roll_custom_sides(self):
        result = try_skill("roll d20", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual(20, result["data"]["sides"])
        self.assertIn(result["data"]["rolls"][0], range(1, 21))

    def test_dice_roll_count_clamped_at_20(self):
        result = try_skill("roll 99d6", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual(20, result["data"]["count"])

    def test_dice_roll_sides_clamped_at_100(self):
        result = try_skill("roll 1d999", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual(100, result["data"]["sides"])

    def test_dice_roll_reply_contains_total(self):
        result = try_skill("roll 3d6", **_deps())
        total = str(result["data"]["total"])
        self.assertIn(total, result["reply"])


class AsciiRomanSkillTests(unittest.TestCase):
    def test_ascii_char_to_code(self):
        result = try_skill("ascii A", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("ascii", result["data"]["route"])
        self.assertEqual(65, result["data"]["code"])
        self.assertEqual("A", result["data"]["char"])

    def test_ascii_code_to_char(self):
        result = try_skill("ascii 65", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual(65, result["data"]["code"])
        self.assertEqual("A", result["data"]["char"])

    def test_ascii_space_char(self):
        result = try_skill("ascii 32", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual(32, result["data"]["code"])
        self.assertEqual(" ", result["data"]["char"])

    def test_ascii_out_of_range(self):
        result = try_skill("ascii 200", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("out_of_range", result["data"]["error"])

    def test_roman_int_to_roman(self):
        result = try_skill("to roman 14", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("roman", result["data"]["route"])
        self.assertEqual("to_roman", result["data"]["op"])
        self.assertEqual("XIV", result["data"]["roman"])
        self.assertEqual(14, result["data"]["value"])

    def test_roman_to_int(self):
        result = try_skill("roman XIV", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("roman", result["data"]["route"])
        self.assertEqual("to_int", result["data"]["op"])
        self.assertEqual(14, result["data"]["value"])

    def test_roman_out_of_range(self):
        result = try_skill("to roman 4000", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("out_of_range", result["data"]["error"])

    def test_roman_known_values(self):
        cases = [(1, "I"), (4, "IV"), (9, "IX"), (40, "XL"), (1999, "MCMXCIX"), (3999, "MMMCMXCIX")]
        for n, expected in cases:
            with self.subTest(n=n):
                result = try_skill(f"to roman {n}", **_deps())
                self.assertEqual(expected, result["data"]["roman"])

    def test_roman_roundtrip(self):
        for n in [1, 5, 10, 42, 100, 2024]:
            with self.subTest(n=n):
                r1 = try_skill(f"to roman {n}", **_deps())
                roman_str = r1["data"]["roman"]
                r2 = try_skill(f"roman {roman_str}", **_deps())
                self.assertEqual(n, r2["data"]["value"])


class NumericListSkillTests(unittest.TestCase):
    def test_sort_numbers(self):
        result = try_skill("sort 3 1 4 1 5 9", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("numlist", result["data"]["route"])
        self.assertEqual("sort", result["data"]["op"])
        self.assertEqual([1.0, 1.0, 3.0, 4.0, 5.0, 9.0], result["data"]["result"])

    def test_sort_reply_shows_sorted_values(self):
        result = try_skill("sort 5 2 8 1", **_deps())
        self.assertIn("1", result["reply"])
        self.assertIn("8", result["reply"])

    def test_average_integers(self):
        result = try_skill("average 2 4 6 8", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("average", result["data"]["op"])
        self.assertAlmostEqual(5.0, result["data"]["result"])
        self.assertEqual(4, result["data"]["count"])

    def test_average_alias_mean(self):
        result = try_skill("mean 10 20 30", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("average", result["data"]["op"])
        self.assertAlmostEqual(20.0, result["data"]["result"])

    def test_average_alias_avg(self):
        result = try_skill("avg 5 15", **_deps())
        self.assertIsNotNone(result)
        self.assertAlmostEqual(10.0, result["data"]["result"])

    def test_min_of_list(self):
        result = try_skill("min 7 3 9 1 5", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("min", result["data"]["op"])
        self.assertEqual(1.0, result["data"]["result"])

    def test_max_of_list(self):
        result = try_skill("max 7 3 9 1 5", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("max", result["data"]["op"])
        self.assertEqual(9.0, result["data"]["result"])

    def test_sum_of_list(self):
        result = try_skill("sum 1 2 3 4 5", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("sum", result["data"]["op"])
        self.assertEqual(15.0, result["data"]["result"])

    def test_sort_single_number(self):
        result = try_skill("sort 42", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual([42.0], result["data"]["result"])

    def test_average_single_number(self):
        result = try_skill("average 99", **_deps())
        self.assertIsNotNone(result)
        self.assertAlmostEqual(99.0, result["data"]["result"])


class MorseCodeSkillTests(unittest.TestCase):
    def test_morse_encode_hello(self):
        result = try_skill("morse hello", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("morse", result["data"]["route"])
        self.assertEqual("encode", result["data"]["op"])
        self.assertEqual(".... . .-.. .-.. ---", result["data"]["result"])

    def test_morse_encode_sos(self):
        result = try_skill("morse encode SOS", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("... --- ...", result["data"]["result"])

    def test_morse_encode_multi_word(self):
        result = try_skill("morse HI THERE", **_deps())
        self.assertIsNotNone(result)
        self.assertIn("/", result["data"]["result"])

    def test_morse_decode(self):
        result = try_skill("morse decode .... . .-.. .-.. ---", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("decode", result["data"]["op"])
        self.assertEqual("HELLO", result["data"]["result"])

    def test_morse_decode_alias(self):
        result = try_skill("unmorse ... --- ...", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("decode", result["data"]["op"])
        self.assertEqual("SOS", result["data"]["result"])

    def test_morse_encode_numbers(self):
        result = try_skill("morse 42", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("....- ..---", result["data"]["result"])

    def test_morse_unsupported_chars(self):
        result = try_skill("morse encode hello!", **_deps())
        self.assertIsNotNone(result)
        self.assertEqual("unsupported_chars", result["data"]["error"])

    def test_morse_roundtrip(self):
        r1 = try_skill("morse JARVIS", **_deps())
        encoded = r1["data"]["result"]
        r2 = try_skill(f"morse decode {encoded}", **_deps())
        self.assertEqual("JARVIS", r2["data"]["result"])


if __name__ == "__main__":
    unittest.main()
