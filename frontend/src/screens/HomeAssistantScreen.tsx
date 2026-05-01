import { useState, useEffect } from 'react';
import { J, useJ, StatusBadge, Spinner, IconRefresh, IconX, IconChat, IconBulb, IconActivity, IconTherm, IconSettings } from './jarvis-shared';
import { fetchHomeAssistantOverview, fetchHomeAssistantEntities, fetchHomeAssistantAreas, fetchHomeAssistantAutomations, useHomeAssistantLiveSnapshot, requestHomeAssistantEntityAction, type HomeAssistantManagedEntity, type HomeAssistantAreaSummary, type HomeAssistantAutomationRule } from '../shared/api/homeAssistant';

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

function DeviceDrawer({ device, onClose }: { device: HomeAssistantManagedEntity; onClose: () => void }) {
  const [on, setOn] = useState(isOnState(device));
  const [busy, setBusy] = useState(false);
  const attrs = (device.metadata as Record<string, unknown>) || {};
  useEffect(() => { setOn(isOnState(device)); }, [device.state]);

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
          {Object.keys(attrs).length > 0 && (
            <div style={{ marginBottom: 18 }}>
              <div style={{ fontSize: 10, color: J.textMuted, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 600, marginBottom: 9 }}>Attributes</div>
              {Object.entries(attrs).slice(0, 8).map(([k, v]) => (
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
            <button className="j-btn" style={{ background: J.amberDim, border: `1px solid ${J.borderAccent}`, color: J.amber, borderRadius: 7, padding: '7px 13px', fontSize: 12, fontWeight: 500 }}>
              <IconChat size={12} /> Use in Chat
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

export function HomeAssistantScreen() {
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

  const areaEntities = selectedArea ? entities.filter(e => e.area === selectedArea) : entities;

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

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <div style={{ width: 200, flexShrink: 0, borderRight: `1px solid ${J.border}`, background: J.bg1, padding: '12px 7px', overflowY: 'auto' }}>
          <div style={{ fontSize: 10, color: J.textMuted, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 600, padding: '2px 9px 7px' }}>Areas</div>
          <button onClick={() => setSelectedArea(null)}
            style={{ width: '100%', textAlign: 'left', background: selectedArea === null ? J.bg2 : 'none', border: selectedArea === null ? `1px solid ${J.border}` : '1px solid transparent', color: selectedArea === null ? J.text : J.textSec, borderRadius: 8, padding: '8px 10px', fontSize: 13, cursor: 'pointer', marginBottom: 2 }}>
            All Devices
            <span style={{ marginLeft: 6, fontSize: 11, color: J.textMuted }}>({entities.length})</span>
          </button>
          {areas.map(a => <AreaBtn key={a.area} area={a} active={selectedArea === a.area} onClick={() => setSelectedArea(a.area)} />)}

          {automations.length > 0 && (
            <>
              <div style={{ height: 1, background: J.border, margin: '10px 7px' }} />
              <div style={{ fontSize: 10, color: J.textMuted, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 600, padding: '2px 9px 7px' }}>Automations</div>
              {automations.slice(0, 8).map(a => (
                <div key={a.id}
                  style={{ padding: '7px 10px', fontSize: 12, color: a.enabled ? J.textSec : J.textMuted, borderRadius: 7, marginBottom: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name}</span>
                  <span style={{ fontSize: 10, color: a.enabled ? J.success : J.textMuted, flexShrink: 0, marginLeft: 4 }}>{a.enabled ? '●' : '○'}</span>
                </div>
              ))}
            </>
          )}
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '22px 24px' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20 }}>
            <div>
              <h2 style={{ fontSize: 18, fontWeight: 600, color: J.text, marginBottom: 3, textTransform: 'capitalize' }}>
                {selectedArea || 'All Devices'}
              </h2>
              <p style={{ fontSize: 13, color: J.textMuted }}>{areaEntities.length} devices</p>
            </div>
          </div>

          {areaEntities.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '60px 20px', color: J.textMuted, fontSize: 14 }}>
              {entities.length === 0
                ? 'No devices configured. Use the Admin Dashboard to add devices via Home Assistant.'
                : 'No devices in this area.'}
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(148px,1fr))', gap: 10 }}>
              {areaEntities.map(d => <DeviceCard key={d.entity_id} device={d} onClick={setSelected} />)}
            </div>
          )}
        </div>
      </div>

      {selected && <DeviceDrawer device={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
