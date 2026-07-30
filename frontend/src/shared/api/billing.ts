import { apiRequest } from "./client";

export type Plan = {
  id: string;
  name: string;
  price_chf_per_month: number;
  ai_credit_chf_monthly: number;
  storage_gb_included: number;
  sort_order: number;
};

export type PlanCreate = Omit<Plan, "id">;
export type PlanUpdate = Partial<PlanCreate>;

export type BillingInfo = {
  user_id: string;
  balance_chf: number;
  limits: Record<string, unknown>;
  recent_usage: unknown[];
  plan: Plan | null;
  plans: Plan[];
  storage: {
    used_bytes: number;
    quota_bytes: number;
    overage_price_chf_per_gb_month: number;
    estimated_overage_chf: number;
  };
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

export function fetchAdminPlans(): Promise<{ plans: Plan[] }> {
  return apiRequest<{ plans: Plan[] }>("/admin/plans", { includeAdmin: true });
}

export function createAdminPlan(body: PlanCreate): Promise<{ plan: Plan }> {
  return apiRequest<{ plan: Plan }>("/admin/plans", { method: "POST", includeAdmin: true, body });
}

export function updateAdminPlan(planId: string, body: PlanUpdate): Promise<{ plan: Plan }> {
  return apiRequest<{ plan: Plan }>(`/admin/plans/${encodeURIComponent(planId)}`, {
    method: "PATCH",
    includeAdmin: true,
    body,
  });
}

export function deleteAdminPlan(planId: string): Promise<{ ok: boolean; id: string }> {
  return apiRequest<{ ok: boolean; id: string }>(`/admin/plans/${encodeURIComponent(planId)}`, {
    method: "DELETE",
    includeAdmin: true,
  });
}

export function assignUserPlan(userId: string, planId: string): Promise<Record<string, unknown>> {
  return apiRequest<Record<string, unknown>>(`/admin/users/${encodeURIComponent(userId)}/plan`, {
    method: "PUT",
    includeAdmin: true,
    body: { plan_id: planId },
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
