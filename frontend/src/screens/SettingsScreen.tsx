import { useState, useEffect } from 'react';
import { J, useJ, applyTheme, applyAccent, applyCompact, StatusBadge, IconSettings, IconMic, IconChat, IconMemory, IconGrid, IconShield, IconCode, IconActivity, IconCheck } from './jarvis-shared';
import { getStoredPreferences, setStoredPreferences, getSessionToken, apiRequest, type UserPreferences } from '../shared/api/client';

type JarvisVoice = { id: string; name: string; lang: string; flag: string };

const CATS = [
  { id: 'appearance',   label: 'Appearance',   icon: <IconActivity size={13} /> },
  { id: 'chat',         label: 'Chat',         icon: <IconChat size={13} /> },
  { id: 'voice',        label: 'Voice',        icon: <IconMic size={13} /> },
  { id: 'integrations', label: 'Integrations', icon: <IconGrid size={13} /> },
  { id: 'security',     label: 'Security',     icon: <IconShield size={13} /> },
  { id: 'developer',    label: 'Developer',    icon: <IconCode size={13} /> },
];

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button onClick={() => onChange(!on)}
      style={{ width: 38, height: 21, borderRadius: 11, background: on ? J.amber : J.bg4, border: `1px solid ${on ? J.amber : J.border}`, cursor: 'pointer', position: 'relative', transition: 'all .18s', flexShrink: 0 }}>
      <span style={{ position: 'absolute', top: 3, left: on ? 17 : 3, width: 13, height: 13, borderRadius: '50%', background: on ? J.bg0 : J.textMuted, transition: 'left .18s' }} />
    </button>
  );
}

function Row({ label, desc, children }: { label: string; desc?: string; children?: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '13px 0', borderBottom: `1px solid ${J.border}`, gap: 16 }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 14, color: J.text }}>{label}</div>
        {desc && <div style={{ fontSize: 12, color: J.textMuted, marginTop: 2 }}>{desc}</div>}
      </div>
      {children}
    </div>
  );
}

function Sel({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: Array<{ v: string; l: string }> }) {
  return (
    <select className="j-input" value={value} onChange={e => onChange(e.target.value)}
      style={{ borderRadius: 7, padding: '6px 10px', fontSize: 13, cursor: 'pointer', flexShrink: 0 }}>
      {options.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
    </select>
  );
}

function Field({ label, value, onChange, placeholder, type = 'text', readOnly }: { label: string; value: string; onChange?: (v: string) => void; placeholder?: string; type?: string; readOnly?: boolean }) {
  return (
    <div style={{ padding: '13px 0', borderBottom: `1px solid ${J.border}` }}>
      <div style={{ fontSize: 14, color: J.text, marginBottom: 8 }}>{label}</div>
      <input className="j-input" type={type} value={value} readOnly={readOnly}
        onChange={e => onChange?.(e.target.value)} placeholder={placeholder}
        style={{ width: '100%', borderRadius: 7, padding: '9px 12px', fontSize: 13, opacity: readOnly ? 0.5 : 1 }} />
    </div>
  );
}

function Integration({ name, status, note, icon }: { name: string; status: string; note?: string; icon: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '13px 0', borderBottom: `1px solid ${J.border}` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ width: 36, height: 36, borderRadius: 9, background: J.bg3, border: `1px solid ${J.border}`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: J.textSec }}>{icon}</div>
        <div>
          <div style={{ fontSize: 14, color: J.text, fontWeight: 500 }}>{name}</div>
          {note && <div style={{ fontSize: 11, color: J.textMuted }}>{note}</div>}
        </div>
      </div>
      <StatusBadge status={status} size="xs" />
    </div>
  );
}

const ACCENT_COLORS = ['#e09a1a', '#5294e8', '#3dba84', '#a855f7', '#e05555', '#f97316'];

export function SettingsScreen() {
  useJ();
  const [cat, setCat] = useState('appearance');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [prefs, setPrefs] = useState<UserPreferences>(() => getStoredPreferences());
  const [voices, setVoices] = useState<JarvisVoice[]>([]);

  useEffect(() => {
    if (getSessionToken()) {
      apiRequest<{ preferences: UserPreferences }>('/auth/me/preferences', { includeUser: true })
        .then(data => {
          const merged = { ...getStoredPreferences(), ...data.preferences };
          setStoredPreferences(merged);
          setPrefs(merged);
        })
        .catch(() => setPrefs(getStoredPreferences()));
    } else {
      setPrefs(getStoredPreferences());
    }
    apiRequest<{ voices: JarvisVoice[] }>('/api/tts/voices')
      .then(data => setVoices(data.voices))
      .catch(() => setVoices([]));
  }, []);

  const set = <K extends keyof UserPreferences>(k: K, v: UserPreferences[K]) => {
    const next = { ...prefs, [k]: v };
    setPrefs(next);
    setStoredPreferences(next);
    if (k === 'theme') applyTheme(v as 'dark' | 'light');
    if (k === 'accent_color') applyAccent(v as string);
    if (k === 'compact_mode') applyCompact(v as boolean);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      setStoredPreferences(prefs);
      if (getSessionToken()) {
        await apiRequest('/auth/me/preferences', { method: 'PUT', includeUser: true, body: prefs });
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    const defaults: UserPreferences = { theme: 'dark', compact_mode: false };
    setPrefs(defaults);
    applyTheme('dark');
  };

  const current = CATS.find(c => c.id === cat);

  const panels: Record<string, React.ReactNode> = {
    appearance: (<>
      <Row label="Theme" desc="Applies immediately">
        <Sel value={prefs.theme || 'dark'} onChange={v => set('theme', v as 'dark' | 'light')}
          options={[{ v: 'dark', l: 'Dark' }, { v: 'light', l: 'Light' }]} />
      </Row>
      <Row label="Accent Color" desc="Saved with preferences">
        <div style={{ display: 'flex', gap: 6 }}>
          {ACCENT_COLORS.map(c => (
            <button key={c} onClick={() => set('accent_color', c)}
              style={{ width: 22, height: 22, borderRadius: '50%', background: c, border: (prefs.accent_color || '#e09a1a') === c ? `2px solid ${J.text}` : '2px solid transparent', cursor: 'pointer', transition: 'border .15s' }} />
          ))}
        </div>
      </Row>
      <Row label="Compact Mode" desc="Reduce spacing and element sizes">
        <Toggle on={prefs.compact_mode ?? false} onChange={v => set('compact_mode', v)} />
      </Row>
    </>),

    chat: (<>
      <Row label="Auto-play Voice" desc="Automatically play voice responses">
        <Toggle on={prefs.auto_play_voice ?? false} onChange={v => set('auto_play_voice', v)} />
      </Row>
      <Row label="Chat History" desc="Stored on server — managed per session">
        <span style={{ fontSize: 12, color: J.textMuted }}>Always on</span>
      </Row>
      <Row label="Orb Detail" desc="Canvas animation quality">
        <Sel value={prefs.orb_detail || 'normal'}
          onChange={v => set('orb_detail', v)}
          options={[{ v: 'low', l: 'Low (fast)' }, { v: 'normal', l: 'Normal' }, { v: 'high', l: 'High' }]} />
      </Row>
      <Field label="Location" value={prefs.location || ''}
        onChange={v => set('location', v)} placeholder="City for weather skill (e.g. Munich)" />
    </>),

    voice: (<>
      <div style={{ padding: '16px 0', borderBottom: `1px solid ${J.border}` }}>
        <div style={{ fontSize: 14, color: J.text, marginBottom: 8 }}>TTS Voice</div>
        <div style={{ fontSize: 12, color: J.textMuted, marginBottom: 12, lineHeight: 1.5 }}>
          Choose your preferred text-to-speech voice. Applied when the server uses the <strong>edge-tts</strong> provider.
        </div>
        {voices.length === 0 ? (
          <div style={{ fontSize: 12, color: J.textMuted }}>Loading voices…</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {voices.map(v => {
              const selected = (prefs.tts_voice ?? '') === v.id;
              return (
                <button key={v.id} onClick={() => set('tts_voice', v.id)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    background: selected ? J.bg3 : J.bg2,
                    border: `1px solid ${selected ? J.amber : J.border}`,
                    borderRadius: 8, padding: '9px 14px', cursor: 'pointer',
                    textAlign: 'left', transition: 'all .15s',
                  }}>
                  <span style={{ fontSize: 16, lineHeight: 1 }}>{v.flag}</span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, color: J.text, fontWeight: selected ? 600 : 400 }}>{v.name}</div>
                    {v.id && <div style={{ fontSize: 11, color: J.textMuted, fontFamily: 'JetBrains Mono,monospace' }}>{v.id}</div>}
                  </div>
                  {selected && <span style={{ fontSize: 11, color: J.amber, fontWeight: 600 }}>ACTIVE</span>}
                </button>
              );
            })}
          </div>
        )}
      </div>
      <div style={{ padding: '16px 0', borderBottom: `1px solid ${J.border}` }}>
        <div style={{ fontSize: 14, color: J.text, marginBottom: 6 }}>Wake Word</div>
        <div style={{ fontSize: 13, color: J.textMuted, lineHeight: 1.6 }}>
          Wake word settings (phrase, enabled state) are configured in the{' '}
          <a href="/dashboard/settings" style={{ color: J.amber, textDecoration: 'underline' }}>Admin Dashboard → Settings</a>.
        </div>
      </div>
      <div style={{ padding: '16px 0', borderBottom: `1px solid ${J.border}` }}>
        <div style={{ fontSize: 14, color: J.text, marginBottom: 6 }}>STT provider</div>
        <div style={{ fontSize: 13, color: J.textMuted, lineHeight: 1.6 }}>
          Speech-to-text engine selection is configured server-side via environment variables (<code>STT_PROVIDER</code>).
        </div>
      </div>
    </>),

    integrations: (<>
      <Integration name="Proxmox" status="configured" note="Via JARVIS_PROXMOX_HOST env var" icon={<IconSettings size={14} />} />
      <Integration name="Home Assistant" status="configured" note="Via JARVIS_HA_BASE_URL env var" icon={<IconSettings size={14} />} />
      <Integration name="GitHub RAG" status="configured" note="Indexes repos for knowledge queries" icon={<IconCode size={14} />} />
      <Integration name="WikiJS RAG" status="configured" note="Indexes wiki pages for knowledge queries" icon={<IconMemory size={14} />} />
      <div style={{ padding: '14px 0', fontSize: 13, color: J.textMuted }}>
        Integrations are configured via environment variables on the server. Use the{' '}
        <a href="/dashboard/settings" style={{ color: J.amber, textDecoration: 'underline' }}>Admin Dashboard</a>{' '}
        to view current configuration.
      </div>
    </>),

    security: (<>
      <Row label="Confirm Critical Actions" desc="Always required for high-risk operations">
        <span style={{ fontSize: 12, color: J.textMuted }}>Always on</span>
      </Row>
      <Row label="Audit Logging" desc="All actions are logged to disk">
        <span style={{ fontSize: 12, color: J.textMuted }}>Always on</span>
      </Row>
      <Row label="Session" desc="Managed server-side, tied to your login">
        <span style={{ fontSize: 12, color: J.textMuted }}>Server-managed</span>
      </Row>
      <div style={{ padding: '14px 0', fontSize: 13, color: J.textMuted }}>
        Security settings like role permissions and emergency stop are managed in the{' '}
        <a href="/dashboard" style={{ color: J.amber, textDecoration: 'underline' }}>Admin Dashboard</a>.
      </div>
    </>),

    developer: (<>
      <Field label="Display Name" value={prefs.display_name || ''}
        onChange={v => set('display_name', v)} placeholder="Your name shown in the interface" />
      <div style={{ padding: '13px 0', borderBottom: `1px solid ${J.border}` }}>
        <div style={{ fontSize: 14, color: J.text, marginBottom: 8 }}>Notes ({(prefs.notes || []).length})</div>
        {(prefs.notes || []).length === 0 ? (
          <div style={{ fontSize: 12, color: J.textMuted }}>No saved notes. Say "remember that…" to Jarvis.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {(prefs.notes || []).map((note, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: J.bg3, borderRadius: 7, padding: '6px 10px', gap: 8 }}>
                <span style={{ fontSize: 12, color: J.textSec, flex: 1 }}>{note}</span>
                <button onClick={() => { const next = (prefs.notes || []).filter((_, j) => j !== i); set('notes', next); }}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: J.textMuted, fontSize: 13, padding: '0 2px', lineHeight: 1 }}
                  onMouseEnter={e => { e.currentTarget.style.color = J.error; }}
                  onMouseLeave={e => { e.currentTarget.style.color = J.textMuted; }}>×</button>
              </div>
            ))}
            <button onClick={() => set('notes', [])}
              style={{ background: 'none', border: `1px solid ${J.border}`, cursor: 'pointer', color: J.textMuted, fontSize: 11, padding: '4px 10px', borderRadius: 6, marginTop: 4, alignSelf: 'flex-start' }}
              onMouseEnter={e => { e.currentTarget.style.color = J.error; e.currentTarget.style.borderColor = J.error; }}
              onMouseLeave={e => { e.currentTarget.style.color = J.textMuted; e.currentTarget.style.borderColor = J.border; }}>
              Clear all notes
            </button>
          </div>
        )}
      </div>
      <div style={{ padding: '13px 0', borderBottom: `1px solid ${J.border}` }}>
        <div style={{ fontSize: 12, color: J.textMuted, marginBottom: 4 }}>Version</div>
        <div style={{ fontFamily: 'JetBrains Mono,monospace', fontSize: 12, color: J.textSec }}>
          Jarvis V1 · Build 2026.04 · local-first
        </div>
      </div>
      <div style={{ padding: '13px 0', borderBottom: `1px solid ${J.border}` }}>
        <div style={{ fontSize: 12, color: J.textMuted, marginBottom: 4 }}>API</div>
        <div style={{ fontFamily: 'JetBrains Mono,monospace', fontSize: 12, color: J.textSec }}>
          {window.location.origin}
        </div>
      </div>
    </>),
  };

  return (
    <div style={{ flex: 1, display: 'flex', overflow: 'hidden', background: J.bg1 }}>
      <div style={{ width: 180, flexShrink: 0, borderRight: `1px solid ${J.border}`, padding: '16px 8px', overflowY: 'auto' }}>
        <div style={{ fontSize: 10, color: J.textMuted, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 600, padding: '2px 10px 10px' }}>Settings</div>
        {CATS.map(c => (
          <button key={c.id} onClick={() => setCat(c.id)}
            style={{ width: '100%', textAlign: 'left', background: cat === c.id ? J.bg2 : 'none', border: cat === c.id ? `1px solid ${J.border}` : '1px solid transparent', color: cat === c.id ? J.text : J.textSec, borderRadius: 8, padding: '8px 11px', fontSize: 13, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2, transition: 'all .1s' }}
            onMouseEnter={e => { if (cat !== c.id) e.currentTarget.style.background = J.bg2; }}
            onMouseLeave={e => { if (cat !== c.id) e.currentTarget.style.background = 'none'; }}>
            <span style={{ color: cat === c.id ? J.amber : J.textMuted }}>{c.icon}</span>
            {c.label}
          </button>
        ))}
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '28px 36px', maxWidth: 600 }}>
        <h2 style={{ fontSize: 18, fontWeight: 600, color: J.text, marginBottom: 3 }}>{current?.label}</h2>
        <p style={{ fontSize: 13, color: J.textMuted, marginBottom: 24 }}>Configure {current?.label?.toLowerCase()} preferences</p>
        {panels[cat]}
        {['appearance', 'chat', 'voice', 'developer'].includes(cat) && (
          <div style={{ padding: '22px 0 8px', display: 'flex', gap: 9, alignItems: 'center' }}>
            <button onClick={handleSave} disabled={saving} className="j-btn"
              style={{ background: saved ? J.success : J.amber, color: J.bg0, borderRadius: 8, padding: '9px 20px', fontSize: 13, fontWeight: 600, opacity: saving ? 0.7 : 1, transition: 'background .2s' }}>
              <IconCheck size={13} /> {saved ? 'Saved!' : saving ? 'Saving…' : 'Save'}
            </button>
            <button onClick={handleReset} className="j-btn"
              style={{ background: J.bg2, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '9px 16px', fontSize: 13 }}>
              Reset
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
