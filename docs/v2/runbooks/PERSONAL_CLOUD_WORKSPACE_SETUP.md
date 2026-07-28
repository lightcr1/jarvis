# Personal Cloud Workspace — Setup Runbook

Code is done and deployed (branch `v2-phase-0-4`). This document is everything left to
do by hand: connect the JARVIS server to your two target PCs over Tailscale, stand up
Guacamole, and wire the two together. Nothing here can be automated from this session —
Tailscale login is an interactive browser flow, and the target PCs aren't reachable from
here at all.

Do the steps in order. Each step says which machine to run it on.

---

## 1. Tailscale — JARVIS server (`jarvissrv01`)

```
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

The second command prints a URL — open it in a browser, log into (or create) a Tailscale
account. Once approved, confirm it's connected:

```
tailscale status
```

Note the server's Tailscale IP (`100.x.y.z`) — you probably won't need it directly, but
useful for troubleshooting.

## 2. Tailscale — Windows target PC

1. Download and install from https://tailscale.com/download/windows
2. Sign in with **the same Tailscale account** you used for the server.
3. Once connected, open a terminal and run `ipconfig` or check the Tailscale tray icon —
   note the machine's Tailscale hostname (shown in the Tailscale admin console at
   https://login.tailscale.com/admin/machines, easier than hunting for the IP) — e.g.
   `desktop-abc123`.
4. **Enable Remote Desktop**: Settings → System → Remote Desktop → toggle on. Note the
   Windows username/password you'll connect with (a real Windows account, not a PIN).

## 3. Tailscale — Linux target PC

1. Install: `curl -fsSL https://tailscale.com/install.sh | sh` then `sudo tailscale up`,
   same account as above.
2. Note its Tailscale hostname the same way (admin console or `tailscale status`).
3. **Enable a remote desktop server** — pick one:
   - **VNC** (simpler): install a VNC server, e.g. `x11vnc` or TigerVNC, and make sure
     it's running with a password set.
   - **RDP via xrdp** (if you'd rather use RDP for both targets):
     `sudo apt install xrdp` (Debian/Ubuntu), `sudo systemctl enable --now xrdp`.

## 4. Guacamole — JARVIS server

The compose file is already at `deploy/guacamole/docker-compose.yml` on this server —
`docker` and `docker-compose` are already installed here, confirmed.

```
cd /home/jarvis/jarvis/deploy/guacamole
mkdir -p init extensions
```

**Generate the shared secret** (you'll use this exact value twice — once here, once on
the JARVIS side in step 5):

```
python3 -c "import secrets; print(secrets.token_hex(16))"
```

**Create `.env`** in that same directory (this file is gitignored-worthy — don't commit
it, it's not tracked):

```
GUACAMOLE_VERSION=1.5.5
GUACAMOLE_DB_PASSWORD=<pick a random password>
GUACAMOLE_JSON_SECRET=<the hex string you just generated>
```

**Generate the Postgres schema** (one-time, before first start):

```
docker run --rm guacamole/guacamole:1.5.5 /opt/guacamole/bin/initdb.sh --postgresql > init/initdb.sql
```

**Get the `guacamole-auth-json` extension jar** — check if it's already bundled first:

```
docker run --rm guacamole/guacamole:1.5.5 ls /opt/guacamole/extensions/ 2>/dev/null
```

If `guacamole-auth-json` isn't listed, download it from
https://guacamole.apache.org/releases/ (find `1.5.5` → extensions →
`guacamole-auth-json-1.5.5.tar.gz`), extract, and copy the `.jar` into
`deploy/guacamole/extensions/`.

**Bring it up:**

```
docker-compose up -d
```

Check it's healthy:

```
docker-compose ps
curl -sI http://localhost:8081/guacamole/ | head -1
```

Should return `HTTP/1.1 200 OK` (or a redirect, both fine).

## 5. Wire JARVIS to Guacamole

Edit `/etc/jarvis/jarvis.env` (needs `sudo`) and add:

```
JARVIS_WORKSPACE_GUACAMOLE_URL=http://localhost:8081/guacamole
JARVIS_WORKSPACE_JSON_SECRET=<the exact same hex string from step 4>
```

Then restart JARVIS to pick it up:

```
sudo systemctl restart jarvis.service
```

## 6. Add your targets in the JARVIS UI

Open JARVIS → **Workspace** (new nav rail entry) → Add Target, once per PC:

| Field | Windows target | Linux target |
|---|---|---|
| OS type | windows | linux |
| Protocol | rdp | vnc (or rdp, if you set up xrdp) |
| Tailscale host | the hostname/IP from step 2.3 | the hostname/IP from step 3.2 |
| Port | 3389 | 5900 (vnc) or 3389 (xrdp) |
| Credentials | the Windows account from step 2.4 | your VNC password / Linux account |

Hit **Connect** — it opens a new tab straight into the remote desktop, no separate
Guacamole login.

---

## Known limitation: Wake-on-LAN

Since both target PCs are on a different network than the JARVIS server, a plain WoL
magic packet from JARVIS can't reach them — Tailscale doesn't forward LAN broadcast
traffic across the tailnet. The **Wake** button in the Workspace screen stays disabled
until a target has a `wol_relay_host` configured — an always-on device on the *same
physical LAN* as that target, capable of sending the local broadcast on JARVIS's behalf.
Not built in this pass (the relay side needs its own tiny listener service, not scoped
yet). Practically: just make sure the target PCs don't go to sleep, or wake them
manually before connecting, until this gets picked up later.

## Before you rely on this for real use

`jarvis/workspace/guac_auth.py`'s token format was implemented from Apache's
documentation and reference script, with one detail (PKCS7 padding) inferred rather than
explicitly confirmed in the docs. It has its own round-trip self-test, but that only
proves the encode/decode logic agrees with itself — not that a real Guacamole server
accepts it. **The first real Connect attempt in step 6 is the actual verification.** If
it fails, check the `guacamole` container's logs (`docker-compose logs guacamole`) —
report back what you see and it's a quick fix either way.
