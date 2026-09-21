# Agent operating rules

These rules apply to OpenHands and every other coding agent working in this repository.

## Default workflow

1. Work on a dedicated branch named `agent/<short-task-name>`.
2. Read `config/agent-policy.json` before changing files.
3. Keep changes limited to the requested task.
4. Run `python3 scripts/agent/check_policy.py --staged` before committing.
5. Run the relevant backend and frontend tests.
6. Open a pull request. Never push directly to `main`.

## Non-negotiable boundaries

- Never commit secrets, tokens, private keys, `.env` files, production data, or credentials.
- Never create, start, stop, resize, or delete Runpod resources.
- Never enable a billable service, purchase, subscription, or paid API call.
- Never deploy to production, alter firewalls/DNS, or run destructive commands.
- Never bypass tests, branch protection, CODEOWNERS, or required human approval.
- Do not mount the Docker socket or host root into an agent workspace.

## Human approval

Changes to authentication, authorization, billing, deployment, infrastructure, GitHub workflows,
agent policy, secrets handling, or destructive operations require owner review. The protected paths
are listed in `config/agent-policy.json` and `.github/CODEOWNERS`.

## Verification

Backend: `python -m pytest -q`

Frontend: `cd frontend && npm ci && npm run lint && npm run test:run && npm run build`
