import { useState, useEffect } from 'react';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { J, useJ, applyTheme, applyAccent, applyCompact, StatusBadge, ToastContainer, IconChat, IconOrb, IconHome, IconGrid, IconSettings, IconServer, IconBook, IconX, IconSun, IconMoon } from './jarvis-shared';
import { GreetingOverlay } from '../components/GreetingOverlay';
import { OnboardingModal, shouldShowOnboarding } from '../components/OnboardingModal';
import { LoginScreen } from './LoginScreen';
import { ChatScreen } from './ChatScreen';
import { OrbScreen } from './OrbScreen';
import { HomeAssistantScreen } from './HomeAssistantScreen';
import { ProxmoxScreen } from './ProxmoxScreen';
import { ServiceHubScreen } from './ServiceHubScreen';
import { SettingsScreen } from './SettingsScreen';
import { DocsScreen } from './DocsScreen';
import { getSessionToken, clearStoredIdentity, getStoredPreferences, setStoredPreferences, getStoredUser, setGuestMode, isGuestMode } from '../shared/api/client';
import { useJarvisAlerts } from '../shared/api/alerts';
import { useJarvisLiveStatus } from '../shared/api/status';

type Screen = 'login' | 'chat' | 'orb' | 'home' | 'proxmox' | 'services' | 'settings' | 'docs';

const NAV: Array<{ id: Screen; label: string; icon: (p: { size?: number }) => JSX.Element }> = [
  { id: 'chat',     label: 'Chat',     icon: IconChat     },
  { id: 'orb',      label: 'Voice',    icon: IconOrb      },
  { id: 'home',     label: 'Home',     icon: IconHome     },
  { id: 'proxmox',  label: 'Proxmox',  icon: IconServer   },
  { id: 'services', label: 'Services', icon: IconGrid     },
  { id: 'docs',     label: 'Docs',     icon: IconBook     },
  { id: 'settings', label: 'Settings', icon: IconSettings },
];

// Inject mobile nav styles once
(function () {
  if (document.getElementById('jarvis-nav-styles')) return;
  const s = document.createElement('style');
  s.id = 'jarvis-nav-styles';
  s.textContent = `
    .nav-rail   { display: flex; }
    .nav-bottom { display: none; }
    @media (max-width: 640px) {
      .nav-rail   { display: none !important; }
      .nav-bottom { display: flex !important; }
    }
  `;
  document.head.appendChild(s);
})();

function NavRail({ current, onNav, onLogout }: { current: Screen; onNav: (s: Screen) => void; onLogout: () => void }) {
  const [showMenu, setShowMenu] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);
  const [isDark, setIsDark] = useState(() => (getStoredPreferences().theme ?? 'dark') === 'dark');
  const prefs = getStoredPreferences();
  const user = getStoredUser();
  const userInitial = ((prefs.display_name || user?.username || 'G')[0] ?? 'G').toUpperCase();

  const toggleTheme = () => {
    const next = isDark ? 'light' : 'dark';
    setIsDark(!isDark);
    applyTheme(next);
    const p = getStoredPreferences();
    const updated = { ...p, theme: next as 'dark' | 'light' };
    setStoredPreferences(updated);
  };

  return (
    <nav className="nav-rail" aria-label="Main navigation" style={{ width: 60, flexShrink: 0, background: J.bg1, borderRight: `1px solid ${J.border}`, flexDirection: 'column', alignItems: 'center', padding: '14px 0', zIndex: 10, position: 'relative' }}>
      <div style={{ width: 34, height: 34, borderRadius: 9, background: J.amberDim, border: `1px solid ${J.borderAccent}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, fontWeight: 700, color: J.amber, marginBottom: 20, cursor: 'default', userSelect: 'none' }}>
        J
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1 }}>
        {NAV.map(item => {
          const active = current === item.id;
          return (
            <div key={item.id} style={{ position: 'relative' }}>
              <button onClick={() => onNav(item.id)} aria-label={item.label}
                onMouseEnter={e => { setHovered(item.id); if (!active) { e.currentTarget.style.background = J.bg2; e.currentTarget.style.color = J.textSec; } }}
                onMouseLeave={e => { setHovered(null); if (!active) { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = J.textMuted; } }}
                style={{ width: 44, height: 44, borderRadius: 10, background: active ? J.bg3 : 'none', border: `1px solid ${active ? J.border : 'transparent'}`, color: active ? J.amber : J.textMuted, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all .12s' }}>
                <item.icon size={17} />
              </button>
              {hovered === item.id && (
                <div style={{ position: 'absolute', left: 50, top: '50%', transform: 'translateY(-50%)', background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6, padding: '4px 10px', fontSize: 12, color: J.textSec, whiteSpace: 'nowrap', pointerEvents: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.35)', zIndex: 100, animation: 'fadeIn .1s ease' }}>
                  {item.label}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Theme toggle */}
      <button onClick={toggleTheme} title={isDark ? 'Switch to light mode' : 'Switch to dark mode'} aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
        style={{ width: 34, height: 34, borderRadius: 9, background: 'none', border: `1px solid ${J.border}`, color: J.textMuted, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 8, transition: 'all .15s' }}
        onMouseEnter={e => { e.currentTarget.style.color = J.amber; e.currentTarget.style.borderColor = J.borderAccent; }}
        onMouseLeave={e => { e.currentTarget.style.color = J.textMuted; e.currentTarget.style.borderColor = J.border; }}>
        {isDark ? <IconSun size={15} /> : <IconMoon size={15} />}
      </button>

      <div style={{ position: 'relative' }}>
        <button onClick={() => setShowMenu(v => !v)}
          style={{ width: 32, height: 32, borderRadius: 8, background: J.bg3, border: `1px solid ${J.border}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 600, color: J.textSec, cursor: 'pointer', userSelect: 'none' }}>
          {userInitial}
        </button>
        {showMenu && (
          <>
            <div onClick={() => setShowMenu(false)} style={{ position: 'fixed', inset: 0, zIndex: 20 }} />
            <div style={{ position: 'absolute', bottom: 40, left: 8, width: 168, background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 10, zIndex: 21, overflow: 'hidden', boxShadow: '0 8px 24px rgba(0,0,0,0.4)' }}>
              <button onClick={() => { setShowMenu(false); toggleTheme(); }}
                style={{ width: '100%', textAlign: 'left', padding: '10px 14px', background: 'none', border: 'none', color: J.textSec, fontSize: 13, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
                onMouseEnter={e => { e.currentTarget.style.background = J.bg3; e.currentTarget.style.color = J.text; }}
                onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = J.textSec; }}>
                {isDark ? 'Light mode' : 'Dark mode'}
                <span style={{ opacity: 0.5 }}>{isDark ? <IconSun size={13} /> : <IconMoon size={13} />}</span>
              </button>
              <div style={{ height: 1, background: J.border, margin: '0 10px' }} />
              <button onClick={() => { setShowMenu(false); onNav('settings'); }}
                style={{ width: '100%', textAlign: 'left', padding: '10px 14px', background: 'none', border: 'none', color: J.textSec, fontSize: 13, cursor: 'pointer' }}
                onMouseEnter={e => { e.currentTarget.style.background = J.bg3; e.currentTarget.style.color = J.text; }}
                onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = J.textSec; }}>
                Settings
              </button>
              <button onClick={() => { setShowMenu(false); window.location.href = '/dashboard'; }}
                style={{ width: '100%', textAlign: 'left', padding: '10px 14px', background: 'none', border: 'none', color: J.textSec, fontSize: 13, cursor: 'pointer' }}
                onMouseEnter={e => { e.currentTarget.style.background = J.bg3; e.currentTarget.style.color = J.text; }}
                onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = J.textSec; }}>
                Admin Dashboard
              </button>
              <div style={{ height: 1, background: J.border, margin: '0 10px' }} />
              <button onClick={() => { setShowMenu(false); onLogout(); }}
                style={{ width: '100%', textAlign: 'left', padding: '10px 14px', background: 'none', border: 'none', color: J.error, fontSize: 13, cursor: 'pointer' }}
                onMouseEnter={e => { e.currentTarget.style.background = J.bg3; }}
                onMouseLeave={e => { e.currentTarget.style.background = 'none'; }}>
                Sign out
              </button>
            </div>
          </>
        )}
      </div>
    </nav>
  );
}

const NAV_BOTTOM = NAV.filter(n => ['chat', 'orb', 'home', 'services', 'settings'].includes(n.id));

function BottomNav({ current, onNav }: { current: Screen; onNav: (s: Screen) => void }) {
  return (
    <nav className="nav-bottom" aria-label="Main navigation" style={{ position: 'fixed', bottom: 0, left: 0, right: 0, height: 60, background: J.bg1, borderTop: `1px solid ${J.border}`, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around', zIndex: 100, paddingBottom: 'env(safe-area-inset-bottom)' }}>
      {NAV_BOTTOM.map(item => {
        const active = current === item.id;
        return (
          <button key={item.id} onClick={() => onNav(item.id)}
            style={{ flex: 1, height: '100%', background: 'none', border: 'none', color: active ? J.amber : J.textMuted, cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 3, transition: 'color .12s' }}>
            <item.icon size={18} />
            <span style={{ fontSize: 10, fontWeight: 500 }}>{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

export function JarvisApp() {
  useJ(); // re-render when theme changes
  const liveStatus = useJarvisLiveStatus();
  const { alerts, dismissAlert } = useJarvisAlerts();
  const [screen, setScreen] = useState<Screen>(() => {
    const params = new URLSearchParams(window.location.search);
    const req = params.get('screen') as Screen | null;
    const publicScreens: Screen[] = ['docs'];
    const validScreens: Screen[] = ['chat', 'orb', 'home', 'proxmox', 'services', 'settings', 'docs'];
    const requested = (req && validScreens.includes(req)) ? req : null;
    if (getSessionToken() || isGuestMode()) return requested ?? 'chat';
    if (requested && publicScreens.includes(requested)) return requested;
    return 'login';
  });
  // Show greeting on every fresh app open (not suppressed — fires each load by design)
  const [showGreeting, setShowGreeting] = useState(() => !!(getSessionToken() || isGuestMode()));
  const [showOnboarding, setShowOnboarding] = useState(false);

  useEffect(() => {
    const prefs = getStoredPreferences();
    if (prefs.theme) applyTheme(prefs.theme);
    if (prefs.accent_color) applyAccent(prefs.accent_color);
    applyCompact(prefs.compact_mode ?? false);
    // Check onboarding on initial load if already authenticated
    if (getSessionToken()) {
      shouldShowOnboarding().then(show => { if (show) setShowOnboarding(true); }).catch(() => {});
    }
  }, []);

  const handleLogin = () => {
    const prefs = getStoredPreferences();
    if (prefs.theme) applyTheme(prefs.theme);
    if (prefs.accent_color) applyAccent(prefs.accent_color);
    applyCompact(prefs.compact_mode ?? false);
    setScreen('chat');
    setShowGreeting(true); // greet on every login
    shouldShowOnboarding().then(show => { if (show) setShowOnboarding(true); }).catch(() => {});
  };

  const handleGuestLogin = () => {
    setGuestMode();
    setScreen('chat');
    setShowGreeting(true);
  };

  const handleLogout = () => {
    clearStoredIdentity();
    setScreen('login');
  };

  const navigate = (s: string) => {
    const valid: Screen[] = ['chat', 'orb', 'home', 'proxmox', 'services', 'settings', 'docs', 'login'];
    if (valid.includes(s as Screen)) setScreen(s as Screen);
  };

  // Mobile bottom-nav padding
  const [mobilePad, setMobilePad] = useState(false);
  useEffect(() => {
    const update = () => setMobilePad(window.innerWidth <= 640);
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  useEffect(() => {
    if (!alerts.length) return;
    const timers = alerts.map((alert) => window.setTimeout(() => dismissAlert(alert.id), 7000));
    return () => { timers.forEach(timer => window.clearTimeout(timer)); };
  }, [alerts, dismissAlert]);

  if (screen === 'login') return <LoginScreen onLogin={handleLogin} onGuest={handleGuestLogin} />;

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {showGreeting && <GreetingOverlay onDismiss={() => setShowGreeting(false)} />}
      {showOnboarding && <OnboardingModal onDismiss={() => setShowOnboarding(false)} />}
      <ToastContainer />
      <NavRail current={screen} onNav={setScreen} onLogout={handleLogout} />
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', paddingBottom: mobilePad ? 60 : 0, position: 'relative' }}>
        {screen !== 'chat' && screen !== 'orb' && (
          <div style={{ position: 'absolute', top: 10, right: 14, zIndex: 30, display: 'flex', alignItems: 'center', gap: 7, background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 999, padding: '6px 10px', boxShadow: '0 8px 24px rgba(0,0,0,0.18)' }}>
            <StatusBadge status={liveStatus.state === 'idle' ? 'local' : liveStatus.state === 'processing' ? 'running' : liveStatus.state === 'recording' ? 'active' : 'online'} size="xs" />
            <span style={{ fontSize: 11, color: J.textSec, textTransform: 'capitalize' }}>{liveStatus.state}</span>
          </div>
        )}
        <ErrorBoundary label={screen}>
          {screen === 'chat'     && <ChatScreen onNavigate={navigate} />}
          {screen === 'orb'      && <OrbScreen onNavigate={navigate} liveState={liveStatus.state} />}
          {screen === 'home'     && <HomeAssistantScreen onNavigate={navigate} />}
          {screen === 'proxmox'  && <ProxmoxScreen onNavigate={navigate} />}
          {screen === 'services' && <ServiceHubScreen onNavigate={navigate} />}
          {screen === 'docs'     && <DocsScreen />}
          {screen === 'settings' && <SettingsScreen />}
        </ErrorBoundary>
        <div style={{ position: 'absolute', right: 14, bottom: mobilePad ? 74 : 14, zIndex: 40, display: 'flex', flexDirection: 'column', gap: 10, pointerEvents: 'none' }}>
          {alerts.map(alert => (
            <div key={alert.id} style={{ width: 'min(340px, calc(100vw - 28px))', background: J.bg2, border: `1px solid ${alert.level === 'warning' ? J.warn : J.border}`, borderLeft: `3px solid ${alert.level === 'warning' ? J.warn : J.blue}`, borderRadius: 12, padding: '12px 14px', boxShadow: '0 12px 32px rgba(0,0,0,0.28)', pointerEvents: 'auto' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 4 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: J.text }}>{alert.title}</div>
                <button onClick={() => dismissAlert(alert.id)} aria-label="Dismiss alert" style={{ background: 'none', border: 'none', color: J.textMuted, cursor: 'pointer', display: 'flex', padding: 0 }}>
                  <IconX size={14} />
                </button>
              </div>
              <div style={{ fontSize: 12, color: J.textSec, lineHeight: 1.5 }}>{alert.message}</div>
            </div>
          ))}
        </div>
      </div>
      <BottomNav current={screen} onNav={setScreen} />
    </div>
  );
}
