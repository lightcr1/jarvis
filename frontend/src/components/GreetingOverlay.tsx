import { useEffect, useRef, useState } from 'react';
import { J } from '../screens/jarvis-shared';

// Greets every time the app opens — no suppression by design.
// Fetches /greeting for a time-aware text; falls back to local time-based text if offline.

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
  } catch { /* offline or not local — fall through */ }
  return localGreeting();
}

function speak(text: string): void {
  if (!('speechSynthesis' in window)) return;
  try {
    window.speechSynthesis.cancel();
    const utt = new SpeechSynthesisUtterance(text);
    utt.rate  = 0.88;   // deliberate, measured pace — like the original
    utt.pitch = 0.80;   // slightly lower, more authoritative
    utt.volume = 1;

    const voices = window.speechSynthesis.getVoices();

    // Priority order — closest to original JARVIS (British, male, neural)
    const preferred =
      // 1. Microsoft neural British male (Edge / Windows)
      voices.find(v => /microsoft ryan|microsoft george|microsoft oliver/i.test(v.name)) ??
      // 2. Google UK English Male (Chrome on desktop)
      voices.find(v => /google uk english male/i.test(v.name)) ??
      // 3. Any en-GB male
      voices.find(v => v.lang === 'en-GB' && !/female|zira|hazel/i.test(v.name)) ??
      // 4. Any en-GB voice
      voices.find(v => v.lang === 'en-GB') ??
      // 5. Any English male (not explicitly female)
      voices.find(v => v.lang.startsWith('en') && !/female|zira|hazel|karen|moira|tessa/i.test(v.name));

    if (preferred) utt.voice = preferred;
    window.speechSynthesis.speak(utt);
  } catch { /* speech blocked by browser policy */ }
}

interface Props {
  onDismiss: () => void;
}

export function GreetingOverlay({ onDismiss }: Props) {
  const [text, setText] = useState('');
  const [displayed, setDisplayed] = useState('');
  const [phase, setPhase] = useState<'loading' | 'typing' | 'done' | 'fading'>('loading');
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const typingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const spoken = useRef(false);

  // Fetch greeting text on mount
  useEffect(() => {
    fetchGreeting().then(t => {
      setText(t);
      setPhase('typing');
    });
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (typingRef.current) clearInterval(typingRef.current);
      window.speechSynthesis?.cancel();
    };
  }, []);

  // Typed-text animation
  useEffect(() => {
    if (phase !== 'typing' || !text) return;
    let i = 0;
    typingRef.current = setInterval(() => {
      i += 2; // 2 chars per tick for snappy feel
      setDisplayed(text.slice(0, i));
      if (i >= text.length) {
        if (typingRef.current) clearInterval(typingRef.current);
        setPhase('done');
      }
    }, 22);
    return () => { if (typingRef.current) clearInterval(typingRef.current); };
  }, [phase, text]);

  // Speak once text is set
  useEffect(() => {
    if (text && !spoken.current) {
      spoken.current = true;
      // Short delay so voices are loaded
      timerRef.current = setTimeout(() => speak(text), 300);
    }
  }, [text]);

  // Auto-dismiss 4s after typing finishes
  useEffect(() => {
    if (phase !== 'done') return;
    timerRef.current = setTimeout(() => {
      setPhase('fading');
      timerRef.current = setTimeout(onDismiss, 600);
    }, 4000);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [phase, onDismiss]);

  const dismiss = () => {
    window.speechSynthesis?.cancel();
    if (typingRef.current) clearInterval(typingRef.current);
    if (timerRef.current) clearTimeout(timerRef.current);
    setPhase('fading');
    timerRef.current = setTimeout(onDismiss, 400);
  };

  return (
    <div
      onClick={dismiss}
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: 'rgba(10,10,15,0.97)',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        cursor: 'pointer',
        opacity: phase === 'fading' ? 0 : 1,
        transition: 'opacity 0.5s ease',
      }}
    >
      {/* Ambient glow */}
      <div style={{
        position: 'absolute', top: '40%', left: '50%', transform: 'translate(-50%,-50%)',
        width: 420, height: 420,
        background: 'radial-gradient(circle, rgba(0,212,255,0.06) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      {/* J.A.R.V.I.S. logo */}
      <div style={{
        fontFamily: 'monospace', fontSize: 11, letterSpacing: '0.45em',
        color: 'rgba(0,212,255,0.45)', textTransform: 'uppercase',
        marginBottom: 32,
      }}>
        J.A.R.V.I.S.
      </div>

      {/* Greeting text */}
      <div style={{
        maxWidth: 560, padding: '0 32px',
        textAlign: 'center',
        fontSize: 22, fontWeight: 300,
        lineHeight: 1.55,
        color: '#e8e8e8',
        letterSpacing: '0.02em',
        minHeight: 80,
      }}>
        {displayed}
        {phase === 'typing' && (
          <span style={{
            display: 'inline-block', width: 2, height: '1em',
            background: '#00d4ff', marginLeft: 3, verticalAlign: 'text-bottom',
            animation: 'jarvis-cursor-blink 0.7s step-end infinite',
          }} />
        )}
      </div>

      {/* Scanline decoration */}
      <div style={{
        marginTop: 40,
        width: 120, height: 1,
        background: 'linear-gradient(90deg, transparent, rgba(0,212,255,0.4), transparent)',
      }} />

      {/* Dismiss hint */}
      <div style={{
        marginTop: 24, fontSize: 11,
        color: 'rgba(255,255,255,0.18)', letterSpacing: '0.15em',
        opacity: phase === 'loading' ? 0 : 1,
        transition: 'opacity 1s',
      }}>
        TAP ANYWHERE TO CONTINUE
      </div>

      <style>{`
        @keyframes jarvis-cursor-blink {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0; }
        }
      `}</style>
    </div>
  );
}
