import React, { useEffect, useState, useCallback } from "react";
import { AdminSettings, AdminSettingsPayload, fetchAdminSettings, updateAdminSettings, downloadAdminBackup } from "../../../shared/api/admin";
import {
  AlertRule,
  AlertRuleCreate,
  fetchAlertRules,
  createAlertRule,
  updateAlertRule,
  deleteAlertRule,
  testAlertRule,
} from "../../../shared/api/alerts";
import { useJ } from "../../../screens/jarvis-shared";
import { OverlayDialog } from "../../../shared/ui/OverlayDialog";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  const J = useJ();
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderBottom: `1px solid ${J.border}` }}>
      <span style={{ flex: "0 0 200px", fontSize: 12, color: J.textSec }}>{label}</span>
      <div style={{ flex: 1 }}>{children}</div>
    </div>
  );
}

const SEVERITY_COLOR = (J: ReturnType<typeof useJ>, sev: string) => {
  if (sev === "critical") return J.error;
  if (sev === "warning") return J.warn;
  return J.blue;
};

type RuleFormState = Omit<AlertRule, "id">;

const DEFAULT_FORM: RuleFormState = {
  name: "",
  enabled: true,
  metric: "cpu",
  condition: "above",
  threshold: 80,
  duration_seconds: 0,
  severity: "warning",
  cooldown_seconds: 300,
  ha_entity_id: null,
  ha_attribute: null,
  message_template: "Alert: {metric} is {value} (threshold: {threshold})",
};

function AlertRuleForm({
  initial,
  onSave,
  onCancel,
  saving,
}: {
  initial: RuleFormState;
  onSave: (data: RuleFormState) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const J = useJ();
  const [form, setForm] = useState<RuleFormState>(initial);

  const inp: React.CSSProperties = {
    width: "100%", boxSizing: "border-box", padding: "5px 9px", fontSize: 12,
    borderRadius: 4, background: J.bg3, border: `1px solid ${J.border}`,
    color: J.text, outline: "none",
  };

  const set = (patch: Partial<RuleFormState>) => setForm(f => ({ ...f, ...patch }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <Field label="Name">
        <input style={inp} value={form.name} onChange={e => set({ name: e.target.value })} placeholder="Rule name" />
      </Field>
      <Field label="Metric">
        <select style={inp} value={form.metric} onChange={e => set({ metric: e.target.value as AlertRule["metric"] })}>
          <option value="cpu">CPU</option>
          <option value="ram">RAM</option>
          <option value="disk">Disk</option>
          <option value="ha_entity">Home Assistant entity</option>
        </select>
      </Field>
      {form.metric === "ha_entity" && (
        <>
          <Field label="HA entity ID">
            <input style={inp} value={form.ha_entity_id ?? ""} onChange={e => set({ ha_entity_id: e.target.value || null })} placeholder="e.g. switch.living_room" />
          </Field>
          <Field label="HA attribute">
            <input style={inp} value={form.ha_attribute ?? ""} onChange={e => set({ ha_attribute: e.target.value || null })} placeholder="state (default)" />
          </Field>
        </>
      )}
      <Field label="Condition">
        <select style={inp} value={form.condition} onChange={e => set({ condition: e.target.value as AlertRule["condition"] })}>
          <option value="above">above</option>
          <option value="below">below</option>
          <option value="equals">equals</option>
          <option value="contains">contains</option>
        </select>
      </Field>
      <Field label="Threshold">
        <input style={inp} value={String(form.threshold)} onChange={e => {
          const v = parseFloat(e.target.value);
          set({ threshold: isNaN(v) ? e.target.value : v });
        }} placeholder="e.g. 90" />
      </Field>
      <Field label="Duration (seconds)">
        <input type="number" style={inp} min={0} value={form.duration_seconds}
          onChange={e => set({ duration_seconds: Math.max(0, parseInt(e.target.value) || 0) })} />
      </Field>
      <Field label="Severity">
        <select style={inp} value={form.severity} onChange={e => set({ severity: e.target.value as AlertRule["severity"] })}>
          <option value="info">info</option>
          <option value="warning">warning</option>
          <option value="critical">critical</option>
        </select>
      </Field>
      <Field label="Cooldown (seconds)">
        <input type="number" style={inp} min={60} value={form.cooldown_seconds}
          onChange={e => set({ cooldown_seconds: Math.max(60, parseInt(e.target.value) || 300) })} />
      </Field>
      <Field label="Message template">
        <input style={inp} value={form.message_template}
          onChange={e => set({ message_template: e.target.value })}
          placeholder="{metric} is {value} (threshold: {threshold})" />
      </Field>
      <Field label="Enabled">
        <select style={inp} value={String(form.enabled)} onChange={e => set({ enabled: e.target.value === "true" })}>
          <option value="true">Yes</option>
          <option value="false">No</option>
        </select>
      </Field>
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 6 }}>
        <button onClick={onCancel} style={{
          padding: "6px 14px", fontSize: 12, borderRadius: 4, cursor: "pointer",
          background: "transparent", color: J.textSec, border: `1px solid ${J.border}`,
        }}>Cancel</button>
        <button onClick={() => onSave(form)} disabled={saving || !form.name.trim()} style={{
          padding: "6px 16px", fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: "pointer",
          background: J.amber, color: J.bg0, border: "none", opacity: saving ? 0.6 : 1,
        }}>{saving ? "Saving…" : "Save rule"}</button>
      </div>
    </div>
  );
}

function AlertRulesSection() {
  const J = useJ();
  const [rules, setRules] = useState<AlertRule[] | null>(null);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [editRule, setEditRule] = useState<AlertRule | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<AlertRule | null>(null);
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchAlertRules()
      .then(d => setRules(d.rules))
      .catch(e => setError(String(e)));
  }, []);

  useEffect(() => { load(); }, [load]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(""), 3500);
  };

  const handleCreate = async (data: RuleFormState) => {
    setSaving(true);
    try {
      await createAlertRule(data as AlertRuleCreate);
      setShowAdd(false);
      load();
      showToast("Rule created.");
    } catch (e) {
      showToast(`Error: ${e instanceof Error ? e.message : "Failed."}`);
    } finally {
      setSaving(false);
    }
  };

  const handleUpdate = async (data: RuleFormState) => {
    if (!editRule) return;
    setSaving(true);
    try {
      await updateAlertRule(editRule.id, data);
      setEditRule(null);
      load();
      showToast("Rule updated.");
    } catch (e) {
      showToast(`Error: ${e instanceof Error ? e.message : "Failed."}`);
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async (rule: AlertRule) => {
    try {
      await updateAlertRule(rule.id, { enabled: !rule.enabled });
      load();
    } catch (e) {
      showToast(`Error: ${e instanceof Error ? e.message : "Failed."}`);
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    try {
      await deleteAlertRule(confirmDelete.id);
      setConfirmDelete(null);
      load();
      showToast("Rule deleted.");
    } catch (e) {
      showToast(`Error: ${e instanceof Error ? e.message : "Failed."}`);
    }
  };

  const handleTest = async (rule: AlertRule) => {
    setTestingId(rule.id);
    try {
      await testAlertRule(rule.id);
      showToast(`Test alert fired for "${rule.name}".`);
    } catch (e) {
      showToast(`Test failed: ${e instanceof Error ? e.message : "Failed."}`);
    } finally {
      setTestingId(null);
    }
  };

  const card: React.CSSProperties = {
    background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6,
  };
  const btnSm: React.CSSProperties = {
    padding: "3px 10px", fontSize: 11, borderRadius: 3, cursor: "pointer",
    border: `1px solid ${J.border}`, background: "transparent", color: J.textSec,
  };

  return (
    <div style={{ ...card, padding: "16px 18px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>Alert rules</div>
          <div style={{ fontSize: 11, color: J.textMuted, marginTop: 2 }}>Background monitoring of CPU, RAM, disk, and Home Assistant entities.</div>
        </div>
        <button onClick={() => setShowAdd(true)} style={{
          padding: "5px 14px", fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: "pointer",
          background: J.amberDim, color: J.amber, border: `1px solid ${J.borderAccent}`,
        }}>+ Add rule</button>
      </div>

      {error && <div style={{ color: J.error, fontSize: 12, marginBottom: 10 }}>{error}</div>}

      {rules === null ? (
        <div style={{ color: J.textMuted, fontSize: 12, padding: "12px 0" }}>Loading rules…</div>
      ) : rules.length === 0 ? (
        <div style={{ color: J.textMuted, fontSize: 12, padding: "12px 0" }}>No alert rules configured.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {rules.map(rule => (
            <div key={rule.id} style={{
              display: "flex", alignItems: "center", gap: 10, padding: "9px 12px",
              borderRadius: 5, border: `1px solid ${J.border}`, background: J.bg1,
              flexWrap: "wrap",
            }}>
              <div style={{
                width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                background: SEVERITY_COLOR(J, rule.severity),
              }} />
              <div style={{ flex: 1, minWidth: 120 }}>
                <div style={{ fontSize: 13, fontWeight: 500, color: rule.enabled ? J.text : J.textMuted }}>{rule.name}</div>
                <div style={{ fontSize: 11, color: J.textSec, marginTop: 2 }}>
                  {rule.metric.toUpperCase()} {rule.condition} {String(rule.threshold)}
                  {rule.duration_seconds > 0 ? ` for ${rule.duration_seconds}s` : ""}
                  {" — "}<span style={{ color: SEVERITY_COLOR(J, rule.severity) }}>{rule.severity}</span>
                </div>
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center", flexShrink: 0 }}>
                <button
                  onClick={() => handleToggle(rule)}
                  title={rule.enabled ? "Disable" : "Enable"}
                  style={{
                    ...btnSm,
                    color: rule.enabled ? J.success : J.textMuted,
                    borderColor: rule.enabled ? J.success : J.border,
                  }}
                >
                  {rule.enabled ? "Enabled" : "Disabled"}
                </button>
                <button style={btnSm} onClick={() => setEditRule(rule)}>Edit</button>
                <button
                  style={{ ...btnSm, color: J.blue }}
                  disabled={testingId === rule.id}
                  onClick={() => handleTest(rule)}
                >
                  {testingId === rule.id ? "…" : "Test"}
                </button>
                <button style={{ ...btnSm, color: J.error, borderColor: J.error }} onClick={() => setConfirmDelete(rule)}>
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {toast && (
        <div style={{
          position: "fixed", bottom: 24, right: 24, zIndex: 300,
          background: J.bg3, border: `1px solid ${J.border}`, borderRadius: 6,
          padding: "10px 16px", fontSize: 12, color: J.text,
          boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
          animation: "fadeIn .2s ease",
        }}>{toast}</div>
      )}

      {showAdd && (
        <OverlayDialog title="Add alert rule" eyebrow="Alert rules" onClose={() => setShowAdd(false)}>
          <AlertRuleForm
            initial={{ ...DEFAULT_FORM }}
            onSave={handleCreate}
            onCancel={() => setShowAdd(false)}
            saving={saving}
          />
        </OverlayDialog>
      )}

      {editRule && (
        <OverlayDialog title="Edit alert rule" eyebrow="Alert rules" onClose={() => setEditRule(null)}>
          <AlertRuleForm
            initial={{ ...editRule }}
            onSave={handleUpdate}
            onCancel={() => setEditRule(null)}
            saving={saving}
          />
        </OverlayDialog>
      )}

      {confirmDelete && (
        <OverlayDialog
          title={`Delete "${confirmDelete.name}"?`}
          eyebrow="Confirm deletion"
          onClose={() => setConfirmDelete(null)}
          actions={
            <>
              <button onClick={() => setConfirmDelete(null)} style={{
                padding: "6px 14px", fontSize: 12, borderRadius: 4, cursor: "pointer",
                background: "transparent", color: J.textSec, border: `1px solid ${J.border}`,
              }}>Cancel</button>
              <button onClick={handleDelete} style={{
                padding: "6px 16px", fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: "pointer",
                background: J.error, color: J.text, border: "none",
              }}>Delete</button>
            </>
          }
        >
          <p style={{ fontSize: 13, color: J.textSec }}>
            This will permanently remove the rule. Fired alerts are not affected.
          </p>
        </OverlayDialog>
      )}
    </div>
  );
}

export function SettingsPage() {
  const J = useJ();
  const [settings, setSettings] = useState<AdminSettingsPayload | null>(null);
  const [form, setForm] = useState<AdminSettings | null>(null);
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchAdminSettings().then(p => {
      setSettings(p);
      setForm(p.settings);
    }).catch(() => undefined);
  }, []);

  if (!settings || !form) {
    return <div style={{ padding: 40, color: J.textSec, fontSize: 13 }}>Loading settings…</div>;
  }

  const save = async () => {
    setSaving(true);
    setStatus("");
    try {
      const payload = await updateAdminSettings(form);
      setSettings(payload);
      setForm(payload.settings);
      setStatus("Settings saved.");
    } catch (e) {
      setStatus(`Error: ${e instanceof Error ? e.message : "Failed."}`);
    } finally {
      setSaving(false);
    }
  };

  const card: React.CSSProperties = {
    background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6,
  };
  const inp: React.CSSProperties = {
    width: "100%", boxSizing: "border-box", padding: "5px 9px", fontSize: 12,
    borderRadius: 4, background: J.bg3, border: `1px solid ${J.border}`,
    color: J.text, outline: "none",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>

      {/* ── Metrics ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: 10 }}>
        {[
          { label: "Token TTL", value: `${form.usage_limits.token_ttl_min}m` },
          { label: "Max tokens", value: form.usage_limits.max_active_tokens },
          { label: "Wakeword", value: form.voice.wakeword_enabled ? "on" : "off", accent: form.voice.wakeword_enabled ? J.success : undefined },
          { label: "WW engine", value: form.voice.wakeword_engine ?? "software" },
          { label: "STT provider", value: form.voice.stt_provider },
          { label: "HA confirm TTL", value: `${form.home_assistant.confirmation_ttl_sec}s` },
        ].map(({ label, value, accent }) => (
          <div key={label} style={{ ...card, padding: "12px 16px" }}>
            <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>{label}</div>
            <div style={{ fontSize: 18, fontWeight: 700, color: (accent as string | undefined) || J.text }}>{value}</div>
          </div>
        ))}
      </div>

      {/* ── Runtime defaults ── */}
      <div style={{ ...card, padding: "16px 18px" }}>
        <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 12 }}>Runtime defaults</div>

        <Field label="Token TTL (minutes)">
          <input type="number" style={inp} value={form.usage_limits.token_ttl_min}
            onChange={e => setForm({ ...form, usage_limits: { ...form.usage_limits, token_ttl_min: Number(e.target.value) } })} />
        </Field>
        <Field label="Max active tokens">
          <input type="number" style={inp} value={form.usage_limits.max_active_tokens}
            onChange={e => setForm({ ...form, usage_limits: { ...form.usage_limits, max_active_tokens: Number(e.target.value) } })} />
        </Field>
        <Field label="Wakeword">
          <select style={inp} value={String(form.voice.wakeword_enabled)}
            onChange={e => setForm({ ...form, voice: { ...form.voice, wakeword_enabled: e.target.value === "true" } })}>
            <option value="false">Off</option>
            <option value="true">On</option>
          </select>
        </Field>
        <Field label="Wakeword phrase">
          <input style={inp} value={form.voice.wakeword_phrase}
            onChange={e => setForm({ ...form, voice: { ...form.voice, wakeword_phrase: e.target.value } })} />
        </Field>
        <Field label="Wakeword engine">
          <select style={inp} value={form.voice.wakeword_engine ?? "software"}
            onChange={e => setForm({ ...form, voice: { ...form.voice, wakeword_engine: e.target.value as "software" | "openwakeword" | "none" } })}>
            <option value="software">software (post-transcription strip)</option>
            <option value="openwakeword">openwakeword (always-on mic)</option>
            <option value="none">none</option>
          </select>
        </Field>
        <Field label="Wakeword sensitivity (0.0 – 1.0)">
          <input type="number" style={inp} min={0} max={1} step={0.05}
            value={form.voice.wakeword_sensitivity ?? 0.5}
            onChange={e => setForm({ ...form, voice: { ...form.voice, wakeword_sensitivity: Math.min(1, Math.max(0, Number(e.target.value))) } })} />
        </Field>
        <Field label="Speech-to-text provider">
          <select style={inp} value={form.voice.stt_provider}
            onChange={e => setForm({ ...form, voice: { ...form.voice, stt_provider: e.target.value as "local" | "gemini" } })}>
            <option value="local">local</option>
            <option value="gemini">gemini</option>
          </select>
        </Field>
        <Field label="HA confirmation TTL (seconds)">
          <input type="number" style={inp} value={form.home_assistant.confirmation_ttl_sec}
            onChange={e => setForm({ ...form, home_assistant: { ...form.home_assistant, confirmation_ttl_sec: Number(e.target.value) } })} />
        </Field>
        <Field label="HA remote allowed CIDRs">
          <textarea
            rows={3}
            style={{ ...inp, resize: "vertical", fontFamily: "monospace", fontSize: 11 }}
            value={form.home_assistant.remote_allowed_cidrs.join("\n")}
            onChange={e => setForm({
              ...form,
              home_assistant: {
                ...form.home_assistant,
                remote_allowed_cidrs: e.target.value.split("\n").map(s => s.trim()).filter(Boolean),
              },
            })}
            placeholder="One CIDR per line, e.g. 192.168.1.0/24"
          />
        </Field>

        <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 14 }}>
          <button onClick={() => void save()} disabled={saving} style={{
            padding: "7px 18px", fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: "pointer",
            background: J.amber, color: J.bg0, border: "none",
            opacity: saving ? 0.6 : 1, transition: "opacity .15s",
          }}>{saving ? "Saving…" : "Save changes"}</button>
          {status && (
            <span style={{ fontSize: 12, color: status.startsWith("Error") ? J.error : J.success }}>{status}</span>
          )}
        </div>
      </div>

      {/* ── Alert Rules ── */}
      <AlertRulesSection />

      {/* ── Backup ── */}
      <div style={{ ...card, padding: "16px 18px" }}>
        <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 12 }}>Backup</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 14 }}>
          {[
            ["Schedule", "Every JARVIS_AUTO_BACKUP_INTERVAL_HOURS hours (default 24)"],
            ["Destination", "/var/lib/jarvis/auto_backups/ (7 kept)"],
            ["Disable flag", "JARVIS_AUTO_BACKUP_DISABLED=1"],
          ].map(([k, v]) => (
            <div key={k} style={{ display: "flex", gap: 12, fontSize: 12 }}>
              <span style={{ flex: "0 0 100px", color: J.textSec }}>{k}</span>
              <code style={{ color: J.text, fontFamily: "monospace" }}>{v}</code>
            </div>
          ))}
        </div>
        <button onClick={async () => {
          try { await downloadAdminBackup(); }
          catch (e) { alert(`Backup failed: ${e instanceof Error ? e.message : String(e)}`); }
        }} style={{
          padding: "6px 16px", fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: "pointer",
          background: J.amberDim, color: J.amber, border: `1px solid ${J.borderAccent}`,
        }}>Download manual backup</button>
      </div>

      {/* ── Effective values ── */}
      <div style={{ ...card, padding: "16px 18px" }}>
        <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>Effective runtime values</div>
        <div style={{ fontSize: 11, color: J.textMuted, marginBottom: 12 }}>Actual values in use — environment variables take precedence over settings above.</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 0, borderRadius: 4, overflow: "hidden", border: `1px solid ${J.border}` }}>
          {Object.entries(settings.effective).map(([key, val], i, arr) => (
            <div key={key} style={{
              display: "flex", gap: 12, padding: "7px 12px", alignItems: "baseline",
              borderBottom: i < arr.length - 1 ? `1px solid ${J.border}` : "none",
              background: i % 2 === 1 ? J.bg1 : "transparent",
            }}>
              <code style={{ flex: "0 0 240px", fontSize: 11, fontFamily: "monospace", color: J.textSec }}>{key}</code>
              <code style={{ fontSize: 11, fontFamily: "monospace", color: J.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {typeof val === "boolean" ? (val ? "true" : "false") : String(val ?? "—")}
              </code>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
