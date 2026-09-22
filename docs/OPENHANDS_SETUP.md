# OpenHands / Agent Canvas for Jarvis

This repository contains a pinned, local-only Agent Canvas deployment. It gives a coding agent write access only to `/opt/jarvis-openhands/projects`, not to the host filesystem or production data. The UI listens on loopback by default. The image is pinned to the official OpenHands Agent Canvas `1.20.0` amd64 digest.

## Prepared architecture

- Agent Canvas: `deploy/openhands/compose.yml`
- Persistent state: `/opt/jarvis-openhands/state`
- Separate writable Jarvis clone: `/opt/jarvis-openhands/projects/jarvis`
- LLM route: `http://controller:8080/code/v1` on Docker network `runpod_default`
- LLM credential: `MODEL_ACCESS_TOKEN` only; never `CONTROL_TOKEN`
- Repository instructions: `AGENTS.md`
- Policy definition and checker: `config/agent-policy.json`, `scripts/agent/check_policy.py`
- Enforcement: CI, CODEOWNERS, pull requests, and protected `main`

## Prepare without starting

```bash
./scripts/prepare_openhands.sh /home/media/runpod/.env
```

The script creates the restricted directories, clones Jarvis into the agent workspace, writes the ignored Compose `.env`, and validates the Compose model. It does not start OpenHands and does not create a Runpod resource.

## Start and verify

```bash
docker compose --env-file deploy/openhands/.env -f deploy/openhands/compose.yml up -d
./scripts/check_openhands.sh
```

Open `http://127.0.0.1:8000/canvas` on the host or use an SSH tunnel:

```bash
ssh -L 8000:127.0.0.1:8000 <user>@<jarvis-host>
```

In Agent Canvas create an LLM profile with:

- Model: `openai/code`
- Base URL: `http://controller:8080/code/v1`
- API key: the value of `MODEL_ACCESS_TOKEN` from `/home/media/runpod/.env`

The model route will only answer once the Runpod worker is configured and running. Agent Canvas itself can start before that.

## Running Jarvis autonomously (continuous self-improvement)

Once the pod is live and the LLM profile + GitHub token are configured, Jarvis
works proactively per `AGENTS.md` ("Autonomy mode"). Two controls:

- **Master switch:** `config/autonomy.json` in the repo workspace
  (`enabled: true/false`). The Jarvis web UI exposes it under
  Admin → Autonomy (route `/dashboard/autonomy`); the coding agent reads it
  before each round. Missing file = enabled.
- **Work loop:** a scheduled workflow (`.github/workflows/autonomy-trigger.yml`,
  every 6 h) keeps exactly one open issue labeled `autonomy` as the queue.
  Jarvis works it, then closes it when done.
- **Stop autonomous work:** flip the switch in the web UI (or set
  `config/autonomy.json` to `enabled: false`, or close the `autonomy` issue).
  Jarvis then stops starting new rounds; direct owner requests always work.
- **Owner priority:** when you chat/task Jarvis directly, he pauses autonomous
  work (safe checkpoint), serves you, and resumes afterwards — he never
  aborts half-done work.
- **Efficiency rule:** changes are bundled into a few PRs per session, not
  one commit per tiny step. Nothing to do -> the loop stays idle instead of
  producing churn.

## Troubleshooting: Onboarding dialog stuck (Telemetry / profile setup)

If the first-run dialog ("usage data" / profile setup) cannot be dismissed,
the most common cause is that the bind-mounted state directory is not
writable by the container user (uid 10001). Check the container logs for:

    PermissionError: ... '/home/openhands/.openhands/provider-connections'

Fix (on the host, as the VM user):

    chmod -R a+rwX /home/media/jarvis-openhands/state /home/media/jarvis-openhands/projects
    docker restart jarvis-openhands

Then reload the canvas page; the dialog should complete. The prepare script
already applies these permissions; run it again after restoring a backup.

## Security model

Agent work must happen on `agent/*` branches and enter `main` through a pull request. Critical paths are owned by `@lightcr1`. The agent is forbidden from changing Runpod resources, spending money, deploying production, handling secrets, or bypassing repository controls. OpenHands remains powerful software: review its proposed commands and never broaden the `/projects` mount to `/`, `/home`, Docker socket, production data, or secret directories.
