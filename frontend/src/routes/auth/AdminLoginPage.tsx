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
          <div className="eyebrow">Jarvis Admin Portal</div>
          <h1>Enter the separated dashboard</h1>
          <p>The dashboard stays isolated from chat, but uses the same account identity. Only users with the `admin` role receive an admin session.</p>
          <div className="auth-feature-list">
            <div className="auth-feature"><strong>Separate area</strong><span>Dedicated admin routes, shell and navigation.</span></div>
            <div className="auth-feature"><strong>Shared identity</strong><span>No second account model is required.</span></div>
            <div className="auth-feature"><strong>Role gate</strong><span>Session issuance happens only after admin role validation.</span></div>
          </div>
        </div>
        <form className="auth-form" onSubmit={(event) => { event.preventDefault(); void submitLogin(); }}>
          <input className="ui-input" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Admin username" />
          <input className="ui-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" />
          <button className="ui-button primary wide" type="submit">Enter dashboard</button>
          {error ? <div className="error-text">{error}</div> : null}
        </form>
      </div>
    </div>
  );
}
