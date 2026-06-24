import { useEffect, useState } from "react";

import { apiRequest, getSessionToken } from "./client";

export type HomeAssistantOverview = {
  policy: {
    first_admin_user_id: string | null;
    role: string;
    effective_permissions: string[];
    access_granted: boolean;
    access_reason: string;
    capability_groups: Record<string, string[]>;
    action_policies: Record<
      string,
      {
        capability: string;
        risk_level: string;
        requires_confirmation: boolean;
        remote_restricted: boolean;
      }
    >;
  };
  integration: {
    configured: boolean;
    base_url: string;
    mode: string;
    healthy: boolean;
    calendar_provider?: string;
    calendar_write_enabled?: boolean;
    inbox_provider?: string;
    inbox_write_enabled?: boolean;
  };
  security?: {
    confirmation_ttl_sec: number;
    remote_control_requires_capability: boolean;
    system_control_preapproved_only: boolean;
    remote_allowed_cidrs?: string[];
    pending_confirmations: number;
    expired_confirmations: number;
  };
  store: Record<string, unknown>;
  counts: {
    managed_entities: number;
    discovery_candidates: number;
    shopping_list_items: number;
    calendar_items: number;
    inbox_items: number;
    system_targets?: number;
    control_requests: number;
    deferred_provider_writes?: number;
  };
  areas: string[];
  shopping_lists: Array<{ id: string; name: string; open_items: number }>;
  calendar_items: HomeAssistantCalendarItem[];
  inbox_items: HomeAssistantInboxItem[];
  alerts: Array<{ level: string; code: string; message: string }>;
};

export type HomeAssistantDiscoveryCandidate = {
  id: string;
  source: string;
  ip_address: string;
  label: string;
  suggested_type: string;
  suggested_area: string;
  trust_level: string;
  risk_level: string;
  onboarding_status: string;
  approval_status: string;
  metadata?: Record<string, unknown>;
};

export type HomeAssistantManagedEntity = {
  source_candidate_id?: string;
  entity_id: string;
  label: string;
  kind: string;
  area: string;
  state?: string;
  available?: boolean;
  integration_source: string;
  control_mode: string;
  trust_level: string;
  risk_level: string;
  approval_status: string;
  onboarding_status: string;
  metadata?: Record<string, unknown>;
};

export type HomeAssistantShoppingListItem = {
  id: string;
  title: string;
  list_id: string;
  status: string;
  source: string;
  created_at: number;
  metadata?: Record<string, unknown>;
};

export type HomeAssistantCalendarItem = {
  id: string;
  title: string;
  starts_at: string;
  ends_at?: string;
  calendar_id: string;
  status: string;
  source: string;
  created_at: number;
  metadata?: Record<string, unknown>;
};

export type HomeAssistantInboxItem = {
  id: string;
  subject: string;
  from_label: string;
  status: string;
  received_at: number;
  source: string;
  summary?: string;
  metadata?: Record<string, unknown>;
};

export type HomeAssistantControlRequest = {
  id: string;
  entity_id: string;
  entity_label: string;
  action: string;
  value?: unknown;
  risk_level: string;
  required_capability: string;
  requires_confirmation: boolean;
  remote_restricted: boolean;
  status: string;
  requested_by?: string;
  created_at: number;
  confirmed_at?: number;
  denied_at?: number;
};

export type HomeAssistantHealth = {
  policy: HomeAssistantOverview["policy"];
  integration: HomeAssistantOverview["integration"];
  health: {
    managed_entities: number;
    unavailable_entities: number;
    pending_confirmations: number;
    automation_rules: number;
    deferred_provider_writes?: number;
    configured: boolean;
  };
  alerts: {
    unavailable_entities: HomeAssistantManagedEntity[];
    pending_requests: HomeAssistantControlRequest[];
  };
};

export type HomeAssistantAutomationRule = {
  id: string;
  name: string;
  description: string;
  trigger: string;
  target_area: string;
  action_summary: string;
  enabled: boolean;
  review_state: string;
  risk_level: string;
  created_at: number;
  updated_at: number;
};

export type HomeAssistantRecoveryPlaybook = {
  id: string;
  title: string;
  description: string;
  required_permission: string;
  risk_level: string;
};

export type HomeAssistantAreaSummary = {
  area: string;
  entity_count: number;
  unavailable_count: number;
  kinds: string[];
};

export type HomeAssistantSecurityPosture = {
  policy: HomeAssistantOverview["policy"];
  security: {
    confirmation_ttl_sec: number;
    remote_control_requires_capability: boolean;
    system_control_preapproved_only: boolean;
    remote_allowed_cidrs: string[];
    pending_confirmations: number;
    expired_confirmations: number;
  };
};

export type HomeAssistantDeviceProfiles = Record<
  string,
  {
    actions: Array<{ action: string; label: string; risk_level: string; remote: boolean }>;
  }
>;

export type HomeAssistantSystemTarget = {
  id: string;
  label: string;
  target_kind: string;
  host: string;
  area: string;
  allowed_actions: string[];
  status: string;
  risk_level: string;
  integration_source: string;
  metadata?: Record<string, unknown>;
};

export type HomeAssistantSystemTargetProfiles = Record<
  string,
  {
    actions: Array<{ action: string; label: string; risk_level: string; remote: boolean }>;
  }
>;

export type HomeAssistantLiveSnapshot = {
  type: "snapshot";
  areas: HomeAssistantAreaSummary[];
  entities: HomeAssistantManagedEntity[];
  automations: HomeAssistantAutomationRule[];
  sync: {
    configured?: boolean;
    synced_count?: number;
    total_entities?: number;
    timestamp?: number;
  };
};

function wsUrl(path: string) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${path}`;
}

export function fetchHomeAssistantOverview() {
  return apiRequest<HomeAssistantOverview>("/home-assistant/overview", { includeUser: true });
}

export function fetchHomeAssistantDeviceProfiles() {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; profiles: HomeAssistantDeviceProfiles }>(
    "/home-assistant/device-profiles",
    { includeUser: true },
  );
}

export function fetchHomeAssistantSystemTargetProfiles() {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; profiles: HomeAssistantSystemTargetProfiles }>(
    "/home-assistant/system-target-profiles",
    { includeUser: true },
  );
}

export function useHomeAssistantLiveSnapshot(enabled = true) {
  const [snapshot, setSnapshot] = useState<HomeAssistantLiveSnapshot | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const token = getSessionToken();
    if (!enabled || !token) return;

    let socket: WebSocket | null = null;
    let retryTimer: number | null = null;
    let closed = false;

    const connect = () => {
      socket = new WebSocket(wsUrl(`/ws/home-assistant?session=${encodeURIComponent(token)}`));
      socket.onopen = () => setConnected(true);
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as HomeAssistantLiveSnapshot;
          if (payload.type === "snapshot") setSnapshot(payload);
        } catch {
          // ignore malformed payloads
        }
      };
      socket.onclose = () => {
        setConnected(false);
        if (closed) return;
        retryTimer = window.setTimeout(connect, 2500);
      };
      socket.onerror = () => {
        socket?.close();
      };
    };

    connect();
    return () => {
      closed = true;
      setConnected(false);
      if (retryTimer) window.clearTimeout(retryTimer);
      socket?.close();
    };
  }, [enabled]);

  return { snapshot, connected };
}

export function fetchHomeAssistantAreas() {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; areas: HomeAssistantAreaSummary[] }>(
    "/home-assistant/areas",
    { includeUser: true },
  );
}

export function fetchHomeAssistantSecurityPosture() {
  return apiRequest<HomeAssistantSecurityPosture>("/home-assistant/security-posture", {
    includeUser: true,
  });
}

export function fetchHomeAssistantDiscoveryCandidates() {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; candidates: HomeAssistantDiscoveryCandidate[] }>(
    "/home-assistant/discovery/candidates",
    { includeUser: true },
  );
}

export function createHomeAssistantDiscoveryCandidate(body: {
  source?: string;
  ip_address: string;
  label: string;
  suggested_type: string;
  suggested_area?: string;
  metadata?: Record<string, unknown>;
}) {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; candidate: HomeAssistantDiscoveryCandidate }>(
    "/home-assistant/discovery/candidates",
    { method: "POST", includeUser: true, body },
  );
}

export function approveHomeAssistantDiscoveryCandidate(candidateId: string, body?: { entity_id?: string; label?: string; area?: string; kind?: string }) {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; candidate: HomeAssistantDiscoveryCandidate; entity: HomeAssistantManagedEntity }>(
    `/home-assistant/discovery/candidates/${candidateId}/approve`,
    { method: "POST", includeUser: true, body: body ?? {} },
  );
}

export function fetchHomeAssistantEntities() {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; entities: HomeAssistantManagedEntity[] }>(
    "/home-assistant/entities",
    { includeUser: true },
  );
}

export function fetchHomeAssistantSystemTargets() {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; targets: HomeAssistantSystemTarget[] }>(
    "/home-assistant/system-targets",
    { includeUser: true },
  );
}

export function createHomeAssistantSystemTarget(body: {
  label: string;
  target_kind: string;
  host?: string;
  area?: string;
  allowed_actions?: string[];
  risk_level?: string;
  metadata?: Record<string, unknown>;
}) {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; target: HomeAssistantSystemTarget }>(
    "/home-assistant/system-targets",
    { method: "POST", includeUser: true, body },
  );
}

export function syncHomeAssistantEntities() {
  return apiRequest<{
    policy: HomeAssistantOverview["policy"];
    entities: HomeAssistantManagedEntity[];
    sync: { configured: boolean; synced_count: number; total_entities: number; timestamp: number };
  }>("/home-assistant/sync/entities", { method: "POST", includeUser: true });
}

export function fetchHomeAssistantShoppingList() {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; items: HomeAssistantShoppingListItem[] }>(
    "/home-assistant/shopping-list",
    { includeUser: true },
  );
}

export function fetchHomeAssistantCalendar() {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; items: HomeAssistantCalendarItem[] }>(
    "/home-assistant/calendar",
    { includeUser: true },
  );
}

export function addHomeAssistantCalendarItem(body: {
  title: string;
  starts_at: string;
  ends_at?: string;
  calendar_id?: string;
  status?: string;
  source?: string;
  metadata?: Record<string, unknown>;
}) {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; item: HomeAssistantCalendarItem }>(
    "/home-assistant/calendar/items",
    { method: "POST", includeUser: true, body },
  );
}

export function syncHomeAssistantCalendar() {
  return apiRequest<{
    policy: HomeAssistantOverview["policy"];
    items: HomeAssistantCalendarItem[];
    sync: { provider: string; synced_count: number; timestamp: number };
  }>("/home-assistant/sync/calendar", { method: "POST", includeUser: true });
}

export function actOnHomeAssistantCalendarItem(
  itemId: string,
  body: { action: "mark_done" | "reschedule_plus_1d" },
) {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; item: HomeAssistantCalendarItem }>(
    `/home-assistant/calendar/items/${itemId}/actions`,
    { method: "POST", includeUser: true, body },
  );
}

export function fetchHomeAssistantInbox() {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; items: HomeAssistantInboxItem[] }>(
    "/home-assistant/inbox",
    { includeUser: true },
  );
}

export function addHomeAssistantInboxItem(body: {
  subject: string;
  from_label?: string;
  status?: string;
  received_at?: number;
  source?: string;
  summary?: string;
  metadata?: Record<string, unknown>;
}) {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; item: HomeAssistantInboxItem }>(
    "/home-assistant/inbox/items",
    { method: "POST", includeUser: true, body },
  );
}

export function syncHomeAssistantInbox() {
  return apiRequest<{
    policy: HomeAssistantOverview["policy"];
    items: HomeAssistantInboxItem[];
    sync: { provider: string; synced_count: number; timestamp: number };
  }>("/home-assistant/sync/inbox", { method: "POST", includeUser: true });
}

export function actOnHomeAssistantInboxItem(
  itemId: string,
  body: { action: "mark_read" | "archive" },
) {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; item: HomeAssistantInboxItem }>(
    `/home-assistant/inbox/items/${itemId}/actions`,
    { method: "POST", includeUser: true, body },
  );
}

export function fetchHomeAssistantControlRequests() {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; requests: HomeAssistantControlRequest[] }>(
    "/home-assistant/control-requests",
    { includeUser: true },
  );
}

export function fetchHomeAssistantHealth() {
  return apiRequest<HomeAssistantHealth>("/home-assistant/health", { includeUser: true });
}

export function fetchHomeAssistantAutomations() {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; automations: HomeAssistantAutomationRule[] }>(
    "/home-assistant/automations",
    { includeUser: true },
  );
}

export function fetchHomeAssistantRecoveryPlaybooks() {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; playbooks: HomeAssistantRecoveryPlaybook[] }>(
    "/home-assistant/recovery-playbooks",
    { includeUser: true },
  );
}

export function executeHomeAssistantRecoveryPlaybook(playbookId: string) {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; playbook: HomeAssistantRecoveryPlaybook; result: Record<string, unknown>; executed_at: number }>(
    `/home-assistant/recovery-playbooks/${playbookId}/execute`,
    { method: "POST", includeUser: true },
  );
}

export function createHomeAssistantAutomation(body: {
  name: string;
  description?: string;
  trigger?: string;
  target_area?: string;
  action_summary?: string;
  enabled?: boolean;
  review_state?: string;
  risk_level?: string;
  metadata?: Record<string, unknown>;
}) {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; automation: HomeAssistantAutomationRule }>(
    "/home-assistant/automations",
    { method: "POST", includeUser: true, body },
  );
}

export function toggleHomeAssistantAutomation(ruleId: string, body?: { enabled?: boolean }) {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; automation: HomeAssistantAutomationRule }>(
    `/home-assistant/automations/${ruleId}/toggle`,
    { method: "POST", includeUser: true, body: body ?? {} },
  );
}

export function requestHomeAssistantEntityAction(
  entityId: string,
  body: { action: string; value?: unknown; remote?: boolean },
) {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; request: HomeAssistantControlRequest; entity: HomeAssistantManagedEntity; executed: boolean }>(
    `/home-assistant/entities/${entityId}/actions`,
    { method: "POST", includeUser: true, body },
  );
}

export function requestHomeAssistantSystemTargetAction(
  targetId: string,
  body: { action: string; value?: unknown; remote?: boolean },
) {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; request: HomeAssistantControlRequest; target: HomeAssistantSystemTarget; executed: boolean }>(
    `/home-assistant/system-targets/${targetId}/actions`,
    { method: "POST", includeUser: true, body },
  );
}

export function confirmHomeAssistantControlRequest(requestId: string, body?: { confirmed?: boolean }) {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; request: HomeAssistantControlRequest; entity: HomeAssistantManagedEntity; executed: boolean }>(
    `/home-assistant/control-requests/${requestId}/confirm`,
    { method: "POST", includeUser: true, body: body ?? { confirmed: true } },
  );
}

export function addHomeAssistantShoppingListItem(body: { title: string; list_id?: string; source?: string; metadata?: Record<string, unknown> }) {
  return apiRequest<{ policy: HomeAssistantOverview["policy"]; item: HomeAssistantShoppingListItem }>(
    "/home-assistant/shopping-list/items",
    { method: "POST", includeUser: true, body },
  );
}

export function fetchHomeAssistantScenes() {
  return apiRequest<{ scenes: { id: string; name: string; entity_id: string; state: string | null }[] }>(
    "/home-assistant/scenes",
    { includeUser: true },
  );
}

export function activateHomeAssistantScene(sceneId: string) {
  return apiRequest<{ status: string; scene_id: string }>(
    `/home-assistant/scenes/${sceneId}/activate`,
    { method: "POST", includeUser: true },
  );
}
