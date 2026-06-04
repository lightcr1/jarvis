import { useState, useEffect } from 'react';
import { J, useJ, StatusBadge, Spinner, IconRefresh, IconX, IconChat, IconBulb, IconActivity, IconTherm, IconSettings, IconSearch } from './jarvis-shared';
import {
  fetchHomeAssistantOverview, fetchHomeAssistantEntities, fetchHomeAssistantAreas,
  fetchHomeAssistantAutomations, toggleHomeAssistantAutomation, useHomeAssistantLiveSnapshot, requestHomeAssistantEntityAction,
  fetchHomeAssistantShoppingList, addHomeAssistantShoppingListItem,
  fetchHomeAssistantCalendar, actOnHomeAssistantCalendarItem,
  fetchHomeAssistantInbox, actOnHomeAssistantInboxItem,
  fetchHomeAssistantDiscoveryCandidates, approveHomeAssistantDiscoveryCandidate,
  fetchHomeAssistantControlRequests, confirmHomeAssistantControlRequest,
  type HomeAssistantManagedEntity, type HomeAssistantAreaSummary, type HomeAssistantAutomationRule,
  type HomeAssistantShoppingListItem, type HomeAssistantCalendarItem,
  type HomeAssistantInboxItem, type HomeAssistantDiscoveryCandidate, type HomeAssistantControlRequest,
} from '../shared/api/homeAssistant';
import { setPendingChatPrefill } from '../shared/api/client';

type HaView = 'devices' | 'shopping' | 'calendar' | 'inbox' | 'requests';

const TYPE_ICON: Record<string, JSX.Element> = {
  light:   <IconBulb size={14} />,
  media:   <IconActivity size={14} />,
  climate: <IconTherm size={14} />,
  switch:  <IconActivity size={14} />,
  sensor:  <IconActivity size={14} />,
};

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button onClick={e => { e.stopPropagation(); onChange(!on); }}
      style={{ width: 36, height: 20, borderRadius: 10, background: on ? J.amber : J.bg4, border: `1px solid ${on ? J.amber : J.border}`, cursor: 'pointer', position: 'relative', transition: 'all .18s', flexShrink: 0 }}>
      <span style={{ position: 'absolute', top: 2.5, left: on ? 15.5 : 2.5, width: 13, height: 13, borderRadius: '50%', background: on ? J.bg0 : J.textMuted, transition: 'left .18s' }} />
    </button>
  );
}

function isOnState(d: HomeAssistantManagedEntity) {
  return d.state === 'on' || d.state === 'active';
}

function DeviceCard({ device, onClick }: { device: HomeAssistantManagedEntity; onClick: (d: HomeAssistantManagedEntity) => void }) {
  const [on, setOn] = useState(isOnState(device));
  const [busy, setBusy] = useState(false);
  const isAvailable = device.available !== false;
  useEffect(() => { setOn(isOnState(device)); }, [device.state]);

  const handleToggle = async (next: boolean) => {
    setOn(next);
    setBusy(true);
    try {
      await requestHomeAssistantEntityAction(device.entity_id, { action: next ? 'turn_on' : 'turn_off' });
    } catch {
      setOn(!next); // revert on failure
    } finally {
      setBusy(false);
    }
  };

  return (
    <div onClick={() => onClick(device)}
      style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 11, padding: '13px 14px', cursor: 'pointer', transition: 'all .12s', opacity: isAvailable ? 1 : 0.5 }}
      onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.background = J.bg3; (e.currentTarget as HTMLDivElement).style.borderColor = J.borderHover; }}
      onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = J.bg2; (e.currentTarget as HTMLDivElement).style.borderColor = J.border; }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 10 }}>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: on ? J.amberDim : J.bg3, border: `1px solid ${on ? J.borderAccent : J.border}`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: on ? J.amber : J.textMuted }}>
          {TYPE_ICON[device.kind] || <IconActivity size={14} />}
        </div>
        <Toggle on={on} onChange={v => { if (!busy && isAvailable) void handleToggle(v); }} />
      </div>
      <div style={{ fontSize: 13, fontWeight: 500, color: J.text, marginBottom: 2 }}>{device.label}</div>
      <div style={{ fontSize: 11, color: J.textMuted, marginBottom: 5, textTransform: 'capitalize' }}>{device.kind}</div>
      <div style={{ fontSize: 12, color: on ? J.amber : J.textMuted, fontWeight: 500 }}>{device.state || (isAvailable ? 'Unknown' : 'Unavailable')}</div>
    </div>
  );
}

function AreaBtn({ area, active, onClick }: { area: HomeAssistantAreaSummary; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      style={{ width: '100%', textAlign: 'left', background: active ? J.bg2 : 'none', border: active ? `1px solid ${J.border}` : '1px solid transparent', color: active ? J.text : J.textSec, borderRadius: 8, padding: '8px 10px', fontSize: 13, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 2, transition: 'all .1s' }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.background = J.bg2; }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'none'; }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: active ? 500 : 400, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', textTransform: 'capitalize' }}>{area.area}</div>
        <div style={{ fontSize: 11, color: J.textMuted, marginTop: 1 }}>{area.entity_count} devices</div>
      </div>
      {area.unavailable_count > 0 && (
        <span style={{ fontSize: 10, fontWeight: 600, color: J.error, background: J.errorDim, padding: '1px 6px', borderRadius: 4, flexShrink: 0 }}>{area.unavailable_count}</span>
      )}
    </button>
  );
}

function LightSlider({ label, value, min, max, unit, onChange }: { label: string; value: number; min: number; max: number; unit: string; onChange: (v: number) => void }) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: J.textSec, marginBottom: 7 }}>
        <span>{label}</span>
        <span style={{ fontFamily: 'JetBrains Mono,monospace', color: J.amber }}>{value}{unit}</span>
      </div>
      <div style={{ position: 'relative', height: 6, borderRadius: 3, background: J.bg4 }}>
        <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${pct}%`, background: J.amber, borderRadius: 3, transition: 'width .08s' }} />
        <input
          type="range" min={min} max={max} value={value}
          onChange={e => onChange(Number(e.target.value))}
          style={{ position: 'absolute', inset: 0, width: '100%', opacity: 0, cursor: 'pointer', height: '100%' }}
        />
      </div>
    </div>
  );
}

function DeviceDrawer({ device, onClose, onUseInChat }: { device: HomeAssistantManagedEntity; onClose: () => void; onUseInChat: (d: HomeAssistantManagedEntity) => void }) {
  const [on, setOn] = useState(isOnState(device));
  const [busy, setBusy] = useState(false);
  const attrs = (device.metadata as Record<string, unknown>) || {};
  const haAttrs = (attrs.ha_attributes as Record<string, unknown>) || {};

  // Light
  const rawBrightness = typeof haAttrs.brightness === 'number' ? haAttrs.brightness : null;
  const rawColorTemp = typeof haAttrs.color_temp === 'number' ? haAttrs.color_temp : null;
  const colorTempMin = typeof haAttrs.min_mireds === 'number' ? haAttrs.min_mireds : 153;
  const colorTempMax = typeof haAttrs.max_mireds === 'number' ? haAttrs.max_mireds : 500;
  const [brightness, setBrightness] = useState(rawBrightness !== null ? Math.round((rawBrightness / 255) * 100) : 100);
  const [colorTemp, setColorTemp] = useState(rawColorTemp !== null ? rawColorTemp : colorTempMin);

  // Climate
  const rawSetpoint = typeof haAttrs.temperature === 'number' ? haAttrs.temperature : (typeof haAttrs.target_temp_high === 'number' ? haAttrs.target_temp_high : null);
  const rawHvacMode = typeof haAttrs.hvac_mode === 'string' ? haAttrs.hvac_mode : (typeof device.state === 'string' ? device.state : null);
  const hvacModes: string[] = Array.isArray(haAttrs.hvac_modes) ? (haAttrs.hvac_modes as string[]) : [];
  const tempMin = typeof haAttrs.min_temp === 'number' ? haAttrs.min_temp : 15;
  const tempMax = typeof haAttrs.max_temp === 'number' ? haAttrs.max_temp : 35;
  const [setpoint, setSetpoint] = useState(rawSetpoint ?? 20);
  const [hvacMode, setHvacMode] = useState(rawHvacMode ?? '');

  useEffect(() => { setOn(isOnState(device)); }, [device.state]);
  useEffect(() => { if (rawBrightness !== null) setBrightness(Math.round((rawBrightness / 255) * 100)); }, [rawBrightness]);
  useEffect(() => { if (rawColorTemp !== null) setColorTemp(rawColorTemp); }, [rawColorTemp]);
  useEffect(() => { if (rawSetpoint !== null) setSetpoint(rawSetpoint); }, [rawSetpoint]);
  useEffect(() => { if (rawHvacMode !== null) setHvacMode(rawHvacMode); }, [rawHvacMode]);

  const handleToggle = async (next: boolean) => {
    setOn(next);
    setBusy(true);
    try {
      await requestHomeAssistantEntityAction(device.entity_id, { action: next ? 'turn_on' : 'turn_off' });
    } catch {
      setOn(!next);
    } finally {
      setBusy(false);
    }
  };

  const handleBrightness = async (pct: number) => {
    setBrightness(pct);
    try {
      await requestHomeAssistantEntityAction(device.entity_id, { action: 'set_brightness', value: Math.round((pct / 100) * 255) });
    } catch { /* silent */ }
  };

  const handleColorTemp = async (mireds: number) => {
    setColorTemp(mireds);
    try {
      await requestHomeAssistantEntityAction(device.entity_id, { action: 'set_color_temp', value: mireds });
    } catch { /* silent */ }
  };

  // Media
  const rawVolume = typeof haAttrs.volume_level === 'number' ? Math.round(haAttrs.volume_level * 100) : null;
  const rawMuted = typeof haAttrs.is_volume_muted === 'boolean' ? haAttrs.is_volume_muted : false;
  const mediaTitle = typeof haAttrs.media_title === 'string' ? haAttrs.media_title : null;
  const mediaArtist = typeof haAttrs.media_artist === 'string' ? haAttrs.media_artist : null;
  const [volume, setVolume] = useState(rawVolume ?? 50);
  const [muted, setMuted] = useState(rawMuted);
  useEffect(() => { if (rawVolume !== null) setVolume(rawVolume); }, [rawVolume]);
  useEffect(() => { setMuted(rawMuted); }, [rawMuted]);

  const handleSetpoint = async (temp: number) => {
    setSetpoint(temp);
    try {
      await requestHomeAssistantEntityAction(device.entity_id, { action: 'set_temperature', value: temp });
    } catch { /* silent */ }
  };

  const handleVolume = async (pct: number) => {
    setVolume(pct);
    try { await requestHomeAssistantEntityAction(device.entity_id, { action: 'set_volume', value: pct / 100 }); } catch { /* silent */ }
  };

  const handleMediaAction = async (action: string) => {
    try { await requestHomeAssistantEntityAction(device.entity_id, { action }); } catch { /* silent */ }
  };

  const handleHvacMode = async (mode: string) => {
    setHvacMode(mode);
    try {
      await requestHomeAssistantEntityAction(device.entity_id, { action: 'set_hvac_mode', value: mode });
    } catch { /* silent */ }
  };

  const displayAttrs = Object.entries(attrs).filter(([k]) => k !== 'ha_attributes' && k !== 'last_action_value' && k !== 'last_action' && k !== 'last_actor_user_id' && k !== 'last_action_at' && k !== 'last_synced_at' && k !== 'sync_source');

  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 40 }} />
      <div style={{ position: 'fixed', right: 0, top: 0, bottom: 0, width: 340, background: J.bg2, borderLeft: `1px solid ${J.border}`, zIndex: 41, display: 'flex', flexDirection: 'column', animation: 'slideInRight .2s ease' }}>
        <div style={{ padding: '16px 20px', borderBottom: `1px solid ${J.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 600, color: J.text }}>{device.label}</div>
            <div style={{ fontSize: 12, color: J.textMuted, textTransform: 'capitalize', marginTop: 2 }}>{device.kind} · {device.area}</div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: J.textMuted, display: 'flex' }}><IconX size={16} /></button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '18px 20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18, padding: '12px 14px', background: J.bg3, border: `1px solid ${J.border}`, borderRadius: 10 }}>
            <div>
              <StatusBadge status={on ? 'on' : 'off'} />
              <div style={{ fontSize: 11, color: J.textMuted, marginTop: 5, fontFamily: 'JetBrains Mono,monospace' }}>{device.entity_id}</div>
            </div>
            <Toggle on={on} onChange={v => { if (!busy) void handleToggle(v); }} />
          </div>

          {device.kind === 'light' && on && (
            <div style={{ marginBottom: 18, padding: '14px 14px 10px', background: J.bg3, border: `1px solid ${J.border}`, borderRadius: 10 }}>
              <div style={{ fontSize: 10, color: J.textMuted, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 600, marginBottom: 14 }}>Light controls</div>
              <LightSlider label="Brightness" value={brightness} min={1} max={100} unit="%" onChange={v => void handleBrightness(v)} />
              {rawColorTemp !== null && (
                <LightSlider label="Color temperature" value={colorTemp} min={colorTempMin} max={colorTempMax} unit=" K" onChange={v => void handleColorTemp(v)} />
              )}
            </div>
          )}

          {device.kind === 'media' && (
            <div style={{ marginBottom: 18, padding: '14px 14px 10px', background: J.bg3, border: `1px solid ${J.border}`, borderRadius: 10 }}>
              <div style={{ fontSize: 10, color: J.textMuted, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 600, marginBottom: 12 }}>Media controls</div>
              {(mediaTitle || mediaArtist) && (
                <div style={{ marginBottom: 12, fontSize: 12 }}>
                  {mediaTitle && <div style={{ color: J.text, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{mediaTitle}</div>}
                  {mediaArtist && <div style={{ color: J.textMuted, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{mediaArtist}</div>}
                </div>
              )}
              <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
                {[
                  { action: 'previous_track', label: '⏮' },
                  { action: 'play', label: '▶' },
                  { action: 'pause', label: '⏸' },
                  { action: 'stop', label: '⏹' },
                  { action: 'next_track', label: '⏭' },
                ].map(({ action, label }) => (
                  <button key={action} onClick={() => void handleMediaAction(action)} title={action.replace(/_/g, ' ')}
                    style={{ padding: '6px 11px', fontSize: 14, borderRadius: 7, border: `1px solid ${J.border}`, background: J.bg4, color: J.text, cursor: 'pointer', transition: 'all .12s' }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = J.borderAccent; e.currentTarget.style.color = J.amber; }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = J.border; e.currentTarget.style.color = J.text; }}>
                    {label}
                  </button>
                ))}
                <button onClick={async () => { const next = !muted; setMuted(next); try { await requestHomeAssistantEntityAction(device.entity_id, { action: 'mute' }); } catch { setMuted(!next); } }}
                  title="Toggle mute"
                  style={{ padding: '6px 11px', fontSize: 13, borderRadius: 7, border: `1px solid ${muted ? J.borderAccent : J.border}`, background: muted ? J.amberDim : J.bg4, color: muted ? J.amber : J.textMuted, cursor: 'pointer', transition: 'all .12s' }}>
                  {muted ? '🔇' : '🔊'}
                </button>
              </div>
              <LightSlider label="Volume" value={volume} min={0} max={100} unit="%" onChange={v => void handleVolume(v)} />
            </div>
          )}

          {device.kind === 'climate' && (
            <div style={{ marginBottom: 18, padding: '14px 14px 10px', background: J.bg3, border: `1px solid ${J.border}`, borderRadius: 10 }}>
              <div style={{ fontSize: 10, color: J.textMuted, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 600, marginBottom: 14 }}>Climate controls</div>
              <LightSlider label="Target temperature" value={setpoint} min={tempMin} max={tempMax} unit="°" onChange={v => void handleSetpoint(v)} />
              {hvacModes.length > 0 && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 12, color: J.textSec, marginBottom: 7 }}>HVAC mode</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {hvacModes.map(mode => (
                      <button key={mode} onClick={() => void handleHvacMode(mode)}
                        style={{ padding: '4px 10px', fontSize: 11, borderRadius: 6, border: `1px solid ${hvacMode === mode ? J.amber : J.border}`, background: hvacMode === mode ? J.amberDim : J.bg4, color: hvacMode === mode ? J.amber : J.textSec, cursor: 'pointer', textTransform: 'capitalize', transition: 'all .15s' }}>
                        {mode}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {displayAttrs.length > 0 && (
            <div style={{ marginBottom: 18 }}>
              <div style={{ fontSize: 10, color: J.textMuted, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 600, marginBottom: 9 }}>Attributes</div>
              {displayAttrs.map(([k, v]) => (
                <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: `1px solid ${J.border}`, fontSize: 13 }}>
                  <span style={{ color: J.textSec, textTransform: 'capitalize' }}>{k.replace(/_/g, ' ')}</span>
                  <span style={{ color: J.text, fontWeight: 500 }}>{String(v)}</span>
                </div>
              ))}
            </div>
          )}
          <div>
            <div style={{ fontSize: 10, color: J.textMuted, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 600, marginBottom: 9 }}>Info</div>
            {[['Source', device.integration_source], ['Trust Level', device.trust_level], ['Control Mode', device.control_mode], ['Risk', device.risk_level]].map(([k, v]) => v && (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 0', borderBottom: `1px solid ${J.border}`, fontSize: 13 }}>
                <span style={{ color: J.textSec }}>{k}</span>
                <span style={{ color: J.text, textTransform: 'capitalize' }}>{v}</span>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 18 }}>
            <button className="j-btn" style={{ background: J.amberDim, border: `1px solid ${J.borderAccent}`, color: J.amber, borderRadius: 7, padding: '7px 13px', fontSize: 12, fontWeight: 500 }}
              onClick={() => { onClose(); onUseInChat(device); }}>
              <IconChat size={12} /> Use in Chat
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

function AutomationRow({ automation, onToggle }: { automation: HomeAssistantAutomationRule; onToggle: (next: boolean) => void }) {
  const [busy, setBusy] = useState(false);
  const toggle = async () => {
    setBusy(true);
    try {
      const res = await toggleHomeAssistantAutomation(automation.id);
      onToggle(res.automation.enabled);
    } catch { /* silent */ } finally { setBusy(false); }
  };
  return (
    <div style={{ padding: '6px 10px', fontSize: 12, borderRadius: 7, marginBottom: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6, opacity: busy ? 0.6 : 1, transition: 'opacity .15s' }}>
      <span style={{ color: automation.enabled ? J.textSec : J.textMuted, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>{automation.name}</span>
      <button onClick={() => void toggle()} disabled={busy} title={automation.enabled ? 'Disable' : 'Enable'}
        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '1px 2px', fontSize: 13, color: automation.enabled ? J.success : J.textMuted, flexShrink: 0, transition: 'color .15s' }}>
        {automation.enabled ? '●' : '○'}
      </button>
    </div>
  );
}

export function HomeAssistantScreen({ onNavigate }: { onNavigate?: (screen: string) => void } = {}) {
  useJ();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<'no_access' | 'not_configured' | 'error' | null>(null);
  const [areas, setAreas] = useState<HomeAssistantAreaSummary[]>([]);
  const [entities, setEntities] = useState<HomeAssistantManagedEntity[]>([]);
  const [automations, setAutomations] = useState<HomeAssistantAutomationRule[]>([]);
  const [selectedArea, setSelectedArea] = useState<string | null>(null);
  const [selected, setSelected] = useState<HomeAssistantManagedEntity | null>(null);
  const [lastSync, setLastSync] = useState<string>('—');
  const [search, setSearch] = useState('');
  const [kindFilter, setKindFilter] = useState<string | null>(null);
  const [view, setView] = useState<HaView>('devices');
  const [shopping, setShopping] = useState<HomeAssistantShoppingListItem[]>([]);
  const [newItem, setNewItem] = useState('');
  const [calendar, setCalendar] = useState<HomeAssistantCalendarItem[]>([]);
  const [inbox, setInbox] = useState<HomeAssistantInboxItem[]>([]);
  const [candidates, setCandidates] = useState<HomeAssistantDiscoveryCandidate[]>([]);
  const [controlRequests, setControlRequests] = useState<HomeAssistantControlRequest[]>([]);
  const [sideDataLoaded, setSideDataLoaded] = useState(false);
  const { snapshot, connected: liveConnected } = useHomeAssistantLiveSnapshot(!loading && !error);

  const load = async (background = false) => {
    if (background) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const overview = await fetchHomeAssistantOverview();
      if (!overview.policy.access_granted) { setError('no_access'); return; }
      if (!overview.integration.configured) { setError('not_configured'); return; }
      const [areaRes, entityRes, autoRes] = await Promise.all([
        fetchHomeAssistantAreas(),
        fetchHomeAssistantEntities(),
        fetchHomeAssistantAutomations().catch(() => ({ automations: [] })),
      ]);
      setAreas(areaRes.areas || []);
      setEntities(entityRes.entities || []);
      setAutomations(autoRes.automations || []);
      setSelectedArea(prev => {
        if (prev === null) return null;
        const nextAreas = areaRes.areas || [];
        if (prev && nextAreas.some(area => area.area === prev)) return prev;
        return nextAreas[0]?.area ?? null;
      });
      setSelected(prev => {
        if (!prev) return null;
        return (entityRes.entities || []).find(entity => entity.entity_id === prev.entity_id) || null;
      });
      setLastSync(new Date().toLocaleTimeString());
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '';
      if (msg.includes('403') || msg.includes('permission') || msg.includes('access')) setError('no_access');
      else setError('error');
    } finally {
      if (background) setRefreshing(false);
      else setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => { void load(true); }, 30000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!snapshot) return;
    setAreas(snapshot.areas || []);
    setEntities(snapshot.entities || []);
    setAutomations(snapshot.automations || []);
    setSelectedArea(prev => {
      if (prev === null) return null;
      const nextAreas = snapshot.areas || [];
      if (prev && nextAreas.some(area => area.area === prev)) return prev;
      return nextAreas[0]?.area ?? null;
    });
    setSelected(prev => {
      if (!prev) return null;
      return (snapshot.entities || []).find(entity => entity.entity_id === prev.entity_id) || null;
    });
    const timestamp = Number(snapshot.sync?.timestamp || 0);
    if (timestamp > 0) setLastSync(new Date(timestamp * 1000).toLocaleTimeString());
  }, [snapshot]);

  useEffect(() => {
    if (loading || error || sideDataLoaded) return;
    setSideDataLoaded(true);
    Promise.allSettled([
      fetchHomeAssistantShoppingList().then(r => setShopping(r.items || [])),
      fetchHomeAssistantCalendar().then(r => setCalendar(r.items || [])),
      fetchHomeAssistantInbox().then(r => setInbox(r.items || [])),
      fetchHomeAssistantDiscoveryCandidates().then(r => setCandidates(r.candidates || [])),
      fetchHomeAssistantControlRequests().then(r => setControlRequests(r.requests || [])),
    ]);
  }, [loading, error, sideDataLoaded]);

  const baseEntities = selectedArea ? entities.filter(e => e.area === selectedArea) : entities;
  const availableKinds = Array.from(new Set(baseEntities.map(e => e.kind))).filter(Boolean).sort();
  const areaEntities = baseEntities
    .filter(e => !search || e.label.toLowerCase().includes(search.toLowerCase()) || e.entity_id.toLowerCase().includes(search.toLowerCase()))
    .filter(e => !kindFilter || e.kind === kindFilter);

  const handleUseInChat = (device: HomeAssistantManagedEntity) => {
    setPendingChatPrefill(`Tell me about the ${device.label} (${device.entity_id}). It is currently ${device.state}.`);
    onNavigate?.('chat');
  };

  if (loading) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: J.bg0 }}>
        <Spinner size={24} />
      </div>
    );
  }

  if (error === 'no_access') {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: J.bg0, flexDirection: 'column', gap: 12 }}>
        <div style={{ fontSize: 24, color: J.textMuted }}>🏠</div>
        <div style={{ fontSize: 16, fontWeight: 600, color: J.text }}>No Home Assistant Access</div>
        <div style={{ fontSize: 13, color: J.textMuted, textAlign: 'center', maxWidth: 320 }}>
          Your account doesn't have the <code style={{ color: J.amber }}>home_assistant.access</code> permission.<br />
          Ask an admin to grant it via the <a href="/dashboard/permissions" style={{ color: J.amber, textDecoration: 'underline' }}>Admin Dashboard</a>.
        </div>
      </div>
    );
  }

  if (error === 'not_configured') {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: J.bg0, flexDirection: 'column', gap: 12 }}>
        <div style={{ fontSize: 24, color: J.textMuted }}>🔌</div>
        <div style={{ fontSize: 16, fontWeight: 600, color: J.text }}>Home Assistant Not Configured</div>
        <div style={{ fontSize: 13, color: J.textMuted, textAlign: 'center', maxWidth: 320 }}>
          Set <code style={{ color: J.amber }}>JARVIS_HA_BASE_URL</code> and <code style={{ color: J.amber }}>JARVIS_HA_TOKEN</code> environment variables, then restart Jarvis.
        </div>
      </div>
    );
  }

  if (error === 'error') {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: J.bg0, flexDirection: 'column', gap: 12 }}>
        <div style={{ fontSize: 16, fontWeight: 600, color: J.error }}>Failed to load</div>
        <button onClick={() => void load()} className="j-btn" style={{ background: J.bg2, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '8px 16px', fontSize: 13 }}>
          <IconRefresh size={13} /> Retry
        </button>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: J.bg0 }}>
      <div style={{ height: 50, borderBottom: `1px solid ${J.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 20px', background: J.bg1, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 14, fontWeight: 500, color: J.text }}>Home</span>
          <StatusBadge status={liveConnected ? 'connected' : 'pending'} size="xs" />
          <span style={{ fontSize: 12, color: J.textMuted }}>{entities.length} devices</span>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {refreshing && <Spinner size={12} />}
          <span style={{ fontSize: 12, color: J.textMuted }}>Updated {lastSync}</span>
          <button onClick={() => void load()} className="j-btn" style={{ background: J.bg2, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 7, padding: '5px 11px', fontSize: 12 }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = J.borderHover; e.currentTarget.style.color = J.text; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = J.border; e.currentTarget.style.color = J.textSec; }}>
            <IconRefresh size={12} /> Refresh
          </button>
        </div>
      </div>

      {/* Tab bar */}
      <div style={{ borderBottom: `1px solid ${J.border}`, background: J.bg1, display: 'flex', padding: '0 16px', flexShrink: 0, overflowX: 'auto' }}>
        {([
          { id: 'devices',  label: 'Devices',   badge: entities.length },
          { id: 'shopping', label: 'Shopping',  badge: shopping.filter(i => i.status !== 'completed').length || undefined },
          { id: 'calendar', label: 'Calendar',  badge: calendar.filter(i => i.status !== 'done').length || undefined },
          { id: 'inbox',    label: 'Inbox',     badge: inbox.filter(i => i.status === 'unread').length || undefined },
          { id: 'requests', label: 'Requests',  badge: controlRequests.filter(r => r.status === 'pending').length || undefined, warn: true },
        ] as Array<{ id: HaView; label: string; badge?: number; warn?: boolean }>).map(tab => (
          <button key={tab.id} onClick={() => setView(tab.id)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '10px 14px', fontSize: 13, fontWeight: view === tab.id ? 600 : 400, color: view === tab.id ? J.amber : J.textSec, borderBottom: view === tab.id ? `2px solid ${J.amber}` : '2px solid transparent', display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap', transition: 'color .15s' }}>
            {tab.label}
            {tab.badge ? (
              <span style={{ fontSize: 10, fontWeight: 600, background: tab.warn ? J.errorDim : J.amberDim, color: tab.warn ? J.error : J.amber, border: `1px solid ${tab.warn ? 'rgba(224,85,85,0.3)' : J.borderAccent}`, borderRadius: 10, padding: '1px 6px', minWidth: 16, textAlign: 'center' }}>
                {tab.badge}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Devices view — sidebar + grid */}
        {view === 'devices' && (
          <>
            <div style={{ width: 200, flexShrink: 0, borderRight: `1px solid ${J.border}`, background: J.bg1, padding: '12px 7px', overflowY: 'auto' }}>
              <div style={{ fontSize: 10, color: J.textMuted, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 600, padding: '2px 9px 7px' }}>Areas</div>
              <button onClick={() => { setSelectedArea(null); setKindFilter(null); }}
                style={{ width: '100%', textAlign: 'left', background: selectedArea === null ? J.bg2 : 'none', border: selectedArea === null ? `1px solid ${J.border}` : '1px solid transparent', color: selectedArea === null ? J.text : J.textSec, borderRadius: 8, padding: '8px 10px', fontSize: 13, cursor: 'pointer', marginBottom: 2 }}>
                All Devices <span style={{ marginLeft: 6, fontSize: 11, color: J.textMuted }}>({entities.length})</span>
              </button>
              {areas.map(a => <AreaBtn key={a.area} area={a} active={selectedArea === a.area} onClick={() => { setSelectedArea(a.area); setKindFilter(null); }} />)}
              {automations.length > 0 && (
                <>
                  <div style={{ height: 1, background: J.border, margin: '10px 7px' }} />
                  <div style={{ fontSize: 10, color: J.textMuted, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 600, padding: '2px 9px 7px' }}>Automations</div>
                  {automations.slice(0, 12).map(a => (
                    <AutomationRow key={a.id} automation={a} onToggle={next => setAutomations(prev => prev.map(x => x.id === a.id ? { ...x, enabled: next } : x))} />
                  ))}
                </>
              )}
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '22px 24px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: availableKinds.length > 1 ? 12 : 20, gap: 12, flexWrap: 'wrap' }}>
                <div>
                  <h2 style={{ fontSize: 18, fontWeight: 600, color: J.text, marginBottom: 3, textTransform: 'capitalize' }}>{selectedArea || 'All Devices'}</h2>
                  <p style={{ fontSize: 13, color: J.textMuted }}>{areaEntities.length} device{areaEntities.length !== 1 ? 's' : ''}{search || kindFilter ? ' matching' : ''}</p>
                </div>
                <div style={{ position: 'relative', flexShrink: 0 }}>
                  <span style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: J.textMuted, pointerEvents: 'none' }}><IconSearch size={13} /></span>
                  <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search devices…"
                    style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 8, padding: '6px 11px 6px 29px', fontSize: 13, color: J.text, width: 200, outline: 'none' }}
                    onFocus={e => { e.currentTarget.style.borderColor = J.borderHover; }}
                    onBlur={e => { e.currentTarget.style.borderColor = J.border; }} />
                </div>
              </div>
              {availableKinds.length > 1 && (
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 18 }}>
                  {availableKinds.map(k => {
                    const active = kindFilter === k;
                    return (
                      <button key={k} onClick={() => setKindFilter(active ? null : k)}
                        style={{ padding: '3px 10px', fontSize: 11, fontWeight: active ? 600 : 400, borderRadius: 20, border: `1px solid ${active ? J.amber : J.border}`, background: active ? J.amberDim : J.bg2, color: active ? J.amber : J.textSec, cursor: 'pointer', textTransform: 'capitalize', display: 'flex', alignItems: 'center', gap: 5, transition: 'all .12s' }}
                        onMouseEnter={e => { if (!active) { e.currentTarget.style.borderColor = J.borderHover; e.currentTarget.style.color = J.text; } }}
                        onMouseLeave={e => { if (!active) { e.currentTarget.style.borderColor = J.border; e.currentTarget.style.color = J.textSec; } }}>
                        {TYPE_ICON[k] ?? null}{k}
                      </button>
                    );
                  })}
                  {kindFilter && (
                    <button onClick={() => setKindFilter(null)}
                      style={{ padding: '3px 9px', fontSize: 11, borderRadius: 20, border: `1px solid ${J.border}`, background: 'none', color: J.textMuted, cursor: 'pointer', transition: 'all .12s' }}>
                      Clear
                    </button>
                  )}
                </div>
              )}
              {areaEntities.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '60px 20px', color: J.textMuted, fontSize: 14 }}>
                  {entities.length === 0 ? 'No devices configured.' : search ? 'No devices match your search.' : 'No devices in this area.'}
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(148px,1fr))', gap: 10 }}>
                  {areaEntities.map(d => <DeviceCard key={d.entity_id} device={d} onClick={setSelected} />)}
                </div>
              )}
            </div>
          </>
        )}

        {/* Shopping list */}
        {view === 'shopping' && (
          <div style={{ flex: 1, overflowY: 'auto', padding: '24px 28px', maxWidth: 640 }}>
            <h2 style={{ fontSize: 18, fontWeight: 600, color: J.text, marginBottom: 18 }}>Shopping List</h2>
            <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
              <input value={newItem} onChange={e => setNewItem(e.target.value)}
                onKeyDown={async e => {
                  if (e.key !== 'Enter' || !newItem.trim()) return;
                  const title = newItem.trim(); setNewItem('');
                  const res = await addHomeAssistantShoppingListItem({ title }).catch(() => null);
                  if (res) setShopping(prev => [res.item, ...prev]);
                }}
                placeholder="Add item… (Enter to add)"
                style={{ flex: 1, background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 8, padding: '8px 12px', fontSize: 13, color: J.text, outline: 'none' }}
                onFocus={e => { e.currentTarget.style.borderColor = J.borderHover; }}
                onBlur={e => { e.currentTarget.style.borderColor = J.border; }} />
              <button className="j-btn" style={{ background: J.amberDim, border: `1px solid ${J.borderAccent}`, color: J.amber, borderRadius: 8, padding: '8px 14px', fontSize: 13 }}
                onClick={async () => {
                  if (!newItem.trim()) return;
                  const title = newItem.trim(); setNewItem('');
                  const res = await addHomeAssistantShoppingListItem({ title }).catch(() => null);
                  if (res) setShopping(prev => [res.item, ...prev]);
                }}>Add</button>
            </div>
            {shopping.length === 0 ? (
              <div style={{ color: J.textMuted, fontSize: 14, textAlign: 'center', paddingTop: 40 }}>No items on the shopping list.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {shopping.map(item => (
                  <div key={item.id} style={{ display: 'flex', alignItems: 'center', gap: 12, background: J.bg2, border: `1px solid ${item.status === 'completed' ? J.border : J.border}`, borderRadius: 10, padding: '10px 14px', opacity: item.status === 'completed' ? 0.5 : 1 }}>
                    <button onClick={() => {
                      const nextStatus = item.status === 'completed' ? 'active' : 'completed';
                      setShopping(prev => prev.map(i => i.id === item.id ? { ...i, status: nextStatus } : i));
                    }}
                      style={{ width: 20, height: 20, borderRadius: '50%', border: `2px solid ${item.status === 'completed' ? J.success : J.border}`, background: item.status === 'completed' ? J.success : 'none', cursor: 'pointer', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: J.bg0, fontSize: 11, fontWeight: 700 }}>
                      {item.status === 'completed' ? '✓' : ''}
                    </button>
                    <span style={{ flex: 1, fontSize: 14, color: J.text, textDecoration: item.status === 'completed' ? 'line-through' : 'none' }}>{item.title}</span>
                    <span style={{ fontSize: 11, color: J.textMuted }}>{item.source}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Calendar */}
        {view === 'calendar' && (
          <div style={{ flex: 1, overflowY: 'auto', padding: '24px 28px', maxWidth: 680 }}>
            <h2 style={{ fontSize: 18, fontWeight: 600, color: J.text, marginBottom: 18 }}>Calendar</h2>
            {calendar.length === 0 ? (
              <div style={{ color: J.textMuted, fontSize: 14, textAlign: 'center', paddingTop: 40 }}>No upcoming events.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {calendar.map(ev => {
                  const start = ev.starts_at ? new Date(ev.starts_at) : null;
                  const isPast = start && start < new Date();
                  return (
                    <div key={ev.id} style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 11, padding: '13px 16px', opacity: ev.status === 'done' || isPast ? 0.55 : 1 }}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 14, fontWeight: 500, color: J.text, marginBottom: 4 }}>{ev.title}</div>
                          <div style={{ fontSize: 12, color: J.textMuted }}>
                            {start ? start.toLocaleString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'}
                            {ev.ends_at && ` → ${new Date(ev.ends_at).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}`}
                          </div>
                        </div>
                        <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                          <span style={{ fontSize: 11, color: isPast ? J.textMuted : J.amber, background: isPast ? J.bg3 : J.amberDim, border: `1px solid ${isPast ? J.border : J.borderAccent}`, borderRadius: 6, padding: '2px 7px' }}>
                            {ev.status === 'done' ? 'done' : isPast ? 'past' : 'upcoming'}
                          </span>
                          {ev.status !== 'done' && (
                            <button className="j-btn" style={{ background: 'none', border: `1px solid ${J.border}`, color: J.textMuted, borderRadius: 6, padding: '2px 8px', fontSize: 11 }}
                              onClick={async () => {
                                await actOnHomeAssistantCalendarItem(ev.id, { action: 'mark_done' }).catch(() => null);
                                setCalendar(prev => prev.map(e => e.id === ev.id ? { ...e, status: 'done' } : e));
                              }}>Done</button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Inbox */}
        {view === 'inbox' && (
          <div style={{ flex: 1, overflowY: 'auto', padding: '24px 28px', maxWidth: 680 }}>
            <h2 style={{ fontSize: 18, fontWeight: 600, color: J.text, marginBottom: 18 }}>Inbox</h2>
            {inbox.length === 0 ? (
              <div style={{ color: J.textMuted, fontSize: 14, textAlign: 'center', paddingTop: 40 }}>Inbox is empty.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {inbox.map(msg => (
                  <div key={msg.id} style={{ background: J.bg2, border: `1px solid ${msg.status === 'unread' ? J.borderAccent : J.border}`, borderLeft: `3px solid ${msg.status === 'unread' ? J.amber : J.border}`, borderRadius: 11, padding: '13px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
                          <span style={{ fontSize: 13, fontWeight: 600, color: J.text }}>{msg.subject}</span>
                          {msg.status === 'unread' && <span style={{ fontSize: 10, color: J.amber, background: J.amberDim, border: `1px solid ${J.borderAccent}`, borderRadius: 6, padding: '1px 6px' }}>new</span>}
                        </div>
                        <div style={{ fontSize: 12, color: J.textMuted, marginBottom: msg.summary ? 8 : 0 }}>From: {msg.from_label} · {new Date(msg.received_at > 1e10 ? msg.received_at : msg.received_at * 1000).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</div>
                        {msg.summary && <div style={{ fontSize: 13, color: J.textSec, lineHeight: 1.5 }}>{msg.summary}</div>}
                      </div>
                      <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                        {msg.status === 'unread' && (
                          <button className="j-btn" style={{ background: 'none', border: `1px solid ${J.border}`, color: J.textMuted, borderRadius: 6, padding: '3px 9px', fontSize: 11 }}
                            onClick={async () => {
                              await actOnHomeAssistantInboxItem(msg.id, { action: 'mark_read' }).catch(() => null);
                              setInbox(prev => prev.map(m => m.id === msg.id ? { ...m, status: 'read' } : m));
                            }}>Mark read</button>
                        )}
                        <button className="j-btn" style={{ background: 'none', border: `1px solid ${J.border}`, color: J.textMuted, borderRadius: 6, padding: '3px 9px', fontSize: 11 }}
                          onClick={async () => {
                            await actOnHomeAssistantInboxItem(msg.id, { action: 'archive' }).catch(() => null);
                            setInbox(prev => prev.filter(m => m.id !== msg.id));
                          }}>Archive</button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Control requests + discovery */}
        {view === 'requests' && (
          <div style={{ flex: 1, overflowY: 'auto', padding: '24px 28px' }}>
            <h2 style={{ fontSize: 18, fontWeight: 600, color: J.text, marginBottom: 6 }}>Pending Requests</h2>
            <p style={{ fontSize: 13, color: J.textMuted, marginBottom: 20 }}>Sensitive actions that require your confirmation, and new devices awaiting approval.</p>

            {controlRequests.length > 0 && (
              <>
                <div style={{ fontSize: 10, color: J.textMuted, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 600, marginBottom: 10 }}>Control requests</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 28 }}>
                  {controlRequests.map(req => (
                    <div key={req.id} style={{ background: J.bg2, border: `1px solid ${req.status === 'pending' ? J.errorDim : J.border}`, borderLeft: `3px solid ${req.status === 'pending' ? J.error : J.border}`, borderRadius: 11, padding: '13px 16px' }}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 14, fontWeight: 600, color: J.text, marginBottom: 4 }}>{req.entity_label}</div>
                          <div style={{ fontSize: 12, color: J.textMuted, marginBottom: 4 }}>Action: <strong style={{ color: J.textSec }}>{req.action}</strong> · Risk: <strong style={{ color: req.risk_level === 'high' ? J.error : req.risk_level === 'medium' ? J.warn : J.textSec }}>{req.risk_level}</strong></div>
                          <code style={{ fontSize: 11, color: J.textMuted, fontFamily: 'JetBrains Mono,monospace' }}>{req.entity_id}</code>
                        </div>
                        {req.status === 'pending' && (
                          <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                            <button className="j-btn" style={{ background: J.successDim, border: `1px solid rgba(61,186,132,0.3)`, color: J.success, borderRadius: 6, padding: '5px 12px', fontSize: 12, fontWeight: 500 }}
                              onClick={async () => {
                                await confirmHomeAssistantControlRequest(req.id, { confirmed: true }).catch(() => null);
                                setControlRequests(prev => prev.map(r => r.id === req.id ? { ...r, status: 'confirmed' } : r));
                              }}>Confirm</button>
                            <button className="j-btn" style={{ background: J.errorDim, border: `1px solid rgba(224,85,85,0.3)`, color: J.error, borderRadius: 6, padding: '5px 12px', fontSize: 12, fontWeight: 500 }}
                              onClick={async () => {
                                await confirmHomeAssistantControlRequest(req.id, { confirmed: false }).catch(() => null);
                                setControlRequests(prev => prev.map(r => r.id === req.id ? { ...r, status: 'denied' } : r));
                              }}>Deny</button>
                          </div>
                        )}
                        {req.status !== 'pending' && (
                          <span style={{ fontSize: 11, color: req.status === 'confirmed' ? J.success : J.error, fontWeight: 600 }}>{req.status}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}

            <div style={{ fontSize: 10, color: J.textMuted, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 600, marginBottom: 10 }}>Device discovery</div>
            {candidates.length === 0 ? (
              <div style={{ color: J.textMuted, fontSize: 14, paddingTop: 10 }}>No devices pending approval.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {candidates.filter(c => c.approval_status === 'pending').map(candidate => (
                  <div key={candidate.id} style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 11, padding: '13px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 14, fontWeight: 600, color: J.text, marginBottom: 4 }}>{candidate.label}</div>
                        <div style={{ fontSize: 12, color: J.textMuted, marginBottom: 2 }}>Type: {candidate.suggested_type} · Area: {candidate.suggested_area || '—'} · IP: {candidate.ip_address || '—'}</div>
                        <div style={{ display: 'flex', gap: 6, marginTop: 5 }}>
                          <span style={{ fontSize: 10, color: J.textMuted, background: J.bg3, borderRadius: 5, padding: '1px 7px', border: `1px solid ${J.border}` }}>{candidate.trust_level}</span>
                          <span style={{ fontSize: 10, color: candidate.risk_level === 'high' ? J.error : J.textMuted, background: J.bg3, borderRadius: 5, padding: '1px 7px', border: `1px solid ${J.border}` }}>{candidate.risk_level} risk</span>
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                        <button className="j-btn" style={{ background: J.amberDim, border: `1px solid ${J.borderAccent}`, color: J.amber, borderRadius: 6, padding: '5px 12px', fontSize: 12, fontWeight: 500 }}
                          onClick={async () => {
                            await approveHomeAssistantDiscoveryCandidate(candidate.id).catch(() => null);
                            setCandidates(prev => prev.map(c => c.id === candidate.id ? { ...c, approval_status: 'approved' } : c));
                          }}>Approve</button>
                        <button className="j-btn" style={{ background: 'none', border: `1px solid ${J.border}`, color: J.textMuted, borderRadius: 6, padding: '5px 10px', fontSize: 12 }}
                          onClick={() => setCandidates(prev => prev.map(c => c.id === candidate.id ? { ...c, approval_status: 'dismissed' } : c))}>Dismiss</button>
                      </div>
                    </div>
                  </div>
                ))}
                {candidates.filter(c => c.approval_status === 'pending').length === 0 && (
                  <div style={{ color: J.textMuted, fontSize: 14 }}>All candidates have been reviewed.</div>
                )}
              </div>
            )}
            {controlRequests.length === 0 && candidates.filter(c => c.approval_status === 'pending').length === 0 && (
              <div style={{ textAlign: 'center', paddingTop: 40, color: J.textMuted, fontSize: 14 }}>No pending requests or device approvals.</div>
            )}
          </div>
        )}
      </div>

      {selected && <DeviceDrawer device={selected} onClose={() => setSelected(null)} onUseInChat={handleUseInChat} />}
    </div>
  );
}
