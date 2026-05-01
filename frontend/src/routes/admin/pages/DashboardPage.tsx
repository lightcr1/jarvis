import React, { useEffect, useState } from "react";
import { AdminAuditEvent, AdminStatusSummary, fetchAdminAuditCounts, fetchAdminAuditEvents, fetchAdminStatusSummary } from "../../../shared/api/admin";

export function DashboardPage() {
  const [summary, setSummary] = useState<AdminStatusSummary | null>(null);
  const [auditCounts, setAuditCounts] = useState<Record<string, number>>({});
  const [recentEvents, setRecentEvents] = useState<AdminAuditEvent[]>([]);

  useEffect(() => {
    Promise.all([
      fetchAdminStatusSummary(),
      fetchAdminAuditCounts(),
      fetchAdminAuditEvents("?limit=6"),
    ]).then(([summaryData, countData, eventData]) => {
      setSummary(summaryData);
      setAuditCounts(countData.counts || {});
      setRecentEvents(eventData.events || []);
    }).catch(() => undefined);
  }, []);

  const counts = summary?.counts || {};
  const haAuditEntries = Object.entries(auditCounts).filter(([event]) => event.startsWith("ha_"));
  const haAuditTotal = haAuditEntries.reduce((sum, [, count]) => sum + count, 0);
  return (
    <div className="page-stack">
      <div className="panel dashboard-hero">
        <div>
          <div className="eyebrow">Operations overview</div>
          <h2>Jarvis control dashboard</h2>
          <p>Monitor operator status, audit activity, and configuration drift at a glance.</p>
        </div>
        <div className="dashboard-hero-status">
          <div className={`status-pill ${counts.admin_lockout_state || "unknown"}`}>{counts.admin_lockout_state || "unknown"}</div>
          <div className="tiny-note">Admin-Lockout-Status</div>
        </div>
      </div>

      <div className="dashboard-grid">
        {[
          ["users", "Users"],
          ["groups", "Groups"],
          ["memberships", "Memberships"],
          ["audit_events", "Audit events"],
          ["ha_audit_total", "HA activity"],
          ["enabled_admins", "Enabled admins"],
          ["group_permission_sets", "Group permission sets"],
        ].map(([key, label]) => (
          <div className="panel metric-card" key={key}>
            <div className="eyebrow">{label}</div>
            <strong>{String(key === "ha_audit_total" ? haAuditTotal : (counts[key] ?? 0))}</strong>
          </div>
        ))}
      </div>

      <div className="dashboard-grid">
        <div className="panel span-2">
          <div className="eyebrow">Integrity summary</div>
          <div className="dashboard-stat-list">
            <div><span>Orphan memberships</span><strong>{counts.orphan_memberships ?? 0}</strong></div>
            <div><span>Orphan group permission sets</span><strong>{counts.orphan_group_permission_sets ?? 0}</strong></div>
            <div><span>Orphan user permission sets</span><strong>{counts.orphan_user_permission_sets ?? 0}</strong></div>
            <div><span>Disabled admins</span><strong>{counts.disabled_admins ?? 0}</strong></div>
          </div>
        </div>
        <div className="panel span-2">
          <div className="eyebrow">Home Assistant activity</div>
          <div className="dashboard-stat-list">
            {haAuditEntries.slice(0, 6).map(([event, count]) => (
              <div key={event}><span>{event}</span><strong>{count}</strong></div>
            ))}
            {haAuditEntries.length === 0 ? <div><span>No HA audit events yet</span><strong>0</strong></div> : null}
          </div>
        </div>
        <div className="panel span-2">
          <div className="eyebrow">Most frequent audit events</div>
          <div className="dashboard-stat-list">
            {Object.entries(auditCounts).slice(0, 6).map(([event, count]) => (
              <div key={event}><span>{event}</span><strong>{count}</strong></div>
            ))}
            {Object.keys(auditCounts).length === 0 ? <div><span>No audit events yet</span><strong>0</strong></div> : null}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="eyebrow">Recent admin activity</div>
        <div className="event-list">
          {recentEvents.map((event, index) => (
            <div className="event-row" key={`${event.ts}-${event.event}-${index}`}>
              <div>
                <div className="event-title">{event.event}</div>
                <div className="tiny-note">{event.actor_role || "unknown role"} · {event.actor_user_id || "system"}</div>
              </div>
              <div className="tiny-note">{event.ts}</div>
            </div>
          ))}
          {recentEvents.length === 0 ? <div className="tiny-note">No admin events yet.</div> : null}
        </div>
      </div>

      <div className="panel">
        <div className="eyebrow">Orphan details</div>
        <pre>{JSON.stringify(summary?.orphans || {}, null, 2)}</pre>
      </div>
    </div>
  );
}
