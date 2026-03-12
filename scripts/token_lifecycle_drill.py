#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


@dataclass
class HttpResult:
    status: int
    body: dict[str, Any] | str


class HttpClient:
    def __init__(self, base_url: str, *, timeout: float, insecure: bool) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.context = ssl._create_unverified_context() if insecure else None

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResult:
        payload = None
        request_headers = {"Accept": "application/json", **(headers or {})}
        if json_body is not None:
            payload = json.dumps(json_body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        req = urlrequest.Request(
            f"{self.base_url}{path}",
            data=payload,
            headers=request_headers,
            method=method,
        )
        try:
            with urlrequest.urlopen(req, timeout=self.timeout, context=self.context) as resp:
                raw = resp.read().decode("utf-8")
                return HttpResult(status=resp.status, body=_decode_body(raw))
        except urlerror.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            return HttpResult(status=exc.code, body=_decode_body(raw))


def _decode_body(raw: str) -> dict[str, Any] | str:
    raw = raw.strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(value, dict):
        return value
    return {"value": value}


def _read_audit_events(audit_log_path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not audit_log_path.exists():
        return events
    for line in audit_log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _find_audit_event(
    events: list[dict[str, Any]],
    event_name: str,
    *,
    token_fingerprint: str | None = None,
    reason: str | None = None,
) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.get("event") != event_name:
            continue
        if token_fingerprint is not None and event.get("token_fingerprint") != token_fingerprint:
            continue
        if reason is not None and event.get("reason") != reason:
            continue
        return event
    return None


def _record_step(
    steps: list[dict[str, Any]],
    name: str,
    passed: bool,
    detail: str,
    *,
    status: int | None = None,
    body: dict[str, Any] | str | None = None,
) -> None:
    item: dict[str, Any] = {
        "name": name,
        "passed": passed,
        "detail": detail,
    }
    if status is not None:
        item["status"] = status
    if body is not None:
        item["body"] = body
    steps.append(item)


def _fail(steps: list[dict[str, Any]], name: str, detail: str, *, status: int | None = None, body: Any = None) -> int:
    _record_step(steps, name, False, detail, status=status, body=body)
    return 1


def _write_report(report_path: Path | None, report_text: str) -> None:
    if report_path is None:
        print(report_text)
        return
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text, encoding="utf-8")
    print(f"Report written: {report_path}")


def _render_report(
    *,
    base_url: str,
    audit_log_path: Path,
    expiry_wait_seconds: float,
    mode: str,
    admin_user_id: str | None,
    steps: list[dict[str, Any]],
) -> str:
    lines = [
        "# Token Lifecycle Drill Report",
        "",
        f"- Timestamp: {_utc_now()}",
        f"- Base URL: `{base_url}`",
        f"- Audit log: `{audit_log_path}`",
        f"- Admin identity mode: `{mode}`",
        f"- Admin user id: `{admin_user_id or 'bootstrap-created'}`",
        f"- Expiry wait seconds: `{expiry_wait_seconds}`",
        "",
        "## Results",
        "",
    ]
    for step in steps:
        marker = "PASS" if step["passed"] else "FAIL"
        status = f" (HTTP {step['status']})" if "status" in step else ""
        lines.append(f"- {marker} `{step['name']}`{status}: {step['detail']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run unlock/revoke/expiry drill against a live Jarvis instance.")
    parser.add_argument("--base-url", default="https://localhost:8000", help="Jarvis base URL.")
    parser.add_argument("--passphrase", required=True, help="Unlock passphrase.")
    parser.add_argument(
        "--audit-log-path",
        default="/var/lib/jarvis/audit.log",
        help="Path to the JSONL audit log for evidence verification.",
    )
    parser.add_argument(
        "--admin-user-id",
        help="Existing enabled admin user id used for the authenticated admin endpoint check.",
    )
    parser.add_argument(
        "--bootstrap-admin-username",
        default="ops-drill-admin",
        help="Username to create via bootstrap flow when --admin-user-id is not provided.",
    )
    parser.add_argument(
        "--expiry-wait-seconds",
        type=float,
        default=0.0,
        help="Wait duration before the expiry validation step. Set above the configured token TTL to verify expiry.",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="Per-request timeout in seconds.")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS certificate verification.")
    parser.add_argument("--report-path", help="Optional Markdown output path.")
    args = parser.parse_args()

    client = HttpClient(args.base_url, timeout=args.timeout, insecure=args.insecure)
    audit_log_path = Path(args.audit_log_path)
    steps: list[dict[str, Any]] = []

    unlock = client.request("POST", "/unlock", json_body={"passphrase": args.passphrase})
    if unlock.status != 200 or not isinstance(unlock.body, dict) or "token" not in unlock.body:
        return _fail(steps, "unlock", "Failed to obtain unlock token", status=unlock.status, body=unlock.body)

    first_token = str(unlock.body["token"])
    first_fingerprint = _token_fingerprint(first_token)
    _record_step(steps, "unlock", True, "Unlock token issued", status=unlock.status, body=unlock.body)

    created_admin_user_id: str | None = None
    if args.admin_user_id:
        admin_user_id = args.admin_user_id
        identity_mode = "existing-admin"
    else:
        identity_mode = "bootstrap-admin"
        create_admin = client.request(
            "POST",
            "/admin/users",
            json_body={"username": args.bootstrap_admin_username, "role": "admin", "enabled": True},
            headers={"Authorization": f"Bearer {first_token}", "X-Jarvis-Role": "admin"},
        )
        if create_admin.status != 200 or not isinstance(create_admin.body, dict) or "id" not in create_admin.body:
            return _fail(
                steps,
                "bootstrap-admin",
                "Failed to create bootstrap admin user",
                status=create_admin.status,
                body=create_admin.body,
            )
        created_admin_user_id = str(create_admin.body["id"])
        admin_user_id = created_admin_user_id
        _record_step(
            steps,
            "bootstrap-admin",
            True,
            f"Bootstrap admin created as {args.bootstrap_admin_username}",
            status=create_admin.status,
            body=create_admin.body,
        )

    admin_headers = {
        "Authorization": f"Bearer {first_token}",
        "X-Jarvis-Role": "admin",
        "X-Jarvis-User-Id": admin_user_id,
    }
    active_access = client.request("GET", "/admin/users", headers=admin_headers)
    if active_access.status != 200:
        return _fail(
            steps,
            "admin-access-active",
            "Active token failed against admin endpoint",
            status=active_access.status,
            body=active_access.body,
        )
    _record_step(
        steps,
        "admin-access-active",
        True,
        "Active token accepted by admin endpoint",
        status=active_access.status,
        body=active_access.body,
    )

    revoke = client.request("POST", "/unlock/revoke", headers={"Authorization": f"Bearer {first_token}"})
    if revoke.status != 200:
        return _fail(steps, "revoke", "Failed to revoke active token", status=revoke.status, body=revoke.body)
    _record_step(steps, "revoke", True, "Active token revoked", status=revoke.status, body=revoke.body)

    revoked_access = client.request("GET", "/admin/users", headers=admin_headers)
    if revoked_access.status != 401:
        return _fail(
            steps,
            "admin-access-revoked",
            "Revoked token unexpectedly retained admin access",
            status=revoked_access.status,
            body=revoked_access.body,
        )
    _record_step(
        steps,
        "admin-access-revoked",
        True,
        "Revoked token denied by admin endpoint",
        status=revoked_access.status,
        body=revoked_access.body,
    )

    audit_events = _read_audit_events(audit_log_path)
    if _find_audit_event(audit_events, "unlock_issued", token_fingerprint=first_fingerprint) is None:
        return _fail(steps, "audit-issued", "Missing unlock_issued audit event for first token")
    _record_step(steps, "audit-issued", True, "unlock_issued audit event located")

    if _find_audit_event(audit_events, "unlock_revoked", token_fingerprint=first_fingerprint) is None:
        return _fail(steps, "audit-revoked", "Missing unlock_revoked audit event for first token")
    _record_step(steps, "audit-revoked", True, "unlock_revoked audit event located")

    if args.expiry_wait_seconds > 0:
        expiry_unlock = client.request("POST", "/unlock", json_body={"passphrase": args.passphrase})
        if expiry_unlock.status != 200 or not isinstance(expiry_unlock.body, dict) or "token" not in expiry_unlock.body:
            return _fail(
                steps,
                "unlock-expiry",
                "Failed to obtain token for expiry validation",
                status=expiry_unlock.status,
                body=expiry_unlock.body,
            )
        expiry_token = str(expiry_unlock.body["token"])
        expiry_fingerprint = _token_fingerprint(expiry_token)
        _record_step(
            steps,
            "unlock-expiry",
            True,
            "Second token issued for expiry validation",
            status=expiry_unlock.status,
            body=expiry_unlock.body,
        )

        time.sleep(args.expiry_wait_seconds)

        expired_revoke = client.request("POST", "/unlock/revoke", headers={"Authorization": f"Bearer {expiry_token}"})
        if expired_revoke.status != 401:
            return _fail(
                steps,
                "revoke-expired",
                "Expired token was not rejected on revoke path",
                status=expired_revoke.status,
                body=expired_revoke.body,
            )
        _record_step(
            steps,
            "revoke-expired",
            True,
            "Expired token rejected on revoke path",
            status=expired_revoke.status,
            body=expired_revoke.body,
        )

        audit_events = _read_audit_events(audit_log_path)
        if _find_audit_event(
            audit_events,
            "unlock_revoke_denied",
            token_fingerprint=expiry_fingerprint,
            reason="inactive_token",
        ) is None:
            return _fail(
                steps,
                "audit-expired",
                "Missing inactive-token revoke denial audit event for expired token",
            )
        _record_step(
            steps,
            "audit-expired",
            True,
            "unlock_revoke_denied inactive-token audit event located",
        )

    report_text = _render_report(
        base_url=args.base_url,
        audit_log_path=audit_log_path,
        expiry_wait_seconds=args.expiry_wait_seconds,
        mode=identity_mode,
        admin_user_id=created_admin_user_id or args.admin_user_id,
        steps=steps,
    )
    _write_report(Path(args.report_path) if args.report_path else None, report_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
