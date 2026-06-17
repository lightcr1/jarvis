import React, { useCallback, useEffect, useRef, useState } from "react";
import { AdminAuditEvent, fetchAdminAuditCounts, fetchAdminAuditEvents } from "../../../shared/api/admin";
import { useJ } from "../../../screens/jarvis-shared";

function fmtTs(ts: number): string {
  if (!ts) return "—";
  const d = new Date(ts > 1e10 ? ts : ts * 1000);
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function PayloadCell({ payload, J }: { payload: Record<string, unknown> | undefined; J: ReturnType<typeof useJ> }) {
  const [open, setOpen] = useState(false);
  const str = JSON.stringify(payload || {});
  if (str === "{}") return <span style={{ color: J.textMuted, fontSize: 11 }}>—</span>;
  return (
    <button onClick={() => setOpen(v => !v)} style={{
      background: "none", border: "none", cursor: "pointer", padding: 0,
      textAlign: "left", display: "block", maxWidth: 280,
    }}>
      <code style={{
        fontSize: 10, fontFamily: "monospace", display: "block",
        color: J.textSec, background: J.bg4, padding: "2px 5px", borderRadius: 3,
        overflow: "hidden", textOverflow: open ? "unset" : "ellipsis",
        whiteSpace: open ? "pre-wrap" : "nowrap", wordBreak: "break-all",
      }}>{open ? JSON.stringify(payload, null, 2) : str}</code>
    </button>
  );
}

export function LogsPage() {
  const J = useJ();
  const [events, setEvents] = useState<AdminAuditEvent[]>([]);
  const [filterEvent, setFilterEvent] = useState("");
  const [filterRole, setFilterRole] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [limit, setLimit] = useState(40);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(() => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (filterEvent.trim()) params.set("event", filterEvent.trim());
    if (filterRole.trim()) params.set("role", filterRole.trim());
    if (since) params.set("since_ts", String(Math.floor(new Date(since).getTime() / 1000)));
    if (until) params.set("until_ts", String(Math.floor(new Date(until).getTime() / 1000)));
    return Promise.all([
      fetchAdminAuditEvents(`?${params.toString()}`),
      fetchAdminAuditCounts(`?${params.toString()}`),
    ])
      .then(([eventData, countData]) => {
        setEvents(eventData.events || []);
        setCounts(countData.counts || {});
        setLastRefresh(new Date());
      })
      .catch(() => undefined);
  }, [filterEvent, filterRole, since, until, limit]);

  useEffect(() => { setLimit(40); }, [filterEvent, filterRole, since, until]);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (autoRefresh) intervalRef.current = setInterval(() => { void load(); }, 10000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [autoRefresh, load]);

  const topCounts = Object.entries(counts).sort((a, b) => b[1] - a[1]);

  const exportCsv = () => {
    const header = ["timestamp", "event", "role", "actor_user_id", "payload"];
    const rows = events.map(e => [
      e.ts ? new Date(e.ts > 1e10 ? e.ts : e.ts * 1000).toISOString() : "",
      e.event || "",
      e.actor_role || e.role || "",
      e.actor_user_id || "",
      JSON.stringify(e.payload || {}),
    ].map(v => `"${String(v).replace(/"/g, '""')}"`).join(","));
    const csv = [header.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const dateStr = new Date().toISOString().slice(0, 10);
    a.href = url; a.download = `jarvis-audit-${dateStr}.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  const card: React.CSSProperties = {
    background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6,
  };
  const btn = (active?: boolean): React.CSSProperties => ({
    padding: "5px 12px", fontSize: 11, borderRadius: 4, cursor: "pointer",
    background: active ? J.amber : "transparent",
    color: active ? J.bg0 : J.textSec,
    border: `1px solid ${active ? J.amber : J.border}`,
    fontWeight: active ? 600 : 400, transition: "all .1s",
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>

      {/* ── Metrics ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: 10 }}>
        {[
          { label: "Loaded", value: events.length },
          { label: "Event types", value: Object.keys(counts).length },
          { label: "Auto-refresh", value: autoRefresh ? "10s" : "off", accent: autoRefresh ? J.success : undefined },
        ].map(({ label, value, accent }) => (
          <div key={label} style={{ ...card, padding: "12px 16px" }}>
            <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>{label}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: (accent as string) || J.text }}>{value}</div>
          </div>
        ))}
        {topCounts.slice(0, 1).map(([ev, cnt]) => (
          <div key={ev} style={{ ...card, padding: "12px 16px" }}>
            <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>Top event</div>
            <div style={{ fontSize: 11, fontWeight: 600, color: J.text, fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{ev}</div>
            <div style={{ fontSize: 11, color: J.textMuted }}>{cnt}×</div>
          </div>
        ))}
      </div>

      {/* ── Filters ── */}
      <div style={{ ...card, padding: "14px 18px" }}>
        <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10 }}>Filters & controls</div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 10 }}>
          <input
            value={filterEvent}
            onChange={e => setFilterEvent(e.target.value)}
            onKeyDown={e => e.key === "Enter" && void load()}
            placeholder="Event type…"
            style={{
              flex: "1 1 160px", padding: "5px 10px", fontSize: 12, borderRadius: 4,
              background: J.bg3, border: `1px solid ${J.border}`, color: J.text, outline: "none",
            }}
          />
          <select
            value={filterRole}
            onChange={e => setFilterRole(e.target.value)}
            style={{ padding: "5px 10px", fontSize: 12, borderRadius: 4, background: J.bg3, border: `1px solid ${J.border}`, color: J.text, outline: "none" }}
          >
            <option value="">All roles</option>
            <option value="admin">admin</option>
            <option value="standard_user">standard_user</option>
            <option value="guest_restricted">guest_restricted</option>
            <option value="service_system">service_system</option>
          </select>
          <button onClick={() => void load()} style={{ ...btn(true), padding: "5px 14px" }}>Apply</button>
          <button onClick={() => void load()} style={{ ...btn(), padding: "5px 12px" }}>↺ Refresh</button>
          <button onClick={() => setFilterEvent("ha_entity_action_requested")} style={btn()}>HA actions</button>
          <button onClick={() => setFilterEvent("ha_automation_created")} style={btn()}>HA automations</button>
          {events.length > 0 && (
            <button onClick={exportCsv} style={btn()}>↓ CSV</button>
          )}
          <button
            onClick={() => setAutoRefresh(v => !v)}
            style={{ ...btn(autoRefresh), marginLeft: "auto" }}
          >{autoRefresh ? "⏵ Live" : "⏸ Paused"}</button>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ fontSize: 11, color: J.textMuted }}>From</span>
          <input
            type="datetime-local"
            value={since}
            onChange={e => setSince(e.target.value)}
            style={{ padding: "4px 8px", fontSize: 11, borderRadius: 4, background: J.bg3, border: `1px solid ${J.border}`, color: J.text, outline: "none" }}
          />
          <span style={{ fontSize: 11, color: J.textMuted }}>To</span>
          <input
            type="datetime-local"
            value={until}
            onChange={e => setUntil(e.target.value)}
            style={{ padding: "4px 8px", fontSize: 11, borderRadius: 4, background: J.bg3, border: `1px solid ${J.border}`, color: J.text, outline: "none" }}
          />
          {(since || until) && (
            <button onClick={() => { setSince(""); setUntil(""); }} style={btn()}>Clear range</button>
          )}
        </div>

        {lastRefresh && (
          <div style={{ fontSize: 10, color: J.textMuted, marginTop: 8 }}>
            Updated: {lastRefresh.toLocaleTimeString()}{autoRefresh ? " · auto-refreshing every 10s" : ""}
          </div>
        )}
      </div>

      {/* ── Event breakdown ── */}
      {topCounts.length > 0 && (
        <div style={{ ...card, padding: "14px 18px" }}>
          <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10 }}>Event breakdown</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 0, borderRadius: 4, overflow: "hidden", border: `1px solid ${J.border}` }}>
            {topCounts.map(([ev, cnt], i) => {
              const max = topCounts[0][1];
              return (
                <div key={ev} style={{
                  display: "flex", alignItems: "center", gap: 12, padding: "7px 12px",
                  borderBottom: i < topCounts.length - 1 ? `1px solid ${J.border}` : "none",
                  background: i % 2 === 1 ? J.bg1 : "transparent",
                  position: "relative", overflow: "hidden",
                }}>
                  <div style={{
                    position: "absolute", left: 0, top: 0, bottom: 0,
                    width: `${(cnt / max) * 100}%`,
                    background: J.amberGlow, pointerEvents: "none",
                  }} />
                  <code style={{ fontSize: 11, fontFamily: "monospace", color: J.text, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", position: "relative" }}>{ev}</code>
                  <span style={{ fontSize: 12, fontWeight: 700, color: J.amber, flexShrink: 0, position: "relative" }}>{cnt}</span>
                  <button onClick={() => { setFilterEvent(ev); void load(); }} style={{ ...btn(), fontSize: 10, padding: "2px 8px", flexShrink: 0, position: "relative" }}>Filter</button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Audit log ── */}
      <div style={{ ...card, overflow: "hidden" }}>
        <div style={{
          padding: "10px 14px", borderBottom: `1px solid ${J.border}`, background: J.bg1,
          display: "flex", alignItems: "center", gap: 8,
        }}>
          <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", flex: 1 }}>Audit log</div>
          <span style={{ fontSize: 10, color: J.textMuted }}>click payload to expand</span>
        </div>

        {/* Column headers */}
        <div style={{
          display: "grid", gridTemplateColumns: "120px 1fr 110px 90px 1fr",
          padding: "6px 14px", borderBottom: `1px solid ${J.border}`,
          fontSize: 10, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em",
          background: J.bg1,
        }}>
          <div>Time</div><div>Event</div><div>Role</div><div>Actor</div><div>Payload</div>
        </div>

        {events.length === 0 && (
          <div style={{ padding: "24px 18px", color: J.textMuted, fontSize: 12, textAlign: "center" }}>
            No events match the current filter.
          </div>
        )}

        {events.map((entry, index) => (
          <div key={`${entry.ts}-${entry.event}-${index}`} style={{
            display: "grid", gridTemplateColumns: "120px 1fr 110px 90px 1fr",
            padding: "8px 14px", alignItems: "start",
            borderBottom: index < events.length - 1 ? `1px solid ${J.border}` : "none",
            background: index % 2 === 1 ? J.bg1 : "transparent",
          }}>
            <div style={{ fontSize: 11, color: J.textMuted, whiteSpace: "nowrap" }}>{fmtTs(entry.ts)}</div>
            <div style={{ fontSize: 12, color: J.text, fontWeight: 500 }}>{entry.event}</div>
            <div>
              <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 3, background: J.bg4, color: J.textSec }}>
                {entry.actor_role || entry.role || "unknown"}
              </span>
            </div>
            <div>
              <code style={{ fontSize: 10, fontFamily: "monospace", color: J.textMuted }}>
                {entry.actor_user_id ? entry.actor_user_id.slice(0, 8) : "system"}
              </code>
            </div>
            <div><PayloadCell payload={entry.payload} J={J} /></div>
          </div>
        ))}
        {events.length >= limit && (
          <div style={{ padding: "10px 14px", borderTop: `1px solid ${J.border}`, display: "flex", justifyContent: "center" }}>
            <button onClick={() => setLimit(l => l + 40)} style={btn()}>
              Load more (showing {limit})
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
