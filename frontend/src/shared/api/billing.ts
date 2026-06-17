import { apiRequest } from "./client";

export type BillingInfo = {
  user_id: string;
  balance_chf: number;
  limits: Record<string, unknown>;
  recent_usage: unknown[];
};

export type ByokKey = {
  provider: string;
  masked: string;
  label?: string;
  created_at: number;
};

export type CreditLedgerEntry = {
  id: string;
  type: string;
  amount_chf: number;
  balance_after: number;
  note: string;
  created_at: number;
};

export type UsageSummary = {
  aggregate: Record<string, number>;
  daily_buckets: Array<{ bucket_ts: number; cost_chf: number; requests: number }>;
  recent: unknown[];
};

export function fetchMyBilling(): Promise<BillingInfo> {
  return apiRequest<BillingInfo>("/auth/me/billing", { includeUser: true });
}

export function fetchMyByokKeys(): Promise<{ keys: ByokKey[] }> {
  return apiRequest<{ keys: ByokKey[] }>("/auth/me/keys", { includeUser: true });
}

export function setByokKey(provider: string, api_key: string): Promise<{ ok: boolean; key: ByokKey }> {
  return apiRequest<{ ok: boolean; key: ByokKey }>(`/auth/me/keys/${encodeURIComponent(provider)}`, {
    method: "PUT",
    includeUser: true,
    body: { api_key },
  });
}

export function deleteByokKey(provider: string): Promise<{ ok: boolean }> {
  return apiRequest<{ ok: boolean }>(`/auth/me/keys/${encodeURIComponent(provider)}`, {
    method: "DELETE",
    includeUser: true,
  });
}

// admin

export function adminTopUp(
  user_id: string,
  amount_chf: number,
  note?: string,
): Promise<{ ok: boolean; entry: CreditLedgerEntry }> {
  return apiRequest<{ ok: boolean; entry: CreditLedgerEntry }>("/admin/credits/topup", {
    method: "POST",
    includeAdmin: true,
    body: { user_id, amount_chf, note: note ?? "" },
  });
}

export function fetchAdminCredits(
  user_id: string,
): Promise<{ user_id: string; balance_chf: number; ledger: CreditLedgerEntry[] }> {
  return apiRequest<{ user_id: string; balance_chf: number; ledger: CreditLedgerEntry[] }>(
    `/admin/credits/${encodeURIComponent(user_id)}`,
    { includeAdmin: true },
  );
}

export function updateUserLimits(
  user_id: string,
  limits: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  return apiRequest<Record<string, unknown>>(`/admin/users/${encodeURIComponent(user_id)}/limits`, {
    method: "PUT",
    includeAdmin: true,
    body: limits,
  });
}

export function fetchAdminUsage(params?: {
  user_id?: string;
  provider?: string;
  days?: number;
}): Promise<UsageSummary> {
  const qs = new URLSearchParams();
  if (params?.user_id) qs.set("user_id", params.user_id);
  if (params?.provider) qs.set("provider", params.provider);
  if (params?.days != null) qs.set("days", String(params.days));
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return apiRequest<UsageSummary>(`/admin/usage${query}`, { includeAdmin: true });
}
