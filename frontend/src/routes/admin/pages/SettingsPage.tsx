import React, { useEffect, useState } from "react";
import { AdminSettings, AdminSettingsPayload, fetchAdminSettings, updateAdminSettings } from "../../../shared/api/admin";

export function SettingsPage() {
  const [settings, setSettings] = useState<AdminSettingsPayload | null>(null);
  const [form, setForm] = useState<AdminSettings | null>(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    fetchAdminSettings().then((payload) => {
      setSettings(payload);
      setForm(payload.settings);
    }).catch(() => undefined);
  }, []);

  if (!settings || !form) return <div className="panel">Loading settings…</div>;

  return (
    <div className="page-stack">
      <div className="dashboard-grid">
        <div className="panel metric-card">
          <div className="eyebrow">Token TTL</div>
          <strong>{form.usage_limits.token_ttl_min}</strong>
        </div>
        <div className="panel metric-card">
          <div className="eyebrow">Max active tokens</div>
          <strong>{form.usage_limits.max_active_tokens}</strong>
        </div>
        <div className="panel metric-card">
          <div className="eyebrow">Wakeword</div>
          <strong>{form.voice.wakeword_enabled ? "on" : "off"}</strong>
        </div>
        <div className="panel metric-card">
          <div className="eyebrow">STT provider</div>
          <strong>{form.voice.stt_provider}</strong>
        </div>
      </div>
      <div className="dashboard-grid">
        <div className="panel span-2">
          <div className="eyebrow">Runtime defaults</div>
          <div className="page-stack">
            <label className="settings-field">
              <span>Token TTL minutes</span>
              <input className="ui-input" type="number" value={form.usage_limits.token_ttl_min} onChange={(e) => setForm({ ...form, usage_limits: { ...form.usage_limits, token_ttl_min: Number(e.target.value) } })} />
            </label>
            <label className="settings-field">
              <span>Max active tokens</span>
              <input className="ui-input" type="number" value={form.usage_limits.max_active_tokens} onChange={(e) => setForm({ ...form, usage_limits: { ...form.usage_limits, max_active_tokens: Number(e.target.value) } })} />
            </label>
            <label className="settings-field">
              <span>Wakeword</span>
              <select className="ui-input" value={String(form.voice.wakeword_enabled)} onChange={(e) => setForm({ ...form, voice: { ...form.voice, wakeword_enabled: e.target.value === "true" } })}>
                <option value="false">wakeword off</option>
                <option value="true">wakeword on</option>
              </select>
            </label>
            <label className="settings-field">
              <span>Wakeword phrase</span>
              <input className="ui-input" value={form.voice.wakeword_phrase} onChange={(e) => setForm({ ...form, voice: { ...form.voice, wakeword_phrase: e.target.value } })} />
            </label>
            <label className="settings-field">
              <span>Speech-to-text provider</span>
              <select className="ui-input" value={form.voice.stt_provider} onChange={(e) => setForm({ ...form, voice: { ...form.voice, stt_provider: e.target.value as "local" | "gemini" } })}>
                <option value="local">local</option>
                <option value="gemini">gemini</option>
              </select>
            </label>
            <button className="ui-button primary" onClick={async () => {
              const payload = await updateAdminSettings(form);
              setSettings(payload);
              setForm(payload.settings);
              setStatus("Settings updated.");
            }}>Save settings</button>
            {status ? <div className="tiny-note">{status}</div> : null}
          </div>
        </div>
        <div className="panel span-2">
          <div className="eyebrow">Voice and wakeword control</div>
          <div className="dashboard-stat-list">
            <div><span>Wakeword activation</span><strong>{form.voice.wakeword_enabled ? "enabled" : "disabled"}</strong></div>
            <div><span>Wakeword phrase</span><strong>{form.voice.wakeword_phrase}</strong></div>
            <div><span>Speech-to-text backend</span><strong>{form.voice.stt_provider}</strong></div>
            <div><span>Where to change it</span><strong>Save in this page</strong></div>
          </div>
          <p className="tiny-note">This page is the runtime control surface for wakeword and voice behavior. Environment variables can still override the effective values shown on the right.</p>
        </div>
      </div>
      <div className="dashboard-grid">
        <div className="panel span-2">
          <div className="eyebrow">Effective values</div>
          <pre>{JSON.stringify(settings.effective, null, 2)}</pre>
        </div>
      </div>
    </div>
  );
}
