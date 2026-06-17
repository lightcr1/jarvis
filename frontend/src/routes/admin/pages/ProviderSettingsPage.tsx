import React, { useEffect, useState } from "react";
import {
  AdminSettings,
  AdminSettingsPayload,
  ModelPrice,
  fetchAdminSettings,
  updateAdminSettings,
} from "../../../shared/api/admin";
import { useJ } from "../../../screens/jarvis-shared";

const PROVIDERS = ["openrouter", "anthropic", "openai", "gemini", "mistral", "deepseek", "local"] as const;

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  const J = useJ();
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderBottom: `1px solid ${J.border}` }}>
      <span style={{ flex: "0 0 220px", fontSize: 12, color: J.textSec }}>{label}</span>
      <div style={{ flex: 1 }}>{children}</div>
    </div>
  );
}

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  const J = useJ();
  return (
    <button
      onClick={() => onChange(!on)}
      style={{
        width: 38, height: 21, borderRadius: 11,
        background: on ? J.amber : J.bg4,
        border: `1px solid ${on ? J.amber : J.border}`,
        cursor: "pointer", position: "relative", transition: "all .18s", flexShrink: 0,
      }}
    >
      <span style={{
        position: "absolute", top: 3, left: on ? 17 : 3, width: 13, height: 13,
        borderRadius: "50%", background: on ? J.bg0 : J.textMuted, transition: "left .18s",
      }} />
    </button>
  );
}

const DEFAULT_PROVIDER_SETTINGS: NonNullable<AdminSettings["provider"]> = {
  default_provider: "openrouter",
  openrouter_enabled: true,
  usd_to_chf_rate: 0.90,
  kill_switch: false,
  disable_expensive_models: false,
  expensive_threshold_chf: 0.10,
  global_daily_budget_chf: 0.0,
  global_monthly_budget_chf: 0.0,
  model_prices: {},
};

type NewModelRow = {
  model: string;
  in_usd: string;
  out_usd: string;
  tier: string;
  expensive: boolean;
};

const EMPTY_ROW: NewModelRow = { model: "", in_usd: "", out_usd: "", tier: "standard", expensive: false };

export function ProviderSettingsPage() {
  const J = useJ();
  const [payload, setPayload] = useState<AdminSettingsPayload | null>(null);
  const [provider, setProvider] = useState<NonNullable<AdminSettings["provider"]>>(DEFAULT_PROVIDER_SETTINGS);
  const [effective, setEffective] = useState<Record<string, unknown>>({});
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const [newRow, setNewRow] = useState<NewModelRow>(EMPTY_ROW);

  useEffect(() => {
    fetchAdminSettings()
      .then((p) => {
        setPayload(p);
        setProvider({ ...DEFAULT_PROVIDER_SETTINGS, ...(p.settings.provider ?? {}) });
        setEffective(p.effective ?? {});
      })
      .catch(() => setStatus("Failed to load settings."));
  }, []);

  const save = async () => {
    if (!payload) return;
    setSaving(true);
    setStatus("");
    try {
      const updated = await updateAdminSettings({ ...payload.settings, provider });
      setPayload(updated);
      setProvider({ ...DEFAULT_PROVIDER_SETTINGS, ...(updated.settings.provider ?? {}) });
      setStatus("Saved.");
    } catch (e) {
      setStatus(`Error: ${e instanceof Error ? e.message : "Failed."}`);
    } finally {
      setSaving(false);
    }
  };

  const addModelRow = () => {
    const model = newRow.model.trim();
    if (!model) return;
    const price: ModelPrice = {
      in_usd_per_1k: parseFloat(newRow.in_usd) || 0,
      out_usd_per_1k: parseFloat(newRow.out_usd) || 0,
      tier: newRow.tier || "standard",
      expensive: newRow.expensive,
    };
    setProvider(p => ({ ...p, model_prices: { ...p.model_prices, [model]: price } }));
    setNewRow(EMPTY_ROW);
  };

  const removeModel = (model: string) => {
    setProvider(p => {
      const next = { ...p.model_prices };
      delete next[model];
      return { ...p, model_prices: next };
    });
  };

  if (!payload) {
    return <div style={{ padding: 40, color: J.textSec, fontSize: 13 }}>Loading provider settings…</div>;
  }

  const card: React.CSSProperties = {
    background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6, padding: "16px 18px",
  };
  const inp: React.CSSProperties = {
    width: "100%", boxSizing: "border-box", padding: "5px 9px", fontSize: 12,
    borderRadius: 4, background: J.bg3, border: `1px solid ${J.border}`,
    color: J.text, outline: "none",
  };
  const killColor = provider.kill_switch ? J.error : J.success;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>

      {/* Status banner */}
      {provider.kill_switch && (
        <div style={{ padding: "10px 16px", borderRadius: 6, background: "rgba(239,68,68,0.12)", border: `1px solid ${J.error}`, color: J.error, fontSize: 12, fontWeight: 500 }}>
          Kill switch active — all AI requests are blocked.
        </div>
      )}

      {/* System key status */}
      {!!effective.provider_keys && (
        <div style={{ ...card }}>
          <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10 }}>
            System Keys (env vars — default for all users without BYOK)
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 10 }}>
            {Object.entries(effective.provider_keys as Record<string, boolean>).map(([prov, set]) => (
              <div key={prov} style={{
                padding: "4px 10px", borderRadius: 4, fontSize: 11, fontWeight: 600,
                background: set ? "rgba(16,185,129,0.1)" : J.bg3,
                border: `1px solid ${set ? J.success : J.border}`,
                color: set ? J.success : J.textMuted,
              }}>
                {prov} {set ? "✓ configured" : "— not set"}
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: 16, fontSize: 11 }}>
            <span style={{ color: (effective.secret_key_configured as boolean) ? J.success : J.error }}>
              BYOK encryption: {(effective.secret_key_configured as boolean) ? "✓ JARVIS_SECRET_KEY set" : "✗ JARVIS_SECRET_KEY missing — users cannot store API keys"}
            </span>
            <span style={{ color: (effective.ai_router_enabled as boolean) ? J.success : J.textMuted }}>
              AI router: {(effective.ai_router_enabled as boolean) ? "✓ enabled" : "disabled"}
            </span>
          </div>
          <div style={{ marginTop: 8, fontSize: 11, color: J.textMuted }}>
            Set keys in <code style={{ color: J.amber }}>/etc/jarvis/jarvis.env</code> — e.g. <code style={{ color: J.amber }}>OPENROUTER_API_KEY=sk-or-...</code> provides a shared default for all users.
          </div>
        </div>
      )}

      {/* Summary stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 10 }}>
        {[
          { label: "Default provider", value: provider.default_provider },
          { label: "Kill switch", value: provider.kill_switch ? "ON" : "off", accent: provider.kill_switch ? J.error : undefined },
          { label: "USD → CHF", value: provider.usd_to_chf_rate.toFixed(2) },
          { label: "Expensive threshold", value: `CHF ${provider.expensive_threshold_chf.toFixed(2)}` },
          { label: "Daily budget", value: provider.global_daily_budget_chf > 0 ? `CHF ${provider.global_daily_budget_chf.toFixed(2)}` : "none" },
          { label: "Model prices", value: Object.keys(provider.model_prices).length },
        ].map(({ label, value, accent }) => (
          <div key={label} style={{ ...card, padding: "12px 16px" }}>
            <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>{label}</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: (accent as string | undefined) || J.text }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Routing & budgets */}
      <div style={card}>
        <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 12 }}>Routing & Budgets</div>

        <Field label="Default provider">
          <select style={inp} value={provider.default_provider}
            onChange={e => setProvider(p => ({ ...p, default_provider: e.target.value }))}>
            {PROVIDERS.map(pv => <option key={pv} value={pv}>{pv}</option>)}
          </select>
        </Field>

        <Field label="OpenRouter enabled">
          <Toggle on={provider.openrouter_enabled} onChange={v => setProvider(p => ({ ...p, openrouter_enabled: v }))} />
        </Field>

        <Field label="USD → CHF rate">
          <input type="number" style={inp} min={0.01} step={0.01} value={provider.usd_to_chf_rate}
            onChange={e => setProvider(p => ({ ...p, usd_to_chf_rate: Math.max(0.01, parseFloat(e.target.value) || 0.01) }))} />
        </Field>

        <Field label={<span style={{ color: killColor }}>Kill switch (block all AI)</span> as unknown as string}>
          <Toggle on={provider.kill_switch} onChange={v => setProvider(p => ({ ...p, kill_switch: v }))} />
        </Field>

        <Field label="Disable expensive models">
          <Toggle on={provider.disable_expensive_models} onChange={v => setProvider(p => ({ ...p, disable_expensive_models: v }))} />
        </Field>

        <Field label="Expensive threshold (CHF)">
          <input type="number" style={inp} min={0} step={0.01} value={provider.expensive_threshold_chf}
            onChange={e => setProvider(p => ({ ...p, expensive_threshold_chf: Math.max(0, parseFloat(e.target.value) || 0) }))} />
        </Field>

        <Field label="Global daily budget CHF (0 = unlimited)">
          <input type="number" style={inp} min={0} step={0.10} value={provider.global_daily_budget_chf}
            onChange={e => setProvider(p => ({ ...p, global_daily_budget_chf: Math.max(0, parseFloat(e.target.value) || 0) }))} />
        </Field>

        <Field label="Global monthly budget CHF (0 = unlimited)">
          <input type="number" style={inp} min={0} step={1} value={provider.global_monthly_budget_chf}
            onChange={e => setProvider(p => ({ ...p, global_monthly_budget_chf: Math.max(0, parseFloat(e.target.value) || 0) }))} />
        </Field>

        <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 14 }}>
          <button
            onClick={() => void save()}
            disabled={saving}
            style={{
              padding: "7px 18px", fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: "pointer",
              background: J.amber, color: J.bg0, border: "none",
              opacity: saving ? 0.6 : 1, transition: "opacity .15s",
            }}
          >
            {saving ? "Saving…" : "Save changes"}
          </button>
          {status && (
            <span style={{ fontSize: 12, color: status.startsWith("Error") || status.startsWith("Failed") ? J.error : J.success }}>
              {status}
            </span>
          )}
        </div>
      </div>

      {/* Model prices */}
      <div style={card}>
        <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 12 }}>
          Model Prices ({Object.keys(provider.model_prices).length} entries)
        </div>

        {Object.keys(provider.model_prices).length > 0 && (
          <div style={{ marginBottom: 12, overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr>
                  {["Model", "In $/1k", "Out $/1k", "Tier", "Expensive", ""].map(h => (
                    <th key={h} style={{ textAlign: "left", padding: "5px 8px", borderBottom: `1px solid ${J.border}`, color: J.textMuted, fontSize: 11, fontWeight: 500 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.entries(provider.model_prices).map(([model, price]) => (
                  <tr key={model} style={{ borderBottom: `1px solid ${J.border}` }}>
                    <td style={{ padding: "6px 8px", color: J.text, fontFamily: "monospace", fontSize: 11 }}>{model}</td>
                    <td style={{ padding: "6px 8px", color: J.textSec }}>{price.in_usd_per_1k.toFixed(4)}</td>
                    <td style={{ padding: "6px 8px", color: J.textSec }}>{price.out_usd_per_1k.toFixed(4)}</td>
                    <td style={{ padding: "6px 8px", color: J.textSec }}>{price.tier}</td>
                    <td style={{ padding: "6px 8px", color: price.expensive ? J.warn : J.textMuted }}>{price.expensive ? "yes" : "—"}</td>
                    <td style={{ padding: "6px 8px" }}>
                      <button
                        onClick={() => removeModel(model)}
                        style={{ padding: "2px 8px", fontSize: 11, borderRadius: 3, cursor: "pointer", background: "transparent", border: `1px solid ${J.border}`, color: J.error }}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Add new row */}
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <input
            style={{ ...inp, flex: "2 1 140px" }}
            placeholder="model name"
            value={newRow.model}
            onChange={e => setNewRow(r => ({ ...r, model: e.target.value }))}
          />
          <input
            type="number"
            style={{ ...inp, flex: "1 1 70px" }}
            placeholder="in $/1k"
            value={newRow.in_usd}
            onChange={e => setNewRow(r => ({ ...r, in_usd: e.target.value }))}
          />
          <input
            type="number"
            style={{ ...inp, flex: "1 1 70px" }}
            placeholder="out $/1k"
            value={newRow.out_usd}
            onChange={e => setNewRow(r => ({ ...r, out_usd: e.target.value }))}
          />
          <select
            style={{ ...inp, flex: "1 1 80px" }}
            value={newRow.tier}
            onChange={e => setNewRow(r => ({ ...r, tier: e.target.value }))}
          >
            <option value="standard">standard</option>
            <option value="mini">mini</option>
            <option value="premium">premium</option>
          </select>
          <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: J.textSec, flexShrink: 0 }}>
            <input
              type="checkbox"
              checked={newRow.expensive}
              onChange={e => setNewRow(r => ({ ...r, expensive: e.target.checked }))}
            />
            expensive
          </label>
          <button
            onClick={addModelRow}
            disabled={!newRow.model.trim()}
            style={{
              padding: "5px 14px", fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: "pointer",
              background: newRow.model.trim() ? J.amberDim : J.bg3,
              color: newRow.model.trim() ? J.amber : J.textMuted,
              border: `1px solid ${newRow.model.trim() ? J.borderAccent : J.border}`,
              flexShrink: 0,
            }}
          >
            Add
          </button>
        </div>

        <div style={{ marginTop: 14 }}>
          <button
            onClick={() => void save()}
            disabled={saving}
            style={{
              padding: "7px 18px", fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: "pointer",
              background: J.amber, color: J.bg0, border: "none",
              opacity: saving ? 0.6 : 1,
            }}
          >
            {saving ? "Saving…" : "Save model prices"}
          </button>
        </div>
      </div>
    </div>
  );
}
