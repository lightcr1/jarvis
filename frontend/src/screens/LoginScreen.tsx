import { useState } from 'react';
import { J, Spinner, IconCheck, IconLock } from './jarvis-shared';
import { login, setStoredIdentity } from '../shared/api/client';

export function LoginScreen({ onLogin, onGuest }: { onLogin: () => void; onGuest?: () => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [state, setState] = useState<'idle' | 'loading' | 'error' | 'success'>('idle');
  const [errorMsg, setErrorMsg] = useState('');

  const handleLogin = async () => {
    if (!username || !password) { setState('error'); setErrorMsg('Please enter username and password.'); return; }
    setState('loading');
    try {
      const result = await login(username, password);
      setStoredIdentity(result.session_token, result.user, result.preferences || {});
      setState('success');
      setTimeout(onLogin, 500);
    } catch (err) {
      setState('error');
      setErrorMsg((err as Error).message || 'Invalid credentials.');
    }
  };

  const onKey = (e: React.KeyboardEvent) => { if (e.key === 'Enter') void handleLogin(); };

  return (
    <div style={{ position: 'fixed', inset: 0, background: J.bg0, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20, overflow: 'hidden' }}>
      <style>{`@keyframes loginGlow{0%,100%{opacity:.6;transform:translateX(-50%) scale(1)}50%{opacity:1;transform:translateX(-50%) scale(1.06)}}`}</style>
      <div style={{ position: 'absolute', inset: 0, backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.035) 1px, transparent 1px)', backgroundSize: '24px 24px', pointerEvents: 'none' }} />
      <div style={{ position: 'absolute', top: '38%', left: '50%', width: 640, height: 300, background: 'radial-gradient(ellipse, rgba(224,154,26,0.07) 0%, transparent 70%)', pointerEvents: 'none', animation: 'loginGlow 6s ease-in-out infinite', transform: 'translateX(-50%)' }} />
      <div style={{ width: '100%', maxWidth: 400, background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 16, padding: '40px 36px 36px', animation: 'fadeIn 0.3s ease', position: 'relative', zIndex: 1 }}>

        <div style={{ marginBottom: 32 }}>
          <div style={{ width: 44, height: 44, borderRadius: 11, background: J.amberDim, border: `1px solid ${J.borderAccent}`, display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 20 }}>
            <span style={{ fontSize: 18, fontWeight: 700, color: J.amber }}>J</span>
          </div>
          <h1 style={{ fontSize: 22, fontWeight: 600, color: J.text, marginBottom: 4, letterSpacing: '-0.01em' }}>J.A.R.V.I.S.</h1>
          <p style={{ fontSize: 12, color: J.textMuted, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 500 }}>Identity Verification Required</p>
        </div>

        {state === 'error' && (
          <div style={{ background: J.errorDim, border: `1px solid rgba(224,85,85,0.25)`, borderRadius: 8, padding: '10px 14px', fontSize: 13, color: J.error, marginBottom: 16, animation: 'fadeIn .2s ease' }}>
            {errorMsg}
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 16 }}>
          <input autoFocus className="j-input" type="text" placeholder="Username" value={username}
            onChange={e => { setUsername(e.target.value); setState('idle'); }} onKeyDown={onKey}
            style={{ borderRadius: 9, padding: '11px 14px', fontSize: 14, width: '100%' }} />
          <input className="j-input" type="password" placeholder="Password" value={password}
            onChange={e => { setPassword(e.target.value); setState('idle'); }} onKeyDown={onKey}
            style={{ borderRadius: 9, padding: '11px 14px', fontSize: 14, width: '100%' }} />
        </div>

        <button className="j-btn" onClick={() => void handleLogin()}
          style={{ width: '100%', background: state === 'success' ? J.success : J.amber, color: '#0c0c0c', borderRadius: 9, padding: '12px 20px', fontSize: 14, fontWeight: 600, justifyContent: 'center', opacity: state === 'loading' ? .85 : 1 }}>
          {state === 'loading' && <><Spinner size={15} color="#0c0c0c" /> Signing in…</>}
          {state === 'success' && <><IconCheck size={15} /> Access granted</>}
          {(state === 'idle' || state === 'error') && 'Sign in'}
        </button>

        {onGuest && (
          <button onClick={onGuest}
            style={{ width: '100%', marginTop: 10, background: 'none', border: `1px solid ${J.border}`, borderRadius: 9, padding: '10px 20px', fontSize: 13, color: J.textMuted, cursor: 'pointer', transition: 'all .12s' }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.2)'; e.currentTarget.style.color = J.textSec; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = J.border; e.currentTarget.style.color = J.textMuted; }}>
            Continue as Guest
          </button>
        )}

        <p style={{ textAlign: 'center', marginTop: 18, fontSize: 11, color: J.textMuted, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
          <IconLock size={10} /> Local instance · Credentials never leave this network
        </p>
      </div>
    </div>
  );
}
