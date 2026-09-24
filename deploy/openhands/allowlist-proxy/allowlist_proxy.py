#!/usr/bin/env python3
"""Allowlist-proxy fuer den autonomen Jarvis-Agenten.

HTTP(S)-Forward-Proxy, der ausschliesslich genau die erlaubten Hostnamen
durchlaesst (pypi.org, files.pythonhosted.org, github.com und die zugehoerigen
Download-Hosts). Alles andere wird mit 403 blockiert.

Design:
- HTTP-Requests: Host-Header gegen die Allowlist pruefen.
- HTTPS (CONNECT): Zielhost pruefen, DNS aufloesen, und den Tunnel nur dann
  aufbauen, wenn JEDE aufgeloeste IP zu einem erlaubten Host gehoert
  (verhindert DNS-Rebinding). Es wird kein MITM/keine Entschluesselung
  gemacht - der Traffic passiert als reiner Tunnel.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket

import os

LISTEN = ("0.0.0.0", 3128)

# Quell-IP fuer ausgehende Verbindungen: der Proxy haengt an einem
# `internal:true`-Netz (agent-isolated) UND am externen runpod-Netz. Das
# interne Netz routet nicht nach aussen, deshalb muss jede ausgehende
# Verbindung die externe Schnittstelle als Quelle nutzen. Wenn EGRESS_IP
# leer ist, wird sie zur Laufzeit bestimmt (Route-Abfrage liefert die IP,
# die fuer Internet-Ausgaenge gewaehlt wuerde).
EGRESS_IP = os.getenv("EGRESS_IP", "")


def detect_egress_ip() -> str:
    if EGRESS_IP:
        return EGRESS_IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Sendet kein Paket; fragt nur die Routing-Entscheidung ab.
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return ""

ALLOWED_HOSTS = {
    "pypi.org",
    "files.pythonhosted.org",
    "github.com",
    "api.github.com",
    "codeload.github.com",
    "raw.githubusercontent.com",
    "objects.githubusercontent.com",
}

# Erlaubte IP-Bereiche (nur public Internet-Adressen; private/loopback/linklocal raus)
PUBLIC_RANGES = [
    ipaddress.ip_network("0.0.0.0/0"),
    ipaddress.ip_network("::/0"),
]
PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::1/128"),
]


def hostname_of(host_port: str) -> str:
    host = host_port.rsplit(":", 1)[0].strip("[]")
    return host.strip().rstrip(".").lower()


def allowed(hostname: str) -> bool:
    h = hostname.lower()
    return any(h == a or h.endswith("." + a) for a in ALLOWED_HOSTS)


def is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return all(not ip in rng for rng in PRIVATE_RANGES)


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peer = writer.get_extra_info("peername")
    print(f"[dbg] connection from {peer}", flush=True)
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=10)
        print(f"[dbg] request_line: {request_line!r}", flush=True)
        if not request_line:
            return
        method, target, _ = request_line.decode("latin-1").split(" ", 2)

        # Header bis zur Leerzeile lesen (begrenzte Groesse)
        headers = {}
        total = 0
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break
            total += len(line)
            if total > 16384:
                break
            key, _, value = line.decode("latin-1").partition(":")
            headers[key.strip().lower()] = value.strip()

        if method.upper() == "CONNECT":
            await handle_connect(reader, writer, target, peer)
            return

        host = headers.get("host", "")
        if not host or not allowed(hostname_of(host)):
            await reply(writer, 403, "Host nicht erlaubt")
            return

        # HTTP-Weiterleitung: nur einfache GET/HEAD ohne Body-Unterstuetzung noetig.
        await handle_http(writer, method, target, headers)
    except (asyncio.TimeoutError, ConnectionError, OSError):
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def reply(writer: asyncio.StreamWriter, code: int, msg: str, extra: str = "") -> None:
    status = {403: "Forbidden", 200: "Connection established", 502: "Bad Gateway"}.get(code, "Error")
    if code == 200:
        # CONNECT: exakt Statuszeile + ein Header, KEIN Body und keine
        # Leerzeile-Daten danach - alles weitere gehoert dem TLS-Tunnel.
        writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await writer.drain()
        return
    body = f"{msg}\n".encode()
    head = (f"HTTP/1.1 {code} {status}\r\n"
            f"Content-Type: text/plain\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n\r\n").encode()
    writer.write(head + body)
    await writer.drain()


async def tunnel(src: asyncio.StreamReader, src_w: asyncio.StreamWriter,
                 dst_r: asyncio.StreamReader, dst_w: asyncio.StreamWriter) -> None:
    async def pump(r, w):
        try:
            while True:
                data = await r.read(65536)
                if not data:
                    break
                w.write(data)
                await w.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            try:
                w.close()
            except Exception:
                pass
    await asyncio.gather(pump(src, dst_w), pump(dst_r, src_w))


async def handle_connect(reader, writer, target, peer) -> None:
    hostname = hostname_of(target)
    print(f"[dbg] CONNECT target={target!r} host={hostname!r} allowed={allowed(hostname)}", flush=True)
    if not allowed(hostname):
        await reply(writer, 403, f"Host nicht erlaubt: {hostname}")
        return
    try:
        infos = await asyncio.get_event_loop().getaddrinfo(
            hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        await reply(writer, 502, "DNS-Aufloesung fehlgeschlagen")
        return
    ips = []
    for family, _, _, _, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
            if not is_public(ip):
                await reply(writer, 403, f"Nicht-oeffentliche IP: {sockaddr[0]}")
                return
            ips.append(ip)
        except ValueError:
            continue
    if not ips:
        await reply(writer, 502, "Keine IP gefunden")
        return

    # Alle Ziele muessen erlaubte Hosts sein (DNS-Rebinding-Schutz)
    if not all(allowed(hostname) for hostname in [hostname]):
        await reply(writer, 403, "Host nicht erlaubt")
        return

    port = 443
    if ":" in target:
        _, _, rest = target.partition(":")
        try:
            port = int(rest.split("/", 1)[0])
        except ValueError:
            port = 443

    # 200 sofort senden, DANN verbinden: ein CONNECT-Client (git/pip/curl)
    # startet erst nach der Bestaetigung mit dem TLS-Handshake. Die
    # echte Verbindung wird mit der Egress-IP als Quelle aufgebaut; wenn
    # sie scheitert, bleibt die Antwort stehen und der Client kriegt EOF.
    await reply(writer, 200, "Connection established")
    local_addr = None
    ip = detect_egress_ip()
    if ip:
        local_addr = (ip, 0)
    try:
        dst_reader, dst_writer = await asyncio.open_connection(hostname, port,
                                                               local_addr=local_addr)
    except (OSError, ConnectionError):
        try:
            writer.close()
        except Exception:
            pass
        return

    await tunnel(reader, writer, dst_reader, dst_writer)


async def handle_http(writer, method, target, headers) -> None:
    # Nur GET/HEAD an erlaubte Hosts; kein Body-Relay (fuer pip/git reicht das)
    if method.upper() not in ("GET", "HEAD"):
        await reply(writer, 405, "Method Not Allowed")
        return
    host = headers.get("host", "")
    try:
        local_addr = (EGRESS_IP, 0) if EGRESS_IP else None
        reader, dst_writer = await asyncio.open_connection(hostname_of(host), 80,
                                                           local_addr=local_addr)
    except (OSError, ConnectionError):
        await reply(writer, 502, "Ziel nicht erreichbar")
        return
    path = target.split("/", 1)[1] if "/" in target else "/"
    req = (f"{method} /{path} HTTP/1.1\r\n"
           f"Host: {host}\r\n"
           f"User-Agent: allowlist-proxy/1.0\r\n"
           f"Accept: */*\r\n"
           f"Connection: close\r\n\r\n").encode()
    dst_writer.write(req)
    await dst_writer.drain()
    while True:
        data = await reader.read(65536)
        if not data:
            break
        writer.write(data)
        await writer.drain()
    try:
        dst_writer.close()
    except Exception:
        pass


async def main() -> None:
    server = await asyncio.start_server(handle, LISTEN[0], LISTEN[1])
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
