import React, { useCallback, useEffect, useState } from "react";
import {
  AdminGroup,
  AdminMembership,
  AdminUser,
  createAdminAssignment,
  createAdminGroup,
  deleteAdminAssignment,
  deleteAdminGroup,
  fetchAdminAssignments,
  fetchAdminGroups,
  fetchAdminUsers,
} from "../../../shared/api/admin";

export function GroupsPage() {
  const [groups, setGroups] = useState<AdminGroup[]>([]);
  const [memberships, setMemberships] = useState<AdminMembership[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [userId, setUserId] = useState("");
  const [groupId, setGroupId] = useState("");

  const load = useCallback(async () => {
    const [groupData, membershipData, userData] = await Promise.all([
      fetchAdminGroups(),
      fetchAdminAssignments(),
      fetchAdminUsers(),
    ]);
    setGroups(groupData.groups || []);
    setMemberships(membershipData.memberships || []);
    setUsers(userData.users || []);
    if (!userId && userData.users?.length) setUserId(userData.users[0].id);
    if (!groupId && groupData.groups?.length) setGroupId(groupData.groups[0].id);
  }, [groupId, userId]);
  useEffect(() => { load().catch(() => undefined); }, [load]);

  const linkedUsers = new Set(memberships.map((membership) => membership.user_id));

  return (
    <div className="page-stack">
      <div className="dashboard-grid">
        <div className="panel metric-card">
          <div className="eyebrow">Groups</div>
          <strong>{groups.length}</strong>
        </div>
        <div className="panel metric-card">
          <div className="eyebrow">Assignments</div>
          <strong>{memberships.length}</strong>
        </div>
        <div className="panel metric-card">
          <div className="eyebrow">Users in groups</div>
          <strong>{linkedUsers.size}</strong>
        </div>
        <div className="panel metric-card">
          <div className="eyebrow">Unassigned users</div>
          <strong>{Math.max(users.length - linkedUsers.size, 0)}</strong>
        </div>
      </div>

      <div className="dashboard-grid">
        <div className="panel span-2">
          <div className="eyebrow">Create group</div>
          <div className="page-stack">
            <input className="ui-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Group name" />
            <input className="ui-input" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description" />
            <button className="ui-button primary" onClick={async () => { await createAdminGroup({ name, description }); setName(""); setDescription(""); await load(); }}>Create group</button>
          </div>
        </div>
        <div className="panel span-2">
          <div className="eyebrow">Membership flow</div>
          <div className="dashboard-stat-list">
            <div><span>Assignment model</span><strong>user to group</strong></div>
            <div><span>Best for roles</span><strong>shared permissions</strong></div>
            <div><span>Change strategy</span><strong>group-first governance</strong></div>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="eyebrow">Groups</div>
        <div className="table-card">
          <table className="data-table">
            <thead><tr><th>Group</th><th>Description</th><th>ID</th><th>Actions</th></tr></thead>
            <tbody>
              {groups.map((group) => <tr key={group.id}><td><div className="table-primary">{group.name}</div></td><td>{group.description || "No description"}</td><td><code className="table-code">{group.id}</code></td><td><button className="ui-button ghost" onClick={async () => { await deleteAdminGroup(group.id); await load(); }}>Delete</button></td></tr>)}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <div className="eyebrow">Assignments</div>
        <div className="form-row">
          <select className="ui-input" value={userId} onChange={(e) => setUserId(e.target.value)}>
            {users.map((user) => <option key={user.id} value={user.id}>{user.username}</option>)}
          </select>
          <select className="ui-input" value={groupId} onChange={(e) => setGroupId(e.target.value)}>
            {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
          </select>
          <button className="ui-button primary" onClick={async () => { await createAdminAssignment({ user_id: userId, group_id: groupId }); await load(); }}>Assign</button>
        </div>
        <div className="table-card">
          <table className="data-table">
            <thead><tr><th>User</th><th>Group</th><th>Actions</th></tr></thead>
            <tbody>
              {memberships.map((membership, index) => <tr key={`${membership.user_id}-${membership.group_id}-${index}`}><td><code className="table-code">{membership.user_id}</code></td><td><code className="table-code">{membership.group_id}</code></td><td><button className="ui-button ghost" onClick={async () => { await deleteAdminAssignment(membership.user_id, membership.group_id); await load(); }}>Remove</button></td></tr>)}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
