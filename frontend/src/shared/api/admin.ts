import { apiRequest, buildApiHeaders } from "./client";

export type AdminUser = {
  id: string;
  username: string;
  role: string;
  enabled: boolean;
  active_session?: boolean;
  session_expires_at?: number | null;
  last_seen_at?: number | null;
};

export type AdminGroup = {
  id: string;
  name: string;
  description?: string;
};

export type AdminMembership = {
  user_id: string;
  group_id: string;
};

export type AdminAuditEvent = {
  ts: number;
  event: string;
  actor_role?: string;
  role?: string;
  actor_user_id?: string;
  payload?: Record<string, unknown>;
};

export type AdminPermissionMap = {
  known_permissions: string[];
  group_permissions: Record<string, string[]>;
  user_permissions: Record<string, string[]>;
};

export type AdminStatusSummary = {
  counts: Record<string, number | boolean | string>;
  orphans: Record<string, unknown>;
  settings: Record<string, unknown>;
};

export type ModelPrice = {
  in_usd_per_1k: number;
  out_usd_per_1k: number;
  tier: string;
  expensive: boolean;
};

export type AdminSettings = {
  usage_limits: {
    token_ttl_min: number;
    max_active_tokens: number;
  };
  voice: {
    wakeword_enabled: boolean;
    wakeword_phrase: string;
    wakeword_engine: "software" | "openwakeword" | "none";
    wakeword_sensitivity: number;
    stt_provider: "local" | "gemini";
  };
  home_assistant: {
    confirmation_ttl_sec: number;
    remote_allowed_cidrs: string[];
  };
  files?: {
    default_storage_quota_mb: number;
    overage_price_chf_per_gb_month: number;
  };
  provider?: {
    default_provider: string;
    openrouter_enabled: boolean;
    usd_to_chf_rate: number;
    kill_switch: boolean;
    disable_expensive_models: boolean;
    expensive_threshold_chf: number;
    global_daily_budget_chf: number;
    global_monthly_budget_chf: number;
    model_prices: Record<string, ModelPrice>;
  };
};

export type AdminSettingsPayload = {
  settings: AdminSettings;
  effective: Record<string, unknown>;
};

export function fetchAdminUsers() {
  return apiRequest<{ users: AdminUser[] }>("/admin/users", { includeAdmin: true });
}

export function createAdminUser(body: { username: string; role: string; enabled: boolean; password?: string }) {
  return apiRequest<AdminUser>("/admin/users", { method: "POST", includeAdmin: true, body });
}

export function updateAdminUser(userId: string, body: { role?: string; enabled?: boolean }) {
  return apiRequest<AdminUser>(`/admin/users/${encodeURIComponent(userId)}`, { method: "PATCH", includeAdmin: true, body });
}

export function setAdminUserPassword(userId: string, password: string) {
  return apiRequest<{ ok: boolean; id: string }>(`/admin/users/${encodeURIComponent(userId)}/password`, {
    method: "PUT",
    includeAdmin: true,
    body: { password },
  });
}

export function deleteAdminUser(userId: string) {
  return apiRequest<{ ok: boolean; id: string }>(`/admin/users/${encodeURIComponent(userId)}`, { method: "DELETE", includeAdmin: true });
}

export function deleteAdminUserConversations(userId: string) {
  return apiRequest<{ ok: boolean; deleted: number }>(`/admin/users/${encodeURIComponent(userId)}/conversations`, { method: "DELETE", includeAdmin: true });
}

export type AdminUserLimits = {
  chf_per_day: number;
  chf_per_month: number;
  tokens_per_request: number;
  requests_per_min: number;
  expensive_models_per_day: number;
  allowed_models: string[];
  storage_quota_mb: number;
  updated_at: number;
};

export function updateAdminUserLimits(userId: string, body: Partial<Pick<AdminUserLimits, "storage_quota_mb" | "chf_per_day" | "chf_per_month" | "requests_per_min">>) {
  return apiRequest<AdminUserLimits>(`/admin/users/${encodeURIComponent(userId)}/limits`, { method: "PUT", includeAdmin: true, body });
}

export function fetchAdminGroups() {
  return apiRequest<{ groups: AdminGroup[] }>("/admin/groups", { includeAdmin: true });
}

export function createAdminGroup(body: { name: string; description?: string }) {
  return apiRequest<AdminGroup>("/admin/groups", { method: "POST", includeAdmin: true, body });
}

export function deleteAdminGroup(groupId: string) {
  return apiRequest<{ ok: boolean; id: string }>(`/admin/groups/${encodeURIComponent(groupId)}`, { method: "DELETE", includeAdmin: true });
}

export function fetchAdminAssignments() {
  return apiRequest<{ memberships: AdminMembership[] }>("/admin/assignments", { includeAdmin: true });
}

export function createAdminAssignment(body: AdminMembership) {
  return apiRequest<AdminMembership>("/admin/assignments", { method: "POST", includeAdmin: true, body });
}

export function deleteAdminAssignment(userId: string, groupId: string) {
  return apiRequest<{ ok: boolean; user_id: string; group_id: string }>(
    `/admin/assignments?user_id=${encodeURIComponent(userId)}&group_id=${encodeURIComponent(groupId)}`,
    { method: "DELETE", includeAdmin: true },
  );
}

export function fetchAdminAuditCounts(query = "") {
  return apiRequest<{ counts: Record<string, number> }>(`/admin/audit/counts${query}`, { includeAdmin: true });
}

export function fetchAdminAuditEvents(query = "") {
  return apiRequest<{ events: AdminAuditEvent[] }>(`/admin/audit/events${query}`, { includeAdmin: true });
}

export function fetchAdminPermissions() {
  return apiRequest<AdminPermissionMap>("/admin/permissions", { includeAdmin: true });
}

export function updateAdminPermissions(scope: "users" | "groups", target: string, permissions: string[]) {
  return apiRequest<{ permissions: string[] }>(`/admin/permissions/${scope}/${encodeURIComponent(target)}`, {
    method: "PUT",
    includeAdmin: true,
    body: { permissions },
  });
}

export type EffectivePermissionContext = {
  role: string;
  user_id: string | null;
  role_permissions: string[];
  user_permissions: string[];
  group_ids: string[];
  group_permissions: Record<string, string[]>;
  effective_permissions: string[];
};

export type EffectivePermissionsResponse = {
  user: AdminUser;
  permissions: EffectivePermissionContext;
};

export function fetchEffectivePermissions(userId: string) {
  return apiRequest<EffectivePermissionsResponse>(`/admin/permissions/effective/${encodeURIComponent(userId)}`, { includeAdmin: true });
}

export type AdminSession = {
  user_id: string;
  username: string;
  role: string;
  expires_at: number;
  expires_in_sec: number;
};

export function fetchAdminStatusSummary() {
  return apiRequest<AdminStatusSummary>("/admin/status/summary", { includeAdmin: true });
}

export function fetchAdminSessions() {
  return apiRequest<{ sessions: AdminSession[]; count: number }>("/admin/sessions", { includeAdmin: true });
}

export function revokeAdminSession(userId: string) {
  return apiRequest<{ ok: boolean; revoked: number; user_id: string }>(
    `/admin/sessions/${encodeURIComponent(userId)}`,
    { method: "DELETE", includeAdmin: true },
  );
}

export function fetchAdminSettings() {
  return apiRequest<AdminSettingsPayload>("/admin/settings", { includeAdmin: true });
}

export function updateAdminSettings(settings: AdminSettings) {
  return apiRequest<AdminSettingsPayload>("/admin/settings", { method: "PUT", includeAdmin: true, body: settings });
}

export async function downloadAdminBackup(): Promise<void> {
  const headers = buildApiHeaders({ includeAdmin: true });
  const res = await fetch("/admin/backup", { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const disposition = res.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match ? match[1] : "jarvis_backup.json";
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

export async function restoreAdminBackup(payload: Record<string, unknown>) {
  return apiRequest<{ ok: boolean; restored: Record<string, number> }>("/admin/backup/restore", {
    method: "POST",
    includeAdmin: true,
    body: payload,
  });
}

// ---------------------------------------------------------------------------
// Policies & Playbooks
// ---------------------------------------------------------------------------

export type PolicyCondition = {
  metric: string;
  comparator: "above" | "below" | "equals" | "contains";
  threshold: number | string;
  duration_sec: number;
};

export type PolicyAction = {
  type: string;
  params: Record<string, unknown>;
};

export type AdminPolicy = {
  id: string;
  name: string;
  domain: string;
  condition: PolicyCondition;
  action: PolicyAction;
  enabled: boolean;
  dry_run: boolean;
  cooldown_sec: number;
  last_fired_at: number | null;
  created_at: number;
};

export type PolicyEvent = {
  type: string;
  event_id: string;
  policy_id: string;
  policy_name: string;
  domain: string;
  severity: string;
  current_value: number | string;
  message: string;
  timestamp: number;
};

export type AdminPlaybookStepInput = {
  step_id?: string;
  description?: string;
  action: PolicyAction;
  requires_confirmation?: boolean;
};

export type AdminPlaybookStep = {
  step_id: string;
  description: string;
  action: PolicyAction;
  requires_confirmation: boolean;
};

export type AdminPlaybook = {
  id: string;
  name: string;
  description: string;
  dry_run: boolean;
  steps: AdminPlaybookStep[];
  created_at: number;
};

export type PlaybookRunStep = {
  step_id: string;
  status: "pending" | "running" | "succeeded" | "failed" | "skipped" | "would_execute";
  started_at: number | null;
  finished_at: number | null;
  output: Record<string, unknown> | null;
  error: string | null;
};

export type PlaybookRun = {
  id: string;
  playbook_id: string;
  playbook_name: string;
  dry_run: boolean;
  status: "running" | "completed" | "failed" | "awaiting_confirmation" | "cancelled";
  started_at: number;
  finished_at: number | null;
  steps: PlaybookRunStep[];
};

export function fetchAdminPolicies() {
  return apiRequest<{ policies: AdminPolicy[] }>("/admin/policies", { includeAdmin: true });
}

export function createAdminPolicy(body: {
  name: string;
  domain?: string;
  condition: PolicyCondition;
  action: PolicyAction;
  enabled?: boolean;
  dry_run?: boolean;
  cooldown_sec?: number;
}) {
  return apiRequest<{ policy: AdminPolicy }>("/admin/policies", { method: "POST", includeAdmin: true, body });
}

export function updateAdminPolicy(policyId: string, patch: Partial<{
  name: string;
  domain: string;
  condition: PolicyCondition;
  action: PolicyAction;
  enabled: boolean;
  dry_run: boolean;
  cooldown_sec: number;
}>) {
  return apiRequest<{ policy: AdminPolicy }>(`/admin/policies/${encodeURIComponent(policyId)}`, {
    method: "PATCH",
    includeAdmin: true,
    body: patch,
  });
}

export function deleteAdminPolicy(policyId: string) {
  return apiRequest<{ ok: boolean; id: string }>(`/admin/policies/${encodeURIComponent(policyId)}`, { method: "DELETE", includeAdmin: true });
}

export function testAdminPolicy(policyId: string) {
  return apiRequest<{ ok: boolean; event: PolicyEvent; escalated: boolean }>(`/admin/policies/${encodeURIComponent(policyId)}/test`, {
    method: "POST",
    includeAdmin: true,
  });
}

export function fetchAdminPolicyHistory(limit = 100) {
  return apiRequest<{ events: PolicyEvent[] }>(`/admin/policies/history?limit=${limit}`, { includeAdmin: true });
}

export function fetchAdminPlaybooks() {
  return apiRequest<{ playbooks: AdminPlaybook[] }>("/admin/playbooks", { includeAdmin: true });
}

export function createAdminPlaybook(body: {
  name: string;
  description?: string;
  dry_run?: boolean;
  steps?: AdminPlaybookStepInput[];
}) {
  return apiRequest<{ playbook: AdminPlaybook }>("/admin/playbooks", { method: "POST", includeAdmin: true, body });
}

export function updateAdminPlaybook(playbookId: string, patch: Partial<{
  name: string;
  description: string;
  dry_run: boolean;
  steps: AdminPlaybookStepInput[];
}>) {
  return apiRequest<{ playbook: AdminPlaybook }>(`/admin/playbooks/${encodeURIComponent(playbookId)}`, {
    method: "PATCH",
    includeAdmin: true,
    body: patch,
  });
}

export function deleteAdminPlaybook(playbookId: string) {
  return apiRequest<{ ok: boolean; id: string }>(`/admin/playbooks/${encodeURIComponent(playbookId)}`, { method: "DELETE", includeAdmin: true });
}

export function executeAdminPlaybook(playbookId: string, dryRun?: boolean) {
  const query = dryRun === undefined ? "" : `?dry_run=${dryRun ? "true" : "false"}`;
  return apiRequest<{ run: PlaybookRun }>(`/admin/playbooks/${encodeURIComponent(playbookId)}/execute${query}`, {
    method: "POST",
    includeAdmin: true,
  });
}

export function resumeAdminPlaybookRun(runId: string, confirm = true) {
  return apiRequest<{ run: PlaybookRun }>(`/admin/playbooks/runs/${encodeURIComponent(runId)}/resume?confirm=${confirm ? "true" : "false"}`, {
    method: "POST",
    includeAdmin: true,
  });
}

export function fetchAdminPlaybookRuns(playbookId: string) {
  return apiRequest<{ runs: PlaybookRun[] }>(`/admin/playbooks/${encodeURIComponent(playbookId)}/runs`, { includeAdmin: true });
}

export function fetchAdminPlaybookRun(runId: string) {
  return apiRequest<{ run: PlaybookRun }>(`/admin/playbooks/runs/${encodeURIComponent(runId)}`, { includeAdmin: true });
}

export type AdminIntegrationStatusEntry = {
  user_id: string;
  username?: string;
  field_names: string[];
  updated_at: number;
};

export type AdminIntegrationsStatus = {
  calendar: AdminIntegrationStatusEntry[];
  email: AdminIntegrationStatusEntry[];
};

export function fetchAdminIntegrationsStatus() {
  return apiRequest<AdminIntegrationsStatus>("/admin/integrations/status", { includeAdmin: true });
}

export type HomeAssistantCredentialsStatus = {
  configured: boolean;
  custom: boolean;
  base_url: string;
  token_hint: string;
  updated_at: number | null;
};

export function fetchHomeAssistantCredentials() {
  return apiRequest<HomeAssistantCredentialsStatus>("/admin/integrations/home-assistant", { includeAdmin: true });
}

export function setHomeAssistantCredentials(base_url: string, api_token: string) {
  return apiRequest<{ configured: boolean; base_url: string }>("/admin/integrations/home-assistant", {
    method: "PUT",
    includeAdmin: true,
    body: { base_url, api_token },
  });
}

export function clearHomeAssistantCredentials() {
  return apiRequest<{ configured: boolean }>("/admin/integrations/home-assistant", {
    method: "DELETE",
    includeAdmin: true,
  });
}

export function testHomeAssistantConnection() {
  return apiRequest<{ ok: boolean }>("/admin/integrations/home-assistant/test", {
    method: "POST",
    includeAdmin: true,
  });
}

export interface AutonomyStatus {
  enabled: boolean;
  updated_at?: string;
  note?: string;
  max_gpu_hours_per_day?: number | null;
  allowed_windows?: string[];
  max_rounds_per_pod_session?: number | null;
}

export interface AutonomyPolicyInput {
  max_gpu_hours_per_day?: number;
  allowed_windows?: string[];
  max_rounds_per_pod_session?: number;
}

export function fetchAutonomyStatus() {
  return apiRequest<{ status: AutonomyStatus }>("/autonomy", { includeAdmin: true });
}

export function updateAutonomyStatus(enabled: boolean, note: string, policy?: AutonomyPolicyInput) {
  return apiRequest<{ status: AutonomyStatus }>("/autonomy", {
    method: "PUT",
    includeAdmin: true,
    body: { enabled, note, ...(policy ?? {}) },
  });
}

export interface AgentIdea {
  id: string;
  source: "agent" | "owner";
  kind: string;
  title: string;
  summary: string;
  benefit: string;
  risks: string;
  next_step: string;
  status: string;
  created_at: number;
}

export function fetchAgentIdeas() {
  return apiRequest<{ ideas: AgentIdea[] }>("/admin/ideas", { includeAdmin: true });
}

export function submitOwnerIdea(kind: string, title: string, summary: string) {
  return apiRequest<{ idea: AgentIdea }>("/admin/ideas", {
    method: "POST", includeAdmin: true, body: { kind, title, summary },
  });
}

export function reviewAgentIdea(id: string, status: "shortlisted" | "dismissed") {
  return apiRequest<{ idea: AgentIdea }>(`/admin/ideas/${encodeURIComponent(id)}/review`, {
    method: "POST", includeAdmin: true, body: { status },
  });
}

export interface AgentProject {
  id: string; kind: string; target: string; title: string; operations: string;
  status: string; created_at: number; expires_at: number;
}
export function fetchAgentProjects() { return apiRequest<{ projects: AgentProject[] }>("/admin/agent-projects", { includeAdmin: true }); }
export function decideAgentProject(id: string, approve: boolean) {
  return apiRequest<{ project: AgentProject }>(`/admin/agent-projects/${encodeURIComponent(id)}/decide`, { method: "POST", includeAdmin: true, body: { approve } });
}
export function revokeAgentProject(id: string) {
  return apiRequest<{ project: AgentProject }>(`/admin/agent-projects/${encodeURIComponent(id)}/revoke`, { method: "POST", includeAdmin: true });
}

export interface AgentOneTimeAction {
  id: string; kind: string; target: string; payload: string; digest: string;
  status: string; created_at: number; expires_at: number;
}
export function fetchAgentActions() {
  return apiRequest<{ actions: AgentOneTimeAction[] }>("/admin/agent-actions", { includeAdmin: true });
}
export function decideAgentAction(id: string, approve: boolean) {
  return apiRequest<{ action: AgentOneTimeAction }>(`/admin/agent-actions/${encodeURIComponent(id)}/decide`, {
    method: "POST", includeAdmin: true, body: { approve },
  });
}

export interface AgentGrantRequest {
  id: string;
  kind: string;
  target: string;
  operation: string;
  reason: string;
  status: string;
  created_at: number;
  expires_at: number;
  decided_by: string | null;
}

export function fetchAgentGrants() {
  return apiRequest<{ requests: AgentGrantRequest[] }>("/admin/agent-grants", { includeAdmin: true });
}

export function decideAgentGrant(id: string, approve: boolean) {
  return apiRequest<{ request: AgentGrantRequest }>(`/admin/agent-grants/${encodeURIComponent(id)}/decide`, {
    method: "POST", includeAdmin: true, body: { approve },
  });
}

export function revokeAgentGrant(id: string) {
  return apiRequest<{ request: AgentGrantRequest }>(`/admin/agent-grants/${encodeURIComponent(id)}/revoke`, {
    method: "POST", includeAdmin: true,
  });
}

export interface AgentSession {
  id: string;
  title: string;
  status: string;
  kind?: string;        // 'autonomy' | 'unspecified' | ...
  focus?: string;       // 'engineering' | 'ideas' (aus Loop-Tags)
  updated_at?: string;
  selected_agent?: string;
  branch?: string;
}

export function agentSessionAction(convId: string, action: "pause" | "run" | "interrupt") {
  return apiRequest<{ ok: boolean; action: string }>(
    `/agent/sessions/${encodeURIComponent(convId)}/${action}`,
    { method: "POST", includeAdmin: true },
  );
}

export interface OwnerRequest {
  number: number;
  title: string;
  created_at?: string;
  labels: string[];
  url?: string;
}

export function fetchAgentSessions() {
  return apiRequest<{ sessions: AgentSession[]; count: number }>("/agent/sessions", { includeAdmin: true });
}

export function fetchOwnerRequests() {
  return apiRequest<{ requests: OwnerRequest[]; readonly: boolean; error?: string }>("/agent/requests", { includeAdmin: true });
}

export function decideOwnerRequest(number: number, decision: "approved" | "rejected") {
  return apiRequest<{ ok: boolean; number: number; decision: string }>(
    `/agent/requests/${number}/decide`,
    { method: "POST", includeAdmin: true, body: { number, decision } },
  );
}

export interface LoopVersion {
  repo_sha256?: string | null;
  installed_sha256?: string | null;
  drift?: boolean;
  source?: string;
}

export function fetchLoopVersion() {
  return apiRequest<LoopVersion>("/agent/loop-version", { includeAdmin: true });
}

export interface AgentPatch {
  id: string;
  repository: string;
  branch: string;
  base: string;
  commit?: string;
  message: string;
  paths: string[];
  status: string;
  pr_number?: number | null;
  created_at?: number;
  patch?: string;
}

export function fetchAgentPatches() {
  return apiRequest<{ patches: AgentPatch[] }>("/admin/agent-patches", { includeAdmin: true });
}

export function fetchAgentPatch(id: string) {
  return apiRequest<{ patch: AgentPatch }>(
    `/admin/agent-patches/${encodeURIComponent(id)}`, { includeAdmin: true });
}

export function decideAgentPatch(id: string, approve: boolean, title?: string) {
  return apiRequest<{ patch: AgentPatch; pr?: { number: number; url: string } }>(
    `/admin/agent-patches/${encodeURIComponent(id)}/decide`,
    { method: "POST", includeAdmin: true, body: { approve, title } },
  );
}

export interface RoundMetric {
  round_id: string;
  task_id?: string | null;
  gpu_seconds: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_estimate: number;
  status: string;
}

export interface RoundMetricsAggregate {
  rounds: number;
  gpu_hours: number;
  total_tokens: number;
  submitted: number;
  cost_estimate: number;
  tokens_per_submitted?: number | null;
  patches_per_gpu_hour?: number | null;
}

export function fetchRoundMetrics() {
  return apiRequest<{ aggregate: RoundMetricsAggregate; metrics: RoundMetric[] }>(
    "/admin/autonomy/round-metrics", { includeAdmin: true });
}
