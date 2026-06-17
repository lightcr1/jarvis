import React, { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthProvider";
import { getStoredPreferences } from "../api/client";
import { J, useJ, IconMoon, IconSun, applyTheme } from "../../screens/jarvis-shared";

const NAV_LINKS = [
  { to: "/chat",                label: "← Back to Chat", end: false },
  { to: "/dashboard",           label: "Overview",       end: true  },
  { to: "/dashboard/users",     label: "Users",          end: false },
  { to: "/dashboard/groups",    label: "Groups",         end: false },
  { to: "/dashboard/permissions", label: "Permissions",  end: false },
  { to: "/dashboard/status",    label: "Status",         end: false },
  { to: "/dashboard/logs",      label: "Logs",           end: false },
  { to: "/dashboard/settings",  label: "Settings",       end: false },
  { to: "/dashboard/provider",  label: "AI Provider",    end: false },
  { to: "/dashboard/usage",     label: "Usage",          end: false },
  { to: "/dashboard/docs",      label: "Docs",           end: false },
];

export function AdminShell() {
  useJ();
  const { isAdmin, loading, ensureAdminAccess, user, logout, preferences, savePreferences } = useAuth();
  const navigate = useNavigate();
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState("");
  const isDark = (preferences.theme ?? "dark") === "dark";

  useEffect(() => {
    const storedTheme = getStoredPreferences().theme;
    if (storedTheme) applyTheme(storedTheme as "dark" | "light");
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!isAdmin) { navigate("/dashboard/login", { replace: true }); return; }
    ensureAdminAccess()
      .then(() => setBooting(false))
      .catch((err: Error) => { setError(err.message); navigate("/dashboard/login", { replace: true }); });
  }, [ensureAdminAccess, isAdmin, loading, navigate]);

  if (loading || booting) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", background: J.bg0, color: J.textSec, fontSize: 13 }}>
        Loading dashboard…
      </div>
    );
  }

  const userInitial = (user?.username?.[0] ?? "A").toUpperCase();

  return (
    <div style={{ display: "flex", height: "100vh", background: J.bg0, color: J.text, overflow: "hidden" }}>

      {/* ── Sidebar ── */}
      <aside style={{
        width: 200, flexShrink: 0, background: J.bg1, borderRight: `1px solid ${J.border}`,
        display: "flex", flexDirection: "column", overflow: "hidden",
      }}>
        {/* Brand */}
        <Link to="/dashboard" style={{ textDecoration: "none", display: "flex", alignItems: "center", gap: 10, padding: "16px 16px 12px", borderBottom: `1px solid ${J.border}` }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8, background: J.amberDim,
            border: `1px solid ${J.borderAccent}`, display: "flex", alignItems: "center",
            justifyContent: "center", fontSize: 14, fontWeight: 700, color: J.amber, flexShrink: 0,
          }}>J</div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: J.text }}>Jarvis Admin</div>
            <div style={{ fontSize: 10, color: J.textMuted }}>Operator Dashboard</div>
          </div>
        </Link>

        {/* Nav links */}
        <nav style={{ flex: 1, padding: "8px 8px", display: "flex", flexDirection: "column", gap: 2, overflowY: "auto" }}>
          {NAV_LINKS.map(({ to, label, end }) => (
            <NavLink key={to} to={to} end={end} style={({ isActive }) => ({
              display: "block", padding: "7px 10px", borderRadius: 6, fontSize: 13,
              textDecoration: "none", transition: "all .1s",
              background: isActive ? J.amberGlow : "transparent",
              color: isActive ? J.amber : J.textSec,
              borderLeft: `2px solid ${isActive ? J.amber : "transparent"}`,
              fontWeight: isActive ? 600 : 400,
            })}>
              {label}
            </NavLink>
          ))}
        </nav>

        {/* User / sign out */}
        <div style={{ padding: "12px 12px", borderTop: `1px solid ${J.border}` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <div style={{
              width: 26, height: 26, borderRadius: "50%", background: J.bg4, border: `1px solid ${J.border}`,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 11, fontWeight: 700, color: J.textSec, flexShrink: 0,
            }}>{userInitial}</div>
            <div style={{ minWidth: 0, overflow: "hidden" }}>
              <div style={{ fontSize: 12, color: J.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{user?.username ?? "Admin"}</div>
              <div style={{ fontSize: 10, color: J.textMuted }}>admin</div>
            </div>
          </div>
          <button
            onClick={() => logout().then(() => navigate("/chat"))}
            style={{
              width: "100%", padding: "6px 10px", fontSize: 12, borderRadius: 5, cursor: "pointer",
              background: J.errorDim, color: J.error, border: `1px solid ${J.error}30`,
            }}
          >Sign out</button>
          {error && <div style={{ fontSize: 11, color: J.error, marginTop: 6 }}>{error}</div>}
        </div>
      </aside>

      {/* ── Main area ── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {/* Topbar */}
        <header style={{
          height: 52, flexShrink: 0, background: J.bg1, borderBottom: `1px solid ${J.border}`,
          display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 20px",
        }}>
          <div>
            <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>Admin Portal</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: J.text }}>Admin Control Panel</div>
          </div>
          <button
            onClick={() => {
              const next = isDark ? "light" : "dark";
              applyTheme(next);
              void savePreferences({ ...preferences, theme: next });
            }}
            title={isDark ? "Switch to light mode" : "Switch to dark mode"}
            style={{
              width: 32, height: 32, borderRadius: 7, background: "transparent",
              border: `1px solid ${J.border}`, color: J.textMuted, cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center",
              transition: "all .15s",
            }}
            onMouseEnter={e => { const el = e.currentTarget; el.style.color = J.amber; el.style.borderColor = J.borderAccent; }}
            onMouseLeave={e => { const el = e.currentTarget; el.style.color = J.textMuted; el.style.borderColor = J.border; }}
          >
            {isDark ? <IconSun size={14} /> : <IconMoon size={14} />}
          </button>
        </header>

        {/* Page content */}
        <main style={{ flex: 1, overflowY: "auto", padding: "22px 24px" }}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
