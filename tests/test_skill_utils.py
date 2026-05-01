import unittest

from fastapi import HTTPException

from jarvis.skill_utils import (
    ensure_service_allowed,
    format_bytes,
    is_write_command,
    parse_ping,
    tail_lines,
    valid_service_name,
)


class ValidServiceNameTests(unittest.TestCase):
    def test_simple_service_name_valid(self):
        self.assertTrue(valid_service_name("nginx"))

    def test_service_with_dot_valid(self):
        self.assertTrue(valid_service_name("docker.service"))

    def test_service_with_at_valid(self):
        self.assertTrue(valid_service_name("getty@tty1"))

    def test_service_with_dash_valid(self):
        self.assertTrue(valid_service_name("fail2ban"))

    def test_service_with_underscore_valid(self):
        self.assertTrue(valid_service_name("my_service"))

    def test_service_with_space_invalid(self):
        self.assertFalse(valid_service_name("bad service"))

    def test_service_with_semicolon_invalid(self):
        self.assertFalse(valid_service_name("nginx;rm"))

    def test_empty_service_invalid(self):
        self.assertFalse(valid_service_name(""))

    def test_service_with_slash_invalid(self):
        self.assertFalse(valid_service_name("/etc/passwd"))


class EnsureServiceAllowedTests(unittest.TestCase):
    def test_allowed_service_passes(self):
        ensure_service_allowed("nginx")  # should not raise

    def test_invalid_name_raises_400(self):
        with self.assertRaises(HTTPException) as ctx:
            ensure_service_allowed("bad name!")
        self.assertEqual(400, ctx.exception.status_code)

    def test_not_in_allowlist_raises_403(self):
        with self.assertRaises(HTTPException) as ctx:
            ensure_service_allowed("apache2")
        self.assertEqual(403, ctx.exception.status_code)

    def test_all_known_allowed_services_pass(self):
        for svc in ["jarvis", "nginx", "docker", "ssh", "ufw", "fail2ban"]:
            with self.subTest(svc=svc):
                ensure_service_allowed(svc)


class FormatBytesTests(unittest.TestCase):
    def test_bytes(self):
        self.assertEqual("512.0 B", format_bytes(512))

    def test_kilobytes(self):
        self.assertEqual("1.0 KB", format_bytes(1024))

    def test_megabytes(self):
        self.assertEqual("1.0 MB", format_bytes(1024 ** 2))

    def test_gigabytes(self):
        result = format_bytes(2 * 1024 ** 3)
        self.assertIn("GB", result)
        self.assertIn("2.0", result)

    def test_terabytes(self):
        result = format_bytes(1024 ** 4)
        self.assertIn("TB", result)

    def test_fractional_bytes(self):
        result = format_bytes(1536)
        self.assertIn("KB", result)


class TailLinesTests(unittest.TestCase):
    def test_returns_last_n_lines(self):
        text = "line1\nline2\nline3\nline4\nline5"
        result = tail_lines(text, max_lines=3)
        self.assertEqual("line3\nline4\nline5", result)

    def test_skips_empty_lines(self):
        text = "line1\n\n\nline2\n\nline3"
        result = tail_lines(text, max_lines=5)
        lines = result.splitlines()
        self.assertEqual(3, len(lines))

    def test_empty_input_returns_empty(self):
        self.assertEqual("", tail_lines(""))

    def test_whitespace_only_returns_empty(self):
        self.assertEqual("", tail_lines("   \n   \n   "))

    def test_fewer_lines_than_max(self):
        text = "only one line"
        result = tail_lines(text, max_lines=10)
        self.assertEqual("only one line", result)


class ParsePingTests(unittest.TestCase):
    SAMPLE = (
        "PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.\n"
        "64 bytes from 8.8.8.8: icmp_seq=1 ttl=116 time=12.3 ms\n"
        "--- 8.8.8.8 ping statistics ---\n"
        "4 packets transmitted, 4 received, 0% packet loss, time 3004ms\n"
        "rtt min/avg/max/mdev = 11.5/12.3/13.1/0.6 ms"
    )

    def test_parses_packet_loss(self):
        data = parse_ping(self.SAMPLE)
        self.assertEqual("0%", data["packet_loss"])

    def test_parses_rtt_values(self):
        data = parse_ping(self.SAMPLE)
        self.assertEqual("11.5", data["rtt_min_ms"])
        self.assertEqual("12.3", data["rtt_avg_ms"])
        self.assertEqual("13.1", data["rtt_max_ms"])

    def test_empty_output_returns_empty_dict(self):
        data = parse_ping("")
        self.assertEqual({}, data)

    def test_100_percent_packet_loss(self):
        text = "4 packets transmitted, 0 received, 100% packet loss"
        data = parse_ping(text)
        self.assertEqual("100%", data["packet_loss"])


class IsWriteCommandTests(unittest.TestCase):
    def test_restart_is_write(self):
        self.assertTrue(is_write_command("restart nginx"))

    def test_start_is_write(self):
        self.assertTrue(is_write_command("start docker"))

    def test_stop_is_write(self):
        self.assertTrue(is_write_command("stop ssh"))

    def test_status_is_not_write(self):
        self.assertFalse(is_write_command("status nginx"))

    def test_logs_is_not_write(self):
        self.assertFalse(is_write_command("logs nginx"))

    def test_case_insensitive(self):
        self.assertTrue(is_write_command("RESTART nginx"))


if __name__ == "__main__":
    unittest.main()
