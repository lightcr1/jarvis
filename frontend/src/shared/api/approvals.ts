import { apiRequest } from "./client";

export interface ApprovalRequest {
  id: string;
  capability: string;
  target: string;
  tier: string;
  params: string;
  digest: string;
  reason: string;
  expires_at: number;
}

export function fetchApprovals() {
  return apiRequest<{ requests: ApprovalRequest[] }>("/admin/approval-requests", { includeAdmin: true });
}

export function decideApproval(id: string, approve: boolean, totp?: string) {
  return apiRequest(`/admin/approval-requests/${encodeURIComponent(id)}/decide`, {
    method: "POST", includeAdmin: true, body: { approve, totp },
  });
}

export function fetchTwoFactorStatus() {
  return apiRequest<{ enabled: boolean; pending: boolean }>("/admin/2fa", { includeAdmin: true });
}

export function enrollTwoFactor() {
  return apiRequest<{ secret: string; otpauth_uri: string }>("/admin/2fa/enroll", {
    method: "POST", includeAdmin: true,
  });
}

export function activateTwoFactor(code: string) {
  return apiRequest("/admin/2fa/activate", { method: "POST", includeAdmin: true, body: { code } });
}
