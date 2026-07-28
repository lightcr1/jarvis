import React, { useCallback, useEffect, useState } from "react";
import {
  AdminPlaybook,
  AdminPlaybookStepInput,
  AdminPolicy,
  PlaybookRun,
  PolicyAction,
  PolicyCondition,
  PolicyEvent,
  createAdminPlaybook,
  createAdminPolicy,
  deleteAdminPlaybook,
  deleteAdminPolicy,
  executeAdminPlaybook,
  fetchAdminPlaybookRuns,
  fetchAdminPlaybooks,
  fetchAdminPolicies,
  fetchAdminPolicyHistory,
  resumeAdminPlaybookRun,
  testAdminPolicy,
  updateAdminPlaybook,
  updateAdminPolicy,
} from "../../../shared/api/admin";
import { useJ } from "../../../screens/jarvis-shared";
import { OverlayDialog } from "../../../shared/ui/OverlayDialog";

type PolicyDraft = {
  name: string;
  domain: string;
  condition: PolicyCondition;
  action: PolicyAction;
  enabled: boolean;
  dry_run: boolean;
  cooldown_sec: number;
};

type StepDraft = {
  step_id: string;
  description: string;
  action: PolicyAction;
  requires_confirmation: boolean;
};

type PlaybookDraft = {
  name: string;
  description: string;
  dry_run: boolean;
  steps: StepDraft[];
};

type TestResult = { loading?: boolean; event?: PolicyEvent; escalated?: boolean; error?: string };
type Tone = "success" | "error" | "warn" | "blue" | "muted";

const KNOWN_ACTION_TYPES = ["restart_service", "noop"];
const KNOWN_METRICS = ["cpu", "ram", "disk", "ha_health", "service_status"];

function fmtTs(ts: number | null): string {
  if (!ts) return "—";
  const d = new Date(ts > 1e10 ? ts : ts * 1000);
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function toneForStatus(status: string): Tone {
  if (status === "succeeded" || status === "completed") return "success";
  if (status === "failed") return "error";
  if (status === "awaiting_confirmation") return "warn";
  if (status === "would_execute") return "blue";
  return "muted";
}

function emptyPolicyDraft(): PolicyDraft {
  return {
    name: "",
    domain: "system",
    condition: { metric: "cpu", comparator: "above", threshold: 90, duration_sec: 60 },
    action: { type: "restart_service", params: {} },
    enabled: true,
    dry_run: true,
    cooldown_sec: 300,
  };
}

function policyToDraft(p: AdminPolicy): PolicyDraft {
  return {
    name: p.name,
    domain: p.domain,
    condition: { ...p.condition },
    action: { type: p.action.type, params: { ...p.action.params } },
    enabled: p.enabled,
    dry_run: p.dry_run,
    cooldown_sec: p.cooldown_sec,
  };
}

function emptyPlaybookDraft(): PlaybookDraft {
  return { name: "", description: "", dry_run: true, steps: [] };
}

function playbookToDraft(pb: AdminPlaybook): PlaybookDraft {
  return {
    name: pb.name,
    description: pb.description,
    dry_run: pb.dry_run,
    steps: pb.steps.map(s => ({
      step_id: s.step_id,
      description: s.description,
      action: { type: s.action.type, params: { ...s.action.params } },
      requires_confirmation: s.requires_confirmation,
    })),
  };
}

function btnStyle(J: ReturnType<typeof useJ>): React.CSSProperties {
  return {
    padding: "5px 12px", fontSize: 11, borderRadius: 4, cursor: "pointer",
    background: "transparent", color: J.textSec, border: `1px solid ${J.border}`,
  };
}

function dangerBtnStyle(J: ReturnType<typeof useJ>): React.CSSProperties {
  return {
    padding: "5px 12px", fontSize: 11, borderRadius: 4, cursor: "pointer",
    background: J.errorDim, color: J.error, border: `1px solid ${J.error}30`,
  };
}

function primaryBtnStyle(J: ReturnType<typeof useJ>, disabled?: boolean): React.CSSProperties {
  return {
    padding: "6px 16px", fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: "pointer",
    background: J.amber, color: J.bg0, border: "none", opacity: disabled ? 0.5 : 1,
  };
}

function fieldInput(J: ReturnType<typeof useJ>): React.CSSProperties {
  return {
    width: "100%", boxSizing: "border-box", padding: "6px 10px", fontSize: 12,
    borderRadius: 4, background: J.bg3, border: `1px solid ${J.border}`, color: J.text, outline: "none",
  };
}

function fieldLabel(J: ReturnType<typeof useJ>): React.CSSProperties {
  return { fontSize: 11, color: J.textMuted, marginBottom: 4, display: "block" };
}

function StatusPill({ text, tone, J }: { text: string; tone: Tone; J: ReturnType<typeof useJ> }) {
  const map: Record<Tone, { bg: string; fg: string; bd: string }> = {
    success: { bg: J.successDim, fg: J.success, bd: `${J.success}30` },
    error: { bg: J.errorDim, fg: J.error, bd: `${J.error}30` },
    warn: { bg: J.warnDim, fg: J.warn, bd: `${J.warn}30` },
    blue: { bg: J.blueDim, fg: J.blue, bd: `${J.blue}40` },
    muted: { bg: J.bg4, fg: J.textSec, bd: J.border },
  };
  const c = map[tone];
  return (
    <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 3, background: c.bg, color: c.fg, border: `1px solid ${c.bd}`, fontWeight: 600, whiteSpace: "nowrap" }}>
      {text}
    </span>
  );
}

function ParamsEditor({ params, onChange, J }: {
  params: Record<string, unknown>;
  onChange: (p: Record<string, unknown>) => void;
  J: ReturnType<typeof useJ>;
}) {
  const entries = Object.entries(params);
  const cell: React.CSSProperties = {
    flex: 1, padding: "4px 8px", fontSize: 11, borderRadius: 4,
    background: J.bg3, border: `1px solid ${J.border}`, color: J.text, outline: "none",
  };
  const setEntry = (idx: number, key: string, value: string) => {
    const next = entries.map(e => [...e] as [string, unknown]);
    next[idx] = [key, value];
    onChange(Object.fromEntries(next));
  };
  const removeEntry = (idx: number) => onChange(Object.fromEntries(entries.filter((_, i) => i !== idx)));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {entries.map(([k, v], idx) => (
        <div key={idx} style={{ display: "flex", gap: 6 }}>
          <input value={k} onChange={e => setEntry(idx, e.target.value, String(v ?? ""))} placeholder="key" style={{ ...cell, flex: "0 0 110px" }} />
          <input value={String(v ?? "")} onChange={e => setEntry(idx, k, e.target.value)} placeholder="value" style={cell} />
          <button onClick={() => removeEntry(idx)} style={{ padding: "2px 8px", fontSize: 11, borderRadius: 4, cursor: "pointer", background: J.errorDim, color: J.error, border: `1px solid ${J.error}30` }}>×</button>
        </div>
      ))}
      <button
        onClick={() => onChange({ ...params, [`param${entries.length + 1}`]: "" })}
        style={{ alignSelf: "flex-start", padding: "3px 10px", fontSize: 11, borderRadius: 4, cursor: "pointer", background: J.bg4, color: J.textSec, border: `1px solid ${J.border}` }}
      >+ Param</button>
    </div>
  );
}

function ActionEditor({ action, onChange, J }: {
  action: PolicyAction;
  onChange: (next: PolicyAction) => void;
  J: ReturnType<typeof useJ>;
}) {
  const isKnown = KNOWN_ACTION_TYPES.includes(action.type);
  const sel = fieldInput(J);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <select
          value={isKnown ? action.type : "custom"}
          onChange={e => {
            const v = e.target.value;
            if (v === "restart_service") onChange({ type: v, params: { service: String(action.params.service ?? "") } });
            else if (v === "noop") onChange({ type: v, params: { note: String(action.params.note ?? "") } });
            else onChange({ type: "", params: {} });
          }}
          style={{ ...sel, flex: "0 0 180px" }}
        >
          <option value="restart_service">Restart service</option>
          <option value="noop">No-op (test only)</option>
          <option value="custom">Custom type…</option>
        </select>
        {!isKnown && (
          <input
            value={action.type}
            onChange={e => onChange({ ...action, type: e.target.value })}
            placeholder="Action type (e.g. notify)"
            style={{ ...sel, flex: 1, minWidth: 140 }}
          />
        )}
      </div>
      {action.type === "restart_service" && (
        <input
          value={String(action.params.service ?? "")}
          onChange={e => onChange({ ...action, params: { ...action.params, service: e.target.value } })}
          placeholder="Service name (e.g. nginx)"
          style={sel}
        />
      )}
      {action.type === "noop" && (
        <input
          value={String(action.params.note ?? "")}
          onChange={e => onChange({ ...action, params: { ...action.params, note: e.target.value } })}
          placeholder="Note (optional)"
          style={sel}
        />
      )}
      {!isKnown && action.type !== "" && (
        <ParamsEditor params={action.params} onChange={p => onChange({ ...action, params: p })} J={J} />
      )}
    </div>
  );
}

function ConditionEditor({ condition, onChange, J }: {
  condition: PolicyCondition;
  onChange: (c: PolicyCondition) => void;
  J: ReturnType<typeof useJ>;
}) {
  const isKnown = KNOWN_METRICS.includes(condition.metric);
  const sel = fieldInput(J);
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
      <select
        value={isKnown ? condition.metric : "custom"}
        onChange={e => { const v = e.target.value; onChange({ ...condition, metric: v === "custom" ? "" : v }); }}
        style={{ ...sel, flex: "0 0 150px" }}
      >
        <option value="cpu">CPU %</option>
        <option value="ram">RAM %</option>
        <option value="disk">Disk %</option>
        <option value="ha_health">HA health</option>
        <option value="service_status">Service status</option>
        <option value="custom">Custom…</option>
      </select>
      {!isKnown && (
        <input value={condition.metric} onChange={e => onChange({ ...condition, metric: e.target.value })} placeholder="Metric name" style={{ ...sel, flex: 1, minWidth: 110 }} />
      )}
      <select
        value={condition.comparator}
        onChange={e => onChange({ ...condition, comparator: e.target.value as PolicyCondition["comparator"] })}
        style={{ ...sel, flex: "0 0 110px" }}
      >
        <option value="above">above</option>
        <option value="below">below</option>
        <option value="equals">equals</option>
        <option value="contains">contains</option>
      </select>
      <input
        value={String(condition.threshold)}
        onChange={e => onChange({ ...condition, threshold: e.target.value })}
        placeholder="Threshold"
        style={{ ...sel, flex: "0 0 100px" }}
      />
      <span style={{ fontSize: 11, color: J.textMuted }}>for</span>
      <input
        type="number"
        min={0}
        value={condition.duration_sec}
        onChange={e => onChange({ ...condition, duration_sec: Math.max(0, Number(e.target.value) || 0) })}
        style={{ ...sel, flex: "0 0 80px" }}
      />
      <span style={{ fontSize: 11, color: J.textMuted }}>sec</span>
    </div>
  );
}

function PolicyForm({ draft, onChange, onSave, onCancel, saving, isEdit, J }: {
  draft: PolicyDraft;
  onChange: (d: PolicyDraft) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
  isEdit: boolean;
  J: ReturnType<typeof useJ>;
}) {
  const inp = fieldInput(J);
  const label = fieldLabel(J);
  const canSave = draft.name.trim() !== "" && draft.condition.metric.trim() !== "" && !saving;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 10 }}>
        <div>
          <span style={label}>Name</span>
          <input value={draft.name} onChange={e => onChange({ ...draft, name: e.target.value })} placeholder="Policy name" style={inp} autoFocus />
        </div>
        <div>
          <span style={label}>Domain</span>
          <input value={draft.domain} onChange={e => onChange({ ...draft, domain: e.target.value })} placeholder="system" style={inp} />
        </div>
      </div>

      <div>
        <span style={label}>Condition</span>
        <ConditionEditor condition={draft.condition} onChange={c => onChange({ ...draft, condition: c })} J={J} />
      </div>

      <div>
        <span style={label}>Action</span>
        <ActionEditor action={draft.action} onChange={a => onChange({ ...draft, action: a })} J={J} />
      </div>

      <div style={{ display: "flex", gap: 18, flexWrap: "wrap", alignItems: "center" }}>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: J.textSec, cursor: "pointer" }}>
          <input type="checkbox" checked={draft.enabled} onChange={e => onChange({ ...draft, enabled: e.target.checked })} />
          Enabled
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: J.textSec, cursor: "pointer" }}>
          <input type="checkbox" checked={draft.dry_run} onChange={e => onChange({ ...draft, dry_run: e.target.checked })} />
          Dry run (log only, don't act)
        </label>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 12, color: J.textSec }}>Cooldown</span>
          <input
            type="number"
            min={60}
            value={draft.cooldown_sec}
            onChange={e => onChange({ ...draft, cooldown_sec: Math.max(60, Number(e.target.value) || 60) })}
            style={{ ...inp, width: 80 }}
          />
          <span style={{ fontSize: 12, color: J.textSec }}>sec</span>
        </div>
      </div>

      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={onSave} disabled={!canSave} style={primaryBtnStyle(J, !canSave)}>
          {saving ? "Saving…" : isEdit ? "Save changes" : "Create policy"}
        </button>
        <button onClick={onCancel} style={btnStyle(J)}>Cancel</button>
      </div>
    </div>
  );
}

function PolicyCard({ policy, onEdit, onDelete, onTest, testResult, J }: {
  policy: AdminPolicy;
  onEdit: () => void;
  onDelete: () => void;
  onTest: () => void;
  testResult?: TestResult;
  J: ReturnType<typeof useJ>;
}) {
  const serviceParam = policy.action.params.service;
  return (
    <div style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6, padding: "13px 16px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: J.text }}>{policy.name}</span>
            <StatusPill text={policy.enabled ? "enabled" : "disabled"} tone={policy.enabled ? "success" : "muted"} J={J} />
            {policy.dry_run && <StatusPill text="dry run" tone="blue" J={J} />}
            <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 3, background: J.bg4, color: J.textSec }}>{policy.domain}</span>
          </div>
          <div style={{ fontSize: 11, color: J.textMuted, marginTop: 4, fontFamily: "monospace" }}>
            IF {policy.condition.metric} {policy.condition.comparator} {String(policy.condition.threshold)}
            {policy.condition.duration_sec > 0 ? ` for ${policy.condition.duration_sec}s` : ""}
            {" → "}{policy.action.type}
            {serviceParam ? `(${String(serviceParam)})` : ""}
          </div>
          <div style={{ fontSize: 10, color: J.textMuted, marginTop: 3 }}>
            Cooldown {policy.cooldown_sec}s · {policy.last_fired_at ? `last fired ${fmtTs(policy.last_fired_at)}` : "never fired"}
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
          <button onClick={onTest} disabled={testResult?.loading} style={{ ...btnStyle(J), opacity: testResult?.loading ? 0.5 : 1 }}>
            {testResult?.loading ? "Testing…" : "Test"}
          </button>
          <button onClick={onEdit} style={btnStyle(J)}>Edit</button>
          <button onClick={onDelete} style={dangerBtnStyle(J)}>Delete</button>
        </div>
      </div>
      {testResult && !testResult.loading && (
        <div style={{
          marginTop: 10, padding: "8px 10px", borderRadius: 4, fontSize: 11,
          background: testResult.error ? J.errorDim : testResult.escalated ? J.warnDim : J.successDim,
          color: testResult.error ? J.error : testResult.escalated ? J.warn : J.success,
          border: `1px solid ${testResult.error ? J.error : testResult.escalated ? J.warn : J.success}30`,
        }}>
          {testResult.error || testResult.event?.message}
        </div>
      )}
    </div>
  );
}

function HistoryPanel({ history, J }: { history: PolicyEvent[]; J: ReturnType<typeof useJ> }) {
  return (
    <div style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6, overflow: "hidden" }}>
      <div style={{ padding: "10px 14px", borderBottom: `1px solid ${J.border}`, background: J.bg1, fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>
        Policy history
      </div>
      {history.length === 0 ? (
        <div style={{ padding: "16px 14px", fontSize: 12, color: J.textMuted }}>No policy events yet.</div>
      ) : (
        <div>
          {history.map((ev, i) => (
            <div key={ev.event_id} style={{
              display: "grid", gridTemplateColumns: "110px 1fr 90px", gap: 10, padding: "8px 14px", alignItems: "start",
              borderBottom: i < history.length - 1 ? `1px solid ${J.border}` : "none",
              background: i % 2 === 1 ? J.bg1 : "transparent",
            }}>
              <div style={{ fontSize: 11, color: J.textMuted, whiteSpace: "nowrap" }}>{fmtTs(ev.timestamp)}</div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 12, color: J.text }}>{ev.message}</div>
                <div style={{ fontSize: 10, color: J.textMuted, marginTop: 2 }}>{ev.policy_name} · {ev.type}</div>
              </div>
              <div style={{ textAlign: "right" }}>
                <StatusPill text={ev.severity} tone={ev.severity === "critical" ? "error" : "muted"} J={J} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StepCard({ step, index, total, onChange, onRemove, onMoveUp, onMoveDown, J }: {
  step: StepDraft;
  index: number;
  total: number;
  onChange: (patch: Partial<StepDraft>) => void;
  onRemove: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  J: ReturnType<typeof useJ>;
}) {
  const inp = fieldInput(J);
  return (
    <div style={{ background: J.bg1, border: `1px solid ${J.border}`, borderRadius: 6, padding: "10px 12px", display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: J.amber }}>Step {index + 1}</span>
        <div style={{ display: "flex", gap: 4 }}>
          <button onClick={onMoveUp} disabled={index === 0} title="Move up" style={{ ...btnStyle(J), padding: "2px 8px", opacity: index === 0 ? 0.35 : 1 }}>↑</button>
          <button onClick={onMoveDown} disabled={index === total - 1} title="Move down" style={{ ...btnStyle(J), padding: "2px 8px", opacity: index === total - 1 ? 0.35 : 1 }}>↓</button>
          <button onClick={onRemove} title="Remove step" style={{ ...dangerBtnStyle(J), padding: "2px 8px" }}>×</button>
        </div>
      </div>
      <input value={step.description} onChange={e => onChange({ description: e.target.value })} placeholder="Step description" style={inp} />
      <ActionEditor action={step.action} onChange={a => onChange({ action: a })} J={J} />
      <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: J.textSec, cursor: "pointer" }}>
        <input type="checkbox" checked={step.requires_confirmation} onChange={e => onChange({ requires_confirmation: e.target.checked })} />
        Requires confirmation before running
      </label>
    </div>
  );
}

function PlaybookForm({ draft, onChange, onSave, onCancel, saving, isEdit, J }: {
  draft: PlaybookDraft;
  onChange: (d: PlaybookDraft) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
  isEdit: boolean;
  J: ReturnType<typeof useJ>;
}) {
  const inp = fieldInput(J);

  const addStep = () => onChange({
    ...draft,
    steps: [...draft.steps, { step_id: `step-${draft.steps.length + 1}`, description: "", action: { type: "noop", params: {} }, requires_confirmation: false }],
  });
  const removeStep = (idx: number) => onChange({ ...draft, steps: draft.steps.filter((_, i) => i !== idx) });
  const moveStep = (idx: number, dir: -1 | 1) => {
    const target = idx + dir;
    if (target < 0 || target >= draft.steps.length) return;
    const next = [...draft.steps];
    [next[idx], next[target]] = [next[target], next[idx]];
    onChange({ ...draft, steps: next });
  };
  const updateStep = (idx: number, patch: Partial<StepDraft>) =>
    onChange({ ...draft, steps: draft.steps.map((s, i) => (i === idx ? { ...s, ...patch } : s)) });

  const canSave = draft.name.trim() !== "" && !saving;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <input value={draft.name} onChange={e => onChange({ ...draft, name: e.target.value })} placeholder="Playbook name" style={inp} autoFocus />
      <input value={draft.description} onChange={e => onChange({ ...draft, description: e.target.value })} placeholder="Description (optional)" style={inp} />
      <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: J.textSec, cursor: "pointer" }}>
        <input type="checkbox" checked={draft.dry_run} onChange={e => onChange({ ...draft, dry_run: e.target.checked })} />
        Default to dry run when executed
      </label>

      <div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
          <span style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>Steps ({draft.steps.length})</span>
          <button onClick={addStep} style={btnStyle(J)}>+ Add step</button>
        </div>
        {draft.steps.length === 0 ? (
          <div style={{ fontSize: 12, color: J.textMuted, padding: "6px 0" }}>No steps yet. Add one above.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {draft.steps.map((step, idx) => (
              <StepCard
                key={idx}
                step={step}
                index={idx}
                total={draft.steps.length}
                onChange={patch => updateStep(idx, patch)}
                onRemove={() => removeStep(idx)}
                onMoveUp={() => moveStep(idx, -1)}
                onMoveDown={() => moveStep(idx, 1)}
                J={J}
              />
            ))}
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={onSave} disabled={!canSave} style={primaryBtnStyle(J, !canSave)}>
          {saving ? "Saving…" : isEdit ? "Save changes" : "Create playbook"}
        </button>
        <button onClick={onCancel} style={btnStyle(J)}>Cancel</button>
      </div>
    </div>
  );
}

function PlaybookCard({ playbook, onEdit, onDelete, onExecute, runs, runsLoading, expanded, onToggleExpand, onResume, resumingId, J }: {
  playbook: AdminPlaybook;
  onEdit: () => void;
  onDelete: () => void;
  onExecute: () => void;
  runs: PlaybookRun[] | undefined;
  runsLoading: boolean;
  expanded: boolean;
  onToggleExpand: () => void;
  onResume: (runId: string) => void;
  resumingId: string | null;
  J: ReturnType<typeof useJ>;
}) {
  return (
    <div style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6, overflow: "hidden" }}>
      <div style={{ padding: "13px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: J.text }}>{playbook.name}</span>
              {playbook.dry_run && <StatusPill text="dry run default" tone="blue" J={J} />}
              <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 3, background: J.bg4, color: J.textSec }}>
                {playbook.steps.length} step{playbook.steps.length !== 1 ? "s" : ""}
              </span>
            </div>
            {playbook.description && <div style={{ fontSize: 11, color: J.textMuted, marginTop: 3 }}>{playbook.description}</div>}
          </div>
          <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
            <button onClick={onExecute} style={primaryBtnStyle(J)}>Execute</button>
            <button onClick={onEdit} style={btnStyle(J)}>Edit</button>
            <button onClick={onDelete} style={dangerBtnStyle(J)}>Delete</button>
            <button onClick={onToggleExpand} style={btnStyle(J)}>{expanded ? "Hide runs" : "Runs"}</button>
          </div>
        </div>
      </div>
      {expanded && (
        <div style={{ borderTop: `1px solid ${J.border}`, background: J.bg1, padding: "10px 16px" }}>
          {runsLoading ? (
            <div style={{ fontSize: 12, color: J.textMuted }}>Loading runs…</div>
          ) : !runs || runs.length === 0 ? (
            <div style={{ fontSize: 12, color: J.textMuted }}>No runs yet.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {runs.map(run => (
                <div key={run.id} style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10,
                  padding: "6px 0", borderBottom: `1px solid ${J.border}`, flexWrap: "wrap",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <StatusPill text={run.status} tone={toneForStatus(run.status)} J={J} />
                    {run.dry_run && <StatusPill text="dry run" tone="blue" J={J} />}
                    <span style={{ fontSize: 11, color: J.textMuted }}>{fmtTs(run.started_at)}</span>
                    <span style={{ fontSize: 10, color: J.textMuted }}>
                      {run.steps.filter(s => s.status === "succeeded" || s.status === "would_execute").length}/{run.steps.length} steps
                    </span>
                  </div>
                  {run.status === "awaiting_confirmation" && (
                    <button
                      onClick={() => onResume(run.id)}
                      disabled={resumingId === run.id}
                      style={{ ...primaryBtnStyle(J, resumingId === run.id), padding: "4px 10px" }}
                    >
                      {resumingId === run.id ? "Resuming…" : "Resume"}
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ExecuteDialog({ playbook, dryRun, setDryRun, onRun, running, run, onResume, resuming, onClose, J }: {
  playbook: AdminPlaybook;
  dryRun: boolean;
  setDryRun: (v: boolean) => void;
  onRun: () => void;
  running: boolean;
  run: PlaybookRun | null;
  onResume: () => void;
  resuming: boolean;
  onClose: () => void;
  J: ReturnType<typeof useJ>;
}) {
  return (
    <OverlayDialog
      title={`Execute "${playbook.name}"`}
      eyebrow="Playbook"
      onClose={onClose}
      actions={
        <>
          <button onClick={onClose} style={btnStyle(J)}>Close</button>
          {run?.status === "awaiting_confirmation" ? (
            <button onClick={onResume} disabled={resuming} style={primaryBtnStyle(J, resuming)}>
              {resuming ? "Resuming…" : "Resume & confirm"}
            </button>
          ) : (
            <button onClick={onRun} disabled={running} style={primaryBtnStyle(J, running)}>
              {running ? "Running…" : "Run"}
            </button>
          )}
        </>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: J.textSec, cursor: "pointer" }}>
          <input type="checkbox" checked={dryRun} onChange={e => setDryRun(e.target.checked)} disabled={!!run} />
          Dry run (simulate steps, don't execute)
        </label>
        {playbook.steps.some(s => s.requires_confirmation) && (
          <div style={{ fontSize: 11, color: J.textMuted }}>
            This playbook has steps requiring confirmation — a live run will pause and you can resume it here.
          </div>
        )}
        {run && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 12, color: J.text, fontWeight: 600 }}>Run status:</span>
              <StatusPill text={run.status} tone={toneForStatus(run.status)} J={J} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {run.steps.map(step => (
                <div key={step.step_id} style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between", padding: "5px 8px",
                  borderRadius: 4, background: J.bg3, border: `1px solid ${J.border}`,
                }}>
                  <span style={{ fontSize: 12, color: J.text }}>{step.step_id}</span>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    {step.error && <span style={{ fontSize: 10, color: J.error }}>{step.error}</span>}
                    <StatusPill text={step.status} tone={toneForStatus(step.status)} J={J} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </OverlayDialog>
  );
}

export function PoliciesPage() {
  const J = useJ();
  const [tab, setTab] = useState<"policies" | "playbooks">("policies");

  const [policies, setPolicies] = useState<AdminPolicy[]>([]);
  const [playbooks, setPlaybooks] = useState<AdminPlaybook[]>([]);
  const [history, setHistory] = useState<PolicyEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("");

  const load = useCallback(async () => {
    const [pd, pbd, hd] = await Promise.all([
      fetchAdminPolicies(),
      fetchAdminPlaybooks(),
      fetchAdminPolicyHistory(100),
    ]);
    setPolicies(pd.policies || []);
    setPlaybooks(pbd.playbooks || []);
    setHistory(hd.events || []);
    setLoading(false);
  }, []);

  useEffect(() => { load().catch(() => setLoading(false)); }, [load]);
  useEffect(() => {
    if (!status) return;
    const id = setTimeout(() => setStatus(""), 4000);
    return () => clearTimeout(id);
  }, [status]);

  // ── Policy form state ──
  const [policyFormOpen, setPolicyFormOpen] = useState(false);
  const [editingPolicyId, setEditingPolicyId] = useState<string | null>(null);
  const [policyDraft, setPolicyDraft] = useState<PolicyDraft>(emptyPolicyDraft());
  const [savingPolicy, setSavingPolicy] = useState(false);
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({});

  const openCreatePolicy = () => { setEditingPolicyId(null); setPolicyDraft(emptyPolicyDraft()); setPolicyFormOpen(true); };
  const openEditPolicy = (p: AdminPolicy) => { setEditingPolicyId(p.id); setPolicyDraft(policyToDraft(p)); setPolicyFormOpen(true); };
  const closePolicyForm = () => { setPolicyFormOpen(false); setEditingPolicyId(null); };

  const savePolicy = async () => {
    setSavingPolicy(true);
    try {
      if (editingPolicyId) await updateAdminPolicy(editingPolicyId, policyDraft);
      else await createAdminPolicy(policyDraft);
      setStatus(editingPolicyId ? "Policy updated." : "Policy created.");
      closePolicyForm();
      await load();
    } catch (e) {
      setStatus(`Error: ${e instanceof Error ? e.message : "Failed to save policy."}`);
    } finally {
      setSavingPolicy(false);
    }
  };

  const removePolicy = async (p: AdminPolicy) => {
    if (!window.confirm(`Delete policy "${p.name}"?`)) return;
    try { await deleteAdminPolicy(p.id); setStatus("Policy deleted."); await load(); }
    catch (e) { setStatus(`Error: ${e instanceof Error ? e.message : "Failed to delete policy."}`); }
  };

  const runTest = async (p: AdminPolicy) => {
    setTestResults(cur => ({ ...cur, [p.id]: { loading: true } }));
    try {
      const res = await testAdminPolicy(p.id);
      setTestResults(cur => ({ ...cur, [p.id]: { event: res.event, escalated: res.escalated } }));
      const hd = await fetchAdminPolicyHistory(100);
      setHistory(hd.events || []);
    } catch (e) {
      setTestResults(cur => ({ ...cur, [p.id]: { error: e instanceof Error ? e.message : "Test failed." } }));
    }
  };

  // ── Playbook form state ──
  const [playbookFormOpen, setPlaybookFormOpen] = useState(false);
  const [editingPlaybookId, setEditingPlaybookId] = useState<string | null>(null);
  const [playbookDraft, setPlaybookDraft] = useState<PlaybookDraft>(emptyPlaybookDraft());
  const [savingPlaybook, setSavingPlaybook] = useState(false);

  const openCreatePlaybook = () => { setEditingPlaybookId(null); setPlaybookDraft(emptyPlaybookDraft()); setPlaybookFormOpen(true); };
  const openEditPlaybook = (pb: AdminPlaybook) => { setEditingPlaybookId(pb.id); setPlaybookDraft(playbookToDraft(pb)); setPlaybookFormOpen(true); };
  const closePlaybookForm = () => { setPlaybookFormOpen(false); setEditingPlaybookId(null); };

  const savePlaybook = async () => {
    setSavingPlaybook(true);
    const payload: { name: string; description: string; dry_run: boolean; steps: AdminPlaybookStepInput[] } = {
      name: playbookDraft.name,
      description: playbookDraft.description,
      dry_run: playbookDraft.dry_run,
      steps: playbookDraft.steps.map(s => ({
        step_id: s.step_id, description: s.description, action: s.action, requires_confirmation: s.requires_confirmation,
      })),
    };
    try {
      if (editingPlaybookId) await updateAdminPlaybook(editingPlaybookId, payload);
      else await createAdminPlaybook(payload);
      setStatus(editingPlaybookId ? "Playbook updated." : "Playbook created.");
      closePlaybookForm();
      await load();
    } catch (e) {
      setStatus(`Error: ${e instanceof Error ? e.message : "Failed to save playbook."}`);
    } finally {
      setSavingPlaybook(false);
    }
  };

  const removePlaybook = async (pb: AdminPlaybook) => {
    if (!window.confirm(`Delete playbook "${pb.name}"?`)) return;
    try { await deleteAdminPlaybook(pb.id); setStatus("Playbook deleted."); await load(); }
    catch (e) { setStatus(`Error: ${e instanceof Error ? e.message : "Failed to delete playbook."}`); }
  };

  // ── Runs / expand state ──
  const [expandedPlaybookId, setExpandedPlaybookId] = useState<string | null>(null);
  const [runsByPlaybook, setRunsByPlaybook] = useState<Record<string, PlaybookRun[]>>({});
  const [runsLoading, setRunsLoading] = useState(false);
  const [resumingRunId, setResumingRunId] = useState<string | null>(null);

  const toggleExpand = async (pb: AdminPlaybook) => {
    if (expandedPlaybookId === pb.id) { setExpandedPlaybookId(null); return; }
    setExpandedPlaybookId(pb.id);
    setRunsLoading(true);
    try {
      const rd = await fetchAdminPlaybookRuns(pb.id);
      setRunsByPlaybook(cur => ({ ...cur, [pb.id]: rd.runs || [] }));
    } catch {
      // leave panel showing empty state
    } finally {
      setRunsLoading(false);
    }
  };

  const resumeRunInList = async (runId: string, playbookId: string) => {
    setResumingRunId(runId);
    try {
      await resumeAdminPlaybookRun(runId, true);
      const rd = await fetchAdminPlaybookRuns(playbookId);
      setRunsByPlaybook(cur => ({ ...cur, [playbookId]: rd.runs || [] }));
    } catch (e) {
      setStatus(`Error: ${e instanceof Error ? e.message : "Failed to resume run."}`);
    } finally {
      setResumingRunId(null);
    }
  };

  // ── Execute dialog state ──
  const [executePlaybook, setExecutePlaybook] = useState<AdminPlaybook | null>(null);
  const [executeDryRun, setExecuteDryRun] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [executeResult, setExecuteResult] = useState<PlaybookRun | null>(null);
  const [resumingDialog, setResumingDialog] = useState(false);

  const openExecuteDialog = (pb: AdminPlaybook) => { setExecutePlaybook(pb); setExecuteDryRun(pb.dry_run); setExecuteResult(null); };
  const closeExecuteDialog = () => { setExecutePlaybook(null); setExecuteResult(null); };

  const refreshExpandedRuns = async (playbookId: string) => {
    if (expandedPlaybookId !== playbookId) return;
    const rd = await fetchAdminPlaybookRuns(playbookId);
    setRunsByPlaybook(cur => ({ ...cur, [playbookId]: rd.runs || [] }));
  };

  const runExecute = async () => {
    if (!executePlaybook) return;
    setExecuting(true);
    try {
      const res = await executeAdminPlaybook(executePlaybook.id, executeDryRun);
      setExecuteResult(res.run);
      await load();
      await refreshExpandedRuns(executePlaybook.id);
    } catch (e) {
      setStatus(`Error: ${e instanceof Error ? e.message : "Failed to execute playbook."}`);
    } finally {
      setExecuting(false);
    }
  };

  const resumeExecuteDialog = async () => {
    if (!executeResult) return;
    setResumingDialog(true);
    try {
      const res = await resumeAdminPlaybookRun(executeResult.id, true);
      setExecuteResult(res.run);
      if (executePlaybook) await refreshExpandedRuns(executePlaybook.id);
    } catch (e) {
      setStatus(`Error: ${e instanceof Error ? e.message : "Failed to resume run."}`);
    } finally {
      setResumingDialog(false);
    }
  };

  const card: React.CSSProperties = { background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6 };
  const eyebrow: React.CSSProperties = { fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" };

  if (loading) {
    return <div style={{ padding: 40, color: J.textSec, fontSize: 13 }}>Loading policies…</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>

      {/* ── Metrics ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 10 }}>
        {[
          { label: "Policies", value: policies.length },
          { label: "Enabled", value: policies.filter(p => p.enabled).length },
          { label: "Playbooks", value: playbooks.length },
          { label: "History events", value: history.length },
        ].map(({ label, value }) => (
          <div key={label} style={{ ...card, padding: "12px 16px" }}>
            <div style={{ ...eyebrow, marginBottom: 4 }}>{label}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: J.text }}>{value}</div>
          </div>
        ))}
      </div>

      {/* ── Tabs ── */}
      <div style={{ display: "flex", alignItems: "center", borderBottom: `1px solid ${J.border}` }}>
        {(["policies", "playbooks"] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: "8px 18px", fontSize: 13, fontWeight: 600, cursor: "pointer",
            background: tab === t ? J.amberGlow : "transparent",
            color: tab === t ? J.amber : J.textSec,
            border: "none", borderBottom: tab === t ? `2px solid ${J.amber}` : "2px solid transparent",
            textTransform: "capitalize",
          }}>{t}</button>
        ))}
        {status && <span style={{ marginLeft: "auto", fontSize: 11, color: status.startsWith("Error") ? J.error : J.success }}>{status}</span>}
      </div>

      {tab === "policies" ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button onClick={policyFormOpen && !editingPolicyId ? closePolicyForm : openCreatePolicy} style={primaryBtnStyle(J)}>
              {policyFormOpen && !editingPolicyId ? "Cancel" : "+ New policy"}
            </button>
          </div>

          {policyFormOpen && (
            <div style={{ ...card, padding: "16px 18px" }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: J.text, marginBottom: 12 }}>
                {editingPolicyId ? "Edit policy" : "Create policy"}
              </div>
              <PolicyForm
                draft={policyDraft}
                onChange={setPolicyDraft}
                onSave={() => void savePolicy()}
                onCancel={closePolicyForm}
                saving={savingPolicy}
                isEdit={!!editingPolicyId}
                J={J}
              />
            </div>
          )}

          {policies.length === 0 ? (
            <div style={{ ...card, padding: "20px 18px", color: J.textMuted, fontSize: 12 }}>
              No policies yet. Create one above to have JARVIS self-heal a condition automatically.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {policies.map(p => (
                <PolicyCard
                  key={p.id}
                  policy={p}
                  onEdit={() => openEditPolicy(p)}
                  onDelete={() => void removePolicy(p)}
                  onTest={() => void runTest(p)}
                  testResult={testResults[p.id]}
                  J={J}
                />
              ))}
            </div>
          )}

          <HistoryPanel history={history} J={J} />
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button onClick={playbookFormOpen && !editingPlaybookId ? closePlaybookForm : openCreatePlaybook} style={primaryBtnStyle(J)}>
              {playbookFormOpen && !editingPlaybookId ? "Cancel" : "+ New playbook"}
            </button>
          </div>

          {playbookFormOpen && (
            <div style={{ ...card, padding: "16px 18px" }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: J.text, marginBottom: 12 }}>
                {editingPlaybookId ? "Edit playbook" : "Create playbook"}
              </div>
              <PlaybookForm
                draft={playbookDraft}
                onChange={setPlaybookDraft}
                onSave={() => void savePlaybook()}
                onCancel={closePlaybookForm}
                saving={savingPlaybook}
                isEdit={!!editingPlaybookId}
                J={J}
              />
            </div>
          )}

          {playbooks.length === 0 ? (
            <div style={{ ...card, padding: "20px 18px", color: J.textMuted, fontSize: 12 }}>
              No playbooks yet. Create one above to run a repeatable sequence of maintenance steps.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {playbooks.map(pb => (
                <PlaybookCard
                  key={pb.id}
                  playbook={pb}
                  onEdit={() => openEditPlaybook(pb)}
                  onDelete={() => void removePlaybook(pb)}
                  onExecute={() => openExecuteDialog(pb)}
                  runs={runsByPlaybook[pb.id]}
                  runsLoading={runsLoading && expandedPlaybookId === pb.id}
                  expanded={expandedPlaybookId === pb.id}
                  onToggleExpand={() => void toggleExpand(pb)}
                  onResume={runId => void resumeRunInList(runId, pb.id)}
                  resumingId={resumingRunId}
                  J={J}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {executePlaybook && (
        <ExecuteDialog
          playbook={executePlaybook}
          dryRun={executeDryRun}
          setDryRun={setExecuteDryRun}
          onRun={() => void runExecute()}
          running={executing}
          run={executeResult}
          onResume={() => void resumeExecuteDialog()}
          resuming={resumingDialog}
          onClose={closeExecuteDialog}
          J={J}
        />
      )}
    </div>
  );
}
