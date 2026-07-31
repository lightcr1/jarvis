import React, { useEffect, useState } from "react";
import { AdminSettingsPayload, fetchAdminSettings, updateAdminSettings } from "../../../shared/api/admin";
import {
  Plan,
  PlanCreate,
  createAdminPlan,
  deleteAdminPlan,
  fetchAdminPlans,
  updateAdminPlan,
} from "../../../shared/api/billing";
import { useJ } from "../../../screens/jarvis-shared";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  const J = useJ();
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderBottom: `1px solid ${J.border}` }}>
      <span style={{ flex: "0 0 280px", fontSize: 12, color: J.textSec }}>{label}</span>
      <div style={{ flex: 1 }}>{children}</div>
    </div>
  );
}

const EMPTY_PLAN: PlanCreate = { name: "", price_chf_per_month: 0, ai_credit_chf_monthly: 0, storage_gb_included: 0, sort_order: 0, stripe_price_id: "" };

export function BillingPage() {
  const J = useJ();
  const [payload, setPayload] = useState<AdminSettingsPayload | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [newPlan, setNewPlan] = useState<PlanCreate>(EMPTY_PLAN);
  const [planStatus, setPlanStatus] = useState("");
  const [overagePrice, setOveragePrice] = useState(0.15);
  const [savingFiles, setSavingFiles] = useState(false);

  useEffect(() => {
    fetchAdminSettings()
      .then(p => {
        setPayload(p);
        setOveragePrice(p.settings.files?.overage_price_chf_per_gb_month ?? 0.15);
      })
      .catch(() => setPlanStatus("Failed to load settings."));
    fetchAdminPlans()
      .then(res => setPlans(res.plans))
      .catch(() => setPlanStatus("Failed to load plans."));
  }, []);

  const saveOveragePrice = async () => {
    if (!payload) return;
    setSavingFiles(true);
    try {
      const updated = await updateAdminSettings({
        ...payload.settings,
        files: { default_storage_quota_mb: payload.settings.files?.default_storage_quota_mb ?? 12000, overage_price_chf_per_gb_month: overagePrice },
      });
      setPayload(updated);
    } catch {
      setPlanStatus("Failed to save storage overage price.");
    } finally {
      setSavingFiles(false);
    }
  };

  const addPlan = async () => {
    if (!newPlan.name.trim()) return;
    try {
      const created = await createAdminPlan({ ...newPlan, name: newPlan.name.trim() });
      setPlans(prev => [...prev, created.plan].sort((a, b) => a.sort_order - b.sort_order));
      setNewPlan(EMPTY_PLAN);
    } catch {
      setPlanStatus("Failed to create plan.");
    }
  };

  const savePlanField = async (planId: string, patch: Partial<PlanCreate>) => {
    try {
      const updated = await updateAdminPlan(planId, patch);
      setPlans(prev => prev.map(p => (p.id === planId ? updated.plan : p)));
    } catch {
      setPlanStatus("Failed to update plan.");
    }
  };

  const removePlan = async (planId: string) => {
    try {
      await deleteAdminPlan(planId);
      setPlans(prev => prev.filter(p => p.id !== planId));
    } catch {
      setPlanStatus("Failed to delete plan.");
    }
  };

  if (!payload) {
    return <div style={{ padding: 40, color: J.textSec, fontSize: 13 }}>Loading billing…</div>;
  }

  const card: React.CSSProperties = {
    background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6, padding: "16px 18px",
  };
  const inp: React.CSSProperties = {
    width: "100%", boxSizing: "border-box", padding: "5px 9px", fontSize: 12,
    borderRadius: 4, background: J.bg3, border: `1px solid ${J.border}`,
    color: J.text, outline: "none",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>

      {/* Summary + cross-links */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 10 }}>
        <div style={{ ...card, padding: "12px 16px" }}>
          <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>Plans</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: J.text }}>{plans.length}</div>
        </div>
        <div style={{ ...card, padding: "12px 16px" }}>
          <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>Storage overage</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: J.text }}>CHF {overagePrice.toFixed(2)}/GB·mo</div>
        </div>
        <a href="/dashboard/usage" style={{ ...card, padding: "12px 16px", textDecoration: "none", display: "block" }}>
          <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>Usage & spend</div>
          <div style={{ fontSize: 13, fontWeight: 600, color: J.amber }}>View usage →</div>
        </a>
        <a href="/dashboard/provider" style={{ ...card, padding: "12px 16px", textDecoration: "none", display: "block" }}>
          <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>AI routing & budgets</div>
          <div style={{ fontSize: 13, fontWeight: 600, color: J.amber }}>AI Provider →</div>
        </a>
      </div>

      {/* Stripe pointer */}
      <div style={{ ...card, borderColor: J.borderAccent }}>
        <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
          Stripe connection
        </div>
        <div style={{ fontSize: 12, color: J.textSec, lineHeight: 1.6 }}>
          Stripe API keys are configured under the main app's <strong>Settings → Payments</strong> tab, not here —
          that keeps it reachable by anyone granted the <code style={{ color: J.amber }}>billing.manage</code> permission,
          not only full admins (the rest of this dashboard is admin-only). Assign a Stripe Price ID to a plan below
          to enable its "Subscribe" button for users.
        </div>
      </div>

      {/* Plans */}
      <div style={card}>
        <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 12 }}>
          Plans ({plans.length}) — bundled AI credit + storage, assignable per user under Users
        </div>
        {planStatus && (
          <div style={{ marginBottom: 10, fontSize: 12, color: J.error }}>{planStatus}</div>
        )}
        {plans.length > 0 && (
          <div style={{ marginBottom: 12, overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr>
                  {["Name", "CHF/month", "AI credit/month", "Storage (GB)", "Stripe Price ID", ""].map(h => (
                    <th key={h} style={{ textAlign: "left", padding: "5px 8px", borderBottom: `1px solid ${J.border}`, color: J.textMuted, fontSize: 11, fontWeight: 500 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {plans.map(plan => (
                  <tr key={plan.id} style={{ borderBottom: `1px solid ${J.border}` }}>
                    <td style={{ padding: "6px 8px" }}>
                      <input style={{ ...inp, width: 140 }} defaultValue={plan.name}
                        onBlur={e => { if (e.target.value.trim() && e.target.value !== plan.name) void savePlanField(plan.id, { name: e.target.value.trim() }); }} />
                    </td>
                    <td style={{ padding: "6px 8px" }}>
                      <input type="number" style={{ ...inp, width: 90 }} step={0.5} defaultValue={plan.price_chf_per_month}
                        onBlur={e => { const v = parseFloat(e.target.value) || 0; if (v !== plan.price_chf_per_month) void savePlanField(plan.id, { price_chf_per_month: v }); }} />
                    </td>
                    <td style={{ padding: "6px 8px" }}>
                      <input type="number" style={{ ...inp, width: 90 }} step={0.5} defaultValue={plan.ai_credit_chf_monthly}
                        onBlur={e => { const v = parseFloat(e.target.value) || 0; if (v !== plan.ai_credit_chf_monthly) void savePlanField(plan.id, { ai_credit_chf_monthly: v }); }} />
                    </td>
                    <td style={{ padding: "6px 8px" }}>
                      <input type="number" style={{ ...inp, width: 90 }} step={1} defaultValue={plan.storage_gb_included}
                        onBlur={e => { const v = parseFloat(e.target.value) || 0; if (v !== plan.storage_gb_included) void savePlanField(plan.id, { storage_gb_included: v }); }} />
                    </td>
                    <td style={{ padding: "6px 8px" }}>
                      <input style={{ ...inp, width: 140 }} placeholder="price_..." defaultValue={plan.stripe_price_id}
                        onBlur={e => { const v = e.target.value.trim(); if (v !== plan.stripe_price_id) void savePlanField(plan.id, { stripe_price_id: v }); }} />
                    </td>
                    <td style={{ padding: "6px 8px" }}>
                      <button onClick={() => void removePlan(plan.id)}
                        style={{ padding: "2px 8px", fontSize: 11, borderRadius: 3, cursor: "pointer", background: "transparent", border: `1px solid ${J.border}`, color: J.error }}>
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <input style={{ ...inp, flex: "2 1 140px" }} placeholder="plan name"
            value={newPlan.name} onChange={e => setNewPlan(p => ({ ...p, name: e.target.value }))} />
          <input type="number" style={{ ...inp, flex: "1 1 90px" }} placeholder="CHF/month" step={0.5}
            value={newPlan.price_chf_per_month} onChange={e => setNewPlan(p => ({ ...p, price_chf_per_month: parseFloat(e.target.value) || 0 }))} />
          <input type="number" style={{ ...inp, flex: "1 1 100px" }} placeholder="AI credit/month" step={0.5}
            value={newPlan.ai_credit_chf_monthly} onChange={e => setNewPlan(p => ({ ...p, ai_credit_chf_monthly: parseFloat(e.target.value) || 0 }))} />
          <input type="number" style={{ ...inp, flex: "1 1 90px" }} placeholder="GB storage" step={1}
            value={newPlan.storage_gb_included} onChange={e => setNewPlan(p => ({ ...p, storage_gb_included: parseFloat(e.target.value) || 0 }))} />
          <input style={{ ...inp, flex: "1 1 140px" }} placeholder="Stripe Price ID (optional)"
            value={newPlan.stripe_price_id} onChange={e => setNewPlan(p => ({ ...p, stripe_price_id: e.target.value.trim() }))} />
          <button onClick={() => void addPlan()} disabled={!newPlan.name.trim()}
            style={{
              padding: "5px 14px", fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: "pointer",
              background: newPlan.name.trim() ? J.amberDim : J.bg3,
              color: newPlan.name.trim() ? J.amber : J.textMuted,
              border: `1px solid ${newPlan.name.trim() ? J.borderAccent : J.border}`,
              flexShrink: 0,
            }}>
            Add plan
          </button>
        </div>
      </div>

      {/* Storage overage price */}
      <div style={card}>
        <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 12 }}>
          Storage Overage Pricing
        </div>
        <Field label="CHF per GB / month (beyond a user's included quota)">
          <input type="number" style={inp} min={0} step={0.01} value={overagePrice}
            onChange={e => setOveragePrice(Math.max(0, parseFloat(e.target.value) || 0))} />
        </Field>
        <div style={{ marginTop: 10 }}>
          <button onClick={() => void saveOveragePrice()} disabled={savingFiles}
            style={{ padding: "7px 18px", fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: "pointer", background: J.amber, color: J.bg0, border: "none", opacity: savingFiles ? 0.6 : 1 }}>
            {savingFiles ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
