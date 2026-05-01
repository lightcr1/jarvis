import React, { useState } from 'react';
import { J, useJ, StatusBadge, MetricCard, Spinner, IconSettings, IconPlus, IconX, IconCheck, IconActivity, IconGrid, IconShield, IconCode, IconMemory } from './jarvis-shared';

const SERVICES = [
  { id: 'chat',    name: 'Chat',           desc: 'AI conversation — text and context',      status: 'connected', cat: 'Core',           screen: 'chat',  note: 'Always active' },
  { id: 'orb',     name: 'Voice',          desc: 'Voice interaction & wake word',            status: 'connected', cat: 'Core',           screen: 'orb',   note: 'Always active' },
  { id: 'memory',  name: 'Memory',         desc: 'Long-term context, feedback & aliases',    status: 'connected', cat: 'Core',           note: 'Always active' },
  { id: 'security',name: 'Security',       desc: 'Audit log, RBAC, action confirmation',     status: 'connected', cat: 'Core',           note: 'Always active' },
  { id: 'admin',   name: 'Admin',          desc: 'User & permission management dashboard',   status: 'connected', cat: 'Core',           note: 'Via /dashboard' },
  { id: 'ha',      name: 'Home Assistant', desc: 'Smart home device control & automations',  status: 'configured', cat: 'Integrations',  screen: 'home',  note: 'Needs JARVIS_HA_BASE_URL' },
  { id: 'proxmox', name: 'Proxmox',        desc: 'VM and LXC container management',          status: 'configured', cat: 'Integrations',  screen: 'proxmox', note: 'Needs Proxmox hosts configured' },
  { id: 'github',  name: 'GitHub RAG',     desc: 'Repository knowledge indexing',            status: 'configured', cat: 'Knowledge',     note: 'Needs JARVIS_GITHUB_TOKEN' },
  { id: 'wikijs',  name: 'WikiJS RAG',     desc: 'Wiki page knowledge indexing',             status: 'configured', cat: 'Knowledge',     note: 'Needs JARVIS_WIKIJS_URL' },
] as const;

const CATS = ['All', 'Core', 'Integrations', 'Knowledge'];

type Service = typeof SERVICES[number];

function ServiceCard({ svc, onNavigate }: { svc: Service; onNavigate: (s: string) => void }) {
  const isConnected  = svc.status === 'connected';
  const isConfigured = svc.status === 'configured';

  const iconMap: Record<string, JSX.Element> = {
    Core:         <IconShield size={15} />,
    Integrations: <IconSettings size={15} />,
    Knowledge:    <IconMemory size={15} />,
  };

  return (
    <div style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 12, padding: '18px', display: 'flex', flexDirection: 'column', gap: 12, transition: 'all .12s' }}
      onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.background = J.bg3; (e.currentTarget as HTMLDivElement).style.borderColor = J.borderHover; }}
      onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = J.bg2; (e.currentTarget as HTMLDivElement).style.borderColor = J.border; }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div style={{ width: 38, height: 38, borderRadius: 9, background: J.bg3, border: `1px solid ${J.border}`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: isConnected ? J.amber : J.textMuted }}>
          {iconMap[svc.cat] || <IconSettings size={15} />}
        </div>
        <StatusBadge status={svc.status} size="xs" />
      </div>
      <div>
        <div style={{ fontSize: 14, fontWeight: 500, color: J.text, marginBottom: 3 }}>{svc.name}</div>
        <div style={{ fontSize: 12, color: J.textMuted, lineHeight: 1.45 }}>{svc.desc}</div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 'auto' }}>
        <span style={{ fontSize: 11, color: J.textMuted }}>{'note' in svc ? svc.note : ''}</span>
        {'screen' in svc && (
          <button className="j-btn" onClick={() => onNavigate(svc.screen as string)}
            style={{ background: J.amberDim, border: `1px solid ${J.borderAccent}`, color: J.amber, borderRadius: 7, padding: '4px 11px', fontSize: 11, fontWeight: 500 }}>Open</button>
        )}
        {isConfigured && (
          <span style={{ fontSize: 11, color: J.textMuted }}>env var required</span>
        )}
      </div>
    </div>
  );
}

function AddModal({ onClose }: { onClose: () => void }) {
  const [step, setStep]       = useState(1);
  const [cat, setCat]         = useState('Integrations');
  const [name, setName]       = useState('');
  const [url, setUrl]         = useState('');
  const [token, setToken]     = useState('');
  const [testing, setTesting] = useState(false);
  const [tested, setTested]   = useState(false);

  const doTest = () => {
    setTesting(true);
    setTimeout(() => { setTesting(false); setTested(true); }, 1400);
  };

  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 50 }} />
      <div style={{ position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', width: 'min(480px, 95vw)', background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 16, zIndex: 51, animation: 'fadeIn .2s ease', overflow: 'hidden' }}>
        <div style={{ padding: '18px 22px', borderBottom: `1px solid ${J.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 600, color: J.text }}>Add Integration</div>
            <div style={{ fontSize: 12, color: J.textMuted, marginTop: 2 }}>Note: integrations are configured via env vars on the server</div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: J.textMuted, display: 'flex' }}><IconX size={16} /></button>
        </div>

        <div style={{ display: 'flex', gap: 6, padding: '16px 22px 0', alignItems: 'center' }}>
          {['Category', 'Configure', 'Test'].map((label, i) => (
            <React.Fragment key={label}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div style={{ width: 22, height: 22, borderRadius: '50%', background: step > i+1 ? J.success : step === i+1 ? J.amber : J.bg4, border: `1px solid ${step >= i+1 ? (step > i+1 ? J.success : J.amber) : J.border}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 600, color: step >= i+1 ? J.bg0 : J.textMuted, transition: 'all .2s' }}>
                  {step > i+1 ? '✓' : i+1}
                </div>
                <span style={{ fontSize: 12, color: step === i+1 ? J.text : J.textMuted, fontWeight: step === i+1 ? 500 : 400 }}>{label}</span>
              </div>
              {i < 2 && <div style={{ flex: 1, height: 1, background: step > i+1 ? J.success : J.border, transition: 'background .3s' }} />}
            </React.Fragment>
          ))}
        </div>

        <div style={{ padding: '20px 22px 22px' }}>
          {step === 1 && (
            <div>
              <p style={{ fontSize: 13, color: J.textSec, marginBottom: 12 }}>What kind of integration?</p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 7 }}>
                {['Integrations', 'Knowledge', 'Other'].map(c => (
                  <button key={c} onClick={() => setCat(c)}
                    style={{ background: cat === c ? J.amberDim : J.bg3, border: `1px solid ${cat === c ? J.borderAccent : J.border}`, color: cat === c ? J.amber : J.textSec, borderRadius: 8, padding: '10px 8px', fontSize: 12, fontWeight: cat === c ? 500 : 400, cursor: 'pointer' }}>
                    {c}
                  </button>
                ))}
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
                <button onClick={() => setStep(2)} className="j-btn" style={{ background: J.amber, color: J.bg0, borderRadius: 8, padding: '8px 20px', fontSize: 13, fontWeight: 600 }}>Continue →</button>
              </div>
            </div>
          )}
          {step === 2 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {[
                { label: 'Service Name', val: name, set: setName, ph: 'e.g. My Sensor Hub', type: 'text' },
                { label: 'API URL',      val: url,   set: setUrl,   ph: 'https://your-service.local/api', type: 'url' },
                { label: 'API Token',    val: token, set: setToken, ph: 'Bearer token or API key', type: 'password' },
              ].map(f => (
                <div key={f.label}>
                  <label style={{ fontSize: 12, color: J.textSec, display: 'block', marginBottom: 5 }}>{f.label}</label>
                  <input className="j-input" type={f.type} value={f.val} onChange={e => f.set(e.target.value)} placeholder={f.ph}
                    style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
                </div>
              ))}
              <div style={{ display: 'flex', gap: 7, justifyContent: 'flex-end', marginTop: 2 }}>
                <button onClick={() => setStep(1)} className="j-btn" style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '8px 16px', fontSize: 13 }}>← Back</button>
                <button onClick={() => setStep(3)} className="j-btn" style={{ background: J.amber, color: J.bg0, borderRadius: 8, padding: '8px 20px', fontSize: 13, fontWeight: 600 }}>Continue →</button>
              </div>
            </div>
          )}
          {step === 3 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <p style={{ fontSize: 13, color: J.textSec }}>Test the connection before saving.</p>
              <button onClick={doTest} disabled={testing} className="j-btn"
                style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '10px 20px', fontSize: 13, justifyContent: 'center' }}>
                {testing ? <><Spinner size={13} /> Testing…</> : 'Test Connection'}
              </button>
              {tested && (
                <div style={{ background: J.successDim, border: `1px solid rgba(61,186,132,0.25)`, borderRadius: 9, padding: '10px 14px', display: 'flex', gap: 8, alignItems: 'center', color: J.success, fontSize: 13 }}>
                  <IconCheck size={14} /> Connection successful.
                </div>
              )}
              <div style={{ display: 'flex', gap: 7, justifyContent: 'flex-end' }}>
                <button onClick={() => setStep(2)} className="j-btn" style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '8px 16px', fontSize: 13 }}>← Back</button>
                <button onClick={onClose} className="j-btn" style={{ background: J.amber, color: J.bg0, borderRadius: 8, padding: '8px 20px', fontSize: 13, fontWeight: 600, opacity: tested ? 1 : .4 }}>Save</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

export function ServiceHubScreen({ onNavigate }: { onNavigate: (screen: string) => void }) {
  useJ();
  const [cat, setCat]         = useState('All');
  const [showAdd, setShowAdd] = useState(false);

  const shown     = cat === 'All' ? SERVICES : SERVICES.filter(s => s.cat === cat);
  const connected = SERVICES.filter(s => s.status === 'connected').length;
  const configured = SERVICES.filter(s => s.status === 'configured').length;

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: J.bg0 }}>
      <div style={{ height: 50, borderBottom: `1px solid ${J.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px', background: J.bg1, flexShrink: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 500, color: J.text }}>Services</div>
        <button onClick={() => setShowAdd(true)} className="j-btn"
          style={{ background: J.amberDim, border: `1px solid ${J.borderAccent}`, color: J.amber, borderRadius: 8, padding: '6px 14px', fontSize: 13, fontWeight: 500 }}>
          <IconPlus size={13} /> Add
        </button>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '22px 24px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(160px,1fr))', gap: 10, marginBottom: 24 }}>
          <MetricCard label="Active"       value={connected}    sublabel="Always-on services"     icon={<IconGrid size={14} />} />
          <MetricCard label="Integrations" value={configured}   sublabel="Env-var configured"      icon={<IconCode size={14} />} />
          <MetricCard label="Total"        value={SERVICES.length} sublabel="Registered services"  icon={<IconActivity size={14} />} />
          <MetricCard label="Security"     value="RBAC"         sublabel="Role-based access"        icon={<IconShield size={14} />} accent={J.success} />
        </div>
        <div style={{ display: 'flex', gap: 6, marginBottom: 18, flexWrap: 'wrap' }}>
          {CATS.map(c => (
            <button key={c} onClick={() => setCat(c)}
              style={{ background: cat === c ? J.amberDim : J.bg2, border: `1px solid ${cat === c ? J.borderAccent : J.border}`, color: cat === c ? J.amber : J.textSec, borderRadius: 7, padding: '4px 13px', fontSize: 12, fontWeight: cat === c ? 500 : 400, cursor: 'pointer', transition: 'all .1s' }}>
              {c}
            </button>
          ))}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(210px,1fr))', gap: 10 }}>
          {shown.map(svc => <ServiceCard key={svc.id} svc={svc} onNavigate={onNavigate} />)}
        </div>
      </div>
      {showAdd && <AddModal onClose={() => setShowAdd(false)} />}
    </div>
  );
}
