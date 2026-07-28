from __future__ import annotations

import email as _email_pkg
import imaplib
import smtplib
import ssl
from email.header import decode_header
from email.message import EmailMessage
from email.utils import parsedate_to_datetime


def _decode_field(raw: str | None) -> str:
    if not raw:
        return ""
    parts = decode_header(raw)
    out = []
    for text, charset in parts:
        if isinstance(text, bytes):
            out.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _parse_date_epoch(raw: str | None) -> int:
    if not raw:
        return 0
    try:
        return int(parsedate_to_datetime(raw).timestamp())
    except (TypeError, ValueError):
        return 0


def _extract_text_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition") or ""):
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                except Exception:
                    continue
        return ""
    try:
        return msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="replace")
    except Exception:
        return ""


class ImapSmtpClient:
    """Pure IMAP/SMTP I/O using stdlib `imaplib`/`smtplib`/`email` only — no external
    dependency, provider-agnostic (Gmail app password, iCloud, self-hosted, anything).
    IMAP always connects over implicit TLS (IMAP4_SSL). SMTP uses implicit TLS on port
    465, otherwise STARTTLS — covers the near-universal provider convention.
    All methods swallow network/protocol errors and return a falsy sentinel, matching
    jarvis/home_assistant/client.py's pattern.
    """

    def __init__(
        self,
        imap_host: str,
        imap_port: int,
        imap_username: str,
        imap_password: str,
        smtp_host: str,
        smtp_port: int,
        smtp_username: str,
        smtp_password: str,
    ) -> None:
        self.imap_host = imap_host
        self.imap_port = int(imap_port) if imap_port else 993
        self.imap_username = imap_username
        self.imap_password = imap_password
        self.smtp_host = smtp_host
        self.smtp_port = int(smtp_port) if smtp_port else 587
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password

    def _imap_connect(self) -> imaplib.IMAP4_SSL | None:
        try:
            conn = imaplib.IMAP4_SSL(self.imap_host, self.imap_port, timeout=10)
            conn.login(self.imap_username, self.imap_password)
            return conn
        except (OSError, imaplib.IMAP4.error):
            return None

    def test_connection(self) -> bool:
        imap_ok = False
        conn = self._imap_connect()
        if conn is not None:
            imap_ok = True
            try:
                conn.logout()
            except Exception:
                pass
        server = self._smtp_connect()
        smtp_ok = server is not None
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass
        return imap_ok and smtp_ok

    def fetch_recent_messages(self, folder: str = "INBOX", limit: int = 20) -> list[dict]:
        conn = self._imap_connect()
        if conn is None:
            return []
        try:
            status, _ = conn.select(folder, readonly=True)
            if status != "OK":
                return []
            status, data = conn.search(None, "ALL")
            if status != "OK":
                return []
            uids = data[0].split()[-limit:]
            return [m for m in (self._fetch_headers(conn, uid, folder) for uid in reversed(uids)) if m]
        except (OSError, imaplib.IMAP4.error):
            return []
        finally:
            self._imap_close(conn)

    def _fetch_headers(self, conn, uid: bytes, folder: str) -> dict | None:
        try:
            status, msg_data = conn.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)] FLAGS)")
            if status != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                return None
            header_bytes = msg_data[0][1]
            flags_raw = imaplib.ParseFlags(msg_data[0][0]) if msg_data[0][0] else ()
            msg = _email_pkg.message_from_bytes(header_bytes)
            return {
                "uid": uid.decode(),
                "folder": folder,
                "subject": _decode_field(msg.get("Subject")),
                "sender": _decode_field(msg.get("From")),
                "date": _parse_date_epoch(msg.get("Date")),
                "read": b"\\Seen" in flags_raw,
            }
        except (OSError, imaplib.IMAP4.error, IndexError):
            return None

    def fetch_message_body(self, uid: str, folder: str = "INBOX") -> str | None:
        conn = self._imap_connect()
        if conn is None:
            return None
        try:
            status, _ = conn.select(folder, readonly=True)
            if status != "OK":
                return None
            status, msg_data = conn.fetch(uid.encode(), "(BODY.PEEK[])")
            if status != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                return None
            msg = _email_pkg.message_from_bytes(msg_data[0][1])
            return _extract_text_body(msg)
        except (OSError, imaplib.IMAP4.error, IndexError):
            return None
        finally:
            self._imap_close(conn)

    def mark_read(self, uid: str, folder: str = "INBOX") -> bool:
        conn = self._imap_connect()
        if conn is None:
            return False
        try:
            status, _ = conn.select(folder, readonly=False)
            if status != "OK":
                return False
            status, _ = conn.store(uid.encode(), "+FLAGS", "\\Seen")
            return status == "OK"
        except (OSError, imaplib.IMAP4.error):
            return False
        finally:
            self._imap_close(conn)

    def _imap_close(self, conn) -> None:
        try:
            conn.close()
        except Exception:
            pass
        try:
            conn.logout()
        except Exception:
            pass

    def _smtp_connect(self):
        try:
            if self.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10)
                server.starttls(context=ssl.create_default_context())
            server.login(self.smtp_username, self.smtp_password)
            return server
        except (OSError, smtplib.SMTPException):
            return None

    def send_message(self, to: str, subject: str, body: str, *, in_reply_to: str | None = None) -> bool:
        server = self._smtp_connect()
        if server is None:
            return False
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = self.smtp_username
            msg["To"] = to
            if in_reply_to:
                msg["In-Reply-To"] = in_reply_to
                msg["References"] = in_reply_to
            msg.set_content(body)
            server.send_message(msg)
            return True
        except (OSError, smtplib.SMTPException):
            return False
        finally:
            try:
                server.quit()
            except Exception:
                pass
