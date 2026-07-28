import React, { useCallback, useEffect, useState } from "react";
import { AdminIntegrationStatusEntry, AdminIntegrationsStatus, fetchAdminIntegrationsStatus } from "../../../shared/api/admin";
import { useJ } from "../../../screens/jarvis-shared";

function fmtTs(ts: number): string {
  if (!ts) return "—";
  const d = new Date(ts > 1e10 ? ts : ts * 1000);
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function IntegrationTable({ title, entries, J }: { title: string; entries: AdminIntegrationStatusEntry[]; J: ReturnType<typeof useJ> }) {
  const card: React.CSSProperties = {
    background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6, overflow: "hidden",
  };

  return (
    <div style={card}>
      <div style={{
        padding: "10px 14px", borderBottom: `1px solid ${J.border}`, background: J.bg1,
        display: "flex", alignItems: "center", gap: 8,
      }}>
        <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", flex: 1 }}>{title}</div>
        <span style={{ fontSize: 10, color: J.textMuted }}>{entries.length} configured</span>
      </div>

      <div style={{
        display: "grid", gridTemplateColumns: "1fr 1.6fr 160px",
        padding: "6px 14px", borderBottom: `1px solid ${J.border}`,
        fontSize: 10, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em",
        background: J.bg1,
      }}>
        <div>User</div><div>Fields</div><div>Updated</div>
      </div>

      {entries.length === 0 && (
        <div style={{ padding: "24px 18px", color: J.textMuted, fontSize: 12, textAlign: "center" }}>
          No users have configured this integration.
        </div>
      )}

      {entries.map((entry, index) => (
        <div key={`${entry.user_id}-${index}`} style={{
          display: "grid", gridTemplateColumns: "1fr 1.6fr 160px",
          padding: "8px 14px", alignItems: "start",
          borderBottom: index < entries.length - 1 ? `1px solid ${J.border}` : "none",
          background: index % 2 === 1 ? J.bg1 : "transparent",
        }}>
          <div style={{ fontSize: 12, color: J.text, fontWeight: 500 }}>
            {entry.username || <code style={{ fontSize: 10, fontFamily: "monospace", color: J.textMuted }}>{entry.user_id.slice(0, 8)}</code>}
          </div>
          <div style={{ fontSize: 11, color: J.textSec, fontFamily: "monospace" }}>
            {entry.field_names.join(", ")}
          </div>
          <div style={{ fontSize: 11, color: J.textMuted, whiteSpace: "nowrap" }}>{fmtTs(entry.updated_at)}</div>
        </div>
      ))}
    </div>
  );
}

export function IntegrationsPage() {
  const J = useJ();
  const [status, setStatus] = useState<AdminIntegrationsStatus>({ calendar: [], email: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    return fetchAdminIntegrationsStatus()
      .then(data => {
        setStatus(data);
        setError("");
        setLastRefresh(new Date());
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const card: React.CSSProperties = {
    background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6,
  };
  const btn: React.CSSProperties = {
    padding: "5px 14px", fontSize: 11, borderRadius: 4, cursor: "pointer",
    background: J.amber, color: J.bg0, border: `1px solid ${J.amber}`, fontWeight: 600,
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: 10 }}>
        {[
          { label: "Calendar users", value: status.calendar.length },
          { label: "Email users", value: status.email.length },
        ].map(({ label, value }) => (
          <div key={label} style={{ ...card, padding: "12px 16px" }}>
            <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>{label}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: J.text }}>{value}</div>
          </div>
        ))}
      </div>

      <div style={{ ...card, padding: "14px 18px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", flex: 1 }}>
            Per-user integration credentials
          </div>
          <button onClick={() => void load()} style={btn} disabled={loading}>
            {loading ? "Loading…" : "↺ Refresh"}
          </button>
        </div>
        {error && <div style={{ fontSize: 11, color: J.error, marginTop: 8 }}>{error}</div>}
        {lastRefresh && (
          <div style={{ fontSize: 10, color: J.textMuted, marginTop: 8 }}>
            Updated: {lastRefresh.toLocaleTimeString()}
          </div>
        )}
      </div>

      <IntegrationTable title="Calendar" entries={status.calendar} J={J} />
      <IntegrationTable title="Email" entries={status.email} J={J} />
    </div>
  );
}
