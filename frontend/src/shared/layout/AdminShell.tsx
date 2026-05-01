import React, { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthProvider";

export function AdminShell() {
  const { isAdmin, loading, ensureAdminAccess, user, logout, preferences, savePreferences } = useAuth();
  const navigate = useNavigate();
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (loading) return;
    if (!isAdmin) {
      navigate("/dashboard/login", { replace: true });
      return;
    }
    ensureAdminAccess()
      .then(() => setBooting(false))
      .catch((err) => {
        setError(err.message);
        navigate("/dashboard/login", { replace: true });
      });
  }, [ensureAdminAccess, isAdmin, loading, navigate]);

  if (loading || booting) {
    return <div className="center-screen"><div className="panel">Loading dashboard…</div></div>;
  }

  const currentTheme = preferences.theme === "light" ? "light" : "dark";

  return (
    <div className="admin-frame">
      <aside className="admin-sidebar">
        <Link className="brand" to="/dashboard">
          <span className="brand-mark">A</span>
          <div>
            <div className="brand-title">Jarvis Admin</div>
            <div className="brand-sub">Operator Dashboard</div>
          </div>
        </Link>
        <nav className="nav-stack">
          <NavLink to="/chat" className="nav-link">Back to Chat</NavLink>
          <NavLink to="/dashboard" end className="nav-link">Overview</NavLink>
          <NavLink to="/dashboard/users" className="nav-link">Users</NavLink>
          <NavLink to="/dashboard/groups" className="nav-link">Groups</NavLink>
          <NavLink to="/dashboard/permissions" className="nav-link">Permissions</NavLink>
          <NavLink to="/dashboard/status" className="nav-link">Status</NavLink>
          <NavLink to="/dashboard/logs" className="nav-link">Logs</NavLink>
          <NavLink to="/dashboard/settings" className="nav-link">Settings</NavLink>
        </nav>
        <div className="sidebar-user">
          <div className="status-chip">{user ? `${user.username} · admin` : "Admin"}</div>
          <button className="ui-button ghost" onClick={() => logout().then(() => navigate("/chat"))}>Sign out</button>
          {error ? <div className="tiny-note">{error}</div> : null}
        </div>
      </aside>
      <div className="app-main">
        <header className="topbar">
          <div className="topbar-copy">
            <div className="eyebrow">Admin Portal</div>
            <h1>Admin Control Panel</h1>
          </div>
          <div className="topbar-actions">
            <button
              className="ui-button ghost theme-toggle"
              onClick={() => { void savePreferences({ ...preferences, theme: currentTheme === "dark" ? "light" : "dark" }); }}
              aria-label={`Switch to ${currentTheme === "dark" ? "light" : "dark"} theme`}
            >
              <span className={`theme-icon ${currentTheme}`} aria-hidden="true">
                <span className="theme-icon-core" />
              </span>
              <span>{currentTheme === "dark" ? "Dark" : "Light"}</span>
            </button>
          </div>
        </header>
        <main className="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
