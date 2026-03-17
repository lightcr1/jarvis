import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthProvider";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function submitLogin() {
    try {
      await login(username, password);
      navigate("/chat");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="center-screen auth-shell">
      <div className="auth-card auth-grid">
        <div className="auth-copy">
          <div className="eyebrow">Jarvis Login</div>
          <h1>Sign in to personalize Jarvis</h1>
          <p>Chat works as guest. Login unlocks saved preferences, Orb access and role-based features.</p>
          <div className="auth-feature-list">
            <div className="auth-feature"><strong>Saved profile</strong><span>User-specific preferences and identity.</span></div>
            <div className="auth-feature"><strong>Orb access</strong><span>Voice-first mode is available only to signed-in users.</span></div>
            <div className="auth-feature"><strong>Admin handoff</strong><span>Admin-capable users can continue into the dashboard.</span></div>
          </div>
        </div>
        <form className="auth-form" onSubmit={(event) => { event.preventDefault(); void submitLogin(); }}>
          <input className="ui-input" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Username" />
          <input className="ui-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" />
          <div className="inline-actions">
            <button className="ui-button primary" type="submit">Login</button>
            <Link className="ui-button ghost" to="/chat">Continue as guest</Link>
          </div>
          {error ? <div className="error-text">{error}</div> : null}
        </form>
      </div>
    </div>
  );
}
