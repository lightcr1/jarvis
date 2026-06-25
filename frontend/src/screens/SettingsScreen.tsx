import { useState, useEffect, useRef } from 'react';
import { J, useJ, applyTheme, applyAccent, applyCompact, StatusBadge, IconSettings, IconMic, IconChat, IconMemory, IconGrid, IconShield, IconCode, IconActivity, IconCheck, IconVolume, IconKey, IconBell, IconBook } from './jarvis-shared';
import { getStoredPreferences, setStoredPreferences, getSessionToken, isGuestMode, apiRequest, type UserPreferences } from '../shared/api/client';
import { synthesizeSpeech } from '../shared/api/chat';
import { listNotes, createNote, deleteNote, listAliases, createAlias, deleteAlias, clearAllMemory, type MemoryNote, type MemoryAlias } from '../shared/api/memory';
import { fetchMyBilling, fetchMyByokKeys, setByokKey, deleteByokKey, type BillingInfo, type ByokKey } from '../shared/api/billing';
import { OverlayDialog } from '../shared/ui/OverlayDialog';

type IntegrationState = 'checking' | 'online' | 'offline' | 'unconfigured';

type JarvisVoice = { id: string; name: string; lang: string; flag: string };

const CATS = [
  { id: 'appearance',   label: 'Appearance',   icon: <IconActivity size={13} /> },
  { id: 'chat',         label: 'Chat',         icon: <IconChat size={13} /> },
  { id: 'notifications',label: 'Notifications',icon: <IconBell size={13} /> },
  { id: 'briefing',     label: 'Briefing',     icon: <IconBook size={13} /> },
  { id: 'voice',        label: 'Voice',        icon: <IconMic size={13} /> },
  { id: 'memory',       label: 'Memory',       icon: <IconMemory size={13} /> },
  { id: 'billing',      label: 'AI & Billing', icon: <IconKey size={13} /> },
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

function MemoryPanel() {
  useJ();
  const [notes, setNotes] = useState<MemoryNote[]>([]);
  const [aliases, setAliases] = useState<MemoryAlias[]>([]);
  const [loading, setLoading] = useState(true);
  const [noteText, setNoteText] = useState('');
  const [aliasKey, setAliasKey] = useState('');
  const [aliasVal, setAliasVal] = useState('');
  const [addingNote, setAddingNote] = useState(false);
  const [addingAlias, setAddingAlias] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [error, setError] = useState('');
  const isLoggedIn = !!getSessionToken();

  const reload = () => {
    if (!isLoggedIn) { setLoading(false); return; }
    setLoading(true);
    Promise.all([listNotes(), listAliases()])
      .then(([n, a]) => { setNotes(n); setAliases(a); })
      .catch(() => setError('Failed to load memory.'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { reload(); }, []);

  const handleAddNote = async () => {
    const text = noteText.trim();
    if (!text) return;
    setAddingNote(true);
    try {
      const note = await createNote(text);
      setNotes(prev => [...prev, note]);
      setNoteText('');
    } catch {
      setError('Failed to save note.');
    } finally {
      setAddingNote(false);
    }
  };

  const handleDeleteNote = async (id: string) => {
    try {
      await deleteNote(id);
      setNotes(prev => prev.filter(n => n.id !== id));
    } catch {
      setError('Failed to delete note.');
    }
  };

  const handleAddAlias = async () => {
    const key = aliasKey.trim();
    const val = aliasVal.trim();
    if (!key || !val) return;
    setAddingAlias(true);
    try {
      const a = await createAlias(key, val);
      setAliases(prev => [...prev.filter(x => x.alias !== key), a]);
      setAliasKey('');
      setAliasVal('');
    } catch {
      setError('Failed to save alias.');
    } finally {
      setAddingAlias(false);
    }
  };

  const handleDeleteAlias = async (alias: string) => {
    try {
      await deleteAlias(alias);
      setAliases(prev => prev.filter(a => a.alias !== alias));
    } catch {
      setError('Failed to delete alias.');
    }
  };

  const handleClearAll = async () => {
    setClearing(true);
    try {
      await clearAllMemory();
      setNotes([]);
      setAliases([]);
      setShowClearConfirm(false);
    } catch {
      setError('Failed to clear memory.');
    } finally {
      setClearing(false);
    }
  };

  if (!isLoggedIn) {
    return <div style={{ padding: '16px 0', fontSize: 13, color: J.textMuted }}>Memory requires a logged-in account.</div>;
  }

  return (
    <>
      {showClearConfirm && (
        <OverlayDialog
          title="Clear all memory?"
          eyebrow="Destructive action"
          onClose={() => setShowClearConfirm(false)}
          actions={<>
            <button onClick={() => setShowClearConfirm(false)}
              style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 7, padding: '8px 16px', fontSize: 13, cursor: 'pointer' }}>
              Cancel
            </button>
            <button onClick={() => void handleClearAll()} disabled={clearing}
              style={{ background: J.error, border: 'none', color: J.bg0, borderRadius: 7, padding: '8px 16px', fontSize: 13, fontWeight: 600, cursor: clearing ? 'not-allowed' : 'pointer', opacity: clearing ? 0.7 : 1 }}>
              {clearing ? 'Clearing…' : 'Clear all memory'}
            </button>
          </>}
        >
          <p style={{ fontSize: 13, color: J.textSec, margin: 0 }}>
            This will permanently delete all notes and aliases. This action cannot be undone.
          </p>
        </OverlayDialog>
      )}

      {error && (
        <div style={{ background: J.errorDim, border: `1px solid ${J.error}`, borderRadius: 7, padding: '8px 12px', fontSize: 12, color: J.error, marginBottom: 12 }}
          onClick={() => setError('')}>
          {error}
        </div>
      )}

      <div style={{ padding: '4px 0 12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 12, color: J.textMuted }}>
          {loading ? 'Loading…' : `${notes.length} note${notes.length !== 1 ? 's' : ''} · ${aliases.length} alias${aliases.length !== 1 ? 'es' : ''}`}
        </span>
        <button onClick={() => setShowClearConfirm(true)}
          style={{ background: 'none', border: `1px solid ${J.error}`, color: J.error, borderRadius: 6, padding: '4px 12px', fontSize: 12, cursor: 'pointer', opacity: 0.8 }}
          onMouseEnter={e => { e.currentTarget.style.opacity = '1'; }}
          onMouseLeave={e => { e.currentTarget.style.opacity = '0.8'; }}>
          Clear all
        </button>
      </div>

      <div style={{ padding: '13px 0', borderBottom: `1px solid ${J.border}` }}>
        <div style={{ fontSize: 14, color: J.text, fontWeight: 500, marginBottom: 10 }}>Notes</div>
        {loading ? (
          <div style={{ fontSize: 12, color: J.textMuted }}>Loading…</div>
        ) : notes.length === 0 ? (
          <div style={{ fontSize: 12, color: J.textMuted }}>No notes. Say "remember that…" to add one.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginBottom: 10 }}>
            {notes.map(n => (
              <div key={n.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, background: J.bg3, borderRadius: 7, padding: '7px 10px', border: `1px solid ${J.border}` }}>
                <span style={{ fontSize: 12, color: J.textSec, flex: 1, lineHeight: 1.5 }}>{n.text}</span>
                <button onClick={() => void handleDeleteNote(n.id)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: J.textMuted, fontSize: 14, lineHeight: 1, padding: '0 2px', flexShrink: 0 }}
                  onMouseEnter={e => { e.currentTarget.style.color = J.error; }}
                  onMouseLeave={e => { e.currentTarget.style.color = J.textMuted; }}>
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          <input className="j-input" value={noteText} onChange={e => setNoteText(e.target.value)}
            placeholder="Add a note…"
            onKeyDown={e => { if (e.key === 'Enter') void handleAddNote(); }}
            style={{ flex: 1, borderRadius: 7, padding: '8px 11px', fontSize: 13 }} />
          <button onClick={() => void handleAddNote()} disabled={addingNote || !noteText.trim()}
            style={{ background: J.amber, color: J.bg0, border: 'none', borderRadius: 7, padding: '8px 16px', fontSize: 13, fontWeight: 600, cursor: addingNote || !noteText.trim() ? 'not-allowed' : 'pointer', opacity: addingNote || !noteText.trim() ? 0.6 : 1, flexShrink: 0 }}>
            {addingNote ? '…' : 'Add'}
          </button>
        </div>
      </div>

      <div style={{ padding: '13px 0', borderBottom: `1px solid ${J.border}` }}>
        <div style={{ fontSize: 14, color: J.text, fontWeight: 500, marginBottom: 10 }}>Aliases</div>
        <div style={{ fontSize: 12, color: J.textMuted, marginBottom: 10 }}>Key → value mappings JARVIS will remember about you.</div>
        {loading ? (
          <div style={{ fontSize: 12, color: J.textMuted }}>Loading…</div>
        ) : aliases.length === 0 ? (
          <div style={{ fontSize: 12, color: J.textMuted }}>{'No aliases. Say "remember <key> is <value>" to add one.'}</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginBottom: 10 }}>
            {aliases.map(a => (
              <div key={a.alias} style={{ display: 'flex', alignItems: 'center', gap: 8, background: J.bg3, borderRadius: 7, padding: '7px 10px', border: `1px solid ${J.border}` }}>
                <span style={{ fontSize: 12, color: J.amber, fontFamily: 'JetBrains Mono,monospace', flexShrink: 0 }}>{a.alias}</span>
                <span style={{ fontSize: 12, color: J.textMuted, flexShrink: 0 }}>→</span>
                <span style={{ fontSize: 12, color: J.textSec, flex: 1 }}>{a.target}</span>
                <button onClick={() => void handleDeleteAlias(a.alias)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: J.textMuted, fontSize: 14, lineHeight: 1, padding: '0 2px', flexShrink: 0 }}
                  onMouseEnter={e => { e.currentTarget.style.color = J.error; }}
                  onMouseLeave={e => { e.currentTarget.style.color = J.textMuted; }}>
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
          <input className="j-input" value={aliasKey} onChange={e => setAliasKey(e.target.value)}
            placeholder="Key (e.g. city)"
            style={{ flex: '1 1 100px', minWidth: 80, borderRadius: 7, padding: '8px 11px', fontSize: 13 }} />
          <input className="j-input" value={aliasVal} onChange={e => setAliasVal(e.target.value)}
            placeholder="Value (e.g. Berlin)"
            onKeyDown={e => { if (e.key === 'Enter') void handleAddAlias(); }}
            style={{ flex: '2 1 140px', minWidth: 100, borderRadius: 7, padding: '8px 11px', fontSize: 13 }} />
          <button onClick={() => void handleAddAlias()} disabled={addingAlias || !aliasKey.trim() || !aliasVal.trim()}
            style={{ background: J.amber, color: J.bg0, border: 'none', borderRadius: 7, padding: '8px 16px', fontSize: 13, fontWeight: 600, cursor: addingAlias || !aliasKey.trim() || !aliasVal.trim() ? 'not-allowed' : 'pointer', opacity: addingAlias || !aliasKey.trim() || !aliasVal.trim() ? 0.6 : 1, flexShrink: 0 }}>
            {addingAlias ? '…' : 'Add'}
          </button>
        </div>
      </div>
    </>
  );
}

function SecurityPanel() {
  const [cur, setCur] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [state, setState] = useState<'idle' | 'saving' | 'ok' | 'error'>('idle');
  const [errMsg, setErrMsg] = useState('');
  const isLoggedIn = !!getSessionToken();

  const handleChange = async () => {
    if (!cur || !next) { setState('error'); setErrMsg('Fill in all fields.'); return; }
    if (next.length < 6) { setState('error'); setErrMsg('New password must be at least 6 characters.'); return; }
    if (next !== confirm) { setState('error'); setErrMsg('New passwords do not match.'); return; }
    setState('saving');
    try {
      await apiRequest('/auth/me/password', { method: 'PUT', includeUser: true, body: { current_password: cur, new_password: next } });
      setState('ok');
      setCur(''); setNext(''); setConfirm('');
      setTimeout(() => setState('idle'), 3000);
    } catch (e) {
      setState('error');
      setErrMsg((e as Error).message || 'Failed to change password.');
    }
  };

  return (<>
    <Row label="Confirm Critical Actions" desc="Always required for high-risk operations">
      <span style={{ fontSize: 12, color: J.textMuted }}>Always on</span>
    </Row>
    <Row label="Audit Logging" desc="All actions are logged to disk">
      <span style={{ fontSize: 12, color: J.textMuted }}>Always on</span>
    </Row>
    <Row label="Session" desc="Managed server-side, tied to your login">
      <span style={{ fontSize: 12, color: J.textMuted }}>Server-managed</span>
    </Row>
    {isLoggedIn && (
      <div style={{ padding: '16px 0', borderBottom: `1px solid ${J.border}` }}>
        <div style={{ fontSize: 14, color: J.text, marginBottom: 4 }}>Change Password</div>
        <div style={{ fontSize: 12, color: J.textMuted, marginBottom: 14 }}>Update your account password.</div>
        {state === 'error' && (
          <div style={{ background: J.errorDim, border: `1px solid rgba(224,85,85,0.2)`, borderRadius: 7, padding: '8px 12px', fontSize: 12, color: J.error, marginBottom: 10 }}>{errMsg}</div>
        )}
        {state === 'ok' && (
          <div style={{ background: J.successDim, border: `1px solid rgba(61,186,132,0.2)`, borderRadius: 7, padding: '8px 12px', fontSize: 12, color: J.success, marginBottom: 10 }}>Password changed successfully.</div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <input className="j-input" type="password" placeholder="Current password" value={cur} onChange={e => { setCur(e.target.value); setState('idle'); }} style={{ borderRadius: 7, padding: '9px 12px', fontSize: 13 }} />
          <input className="j-input" type="password" placeholder="New password (min 6 chars)" value={next} onChange={e => { setNext(e.target.value); setState('idle'); }} style={{ borderRadius: 7, padding: '9px 12px', fontSize: 13 }} />
          <input className="j-input" type="password" placeholder="Confirm new password" value={confirm} onChange={e => { setConfirm(e.target.value); setState('idle'); }} style={{ borderRadius: 7, padding: '9px 12px', fontSize: 13 }} />
          <button onClick={() => void handleChange()} disabled={state === 'saving'} className="j-btn"
            style={{ alignSelf: 'flex-start', background: state === 'ok' ? J.success : J.amber, color: J.bg0, borderRadius: 7, padding: '8px 18px', fontSize: 13, fontWeight: 600, opacity: state === 'saving' ? 0.7 : 1 }}>
            {state === 'saving' ? 'Saving…' : state === 'ok' ? '✓ Changed' : 'Change password'}
          </button>
        </div>
      </div>
    )}
    <div style={{ padding: '14px 0', fontSize: 13, color: J.textMuted }}>
      Role permissions and emergency stop are managed in the{' '}
      <a href="/dashboard" style={{ color: J.amber, textDecoration: 'underline' }}>Admin Dashboard</a>.
    </div>
  </>);
}

const BYOK_PROVIDERS = ['openrouter', 'anthropic', 'openai', 'gemini', 'mistral', 'deepseek'] as const;

function AIBillingPanel() {
  useJ();
  const isLoggedIn = !!getSessionToken();
  const [billing, setBilling] = useState<BillingInfo | null>(null);
  const [byokKeys, setByokKeys] = useState<ByokKey[]>([]);
  const [keyInputs, setKeyInputs] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [error, setError] = useState('');

  const reload = () => {
    if (!isLoggedIn) return;
    Promise.all([fetchMyBilling(), fetchMyByokKeys()])
      .then(([b, k]) => { setBilling(b); setByokKeys(k.keys); })
      .catch(() => setError('Failed to load billing info.'));
  };

  useEffect(() => { reload(); }, []);

  const handleSetKey = async (provider: string) => {
    const key = (keyInputs[provider] || '').trim();
    if (!key) return;
    setSaving(p => ({ ...p, [provider]: true }));
    try {
      const res = await setByokKey(provider, key);
      setByokKeys(prev => [...prev.filter(k => k.provider !== provider), res.key]);
      setKeyInputs(p => ({ ...p, [provider]: '' }));
    } catch {
      setError(`Failed to save key for ${provider}.`);
    } finally {
      setSaving(p => ({ ...p, [provider]: false }));
    }
  };

  const handleDeleteKey = async (provider: string) => {
    setSaving(p => ({ ...p, [provider]: true }));
    try {
      await deleteByokKey(provider);
      setByokKeys(prev => prev.filter(k => k.provider !== provider));
    } catch {
      setError(`Failed to delete key for ${provider}.`);
    } finally {
      setSaving(p => ({ ...p, [provider]: false }));
    }
  };

  if (!isLoggedIn) {
    return (
      <div style={{ padding: '18px 0', color: J.textMuted, fontSize: 13 }}>
        AI Billing requires a logged-in account.
      </div>
    );
  }

  return (
    <>
      {error && (
        <div style={{ padding: '10px 14px', borderRadius: 7, background: J.errorDim ?? J.bg3, border: `1px solid ${J.error}`, color: J.error, fontSize: 13, marginBottom: 12 }}>
          {error}
          <button onClick={() => setError('')} style={{ marginLeft: 10, background: 'none', border: 'none', cursor: 'pointer', color: J.error, fontSize: 13 }}>×</button>
        </div>
      )}

      {/* Balance */}
      <div style={{ padding: '13px 0', borderBottom: `1px solid ${J.border}` }}>
        <div style={{ fontSize: 14, color: J.text, marginBottom: 4 }}>Balance</div>
        <div style={{ fontFamily: 'JetBrains Mono,monospace', fontSize: 22, fontWeight: 700, color: J.amber }}>
          CHF {billing ? billing.balance_chf.toFixed(4) : '—'}
        </div>
        {billing && billing.balance_chf < 1.0 && (
          <div style={{ marginTop: 8, padding: '8px 12px', borderRadius: 6, background: J.amberDim, border: `1px solid ${J.amber}`, color: J.amber, fontSize: 12 }}>
            Balance low. Contact admin to top up.
          </div>
        )}
      </div>

      {/* BYOK section */}
      <div style={{ padding: '13px 0', borderBottom: `1px solid ${J.border}` }}>
        <div style={{ fontSize: 14, color: J.text, marginBottom: 4 }}>API Keys (BYOK)</div>
        <div style={{ fontSize: 12, color: J.textMuted, marginBottom: 12 }}>
          Provide your own API keys to use providers directly. Keys are stored encrypted on the server.
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {BYOK_PROVIDERS.map(provider => {
            const existing = byokKeys.find(k => k.provider === provider);
            const isSaving = saving[provider] ?? false;
            return (
              <div key={provider} style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <div style={{ width: 90, fontSize: 13, color: J.text, fontWeight: 500, flexShrink: 0 }}>{provider}</div>
                {existing ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, flexWrap: 'wrap' }}>
                    <code style={{ fontSize: 11, color: J.textSec, background: J.bg3, padding: '3px 8px', borderRadius: 4, letterSpacing: '0.04em' }}>{existing.masked}</code>
                    <button
                      onClick={() => void handleDeleteKey(provider)}
                      disabled={isSaving}
                      style={{ padding: '4px 10px', fontSize: 11, borderRadius: 5, cursor: 'pointer', background: 'none', border: `1px solid ${J.border}`, color: J.error, opacity: isSaving ? 0.5 : 1 }}
                    >
                      {isSaving ? '…' : 'Delete'}
                    </button>
                  </div>
                ) : (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
                    <input
                      type="password"
                      className="j-input"
                      placeholder={`${provider} API key`}
                      value={keyInputs[provider] ?? ''}
                      onChange={e => setKeyInputs(p => ({ ...p, [provider]: e.target.value }))}
                      style={{ flex: 1, borderRadius: 6, padding: '6px 10px', fontSize: 12 }}
                    />
                    <button
                      onClick={() => void handleSetKey(provider)}
                      disabled={isSaving || !(keyInputs[provider] ?? '').trim()}
                      style={{ padding: '6px 14px', fontSize: 12, borderRadius: 6, cursor: 'pointer', background: J.amber, color: J.bg0, border: 'none', fontWeight: 600, opacity: isSaving || !(keyInputs[provider] ?? '').trim() ? 0.5 : 1 }}
                    >
                      {isSaving ? '…' : 'Set'}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Recent usage */}
      {billing && billing.recent_usage.length > 0 && (
        <div style={{ padding: '13px 0', borderBottom: `1px solid ${J.border}` }}>
          <div style={{ fontSize: 14, color: J.text, marginBottom: 8 }}>Recent Usage</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {(billing.recent_usage as Array<Record<string, unknown>>).slice(0, 5).map((u, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 11, color: J.textSec, padding: '4px 0', borderBottom: `1px solid ${J.border}` }}>
                <span style={{ fontFamily: 'JetBrains Mono,monospace', color: J.textMuted }}>{typeof u['provider'] === 'string' ? u['provider'] : '—'}</span>
                <span style={{ flex: 1 }}>{typeof u['model'] === 'string' ? u['model'] : '—'}</span>
                <span style={{ fontFamily: 'JetBrains Mono,monospace', color: J.amber }}>
                  CHF {typeof u['estimated_cost_chf'] === 'number' ? u['estimated_cost_chf'].toFixed(6) : '0.000000'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {billing && billing.limits && Object.keys(billing.limits).length > 0 && (
        <div style={{ padding: '13px 0' }}>
          <div style={{ fontSize: 14, color: J.text, marginBottom: 8 }}>Spending Limits</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {(['chf_per_day', 'chf_per_month'] as const).map(key => {
              const val = (billing.limits as Record<string, unknown>)[key];
              return (
                <div key={key} style={{ background: J.bg3, borderRadius: 7, padding: '8px 12px', border: `1px solid ${J.border}` }}>
                  <div style={{ fontSize: 10, color: J.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 2 }}>{key.replace(/_/g, ' ')}</div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: J.text }}>
                    {typeof val === 'number' && val > 0 ? `CHF ${val.toFixed(2)}` : 'Unlimited'}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}

export function SettingsScreen() {
  useJ();
  const isGuest = isGuestMode();
  const availableCats = isGuest ? CATS.filter(c => c.id === 'appearance') : CATS;
  const [cat, setCat] = useState('appearance');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [prefs, setPrefs] = useState<UserPreferences>(() => getStoredPreferences());
  const [voices, setVoices] = useState<JarvisVoice[]>([]);
  const [testingVoice, setTestingVoice] = useState(false);
  const [voiceTestErr, setVoiceTestErr] = useState('');
  const [previewingVoice, setPreviewingVoice] = useState<string | null>(null);
  const [intStatus, setIntStatus] = useState<Record<string, IntegrationState>>({
    proxmox: 'checking', ha: 'checking', rag: 'checking',
  });
  const testAudioRef = useRef<HTMLAudioElement | null>(null);
  const previewAudioRef = useRef<HTMLAudioElement | null>(null);

  const handlePreviewVoice = (voiceId: string) => {
    previewAudioRef.current?.pause();
    previewAudioRef.current = null;
    if (previewingVoice === voiceId) { setPreviewingVoice(null); return; }
    setPreviewingVoice(voiceId);
    synthesizeSpeech('Systems nominal. Standing by.', voiceId)
      .then(blob => {
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        previewAudioRef.current = audio;
        audio.onended = () => { URL.revokeObjectURL(url); previewAudioRef.current = null; setPreviewingVoice(null); };
        audio.onerror = () => { URL.revokeObjectURL(url); previewAudioRef.current = null; setPreviewingVoice(null); };
        void audio.play();
      })
      .catch(() => setPreviewingVoice(null));
  };

  const handleTestVoice = () => {
    if (testingVoice) {
      testAudioRef.current?.pause();
      testAudioRef.current = null;
      setTestingVoice(false);
      return;
    }
    setTestingVoice(true);
    setVoiceTestErr('');
    // Pass the currently selected (possibly unsaved) voice as an explicit override
    synthesizeSpeech('Systems nominal. Standing by, sir.', prefs.tts_voice || '')
      .then(blob => {
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        testAudioRef.current = audio;
        audio.onended = () => { URL.revokeObjectURL(url); testAudioRef.current = null; setTestingVoice(false); };
        audio.onerror = () => { URL.revokeObjectURL(url); testAudioRef.current = null; setTestingVoice(false); setVoiceTestErr('Playback failed'); };
        void audio.play();
      })
      .catch(err => { setTestingVoice(false); setVoiceTestErr((err as Error).message || 'Voice synthesis unavailable.'); });
  };

  useEffect(() => {
    if (getSessionToken()) {
      apiRequest<{ preferences: UserPreferences }>('/auth/me/preferences', { includeUser: true })
        .then(data => {
          const local = getStoredPreferences();
          const server = data.preferences;
          // Server values win, except theme — local theme takes priority because the
          // user may have toggled it without hitting Save, and we never want to flash
          // back to dark on Settings open.
          const merged: UserPreferences = { ...local };
          for (const [k, v] of Object.entries(server) as [keyof UserPreferences, UserPreferences[keyof UserPreferences]][]) {
            if (k === 'theme') continue; // always keep local theme
            if (v !== '' && v !== null && v !== undefined) {
              (merged as Record<string, unknown>)[k] = v;
            } else if (!(k in local) || local[k] === undefined) {
              (merged as Record<string, unknown>)[k] = v;
            }
          }
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

    // Check integration status dynamically
    const checkInt = async () => {
      const [px, ha, rag] = await Promise.allSettled([
        apiRequest<{ healthy?: boolean }>('/proxmox/health', { includeUser: true }),
        apiRequest<{ healthy?: boolean }>('/home-assistant/health', { includeUser: true }),
        apiRequest<{ counts?: Record<string, number> }>('/rag/status', { includeUser: true }),
      ]);
      setIntStatus({
        proxmox: px.status === 'fulfilled' ? 'online' : 'offline',
        ha: ha.status === 'fulfilled' ? 'online' : 'offline',
        rag: rag.status === 'fulfilled' ? 'online' : 'offline',
      });
    };
    void checkInt();
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

  const current = availableCats.find(c => c.id === cat);

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
      <Row label="Persona Tone" desc="JARVIS response style">
        <Sel value={prefs.persona_tone || 'formal'}
          onChange={v => set('persona_tone', v as 'formal' | 'casual')}
          options={[{ v: 'formal', l: 'Formal — terse, precise' }, { v: 'casual', l: 'Casual — warmer, conversational' }]} />
      </Row>
      <Field label="Location" value={prefs.location || ''}
        onChange={v => set('location', v)} placeholder="City for weather skill (e.g. Munich)" />
    </>),

    notifications: (<>
      <Row label="In-app alerts" desc="Show alert toasts and badge counter">
        <Toggle on={prefs.notifications_enabled !== false} onChange={v => set('notifications_enabled', v)} />
      </Row>
      <div style={{ padding: '14px 0', fontSize: 13, color: J.textMuted, lineHeight: 1.6 }}>
        When disabled, alert toasts and the notification badge on the Services item will not appear.
      </div>
    </>),

    briefing: (<>
      <Row label="Morning Briefing" desc="Auto-push a briefing at a scheduled time">
        <Toggle on={prefs.morning_briefing_enabled ?? false} onChange={v => set('morning_briefing_enabled', v)} />
      </Row>
      <Field label="Briefing time" value={prefs.morning_briefing_time || '07:00'}
        onChange={v => set('morning_briefing_time', v)} type="time" />
      <div style={{ padding: '8px 0 14px', fontSize: 12, color: J.textMuted, lineHeight: 1.5 }}>
        Requires staying connected to JARVIS at the scheduled time.
      </div>
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
              const previewing = previewingVoice === v.id;
              return (
                <div key={v.id} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <button onClick={() => {
                    const next = { ...prefs, tts_voice: v.id };
                    setPrefs(next);
                    setStoredPreferences(next);
                    if (getSessionToken()) {
                      apiRequest('/auth/me/preferences', { method: 'PUT', includeUser: true, body: next })
                        .catch(() => undefined);
                    }
                  }}
                    style={{
                      flex: 1, display: 'flex', alignItems: 'center', gap: 10,
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
                  <button
                    onClick={e => { e.stopPropagation(); handlePreviewVoice(v.id); }}
                    title="Preview voice"
                    style={{
                      flexShrink: 0, width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: previewing ? J.amberDim : J.bg2,
                      border: `1px solid ${previewing ? J.amber : J.border}`,
                      borderRadius: 7, cursor: 'pointer', fontSize: 13, color: previewing ? J.amber : J.textMuted,
                      transition: 'all .15s',
                    }}>
                    {previewing ? '■' : '▶'}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
      <div style={{ padding: '16px 0', borderBottom: `1px solid ${J.border}` }}>
        <div style={{ fontSize: 14, color: J.text, marginBottom: 8 }}>Test Voice</div>
        <div style={{ fontSize: 12, color: J.textMuted, marginBottom: 12 }}>
          Play a sample phrase using the currently selected voice.
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={handleTestVoice}
            style={{ display: 'flex', alignItems: 'center', gap: 7, background: testingVoice ? J.amberDim : J.bg3, border: `1px solid ${testingVoice ? J.amber : J.border}`, color: testingVoice ? J.amber : J.textSec, borderRadius: 8, padding: '8px 16px', fontSize: 13, cursor: 'pointer', transition: 'all .15s' }}
            onMouseEnter={e => { if (!testingVoice) { e.currentTarget.style.borderColor = J.borderAccent; e.currentTarget.style.color = J.text; } }}
            onMouseLeave={e => { if (!testingVoice) { e.currentTarget.style.borderColor = J.border; e.currentTarget.style.color = J.textSec; } }}>
            <IconVolume size={13} />
            {testingVoice ? 'Stop' : 'Test voice'}
          </button>
          {voiceTestErr && <span style={{ fontSize: 12, color: J.error }}>{voiceTestErr}</span>}
        </div>
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

    memory: (<MemoryPanel />),

    billing: (<AIBillingPanel />),

    integrations: (<>
      <Integration name="Proxmox" status={intStatus.proxmox === 'checking' ? 'checking' : intStatus.proxmox === 'online' ? 'online' : 'offline'} note="Via JARVIS_PROXMOX_HOST env var" icon={<IconSettings size={14} />} />
      <Integration name="Home Assistant" status={intStatus.ha === 'checking' ? 'checking' : intStatus.ha === 'online' ? 'online' : 'offline'} note="Via JARVIS_HA_BASE_URL env var" icon={<IconSettings size={14} />} />
      <Integration name="RAG / Knowledge" status={intStatus.rag === 'checking' ? 'checking' : intStatus.rag === 'online' ? 'active' : 'offline'} note="GitHub repos + WikiJS indexing" icon={<IconCode size={14} />} />
      <div style={{ padding: '14px 0', fontSize: 13, color: J.textMuted }}>
        Integrations are configured via environment variables on the server. Use the{' '}
        <a href="/dashboard/settings" style={{ color: J.amber, textDecoration: 'underline' }}>Admin Dashboard</a>{' '}
        to view current configuration.
      </div>
    </>),

    security: (<SecurityPanel />),

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
        {availableCats.map(c => (
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
        {isGuest && (
          <div style={{ background: J.amberDim, border: `1px solid ${J.borderAccent}`, borderRadius: 10, padding: '12px 16px', marginBottom: 20, fontSize: 13, color: J.amber }}>
            Guest mode — sign in for full settings access.
          </div>
        )}
        <h2 style={{ fontSize: 18, fontWeight: 600, color: J.text, marginBottom: 3 }}>{current?.label}</h2>
        <p style={{ fontSize: 13, color: J.textMuted, marginBottom: 24 }}>Configure {current?.label?.toLowerCase()} preferences</p>
        {panels[cat]}
        {['appearance', 'chat', 'notifications', 'briefing', 'voice', 'developer'].includes(cat) && (
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
