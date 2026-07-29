import { useState } from 'react';
import { J, applyTheme, applyAccent, applyCompact, Row, Sel, Toggle, ACCENT_COLORS, IconCheck } from '../../screens/jarvis-shared';
import { getStoredPreferences, setStoredPreferences, getSessionToken, savePreferences, type UserPreferences } from '../api/client';

export function AppearancePanel() {
  const [prefs, setPrefs] = useState<UserPreferences>(() => getStoredPreferences());
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

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
        await savePreferences(prefs);
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
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
      <div style={{ padding: '18px 0 4px' }}>
        <button onClick={() => void handleSave()} disabled={saving} className="j-btn"
          style={{ background: saved ? J.success : J.amber, color: J.bg0, borderRadius: 8, padding: '9px 20px', fontSize: 13, fontWeight: 600, opacity: saving ? 0.7 : 1, transition: 'background .2s' }}>
          <IconCheck size={13} /> {saved ? 'Saved!' : saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  );
}
