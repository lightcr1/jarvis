import React, { useState } from "react";
import { useJ } from "../../../screens/jarvis-shared";

type Section = {
  id: string;
  label: string;
  content: React.ReactNode;
};

function DocSection({ title, children }: { title: string; children: React.ReactNode }) {
  const J = useJ();
  return (
    <section style={{ marginBottom: 36 }}>
      <h2 style={{ fontSize: 16, fontWeight: 700, color: J.text, margin: "0 0 12px", paddingBottom: 8, borderBottom: `1px solid ${J.border}` }}>
        {title}
      </h2>
      {children}
    </section>
  );
}

function P({ children }: { children: React.ReactNode }) {
  const J = useJ();
  return <p style={{ fontSize: 13, color: J.textSec, lineHeight: 1.7, margin: "0 0 10px" }}>{children}</p>;
}

function Code({ children }: { children: React.ReactNode }) {
  const J = useJ();
  return (
    <code style={{ fontFamily: "monospace", fontSize: 11, background: J.bg3, color: J.amber, padding: "1px 5px", borderRadius: 3 }}>
      {children}
    </code>
  );
}

function Block({ children }: { children: React.ReactNode }) {
  const J = useJ();
  return (
    <pre style={{ fontFamily: "monospace", fontSize: 11, background: J.bg3, color: J.text, padding: "10px 14px", borderRadius: 6, border: `1px solid ${J.border}`, overflowX: "auto", margin: "8px 0 14px", lineHeight: 1.6 }}>
      {children}
    </pre>
  );
}

function Table({ headers, rows }: { headers: string[]; rows: string[][] }) {
  const J = useJ();
  return (
    <div style={{ overflowX: "auto", margin: "8px 0 16px" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr>
            {headers.map(h => (
              <th key={h} style={{ textAlign: "left", padding: "6px 12px", background: J.bg3, color: J.textSec, fontWeight: 600, borderBottom: `1px solid ${J.border}`, whiteSpace: "nowrap" }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={{ borderBottom: `1px solid ${J.border}` }}>
              {row.map((cell, j) => (
                <td key={j} style={{ padding: "7px 12px", color: J.text, verticalAlign: "top" }}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Note({ children, type = "info" }: { children: React.ReactNode; type?: "info" | "warn" | "danger" }) {
  const J = useJ();
  const colors = {
    info:   { bg: J.blueDim,   border: J.blue,  color: J.blue  },
    warn:   { bg: J.warnDim,   border: J.warn,  color: J.warn  },
    danger: { bg: J.errorDim,  border: J.error, color: J.error },
  }[type];
  return (
    <div style={{ background: colors.bg, border: `1px solid ${colors.border}30`, borderLeft: `3px solid ${colors.border}`, borderRadius: 6, padding: "9px 14px", margin: "8px 0 14px", fontSize: 12, color: colors.color, lineHeight: 1.6 }}>
      {children}
    </div>
  );
}

function H3({ children }: { children: React.ReactNode }) {
  const J = useJ();
  return <h3 style={{ fontSize: 13, fontWeight: 600, color: J.text, margin: "16px 0 6px" }}>{children}</h3>;
}

const SECTIONS: Array<{ id: string; label: string }> = [
  { id: "overview",   label: "Overview" },
  { id: "providers",  label: "AI Providers" },
  { id: "routing",    label: "Request Routing" },
  { id: "byok",       label: "BYOK Keys" },
  { id: "credits",    label: "Credits & Billing" },
  { id: "limits",     label: "Per-User Limits" },
  { id: "usage",      label: "Usage Tracking" },
  { id: "killswitch", label: "Kill Switch" },
  { id: "models",     label: "Model Tiers" },
  { id: "rbac",       label: "RBAC & Permissions" },
  { id: "backup",     label: "Backup & Restore" },
];

export function AdminDocsPage() {
  const J = useJ();
  const [active, setActive] = useState("overview");

  return (
    <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>

      {/* TOC sidebar */}
      <aside style={{ width: 180, flexShrink: 0, borderRight: `1px solid ${J.border}`, padding: "16px 8px", overflowY: "auto" }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: J.textMuted, letterSpacing: "0.08em", textTransform: "uppercase", padding: "0 8px 8px" }}>Contents</div>
        {SECTIONS.map(s => (
          <button
            key={s.id}
            onClick={() => setActive(s.id)}
            style={{
              display: "block", width: "100%", textAlign: "left", padding: "6px 10px", borderRadius: 5,
              border: "none", cursor: "pointer", fontSize: 12, transition: "all .1s",
              background: active === s.id ? J.amberGlow : "transparent",
              color: active === s.id ? J.amber : J.textSec,
              fontWeight: active === s.id ? 600 : 400,
            }}
          >
            {s.label}
          </button>
        ))}
      </aside>

      {/* Content */}
      <div style={{ flex: 1, overflowY: "auto", padding: "24px 32px" }}>

        {active === "overview" && (
          <>
            <DocSection title="Admin Reference">
              <P>This reference covers the admin-facing features of JARVIS: AI provider routing, user credits, usage tracking, rate limits, the kill switch, and access control. Use the sidebar to jump to any topic.</P>
              <Table
                headers={["Page", "Path", "What it controls"]}
                rows={[
                  ["Overview",        "/dashboard",           "Summary stats — users, sessions, recent events"],
                  ["AI Provider",     "/dashboard/provider",  "Provider config, model prices, kill switch, budgets"],
                  ["Usage",           "/dashboard/usage",     "Token/cost charts, per-user breakdown, credit top-up"],
                  ["Users",           "/dashboard/users",     "Create/edit users, set roles, assign limits"],
                  ["Groups",          "/dashboard/groups",    "Group membership — permissions inherit from groups"],
                  ["Permissions",     "/dashboard/permissions","Grant specific abilities beyond role defaults"],
                  ["Logs",            "/dashboard/logs",      "Full audit trail — filterable by user/event/date"],
                  ["Settings",        "/dashboard/settings",  "Voice engine, TTS/STT provider, HA + Proxmox config"],
                  ["Status",          "/dashboard/status",    "Live system health, store file sizes"],
                ]}
              />
            </DocSection>
          </>
        )}

        {active === "providers" && (
          <>
            <DocSection title="AI Providers">
              <P>JARVIS supports multiple LLM providers. The AI Router selects the best one for each request based on the priority order below.</P>
              <Table
                headers={["Provider", "Env var", "Notes"]}
                rows={[
                  ["OpenRouter",  "OPENROUTER_API_KEY",  "Recommended. Routes to Claude, GPT-4, Gemini, Mistral, etc. via one key."],
                  ["Anthropic",   "ANTHROPIC_API_KEY",   "Direct Claude access. Used when OpenRouter is not set."],
                  ["OpenAI",      "OPENAI_API_KEY",      "Direct GPT-4o. Fallback after Anthropic."],
                  ["Gemini",      "GEMINI_API_KEY",      "Also used for cloud STT. Fallback after OpenAI."],
                  ["Mistral",     "MISTRAL_API_KEY",     "Fallback for cheaper/faster requests."],
                  ["DeepSeek",    "DEEPSEEK_API_KEY",    "Cheapest fallback for cost-sensitive requests."],
                  ["Local",       "LOCAL_LLM_ENABLED=1", "Ollama / llama.cpp. Used when all cloud keys are absent."],
                ]}
              />
              <Note type="info">
                Set these in <Code>/etc/jarvis/jarvis.env</Code> and restart the service. Keys are never exposed to the frontend or logs.
              </Note>
              <H3>Checking active provider</H3>
              <P>After any chat message, the chat topbar shows a <b>Cloud</b> (blue) or <b>Local</b> (amber) badge reflecting which path the last response used.</P>
            </DocSection>
          </>
        )}

        {active === "routing" && (
          <>
            <DocSection title="Request Routing">
              <P>Every chat message goes through the AI Router before any LLM call is made. The router picks a provider and model, runs preflight checks, and falls back if something fails.</P>
              <H3>Provider priority order</H3>
              <Block>{`1. User BYOK key (if the user stored their own key for this provider)
2. System OpenRouter key (if OPENROUTER_API_KEY is set + openrouter_enabled)
3. Direct system keys (Anthropic → OpenAI → Gemini → Mistral → DeepSeek)
4. Local LLM (if LOCAL_LLM_ENABLED=1)
5. Offline fallback (static reply — no LLM call)`}</Block>
              <H3>Mode → model tier</H3>
              <Table
                headers={["Mode", "Tier selected", "Typical model"]}
                rows={[
                  ["auto-cheap",    "SIMPLE",   "Haiku / Gemini Flash / Mistral small"],
                  ["auto-balanced", "varies",   "Complexity classifier chooses SIMPLE or STANDARD"],
                  ["auto-best",     "COMPLEX",  "Opus / GPT-4o / Gemini Pro"],
                  ["specific",      "User pick", "Any model the user names, validated against allowed_models"],
                ]}
              />
              <H3>Preflight gates (checked before every call)</H3>
              <Block>{`1.  Kill switch enabled?               → hard stop
2.  Expensive models disabled?         → block expensive tier
3.  Per-user requests/min exceeded?    → rate limit error
4.  Per-user tokens/request clamp      → truncate prompt
5.  Per-user allowed_models list       → reject if not in list
6.  Per-user CHF/day exceeded?         → hard stop
7.  Per-user CHF/month exceeded?       → hard stop
8.  Expensive-model confirmation?      → confirmation dialog
9.  System global daily budget hit?    → hard stop
10. System global monthly budget hit?  → hard stop`}</Block>
              <Note type="warn">
                If the user has no credit balance and billing_mode is <Code>credit</Code>, a zero-balance check also runs before step 1.
              </Note>
            </DocSection>
          </>
        )}

        {active === "byok" && (
          <>
            <DocSection title="BYOK — Bring Your Own Key">
              <P>Users can store their own provider API keys in Settings → AI &amp; Billing. These keys are encrypted at rest using Fernet (AES-128-CBC) and the master key <Code>JARVIS_SECRET_KEY</Code>.</P>
              <H3>How encryption works</H3>
              <Table
                headers={["Property", "Detail"]}
                rows={[
                  ["Algorithm",        "Fernet (AES-128-CBC + HMAC-SHA256)"],
                  ["Master key env",   "JARVIS_SECRET_KEY — 32-byte URL-safe base64"],
                  ["On-disk format",   "fernet:v1:<base64-ciphertext>"],
                  ["Key masking",      "Only sk-…abcd shown in UI — never the full key"],
                  ["Backup exclusion", "BYOK store is excluded from /admin/backup exports — keys must be re-entered after restore"],
                ]}
              />
              <H3>Generating a master key</H3>
              <Block>{`python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`}</Block>
              <Note type="danger">
                If <Code>JARVIS_SECRET_KEY</Code> is rotated or lost, all stored BYOK keys become unreadable. Users will be prompted to re-enter their keys — JARVIS will not crash.
              </Note>
              <H3>Admin visibility</H3>
              <P>Admins can see which providers a user has a key stored for (via Users → Keys), but <b>cannot read the actual key</b>. Only the masked suffix is shown. This is by design.</P>
              <H3>BYOK vs system keys</H3>
              <P>A BYOK key always wins over the system key for that provider. If a user stores their own OpenAI key, their requests use that key instead of the system <Code>OPENAI_API_KEY</Code>. Usage is still logged against their user ID.</P>
            </DocSection>
          </>
        )}

        {active === "credits" && (
          <>
            <DocSection title="Credits & Billing">
              <P>JARVIS has an internal CHF credit system. Admins top up user balances; the router deducts the estimated cost of each cloud request.</P>
              <H3>Billing modes</H3>
              <Table
                headers={["Mode", "Who it applies to", "Behaviour"]}
                rows={[
                  ["system",  "All users by default",    "Requests billed against the shared system account — no per-user deduction"],
                  ["credit",  "Users with a CHF balance", "Balance is deducted before each request; request blocked if balance is 0"],
                  ["byok",    "Users with their own key", "No balance check — the user is paying their provider directly"],
                ]}
              />
              <H3>Topping up a user</H3>
              <P>Go to <b>Usage → Top-up</b>. Enter the user ID and CHF amount. The ledger records every topup and deduction with a timestamp and note.</P>
              <Note type="info">
                Cost is estimated before the call using the model price table (<b>AI Provider → Model Prices</b>). The exchange rate is set via <Code>usd_to_chf_rate</Code> in provider settings.
              </Note>
              <H3>Cost estimation formula</H3>
              <Block>{`cost_usd = (input_tokens / 1_000_000) × in_usd_per_1M
           + (output_tokens / 1_000_000) × out_usd_per_1M
cost_chf  = cost_usd × usd_to_chf_rate`}</Block>
              <P>Actual token counts are taken from the provider's response. If the provider does not return token counts, the estimate is used as-is.</P>
            </DocSection>
          </>
        )}

        {active === "limits" && (
          <>
            <DocSection title="Per-User Limits">
              <P>Each user can have spending and rate limits that override global budgets. Set them at <b>Users → Edit → Limits</b> or via <Code>PUT /admin/users/{"{id}"}/limits</Code>.</P>
              <Table
                headers={["Field", "Default", "Effect"]}
                rows={[
                  ["chf_per_day",           "0 (unlimited)", "Max CHF the user can spend in a rolling 24 h window"],
                  ["chf_per_month",         "0 (unlimited)", "Max CHF in a rolling 30-day window"],
                  ["tokens_per_request",    "0 (unlimited)", "Hard cap on prompt+response tokens per single request"],
                  ["requests_per_min",      "0 (unlimited)", "Rate limiter — rejects if exceeded"],
                  ["expensive_models_per_day", "0 (unlimited)", "How many expensive-tier requests allowed per day"],
                  ["allowed_models",        "[] (all)",      "Whitelist of model IDs this user may request; empty = any"],
                ]}
              />
              <Note type="info">
                A value of <Code>0</Code> means no limit is applied. Limits are checked per-user <i>after</i> global budget gates.
              </Note>
              <H3>Limits vs credits</H3>
              <P>Limits cap <i>how much</i> a user can spend in a window regardless of their balance. A user with CHF 100 credit but a <Code>chf_per_day=1</Code> limit is still capped at CHF 1/day.</P>
            </DocSection>
          </>
        )}

        {active === "usage" && (
          <>
            <DocSection title="Usage Tracking">
              <P>Every request (successful or failed) is appended to the usage log at <Code>JARVIS_USAGE_LOG_PATH</Code> (default <Code>/var/lib/jarvis/usage.log</Code>).</P>
              <H3>Usage log record schema</H3>
              <Block>{`{
  "ts":                  1718200000,    // Unix timestamp
  "user_id":             "usr-abc123",
  "conversation_id":     "sess-xyz",
  "provider":            "openrouter",
  "model":               "anthropic/claude-opus-4-8",
  "billing_mode":        "system",       // system | credit | byok
  "input_tokens":        412,
  "output_tokens":       89,
  "total_tokens":        501,
  "estimated_cost_usd":  0.00243,
  "estimated_cost_chf":  0.00219,
  "request_status":      "success",     // success | error | blocked
  "error":               null
}`}</Block>
              <H3>Usage page — what the numbers mean</H3>
              <Table
                headers={["Metric", "How it's computed"]}
                rows={[
                  ["Total requests",  "Count of all log records in the selected window"],
                  ["Total tokens",    "Sum of total_tokens across all records"],
                  ["Total cost (CHF)", "Sum of estimated_cost_chf"],
                  ["Daily chart",     "Bucketed by day — each bar = cost_chf for that day"],
                  ["Per-user table",  "Grouped by user_id — sorted by cost descending"],
                ]}
              />
              <Note type="warn">
                The usage log is append-only and is <b>excluded from backups</b> due to its size. Archive or rotate it externally if needed.
              </Note>
              <H3>Query parameters (API)</H3>
              <Block>{`GET /admin/usage?since_ts=<unix>&until_ts=<unix>&user_id=<id>&limit=500`}</Block>
            </DocSection>
          </>
        )}

        {active === "killswitch" && (
          <>
            <DocSection title="Kill Switch">
              <P>The kill switch is a single toggle that instantly blocks <b>all</b> cloud AI calls system-wide. It takes effect on the next request — no restart required.</P>
              <H3>Ways to activate</H3>
              <Table
                headers={["Method", "How"]}
                rows={[
                  ["Admin UI",  "AI Provider page → Kill Switch toggle → Save"],
                  ["Env var",   "Set JARVIS_EMERGENCY_STOP=1 in /etc/jarvis/jarvis.env and restart"],
                  ["API",       "PUT /admin/settings with { provider: { kill_switch: true } }"],
                ]}
              />
              <Note type="danger">
                When the kill switch is on, JARVIS returns an error to all chat requests that would hit a cloud provider. Skill-based responses (system status, time, weather, etc.) still work. The kill switch does <b>not</b> affect local LLM.
              </Note>
              <H3>Emergency stop vs kill switch</H3>
              <P><Code>JARVIS_EMERGENCY_STOP=1</Code> (env var) blocks all write actions system-wide including service restarts and HA actions — it is a broader safety net. The kill switch in Provider Settings only blocks cloud AI calls.</P>
            </DocSection>
          </>
        )}

        {active === "models" && (
          <>
            <DocSection title="Model Tiers & Prices">
              <P>JARVIS assigns every model to a tier. The router uses tiers to select the right model for the complexity of a request.</P>
              <Table
                headers={["Tier", "Use case", "Example models"]}
                rows={[
                  ["SIMPLE",   "Short factual answers, quick commands",      "claude-haiku-4-5, gemini-flash, mistral-small"],
                  ["STANDARD", "Normal conversation, code snippets",         "claude-sonnet-4-6, gpt-4o-mini, gemini-pro"],
                  ["COMPLEX",  "Long reasoning, multi-step plans, analysis", "claude-opus-4-8, gpt-4o, gemini-ultra"],
                ]}
              />
              <H3>Configuring model prices</H3>
              <P>Go to <b>AI Provider → Model Prices</b>. Add the model ID exactly as the provider uses it (e.g. <Code>anthropic/claude-opus-4-8</Code> for OpenRouter). Set:</P>
              <Table
                headers={["Field", "Unit", "Source"]}
                rows={[
                  ["in_usd_per_1M",  "USD per 1 million input tokens",  "Provider pricing page"],
                  ["out_usd_per_1M", "USD per 1 million output tokens", "Provider pricing page"],
                  ["tier",           "simple / standard / complex",      "Your judgment"],
                  ["expensive",      "true / false",                     "Flag high-cost models for confirmation flow"],
                ]}
              />
              <Note type="info">
                Prices are used for <i>estimation only</i> — the actual charge from the provider may differ slightly. Keep the table current to get accurate CHF cost reporting in Usage.
              </Note>
            </DocSection>
          </>
        )}

        {active === "rbac" && (
          <>
            <DocSection title="RBAC & Permissions">
              <P>Access control uses a four-role model with per-user and per-group permission grants on top.</P>
              <H3>Roles</H3>
              <Table
                headers={["Role", "Default abilities"]}
                rows={[
                  ["admin",           "Full access — all permissions granted by default"],
                  ["standard_user",   "Voice + chat only"],
                  ["guest_restricted","Voice only"],
                  ["service_system",  "No defaults — grant explicitly"],
                ]}
              />
              <H3>Key permissions</H3>
              <Table
                headers={["Permission", "What it unlocks"]}
                rows={[
                  ["assistant.chat",              "Can send chat messages"],
                  ["voice.use",                   "Can use the voice / orb screen"],
                  ["actions.write.execute",       "Service restart, Docker, Proxmox start/stop"],
                  ["actions.dangerous.execute",   "System shutdown, VM deletion"],
                  ["actions.dangerous.approve",   "Can approve confirmation dialogs"],
                  ["home_assistant.access",       "Read HA entities and device state"],
                  ["home_assistant.actions.write","Control HA devices"],
                  ["settings.manage",             "Edit admin settings"],
                  ["audit.read",                  "View audit log"],
                ]}
              />
              <H3>Effective permissions</H3>
              <P>A user's effective permissions = role defaults ∪ group grants ∪ user grants. Check the resolved set at <b>Permissions → Effective</b> or <Code>GET /admin/permissions/effective/{"{user_id}"}</Code>.</P>
            </DocSection>
          </>
        )}

        {active === "backup" && (
          <>
            <DocSection title="Backup & Restore">
              <P>JARVIS auto-backups all JSON data stores every 24 hours (configurable). Up to 7 rolling backups are kept at <Code>/var/lib/jarvis/auto_backups/</Code>.</P>
              <H3>Manual backup</H3>
              <Block>{`GET /admin/backup
# Returns a single JSON with backup_version:1 containing all store data`}</Block>
              <H3>Restore</H3>
              <Block>{`POST /admin/backup/restore
Content-Type: application/json
<paste backup JSON body>`}</Block>
              <Note type="warn">
                Restore is destructive — it replaces all current data. The service does not restart automatically; consider restarting after a restore to flush in-memory caches.
              </Note>
              <H3>What is included / excluded</H3>
              <Table
                headers={["Store", "Included?"]}
                rows={[
                  ["users.json",           "✓ Yes"],
                  ["groups.json",          "✓ Yes"],
                  ["memberships.json",     "✓ Yes"],
                  ["permissions.json",     "✓ Yes"],
                  ["admin_settings.json",  "✓ Yes"],
                  ["user_preferences.json","✓ Yes"],
                  ["credits.json",         "✓ Yes"],
                  ["user_limits.json",     "✓ Yes"],
                  ["byok.json",            "✗ No — re-enter keys after restore"],
                  ["usage.log",            "✗ No — high-volume append log"],
                  ["audit.log",            "✗ No — audit log is never modified"],
                  ["chat_history.db",      "✗ No — SQLite chat history not included"],
                ]}
              />
              <H3>Auto-backup settings</H3>
              <Table
                headers={["Env var", "Default", "Effect"]}
                rows={[
                  ["JARVIS_AUTO_BACKUP_DISABLED",        "0",  "Set to 1 to turn off auto-backup"],
                  ["JARVIS_AUTO_BACKUP_INTERVAL_HOURS",  "24", "How often to write a backup"],
                ]}
              />
            </DocSection>
          </>
        )}

      </div>
    </div>
  );
}
