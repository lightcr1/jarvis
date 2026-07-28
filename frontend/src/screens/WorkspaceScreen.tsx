import { useEffect, useState } from 'react';
import { J, useJ, Spinner, showToast, IconPlus, IconTrash, IconX, IconMonitor, IconExternal, IconZap, IconPencil, IconKey } from './jarvis-shared';
import { OverlayDialog } from '../shared/ui/OverlayDialog';
import {
  WorkspaceOsType, WorkspaceProtocol, WorkspaceTarget,
  connectWorkspaceTarget, createWorkspaceTarget, deleteWorkspaceTarget,
  fetchWorkspaceCredentialsStatus, fetchWorkspaceTargets, setWorkspaceCredentials, updateWorkspaceTarget, wakeWorkspaceTarget,
} from '../shared/api/workspace';

const DEFAULT_PORT: Record<WorkspaceProtocol, number> = { rdp: 3389, vnc: 5900 };

function errMsg(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

function Pill({ label, color }: { label: string; color: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: `${color}1a`, color, borderRadius: 5, padding: '2px 8px', fontSize: 11, fontWeight: 500, whiteSpace: 'nowrap' }}>
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: color, flexShrink: 0 }} />
      {label}
    </span>
  );
}

function labeledInput(label: string, node: React.ReactNode) {
  return (
    <div>
      <label style={{ fontSize: 12, color: J.textSec, display: 'block', marginBottom: 5 }}>{label}</label>
      {node}
    </div>
  );
}

function TargetFormModal({ target, onClose, onSaved }: { target: WorkspaceTarget | null; onClose: () => void; onSaved: (t: WorkspaceTarget) => void }) {
  const isEdit = !!target;
  const [name, setName] = useState(target?.name ?? '');
  const [osType, setOsType] = useState<WorkspaceOsType>(target?.os_type ?? 'windows');
  const [protocol, setProtocol] = useState<WorkspaceProtocol>(target?.protocol ?? 'rdp');
  const [host, setHost] = useState(target?.tailscale_host ?? '');
  const [port, setPort] = useState(target ? String(target.port) : '');
  const [relay, setRelay] = useState(target?.wol_relay_host ?? '');
  const [mac, setMac] = useState(target?.wol_mac ?? '');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    const trimmedName = name.trim();
    const trimmedHost = host.trim();
    if (!trimmedName || !trimmedHost || saving) return;
    setSaving(true);
    try {
      const body = {
        name: trimmedName,
        os_type: osType,
        protocol,
        tailscale_host: trimmedHost,
        port: port.trim() ? Number(port.trim()) : undefined,
        wol_relay_host: relay.trim() || undefined,
        wol_mac: mac.trim() || undefined,
      };
      const res = isEdit ? await updateWorkspaceTarget(target!.id, body) : await createWorkspaceTarget(body);
      onSaved(res.target);
      showToast(isEdit ? 'Target updated' : 'Target added', 'success');
      onClose();
    } catch (err) {
      showToast(errMsg(err, 'Failed to save target'), 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <OverlayDialog
      title={isEdit ? 'Edit Target' : 'New Workspace Target'}
      onClose={onClose}
      actions={
        <>
          <button onClick={onClose} className="j-btn" style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '8px 16px', fontSize: 13 }}>Cancel</button>
          <button onClick={submit} disabled={!name.trim() || !host.trim() || saving} className="j-btn"
            style={{ background: J.amber, color: J.bg0, borderRadius: 8, padding: '8px 20px', fontSize: 13, fontWeight: 600, opacity: name.trim() && host.trim() ? 1 : .5 }}>
            {saving ? <Spinner size={13} color={J.bg0} /> : isEdit ? 'Save' : 'Create'}
          </button>
        </>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {labeledInput('Name', (
          <input className="j-input" autoFocus value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Office Desktop"
            style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
        ))}
        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{ flex: 1 }}>
            {labeledInput('OS', (
              <div style={{ display: 'flex', gap: 6 }}>
                {(['windows', 'linux'] as WorkspaceOsType[]).map(o => (
                  <button key={o} onClick={() => { setOsType(o); if (!isEdit) setProtocol(o === 'windows' ? 'rdp' : 'vnc'); }}
                    style={{ flex: 1, background: osType === o ? J.amberDim : J.bg3, border: `1px solid ${osType === o ? J.borderAccent : J.border}`, color: osType === o ? J.amber : J.textSec, borderRadius: 7, padding: '8px 6px', fontSize: 12, fontWeight: osType === o ? 600 : 400, cursor: 'pointer', textTransform: 'capitalize' }}>
                    {o}
                  </button>
                ))}
              </div>
            ))}
          </div>
          <div style={{ flex: 1 }}>
            {labeledInput('Protocol', (
              <div style={{ display: 'flex', gap: 6 }}>
                {(['rdp', 'vnc'] as WorkspaceProtocol[]).map(p => (
                  <button key={p} onClick={() => setProtocol(p)}
                    style={{ flex: 1, background: protocol === p ? J.amberDim : J.bg3, border: `1px solid ${protocol === p ? J.borderAccent : J.border}`, color: protocol === p ? J.amber : J.textSec, borderRadius: 7, padding: '8px 6px', fontSize: 12, fontWeight: protocol === p ? 600 : 400, cursor: 'pointer', textTransform: 'uppercase' }}>
                    {p}
                  </button>
                ))}
              </div>
            ))}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{ flex: 2 }}>
            {labeledInput('Tailscale host', (
              <input className="j-input" value={host} onChange={e => setHost(e.target.value)} placeholder="100.x.y.z or host.tailnet.ts.net"
                style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
            ))}
          </div>
          <div style={{ flex: 1 }}>
            {labeledInput('Port', (
              <input className="j-input" value={port} onChange={e => setPort(e.target.value)} placeholder={String(DEFAULT_PORT[protocol])}
                style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
            ))}
          </div>
        </div>
        <div style={{ borderTop: `1px solid ${J.border}`, paddingTop: 12, marginTop: 2 }}>
          <div style={{ fontSize: 12, color: J.textMuted, marginBottom: 10, lineHeight: 1.5 }}>
            Wake-on-LAN (optional) — Tailscale cannot deliver a broadcast magic packet directly, so waking a sleeping
            machine requires a relay device on its own physical network. Leave blank if not available.
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <div style={{ flex: 1 }}>
              {labeledInput('Relay host (Tailscale)', (
                <input className="j-input" value={relay} onChange={e => setRelay(e.target.value)} placeholder="optional"
                  style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
              ))}
            </div>
            <div style={{ flex: 1 }}>
              {labeledInput('Target MAC address', (
                <input className="j-input" value={mac} onChange={e => setMac(e.target.value)} placeholder="AA:BB:CC:DD:EE:FF"
                  style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </OverlayDialog>
  );
}

function CredentialsModal({ target, onClose, onSaved }: { target: WorkspaceTarget; onClose: () => void; onSaved: () => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const needsUsername = target.protocol === 'rdp';

  const submit = async () => {
    if (!password.trim() || (needsUsername && !username.trim()) || saving) return;
    setSaving(true);
    try {
      await setWorkspaceCredentials(target.id, { username: username.trim() || undefined, password });
      showToast('Credentials saved', 'success');
      onSaved();
      onClose();
    } catch (err) {
      showToast(errMsg(err, 'Failed to save credentials'), 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <OverlayDialog
      title={`Credentials — ${target.name}`}
      onClose={onClose}
      actions={
        <>
          <button onClick={onClose} className="j-btn" style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '8px 16px', fontSize: 13 }}>Cancel</button>
          <button onClick={submit} disabled={!password.trim() || (needsUsername && !username.trim()) || saving} className="j-btn"
            style={{ background: J.amber, color: J.bg0, borderRadius: 8, padding: '8px 20px', fontSize: 13, fontWeight: 600, opacity: password.trim() ? 1 : .5 }}>
            {saving ? <Spinner size={13} color={J.bg0} /> : 'Save'}
          </button>
        </>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ fontSize: 12.5, color: J.textSec, lineHeight: 1.6 }}>
          Stored encrypted at rest and used only to build the one-time Guacamole connection token when you click Connect.
        </div>
        {needsUsername && labeledInput('Username', (
          <input className="j-input" autoFocus value={username} onChange={e => setUsername(e.target.value)}
            style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
        ))}
        {labeledInput('Password', (
          <input className="j-input" type="password" value={password} onChange={e => setPassword(e.target.value)}
            style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
        ))}
      </div>
    </OverlayDialog>
  );
}

function TargetCard({
  target, configured, connecting, waking, onEdit, onDelete, onCredentials, onConnect, onWake,
}: {
  target: WorkspaceTarget;
  configured: boolean | undefined;
  connecting: boolean;
  waking: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onCredentials: () => void;
  onConnect: () => void;
  onWake: () => void;
}) {
  const canWake = !!target.wol_relay_host && !!target.wol_mac;
  return (
    <div style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 12, padding: '16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 30, height: 30, borderRadius: 8, background: J.bg3, display: 'flex', alignItems: 'center', justifyContent: 'center', color: J.textSec, flexShrink: 0 }}>
            <IconMonitor size={15} />
          </div>
          <div style={{ fontSize: 14, fontWeight: 500, color: J.text }}>{target.name}</div>
        </div>
        <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
          <button onClick={onCredentials} title="Set credentials" aria-label="Set credentials"
            style={{ background: J.bg3, border: `1px solid ${J.border}`, color: configured ? J.success : J.textMuted, borderRadius: 6, width: 26, height: 26, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
            <IconKey size={13} />
          </button>
          <button onClick={onEdit} title="Edit target" aria-label="Edit target"
            style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textMuted, borderRadius: 6, width: 26, height: 26, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
            <IconPencil size={13} />
          </button>
          <button onClick={onDelete} title="Delete target" aria-label="Delete target"
            style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textMuted, borderRadius: 6, width: 26, height: 26, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
            <IconTrash size={13} />
          </button>
        </div>
      </div>

      <div style={{ fontSize: 12, color: J.textSec, fontFamily: 'ui-monospace, monospace' }}>
        {target.tailscale_host}:{target.port}
      </div>

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <Pill label={target.os_type} color={J.blue} />
        <Pill label={target.protocol.toUpperCase()} color={J.textSec} />
        <Pill label={configured ? 'credentials set' : 'no credentials'} color={configured ? J.success : J.warn} />
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
        <button onClick={onConnect} disabled={connecting} className="j-btn"
          style={{ flex: 1, background: J.amber, color: J.bg0, borderRadius: 8, padding: '9px 12px', fontSize: 13, fontWeight: 600, justifyContent: 'center', opacity: connecting ? .7 : 1 }}>
          {connecting ? <Spinner size={13} color={J.bg0} /> : <><IconExternal size={13} /> Connect</>}
        </button>
        <button onClick={onWake} disabled={!canWake || waking} title={canWake ? 'Send Wake-on-LAN' : 'No wol_relay_host configured for this target — Wake-on-LAN unavailable'}
          className="j-btn"
          style={{ background: J.bg3, border: `1px solid ${J.border}`, color: canWake ? J.textSec : J.textMuted, borderRadius: 8, padding: '9px 12px', fontSize: 13, opacity: canWake ? 1 : .45, cursor: canWake ? 'pointer' : 'not-allowed' }}>
          {waking ? <Spinner size={13} /> : <IconZap size={13} />}
        </button>
      </div>
      {!canWake && (
        <div style={{ fontSize: 11, color: J.textMuted, lineHeight: 1.5 }}>
          Wake disabled — no relay device configured on this target's physical LAN.
        </div>
      )}
    </div>
  );
}

export function WorkspaceScreen(_props: { onNavigate?: (screen: string) => void }) {
  useJ();
  const [targets, setTargets] = useState<WorkspaceTarget[]>([]);
  const [credentialStatus, setCredentialStatus] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState<'new' | WorkspaceTarget | null>(null);
  const [credentialsFor, setCredentialsFor] = useState<WorkspaceTarget | null>(null);
  const [connectingId, setConnectingId] = useState<string | null>(null);
  const [wakingId, setWakingId] = useState<string | null>(null);

  const loadCredentialStatuses = async (list: WorkspaceTarget[]) => {
    const entries = await Promise.all(list.map(async t => {
      try {
        const res = await fetchWorkspaceCredentialsStatus(t.id);
        return [t.id, res.status.configured] as const;
      } catch {
        return [t.id, false] as const;
      }
    }));
    setCredentialStatus(Object.fromEntries(entries));
  };

  const load = () => {
    setLoading(true);
    setError(null);
    fetchWorkspaceTargets()
      .then(res => {
        setTargets(res.targets);
        return loadCredentialStatuses(res.targets);
      })
      .catch(err => setError(errMsg(err, 'Failed to load workspace targets')))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleDelete = async (id: string) => {
    try {
      await deleteWorkspaceTarget(id);
      setTargets(prev => prev.filter(t => t.id !== id));
      showToast('Target deleted', 'info');
    } catch (err) {
      showToast(errMsg(err, 'Failed to delete target'), 'error');
    }
  };

  const handleConnect = async (target: WorkspaceTarget) => {
    setConnectingId(target.id);
    try {
      const res = await connectWorkspaceTarget(target.id);
      const win = window.open(res.url, '_blank', 'noopener,noreferrer');
      if (!win) {
        showToast('Pop-up blocked — allow pop-ups for JARVIS or open the connection link manually.', 'error');
      } else {
        showToast(`Connecting to ${target.name}...`, 'success');
      }
    } catch (err) {
      showToast(errMsg(err, 'Failed to start connection'), 'error');
    } finally {
      setConnectingId(null);
    }
  };

  const handleWake = async (target: WorkspaceTarget) => {
    setWakingId(target.id);
    try {
      const res = await wakeWorkspaceTarget(target.id);
      showToast(res.detail, 'info', 5000);
    } catch (err) {
      showToast(errMsg(err, 'Wake failed'), 'error');
    } finally {
      setWakingId(null);
    }
  };

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: J.bg0 }}>
      <div style={{ height: 50, borderBottom: `1px solid ${J.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px', background: J.bg1, flexShrink: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 500, color: J.text }}>Workspace</div>
        <button onClick={() => setShowForm('new')} className="j-btn"
          style={{ background: J.amberDim, border: `1px solid ${J.borderAccent}`, color: J.amber, borderRadius: 8, padding: '6px 14px', fontSize: 13, fontWeight: 500 }}>
          <IconPlus size={13} /> New Target
        </button>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '22px 24px' }}>
        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: J.textMuted, fontSize: 13, padding: '24px 0' }}>
            <Spinner size={14} /> Loading workspace targets...
          </div>
        )}

        {!loading && error && (
          <div style={{ background: J.errorDim, border: `1px solid ${J.error}`, borderRadius: 10, padding: '12px 16px', color: J.error, fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            {error}
            <button onClick={load} style={{ background: 'none', border: 'none', color: J.error, cursor: 'pointer', display: 'flex' }}><IconX size={14} /></button>
          </div>
        )}

        {!loading && !error && targets.length === 0 && (
          <div style={{ textAlign: 'center', color: J.textMuted, fontSize: 13, padding: '48px 0' }}>
            No remote PCs configured yet. Add one to connect from anywhere via Guacamole.
          </div>
        )}

        {!loading && !error && targets.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(280px,1fr))', gap: 10 }}>
            {targets.map(t => (
              <TargetCard
                key={t.id}
                target={t}
                configured={credentialStatus[t.id]}
                connecting={connectingId === t.id}
                waking={wakingId === t.id}
                onEdit={() => setShowForm(t)}
                onDelete={() => handleDelete(t.id)}
                onCredentials={() => setCredentialsFor(t)}
                onConnect={() => handleConnect(t)}
                onWake={() => handleWake(t)}
              />
            ))}
          </div>
        )}
      </div>
      {showForm && (
        <TargetFormModal
          target={showForm === 'new' ? null : showForm}
          onClose={() => setShowForm(null)}
          onSaved={saved => setTargets(prev => {
            const exists = prev.some(t => t.id === saved.id);
            return exists ? prev.map(t => (t.id === saved.id ? saved : t)) : [...prev, saved];
          })}
        />
      )}
      {credentialsFor && (
        <CredentialsModal
          target={credentialsFor}
          onClose={() => setCredentialsFor(null)}
          onSaved={() => setCredentialStatus(prev => ({ ...prev, [credentialsFor.id]: true }))}
        />
      )}
    </div>
  );
}
