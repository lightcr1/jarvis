---
name: autonomous-infra-v2-phase4
description: PolicyStore/PolicyEngine self-healing + PlaybookStore/PlaybookExecutor maintenance playbooks (V2 Roadmap Phase 4)
metadata:
  type: project
---

Built 2026-07-27, same session as [[proactive-intelligence-v2]] and [[alert-engine-architecture]] — this phase builds directly on the Phase 0 pluggable signal-source refactor.

## Architectural call: sibling `PolicyEngine`, not a merged `AlertEngine`

The coordinator explicitly left this as an open decision. Chose a **separate `jarvis/policy_engine.py`** rather than extending `AlertEngine`, for three reasons:

1. **Different execution model.** AlertEngine's job stops at "notify" (broadcast + audit). PolicyEngine's job is "notify, then attempt a WRITE action, then verify, then escalate on repeat failure" — a materially different state machine (incident/retry-window tracking, dry-run branching, permission/emergency-stop gates before mutation) that would bloat `AlertEngine._evaluate_rule`/`_loop` past the ~50-line function guideline and mix concerns the existing 48 alert-engine tests don't expect.
2. **Different rule shape and store.** `AlertRule` (flat: metric/condition/threshold/message_template) vs `PolicyRule` (nested: `condition: {...}`, `action: {type, params}`) — coordinator explicitly required a **separate** `PolicyStore`, not a migration of `AlertRulesStore`.
3. **Reuse without merging is cheap.** Everything actually worth sharing — the signal-source registry and `_evaluate_condition` — was already extracted to module-level functions in `jarvis/alert_engine.py` during the Phase 0 refactor (`_default_signal_sources`, `_evaluate_condition`, both still leading-underscore but freely importable across modules — no public rename needed since call sites are internal, not a public API boundary). `PolicyEngine.__init__` just calls `_default_signal_sources(ha_store)` directly and layers a `service_status` source on top via its own `register_source()` (mirrors `AlertEngine.register_source()` exactly, same pluggable-source contract, independently instantiated).

**Known limitation documented in code:** AlertEngine's `ha_entity` source lambda expects `rule["ha_entity_id"]` at the top level (AlertRule shape). A `PolicyRule` dict doesn't have that key, so if a policy's `condition.metric == "ha_entity"`, the reused source silently returns `None` (treated as "signal unavailable," never crashes) — not a real feature yet, just harmless degradation. HA-entity-conditioned policies aren't a required domain for Phase 4 (only `service_status` is); add a custom `register_source()` call if that's needed later.

## Self-healing authorization design (the trickiest part)

The write-skill machinery (`assistant_domain.py`'s `restart <svc>` skill, via `block_write_if_unauthorized`) **requires a live, active bearer token** (`if not token: return {"error": "missing_token"}`) — by design, since it's meant for interactive chat sessions. A background policy loop has no such token, and minting one via `jarvisappv4._issue_token()` for every autonomous restart would compete with real user/guest tokens for the shared `JARVIS_MAX_ACTIVE_TOKENS` capacity (`enforce_token_capacity` evicts oldest tokens over the cap) — an undesirable side effect purely to satisfy a check that isn't really about *this* actor's identity.

Resolution: `PolicyEngine` does **not** call `try_skill()`. It calls the same underlying primitives directly:
- `jarvis.infra_actions.restart_service()` — wraps the exact same `ensure_service_allowed()` + `run_cmd(["...", "systemctl", "restart", ...])` calls the chat skill uses (new shared module `jarvis/infra_actions.py`, imported by both `policy_engine.py` and `playbook_executor.py` so the restart mechanics exist in exactly one place).
- `emergency_stop_enabled()` — the real env-var-backed function from `jarvis.jarvis_engine`, injected as a constructor dependency and checked **before every live restart attempt** (dry-run policies skip this gate entirely since nothing executes).
- `write_permission_check: Callable[[], bool]` — injected as `lambda: role_has_permission("admin", "actions.write.execute")` in `jarvisappv4.py`, reusing `role_has_permission` (the exact same predicate `block_write_if_unauthorized`'s `permission_check` lambda calls) rather than a hardcoded `True`. If `ROLE_PERMISSIONS["admin"]` ever loses `actions.write.execute`, this blocks automatically too.

Net effect: emergency-stop and the write-permission model are enforced with the *same source-of-truth functions* the interactive path uses, without needing a token at all — token-possession was never actually checked for anything in `block_write_if_unauthorized`'s `permission_check` lambda (`_active_token` param is prefixed-unused there), only its *presence* was gated, so this isn't a weaker check, just a differently-shaped one appropriate for a non-interactive actor.

## Self-healing flapping/escalation logic

`PolicyEngine` tracks **incidents** (not raw restart success/failure) per policy in `_incident_times: dict[policy_id, list[float]]`, pruned to `retry_window_sec` (default 900s). Every time a policy's condition fires and cooldown/duration gates pass, that's one incident, regardless of whether the restart itself reports "active" afterward — because a service that keeps going down and getting restarted successfully each time is *still* the signal that something needs human attention ("goes down again within a retry window" from the spec), not just "restart command exit code failed." Escalates (`type: "policy_escalation"`) once `len(recent_incidents) >= escalate_after_incidents` (default 2). Emergency-stop-blocked and permission-denied restarts escalate **immediately** (no incident-counting wait) since JARVIS categorically cannot self-heal in that state.

`last_fired_at` (cooldown) is **persisted** via `PolicyStore.mark_fired()`, unlike `AlertEngine`'s in-memory-only `_last_fired_at` — deliberate: a policy performs a WRITE action, so "don't restart-storm right after a restart" should survive a process restart, unlike "don't re-notify about the same alert" which is fine to reset.

## Playbooks

`jarvis/playbook_store.py` (`PlaybookStore`) — one JSON file, two collections: `playbooks` (definitions: ordered `steps`, each `{step_id, description, action: {type, params}, requires_confirmation}`) and `runs` (checkpointed execution records: per-step `status` — `pending/running/succeeded/failed/skipped/would_execute` — persisted after every step transition, so `PlaybookStore.get_run(run_id)` from a **freshly constructed** store instance always reflects the true progress, tested explicitly by simulating a process restart mid-playbook).

`jarvis/playbook_executor.py` (`PlaybookExecutor.run()`/`.resume()`) — sequential step execution:
- **dry_run** (playbook-level default, or per-call override): marks each step `would_execute` without touching `action_dispatch` at all.
- **requires_confirmation**: pauses the run (`status: "awaiting_confirmation"`), broadcasts `type: "playbook_awaiting_confirmation"`, returns control. `resume(run_id, confirm=True)` continues past *only* the step that was paused (tracked via a one-shot `skip_confirmation_for_first` flag through `_advance`/`_run_step` — subsequent gated steps in the same playbook still pause normally on a later `resume` call).
- **step failure**: halts the run (`status: "failed"`), persists the error, broadcasts `type: "playbook_result"`. `resume(run_id)` on a `"failed"` run retries from that same step (not just confirmation-pauses) — this is the "resume-after-failure" behavior explicitly required by the coordinator, distinct from the confirmation-resume path.
- **emergency stop**: checked before every live (non-dry-run) step; if active, halts the run with `error: "emergency_stop"` and broadcasts a `policy_escalation`-typed event, same broadcaster as policy escalations.
- `action_dispatch: dict[str, Callable[[dict], dict]]` is injected, not hardcoded — `build_default_action_dispatch(run_cmd, ensure_service_allowed)` in `playbook_executor.py` wires `"restart_service"` (via the shared `jarvis/infra_actions.py` helper) and `"noop"` (for testing/logging-only steps). Adding new step types later is just adding entries to this dict, no executor changes needed.

## API + permissions

`jarvis/api_policies.py` — `build_policies_router(deps)`, one router covering **both** policies and playbooks (coordinator explicitly OK'd folding them together). All endpoints admin-gated via `require_admin_access` — same pattern as `api_alerts.py` (not a `resolve_effective_permissions`-based per-permission check; `alerts.manage` was already declared-but-not-deeply-enforced-that-way, so `policies.manage`/`playbooks.manage`/`playbooks.execute` (all three added to `KNOWN_PERMISSIONS` in `permission_store.py`) follow the same precedent — declared for future/declarative use, enforcement today is uniform admin-only).

Endpoints: `GET/POST /admin/policies`, `PATCH/DELETE /admin/policies/{id}`, `POST /admin/policies/{id}/test` (bypasses duration/cooldown gates like `AlertEngine.fire_test_alert`, still respects dry_run/emergency-stop, doesn't mutate `last_fired_at`/incident state), `GET /admin/policies/history`. Playbooks mirror this: `GET/POST /admin/playbooks`, `PATCH/DELETE /admin/playbooks/{id}`, `POST /admin/playbooks/{id}/execute?dry_run=<bool>` (query override), `POST /admin/playbooks/runs/{run_id}/resume?confirm=<bool>`, `GET /admin/playbooks/{id}/runs`, `GET /admin/playbooks/runs/{run_id}`.

## Wiring in `jarvisappv4.py`

`policy_store`/`playbook_store` instantiated alongside other stores. `policy_engine`/`playbook_executor` instantiated right after `alert_engine`'s push-fanout configuration (both reuse `get_alert_broadcaster().broadcast` as their `broadcast_fn` — **zero new delivery plumbing needed**, `policy_escalation`/`policy_dry_run`/`policy_action`/`playbook_result`/`playbook_awaiting_confirmation` all automatically get webpush fan-out to disconnected subscribers via the Phase 0 `AlertBroadcaster.configure_push_fanout` hook, since they carry no `user_id` so they broadcast to all subscribers per `push_service._target_user_ids`'s fallback). `policy_engine.start()`/`.stop()` added to `_lifespan` alongside `alert_engine.start()`/`.stop()`. Playbook execution is synchronous-on-request (no background loop — it only runs when `POST .../execute` is called), so nothing to start/stop there.

## Deferred / open items

- **No admin UI panel** for policies/playbooks (coordinator explicitly said cut this first if scope-constrained; backend + full test coverage was prioritized). `SettingsPage.tsx` already has the alert-rules panel as a template to follow.
- **Proxmox not wired as a built-in signal source yet** — the mechanism supports it (`policy_engine.register_source("proxmox_vm_status", ...)`), just not pre-built, since the only *required* domain this phase was self-healing systemd services.
- **HA-entity-conditioned policies** aren't usable out of the box (see limitation above).
- **No role-scoping** on policy/playbook execution beyond "is admin" — same gap as push notifications' fanout (see [[push-notifications-architecture]]).
- Files: `jarvis/infra_actions.py` (new, shared restart/status helpers), `jarvis/policy_store.py`, `jarvis/policy_engine.py`, `jarvis/playbook_store.py`, `jarvis/playbook_executor.py`, `jarvis/api_policies.py` (all new). Modified: `jarvis/api_models.py` (Policy/Playbook Pydantic models), `jarvis/permission_store.py`, `jarvis/router_dependencies.py`, `jarvisappv4.py`.
