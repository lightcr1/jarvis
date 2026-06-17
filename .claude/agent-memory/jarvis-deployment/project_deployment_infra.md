---
name: project-deployment-infra
description: Deployment infrastructure decisions — service file, install/update/rollback scripts, env file layout, paths
metadata:
  type: project
---

JARVIS V1 deployment infrastructure lives under three canonical locations:
- `deploy/jarvis.service` — systemd unit
- `scripts/install.sh`, `scripts/update.sh`, `scripts/rollback.sh` — authoritative ops scripts
- `config/dev.env.example`, `config/prod.env.example` — env templates

## Deploy root separation

Source repo: `/home/jarvis/jarvis/` (git repo, where scripts live)
Production deploy root: `/opt/jarvis/` (what the systemd service runs from)

Scripts use `rsync -a --delete` to sync from source to deploy root, excluding `.venv`, `.git`, `__pycache__`, `*.pyc`, `frontend/node_modules`, `frontend/dist`.

**Why:** Keeps git state out of the running service directory. `/opt/jarvis` is conventional for third-party software on Linux and fits `ProtectSystem=strict` cleaner than running from `/home`.

## Systemd unit key decisions

- `WorkingDirectory=/opt/jarvis`
- `ExecStart=/opt/jarvis/.venv/bin/uvicorn jarvisappv4:app --host 0.0.0.0 --port 8000 --workers 1`
- `User=jarvis` (system user, no login shell)
- `EnvironmentFile=/etc/jarvis/jarvis.env` (no leading `-`) — service intentionally fails to start if file is missing; forces operator to configure secrets before first start
- `Restart=on-failure` (not `always`) — avoids restart loops on deliberate `systemctl stop`
- `StartLimitBurst=3` over 60s window
- Hardening: `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ProtectHome=read-only`
- `ReadWritePaths=/var/lib/jarvis /etc/jarvis` — both dirs writable; `/etc/jarvis` needed for env file reads at runtime

## Rollback SHA file

`/var/lib/jarvis/last_deploy_sha` — written by `update.sh` before every pull, so it always points to the last known-good SHA.

## rollback.sh default behaviour

No args → `previous` (reads `last_deploy_sha`). This changed from the prior model where no-args meant HEAD~1. Explicit `HEAD~1` and `<sha>` still work.

## update.sh auto-rollback

If the service fails the 5s health check after restart, `update.sh` calls `rollback.sh` automatically, restores `last_deploy_sha`, and exits 1.

## rsync dependency

`update.sh` and `rollback.sh` require `rsync`. Pre-flight check added. If absent: `apt install rsync`.

`.venv` is excluded from syncs so the virtualenv in `/opt/jarvis/.venv` is never blown away. Created once by `install.sh`, updated in-place by pip.

## env file

Production env file: `/etc/jarvis/jarvis.env`
Permissions: `root:jarvis 640` — jarvis group can read, no world access.
`install.sh` copies `config/prod.env.example` on first install only; never overwrites an existing file.

## Operator steps after install.sh

1. Edit `/etc/jarvis/jarvis.env` — set `JARVIS_PASSPHRASE`, `OPENAI_API_KEY` or `GEMINI_API_KEY`, `JARVIS_DEFAULT_ADMIN_PASSWORD`
2. `sudo systemctl start jarvis`
3. `curl http://localhost:8000/health`
(`systemctl daemon-reload` is run automatically by `install.sh`)

## V1 release criteria addressed

- "Deployment from clean environment is reproducible" — covered by `install.sh`
- "Rollback validated with evidence" — covered by `rollback.sh` + auto-rollback in `update.sh`
- "Environment separation (dev/test/prod)" — covered by `config/dev.env.example` and `config/prod.env.example`

**How to apply:** Use `deploy/` files as canonical. The old `systemd/` directory is a prior model and should not be confused with these.

## Nginx reverse proxy + HTTPS (added V37)

- Nginx config: `deploy/nginx/jarvis.conf`
- Setup script (LAN / mkcert): `scripts/setup-https.sh`
- Setup script (public domain / Let's Encrypt): `scripts/setup-https-letsencrypt.sh`

Key nginx decisions:
- 80 → 443 redirect lives in its own server block (not a rewrite in the SSL block) — compatible with nginx 1.18 and 1.24
- `/ws/` gets a dedicated location block with `Upgrade` + `Connection: upgrade` headers and 3600s read/send timeouts for long-lived WebSocket connections
- `location /` has `proxy_buffering off` to support SSE streaming from `/chat/stream`
- `client_max_body_size 50M` — audio uploads for STT
- LAN cert paths: `/etc/jarvis/ssl/cert.pem` and `key.pem` (mkcert, v1.4.4 linux-amd64 binary)
- Let's Encrypt cert paths: `/etc/letsencrypt/live/<domain>/fullchain.pem` (patched into conf by setup-https-letsencrypt.sh via sed)
- server_name covers: `jarvissrv01 jarvissrv01.local localhost` — add public FQDN when switching to Let's Encrypt

`deploy.sh` reloads nginx only when: (1) nginx is installed AND (2) `/etc/nginx/sites-enabled/jarvis` symlink exists. Safe to run on machines without nginx.

Operator steps after `scripts/setup-https.sh`:
1. Visit `https://jarvissrv01` in browser
2. Import mkcert CA cert on each client device (`mkcert -CAROOT` shows path) to clear browser warnings
