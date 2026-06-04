# JARVIS — Complete Project Reference

> "Just A Rather Very Intelligent System" — a privacy-first, self-hosted AI assistant inspired by Iron Man's JARVIS. Voice, text, home automation, infrastructure control, knowledge retrieval — all in one system, running on your own hardware.

---

## Vision

The goal is a fully autonomous, always-available personal AI that:
- Responds to voice and text commands in natural language
- Controls smart home devices (lights, climate, sensors, locks)
- Manages server infrastructure (Proxmox VMs, LXC containers, Docker)
- Answers questions from a personal knowledge base (GitHub repos, WikiJS)
- Enforces strict access control and logs every sensitive action
- Runs locally by default, falls back to cloud LLMs only when needed
- Speaks with the calm precision of Iron Man's JARVIS

**Target launch: August 2026 (V1)**

---

## Technology Stack

### Backend
| Layer | Technology |
|---|---|
| Runtime | Python 3.12 |
| Framework | FastAPI + Uvicorn (async, ASGI) |
| LLM providers | OpenAI GPT-4o, Google Gemini, local LLM (Ollama / llama.cpp compatible) |
| STT | `faster-whisper` (local, offline) or Google Gemini (cloud) |
| TTS | `edge-tts` (Microsoft Edge cloud TTS), Piper (local), OS `say` (macOS fallback) |
| Data store | SQLite (chat history), JSON files (users, groups, permissions, settings) |
| RAG | GitHub API + WikiJS GraphQL (keyword/semantic document retrieval) |

### Frontend
| Layer | Technology |
|---|---|
| Framework | React 18.3 + TypeScript 5.6 |
| Build tool | Vite 5.4 |
| Router | React Router v6 |
| Styling | Pure CSS-in-JS (no external UI library) — amber/dark Linear-style design system |
| State | React hooks only (no Redux/Zustand) |
| API comms | Fetch with streaming SSE support |

### Infrastructure
| Area | Technology |
|---|---|
| Proxmox integration | HTTP REST via Proxmox API tokens |
| Home Assistant | REST + WebSocket API (`JARVIS_HA_BASE_URL` + `JARVIS_HOME_ASSISTANT_TOKEN`) |
| Tests | pytest (Python), Vitest (frontend) |
| CI | GitHub Actions (`.github/`) |

---

## Project Structure

```
jarvis/
├── jarvisappv4.py              # Application entry point — wires all routers, stores, engine
├── requirements.txt            # Python deps: fastapi, uvicorn, openai, google-genai, faster-whisper, edge-tts
├── CLAUDE.md                   # This file
├── README.md                   # High-level overview
│
├── jarvis/                     # All Python application code
│   ├── __init__.py
│   ├── jarvis_engine.py        # Role/permission model, SecurityPolicy, JarvisEngine, ActionPlan, Skill
│   ├── assistant_domain.py     # ALL skill routing logic (try_skill), weather, RAG, LLM fallback
│   ├── ai_clients.py           # OpenAI / Gemini / local LLM clients, JARVIS system prompt
│   ├── audio_services.py       # TTS (edge-tts/piper), STT (whisper/gemini), wakeword logic
│   ├── authz.py                # resolve_effective_permissions, permission_decision, build_permission_context
│   ├── skill_utils.py          # run_cmd, disk_usage, parse_meminfo, parse_ping, tail_lines
│   ├── llm_utils.py            # Token budget trimming for LLM history
│   ├── rate_limiter.py         # In-memory rate limiter (_rate.allow)
│   │
│   ├── api_admin.py            # /admin/* REST endpoints (users, groups, perms, audit, backup)
│   ├── api_auth_chat.py        # /auth/* /unlock /chat /chat/stream /rag/* /sys/metrics
│   ├── api_voice.py            # /stt /tts /api/tts/voices
│   ├── api_alerts.py           # WebSocket /ws/alerts
│   ├── api_home_assistant.py   # /home-assistant/* REST + WebSocket /ws/home-assistant
│   ├── api_status.py           # WebSocket /ws/status
│   ├── api_models.py           # All Pydantic request/response models
│   ├── router_dependencies.py  # Dependency injection — build_*_deps, LiveRef
│   ├── frontend_routes.py      # Serves built frontend + SPA fallback
│   │
│   ├── runtime_state.py        # ChatHistoryStore (SQLite), RagStore, JarvisStatusHub
│   ├── runtime_helpers.py      # Pure helper functions called by jarvisappv4 (token, audit, etc.)
│   ├── session_auth.py         # Bearer token validation, prune_expired_tokens
│   ├── identity.py             # get_active_user_or_raise
│   │
│   ├── user_store.py           # JSON-backed user CRUD
│   ├── group_store.py          # JSON-backed group CRUD
│   ├── membership_store.py     # User↔Group membership JSON store
│   ├── permission_store.py     # KNOWN_PERMISSIONS, group/user permission grant store
│   ├── audit_log_store.py      # Append-only audit log with filtering and aggregation
│   ├── admin_access.py         # require_admin_access guard
│   ├── admin_password_store.py # Bcrypt-hashed admin passwords
│   ├── admin_settings_store.py # Global settings JSON store
│   ├── user_preferences_store.py # Per-user preferences (theme, voice, display_name, notes)
│   ├── proxmox_module.py       # Proxmox REST proxy — hosts CRUD, VMs, LXC, storage
│   │
│   └── home_assistant/
│       ├── __init__.py
│       ├── client.py           # HomeAssistantClient — HTTP calls to HA REST API
│       ├── service.py          # HomeAssistantService — business logic, risk enforcement
│       ├── store.py            # HomeAssistantStore — entities, areas, automations, shopping list, calendar, inbox
│       ├── models.py           # HA Pydantic models
│       ├── permissions.py      # HOME_ASSISTANT_PERMISSIONS set (home_assistant.access, etc.)
│       ├── risk.py             # HOME_ASSISTANT_ACTION_POLICIES — risk levels per action type
│       ├── discovery.py        # Device discovery candidates
│       ├── chat_intents.py     # execute_home_assistant_chat_intent — NLU→HA action bridge
│       └── chat_actions.py     # Chat-driven HA action execution helpers
│
├── frontend/
│   ├── index.html
│   ├── vite.config.ts
│   ├── package.json
│   └── src/
│       ├── main.tsx            # React root, AuthProvider mount
│       ├── styles.css          # Global CSS reset + theme variables
│       ├── styles/theme.css    # CSS custom properties for amber dark/light themes
│       │
│       ├── features/auth/
│       │   └── AuthProvider.tsx    # Session/guest auth context
│       │
│       ├── components/
│       │   ├── ErrorBoundary.tsx
│       │   └── GreetingOverlay.tsx  # Startup greeting animation
│       │
│       ├── screens/
│       │   ├── JarvisApp.tsx       # Root shell — nav rail, screen switching, theme
│       │   ├── jarvis-shared.tsx   # Design system: J tokens, icons, components (StatusBadge, Toast, etc.)
│       │   ├── LoginScreen.tsx     # User + guest login
│       │   ├── ChatScreen.tsx      # Full chat UI with session sidebar, streaming, TTS playback
│       │   ├── OrbScreen.tsx       # Voice interaction — animated orb canvas, mic, STT→chat→TTS
│       │   ├── HomeAssistantScreen.tsx  # Smart home — devices, shopping, calendar, inbox, control requests
│       │   ├── ProxmoxScreen.tsx   # Proxmox VMs/LXC/storage dashboard
│       │   ├── ServiceHubScreen.tsx    # Overview of all connected services + status
│       │   ├── SettingsScreen.tsx  # Appearance, voice, integrations, security, developer settings
│       │   └── DocsScreen.tsx      # Interactive skill reference / command documentation
│       │
│       ├── routes/
│       │   ├── auth/
│       │   │   └── AdminLoginPage.tsx
│       │   └── admin/pages/
│       │       ├── DashboardPage.tsx   # Admin summary stats
│       │       ├── UsersPage.tsx       # User management
│       │       ├── GroupsPage.tsx      # Group management + membership
│       │       ├── PermissionsPage.tsx # Permission grant UI
│       │       ├── LogsPage.tsx        # Audit log viewer with filters
│       │       ├── SettingsPage.tsx    # Admin-level settings (voice, LLM, HA)
│       │       └── StatusPage.tsx      # Live system status
│       │
│       └── shared/
│           ├── layout/
│           │   └── AdminShell.tsx      # Admin dashboard wrapper/nav
│           ├── ui/
│           │   └── OverlayDialog.tsx   # Reusable modal dialog
│           └── api/
│               ├── client.ts       # Base fetch wrapper, auth headers, stored prefs/identity
│               ├── chat.ts         # Chat sessions, streaming, TTS, STT, metrics, search
│               ├── admin.ts        # Admin REST wrappers
│               ├── homeAssistant.ts # HA REST + WebSocket hooks
│               ├── proxmox.ts      # Proxmox REST wrappers
│               ├── alerts.ts       # useJarvisAlerts WebSocket hook
│               └── status.ts       # useJarvisLiveStatus WebSocket hook
│
├── tests/                      # ~50 pytest test files, 878+ tests passing
├── scripts/                    # Ops scripts: benchmark, evidence collection, token lifecycle drill
└── docs/
    ├── README.md
    └── v1/
        ├── planning/
        │   ├── ROADMAP_V1.md
        │   ├── RELEASE_CRITERIA_V1.md
        │   ├── SPRINT_PLAN_V1.md
        │   ├── EXECUTION_CHECKLIST_V1.md
        │   ├── ROLE_PERMISSION_MATRIX_V1.md
        │   └── HOME_ASSISTANT_FOUNDATION_PLAN.md
        ├── handoff/
        │   ├── MANUAL_ACCEPTANCE_V1.md
        │   └── USER_EXECUTION_RUNBOOK_V1.md
        └── evidence/            # V1 release evidence templates and collected artifacts
```

---

## All API Endpoints

### System
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | none | Liveness check |
| GET | `/greeting` | localhost only | TTS-ready startup greeting |

### Auth & Identity
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/admin/login` | none | Admin username/password → session token |
| POST | `/auth/login` | none | User login → identity session |
| POST | `/auth/logout` | session | Logout / invalidate session |
| GET | `/auth/me` | session | Current user profile |
| GET | `/auth/me/preferences` | session | User preferences |
| PUT | `/auth/me/preferences` | session | Update user preferences |
| PUT | `/auth/me/password` | session | Change own password |
| POST | `/admin/session` | admin token | Mint identity session for a user |
| POST | `/unlock` | passphrase | Get bearer token (for guest/device access) |
| POST | `/unlock/revoke` | bearer | Revoke bearer token |

### Chat & RAG
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/chat` | session/bearer | Single-turn chat (skills → RAG → LLM) |
| POST | `/chat/stream` | session/bearer | Streaming SSE chat |
| GET | `/chat/sessions` | session | List chat sessions |
| POST | `/chat/sessions` | session | Create new session |
| GET | `/chat/sessions/{id}` | session | Get session with messages |
| PATCH | `/chat/sessions/{id}` | session | Rename session |
| DELETE | `/chat/sessions/{id}` | session | Delete session |
| POST | `/chat/sessions/{id}/pending-home-assistant/clear` | session | Clear pending HA action |
| GET | `/chat/search` | session | Full-text search across messages |
| GET | `/sys/metrics` | session | CPU, RAM, disk, load metrics |
| GET | `/rag/status` | session | RAG store status |
| POST | `/rag/refresh` | session | Trigger RAG re-index (GitHub/WikiJS) |
| GET | `/rag/search` | session | Search RAG knowledge base |

### Voice
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/stt` | session (orb mode) | Audio file → transcribed text (Whisper or Gemini) |
| POST | `/tts` | none | Text → synthesized speech audio |
| GET | `/api/tts/voices` | none | List available TTS voices |

### Admin — Users, Groups, Permissions
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/admin/users` | admin | List users |
| POST | `/admin/users` | admin | Create user |
| PATCH | `/admin/users/{id}` | admin | Update user |
| PUT | `/admin/users/{id}/password` | admin | Set user password |
| DELETE | `/admin/users/{id}` | admin | Delete user |
| DELETE | `/admin/users/{id}/conversations` | admin | Purge user's chat history |
| GET | `/admin/groups` | admin | List groups |
| POST | `/admin/groups` | admin | Create group |
| PATCH | `/admin/groups/{id}` | admin | Update group |
| DELETE | `/admin/groups/{id}` | admin | Delete group |
| GET | `/admin/assignments` | admin | List group memberships |
| POST | `/admin/assignments` | admin | Add user to group |
| DELETE | `/admin/assignments` | admin | Remove user from group |
| GET | `/admin/permissions` | admin | List all permission grants |
| PUT | `/admin/permissions/groups/{id}` | admin | Set group permissions |
| PUT | `/admin/permissions/users/{id}` | admin | Set user permissions |
| DELETE | `/admin/permissions/groups/{id}` | admin | Clear group permissions |
| DELETE | `/admin/permissions/users/{id}` | admin | Clear user permissions |
| GET | `/admin/permissions/effective/{user_id}` | admin | Resolved effective permissions |
| GET | `/admin/authz/check` | admin | Permission check dry-run |

### Admin — Settings, Audit, Sessions, Backup
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/admin/settings` | admin | Global settings |
| PUT | `/admin/settings` | admin | Update global settings |
| GET | `/admin/status/summary` | admin | System + store stats |
| GET | `/admin/sessions` | admin | Active session list |
| DELETE | `/admin/sessions/{user_id}` | admin | Revoke a user's sessions |
| GET | `/admin/audit/events` | admin | Query audit log (filterable) |
| GET | `/admin/audit/counts` | admin | Audit event counts |
| GET | `/admin/audit/count` | admin | Single event-type count |
| GET | `/admin/backup` | admin | Export full backup JSON |
| POST | `/admin/backup/restore` | admin | Restore from backup JSON |

### Home Assistant
| Method | Path | Auth | Description |
|---|---|---|---|
| WS | `/ws/home-assistant` | session | Live HA entity state stream |
| GET | `/home-assistant/overview` | session | Summary overview |
| GET | `/home-assistant/entities` | session | All managed entities |
| GET | `/home-assistant/areas` | session | Area/room summaries |
| GET | `/home-assistant/device-profiles` | session | Supported device type profiles |
| GET | `/home-assistant/system-target-profiles` | session | Automation target profiles |
| GET | `/home-assistant/system-targets` | session | Current system targets |
| POST | `/home-assistant/system-targets` | session | Add system target |
| POST | `/home-assistant/entities/{id}/actions` | session | Execute entity action (risk-gated) |
| POST | `/home-assistant/system-targets/{id}/actions` | session | Execute system-target action |
| GET | `/home-assistant/control-requests` | session | Pending control-request queue |
| POST | `/home-assistant/control-requests/{id}/confirm` | session | Approve/deny pending request |
| GET | `/home-assistant/automations` | session | Automation rules |
| POST | `/home-assistant/automations` | session | Create automation rule |
| POST | `/home-assistant/automations/{id}/toggle` | session | Enable/disable automation |
| GET | `/home-assistant/security-posture` | session | Security status |
| GET | `/home-assistant/recovery-playbooks` | session | Available recovery playbooks |
| POST | `/home-assistant/recovery-playbooks/{id}/execute` | session | Run playbook |
| GET | `/home-assistant/discovery/candidates` | session | Discovered but unapproved devices |
| POST | `/home-assistant/discovery/candidates` | session | Scan for new devices |
| POST | `/home-assistant/discovery/candidates/{id}/approve` | session | Approve discovered device |
| POST | `/home-assistant/sync/entities` | session | Sync entities from HA |
| GET | `/home-assistant/health` | session | HA connection health |
| GET | `/home-assistant/shopping-list` | session | Shopping list |
| POST | `/home-assistant/shopping-list/items` | session | Add item |
| GET | `/home-assistant/calendar` | session | Calendar events |
| POST | `/home-assistant/calendar/items` | session | Create calendar entry |
| POST | `/home-assistant/calendar/items/{id}/actions` | session | Act on calendar item |
| POST | `/home-assistant/sync/calendar` | session | Sync calendar from HA |
| GET | `/home-assistant/inbox` | session | Notifications inbox |
| POST | `/home-assistant/inbox/items` | session | Create inbox item |
| POST | `/home-assistant/inbox/items/{id}/actions` | session | Act on inbox item |
| POST | `/home-assistant/sync/inbox` | session | Sync inbox from HA |

### Proxmox
All Proxmox routes are mounted under `/proxmox`:

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/proxmox/hosts` | bearer | List configured Proxmox hosts |
| POST | `/proxmox/hosts` | bearer | Add Proxmox host |
| DELETE | `/proxmox/hosts/{id}` | bearer | Remove host |
| GET | `/proxmox/hosts/{id}/version` | bearer | Host PVE version |
| GET | `/proxmox/hosts/{id}/nodes` | bearer | Node list |
| GET | `/proxmox/hosts/{id}/nodes/{node}/vms` | bearer | VM list |
| GET | `/proxmox/hosts/{id}/nodes/{node}/containers` | bearer | LXC list |
| GET | `/proxmox/hosts/{id}/nodes/{node}/storage` | bearer | Storage list |
| GET | `/proxmox/hosts/{id}/nodes/{node}/vms/{vmid}/status` | bearer | VM status |
| GET | `/proxmox/hosts/{id}/nodes/{node}/containers/{vmid}/status` | bearer | Container status |
| GET | `/proxmox/health` | bearer | Proxmox module health |

### WebSockets
| Path | Description |
|---|---|
| `/ws/status` | JarvisStatusHub — live recording/thinking/speaking state |
| `/ws/alerts` | Live alert stream |
| `/ws/home-assistant` | Live HA entity state push |

---

## Security & Authorization Model

### Roles
| Role | Capabilities |
|---|---|
| `admin` | Full access: voice, write actions, dangerous actions |
| `standard_user` | Voice + chat only by default |
| `guest_restricted` | Voice only by default |
| `service_system` | No default permissions (machine identity) |

### Permission Grants (beyond role defaults)
Permissions can be granted per-user or per-group. Known permissions:
- `voice.use`, `assistant.chat`, `devices.read`, `devices.manage`
- `calendar.read`, `calendar.write`, `email.read`, `email.write`
- `actions.write.execute` — required for all write skills (service restart, etc.)
- `actions.dangerous.execute` — required for dangerous actions (shutdown, VM delete)
- `actions.dangerous.approve` — can approve confirmation dialogs
- `users.manage`, `groups.manage`, `permissions.manage`
- `audit.read`, `settings.manage`, `emergency_stop.trigger`
- `home_assistant.access` + granular HA permissions

### Emergency Stop
`JARVIS_EMERGENCY_STOP=1` blocks all write and dangerous actions system-wide instantly.

---

## Skills System (Deterministic Routing)

All chat input first passes through `try_skill()` in `assistant_domain.py`. If a skill matches, it responds immediately without an LLM call. Unmatched input falls through to RAG, then LLM.

### Skill Categories
| Category | Examples |
|---|---|
| **System status** | `status`, `health`, `briefing`, `cpu`, `memory`, `disk`, `uptime`, `sysinfo`, `load`, `processes` |
| **Networking** | `ip`, `ports`, `ping <host>`, `connections` |
| **Services** | `status <svc>`, `logs <svc>`, `restart/start/stop <svc>` (write permission required) |
| **Docker** | `docker`, `docker stats` |
| **Proxmox** | `pve vm status <id>`, `pve lxc status <id>` |
| **System ops** | `shutdown [in N min]`, `reboot [in N min]` (admin only) |
| **Date/Time** | `time`, `date`, `time in <city>`, `days until <event>` |
| **Weather** | `weather <city>`, `forecast <city>` (open-meteo, no API key) |
| **Math/Calc** | Arithmetic expressions, unit conversions (km↔mi, kg↔lbs, °C↔°F, etc.) |
| **Utilities** | `uuid`, `timestamp`, `epoch`, `hash <text>`, `base64 encode/decode` |
| **Knowledge** | `hostname`, `kernel`, `who`, `last`, `whoami` |
| **Help** | `help`, `skills`, `what can you do` |

Write-level skills (`restart`, `start`, `stop`, `shutdown`) require bearer token + `actions.write.execute` permission.
Dangerous skills (`shutdown`, `reboot`) additionally require `actions.dangerous.execute`.

---

## Voice Pipeline

```
User speaks
  → Mic capture (browser MediaRecorder)
  → POST /stt (WebM/WAV audio)
  → faster-whisper (local) OR Gemini (cloud) → text
  → Optional wakeword stripping ("hey jarvis ...")
  → POST /chat/stream → skill routing or LLM
  → Response text
  → POST /tts → edge-tts (Microsoft neural) or Piper (local) → audio
  → Browser plays audio
```

STT providers: `local` (faster-whisper, default) or `gemini`
TTS providers: `edge-tts` (default), `piper` (local), `say` (macOS only)

---

## LLM Fallback Chain

```
User input
  1. try_skill() → deterministic skill match → return immediately
  2. rag_query_from_prompt() → search GitHub/WikiJS knowledge base
     → if hits: format_rag_reply() or rag_llm_answer() (LLM-grounded)
  3. build_context_reply() → LLM (OpenAI / Gemini / local)
     → history trimmed to token budget via trim_to_budget()
```

LLM providers (env `LLM_PROVIDER`): `openai`, `gemini`, `local`

---

## Environment Variables

### Required for core features
| Variable | Default | Purpose |
|---|---|---|
| `JARVIS_PASSPHRASE` | — | Guest/device unlock passphrase |
| `OPENAI_API_KEY` | — | Chat LLM (if using OpenAI) |
| `GEMINI_API_KEY` | — | Chat LLM or cloud STT |

### Optional — LLM
| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | auto-detect | `openai`, `gemini`, `local` |
| `OPENAI_MODEL` | gpt-4o | Model override |
| `OPENAI_MAX_TOKENS` | 1024 | Max response tokens |
| `GEMINI_MODEL` | gemini-2.0-flash | Model override |
| `LOCAL_LLM_ENABLED` | 0 | Enable local LLM |
| `LOCAL_LLM_BASE_URL` | http://localhost:11434 | Ollama/llama.cpp base URL |
| `LOCAL_LLM_BACKEND` | ollama | Backend type |

### Optional — Voice
| Variable | Default | Purpose |
|---|---|---|
| `STT_PROVIDER` | local | `local` (whisper) or `gemini` |
| `TTS_PROVIDER` | edge-tts | `edge-tts`, `piper`, `say` |
| `WHISPER_MODEL` | base | faster-whisper model size |
| `WHISPER_COMPUTE` | int8 | Compute type |
| `EDGE_TTS_VOICE` | — | Edge-TTS voice override |
| `EDGE_TTS_RATE` | — | Speech rate |
| `EDGE_TTS_PITCH` | — | Speech pitch |
| `PIPER_BIN` | piper | Piper binary path |
| `PIPER_MODEL` | — | Piper model path |
| `JARVIS_WAKEWORD_ENABLED` | false | Enable wakeword detection |
| `JARVIS_WAKEWORD_PHRASE` | hey jarvis | Wakeword phrase |

### Optional — Home Assistant
| Variable | Purpose |
|---|---|
| `JARVIS_HA_BASE_URL` | Home Assistant URL (e.g. `http://homeassistant.local:8123`) |
| `JARVIS_HOME_ASSISTANT_TOKEN` | HA long-lived access token |
| `JARVIS_HOME_ASSISTANT_REMOTE_ALLOWED_CIDRS` | Allowed CIDRs for remote actions |
| `JARVIS_HOME_ASSISTANT_CONFIRMATION_TTL_SEC` | Confirmation request TTL |
| Various `JARVIS_HOME_ASSISTANT_CALENDAR_*` | CalDAV integration config |
| Various `JARVIS_HOME_ASSISTANT_INBOX_*` | Inbox integration config |

### Optional — Proxmox
| Variable | Purpose |
|---|---|
| `PROXMOX_BASE_URL` | Default Proxmox host URL |
| `PROXMOX_API_TOKEN` | Default API token |
| `PROXMOX_HOSTS_FILE` | Path to hosts JSON file |

### Optional — Knowledge / RAG
| Variable | Purpose |
|---|---|
| `GITHUB_PAT` | GitHub personal access token |
| `GITHUB_REPO` | GitHub repo for knowledge (e.g. `owner/repo`) |
| `GITHUB_BRANCH` | Branch to index (default: main) |
| `GITHUB_RAG_INCLUDE_EXTENSIONS` | File extensions to index |
| `WIKIJS_GRAPHQL_URL` | WikiJS GraphQL endpoint |
| `WIKIJS_API_KEY` | WikiJS API key |

### Optional — Paths & Operations
| Variable | Default | Purpose |
|---|---|---|
| `JARVIS_DEFAULT_ADMIN_USERNAME` | admin | Bootstrap admin username |
| `JARVIS_DEFAULT_ADMIN_PASSWORD` | admin123 | Bootstrap admin password |
| `JARVIS_EMERGENCY_STOP` | 0 | Kill switch for write actions |
| `JARVIS_TOKEN_TTL_MIN` | 60 | Bearer token TTL in minutes |
| `JARVIS_MAX_ACTIVE_TOKENS` | 10 | Max concurrent bearer tokens |
| `JARVIS_AUTO_BACKUP_DISABLED` | 0 | Disable auto-backup |
| `JARVIS_AUTO_BACKUP_INTERVAL_HOURS` | 24 | Auto-backup interval |
| `JARVIS_AUDIT_LOG_PATH` | /var/lib/jarvis/ | Audit log location |
| `JARVIS_CHAT_HISTORY_PATH` | /var/lib/jarvis/ | Chat history SQLite path |
| `JARVIS_USER_STORE_PATH` | /var/lib/jarvis/ | User store JSON path |
| `JARVIS_MEMORY_PATH` | /var/lib/jarvis/memory.json | Engine memory file |
| `ALLOWED_TARGETS` | — | Comma-separated allowed service targets |

---

## Data Storage

All data is stored locally by default at `/var/lib/jarvis/` (falls back to `/tmp/jarvis/` if not writable):

| File | Format | Contents |
|---|---|---|
| `chat_history.db` | SQLite | Sessions + messages |
| `users.json` | JSON | User accounts |
| `groups.json` | JSON | Groups |
| `memberships.json` | JSON | User↔group memberships |
| `permissions.json` | JSON | Permission grants |
| `audit_log.json` | JSON (append) | All audited events |
| `admin_settings.json` | JSON | Global settings (voice, LLM, HA config) |
| `admin_passwords.json` | JSON | Bcrypt-hashed passwords |
| `user_preferences.json` | JSON | Per-user preferences |
| `memory.json` | JSON | Engine memory (notes, aliases, feedback) |
| `proxmox_hosts.json` | JSON | Configured Proxmox hosts |
| `/var/lib/jarvis/auto_backups/` | JSON | Rolling auto-backups (7 kept) |

---

## What Is Already Working (V35)

### Backend
- Full RBAC: 4 roles, per-user/group permission grants, effective permission resolution
- Auth system: admin login, user login, guest bearer token, identity sessions
- Chat: streaming SSE, session management, history, full-text search
- Skills: ~40+ deterministic skill routes (system, network, Docker, Proxmox, weather, math, time/date, utilities)
- LLM: OpenAI + Gemini + local LLM routing with conversation history and token budget
- Voice: STT (faster-whisper + Gemini), TTS (edge-tts + Piper), wakeword
- RAG: GitHub + WikiJS ingestion, keyword search, LLM-grounded answers
- Home Assistant: full entity CRUD, actions with risk gating, automations, discovery, control-request queue, shopping list, calendar, inbox, WebSocket live updates
- Proxmox: multi-host management, VMs + LXC + storage, VM/LXC skills
- Admin dashboard: users, groups, permissions, audit logs, settings, backup/restore
- Auto-backup: hourly/daily JSON backup with 7-file rotation
- Emergency stop: env-var kill switch blocks all writes
- Audit log: all sensitive events logged with filtering + aggregation
- Rate limiting: per-session/IP rate limiter on STT and other endpoints
- 878+ passing tests across all core modules

### Frontend
- Full dark/light theme (amber accent, Linear-style)
- NavRail (desktop) + bottom nav (mobile)
- Chat screen with session sidebar, streaming, markdown, TTS playback, message search
- Voice/Orb screen with animated canvas orb, MediaRecorder, audio playback
- Home Assistant screen: device cards, area view, shopping/calendar/inbox tabs, control requests
- Proxmox screen: host management, node/VM/LXC/storage drill-down
- Service Hub: overview of all integrations with live status
- Settings screen: appearance, voice selection, integrations, security, developer panel
- Docs screen: interactive skill reference organized by category
- Admin dashboard at `/dashboard` with full management UI

---

## What Is Still Missing / Must Be Built for V1

### High Priority (P0 — V1 Blockers)

1. **Real wakeword detection** — Current wakeword is software string-stripping only. Needs always-on mic + keyword spotting engine (e.g. OpenWakeWord, Vosk, Porcupine). Required for hands-free "Hey JARVIS" activation.

2. **Voice quality sign-off on target hardware** — STT/TTS pipeline needs formal validation on lower-end hardware (Raspberry Pi 5, mini PC). Latency measurements required (P50/P95).

3. **Deployment + rollback procedure** — Documented and drilled. Systemd unit file, `update.sh`, `rollback.sh`, clean install from scratch. Evidence file required.

4. **Environment separation (dev/test/prod)** — Config isolation between environments must be validated end-to-end.

5. **Performance benchmark** — Formal latency report on target hardware. Script exists at `scripts/benchmark_local.py` but results not collected.

6. **Manual acceptance testing** — `docs/v1/handoff/MANUAL_ACCEPTANCE_V1.md` checklist must be completed and signed.

7. **Security sign-off** — Manual walkthrough of top 10 dangerous actions with RBAC + emergency stop + audit log verification.

8. **Recovery drills** — Backup/restore + rollback drills with evidence (templates in `docs/v1/evidence/templates/`).

### Medium Priority (Significantly improves V1 quality)

9. **Proactive JARVIS mode** — JARVIS should occasionally push alerts without being asked: "Sir, CPU has been above 90% for 5 minutes." Needs background task scheduler + alert policy engine.

10. **Persistent engine memory** — `memory.json` exists but is not yet surfaced in the chat UI. JARVIS should remember user preferences, feedback, and context between sessions. Needs memory read/write UI + skills.

11. **Chat-to-HA intent routing** — `chat_intents.py` exists but NLU routing from free-text to HA actions needs hardening and broader coverage. "Turn off the lights in the kitchen" should reliably work.

12. **Notification system** — `/ws/alerts` WebSocket exists but alert generation is minimal. Needs rules: threshold alerts (CPU, disk), HA state change alerts, calendar reminders.

13. **Documentation screen completeness** — `DocsScreen.tsx` is static. Should show live capability state (which integrations are active, which skills are available given current config).

14. **Admin UX polish** — Admin dashboard is functional but needs layout improvements, bulk operations, and clearer feedback on permission changes.

15. **Multi-voice persona** — Multiple TTS voice profiles with per-user selection. Backend `JARVIS_VOICES` list exists, frontend voice picker exists, but quality tuning is not done.

### Future / Post-V1

16. **Mobile app** — React Native or PWA with push notifications and offline voice.
17. **MFA / device auth** — Passkey or TOTP as second factor for admin actions.
18. **Autonomous home provisioning** — Auto-discover and onboard new HA devices without manual approval.
19. **Self-learning loops** — JARVIS learns from corrections and feedback (already has memory.json foundation).
20. **Telephony** — Accept/place calls, leave voice memos.
21. **Cross-device sync** — Shared session state across phone, desktop, dedicated display.
22. **Plugin system** — Third-party skill packs installable without code changes.
23. **Streaming Home Assistant control** — Real-time bidirectional HA WebSocket (currently polling-based sync).

---

## V1 Release Criteria (from `docs/v1/planning/RELEASE_CRITERIA_V1.md`)

V1 ships only when ALL of these pass:
1. RBAC enforced on all sensitive actions — automated + manual test evidence
2. Assistant responds reliably (skill → RAG → LLM fallback chain deterministic)
3. Voice workflow passes acceptance scenarios (wakeword/STT/TTS failure handling)
4. Deployment from clean environment is reproducible
5. Backup/restore and rollback validated with evidence
6. Performance benchmark on target hardware (P50/P95 latency)
7. Recovery test: service recovers after restart and transient dependency failure

Target: **August 2026**

---

## Running the Project

```bash
# Backend
cd /home/jarvis/jarvis
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn jarvisappv4:app --host 0.0.0.0 --port 8000 --reload

# Frontend (dev)
cd frontend
npm install
npm run dev

# Frontend (build + serve via backend)
npm run build
# Backend then serves dist/ at /

# Tests
pytest tests/ -x -q
```

---

## Agent Rules

These rules apply to ALL agents working in this codebase. Follow them strictly.

### Code Style
- Python 3.12 type hints on all function signatures
- No docstrings unless the function is a public API boundary with non-obvious behavior
- No inline comments unless explaining a non-obvious invariant or workaround
- Maximum function size: ~50 lines. Extract helpers rather than scrolling monsters.
- Prefer pure functions injected with dependencies over class methods that close over globals
- All new backend endpoints follow the `build_*_router(deps: dict)` pattern with `LiveRef` dependency injection

### Testing
- Every new backend endpoint gets at least one test in `tests/`
- Tests use `TestClient` from FastAPI — no real HTTP, no sleep()
- Never mock the stores — instantiate real in-memory instances for tests
- Frontend tests use Vitest — keep them in `src/shared/api/*.test.ts`
- Run `pytest tests/ -x -q` before declaring backend work done

### Frontend
- No external UI libraries — use the existing design system in `jarvis-shared.tsx`
- All colors come from the `J` token object — never hardcode hex values
- All new screens follow the pattern in existing screens: named export, `useJ()` for theme
- Mobile-responsive: test at 375px width minimum

### Security
- Every new endpoint that touches user data or actions must call `require_admin_access` or `require_identity_session`
- Every sensitive action must be audited via `audit_admin_event`
- Write actions must call `block_write_if_unauthorized` before executing
- Never log secrets, tokens, or passwords — log fingerprints only
- JARVIS_EMERGENCY_STOP must always be respected before any write action

### Architecture
- Skill logic lives in `assistant_domain.py::try_skill()` — add new deterministic skills there
- New integrations get their own `api_*.py` router + `build_*_deps()` in `router_dependencies.py`
- New data stores follow the pattern in `user_store.py` — JSON files, thread-safe with file locking
- Never import `jarvisappv4` from inside `jarvis/` modules — it's the top-level wiring only
- The `JarvisEngine` + `build_registry()` in `jarvis_engine.py` is the canonical action registry

### Conventions
- JARVIS speaks in first person with calm, dry authority — never "I cannot", never apologetic
- TTS-destined text must go through `tts_preprocess_text()` before playback
- All timestamps are Unix epoch integers (not ISO strings) in API responses
- Backup format is versioned JSON with `backup_version: 1` field
- All new permissions must be added to `KNOWN_PERMISSIONS` in `permission_store.py`

---

## Iron Man Vision — What "Done" Looks Like

When V1 is complete, JARVIS should behave like this:

```
[System boots]
JARVIS: "Good morning, sir. It is 07:42 on Wednesday. 
         All systems nominal. Three items in your inbox. 
         J.A.R.V.I.S. standing by."

[User walks in]
User: "Hey JARVIS, what's the status of the Proxmox cluster?"
JARVIS: "Node pve-01 is running 4 VMs, all nominal. 
         pve-02 is offline for scheduled maintenance. 
         Storage at 62% capacity."

[User]: "Turn off the living room lights and set the temperature to 20 degrees."
JARVIS: "Done. Lights off, thermostat set to 20."

[User]: "Restart the nginx service."
JARVIS: "Restarting nginx... service is back online."

[User]: "Who accessed the system last night?"
JARVIS: "Three login events between 22:00 and 06:00, all from your account. 
         No anomalies detected."

[User]: "Set an alarm for the team meeting tomorrow at 10."
JARVIS: "Calendar entry created for tomorrow at 10:00."
```

Everything in that exchange either already works or is on the roadmap above.
