from __future__ import annotations

import re

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")


def normalize_mac(mac: str) -> str:
    cleaned = (mac or "").strip()
    if not _MAC_RE.match(cleaned):
        raise ValueError("invalid MAC address format (expected AA:BB:CC:DD:EE:FF)")
    return cleaned.upper().replace("-", ":")


def build_magic_packet(mac: str) -> bytes:
    """Builds a standard Wake-on-LAN magic packet: 6 bytes of 0xFF followed by
    the target MAC address repeated 16 times (102 bytes total).

    This is pure packet construction only — it does NOT send anything over the
    network. Tailscale does not forward LAN broadcast/multicast traffic across
    the tailnet, so a magic packet sent directly from the JARVIS server cannot
    reach a sleeping machine on a different physical LAN. Actually transmitting
    this packet to a relay device (a tiny listener on the target's own LAN that
    rebroadcasts it locally) is out of scope for this module — see
    WorkspaceService.trigger_wake for the stubbed relay-dispatch call site.
    """
    normalized = normalize_mac(mac)
    mac_bytes = bytes.fromhex(normalized.replace(":", ""))
    return b"\xff" * 6 + mac_bytes * 16
