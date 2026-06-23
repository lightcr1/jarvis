from __future__ import annotations

import hashlib
import json
import logging
import os
import urllib.error
import urllib.request

_log = logging.getLogger(__name__)


class EmailServiceUnavailable(Exception):
    pass


def _fingerprint(email: str) -> str:
    return hashlib.sha256(email.lower().encode()).hexdigest()[:12]


def is_configured() -> bool:
    return bool(os.getenv("RESEND_API_KEY")) and bool(os.getenv("JARVIS_EMAIL_FROM"))


def send_email(to: str, subject: str, html: str, text: str = "") -> None:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    from_addr = os.getenv("JARVIS_EMAIL_FROM", "").strip()
    if not api_key or not from_addr:
        raise EmailServiceUnavailable("Email service not configured (RESEND_API_KEY / JARVIS_EMAIL_FROM missing)")

    payload = json.dumps({
        "from": from_addr,
        "to": [to],
        "subject": subject,
        "html": html,
        "text": text or subject,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read(256).decode("utf-8", errors="replace")
        _log.error("Email send failed for %s: HTTP %s — %s", _fingerprint(to), exc.code, body[:120])
        raise EmailServiceUnavailable(f"Email delivery failed (HTTP {exc.code})") from exc
    except OSError as exc:
        _log.error("Email send network error for %s: %s", _fingerprint(to), exc)
        raise EmailServiceUnavailable(f"Email delivery network error: {exc}") from exc

    _log.info("Email sent to %s (status %s)", _fingerprint(to), status)


def send_verification_email(to: str, code: str) -> None:
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0c0c0c;color:#d4d4d4;margin:0;padding:40px 20px}}
  .card{{max-width:440px;margin:0 auto;background:#161616;border:1px solid #2a2a2a;border-radius:12px;padding:36px}}
  .logo{{font-size:20px;font-weight:700;color:#e09a1a;margin-bottom:24px}}
  h1{{font-size:18px;color:#f0f0f0;margin:0 0 10px}}
  p{{font-size:14px;color:#a0a0a0;line-height:1.6;margin:0 0 24px}}
  .code{{font-size:32px;font-weight:700;letter-spacing:0.18em;color:#e09a1a;background:#1a1600;border:1px solid #3a2800;border-radius:8px;padding:16px 24px;text-align:center;margin:0 0 24px}}
  .footer{{font-size:11px;color:#555;margin-top:24px}}
</style></head>
<body>
  <div class="card">
    <div class="logo">J.A.R.V.I.S.</div>
    <h1>Verify your email address</h1>
    <p>Enter this code to complete your account creation. It expires in 15 minutes.</p>
    <div class="code">{code}</div>
    <p>If you did not request an account, you can safely ignore this email.</p>
    <div class="footer">J.A.R.V.I.S. — Just A Rather Very Intelligent System</div>
  </div>
</body>
</html>"""

    send_email(
        to=to,
        subject=f"Your JARVIS verification code: {code}",
        html=html,
        text=f"Your JARVIS verification code is: {code}\n\nThis code expires in 15 minutes.",
    )
