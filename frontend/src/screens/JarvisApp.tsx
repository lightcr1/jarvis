import { useState, useEffect, useRef } from 'react';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { J, useJ, applyTheme, applyAccent, applyCompact, StatusBadge, ToastContainer, Badge, IconChat, IconOrb, IconHome, IconGrid, IconSettings, IconServer, IconBook, IconX, IconSun, IconMoon, IconBell, IconSearch } from './jarvis-shared';
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
import { getSessionToken, clearStoredIdentity, getStoredPreferences, setStoredPreferences, getStoredUser, setGuestMode, isGuestMode, clearGuestMode, setPendingChatPrefill } from '../shared/api/client';
import { useJarvisAlerts } from '../shared/api/alerts';
import { useJarvisLiveStatus } from '../shared/api/status';
import { OverlayDialog } from '../shared/ui/OverlayDialog';

type Screen = 'login' | 'chat' | 'orb' | 'home' | 'proxmox' | 'services' | 'settings' | 'docs';

const NAV_ALL: Array<{ id: Screen; label: string; icon: (p: { size?: number }) => JSX.Element }> = [
  { id: 'chat',     label: 'Chat',     icon: IconChat     },
  { id: 'orb',      label: 'Voice',    icon: IconOrb      },
  { id: 'home',     label: 'Home',     icon: IconHome     },
  { id: 'proxmox',  label: 'Proxmox',  icon: IconServer   },
  { id: 'services', label: 'Services', icon: IconGrid     },
  { id: 'docs',     label: 'Docs',     icon: IconBook     },
  { id: 'settings', label: 'Settings', icon: IconSettings },
];

const NAV_GUEST: Array<{ id: Screen; label: string; icon: (p: { size?: number }) => JSX.Element }> = [
  { id: 'chat',     label: 'Chat',     icon: IconChat     },
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

function NavRail({ current, onNav, onLogout, nav, isGuest, isAdmin, unreadCount }: { current: Screen; onNav: (s: Screen) => void; onLogout: () => void; nav: typeof NAV_ALL; isGuest: boolean; isAdmin: boolean; unreadCount: number }) {
  const [showMenu, setShowMenu] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);
  const [isDark, setIsDark] = useState(() => (getStoredPreferences().theme ?? 'dark') === 'dark');
  const prefs = getStoredPreferences();
  const user = getStoredUser();
  const userInitial = ((prefs.display_name || user?.username || (isGuest ? 'G' : 'G'))[0] ?? 'G').toUpperCase();

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
        {nav.map(item => {
          const active = current === item.id;
          return (
            <div key={item.id} style={{ position: 'relative' }}>
              <button onClick={() => onNav(item.id)} aria-label={item.label}
                onMouseEnter={e => { setHovered(item.id); if (!active) { e.currentTarget.style.background = J.bg2; e.currentTarget.style.color = J.textSec; } }}
                onMouseLeave={e => { setHovered(null); if (!active) { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = J.textMuted; } }}
                style={{ width: 44, height: 44, borderRadius: 10, background: active ? J.bg3 : 'none', border: `1px solid ${active ? J.border : 'transparent'}`, color: active ? J.amber : J.textMuted, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all .12s', position: 'relative' }}>
                <item.icon size={17} />
                {item.id === 'services' && <Badge count={unreadCount} />}
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
              {!isGuest && (
                <button onClick={() => { setShowMenu(false); onNav('settings'); }}
                  style={{ width: '100%', textAlign: 'left', padding: '10px 14px', background: 'none', border: 'none', color: J.textSec, fontSize: 13, cursor: 'pointer' }}
                  onMouseEnter={e => { e.currentTarget.style.background = J.bg3; e.currentTarget.style.color = J.text; }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = J.textSec; }}>
                  Settings
                </button>
              )}
              {isAdmin && (
                <button onClick={() => { setShowMenu(false); window.location.href = '/dashboard'; }}
                  style={{ width: '100%', textAlign: 'left', padding: '10px 14px', background: 'none', border: 'none', color: J.textSec, fontSize: 13, cursor: 'pointer' }}
                  onMouseEnter={e => { e.currentTarget.style.background = J.bg3; e.currentTarget.style.color = J.text; }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = J.textSec; }}>
                  Admin Dashboard
                </button>
              )}
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

function BottomNav({ current, onNav, nav, unreadCount }: { current: Screen; onNav: (s: Screen) => void; nav: typeof NAV_ALL; unreadCount: number }) {
  const bottomItems = nav.filter(n => ['chat', 'orb', 'home', 'services', 'settings', 'docs'].includes(n.id)).slice(0, 5);
  return (
    <nav className="nav-bottom" aria-label="Main navigation" style={{ position: 'fixed', bottom: 0, left: 0, right: 0, height: 60, background: J.bg1, borderTop: `1px solid ${J.border}`, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around', zIndex: 100, paddingBottom: 'env(safe-area-inset-bottom)' }}>
      {bottomItems.map(item => {
        const active = current === item.id;
        return (
          <button key={item.id} onClick={() => onNav(item.id)}
            style={{ flex: 1, height: '100%', background: 'none', border: 'none', color: active ? J.amber : J.textMuted, cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 3, transition: 'color .12s', position: 'relative' }}>
            <span style={{ position: 'relative', display: 'inline-flex' }}>
              <item.icon size={18} />
              {item.id === 'services' && <Badge count={unreadCount} />}
            </span>
            <span style={{ fontSize: 10, fontWeight: 500 }}>{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

function CommandPalette({ nav, onNav, onClose }: { nav: typeof NAV_ALL; onNav: (s: Screen) => void; onClose: () => void }) {
  const [query, setQuery] = useState('');
  const [idx, setIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const prefs = getStoredPreferences();
  const quickActions = prefs.quick_actions ?? ['Briefing', 'System status', 'Weather'];

  const screenItems = nav.map(n => ({ kind: 'screen' as const, id: n.id, label: n.label }));
  const actionItems = quickActions.map(q => ({ kind: 'action' as const, id: q, label: q }));
  const all = [...screenItems, ...actionItems];
  const filtered = query
    ? all.filter(i => i.label.toLowerCase().includes(query.toLowerCase()))
    : all;

  useEffect(() => { inputRef.current?.focus(); }, []);
  useEffect(() => { setIdx(0); }, [query]);

  const select = (item: typeof filtered[0]) => {
    if (item.kind === 'screen') { onNav(item.id as Screen); }
    else { setPendingChatPrefill(item.id); onNav('chat'); }
    onClose();
  };

  return (
    <OverlayDialog title="Command Palette" onClose={onClose}>
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: J.bg3, border: `1px solid ${J.border}`, borderRadius: 8, padding: '8px 12px' }}>
          <span style={{ color: J.textMuted, display: 'flex' }}><IconSearch size={14} /></span>
          <input ref={inputRef} value={query} onChange={e => setQuery(e.target.value)}
            placeholder="Search screens and actions..."
            onKeyDown={e => {
              if (e.key === 'ArrowDown') { e.preventDefault(); setIdx(i => Math.min(i + 1, filtered.length - 1)); }
              if (e.key === 'ArrowUp') { e.preventDefault(); setIdx(i => Math.max(i - 1, 0)); }
              if (e.key === 'Enter' && filtered[idx]) select(filtered[idx]);
            }}
            style={{ background: 'none', border: 'none', outline: 'none', fontSize: 14, color: J.text, flex: 1, fontFamily: 'inherit' }} />
        </div>
      </div>
      <div style={{ maxHeight: 280, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
        {filtered.map((item, i) => (
          <button key={item.kind + item.id} onClick={() => select(item)}
            style={{ width: '100%', textAlign: 'left', background: i === idx ? J.bg3 : 'none', border: `1px solid ${i === idx ? J.border : 'transparent'}`, borderRadius: 7, padding: '9px 12px', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', transition: 'background .08s' }}
            onMouseEnter={() => setIdx(i)}>
            <span style={{ fontSize: 13, color: J.text }}>{item.label}</span>
            <span style={{ fontSize: 11, color: J.textMuted, background: J.bg4, padding: '2px 7px', borderRadius: 4 }}>{item.kind === 'screen' ? 'screen' : 'action'}</span>
          </button>
        ))}
        {filtered.length === 0 && <div style={{ fontSize: 13, color: J.textMuted, padding: '12px 0', textAlign: 'center' }}>No matches</div>}
      </div>
    </OverlayDialog>
  );
}

function ShortcutsOverlay({ onClose }: { onClose: () => void }) {
  const shortcuts = [
    { keys: 'Cmd/Ctrl+K', desc: 'Open command palette' },
    { keys: '?', desc: 'Show keyboard shortcuts' },
    { keys: 'Escape', desc: 'Close overlays / cancel' },
    { keys: '/', desc: 'Focus chat composer' },
    { keys: 'Space', desc: 'Toggle mic (Orb screen)' },
  ];
  return (
    <OverlayDialog title="Keyboard Shortcuts" onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {shortcuts.map(s => (
          <div key={s.keys} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 13, color: J.textSec }}>{s.desc}</span>
            <kbd style={{ fontFamily: 'JetBrains Mono,monospace', fontSize: 11, background: J.bg3, border: `1px solid ${J.border}`, borderRadius: 5, padding: '2px 8px', color: J.amber }}>{s.keys}</kbd>
          </div>
        ))}
      </div>
    </OverlayDialog>
  );
}

export function JarvisApp() {
  useJ(); // re-render when theme changes
  const liveStatus = useJarvisLiveStatus();
  const { alerts, dismissAlert } = useJarvisAlerts();
  const guest = isGuestMode();
  const storedUser = getStoredUser();
  const isAdmin = storedUser?.role === 'admin';
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
  const [unreadCount, setUnreadCount] = useState(0);
  const [showPalette, setShowPalette] = useState(false);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const prevAlertCount = useRef(0);

  const nav = guest ? NAV_GUEST : NAV_ALL;
  const GREETING_COOLDOWN_MS = 4 * 60 * 60 * 1000;
  const GREETING_KEY = 'jarvis_last_greeting';
  const _greetingDue = () => {
    const last = localStorage.getItem(GREETING_KEY);
    return !last || Date.now() - Number(last) > GREETING_COOLDOWN_MS;
  };
  const [showGreeting, setShowGreeting] = useState(() => !!(getSessionToken() || isGuestMode()) && _greetingDue());
  const [showOnboarding, setShowOnboarding] = useState(false);

  useEffect(() => {
    const prefs = getStoredPreferences();
    if (prefs.theme) applyTheme(prefs.theme);
    if (prefs.accent_color) applyAccent(prefs.accent_color);
    applyCompact(prefs.compact_mode ?? false);
    if (getSessionToken()) {
      shouldShowOnboarding().then(show => { if (show) setShowOnboarding(true); }).catch(() => {});
    }
  }, []);

  // Track new alerts for the unread badge
  useEffect(() => {
    const notificationsEnabled = getStoredPreferences().notifications_enabled !== false;
    if (!notificationsEnabled) return;
    if (alerts.length > prevAlertCount.current) {
      setUnreadCount(c => c + (alerts.length - prevAlertCount.current));
    }
    prevAlertCount.current = alerts.length;
  }, [alerts]);

  // Auto-redirect to login when the server restarts (session no longer valid)
  useEffect(() => {
    const handleSessionExpired = () => {
      clearGuestMode();
      setScreen('login');
    };
    window.addEventListener('jarvis:session-expired', handleSessionExpired);
    return () => window.removeEventListener('jarvis:session-expired', handleSessionExpired);
  }, []);

  // Allow any screen to reopen the setup guide via a custom event
  useEffect(() => {
    const handleShowOnboarding = () => setShowOnboarding(true);
    window.addEventListener('jarvis:show-onboarding', handleShowOnboarding);
    return () => window.removeEventListener('jarvis:show-onboarding', handleShowOnboarding);
  }, []);

  // Global keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); setShowPalette(v => !v); return; }
      if (e.key === 'Escape') { setShowPalette(false); setShowShortcuts(false); return; }
      const tag = (document.activeElement as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      if (e.key === '?') { setShowShortcuts(v => !v); }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const handleLogin = () => {
    const prefs = getStoredPreferences();
    if (prefs.theme) applyTheme(prefs.theme);
    if (prefs.accent_color) applyAccent(prefs.accent_color);
    applyCompact(prefs.compact_mode ?? false);
    setScreen('chat');
    localStorage.setItem(GREETING_KEY, String(Date.now()));
    setShowGreeting(true);
    shouldShowOnboarding().then(show => { if (show) setShowOnboarding(true); }).catch(() => {});
  };

  const handleGuestLogin = () => {
    setGuestMode();
    setScreen('chat');
    localStorage.setItem(GREETING_KEY, String(Date.now()));
    setShowGreeting(true);
  };

  const handleLogout = () => {
    clearStoredIdentity();
    clearGuestMode();
    setScreen('login');
  };

  const navigate = (s: string) => {
    const valid: Screen[] = ['chat', 'orb', 'home', 'proxmox', 'services', 'settings', 'docs', 'login'];
    if (!valid.includes(s as Screen)) return;
    const guestAllowed: Screen[] = ['chat', 'docs', 'settings', 'login'];
    if (guest && !guestAllowed.includes(s as Screen)) return;
    setScreen(s as Screen);
    setUnreadCount(0);
  };

  // Mobile bottom-nav padding
  const [mobilePad, setMobilePad] = useState(false);
  useEffect(() => {
    const update = () => setMobilePad(window.innerWidth <= 640);
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  const notificationsEnabled = getStoredPreferences().notifications_enabled !== false;

  useEffect(() => {
    if (!alerts.length || !notificationsEnabled) return;
    const timers = alerts.map((alert) => window.setTimeout(() => dismissAlert(alert.id), 7000));
    return () => { timers.forEach(timer => window.clearTimeout(timer)); };
  }, [alerts, dismissAlert, notificationsEnabled]);

  if (screen === 'login') return <LoginScreen onLogin={handleLogin} onGuest={handleGuestLogin} />;

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {showGreeting && <GreetingOverlay onDismiss={() => { setShowGreeting(false); localStorage.setItem(GREETING_KEY, String(Date.now())); }} />}
      {showOnboarding && <OnboardingModal onDismiss={() => setShowOnboarding(false)} />}
      {showPalette && <CommandPalette nav={nav} onNav={navigate as (s: Screen) => void} onClose={() => setShowPalette(false)} />}
      {showShortcuts && <ShortcutsOverlay onClose={() => setShowShortcuts(false)} />}
      <ToastContainer />
      <NavRail current={screen} onNav={navigate as (s: Screen) => void} onLogout={handleLogout} nav={nav} isGuest={guest} isAdmin={isAdmin} unreadCount={notificationsEnabled ? unreadCount : 0} />
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
        {notificationsEnabled && (
          <div style={{ position: 'absolute', right: 14, bottom: mobilePad ? 74 : 14, zIndex: 40, display: 'flex', flexDirection: 'column', gap: 10, pointerEvents: 'none' }}>
            {alerts.map(alert => (
              <div key={alert.id} style={{ width: 'min(340px, calc(100vw - 28px))', background: J.bg2, border: `1px solid ${alert.level === 'warning' ? J.warn : J.border}`, borderLeft: `3px solid ${alert.level === 'warning' ? J.warn : J.blue}`, borderRadius: 12, padding: '12px 14px', boxShadow: '0 12px 32px rgba(0,0,0,0.28)', pointerEvents: 'auto' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 4 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ color: alert.level === 'warning' ? J.warn : J.blue, display: 'flex' }}><IconBell size={12} /></span>
                    <div style={{ fontSize: 12, fontWeight: 600, color: J.text }}>{alert.title}</div>
                  </div>
                  <button onClick={() => dismissAlert(alert.id)} aria-label="Dismiss alert" style={{ background: 'none', border: 'none', color: J.textMuted, cursor: 'pointer', display: 'flex', padding: 0 }}>
                    <IconX size={14} />
                  </button>
                </div>
                <div style={{ fontSize: 12, color: J.textSec, lineHeight: 1.5 }}>{alert.message}</div>
              </div>
            ))}
          </div>
        )}
      </div>
      <BottomNav current={screen} onNav={navigate as (s: Screen) => void} nav={nav} unreadCount={notificationsEnabled ? unreadCount : 0} />
    </div>
  );
}
