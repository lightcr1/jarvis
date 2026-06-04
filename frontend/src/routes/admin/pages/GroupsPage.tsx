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
import { useJ } from "../../../screens/jarvis-shared";

function GroupCard({
  group,
  members,
  allUsers,
  onRemoveMember,
  onAddMember,
  onDelete,
}: {
  group: AdminGroup;
  members: AdminUser[];
  allUsers: AdminUser[];
  onRemoveMember: (userId: string) => Promise<void>;
  onAddMember: (userId: string) => Promise<void>;
  onDelete: () => Promise<void>;
}) {
  const J = useJ();
  const [expanded, setExpanded] = useState(false);
  const [addUserId, setAddUserId] = useState("");
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);

  const memberIds = new Set(members.map(m => m.id));
  const addOptions = allUsers.filter(u => !memberIds.has(u.id));

  const handleAdd = async () => {
    if (!addUserId) return;
    setAdding(true);
    try { await onAddMember(addUserId); setAddUserId(""); }
    finally { setAdding(false); }
  };

  const handleRemove = async (userId: string) => {
    setRemoving(userId);
    try { await onRemoveMember(userId); }
    finally { setRemoving(null); }
  };

  return (
    <div style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6, overflow: "hidden" }}>
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "13px 16px", cursor: "pointer" }}
        onClick={() => setExpanded(v => !v)}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: J.text }}>{group.name}</span>
            <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 3, background: J.bg4, color: J.textSec }}>
              {members.length} member{members.length !== 1 ? "s" : ""}
            </span>
          </div>
          {group.description && (
            <div style={{ fontSize: 11, color: J.textMuted, marginTop: 3 }}>{group.description}</div>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <code style={{ fontSize: 10, fontFamily: "monospace", color: J.textMuted, background: J.bg4, padding: "2px 5px", borderRadius: 3 }}>
            {group.id.slice(0, 8)}…
          </code>
          <span style={{ color: J.textMuted, fontSize: 13, transition: "transform .15s", display: "inline-block", transform: expanded ? "rotate(180deg)" : "none" }}>▾</span>
        </div>
      </div>

      {/* Expanded panel */}
      {expanded && (
        <div style={{ borderTop: `1px solid ${J.border}`, background: J.bg1 }}>
          {/* Member list */}
          {members.length > 0 ? (
            <div style={{ padding: "6px 16px" }}>
              {members.map(user => (
                <div key={user.id} style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "7px 0", borderBottom: `1px solid ${J.border}`,
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{
                      width: 26, height: 26, borderRadius: "50%", flexShrink: 0,
                      background: J.bg4, border: `1px solid ${J.border}`,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 10, fontWeight: 700, color: J.textSec,
                    }}>
                      {user.username.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 500, color: J.text }}>{user.username}</div>
                      <div style={{ fontSize: 10, color: J.textMuted }}>{user.role} · {user.enabled ? "enabled" : "disabled"}</div>
                    </div>
                  </div>
                  <button
                    disabled={removing === user.id}
                    onClick={e => { e.stopPropagation(); void handleRemove(user.id); }}
                    style={{
                      padding: "3px 9px", fontSize: 11, borderRadius: 4, cursor: "pointer",
                      background: J.errorDim, color: J.error, border: `1px solid ${J.error}30`,
                      opacity: removing === user.id ? 0.5 : 1,
                    }}>
                    {removing === user.id ? "…" : "Remove"}
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ padding: "11px 16px", fontSize: 11, color: J.textMuted }}>No members yet. Add one below.</div>
          )}

          {/* Add member */}
          {addOptions.length > 0 && (
            <div style={{
              padding: "9px 16px", borderTop: `1px solid ${J.border}`,
              display: "flex", gap: 8, alignItems: "center",
            }}>
              <select
                value={addUserId}
                onChange={e => setAddUserId(e.target.value)}
                onClick={e => e.stopPropagation()}
                style={{
                  flex: 1, padding: "5px 8px", fontSize: 12, borderRadius: 4,
                  background: J.bg3, border: `1px solid ${J.border}`, color: J.text, outline: "none",
                }}
              >
                <option value="">Add member…</option>
                {addOptions.map(u => <option key={u.id} value={u.id}>{u.username} ({u.role})</option>)}
              </select>
              <button
                disabled={!addUserId || adding}
                onClick={e => { e.stopPropagation(); void handleAdd(); }}
                style={{
                  padding: "5px 14px", fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: "pointer",
                  background: J.amber, color: J.bg0, border: "none",
                  opacity: !addUserId || adding ? 0.5 : 1, whiteSpace: "nowrap",
                }}>
                {adding ? "Adding…" : "Add"}
              </button>
            </div>
          )}
          {addOptions.length === 0 && allUsers.length > 0 && (
            <div style={{ padding: "9px 16px", borderTop: `1px solid ${J.border}`, fontSize: 11, color: J.textMuted }}>
              All users are already in this group.
            </div>
          )}

          {/* Delete */}
          <div style={{ padding: "9px 16px", borderTop: `1px solid ${J.border}`, display: "flex", justifyContent: "flex-end" }}>
            <button
              onClick={e => { e.stopPropagation(); void onDelete(); }}
              style={{
                padding: "4px 12px", fontSize: 11, borderRadius: 4, cursor: "pointer",
                background: J.errorDim, color: J.error, border: `1px solid ${J.error}30`,
              }}>
              Delete group
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function GroupsPage() {
  const J = useJ();
  const [groups, setGroups] = useState<AdminGroup[]>([]);
  const [memberships, setMemberships] = useState<AdminMembership[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState("");
  const [creating, setCreating] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    const [groupData, membershipData, userData] = await Promise.all([
      fetchAdminGroups(),
      fetchAdminAssignments(),
      fetchAdminUsers(),
    ]);
    setGroups(groupData.groups || []);
    setMemberships(membershipData.memberships || []);
    setUsers(userData.users || []);
  }, []);

  useEffect(() => { load().catch(() => undefined); }, [load]);
  useEffect(() => {
    if (!status) return;
    const id = setTimeout(() => setStatus(""), 4000);
    return () => clearTimeout(id);
  }, [status]);

  const userMap = Object.fromEntries(users.map(u => [u.id, u]));
  const linkedUserIds = new Set(memberships.map(m => m.user_id));
  const unassignedUsers = users.filter(u => !linkedUserIds.has(u.id));

  const getMembersForGroup = (groupId: string) =>
    memberships.filter(m => m.group_id === groupId).map(m => userMap[m.user_id]).filter(Boolean) as AdminUser[];

  const filteredGroups = search
    ? groups.filter(g =>
        g.name.toLowerCase().includes(search.toLowerCase()) ||
        (g.description || "").toLowerCase().includes(search.toLowerCase()))
    : groups;

  const handleCreate = async () => {
    if (!name.trim()) return;
    setCreating(true);
    try {
      await createAdminGroup({ name: name.trim(), description: description.trim() });
      setName(""); setDescription("");
      setStatus("Group created.");
      setShowCreate(false);
      await load();
    } catch (e) {
      setStatus(`Error: ${e instanceof Error ? e.message : "Failed to create group."}`);
    } finally {
      setCreating(false);
    }
  };

  const handleAddMember = (groupId: string, userId: string) =>
    createAdminAssignment({ user_id: userId, group_id: groupId }).then(() => load());

  const handleRemoveMember = (groupId: string, userId: string) =>
    deleteAdminAssignment(userId, groupId).then(() => load());

  const handleDeleteGroup = async (group: AdminGroup) => {
    if (!window.confirm(`Delete group "${group.name}"? This removes all memberships in this group.`)) return;
    try { await deleteAdminGroup(group.id); await load(); }
    catch (e) { setStatus(`Error: ${e instanceof Error ? e.message : "Failed to delete group."}`); }
  };

  const card: React.CSSProperties = {
    background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6,
  };
  const eyebrow: React.CSSProperties = {
    fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em",
  };
  const inp: React.CSSProperties = {
    width: "100%", boxSizing: "border-box", padding: "6px 10px", fontSize: 12,
    borderRadius: 4, background: J.bg3, border: `1px solid ${J.border}`, color: J.text, outline: "none",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>

      {/* ── Metrics ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: 10 }}>
        {[
          { label: "Groups", value: groups.length },
          { label: "Assignments", value: memberships.length },
          { label: "Users in groups", value: linkedUserIds.size },
          { label: "Unassigned", value: unassignedUsers.length, accent: unassignedUsers.length > 0 ? J.warn : undefined },
        ].map(({ label, value, accent }) => (
          <div key={label} style={{ ...card, padding: "12px 16px" }}>
            <div style={{ ...eyebrow, marginBottom: 4 }}>{label}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: (accent as string | undefined) || J.text }}>{value}</div>
          </div>
        ))}
      </div>

      {/* ── Toolbar ── */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        {groups.length > 3 && (
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search groups…"
            style={{ flex: 1, minWidth: 160, ...inp }}
          />
        )}
        <button onClick={() => setShowCreate(v => !v)} style={{
          padding: "6px 14px", fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: "pointer",
          background: showCreate ? J.amberDim : J.amber,
          color: showCreate ? J.amber : J.bg0,
          border: showCreate ? `1px solid ${J.borderAccent}` : "none",
        }}>
          {showCreate ? "Cancel" : "+ New group"}
        </button>
        {status && <span style={{ fontSize: 11, color: status.startsWith("Error") ? J.error : J.success }}>{status}</span>}
      </div>

      {/* ── Create form ── */}
      {showCreate && (
        <div style={{ ...card, padding: "16px 18px" }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: J.text, marginBottom: 12 }}>Create group</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              onKeyDown={e => e.key === "Enter" && void handleCreate()}
              placeholder="Group name"
              autoFocus
              style={inp}
            />
            <input
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="Description (optional)"
              style={inp}
            />
            <button
              onClick={() => void handleCreate()}
              disabled={!name.trim() || creating}
              style={{
                padding: "6px 16px", fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: "pointer",
                background: J.amber, color: J.bg0, border: "none", alignSelf: "flex-start",
                opacity: !name.trim() || creating ? 0.5 : 1,
              }}>
              {creating ? "Creating…" : "Create"}
            </button>
          </div>
        </div>
      )}

      {/* ── Unassigned users ── */}
      {unassignedUsers.length > 0 && (
        <div style={{ ...card, padding: "14px 16px", borderColor: J.borderAccent }}>
          <div style={{ ...eyebrow, marginBottom: 6 }}>Unassigned users</div>
          <div style={{ fontSize: 11, color: J.textMuted, marginBottom: 10 }}>
            These users are not in any group and have no group-based permissions.
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {unassignedUsers.map(u => (
              <span key={u.id} title={u.id} style={{
                fontSize: 11, padding: "3px 8px", borderRadius: 3,
                background: J.warnDim, color: J.warn, border: `1px solid ${J.warn}30`,
              }}>{u.username}</span>
            ))}
          </div>
        </div>
      )}

      {/* ── Groups header ── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ ...eyebrow }}>Groups ({filteredGroups.length})</div>
      </div>

      {/* ── Group cards ── */}
      {filteredGroups.length === 0 ? (
        <div style={{ ...card, padding: "20px 18px", color: J.textMuted, fontSize: 12 }}>
          {groups.length === 0 ? "No groups yet. Create one above." : "No groups match your search."}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {filteredGroups.map(group => (
            <GroupCard
              key={group.id}
              group={group}
              members={getMembersForGroup(group.id)}
              allUsers={users}
              onAddMember={userId => handleAddMember(group.id, userId)}
              onRemoveMember={userId => handleRemoveMember(group.id, userId)}
              onDelete={() => handleDeleteGroup(group)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
