import React, { useEffect, useState } from "react";
import { AdminAuditEvent, AdminSession, AdminStatusSummary, fetchAdminAuditCounts, fetchAdminAuditEvents, fetchAdminSessions, fetchAdminStatusSummary, revokeAdminSession, downloadAdminBackup, restoreAdminBackup } from "../../../shared/api/admin";
import { getSystemMetrics } from "../../../shared/api/chat";
import type { SystemMetrics } from "../../../shared/api/chat";
import { useJ } from "../../../screens/jarvis-shared";

function fmtTs(ts: number): string {
  if (!ts) return "—";
  const d = new Date(ts > 1e10 ? ts : ts * 1000);
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function fmtDuration(sec: number): string {
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h`;
  return `${Math.floor(sec / 86400)}d`;
}

function MiniBar({ pct, color }: { pct: number; color: string }) {
  return (
    <div style={{ flex: 1, height: 4, borderRadius: 2, background: "rgba(255,255,255,0.07)", overflow: "hidden" }}>
      <div style={{ width: `${Math.min(pct, 100)}%`, height: "100%", background: color, borderRadius: 2, transition: "width 1s ease" }} />
    </div>
  );
}

function ActivityChart({ buckets, J }: { buckets: number[]; J: ReturnType<typeof useJ> }) {
  const max = Math.max(...buckets, 1);
  const W = 600, H = 52, pad = 2;
  const barW = (W - pad * (buckets.length - 1)) / buckets.length;
  const now = new Date();
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: H, display: "block" }}>
      {buckets.map((v, i) => {
        const barH = Math.max((v / max) * H, v > 0 ? 3 : 1);
        const x = i * (barW + pad);
        const hour = new Date(now.getTime() - (buckets.length - 1 - i) * 3_600_000).getHours();
        const isCurrent = i === buckets.length - 1;
        return (
          <g key={i}>
            <rect x={x} y={H - barH} width={barW} height={barH} rx={2}
              fill={isCurrent ? J.amber : J.amberDim.replace("0.1)", "0.35)")} />
            {i % 4 === 0 && (
              <text x={x + barW / 2} y={H - barH - 4} textAnchor="middle"
                fill={J.textMuted} fontSize={8} fontFamily="monospace">
                {String(hour).padStart(2, "0")}
              </text>
            )}
            <title>{`${String(hour).padStart(2, "0")}:00 — ${v} event${v !== 1 ? "s" : ""}`}</title>
          </g>
        );
      })}
    </svg>
  );
}

export function DashboardPage() {
  const J = useJ();
  const [summary, setSummary] = useState<AdminStatusSummary | null>(null);
  const [auditCounts, setAuditCounts] = useState<Record<string, number>>({});
  const [recentEvents, setRecentEvents] = useState<AdminAuditEvent[]>([]);
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [metricsTs, setMetricsTs] = useState(0);
  const [orphanOpen, setOrphanOpen] = useState(false);
  const [sessions, setSessions] = useState<AdminSession[]>([]);
  const [loadedAt, setLoadedAt] = useState<Date | null>(null);
  const [chartBuckets, setChartBuckets] = useState<number[]>(Array(24).fill(0));

  const buildChartBuckets = (events: AdminAuditEvent[]): number[] => {
    const buckets = Array(24).fill(0);
    const now = Date.now();
    for (const ev of events) {
      const ts = ev.ts > 1e10 ? ev.ts : ev.ts * 1000;
      const hoursAgo = Math.floor((now - ts) / 3_600_000);
      if (hoursAgo >= 0 && hoursAgo < 24) buckets[23 - hoursAgo]++;
    }
    return buckets;
  };

  const refreshAll = () => {
    const since24h = Math.floor((Date.now() - 86_400_000) / 1000);
    return Promise.all([
      fetchAdminStatusSummary(),
      fetchAdminAuditCounts(),
      fetchAdminAuditEvents("?limit=6"),
      fetchAdminSessions(),
      fetchAdminAuditEvents(`?limit=500&since_ts=${since24h}`),
    ]).then(([sd, cd, ed, ssd, chartd]) => {
      setSummary(sd);
      setAuditCounts(cd.counts || {});
      setRecentEvents(ed.events || []);
      setSessions(ssd.sessions || []);
      setChartBuckets(buildChartBuckets(chartd.events || []));
      setLoadedAt(new Date());
    }).catch(() => undefined);
  };

  useEffect(() => {
    void refreshAll();
    const id = setInterval(() => void refreshAll(), 30000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    let alive = true;
    const poll = () => getSystemMetrics().then(m => { if (alive) { setMetrics(m); setMetricsTs(Date.now()); } }).catch(() => {});
    poll();
    const id = setInterval(poll, 15000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const counts = summary?.counts || {};
  const haAuditEntries = Object.entries(auditCounts).filter(([ev]) => ev.startsWith("ha_"));
  const haAuditTotal = haAuditEntries.reduce((s, [, c]) => s + c, 0);
  const failedLogins = auditCounts["auth_login_failed"] || 0;

  const card: React.CSSProperties = {
    background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6,
  };
  const eyebrow: React.CSSProperties = {
    fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>

      {/* ── Hero ── */}
      <div style={{ ...card, padding: "20px 22px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <div style={{ ...eyebrow, marginBottom: 4 }}>Operations overview</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: J.text }}>Jarvis control dashboard</div>
          <div style={{ fontSize: 12, color: J.textSec, marginTop: 4 }}>Monitor operator status, audit activity, and configuration drift at a glance.</div>
          {loadedAt && (
            <div style={{ fontSize: 11, color: J.textMuted, marginTop: 6 }}>
              Loaded {loadedAt.toLocaleTimeString()} ·{" "}
              <button onClick={() => void refreshAll()} style={{ background: "none", border: "none", cursor: "pointer", color: J.amber, fontSize: 11, padding: 0, textDecoration: "underline" }}>Refresh</button>
            </div>
          )}
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ ...eyebrow, marginBottom: 6 }}>Lockout status</div>
          <div style={{
            display: "inline-block", padding: "4px 12px", borderRadius: 4, fontSize: 12, fontWeight: 600,
            background: counts.admin_lockout_state === "ok" ? J.successDim : J.warnDim,
            color: counts.admin_lockout_state === "ok" ? J.success : J.warn,
            border: `1px solid ${counts.admin_lockout_state === "ok" ? J.success + "30" : J.warn + "30"}`,
          }}>{counts.admin_lockout_state || "unknown"}</div>
        </div>
      </div>

      {/* ── Quick links ── */}
      <div style={{ ...card, padding: "12px 18px" }}>
        <div style={{ ...eyebrow, marginBottom: 10 }}>Quick links</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
          {[
            { label: "+ New User", href: "/dashboard/users" },
            { label: "Groups", href: "/dashboard/groups" },
            { label: "Audit Log", href: "/dashboard/logs" },
            { label: "Settings", href: "/dashboard/settings" },
            { label: "JARVIS Docs", href: "/?screen=docs" },
          ].map(({ label, href }) => (
            <a key={label} href={href} style={{
              padding: "5px 12px", fontSize: 12, borderRadius: 4, color: J.textSec,
              background: J.bg4, border: `1px solid ${J.border}`, textDecoration: "none", transition: "all .12s",
            }}
              onMouseEnter={e => { const el = e.currentTarget as HTMLAnchorElement; el.style.color = J.amber; el.style.borderColor = J.borderAccent; }}
              onMouseLeave={e => { const el = e.currentTarget as HTMLAnchorElement; el.style.color = J.textSec; el.style.borderColor = J.border; }}>
              {label}
            </a>
          ))}
        </div>
      </div>

      {/* ── Metrics grid ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: 10 }}>
        {[
          { key: "users", label: "Users" },
          { key: "groups", label: "Groups" },
          { key: "memberships", label: "Memberships" },
          { key: "audit_events", label: "Audit events" },
          { key: "ha_audit_total", label: "HA activity" },
          { key: "enabled_admins", label: "Active admins" },
          { key: "group_permission_sets", label: "Group perm sets" },
        ].map(({ key, label }) => (
          <div key={key} style={{ ...card, padding: "12px 16px" }}>
            <div style={{ ...eyebrow, marginBottom: 4 }}>{label}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: J.text }}>
              {String(key === "ha_audit_total" ? haAuditTotal : (counts[key] ?? 0))}
            </div>
          </div>
        ))}
        <div style={{ ...card, padding: "12px 16px" }}>
          <div style={{ ...eyebrow, marginBottom: 4 }}>Failed logins</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: failedLogins > 0 ? J.error : J.text }}>{failedLogins}</div>
        </div>
      </div>

      {/* ── Detail rows ── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
        {/* Integrity */}
        <div style={{ ...card, padding: "14px 16px" }}>
          <div style={{ ...eyebrow, marginBottom: 10 }}>Integrity</div>
          {[
            ["Orphan memberships", counts.orphan_memberships ?? 0],
            ["Orphan group perm sets", counts.orphan_group_permission_sets ?? 0],
            ["Orphan user perm sets", counts.orphan_user_permission_sets ?? 0],
            ["Disabled admins", counts.disabled_admins ?? 0],
          ].map(([label, val]) => (
            <div key={label as string} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", borderBottom: `1px solid ${J.border}`, fontSize: 12 }}>
              <span style={{ color: J.textSec }}>{label}</span>
              <strong style={{ color: (val as number) > 0 ? J.warn : J.text }}>{val}</strong>
            </div>
          ))}
        </div>

        {/* HA activity */}
        <div style={{ ...card, padding: "14px 16px" }}>
          <div style={{ ...eyebrow, marginBottom: 10 }}>HA activity</div>
          {haAuditEntries.length === 0
            ? <div style={{ fontSize: 12, color: J.textMuted }}>No HA audit events yet.</div>
            : haAuditEntries.slice(0, 6).map(([ev, cnt]) => (
              <div key={ev} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", borderBottom: `1px solid ${J.border}`, fontSize: 12 }}>
                <span style={{ color: J.textSec, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1, marginRight: 8 }}>{ev}</span>
                <strong style={{ color: J.amber, flexShrink: 0 }}>{cnt}</strong>
              </div>
            ))}
        </div>

        {/* Top events */}
        <div style={{ ...card, padding: "14px 16px" }}>
          <div style={{ ...eyebrow, marginBottom: 10 }}>Top events</div>
          {Object.keys(auditCounts).length === 0
            ? <div style={{ fontSize: 12, color: J.textMuted }}>No audit events yet.</div>
            : Object.entries(auditCounts).slice(0, 6).map(([ev, cnt]) => (
              <div key={ev} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", borderBottom: `1px solid ${J.border}`, fontSize: 12 }}>
                <span style={{ color: J.textSec, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1, marginRight: 8 }}>{ev}</span>
                <strong style={{ color: J.text, flexShrink: 0 }}>{cnt}</strong>
              </div>
            ))}
        </div>
      </div>

      {/* ── Activity chart ── */}
      <div style={{ ...card, padding: "14px 18px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <div style={eyebrow}>Audit activity — last 24h</div>
          <span style={{ fontSize: 11, color: J.textMuted }}>{chartBuckets.reduce((a, b) => a + b, 0)} events</span>
        </div>
        <ActivityChart buckets={chartBuckets} J={J} />
      </div>

      {/* ── Recent events ── */}
      <div style={{ ...card, overflow: "hidden" }}>
        <div style={{ padding: "10px 14px", borderBottom: `1px solid ${J.border}`, background: J.bg1 }}>
          <div style={eyebrow}>Recent admin activity</div>
        </div>
        {recentEvents.length === 0
          ? <div style={{ padding: "16px 14px", color: J.textMuted, fontSize: 12 }}>No admin events yet.</div>
          : recentEvents.map((ev, i) => (
            <div key={`${ev.ts}-${ev.event}-${i}`} style={{
              display: "flex", justifyContent: "space-between", alignItems: "center",
              padding: "9px 14px", borderBottom: i < recentEvents.length - 1 ? `1px solid ${J.border}` : "none",
              background: i % 2 === 1 ? J.bg1 : "transparent",
            }}>
              <div>
                <div style={{ fontSize: 12, color: J.text, fontWeight: 500 }}>{ev.event}</div>
                <div style={{ fontSize: 10, color: J.textMuted, marginTop: 2 }}>
                  {ev.actor_role || "unknown"} · {ev.actor_user_id || "system"}
                </div>
              </div>
              <div style={{ fontSize: 11, color: J.textMuted, whiteSpace: "nowrap" }}>{fmtTs(ev.ts)}</div>
            </div>
          ))
        }
      </div>

      {/* ── Server resources ── */}
      {metrics && (
        <div style={{ ...card, padding: "14px 18px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
            <div style={eyebrow}>Server resources</div>
            <span style={{ fontSize: 11, color: J.textMuted }}>↑ {metrics.uptime} · {new Date(metricsTs).toLocaleTimeString()}</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 16 }}>
            {[
              { label: "CPU", pct: metrics.cpu.pct, val: `${metrics.cpu.pct}%`, color: metrics.cpu.pct > 80 ? J.error : metrics.cpu.pct > 50 ? J.warn : J.success },
              { label: "RAM", pct: metrics.ram.pct, val: `${metrics.ram.used_gb} / ${metrics.ram.total_gb} GB`, color: metrics.ram.pct > 85 ? J.error : metrics.ram.pct > 60 ? J.warn : J.blue },
              { label: "DISK", pct: metrics.disk.pct, val: `${metrics.disk.used_gb} / ${metrics.disk.total_gb} GB`, color: metrics.disk.pct > 90 ? J.error : metrics.disk.pct > 70 ? J.warn : J.textSec },
            ].map(({ label, pct, val, color }) => (
              <div key={label} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                  <span style={{ ...eyebrow }}>{label}</span>
                  <span style={{ fontFamily: "monospace", fontSize: 12, color }}>{val}</span>
                </div>
                <MiniBar pct={pct} color={color} />
                <span style={{ fontSize: 10, color: J.textMuted }}>{pct}% used</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Sessions ── */}
      <div style={{ ...card, overflow: "hidden" }}>
        <div style={{ padding: "10px 14px", borderBottom: `1px solid ${J.border}`, background: J.bg1, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={eyebrow}>Active sessions</div>
          <span style={{ fontSize: 11, color: J.textMuted }}>{sessions.length} active</span>
        </div>
        {sessions.length === 0
          ? <div style={{ padding: "16px 14px", color: J.textMuted, fontSize: 12 }}>No active sessions.</div>
          : sessions.map((s, i) => (
            <div key={i} style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "9px 14px", borderBottom: i < sessions.length - 1 ? `1px solid ${J.border}` : "none",
              background: i % 2 === 1 ? J.bg1 : "transparent",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 13, color: J.text }}>{s.username}</span>
                <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 3, background: J.bg4, color: J.textSec }}>{s.role}</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 11, color: J.textMuted }} title={`Expires ${fmtTs(s.expires_at)}`}>expires in {fmtDuration(s.expires_in_sec)}</span>
                <button onClick={async () => {
                  if (!window.confirm(`Revoke all sessions for "${s.username}"?`)) return;
                  await revokeAdminSession(s.user_id);
                  const data = await fetchAdminSessions();
                  setSessions(data.sessions || []);
                }} style={{
                  padding: "3px 10px", fontSize: 11, borderRadius: 4, cursor: "pointer",
                  background: J.errorDim, color: J.error, border: `1px solid ${J.error}30`,
                }}>Revoke</button>
              </div>
            </div>
          ))
        }
      </div>

      {/* ── Orphan details (collapsible) ── */}
      <div style={{ ...card, overflow: "hidden" }}>
        <div style={{ padding: "10px 14px", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between" }}
          onClick={() => setOrphanOpen(v => !v)}>
          <div style={eyebrow}>Orphan details</div>
          <span style={{ fontSize: 11, color: J.textMuted }}>{orphanOpen ? "▲ hide" : "▼ show"}</span>
        </div>
        {orphanOpen && (() => {
          const orphans = summary?.orphans as { memberships?: unknown[]; group_permission_sets?: string[]; user_permission_sets?: string[] } | undefined;
          const memberships = orphans?.memberships || [];
          const groupPerms = orphans?.group_permission_sets || [];
          const userPerms = orphans?.user_permission_sets || [];
          const total = memberships.length + groupPerms.length + userPerms.length;
          return (
            <div style={{ padding: "0 14px 14px" }}>
              {total === 0 ? (
                <div style={{ fontSize: 12, color: J.success }}>No orphans detected — data is consistent.</div>
              ) : (
                <>
                  {[
                    ["Orphaned memberships", memberships.length],
                    ["Orphaned group permission sets", groupPerms.length],
                    ["Orphaned user permission sets", userPerms.length],
                  ].map(([label, val]) => (
                    <div key={label as string} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", borderBottom: `1px solid ${J.border}`, fontSize: 12 }}>
                      <span style={{ color: J.textSec }}>{label}</span>
                      <strong style={{ color: (val as number) > 0 ? J.error : J.text }}>{val}</strong>
                    </div>
                  ))}
                  {groupPerms.length > 0 && (
                    <div style={{ marginTop: 10 }}>
                      <div style={{ ...eyebrow, marginBottom: 6 }}>Orphaned group IDs</div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                        {groupPerms.map(id => <code key={id} style={{ fontSize: 10, fontFamily: "monospace", background: J.bg4, color: J.textSec, padding: "2px 6px", borderRadius: 3 }}>{id}</code>)}
                      </div>
                    </div>
                  )}
                  {userPerms.length > 0 && (
                    <div style={{ marginTop: 10 }}>
                      <div style={{ ...eyebrow, marginBottom: 6 }}>Orphaned user IDs</div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                        {userPerms.map(id => <code key={id} style={{ fontSize: 10, fontFamily: "monospace", background: J.bg4, color: J.textSec, padding: "2px 6px", borderRadius: 3 }}>{id}</code>)}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          );
        })()}
      </div>

      {/* ── Backup / Restore ── */}
      <div style={{ ...card, padding: "14px 18px" }}>
        <div style={{ ...eyebrow, marginBottom: 10 }}>Backup &amp; Restore</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 14 }}>
          {[
            ["Includes", "users, groups, memberships, permissions, settings"],
            ["Format", "JSON"],
          ].map(([k, v]) => (
            <div key={k as string} style={{ display: "flex", gap: 12, fontSize: 12 }}>
              <span style={{ flex: "0 0 80px", color: J.textSec }}>{k}</span>
              <span style={{ color: J.text }}>{v}</span>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <button onClick={async () => {
            try { await downloadAdminBackup(); }
            catch (e) { alert(`Backup failed: ${e instanceof Error ? e.message : String(e)}`); }
          }} style={{
            padding: "6px 16px", fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: "pointer",
            background: J.amberDim, color: J.amber, border: `1px solid ${J.borderAccent}`,
          }}>↓ Download backup</button>
          <label style={{
            padding: "6px 16px", fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: "pointer",
            background: J.bg3, color: J.textSec, border: `1px solid ${J.border}`, display: "inline-flex", alignItems: "center",
          }}>
            ↑ Restore from file
            <input type="file" accept="application/json" style={{ display: "none" }} onChange={async e => {
              const file = e.target.files?.[0];
              if (!file) return;
              const text = await file.text();
              let payload: Record<string, unknown>;
              try { payload = JSON.parse(text); } catch { alert("Invalid JSON file."); return; }
              if (!confirm(`Restore backup from "${file.name}"? This will overwrite users, groups, permissions and settings.`)) return;
              try {
                const r = await restoreAdminBackup(payload);
                alert(`Restore complete: ${JSON.stringify(r.restored)}`);
                void refreshAll();
              } catch (err) {
                alert(`Restore failed: ${err instanceof Error ? err.message : String(err)}`);
              }
              e.target.value = "";
            }} />
          </label>
        </div>
      </div>
    </div>
  );
}
