import { useEffect, useRef, useState } from 'react';
import { J, useJ } from '../screens/jarvis-shared';
import { buildApiHeaders, getSessionToken } from '../shared/api/client';

// Module-level so dismiss() can stop audio that was started in an async context
let _audio: HTMLAudioElement | null = null;
let _abort: AbortController | null = null;

function stopGreetingAudio() {
  _abort?.abort();
  _abort = null;
  if (_audio) {
    _audio.pause();
    _audio.src = '';
    _audio = null;
  }
  try { window.speechSynthesis?.cancel(); } catch { /* unavailable */ }
}

function localGreeting(): string {
  const h = new Date().getHours();
  const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const date = new Date().toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  let salutation: string;
  if (h >= 5 && h < 12)       salutation = 'Good morning, sir.';
  else if (h >= 12 && h < 17) salutation = 'Good afternoon, sir.';
  else if (h >= 17 && h < 22) salutation = 'Good evening, sir.';
  else                         salutation = 'Sir, working late again.';
  return `${salutation} It is ${time} on ${date}. J.A.R.V.I.S. standing by.`;
}

async function fetchGreeting(): Promise<string> {
  try {
    const res = await fetch('/greeting', { signal: AbortSignal.timeout(3000) });
    if (res.ok) {
      const data = await res.json() as { text?: string };
      if (data.text) return data.text;
    }
  } catch { /* offline — fall through */ }
  return localGreeting();
}

async function speak(text: string): Promise<void> {
  stopGreetingAudio();
  _abort = new AbortController();
  const signal = _abort.signal;

  // Server TTS (uses user's selected voice)
  try {
    const response = await fetch('/tts', {
      method: 'POST',
      headers: buildApiHeaders({ body: { text }, includeUser: getSessionToken() !== '' }),
      body: JSON.stringify({ text }),
      signal,
    });
    if (signal.aborted) return;
    if (response.ok) {
      const blob = await response.blob();
      if (signal.aborted) return;
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      _audio = audio;
      audio.onended = () => { URL.revokeObjectURL(url); if (_audio === audio) _audio = null; };
      audio.onerror = () => { URL.revokeObjectURL(url); if (_audio === audio) _audio = null; };
      await audio.play();
      return;
    }
  } catch { /* aborted or server TTS unavailable */ }

  if (signal.aborted) return;

  // Browser speech synthesis fallback — wait for voices to load before selecting
  if (!('speechSynthesis' in window)) return;
  try {
    window.speechSynthesis.cancel();
    const utt = new SpeechSynthesisUtterance(text);
    utt.rate = 0.88; utt.pitch = 0.80; utt.volume = 1;

    const pickVoice = () => {
      const voices = window.speechSynthesis.getVoices();
      return voices.find(v => /microsoft ryan|microsoft george|microsoft oliver/i.test(v.name))
          ?? voices.find(v => /google uk english male/i.test(v.name))
          ?? voices.find(v => v.lang === 'en-GB' && !/female|zira|hazel/i.test(v.name))
          ?? voices.find(v => v.lang === 'en-GB');
    };

    const trySpeak = () => {
      if (signal.aborted) return;
      const voice = pickVoice();
      if (voice) utt.voice = voice;
      window.speechSynthesis.speak(utt);
    };

    const voices = window.speechSynthesis.getVoices();
    if (voices.length > 0) {
      trySpeak();
    } else {
      // Voices not loaded yet — wait for them
      window.speechSynthesis.onvoiceschanged = () => {
        window.speechSynthesis.onvoiceschanged = null;
        trySpeak();
      };
    }
  } catch { /* speech blocked */ }
}

interface Props { onDismiss: () => void; }

export function GreetingOverlay({ onDismiss }: Props) {
  useJ();
  const [text, setText] = useState('');
  const [displayed, setDisplayed] = useState('');
  const [phase, setPhase] = useState<'loading' | 'typing' | 'done' | 'fading'>('loading');
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const typingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const spoken = useRef(false);

  useEffect(() => {
    fetchGreeting().then(t => { setText(t); setPhase('typing'); });
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (typingRef.current) clearInterval(typingRef.current);
    };
  }, []);

  useEffect(() => {
    if (phase !== 'typing' || !text) return;
    let i = 0;
    typingRef.current = setInterval(() => {
      i += 2;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) {
        if (typingRef.current) clearInterval(typingRef.current);
        setPhase('done');
      }
    }, 22);
    return () => { if (typingRef.current) clearInterval(typingRef.current); };
  }, [phase, text]);

  useEffect(() => {
    if (text && !spoken.current) {
      spoken.current = true;
      void speak(text);
    }
  }, [text]);

  useEffect(() => {
    if (phase !== 'done') return;
    timerRef.current = setTimeout(() => {
      setPhase('fading');
      timerRef.current = setTimeout(onDismiss, 600);
    }, 4000);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [phase, onDismiss]);

  const dismiss = () => {
    stopGreetingAudio();
    if (typingRef.current) clearInterval(typingRef.current);
    if (timerRef.current) clearTimeout(timerRef.current);
    setPhase('fading');
    timerRef.current = setTimeout(onDismiss, 400);
  };

  const dismissRef = useRef(dismiss);
  dismissRef.current = dismiss;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') dismissRef.current(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="JARVIS greeting — click or press Escape to dismiss"
      onClick={dismiss}
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: J.bg0 + 'fa',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        cursor: 'pointer',
        opacity: phase === 'fading' ? 0 : 1,
        transition: 'opacity 0.5s ease',
      }}
    >
      <div style={{ position: 'absolute', inset: 0, backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.03) 1px, transparent 1px)', backgroundSize: '28px 28px', pointerEvents: 'none' }} />
      <div style={{
        position: 'absolute', top: '40%', left: '50%', transform: 'translate(-50%,-50%)',
        width: 500, height: 500,
        background: 'radial-gradient(circle, rgba(224,154,26,0.09) 0%, transparent 65%)',
        pointerEvents: 'none',
        animation: 'jarvis-glow-pulse 4s ease-in-out infinite',
      }} />
      <div style={{ fontFamily: 'monospace', fontSize: 11, letterSpacing: '0.45em', color: 'rgba(224,154,26,0.5)', textTransform: 'uppercase', marginBottom: 32 }}>
        J.A.R.V.I.S.
      </div>
      <div style={{
        maxWidth: 560, padding: '0 32px',
        textAlign: 'center', fontSize: 22, fontWeight: 300,
        lineHeight: 1.55, color: J.text, letterSpacing: '0.02em', minHeight: 80,
      }}>
        {displayed}
        {phase === 'typing' && (
          <span style={{ display: 'inline-block', width: 2, height: '1em', background: '#e09a1a', marginLeft: 3, verticalAlign: 'text-bottom', animation: 'jarvis-cursor-blink 0.7s step-end infinite' }} />
        )}
      </div>
      <div style={{ marginTop: 40, width: 120, height: 1, background: 'linear-gradient(90deg, transparent, rgba(224,154,26,0.45), transparent)' }} />
      <div style={{ marginTop: 24, fontSize: 11, color: J.textMuted, letterSpacing: '0.15em', opacity: phase === 'loading' ? 0 : 1, transition: 'opacity 1s' }}>
        TAP ANYWHERE TO CONTINUE
      </div>
      <style>{`
        @keyframes jarvis-cursor-blink { 0%,100%{opacity:1} 50%{opacity:0} }
        @keyframes jarvis-glow-pulse { 0%,100%{opacity:.7;transform:translate(-50%,-50%) scale(1)} 50%{opacity:1;transform:translate(-50%,-50%) scale(1.08)} }
      `}</style>
    </div>
  );
}
