import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "token_lifecycle_drill.py"
    spec = importlib.util.spec_from_file_location("token_lifecycle_drill", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TokenLifecycleDrillScriptTests(unittest.TestCase):
    def test_drill_script_captures_revoke_and_expiry_evidence(self) -> None:
        module = _load_script_module()

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            audit_log = root / "audit.log"
            report = root / "report.md"

            first_token = "token-1"
            second_token = "token-2"
            first_fp = module._token_fingerprint(first_token)
            second_fp = module._token_fingerprint(second_token)
            audit_log.write_text(
                "\n".join(
                    [
                        (
                            '{"ts":1,"event":"unlock_issued","token_fingerprint":"%s","expires_in_sec":60}'
                            % first_fp
                        ),
                        '{"ts":2,"event":"unlock_revoked","token_fingerprint":"%s"}' % first_fp,
                        (
                            '{"ts":3,"event":"unlock_revoke_denied","token_fingerprint":"%s","reason":"inactive_token"}'
                            % second_fp
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            responses = iter(
                [
                    module.HttpResult(status=200, body={"token": first_token, "expires_in_sec": 60}),
                    module.HttpResult(
                        status=200,
                        body={"id": "usr-123456abcdef", "username": "ops-drill-admin", "role": "admin", "enabled": True},
                    ),
                    module.HttpResult(status=200, body={"users": [{"id": "usr-123456abcdef", "role": "admin"}]}),
                    module.HttpResult(status=200, body={"ok": True}),
                    module.HttpResult(status=401, body={"detail": "admin token required"}),
                    module.HttpResult(status=200, body={"token": second_token, "expires_in_sec": 60}),
                    module.HttpResult(status=401, body={"detail": "Token expired or invalid"}),
                ]
            )

            def fake_request(self, method, path, *, json_body=None, headers=None):
                return next(responses)

            argv = [
                "token_lifecycle_drill.py",
                "--base-url",
                "https://localhost:8000",
                "--passphrase",
                "test-pass",
                "--audit-log-path",
                str(audit_log),
                "--expiry-wait-seconds",
                "0.01",
                "--report-path",
                str(report),
            ]

            with patch.object(module.HttpClient, "request", new=fake_request), patch.object(module.time, "sleep"), patch(
                "sys.argv", argv
            ):
                rc = module.main()

            self.assertEqual(rc, 0)
            content = report.read_text(encoding="utf-8")
            self.assertIn("PASS `unlock`", content)
            self.assertIn("PASS `bootstrap-admin`", content)
            self.assertIn("PASS `admin-access-active`", content)
            self.assertIn("PASS `admin-access-revoked`", content)
            self.assertIn("PASS `audit-issued`", content)
            self.assertIn("PASS `audit-revoked`", content)
            self.assertIn("PASS `audit-expired`", content)


if __name__ == "__main__":
    unittest.main()
