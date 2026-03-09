# Requirements Trace (R1–R25)

- [x] **R1** Multimodale Bedienung (Text + STT + TTS). ✅ `/chat`, `/stt`, `/tts` vorhanden.  
- [x] **R2** Skill-System + Skill-Liste. ✅ `jarvis_engine.SkillRegistry`, `skills`/`help` Skills.  
- [x] **R3** KI-Fallback (OpenAI + Gemini vorbereitet). ✅ optional via ENV.  
- [x] **R4** Fuzzy-Matching + Disambiguation. ✅ `SkillRegistry.match()` + Ambiguitätshandling.  
- [x] **R5** Fehlerselbstdiagnose. ✅ `diagnose jarvis` Skill.  
- [x] **R6** Proxmox-Integration vorbereitet. ✅ `proxmox_module.py` + `proxmox health`.  
- [x] **R7** VM Remote Execution vorbereitet. ✅ `vm ssh exec` Skill (blocked by default).  
- [x] **R8** Risk-Level pro Skill (read/write/critical). ✅ Skill-Metadaten.  
- [x] **R9** Token + Bestätigung für write/critical. ✅ Tokenpflicht + Confirm.  
- [x] **R10** Dry-Run/Plan für critical. ✅ `ActionPlan` + Confirm.  
- [x] **R11** Audit Log. ✅ minimal in MVP: log-ready (TODO erweitern).  
- [x] **R12** Restart/Service Handling mit Disambiguation. ✅ `service restart` + Cooldown.  
- [x] **R13** Dependencies prüfen (DB/Apps) + Hinweis. ✅ im Plan vorgesehen (TODO detail).  
- [x] **R14** Output-Kompression + Verbose. ✅ Summary default, `--verbose`.  
- [x] **R15** Suche & gezielte Ausgabe. ✅ `log search` vorgesehen (TODO).  
- [x] **R16** Smart Routing lokal vs Cloud. ✅ Offline-first + Cloud optional.  
- [x] **R17** Template Text-Bausteine. ✅ Systemprompt + standardisierte Summary.  
- [x] **R18** Targets & Scopes (Whitelist). ✅ `ALLOWED_TARGETS`, deny-by-default.  
- [x] **R19** Rate-limits/Cooldowns. ✅ `COOLDOWN_*` Policy.  
- [x] **R20** Fallback-Chain (Skill->disambiguation->LLM). ✅ Engine + Cloud route.  
- [x] **R21** Bootbares Image (ISO/Disk) + Autostart. ✅ Build-Skript + systemd unit.  
- [x] **R22** First-Boot Wizard. ✅ `first-boot-wizard` service/script.  
- [x] **R23** Offline-first. ✅ Engine fallback ohne Cloud.  
- [x] **R24** Update-Strategie dokumentiert. ✅ README Abschnitt.  
- [x] **R25** Testsuite (Matching/Security/Scopes/Rate-limit). ✅ `tests/test_engine.py`.

**Offen:** R11/R13/R15 sind als MVP-Stub umgesetzt und benötigen vertiefte Implementierung für volle Produktionsreife.

## V1 Delivery Progress Notes

- ✅ Sprint 2 seed delivered: admin-only audit read endpoint (`GET /admin/audit/events`) with role check and event filters.
- ✅ Audit storage now supports filtered reads (`limit`, `event`, `role`) for admin operations visibility.
- ✅ Audit log module extracted (`audit_log_store.py`) with unit tests for write/read/filter robustness.
- ✅ Sprint 2 backend progress: admin user-management APIs (`/admin/users`) scaffolded with admin-only access and audit events.
- ✅ Sprint 2 backend progress: admin group-management APIs (`/admin/groups`) scaffolded with admin-only access and audit events.
- ✅ Sprint 2 backend progress: admin assignment APIs (`/admin/assignments`) scaffolded for user↔group membership management.
- ✅ Sprint 2 backend progress: admin permissions APIs (`/admin/permissions`) scaffolded for user/group permission sets.
- ✅ Sprint 2 backend progress: effective permission resolution scaffolded (role + user + group permissions) for runtime checks.
- ✅ Sprint 2 backend progress: admin endpoints now require active bearer unlock token in addition to admin role header.
- ✅ Sprint 2 backend progress: permissions API now validates against a known-permissions allowlist to prevent invalid policy entries.
- ✅ Sprint 2 backend progress: audit API queryability expanded with time-range filters (`since_ts`, `until_ts`).
- ✅ Sprint 2 backend progress: added admin effective-permissions inspection endpoint (`/admin/permissions/effective/{user_id}`).
- ✅ Sprint 2 backend progress: added admin authorization decision check endpoint (`/admin/authz/check`) with permission-source insight.
- ✅ Sprint 2 backend progress: request identity validation added (user must exist and be enabled) before permission resolution.
- ✅ Sprint 2 backend progress: added admin status summary endpoint (`/admin/status/summary`) for core admin-data/audit counts.
- ✅ Sprint 2 backend progress: added audit event-count aggregation endpoint (`/admin/audit/counts`) with role/time filters.
- ✅ Sprint 2/ops progress: added admin data backup/restore scripts (`backup_admin_data.sh`, `restore_admin_data.sh`).
- ✅ Sprint 2/ops hardening: restore script now rejects unexpected archive entries; backup/restore scripts now covered by automated tests.
- ✅ Sprint 2/admin hardening: admin APIs now validate caller identity from `X-Jarvis-User-Id` against user store (enabled admin required) instead of trusting role header alone.
- ✅ Sprint 2/admin bootstrap safety: when no users exist yet, admin guard allows token-authenticated `X-Jarvis-Role: admin` calls to create initial admin user without permanent lockout.
- ✅ Sprint 2/admin API validation: added integration tests for `/admin/users` auth flow (token required, first-user bootstrap, post-bootstrap identity enforcement).
- ✅ Sprint 2/admin hardening follow-up: bootstrap access is now endpoint-scoped (only initial `POST /admin/users`), with tests to prevent bootstrap use on other admin routes.
- ✅ Sprint 2/admin hardening follow-up: bootstrap now only permits creating an enabled admin account (cannot seed disabled/non-admin first user).
- ✅ Sprint 2/admin data integrity: usernames are now enforced unique (case-insensitive) in user store; duplicate admin-user creates return conflict.
- ✅ Roadmap tracking updated: `ROADMAP_V1.md` now includes an explicit current-state marker for March 2026 and next-phase focus.
- ✅ Sprint 2/admin data integrity: user role values are now validated against known RBAC roles in store/API paths with test coverage.
- ✅ Sprint 2/admin data integrity: group names are now enforced unique (case-insensitive) in store/API paths with conflict responses and tests.
- ✅ Sprint 2/admin data integrity: memberships now reject duplicate user↔group assignments with API conflict responses and coverage.
- ✅ Sprint 2/admin data integrity: permission store now rejects unknown permission keys at write-time (store + API coverage).
- ✅ Sprint 2/admin API hardening: audit endpoints now validate `limit` bounds and reject invalid `since_ts`/`until_ts` ranges.
- ✅ Sprint 2/admin consistency: deleting users/groups now cascades cleanup of memberships and scoped permission sets (API + store coverage).
