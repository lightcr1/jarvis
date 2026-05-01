import { useEffect, useMemo, useState } from 'react';
import {
  J, useJ, StatusBadge, MetricCard, Spinner,
  IconRefresh, IconServer, IconActivity, IconGrid, IconPower, IconChat,
} from './jarvis-shared';
import { sendChatMessage } from '../shared/api/chat';
import { fetchProxmoxHealth, type ProxmoxHostHealth, type ProxmoxResource } from '../shared/api/proxmox';

function fmtPercent(value?: number) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—';
  return `${Math.round(value * 100)}%`;
}

function fmtMem(value?: number, max?: number) {
  if (typeof value !== 'number' || typeof max !== 'number' || Number.isNaN(value) || Number.isNaN(max) || max <= 0) return '—';
  const gb = (bytes: number) => `${(bytes / (1024 ** 3)).toFixed(1)} GB`;
  return `${gb(value)} / ${gb(max)}`;
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
  onAction: (resource: ProxmoxResource, action: 'start' | 'stop') => void;
}) {
  const running = (resource.status || '').toLowerCase() === 'running';
  const stopped = (resource.status || '').toLowerCase() === 'stopped';
  const primaryAction: 'start' | 'stop' = running ? 'stop' : 'start';
  const primaryDisabled = busy || (!running && !stopped);

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.8fr) repeat(3,minmax(72px,.8fr)) auto', gap: 10, alignItems: 'center', padding: '11px 12px', borderTop: `1px solid ${J.border}` }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: J.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {resourceLabel(resource, kind.toUpperCase())}
        </div>
        <div style={{ fontSize: 11, color: J.textMuted, marginTop: 2, fontFamily: 'JetBrains Mono,monospace' }}>
          {hostId}/{node}/{resource.vmid}
        </div>
      </div>
      <div><StatusBadge status={resource.status || 'unknown'} size="xs" /></div>
      <div style={{ fontSize: 12, color: J.textSec }}>{fmtPercent(resource.cpu)}</div>
      <div style={{ fontSize: 12, color: J.textSec }}>{fmtMem(resource.mem, resource.maxmem)}</div>
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button
          className="j-btn"
          onClick={() => onAction(resource, primaryAction)}
          disabled={primaryDisabled}
          style={{
            background: primaryDisabled ? J.bg3 : primaryAction === 'stop' ? J.errorDim : J.amberDim,
            border: `1px solid ${primaryDisabled ? J.border : primaryAction === 'stop' ? 'rgba(224,85,85,0.28)' : J.borderAccent}`,
            color: primaryDisabled ? J.textMuted : primaryAction === 'stop' ? J.error : J.amber,
            borderRadius: 7,
            padding: '5px 11px',
            fontSize: 12,
            fontWeight: 500,
            minWidth: 72,
            justifyContent: 'center',
            cursor: primaryDisabled ? 'default' : 'pointer',
          }}
        >
          {busy ? <Spinner size={12} color={J.textMuted} /> : <IconPower size={12} />}
          {primaryAction === 'stop' ? 'Stop' : 'Start'}
        </button>
      </div>
    </div>
  );
}

function NodeCard({
  host,
  node,
  busyKey,
  onAction,
}: {
  host: ProxmoxHostHealth;
  node: ProxmoxHostHealth['nodes'][number];
  busyKey: string | null;
  onAction: (kind: 'vm' | 'lxc', resource: ProxmoxResource, action: 'start' | 'stop') => void;
}) {
  const resources = [
    ...node.vms.map((resource) => ({ kind: 'vm' as const, resource })),
    ...node.containers.map((resource) => ({ kind: 'lxc' as const, resource })),
  ];

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
        <div style={{ padding: '16px', fontSize: 13, color: J.textMuted }}>No workloads reported on this node.</div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.8fr) repeat(3,minmax(72px,.8fr)) auto', gap: 10, padding: '8px 12px', fontSize: 10, color: J.textMuted, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 600 }}>
            <span>Workload</span>
            <span>Status</span>
            <span>CPU</span>
            <span>Memory</span>
            <span style={{ textAlign: 'right' }}>Action</span>
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

  const handleAction = async (kind: 'vm' | 'lxc', host: ProxmoxHostHealth, nodeName: string, resource: ProxmoxResource, action: 'start' | 'stop') => {
    const key = `${kind}:${host.id}:${nodeName}:${resource.vmid}`;
    setBusyKey(key);
    setActionMessage(null);
    try {
      const command = `pve ${action} ${kind} ${host.id} ${nodeName} ${resource.vmid}`;
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
                      onAction={(kind, resource, action) => void handleAction(kind, host, node.node, resource, action)}
                    />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
