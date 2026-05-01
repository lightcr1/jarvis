import { apiRequest } from "./client";

export type AdminUser = {
  id: string;
  username: string;
  role: string;
  enabled: boolean;
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

export type AdminSettings = {
  usage_limits: {
    token_ttl_min: number;
    max_active_tokens: number;
  };
  voice: {
    wakeword_enabled: boolean;
    wakeword_phrase: string;
    stt_provider: "local" | "gemini";
  };
  home_assistant: {
    confirmation_ttl_sec: number;
    remote_allowed_cidrs: string[];
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

export function fetchEffectivePermissions(userId: string) {
  return apiRequest<Record<string, unknown>>(`/admin/permissions/effective/${encodeURIComponent(userId)}`, { includeAdmin: true });
}

export function fetchAdminStatusSummary() {
  return apiRequest<AdminStatusSummary>("/admin/status/summary", { includeAdmin: true });
}

export function fetchAdminSettings() {
  return apiRequest<AdminSettingsPayload>("/admin/settings", { includeAdmin: true });
}

export function updateAdminSettings(settings: AdminSettings) {
  return apiRequest<AdminSettingsPayload>("/admin/settings", { method: "PUT", includeAdmin: true, body: settings });
}
