import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthProvider";

export function AppShell({
  sidebar,
  children,
  actions,
  onProfileClick,
  onHelpClick,
}: {
  sidebar: React.ReactNode;
  children: React.ReactNode;
  actions?: React.ReactNode;
  onProfileClick?: () => void;
  onHelpClick?: () => void;
}) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div className={`app-frame${sidebarOpen ? "" : " sidebar-hidden"}`}>
      <aside className={`app-sidebar${sidebarOpen ? "" : " hidden"}`}>
        <div className="sidebar-header">
          <Link className="brand brand-card" to="/chat">
            <span className="brand-mark">J</span>
            <div>
              <div className="brand-title">Jarvis</div>
              <div className="brand-sub">Neural Interface</div>
            </div>
          </Link>
          <button className="sidebar-toggle sidebar-toggle-inline" onClick={() => setSidebarOpen(false)} aria-label="Collapse sidebar">☰</button>
        </div>
        <div className="sidebar-block">{sidebar}</div>
        <div className="sidebar-user">
          <button className="profile-button" onClick={() => setMenuOpen((value) => !value)}>
            <div className="profile-avatar">{user ? user.username.slice(0, 1).toUpperCase() : "G"}</div>
            <div>
              <div className="profile-title">{user ? user.username : "Guest mode"}</div>
              <div className="tiny-note">{user ? user.role : "Preferences are not persisted"}</div>
            </div>
          </button>
          {menuOpen ? (
            <div className="profile-menu">
              {user ? (
                <>
                  {onProfileClick ? <button className="profile-menu-item" onClick={() => { setMenuOpen(false); onProfileClick(); }}>Settings</button> : null}
                  {onHelpClick ? <button className="profile-menu-item" onClick={() => { setMenuOpen(false); onHelpClick(); }}>Help</button> : null}
                  <button className="profile-menu-item danger" onClick={() => { setMenuOpen(false); void logout(); }}>Logout</button>
                </>
              ) : (
                <>
                  <button className="profile-menu-item" onClick={() => { setMenuOpen(false); navigate("/login"); }}>Login</button>
                  {onHelpClick ? <button className="profile-menu-item" onClick={() => { setMenuOpen(false); onHelpClick(); }}>Help</button> : null}
                </>
              )}
            </div>
          ) : null}
        </div>
      </aside>
      {!sidebarOpen ? (
        <button className="sidebar-rail-toggle" onClick={() => setSidebarOpen(true)} aria-label="Expand sidebar">☰</button>
      ) : null}
      <div className="app-main">
        <header className="topbar">
          <div className="topbar-copy">
            <div className="topbar-brand-dot" />
          </div>
          <div className="topbar-actions topbar-cluster">{actions}</div>
        </header>
        <main className="main-content">{children}</main>
      </div>
    </div>
  );
}
