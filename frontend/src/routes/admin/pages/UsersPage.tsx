import React, { useEffect, useState } from "react";
import {
  AdminUser,
  createAdminUser,
  deleteAdminUser,
  fetchAdminUsers,
  setAdminUserPassword,
  updateAdminUser,
} from "../../../shared/api/admin";

export function UsersPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [form, setForm] = useState({ username: "", role: "standard_user", enabled: true, password: "" });
  const [status, setStatus] = useState("");

  const load = () => fetchAdminUsers().then((data) => setUsers(data.users || []));
  useEffect(() => { load().catch(() => undefined); }, []);

  const enabledCount = users.filter((user) => user.enabled).length;
  const adminCount = users.filter((user) => user.role === "admin").length;

  return (
    <div className="page-stack">
      <div className="dashboard-grid">
        <div className="panel metric-card">
          <div className="eyebrow">Total users</div>
          <strong>{users.length}</strong>
        </div>
        <div className="panel metric-card">
          <div className="eyebrow">Enabled</div>
          <strong>{enabledCount}</strong>
        </div>
        <div className="panel metric-card">
          <div className="eyebrow">Admins</div>
          <strong>{adminCount}</strong>
        </div>
        <div className="panel metric-card">
          <div className="eyebrow">Disabled</div>
          <strong>{users.length - enabledCount}</strong>
        </div>
      </div>

      <div className="dashboard-grid">
        <div className="panel span-2">
          <div className="eyebrow">Create user</div>
          <div className="page-stack">
            <input className="ui-input" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} placeholder="Username" />
            <div className="form-row">
              <select className="ui-input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                <option value="admin">admin</option>
                <option value="standard_user">standard_user</option>
                <option value="guest_restricted">guest_restricted</option>
                <option value="service_system">service_system</option>
              </select>
              <input className="ui-input" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="Initial password" />
            </div>
            <button className="ui-button primary" onClick={async () => { await createAdminUser(form); setForm({ username: "", role: "standard_user", enabled: true, password: "" }); setStatus("User created."); await load(); }}>Create user</button>
          </div>
        </div>
        <div className="panel span-2">
          <div className="eyebrow">Operator notes</div>
          <div className="dashboard-stat-list">
            <div><span>Shared identity model</span><strong>chat + dashboard</strong></div>
            <div><span>Password management</span><strong>direct reset</strong></div>
            <div><span>Safe toggle flow</span><strong>enable / disable</strong></div>
          </div>
          {status ? <div className="tiny-note">{status}</div> : null}
        </div>
      </div>

      <div className="panel">
        <div className="eyebrow">Users</div>
        <div className="table-card">
          <table className="data-table">
            <thead><tr><th>User</th><th>Role</th><th>Status</th><th>ID</th><th>Actions</th></tr></thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>
                    <div className="table-primary">{user.username}</div>
                    <div className="tiny-note">{user.role === "admin" ? "Dashboard capable" : "Chat workspace user"}</div>
                  </td>
                  <td><span className="tag">{user.role}</span></td>
                  <td><span className={`tag ${user.enabled ? "success" : "danger"}`}>{user.enabled ? "enabled" : "disabled"}</span></td>
                  <td><code className="table-code">{user.id}</code></td>
                  <td>
                    <div className="inline-actions">
                      <button className="ui-button ghost" onClick={async () => { await updateAdminUser(user.id, { enabled: !user.enabled }); await load(); }}>{user.enabled ? "Disable" : "Enable"}</button>
                      <button className="ui-button ghost" onClick={async () => { const password = window.prompt(`New password for ${user.username}`); if (!password) return; await setAdminUserPassword(user.id, password); setStatus(`Password updated for ${user.username}.`); }}>Password</button>
                      <button className="ui-button ghost" onClick={async () => { await deleteAdminUser(user.id); await load(); }}>Delete</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
