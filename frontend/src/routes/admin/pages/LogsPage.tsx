import React, { useCallback, useEffect, useState } from "react";
import { AdminAuditEvent, fetchAdminAuditCounts, fetchAdminAuditEvents } from "../../../shared/api/admin";

export function LogsPage() {
  const [events, setEvents] = useState<AdminAuditEvent[]>([]);
  const [filterEvent, setFilterEvent] = useState("");
  const [filterRole, setFilterRole] = useState("");
  const [counts, setCounts] = useState<Record<string, number>>({});

  const load = useCallback(() => {
    const params = new URLSearchParams({ limit: "40" });
    if (filterEvent.trim()) params.set("event", filterEvent.trim());
    if (filterRole.trim()) params.set("role", filterRole.trim());
    return Promise.all([
      fetchAdminAuditEvents(`?${params.toString()}`),
      fetchAdminAuditCounts(`?${params.toString()}`),
    ])
      .then(([eventData, countData]) => {
        setEvents(eventData.events || []);
        setCounts(countData.counts || {});
      })
      .catch(() => undefined);
  }, [filterEvent, filterRole]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="page-stack">
      <div className="dashboard-grid">
        <div className="panel metric-card">
          <div className="eyebrow">Loaded events</div>
          <strong>{events.length}</strong>
        </div>
        <div className="panel metric-card">
          <div className="eyebrow">Unique event types</div>
          <strong>{Object.keys(counts).length}</strong>
        </div>
        <div className="panel span-2">
          <div className="eyebrow">Top activity</div>
          <div className="dashboard-stat-list">
            {Object.entries(counts).slice(0, 3).map(([event, count]) => (
              <div key={event}><span>{event}</span><strong>{count}</strong></div>
            ))}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="eyebrow">Audit filters</div>
        <div className="form-row">
          <input className="ui-input" value={filterEvent} onChange={(e) => setFilterEvent(e.target.value)} placeholder="Event filter" />
          <select className="ui-input" value={filterRole} onChange={(e) => setFilterRole(e.target.value)}>
            <option value="">all roles</option>
            <option value="admin">admin</option>
            <option value="standard_user">standard_user</option>
            <option value="guest_restricted">guest_restricted</option>
            <option value="service_system">service_system</option>
          </select>
          <button className="ui-button primary" onClick={() => load()}>Apply</button>
          <button className="ui-button secondary" onClick={() => setFilterEvent("ha_entity_action_requested")}>HA action requests</button>
          <button className="ui-button secondary" onClick={() => setFilterEvent("ha_automation_created")}>HA automations</button>
        </div>
        <p className="tiny-note">HA audit events use the `ha_` prefix. Use focused filters here to inspect discovery, actions, confirmations, syncs and recovery flows.</p>
      </div>

      <div className="panel">
        <div className="eyebrow">Audit logs</div>
        <div className="table-card">
          <table className="data-table">
            <thead><tr><th>TS</th><th>Event</th><th>Role</th><th>Actor</th><th>Payload</th></tr></thead>
            <tbody>
              {events.map((entry, index) => <tr key={`${entry.ts}-${entry.event}-${index}`}><td>{entry.ts}</td><td><div className="table-primary">{entry.event}</div></td><td><span className="tag">{entry.actor_role || entry.role || "unknown"}</span></td><td><code className="table-code">{entry.actor_user_id || "system"}</code></td><td><code className="table-code">{JSON.stringify(entry.payload || entry)}</code></td></tr>)}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
