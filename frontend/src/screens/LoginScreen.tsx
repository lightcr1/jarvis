import { useState, useEffect } from 'react';
import { J, Spinner, IconCheck, IconLock, IconChevDown } from './jarvis-shared';
import { login, setStoredIdentity, getSignupConfig, signupRequest, verifySignup, resendSignupCode } from '../shared/api/client';

type View = 'login' | 'signup-details' | 'signup-code';
type FormState = 'idle' | 'loading' | 'error' | 'success';

const inp: React.CSSProperties = { borderRadius: 9, padding: '11px 14px', fontSize: 14, width: '100%' };

export function LoginScreen({ onLogin, onGuest }: { onLogin: () => void; onGuest?: () => void }) {
  const [view, setView] = useState<View>('login');
  const [signupEnabled, setSignupEnabled] = useState(false);

  // login fields
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  // signup fields
  const [suUsername, setSuUsername] = useState('');
  const [suEmail, setSuEmail] = useState('');
  const [suPassword, setSuPassword] = useState('');
  const [pendingEmail, setPendingEmail] = useState('');
  const [code, setCode] = useState('');

  const [state, setState] = useState<FormState>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const [resendCooldown, setResendCooldown] = useState(0);

  useEffect(() => {
    getSignupConfig()
      .then(d => setSignupEnabled(d.enabled))
      .catch(() => setSignupEnabled(false));
  }, []);

  useEffect(() => {
    if (resendCooldown <= 0) return;
    const t = window.setTimeout(() => setResendCooldown(c => c - 1), 1000);
    return () => clearTimeout(t);
  }, [resendCooldown]);

  const reset = (nextView: View = 'login') => {
    setState('idle');
    setErrorMsg('');
    setView(nextView);
  };

  const setErr = (msg: string) => { setState('error'); setErrorMsg(msg); };

  // ── Login ─────────────────────────────────────────────────────────────────
  const handleLogin = async () => {
    if (state === 'loading' || state === 'success') return;
    if (!username || !password) { setErr('Please enter username and password.'); return; }
    setState('loading');
    try {
      const result = await login(username, password);
      setStoredIdentity(result.session_token, result.user, result.preferences || {});
      setState('success');
      setTimeout(onLogin, 500);
    } catch (err) {
      const msg = (err as Error).message || '';
      setErr(msg.includes('401') || msg.toLowerCase().includes('invalid') ? 'Invalid username or password.' : msg || 'Sign in failed. Try again.');
    }
  };

  // ── Signup step 1: request code ───────────────────────────────────────────
  const handleSignupRequest = async () => {
    if (state === 'loading' || state === 'success') return;
    if (!suUsername.trim()) { setErr('Please enter a username (min 3 characters).'); return; }
    if (suUsername.trim().length < 3) { setErr('Username must be at least 3 characters.'); return; }
    if (!suEmail.trim()) { setErr('Please enter your email address.'); return; }
    if (!suPassword || suPassword.length < 6) { setErr('Password must be at least 6 characters.'); return; }
    setState('loading');
    try {
      const result = await signupRequest(suUsername.trim(), suEmail.trim(), suPassword);
      setPendingEmail(result.email);
      setState('idle');
      setErrorMsg('');
      setResendCooldown(60);
      setView('signup-code');
    } catch (err) {
      const msg = (err as Error).message || '';
      setErr(msg || 'Signup failed. Try again.');
    }
  };

  // ── Signup step 2: verify code ────────────────────────────────────────────
  const handleVerifyCode = async () => {
    if (state === 'loading' || state === 'success') return;
    if (code.trim().length !== 6) { setErr('Please enter the 6-digit code from your email.'); return; }
    setState('loading');
    try {
      const result = await verifySignup(pendingEmail, code.trim());
      setStoredIdentity(result.session_token, result.user, result.preferences || {});
      setState('success');
      setTimeout(onLogin, 500);
    } catch (err) {
      const msg = (err as Error).message || '';
      setErr(msg.toLowerCase().includes('expired') ? 'Code expired — request a new one below.' : msg || 'Invalid code.');
    }
  };

  const handleResend = async () => {
    if (resendCooldown > 0) return;
    try {
      await resendSignupCode(pendingEmail);
      setResendCooldown(60);
      setCode('');
      setState('idle');
      setErrorMsg('');
    } catch (err) {
      setErr((err as Error).message || 'Resend failed.');
    }
  };

  const onKeyLogin = (e: React.KeyboardEvent) => { if (e.key === 'Enter') void handleLogin(); };
  const onKeySignup = (e: React.KeyboardEvent) => { if (e.key === 'Enter') void handleSignupRequest(); };
  const onKeyCode = (e: React.KeyboardEvent) => { if (e.key === 'Enter') void handleVerifyCode(); };

  const busy = state === 'loading' || state === 'success';

  return (
    <div style={{ position: 'fixed', inset: 0, background: J.bg0, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20, overflow: 'hidden' }}>
      <style>{`@keyframes loginGlow{0%,100%{opacity:.6;transform:translateX(-50%) scale(1)}50%{opacity:1;transform:translateX(-50%) scale(1.06)}}`}</style>
      <div style={{ position: 'absolute', inset: 0, backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.035) 1px, transparent 1px)', backgroundSize: '24px 24px', pointerEvents: 'none' }} />
      <div style={{ position: 'absolute', top: '38%', left: '50%', width: 640, height: 300, background: 'radial-gradient(ellipse, rgba(224,154,26,0.07) 0%, transparent 70%)', pointerEvents: 'none', animation: 'loginGlow 6s ease-in-out infinite', transform: 'translateX(-50%)' }} />

      <div style={{ width: '100%', maxWidth: 400, background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 16, padding: '40px 36px 36px', animation: 'fadeIn 0.3s ease', position: 'relative', zIndex: 1 }}>

        {/* Header */}
        <div style={{ marginBottom: 28 }}>
          <div style={{ width: 44, height: 44, borderRadius: 11, background: J.amberDim, border: `1px solid ${J.borderAccent}`, display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
            <span style={{ fontSize: 18, fontWeight: 700, color: J.amber }}>J</span>
          </div>
          {view === 'login' && (
            <>
              <h1 style={{ fontSize: 22, fontWeight: 600, color: J.text, marginBottom: 4, letterSpacing: '-0.01em' }}>J.A.R.V.I.S.</h1>
              <p style={{ fontSize: 12, color: J.textMuted, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 500 }}>Identity Verification Required</p>
            </>
          )}
          {view === 'signup-details' && (
            <>
              <h1 style={{ fontSize: 20, fontWeight: 600, color: J.text, marginBottom: 4 }}>Create account</h1>
              <p style={{ fontSize: 12, color: J.textMuted }}>You'll receive a verification code by email.</p>
            </>
          )}
          {view === 'signup-code' && (
            <>
              <h1 style={{ fontSize: 20, fontWeight: 600, color: J.text, marginBottom: 4 }}>Check your email</h1>
              <p style={{ fontSize: 12, color: J.textMuted }}>
                We sent a 6-digit code to <span style={{ color: J.textSec }}>{pendingEmail}</span>.
              </p>
            </>
          )}
        </div>

        {/* Error banner */}
        {state === 'error' && (
          <div style={{ background: J.errorDim, border: `1px solid rgba(224,85,85,0.25)`, borderRadius: 8, padding: '10px 14px', fontSize: 13, color: J.error, marginBottom: 16, animation: 'fadeIn .2s ease' }}>
            {errorMsg}
          </div>
        )}

        {/* ── Login form ── */}
        {view === 'login' && (
          <>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 16 }}>
              <input autoFocus className="j-input" type="text" placeholder="Username" value={username}
                onChange={e => { setUsername(e.target.value); setState('idle'); }} onKeyDown={onKeyLogin}
                style={inp} />
              <input className="j-input" type="password" placeholder="Password" value={password}
                onChange={e => { setPassword(e.target.value); setState('idle'); }} onKeyDown={onKeyLogin}
                style={inp} />
            </div>
            <button className="j-btn" onClick={() => void handleLogin()} disabled={busy}
              style={{ width: '100%', background: state === 'success' ? J.success : J.amber, color: '#0c0c0c', borderRadius: 9, padding: '12px 20px', fontSize: 14, fontWeight: 600, justifyContent: 'center', opacity: busy ? .75 : 1, cursor: busy ? 'not-allowed' : 'pointer' }}>
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
            {signupEnabled && (
              <button onClick={() => reset('signup-details')}
                style={{ width: '100%', marginTop: 10, background: 'none', border: `1px solid ${J.border}`, borderRadius: 9, padding: '10px 20px', fontSize: 13, color: J.textMuted, cursor: 'pointer', transition: 'all .12s' }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = J.borderAccent; e.currentTarget.style.color = J.amber; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = J.border; e.currentTarget.style.color = J.textMuted; }}>
                Create account
              </button>
            )}
          </>
        )}

        {/* ── Signup step 1: details ── */}
        {view === 'signup-details' && (
          <>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 16 }}>
              <input autoFocus className="j-input" type="text" placeholder="Username (min 3 characters)" value={suUsername}
                onChange={e => { setSuUsername(e.target.value); setState('idle'); }} onKeyDown={onKeySignup}
                style={inp} />
              <input className="j-input" type="email" placeholder="Email address" value={suEmail}
                onChange={e => { setSuEmail(e.target.value); setState('idle'); }} onKeyDown={onKeySignup}
                style={inp} />
              <input className="j-input" type="password" placeholder="Password (min 6 characters)" value={suPassword}
                onChange={e => { setSuPassword(e.target.value); setState('idle'); }} onKeyDown={onKeySignup}
                style={inp} />
            </div>
            <button className="j-btn" onClick={() => void handleSignupRequest()} disabled={busy}
              style={{ width: '100%', background: J.amber, color: '#0c0c0c', borderRadius: 9, padding: '12px 20px', fontSize: 14, fontWeight: 600, justifyContent: 'center', opacity: busy ? .75 : 1, cursor: busy ? 'not-allowed' : 'pointer' }}>
              {state === 'loading' ? <><Spinner size={15} color="#0c0c0c" /> Sending code…</> : 'Send verification code'}
            </button>
            <button onClick={() => reset('login')} style={{ width: '100%', marginTop: 10, background: 'none', border: 'none', fontSize: 13, color: J.textMuted, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
              <span style={{ display: 'inline-block', transform: 'rotate(90deg)' }}><IconChevDown size={12} /></span> Back to sign in
            </button>
          </>
        )}

        {/* ── Signup step 2: code ── */}
        {view === 'signup-code' && (
          <>
            <div style={{ marginBottom: 16 }}>
              <input autoFocus className="j-input" type="text" inputMode="numeric" placeholder="6-digit code" value={code} maxLength={6}
                onChange={e => { setCode(e.target.value.replace(/\D/g, '').slice(0, 6)); setState('idle'); }} onKeyDown={onKeyCode}
                style={{ ...inp, letterSpacing: '0.22em', fontSize: 20, textAlign: 'center' }} />
            </div>
            <button className="j-btn" onClick={() => void handleVerifyCode()} disabled={busy}
              style={{ width: '100%', background: state === 'success' ? J.success : J.amber, color: '#0c0c0c', borderRadius: 9, padding: '12px 20px', fontSize: 14, fontWeight: 600, justifyContent: 'center', opacity: busy ? .75 : 1, cursor: busy ? 'not-allowed' : 'pointer' }}>
              {state === 'loading' && <><Spinner size={15} color="#0c0c0c" /> Verifying…</>}
              {state === 'success' && <><IconCheck size={15} /> Account created</>}
              {(state === 'idle' || state === 'error') && 'Verify & create account'}
            </button>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 14, gap: 8 }}>
              <button onClick={() => void handleResend()} disabled={resendCooldown > 0}
                style={{ flex: 1, background: 'none', border: `1px solid ${J.border}`, borderRadius: 8, padding: '9px 12px', fontSize: 12, color: resendCooldown > 0 ? J.textMuted : J.textSec, cursor: resendCooldown > 0 ? 'not-allowed' : 'pointer' }}>
                {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : 'Resend code'}
              </button>
              <button onClick={() => reset('signup-details')}
                style={{ flex: 1, background: 'none', border: `1px solid ${J.border}`, borderRadius: 8, padding: '9px 12px', fontSize: 12, color: J.textSec, cursor: 'pointer' }}>
                Change details
              </button>
            </div>
            <button onClick={() => reset('login')} style={{ width: '100%', marginTop: 10, background: 'none', border: 'none', fontSize: 12, color: J.textMuted, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
              <span style={{ display: 'inline-block', transform: 'rotate(90deg)' }}><IconChevDown size={11} /></span> Back to sign in
            </button>
          </>
        )}

        <p style={{ textAlign: 'center', marginTop: 18, fontSize: 11, color: J.textMuted, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
          <IconLock size={10} /> Local instance · Credentials never leave this network
        </p>
      </div>
    </div>
  );
}
