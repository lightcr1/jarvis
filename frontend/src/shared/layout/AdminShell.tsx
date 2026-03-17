import React, { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthProvider";

export function AdminShell() {
  const { isAdmin, loading, ensureAdminAccess, user, logout } = useAuth();
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
          <NavLink to="/chat" className="nav-link">Back to chat</NavLink>
          <NavLink to="/dashboard" end className="nav-link">Overview</NavLink>
          <NavLink to="/dashboard/users" className="nav-link">Users</NavLink>
          <NavLink to="/dashboard/groups" className="nav-link">Groups</NavLink>
          <NavLink to="/dashboard/permissions" className="nav-link">Permissions</NavLink>
          <NavLink to="/dashboard/status" className="nav-link">System status</NavLink>
          <NavLink to="/dashboard/logs" className="nav-link">Logs</NavLink>
          <NavLink to="/dashboard/settings" className="nav-link">Settings</NavLink>
        </nav>
        <div className="sidebar-user">
          <div className="status-chip">{user ? `${user.username} · admin` : "Admin"}</div>
          <button className="ui-button ghost" onClick={() => logout().then(() => navigate("/chat"))}>Logout</button>
          {error ? <div className="tiny-note">{error}</div> : null}
        </div>
      </aside>
      <div className="app-main">
        <header className="topbar">
          <div className="topbar-copy">
            <div className="eyebrow">Admin Portal</div>
            <h1>Separated dashboard area</h1>
          </div>
        </header>
        <main className="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
