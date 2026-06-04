import { useEffect, useMemo, useState } from 'react';
import {
  J, useJ, StatusBadge, MetricCard, Spinner,
  IconRefresh, IconServer, IconActivity, IconGrid, IconPower, IconChat, IconSearch,
} from './jarvis-shared';
import { sendChatMessage } from '../shared/api/chat';
import { fetchProxmoxHealth, type ProxmoxHostHealth, type ProxmoxResource } from '../shared/api/proxmox';
import { OverlayDialog } from '../shared/ui/OverlayDialog';

function fmtPercent(value?: number) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—';
  return `${Math.round(value * 100)}%`;
}

function fmtMem(value?: number, max?: number) {
  if (typeof value !== 'number' || typeof max !== 'number' || Number.isNaN(value) || Number.isNaN(max) || max <= 0) return '—';
  const gb = (bytes: number) => `${(bytes / (1024 ** 3)).toFixed(1)} GB`;
  return `${gb(value)} / ${gb(max)}`;
}

function fmtUptime(seconds?: number) {
  if (typeof seconds !== 'number' || seconds <= 0) return null;
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function MiniBar({ pct, color }: { pct: number; color: string }) {
  return (
    <div style={{ width: 44, height: 4, borderRadius: 2, background: J.bg4, overflow: 'hidden', flexShrink: 0 }}>
      <div style={{ width: `${Math.min(Math.max(pct, 0), 100)}%`, height: '100%', background: color, borderRadius: 2, transition: 'width .5s ease' }} />
    </div>
  );
}

function resourceLabel(resource: ProxmoxResource, fallback: string) {
  return resource.name || `${fallback} ${resource.vmid}`;
}

function ResourceRow({
  hostId,
  node,
  kind,
  resource,
  busy,
  onAction,
}: {
  hostId: string;
  node: string;
  kind: 'vm' | 'lxc';
  resource: ProxmoxResource;
  busy: boolean;
  onAction: (resource: ProxmoxResource, action: 'start' | 'stop' | 'restart') => void;
}) {
  const running = (resource.status || '').toLowerCase() === 'running';
  const stopped = (resource.status || '').toLowerCase() === 'stopped';
  const canStart = stopped;
  const canStop = running;
  const cpuPct = typeof resource.cpu === 'number' ? resource.cpu * 100 : 0;
  const memPct = typeof resource.mem === 'number' && typeof resource.maxmem === 'number' && resource.maxmem > 0
    ? (resource.mem / resource.maxmem) * 100 : 0;
  const cpuColor = cpuPct > 80 ? J.error : cpuPct > 50 ? J.warn : J.success;
  const memColor = memPct > 85 ? J.error : memPct > 60 ? J.warn : J.blue;
  const uptime = fmtUptime(resource.uptime);

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,2fr) repeat(2,minmax(90px,1fr)) auto', gap: 10, alignItems: 'center', padding: '11px 12px', borderTop: `1px solid ${J.border}` }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: J.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {resourceLabel(resource, kind.toUpperCase())}
        </div>
        <div style={{ fontSize: 11, color: J.textMuted, marginTop: 2, fontFamily: 'JetBrains Mono,monospace', display: 'flex', alignItems: 'center', gap: 7 }}>
          <span>{hostId}/{node}/{resource.vmid}</span>
          {uptime && running && <span style={{ color: J.textMuted }}>up {uptime}</span>}
          <span style={{ fontSize: 10, color: kind === 'vm' ? J.blue : J.amber, background: kind === 'vm' ? 'rgba(56,144,224,0.12)' : J.amberDim, border: `1px solid ${kind === 'vm' ? 'rgba(56,144,224,0.25)' : J.borderAccent}`, borderRadius: 3, padding: '0 4px' }}>{kind.toUpperCase()}</span>
        </div>
      </div>
      <div>
        <StatusBadge status={resource.status || 'unknown'} size="xs" />
        {running && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 5 }}>
            <MiniBar pct={cpuPct} color={cpuColor} />
            <span style={{ fontSize: 10, color: cpuColor, fontFamily: 'JetBrains Mono,monospace', minWidth: 32 }}>{fmtPercent(resource.cpu)}</span>
          </div>
        )}
      </div>
      <div style={{ fontSize: 12, color: J.textSec }}>
        {running ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <MiniBar pct={memPct} color={memColor} />
              <span style={{ fontSize: 10, color: memColor, fontFamily: 'JetBrains Mono,monospace' }}>{Math.round(memPct)}%</span>
            </div>
            <div style={{ fontSize: 10, color: J.textMuted }}>{fmtMem(resource.mem, resource.maxmem)}</div>
          </div>
        ) : '—'}
      </div>
      <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
        {canStop && (
          <button
            className="j-btn"
            onClick={() => onAction(resource, 'restart')}
            disabled={busy}
            title="Restart"
            style={{ background: busy ? J.bg3 : J.bg4, border: `1px solid ${J.border}`, color: busy ? J.textMuted : J.textSec, borderRadius: 7, padding: '5px 9px', fontSize: 12, cursor: busy ? 'default' : 'pointer' }}
            onMouseEnter={e => { if (!busy) { e.currentTarget.style.borderColor = J.borderAccent; e.currentTarget.style.color = J.amber; } }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = J.border; e.currentTarget.style.color = J.textSec; }}>
            ↺
          </button>
        )}
        <button
          className="j-btn"
          onClick={() => onAction(resource, canStart ? 'start' : 'stop')}
          disabled={busy || (!canStart && !canStop)}
          style={{
            background: busy || (!canStart && !canStop) ? J.bg3 : canStop ? J.errorDim : J.amberDim,
            border: `1px solid ${busy || (!canStart && !canStop) ? J.border : canStop ? 'rgba(224,85,85,0.28)' : J.borderAccent}`,
            color: busy || (!canStart && !canStop) ? J.textMuted : canStop ? J.error : J.amber,
            borderRadius: 7,
            padding: '5px 11px',
            fontSize: 12,
            fontWeight: 500,
            minWidth: 68,
            justifyContent: 'center',
            cursor: busy || (!canStart && !canStop) ? 'default' : 'pointer',
          }}
        >
          {busy ? <Spinner size={12} color={J.textMuted} /> : <IconPower size={12} />}
          {canStop ? 'Stop' : 'Start'}
        </button>
      </div>
    </div>
  );
}

function NodeCard({
  host,
  node,
  busyKey,
  kindFilter,
  statusFilter,
  search,
  onAction,
}: {
  host: ProxmoxHostHealth;
  node: ProxmoxHostHealth['nodes'][number];
  busyKey: string | null;
  kindFilter: 'vm' | 'lxc' | null;
  statusFilter: 'running' | 'stopped' | null;
  search: string;
  onAction: (kind: 'vm' | 'lxc', resource: ProxmoxResource, action: 'start' | 'stop' | 'restart') => void;
}) {
  const q = search.toLowerCase();
  const allResources = [
    ...node.vms.map((resource) => ({ kind: 'vm' as const, resource })),
    ...node.containers.map((resource) => ({ kind: 'lxc' as const, resource })),
  ];
  const resources = allResources.filter(({ kind, resource }) => {
    if (kindFilter && kind !== kindFilter) return false;
    if (statusFilter && (resource.status || '').toLowerCase() !== statusFilter) return false;
    if (q && !resourceLabel(resource, kind.toUpperCase()).toLowerCase().includes(q) && !String(resource.vmid).includes(q)) return false;
    return true;
  });

  if (resources.length === 0 && (kindFilter || statusFilter || search)) return null;

  return (
    <div style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 14, overflow: 'hidden' }}>
      <div style={{ padding: '14px 16px', borderBottom: `1px solid ${J.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: J.text }}>{node.node}</span>
            <StatusBadge status={node.online ? 'online' : node.status} size="xs" />
          </div>
          <div style={{ fontSize: 12, color: J.textMuted, marginTop: 3 }}>
            {node.vms.length} VM · {node.containers.length} LXC · CPU {fmtPercent(node.cpu)}
          </div>
        </div>
        <div style={{ fontSize: 12, color: J.textMuted }}>{fmtMem(node.mem, node.maxmem)}</div>
      </div>

      {resources.length === 0 ? (
        <div style={{ padding: '16px', fontSize: 13, color: J.textMuted }}>No workloads on this node.</div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,2fr) repeat(2,minmax(90px,1fr)) auto', gap: 10, padding: '8px 12px', fontSize: 10, color: J.textMuted, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 600 }}>
            <span>Workload</span>
            <span>Status / CPU</span>
            <span>Memory</span>
            <span style={{ textAlign: 'right' }}>Actions</span>
          </div>
          {resources.map(({ kind, resource }) => {
            const rowKey = `${kind}:${host.id}:${node.node}:${resource.vmid}`;
            return (
              <ResourceRow
                key={rowKey}
                hostId={host.id}
                node={node.node}
                kind={kind}
                resource={resource}
                busy={busyKey === rowKey}
                onAction={(target, action) => onAction(kind, target, action)}
              />
            );
          })}
        </>
      )}
    </div>
  );
}

type PendingAction = {
  kind: 'vm' | 'lxc';
  host: ProxmoxHostHealth;
  nodeName: string;
  resource: ProxmoxResource;
  action: 'stop' | 'restart';
};

export function ProxmoxScreen({ onNavigate }: { onNavigate: (screen: string) => void }) {
  useJ();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hosts, setHosts] = useState<ProxmoxHostHealth[]>([]);
  const [summary, setSummary] = useState({ hosts: 0, nodes: 0, vms: 0, containers: 0, running: 0, stopped: 0 });
  const [hint, setHint] = useState<string | null>(null);
  const [lastSync, setLastSync] = useState('—');
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(30);
  const [search, setSearch] = useState('');
  const [kindFilter, setKindFilter] = useState<'vm' | 'lxc' | null>(null);
  const [statusFilter, setStatusFilter] = useState<'running' | 'stopped' | null>(null);
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);

  const unhealthyHosts = useMemo(() => hosts.filter((host) => !host.healthy).length, [hosts]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchProxmoxHealth();
      setHosts(data.hosts || []);
      setSummary(data.summary);
      setHint(data.hint || null);
      setLastSync(new Date().toLocaleTimeString());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load Proxmox state.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    const refresh = window.setInterval(() => {
      setCountdown(c => {
        if (c <= 1) { void load(); return 30; }
        return c - 1;
      });
    }, 1000);
    return () => window.clearInterval(refresh);
  }, []);

  const handleAction = async (kind: 'vm' | 'lxc', host: ProxmoxHostHealth, nodeName: string, resource: ProxmoxResource, action: 'start' | 'stop' | 'restart') => {
    const key = `${kind}:${host.id}:${nodeName}:${resource.vmid}`;
    setBusyKey(key);
    setActionMessage(null);
    try {
      const command = action === 'restart'
        ? `pve restart ${kind} ${host.id} ${nodeName} ${resource.vmid}`
        : `pve ${action} ${kind} ${host.id} ${nodeName} ${resource.vmid}`;
      const response = await sendChatMessage(command, 'web', 'chat');
      setActionMessage(response.reply || `${action} queued.`);
      window.setTimeout(() => { void load(); }, 1200);
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : `Failed to ${action} workload.`);
    } finally {
      setBusyKey(null);
    }
  };

  if (loading) {
    return <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: J.bg0 }}><Spinner size={24} /></div>;
  }

  if (error) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12, background: J.bg0 }}>
        <div style={{ fontSize: 16, fontWeight: 600, color: J.error }}>Failed to load Proxmox</div>
        <div style={{ fontSize: 13, color: J.textMuted, maxWidth: 360, textAlign: 'center' }}>{error}</div>
        <button onClick={() => void load()} className="j-btn" style={{ background: J.bg2, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '8px 16px', fontSize: 13 }}>
          <IconRefresh size={13} /> Retry
        </button>
      </div>
    );
  }

  const hasFilters = search || kindFilter || statusFilter;

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: J.bg0 }}>
      <div style={{ height: 50, borderBottom: `1px solid ${J.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 20px', background: J.bg1, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 14, fontWeight: 500, color: J.text }}>Proxmox</span>
          <StatusBadge status={unhealthyHosts > 0 ? 'warning' : 'connected'} size="xs" />
          <span style={{ fontSize: 12, color: J.textMuted }}>{summary.vms + summary.containers} workloads</span>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button onClick={() => onNavigate('chat')} className="j-btn" style={{ background: J.bg2, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 7, padding: '5px 11px', fontSize: 12 }}>
            <IconChat size={12} /> Chat
          </button>
          <span style={{ fontSize: 12, color: J.textMuted }}>Updated {lastSync}</span>
          <span style={{ fontSize: 11, color: J.textMuted }}>auto in {countdown}s</span>
          <button onClick={() => { void load(); setCountdown(30); }} className="j-btn" style={{ background: J.bg2, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 7, padding: '5px 11px', fontSize: 12 }}>
            <IconRefresh size={12} /> Refresh
          </button>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '22px 24px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(160px,1fr))', gap: 10, marginBottom: 20 }}>
          <MetricCard label="Hosts" value={summary.hosts} sublabel={unhealthyHosts ? `${unhealthyHosts} unhealthy` : 'Connected endpoints'} icon={<IconServer size={14} />} />
          <MetricCard label="Nodes" value={summary.nodes} sublabel="Available compute nodes" icon={<IconGrid size={14} />} />
          <MetricCard label="Running" value={summary.running} sublabel={`${summary.vms} VMs · ${summary.containers} LXCs`} icon={<IconActivity size={14} />} accent={J.success} />
          <MetricCard label="Stopped" value={summary.stopped} sublabel="Ready to start" icon={<IconPower size={14} />} accent={J.warn} />
        </div>

        {/* Filter bar */}
        {hosts.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
            <div style={{ position: 'relative', flexShrink: 0 }}>
              <span style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: J.textMuted, pointerEvents: 'none' }}><IconSearch size={12} /></span>
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search workloads…"
                style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 8, padding: '6px 11px 6px 28px', fontSize: 12, color: J.text, width: 190, outline: 'none' }}
                onFocus={e => { e.currentTarget.style.borderColor = J.borderHover; }}
                onBlur={e => { e.currentTarget.style.borderColor = J.border; }} />
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              {(['vm', 'lxc'] as const).map(k => (
                <button key={k} onClick={() => setKindFilter(kindFilter === k ? null : k)}
                  style={{ padding: '4px 11px', fontSize: 11, fontWeight: kindFilter === k ? 600 : 400, borderRadius: 20, border: `1px solid ${kindFilter === k ? J.amber : J.border}`, background: kindFilter === k ? J.amberDim : J.bg2, color: kindFilter === k ? J.amber : J.textSec, cursor: 'pointer', textTransform: 'uppercase', transition: 'all .12s' }}
                  onMouseEnter={e => { if (kindFilter !== k) { e.currentTarget.style.borderColor = J.borderHover; e.currentTarget.style.color = J.text; } }}
                  onMouseLeave={e => { if (kindFilter !== k) { e.currentTarget.style.borderColor = J.border; e.currentTarget.style.color = J.textSec; } }}>
                  {k}
                </button>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              {(['running', 'stopped'] as const).map(s => (
                <button key={s} onClick={() => setStatusFilter(statusFilter === s ? null : s)}
                  style={{ padding: '4px 11px', fontSize: 11, fontWeight: statusFilter === s ? 600 : 400, borderRadius: 20, border: `1px solid ${statusFilter === s ? (s === 'running' ? J.success : J.textMuted) : J.border}`, background: statusFilter === s ? (s === 'running' ? 'rgba(61,186,132,0.1)' : J.bg3) : J.bg2, color: statusFilter === s ? (s === 'running' ? J.success : J.text) : J.textSec, cursor: 'pointer', textTransform: 'capitalize', transition: 'all .12s' }}
                  onMouseEnter={e => { if (statusFilter !== s) { e.currentTarget.style.borderColor = J.borderHover; e.currentTarget.style.color = J.text; } }}
                  onMouseLeave={e => { if (statusFilter !== s) { e.currentTarget.style.borderColor = J.border; e.currentTarget.style.color = J.textSec; } }}>
                  {s}
                </button>
              ))}
            </div>
            {hasFilters && (
              <button onClick={() => { setSearch(''); setKindFilter(null); setStatusFilter(null); }}
                style={{ padding: '4px 9px', fontSize: 11, borderRadius: 20, border: `1px solid ${J.border}`, background: 'none', color: J.textMuted, cursor: 'pointer', transition: 'all .12s' }}>
                Clear
              </button>
            )}
          </div>
        )}

        {actionMessage && (
          <div style={{ marginBottom: 16, padding: '11px 14px', borderRadius: 10, background: J.bg2, border: `1px solid ${J.border}`, color: J.textSec, fontSize: 13 }}>
            {actionMessage}
          </div>
        )}

        {hint && hosts.length === 0 && (
          <div style={{ marginBottom: 16, padding: '14px 16px', borderRadius: 12, background: J.bg2, border: `1px solid ${J.border}`, color: J.textMuted, fontSize: 13 }}>
            {hint}
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {hosts.map((host) => (
            <div key={host.id} style={{ background: J.bg1, border: `1px solid ${J.border}`, borderRadius: 16, overflow: 'hidden' }}>
              <div style={{ padding: '16px 18px', borderBottom: `1px solid ${J.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                    <span style={{ fontSize: 15, fontWeight: 600, color: J.text }}>{host.name}</span>
                    <StatusBadge status={host.healthy ? 'connected' : 'error'} size="xs" />
                  </div>
                  <div style={{ fontSize: 12, color: J.textMuted, marginTop: 4 }}>{host.base_url}</div>
                </div>
                <div style={{ fontSize: 12, color: J.textMuted }}>{host.nodes.length} nodes</div>
              </div>

              {!host.healthy ? (
                <div style={{ padding: '16px 18px', color: J.error, fontSize: 13 }}>{host.error || 'Unable to query this host.'}</div>
              ) : host.nodes.length === 0 ? (
                <div style={{ padding: '16px 18px', color: J.textMuted, fontSize: 13 }}>No nodes returned for this host.</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '14px' }}>
                  {host.nodes.map((node) => (
                    <NodeCard
                      key={`${host.id}:${node.node}`}
                      host={host}
                      node={node}
                      busyKey={busyKey}
                      kindFilter={kindFilter}
                      statusFilter={statusFilter}
                      search={search}
                      onAction={(kind, resource, action) => {
                if (action === 'stop' || action === 'restart') {
                  setPendingAction({ kind, host, nodeName: node.node, resource, action });
                } else {
                  void handleAction(kind, host, node.node, resource, action);
                }
              }}
                    />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {pendingAction && (
        <OverlayDialog
          title={`${pendingAction.action === 'restart' ? 'Restart' : 'Stop'} ${resourceLabel(pendingAction.resource, pendingAction.kind.toUpperCase())}?`}
          eyebrow="Confirm action"
          onClose={() => setPendingAction(null)}
          actions={
            <>
              <button
                className="j-btn"
                onClick={() => setPendingAction(null)}
                style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '7px 18px', fontSize: 13, cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                className="j-btn"
                onClick={() => {
                  const p = pendingAction;
                  setPendingAction(null);
                  void handleAction(p.kind, p.host, p.nodeName, p.resource, p.action);
                }}
                style={{ background: J.errorDim, border: '1px solid rgba(224,85,85,0.35)', color: J.error, borderRadius: 8, padding: '7px 18px', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
              >
                {pendingAction.action === 'restart' ? 'Restart' : 'Stop'}
              </button>
            </>
          }
        >
          <div style={{ fontSize: 13, color: J.textSec, lineHeight: 1.5 }}>
            {pendingAction.action === 'restart'
              ? `This will restart the workload. It will be briefly unavailable.`
              : `This will stop the workload. It can be started again from this screen.`}
            <div style={{ fontSize: 12, color: J.textMuted, marginTop: 8, fontFamily: 'JetBrains Mono, monospace' }}>
              {pendingAction.host.id}/{pendingAction.nodeName}/{pendingAction.resource.vmid}
            </div>
          </div>
        </OverlayDialog>
      )}
    </div>
  );
}
