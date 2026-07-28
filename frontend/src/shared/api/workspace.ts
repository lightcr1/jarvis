import { apiRequest } from "./client";

export type WorkspaceOsType = "windows" | "linux";
export type WorkspaceProtocol = "rdp" | "vnc";

export type WorkspaceTarget = {
  id: string;
  name: string;
  os_type: WorkspaceOsType;
  protocol: WorkspaceProtocol;
  tailscale_host: string;
  port: number;
  wol_relay_host: string | null;
  wol_mac: string | null;
  created_at: number;
  updated_at: number;
};

export type WorkspacePolicy = {
  role: string;
  effective_permissions: string[];
};

export type WorkspaceCredentialsStatus = {
  configured: boolean;
  field_names: string[];
  updated_at: number | null;
};

export type WorkspaceConnectResponse = {
  policy: WorkspacePolicy;
  url: string;
  token: string;
  expires_at: number;
};

export type WorkspaceWakeResponse = {
  policy: WorkspacePolicy;
  status: string;
  relay_host: string;
  magic_packet_hex: string;
  detail: string;
};

export function fetchWorkspaceTargets() {
  return apiRequest<{ policy: WorkspacePolicy; targets: WorkspaceTarget[] }>("/workspace/targets", { includeUser: true });
}

export function createWorkspaceTarget(body: {
  name: string;
  os_type: WorkspaceOsType;
  protocol: WorkspaceProtocol;
  tailscale_host: string;
  port?: number;
  wol_relay_host?: string;
  wol_mac?: string;
}) {
  return apiRequest<{ policy: WorkspacePolicy; target: WorkspaceTarget }>("/workspace/targets", { method: "POST", includeUser: true, body });
}

export function updateWorkspaceTarget(
  targetId: string,
  body: Partial<{
    name: string;
    os_type: WorkspaceOsType;
    protocol: WorkspaceProtocol;
    tailscale_host: string;
    port: number;
    wol_relay_host: string | null;
    wol_mac: string | null;
  }>,
) {
  return apiRequest<{ policy: WorkspacePolicy; target: WorkspaceTarget }>(`/workspace/targets/${encodeURIComponent(targetId)}`, {
    method: "PATCH", includeUser: true, body,
  });
}

export function deleteWorkspaceTarget(targetId: string) {
  return apiRequest<{ policy: WorkspacePolicy; deleted: boolean }>(`/workspace/targets/${encodeURIComponent(targetId)}`, {
    method: "DELETE", includeUser: true,
  });
}

export function fetchWorkspaceCredentialsStatus(targetId: string) {
  return apiRequest<{ policy: WorkspacePolicy; status: WorkspaceCredentialsStatus }>(
    `/workspace/targets/${encodeURIComponent(targetId)}/credentials/status`, { includeUser: true },
  );
}

export function setWorkspaceCredentials(targetId: string, body: { username?: string; password: string }) {
  return apiRequest<{ policy: WorkspacePolicy; credentials: { integration: string; field_names: string[]; updated_at: number } }>(
    `/workspace/targets/${encodeURIComponent(targetId)}/credentials`, { method: "PUT", includeUser: true, body },
  );
}

export function deleteWorkspaceCredentials(targetId: string) {
  return apiRequest<{ policy: WorkspacePolicy; deleted: boolean }>(
    `/workspace/targets/${encodeURIComponent(targetId)}/credentials`, { method: "DELETE", includeUser: true },
  );
}

export function connectWorkspaceTarget(targetId: string) {
  return apiRequest<WorkspaceConnectResponse>(`/workspace/targets/${encodeURIComponent(targetId)}/connect`, {
    method: "POST", includeUser: true,
  });
}

export function wakeWorkspaceTarget(targetId: string) {
  return apiRequest<WorkspaceWakeResponse>(`/workspace/targets/${encodeURIComponent(targetId)}/wake`, {
    method: "POST", includeUser: true,
  });
}
