import { useState, useEffect, useRef } from 'react';
import { J, useJ, IconCheck, IconX, IconMic, IconSettings, IconHome, IconVolume, IconRefresh } from '../screens/jarvis-shared';
import { getStoredPreferences, setStoredPreferences, getSessionToken, apiRequest } from '../shared/api/client';
import { synthesizeSpeech } from '../shared/api/chat';
import { fetchHomeAssistantHealth } from '../shared/api/homeAssistant';

const DONE_KEY = 'jarvis_onboarding_done';

type ConfigStatus = 'checking' | 'ok' | 'warn' | 'error';
type JarvisVoice = { id: string; name: string; lang: string; flag?: string };

export function isOnboardingComplete(): boolean {
  return !!localStorage.getItem(DONE_KEY);
}

export function markOnboardingComplete(): void {
  localStorage.setItem(DONE_KEY, '1');
}

export async function shouldShowOnboarding(): Promise<boolean> {
  if (isOnboardingComplete()) return false;
  try {
    const [serverRes, haRes] = await Promise.allSettled([
      fetch('/health').then(r => { if (!r.ok) throw new Error(); }),
      fetchHomeAssistantHealth().then(h => { if (!h.integration.healthy) throw new Error(); }),
    ]);
    const prefs = getStoredPreferences();
    const allOk = serverRes.status === 'fulfilled' && haRes.status === 'fulfilled' && !!prefs.tts_voice;
    if (allOk) { markOnboardingComplete(); return false; }
  } catch { /* show onboarding */ }
  return true;
}

const STEPS = [
  { id: 'llm',   label: 'AI Model',   icon: IconSettings },
  { id: 'voice', label: 'Voice',      icon: IconMic      },
  { id: 'ha',    label: 'Smart Home', icon: IconHome     },
] as const;

function StepIndicator({ current }: { current: number }) {
  const J = useJ();
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 28 }}>
      {STEPS.map((step, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <div key={step.id} style={{ display: 'flex', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
              <div style={{
                width: 26, height: 26, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, fontWeight: 700, transition: 'all .2s', flexShrink: 0,
                background: done ? J.amber : active ? J.amberDim : J.bg4,
                border: `2px solid ${done ? J.amber : active ? J.amber : J.border}`,
                color: done ? J.bg0 : active ? J.amber : J.textMuted,
              }}>
                {done ? <IconCheck size={11} /> : i + 1}
              </div>
              <span style={{ fontSize: 12, color: active ? J.amber : done ? J.textSec : J.textMuted, fontWeight: active ? 600 : 400, transition: 'color .2s', whiteSpace: 'nowrap' }}>
                {step.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div style={{ width: 32, height: 2, background: done ? J.amber : J.border, margin: '0 10px', borderRadius: 1, transition: 'background .3s', flexShrink: 0 }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function EnvVarRow({ name, status, value }: { name: string; status: 'set' | 'unset' | 'default'; value?: string }) {
  const J = useJ();
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 11px', borderRadius: 6, background: J.bg1, border: `1px solid ${J.border}` }}>
      <code style={{ flex: 1, fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: J.text }}>{name}</code>
      <span style={{ fontSize: 11, fontWeight: 500, flexShrink: 0, color: status === 'set' ? J.success : status === 'default' ? J.amber : J.textMuted }}>
        <span style={{ marginRight: 4 }}>{status === 'set' ? '●' : status === 'default' ? '◐' : '○'}</span>
        {status === 'set' ? 'set' : status === 'default' ? (value ?? 'default') : 'not set'}
      </span>
    </div>
  );
}

function Spinner({ size = 12 }: { size?: number }) {
  return (
    <div style={{ width: size, height: size, borderRadius: '50%', border: `2px solid ${J.amber}`, borderTopColor: 'transparent', animation: 'spin .7s linear infinite', flexShrink: 0 }} />
  );
}

function LlmStep() {
  const J = useJ();
  const [status, setStatus] = useState<ConfigStatus>('checking');
  const [provider, setProvider] = useState('');

  useEffect(() => {
    fetch('/health')
      .then(async r => {
        if (!r.ok) throw new Error();
        const d = await r.json().catch(() => ({})) as Record<string, unknown>;
        setProvider(String(d.llm_provider ?? d.provider ?? ''));
        setStatus('ok');
      })
      .catch(() => setStatus('error'));
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <div style={{ fontSize: 19, fontWeight: 600, color: J.text, marginBottom: 5 }}>Language Model</div>
        <div style={{ fontSize: 13, color: J.textSec, lineHeight: 1.6 }}>
          JARVIS needs an LLM to understand commands and generate responses.
          Configure the provider via environment variables before starting the server.
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', borderRadius: 8, transition: 'all .2s', background: status === 'ok' ? J.successDim : status === 'error' ? J.errorDim : J.bg3, border: `1px solid ${status === 'ok' ? J.success : status === 'error' ? J.error : J.border}` }}>
        {status === 'checking' && <Spinner />}
        {status === 'ok'    && <div style={{ color: J.success, display: 'flex' }}><IconCheck size={14} /></div>}
        {status === 'error' && <div style={{ color: J.error,   display: 'flex' }}><IconX size={14} /></div>}
        <span style={{ fontSize: 13, fontWeight: 500, color: status === 'ok' ? J.success : status === 'error' ? J.error : J.textSec }}>
          {status === 'checking' && 'Checking connection…'}
          {status === 'ok'       && `Server connected${provider ? ` — ${provider}` : ''}`}
          {status === 'error'    && 'Server unreachable — check your JARVIS backend'}
        </span>
      </div>

      <div>
        <div style={{ fontSize: 11, color: J.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Environment variables</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <EnvVarRow name="LLM_PROVIDER"    status="default" value="auto" />
          <EnvVarRow name="OPENAI_API_KEY"  status="unset" />
          <EnvVarRow name="GEMINI_API_KEY"  status="unset" />
          <EnvVarRow name="LOCAL_LLM_ENABLED" status="default" value="0" />
        </div>
      </div>

      <div style={{ fontSize: 12, color: J.textMuted, background: J.bg3, borderRadius: 7, padding: '10px 12px', lineHeight: 1.6 }}>
        Set one API key and restart the server. JARVIS auto-detects which provider to use.
        For fully local inference, set <code style={{ fontFamily: "'JetBrains Mono', monospace", color: J.amber, fontSize: 11 }}>LOCAL_LLM_ENABLED=1</code>.
      </div>
    </div>
  );
}

function VoiceStep() {
  const J = useJ();
  const [voices, setVoices] = useState<JarvisVoice[]>([]);
  const [selected, setSelected] = useState(() => getStoredPreferences().tts_voice ?? '');
  const [autoPlay, setAutoPlay] = useState(() => getStoredPreferences().auto_play_voice ?? false);
  const [previewing, setPreviewing] = useState(false);
  const [previewErr, setPreviewErr] = useState('');
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    apiRequest<{ voices: JarvisVoice[] }>('/api/tts/voices')
      .then(d => setVoices(d.voices))
      .catch(() => setVoices([]));
  }, []);

  const save = (voiceId: string, ap: boolean) => {
    const next = { ...getStoredPreferences(), tts_voice: voiceId, auto_play_voice: ap };
    setStoredPreferences(next);
    if (getSessionToken()) {
      apiRequest('/auth/me/preferences', { method: 'PUT', includeUser: true, body: next }).catch(() => {});
    }
  };

  const handleVoice = (id: string) => { setSelected(id); save(id, autoPlay); };
  const handleAutoPlay = (v: boolean) => { setAutoPlay(v); save(selected, v); };

  const preview = () => {
    if (previewing) { audioRef.current?.pause(); setPreviewing(false); return; }
    setPreviewErr('');
    setPreviewing(true);
    synthesizeSpeech('Systems nominal. Standing by, sir.')
      .then(blob => {
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audioRef.current = audio;
        audio.onended = () => { setPreviewing(false); URL.revokeObjectURL(url); };
        audio.onerror = () => { setPreviewing(false); setPreviewErr('Playback failed.'); };
        void audio.play();
      })
      .catch(() => { setPreviewing(false); setPreviewErr('Voice synthesis unavailable.'); });
  };

  const displayed = voices.length > 0 ? voices.slice(0, 10) : [{ id: '', name: 'Default (edge-tts)', lang: 'en-US' }];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <div style={{ fontSize: 19, fontWeight: 600, color: J.text, marginBottom: 5 }}>Voice Settings</div>
        <div style={{ fontSize: 13, color: J.textSec, lineHeight: 1.6 }}>
          Choose JARVIS's voice for spoken responses.
        </div>
      </div>

      <div>
        <div style={{ fontSize: 11, color: J.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>TTS Voice</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 5, maxHeight: 180, overflowY: 'auto' }}>
          {displayed.map(v => {
            const active = selected === v.id;
            return (
              <button key={v.id || 'default'} onClick={() => handleVoice(v.id)}
                style={{ padding: '8px 11px', borderRadius: 7, border: `1px solid ${active ? J.amber : J.border}`, background: active ? J.amberDim : J.bg3, color: active ? J.amber : J.textSec, cursor: 'pointer', textAlign: 'left', transition: 'all .12s', display: 'flex', alignItems: 'center', gap: 7 }}
                onMouseEnter={e => { if (!active) { (e.currentTarget as HTMLButtonElement).style.borderColor = J.borderHover; (e.currentTarget as HTMLButtonElement).style.background = J.bg4; } }}
                onMouseLeave={e => { if (!active) { (e.currentTarget as HTMLButtonElement).style.borderColor = J.border; (e.currentTarget as HTMLButtonElement).style.background = J.bg3; } }}>
                {v.flag && <span style={{ fontSize: 14 }}>{v.flag}</span>}
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 12, fontWeight: 500, color: active ? J.amber : J.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v.name}</div>
                  <div style={{ fontSize: 10, color: J.textMuted }}>{v.lang}</div>
                </div>
                {active && <div style={{ color: J.amber, flexShrink: 0, display: 'flex' }}><IconCheck size={11} /></div>}
              </button>
            );
          })}
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0', borderBottom: `1px solid ${J.border}` }}>
        <div>
          <div style={{ fontSize: 13, color: J.text }}>Auto-play responses</div>
          <div style={{ fontSize: 11, color: J.textMuted, marginTop: 2 }}>Speak every reply aloud automatically</div>
        </div>
        <button onClick={() => handleAutoPlay(!autoPlay)}
          style={{ width: 38, height: 21, borderRadius: 11, background: autoPlay ? J.amber : J.bg4, border: `1px solid ${autoPlay ? J.amber : J.border}`, cursor: 'pointer', position: 'relative', transition: 'all .18s', flexShrink: 0 }}>
          <span style={{ position: 'absolute', top: 3, left: autoPlay ? 17 : 3, width: 13, height: 13, borderRadius: '50%', background: autoPlay ? J.bg0 : J.textMuted, transition: 'left .18s' }} />
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <button onClick={preview}
          style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '7px 14px', borderRadius: 7, border: `1px solid ${J.border}`, background: J.bg3, color: previewing ? J.amber : J.textSec, cursor: 'pointer', fontSize: 12, fontWeight: 500, transition: 'all .12s' }}
          onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = J.borderHover; (e.currentTarget as HTMLButtonElement).style.color = J.text; }}
          onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = J.border; (e.currentTarget as HTMLButtonElement).style.color = previewing ? J.amber : J.textSec; }}>
          {previewing ? <Spinner size={12} /> : <IconVolume size={13} />}
          {previewing ? 'Playing…' : 'Preview voice'}
        </button>
        {previewErr && <span style={{ fontSize: 11, color: J.error }}>{previewErr}</span>}
      </div>
    </div>
  );
}

function HaStep() {
  const J = useJ();
  const [status, setStatus] = useState<ConfigStatus>('checking');
  const [info, setInfo] = useState<{ entities?: number } | null>(null);

  const check = () => {
    setStatus('checking');
    fetchHomeAssistantHealth()
      .then(h => {
        if (h.integration.healthy) {
          setInfo({ entities: h.health.managed_entities });
          setStatus('ok');
        } else if (h.integration.configured) {
          setStatus('warn');
        } else {
          setStatus('error');
        }
      })
      .catch(() => setStatus('error'));
  };

  useEffect(() => { check(); }, []);

  const statusColor = { checking: J.border, ok: J.success, warn: J.warn, error: J.error }[status];
  const statusBg   = { checking: J.bg3, ok: J.successDim, warn: J.warnDim, error: J.errorDim }[status];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <div style={{ fontSize: 19, fontWeight: 600, color: J.text, marginBottom: 5 }}>Home Assistant</div>
        <div style={{ fontSize: 13, color: J.textSec, lineHeight: 1.6 }}>
          Connect JARVIS to your Home Assistant instance for smart home control, automations, and device management.
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', borderRadius: 8, background: statusBg, border: `1px solid ${statusColor}`, transition: 'all .2s' }}>
        {status === 'checking' && <Spinner />}
        {status === 'ok'    && <div style={{ color: J.success, display: 'flex' }}><IconCheck size={14} /></div>}
        {(status === 'error' || status === 'warn') && <div style={{ color: statusColor, display: 'flex' }}><IconX size={14} /></div>}
        <div style={{ flex: 1 }}>
          <span style={{ fontSize: 13, fontWeight: 500, color: status === 'checking' ? J.textSec : statusColor }}>
            {status === 'checking' && 'Checking connection…'}
            {status === 'ok'    && `Connected${info?.entities != null ? ` — ${info.entities} managed entities` : ''}`}
            {status === 'warn'  && 'Reachable but reported unhealthy'}
            {status === 'error' && 'Not connected — configure environment variables'}
          </span>
        </div>
        <button onClick={check} title="Re-check"
          style={{ background: 'none', border: 'none', color: J.textMuted, cursor: 'pointer', display: 'flex', padding: 4, borderRadius: 4, transition: 'color .12s' }}
          onMouseEnter={e => (e.currentTarget as HTMLButtonElement).style.color = J.text}
          onMouseLeave={e => (e.currentTarget as HTMLButtonElement).style.color = J.textMuted}>
          <IconRefresh size={13} />
        </button>
      </div>

      {(status === 'error' || status === 'warn') && (
        <div>
          <div style={{ fontSize: 11, color: J.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Required environment variables</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <EnvVarRow name="JARVIS_HA_BASE_URL" status="unset" />
            <EnvVarRow name="JARVIS_HOME_ASSISTANT_TOKEN" status="unset" />
          </div>
        </div>
      )}

      {status === 'error' && (
        <div style={{ fontSize: 12, color: J.textMuted, background: J.bg3, borderRadius: 7, padding: '10px 12px', lineHeight: 1.6 }}>
          Set <code style={{ fontFamily: "'JetBrains Mono', monospace", color: J.amber, fontSize: 11 }}>JARVIS_HA_BASE_URL</code> to your HA instance (e.g.{' '}
          <code style={{ fontFamily: "'JetBrains Mono', monospace", color: J.textSec, fontSize: 11 }}>http://homeassistant.local:8123</code>) and a long-lived access token from your HA profile, then restart JARVIS.
        </div>
      )}

      {status === 'ok' && (
        <div style={{ fontSize: 13, color: J.textSec, background: J.successDim, borderRadius: 7, padding: '10px 12px', lineHeight: 1.5, border: `1px solid rgba(61,186,132,0.2)` }}>
          Home Assistant is connected. JARVIS can control your devices, manage automations, and respond to smart home commands.
        </div>
      )}
    </div>
  );
}

export function OnboardingModal({ onDismiss }: { onDismiss: () => void }) {
  const J = useJ();
  const [step, setStep] = useState(0);
  const isLast = step === STEPS.length - 1;

  const handleNext = () => {
    if (isLast) { markOnboardingComplete(); onDismiss(); }
    else setStep(s => s + 1);
  };

  const handleSkip = () => { markOnboardingComplete(); onDismiss(); };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="JARVIS initial setup"
      style={{ position: 'fixed', inset: 0, zIndex: 250, background: 'rgba(0,0,0,0.72)', display: 'flex', alignItems: 'center', justifyContent: 'center', backdropFilter: 'blur(4px)', animation: 'fadeIn .2s ease' }}>
      <div style={{ width: 'min(540px, 96vw)', background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 14, boxShadow: '0 32px 80px rgba(0,0,0,0.55)', overflow: 'hidden', animation: 'fadeIn .25s ease' }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 22px 0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 28, height: 28, borderRadius: 7, background: J.amberDim, border: `1px solid ${J.borderAccent}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, color: J.amber }}>J</div>
            <span style={{ fontSize: 12, color: J.textMuted, fontWeight: 500, letterSpacing: '0.03em' }}>INITIAL SETUP</span>
          </div>
          <button onClick={handleSkip}
            style={{ background: 'none', border: 'none', color: J.textMuted, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, padding: '4px 8px', borderRadius: 5, transition: 'color .12s' }}
            onMouseEnter={e => (e.currentTarget as HTMLButtonElement).style.color = J.textSec}
            onMouseLeave={e => (e.currentTarget as HTMLButtonElement).style.color = J.textMuted}>
            <IconX size={12} /> Skip setup
          </button>
        </div>

        {/* Steps */}
        <div style={{ padding: '18px 22px 0' }}>
          <StepIndicator current={step} />
        </div>

        {/* Content */}
        <div key={step} style={{ padding: '2px 22px 22px', animation: 'slideInRight .18s ease', minHeight: 280 }}>
          {step === 0 && <LlmStep />}
          {step === 1 && <VoiceStep />}
          {step === 2 && <HaStep />}
        </div>

        {/* Footer */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 22px', borderTop: `1px solid ${J.border}`, background: J.bg1 }}>
          <span style={{ fontSize: 11, color: J.textMuted }}>Step {step + 1} of {STEPS.length}</span>
          <div style={{ display: 'flex', gap: 8 }}>
            {step > 0 && (
              <button onClick={() => setStep(s => s - 1)}
                style={{ padding: '7px 16px', borderRadius: 7, border: `1px solid ${J.border}`, background: 'none', color: J.textSec, cursor: 'pointer', fontSize: 13, fontWeight: 500, transition: 'all .12s' }}
                onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = J.borderHover; (e.currentTarget as HTMLButtonElement).style.color = J.text; }}
                onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = J.border; (e.currentTarget as HTMLButtonElement).style.color = J.textSec; }}>
                ← Back
              </button>
            )}
            <button onClick={handleNext}
              style={{ padding: '7px 20px', borderRadius: 7, border: `1px solid ${J.amber}`, background: J.amber, color: J.bg0, cursor: 'pointer', fontSize: 13, fontWeight: 600, transition: 'all .12s' }}
              onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = J.amberBright; (e.currentTarget as HTMLButtonElement).style.borderColor = J.amberBright; }}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = J.amber; (e.currentTarget as HTMLButtonElement).style.borderColor = J.amber; }}>
              {isLast ? 'Finish setup' : 'Next →'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
