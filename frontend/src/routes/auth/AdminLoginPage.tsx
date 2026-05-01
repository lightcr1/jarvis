import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthProvider";

export function AdminLoginPage() {
  const { login, ensureAdminAccess } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function submitLogin() {
    try {
      await login(username, password);
      await ensureAdminAccess();
      navigate("/dashboard");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="center-screen auth-shell">
      <div className="auth-card auth-grid">
        <div className="auth-copy">
          <div className="auth-chip">Restricted Access</div>
          <div className="eyebrow">Jarvis Admin Portal</div>
          <h1>Betritt den getrennten Operator-Bereich.</h1>
          <p>Das Dashboard bleibt vom Chat getrennt, nutzt aber dieselbe Identität. Eine Admin-Session wird nur nach erfolgreicher Rollenprüfung ausgestellt.</p>
          <div className="auth-feature-list">
            <div className="auth-feature"><strong>Separater Bereich</strong><span>Eigene Navigation, Routen und Session-Grenzen für Operationen.</span></div>
            <div className="auth-feature"><strong>Geteilte Identität</strong><span>Es gibt kein zweites Account-Modell für Administration.</span></div>
            <div className="auth-feature"><strong>Rollen-Gate</strong><span>Der Zugriff erfolgt erst nach verifizierter Admin-Rolle.</span></div>
          </div>
        </div>
        <form className="auth-form" onSubmit={(event) => { event.preventDefault(); void submitLogin(); }}>
          <input className="ui-input" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Admin username" />
          <input className="ui-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" />
          <button className="ui-button primary wide" type="submit">Dashboard öffnen</button>
          {error ? <div className="error-text">{error}</div> : null}
        </form>
      </div>
    </div>
  );
}
