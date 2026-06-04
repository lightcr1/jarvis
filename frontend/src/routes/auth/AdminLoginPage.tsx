import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthProvider";
import { J, useJ } from "../../screens/jarvis-shared";

const FEATURES = [
  { title: "Separater Bereich", desc: "Eigene Navigation, Routen und Session-Grenzen für Operationen." },
  { title: "Geteilte Identität", desc: "Es gibt kein zweites Account-Modell für Administration." },
  { title: "Rollen-Gate", desc: "Der Zugriff erfolgt erst nach verifizierter Admin-Rolle." },
];

export function AdminLoginPage() {
  useJ();
  const { login, ensureAdminAccess } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submitLogin() {
    if (!username.trim()) return;
    setLoading(true);
    setError("");
    try {
      await login(username, password);
      await ensureAdminAccess();
      navigate("/dashboard");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const inp: React.CSSProperties = {
    width: "100%", boxSizing: "border-box", padding: "10px 12px", fontSize: 13,
    borderRadius: 6, background: "rgba(255,255,255,0.05)", border: `1px solid ${J.border}`,
    color: J.text, outline: "none", transition: "border-color .15s",
  };

  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "center",
      minHeight: "100vh", background: J.bg0, padding: 24,
    }}>
      <div style={{
        display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0,
        maxWidth: 760, width: "100%",
        background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 12,
        overflow: "hidden", boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
      }}>

        {/* Left — copy */}
        <div style={{ padding: "36px 32px", background: J.bg1, borderRight: `1px solid ${J.border}` }}>
          <div style={{ fontSize: 10, color: J.amber, textTransform: "uppercase", letterSpacing: "0.12em", fontWeight: 600, marginBottom: 16, padding: "3px 8px", background: J.amberDim, border: `1px solid ${J.borderAccent}`, borderRadius: 3, display: "inline-block" }}>
            Restricted Access
          </div>
          <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
            Jarvis Admin Portal
          </div>
          <h1 style={{ margin: "0 0 12px", fontSize: 20, fontWeight: 700, color: J.text, lineHeight: 1.3 }}>
            Betritt den getrennten Operator-Bereich.
          </h1>
          <p style={{ fontSize: 13, color: J.textSec, lineHeight: 1.6, marginBottom: 24 }}>
            Das Dashboard bleibt vom Chat getrennt, nutzt aber dieselbe Identität. Eine Admin-Session wird nur nach erfolgreicher Rollenprüfung ausgestellt.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {FEATURES.map(f => (
              <div key={f.title} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                <div style={{ width: 5, height: 5, borderRadius: "50%", background: J.amber, marginTop: 6, flexShrink: 0 }} />
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: J.text }}>{f.title}</div>
                  <div style={{ fontSize: 12, color: J.textMuted, marginTop: 2 }}>{f.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right — form */}
        <div style={{ padding: "36px 32px", display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <div style={{ marginBottom: 28 }}>
            <div style={{ width: 36, height: 36, borderRadius: 9, background: J.amberDim, border: `1px solid ${J.borderAccent}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, fontWeight: 700, color: J.amber, marginBottom: 12 }}>J</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: J.text }}>Sign in to Dashboard</div>
            <div style={{ fontSize: 12, color: J.textMuted, marginTop: 4 }}>Admin credentials required</div>
          </div>

          <form onSubmit={e => { e.preventDefault(); void submitLogin(); }} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <div style={{ fontSize: 11, color: J.textMuted, marginBottom: 5 }}>Username</div>
              <input
                style={inp}
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="admin username"
                autoComplete="username"
                autoFocus
                onFocus={e => { e.currentTarget.style.borderColor = J.borderAccent; }}
                onBlur={e => { e.currentTarget.style.borderColor = J.border; }}
              />
            </div>
            <div>
              <div style={{ fontSize: 11, color: J.textMuted, marginBottom: 5 }}>Password</div>
              <input
                style={inp}
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="password"
                autoComplete="current-password"
                onFocus={e => { e.currentTarget.style.borderColor = J.borderAccent; }}
                onBlur={e => { e.currentTarget.style.borderColor = J.border; }}
              />
            </div>
            {error && (
              <div style={{ fontSize: 12, color: J.error, background: J.errorDim, border: `1px solid ${J.error}30`, borderRadius: 5, padding: "8px 12px" }}>{error}</div>
            )}
            <button
              type="submit"
              disabled={loading || !username.trim()}
              style={{
                padding: "10px", fontSize: 13, fontWeight: 600, borderRadius: 6, cursor: "pointer",
                background: J.amber, color: J.bg0, border: "none", marginTop: 4,
                opacity: loading || !username.trim() ? 0.6 : 1, transition: "opacity .15s",
              }}
            >{loading ? "Signing in…" : "Dashboard öffnen"}</button>
          </form>
        </div>
      </div>
    </div>
  );
}
