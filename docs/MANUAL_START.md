# What you must do manually

Everything that can be safely prepared in code is included. The remaining steps require your credential, billing decision, or a browser confirmation.

## 1. Replace the invalid Runpod API key

Open `/home/media/runpod/.env`, replace `RUNPOD_API_KEY`, then run:

```bash
cd /home/media/runpod
docker compose up -d --build controller
curl -k -H "Authorization: Bearer $CONTROL_TOKEN" https://127.0.0.1:8443/api/runpod/preflight
```

A successful preflight must no longer report HTTP 401. Do not enable billable actions yet.

## 2. Publish and select the GPU runtime image

Publish `pod-runtime/Dockerfile` to your container registry for `linux/amd64`. Put the immutable image reference including `@sha256:...` into `RUNPOD_RUNTIME_IMAGE` in `/home/media/runpod/.env`.

## 3. Start the billable Runpod worker when you accept the cost

Choose the GPU type and limits in `/home/media/runpod/.env`. Set `RUNPOD_ALLOW_BILLABLE_ACTIONS=true` only immediately before you intentionally create/start a worker. Follow `/home/media/runpod/docs/DEIN_START.md` for the exact preflight and start commands. Return the switch to `false` when finished.

## 4. Start OpenHands

From a clone of this Jarvis repository on the same Docker host as the Runpod controller:

```bash
./scripts/prepare_openhands.sh /home/media/runpod/.env
docker compose --env-file deploy/openhands/.env -f deploy/openhands/compose.yml up -d
./scripts/check_openhands.sh
```

Open `http://127.0.0.1:8000/canvas` locally or through the SSH tunnel documented in `docs/OPENHANDS_SETUP.md`.

## 5. Enter two secrets in the OpenHands browser UI

Create the LLM profile from `docs/OPENHANDS_SETUP.md`. Paste `MODEL_ACCESS_TOKEN` as the LLM API key. Connect GitHub using a fine-grained token or GitHub App that is limited to `lightcr1/jarvis` with repository contents and pull-request access. Do not grant administration, billing, secrets, or organization-wide access.

After that, assign tasks to the `/projects/jarvis` workspace. Keep protected changes for your review; ordinary changes may be merged only after all required CI checks pass.
