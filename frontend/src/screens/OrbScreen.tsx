import { useState, useRef, useEffect } from 'react';
import { J, useJ, stripMarkdown, StatusBadge, IconMic, IconSettings, IconChat, IconVolume, MarkdownText, showToast } from './jarvis-shared';
import { streamChatMessage, transcribeAudio, synthesizeSpeech, SttError, getSystemMetrics } from '../shared/api/chat';

export type HealthTier = 'good' | 'warn' | 'critical';

export function metricsToHealthTier(metrics: { cpu_percent: number; ram_percent: number; disk_percent: number }): HealthTier {
  if (metrics.cpu_percent > 90 || metrics.ram_percent > 90 || metrics.disk_percent > 90) return 'critical';
  if (metrics.cpu_percent > 75 || metrics.ram_percent > 75 || metrics.disk_percent > 75) return 'warn';
  return 'good';
}

const ORB_STATES: Record<string, { label: string; sub: string; speedMult: number; glowMult: number }> = {
  idle:      { label: 'Ready',      sub: 'Tap the mic to speak',       speedMult: 1,   glowMult: 1   },
  listening: { label: 'Listening',  sub: 'Speak now — tap to send',    speedMult: 1.9, glowMult: 1.6 },
  thinking:  { label: 'Processing', sub: 'Analyzing your request',     speedMult: 2.8, glowMult: 1.3 },
  speaking:  { label: 'Speaking',   sub: 'J.A.R.V.I.S. responding',   speedMult: 1.5, glowMult: 1.8 },
  error:     { label: 'Error',      sub: 'Tap mic to try again',       speedMult: 0.4, glowMult: 0.6 },
};

const RING_DEFS = [
  { axisAngle:   0, flatness: 0.12, speed:  0.50, alpha: 0.85 },
  { axisAngle:  58, flatness: 0.24, speed: -0.38, alpha: 0.78 },
  { axisAngle: 112, flatness: 0.16, speed:  0.62, alpha: 0.82 },
  { axisAngle:  32, flatness: 0.32, speed: -0.45, alpha: 0.70 },
  { axisAngle:  78, flatness: 0.09, speed:  0.30, alpha: 0.65 },
  { axisAngle: 148, flatness: 0.38, speed:  0.42, alpha: 0.72 },
];

function pointOnRing(r: typeof RING_DEFS[0], theta: number, R: number, cx: number, cy: number) {
  const a = r.axisAngle * Math.PI / 180;
  return {
    x: cx + R * Math.cos(theta) * Math.cos(a) - R * r.flatness * Math.sin(theta) * Math.sin(a),
    y: cy + R * Math.cos(theta) * Math.sin(a) + R * r.flatness * Math.sin(theta) * Math.cos(a),
  };
}

function OrbCanvas({ orbState, muted, size, healthTier }: { orbState: string; muted: boolean; size: number; healthTier?: HealthTier }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef   = useRef<number>(0);
  const stateRef  = useRef(orbState);
  const mutedRef  = useRef(muted);
  const healthRef = useRef(healthTier ?? 'good');
  const tRef      = useRef(0);

  useEffect(() => { stateRef.current = orbState; }, [orbState]);
  useEffect(() => { mutedRef.current = muted; }, [muted]);
  useEffect(() => { healthRef.current = healthTier ?? 'good'; }, [healthTier]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;
    const S = size;
    const dpr = window.devicePixelRatio || 1;
    canvas.width  = S * dpr;
    canvas.height = S * dpr;
    canvas.style.width  = S + 'px';
    canvas.style.height = S + 'px';
    ctx.scale(dpr, dpr);
    const cx = S / 2, cy = S / 2, R = S * 0.37;

    const ringParticles = RING_DEFS.map(r => {
      const count = 2 + Math.floor(Math.random() * 2);
      return Array.from({ length: count }, (_, i) => ({
        theta: (i / count) * Math.PI * 2 + Math.random(),
        trail: [] as Array<{ x: number; y: number }>,
      }));
    });

    const sparks: Array<{ x: number; y: number; vx: number; vy: number; life: number; decay: number; sz: number }> = [];

    function spawnSpark(x: number, y: number, intense: boolean) {
      if (sparks.length > 55) return;
      const n = intense ? 3 : 1;
      for (let k = 0; k < n; k++) {
        const ang = Math.random() * Math.PI * 2;
        const spd = 0.4 + Math.random() * (intense ? 2.2 : 1.2);
        sparks.push({ x, y, vx: Math.cos(ang) * spd, vy: Math.sin(ang) * spd, life: 1, decay: 0.012 + Math.random() * 0.025, sz: 0.5 + Math.random() * 1.4 });
      }
    }

    function draw() {
      const st  = stateRef.current;
      const cfg = ORB_STATES[st] || ORB_STATES.idle;
      tRef.current += 0.016 * cfg.speedMult;
      const t = tRef.current;
      const gm = cfg.glowMult;

      const tier = healthRef.current;
      const glowR = tier === 'critical' ? 224 : tier === 'warn' ? 232 : 232;
      const glowG = tier === 'critical' ? 85  : tier === 'warn' ? 148 : 155;
      const glowB = tier === 'critical' ? 85  : tier === 'warn' ? 58  : 28;

      ctx.clearRect(0, 0, S, S);

      const bgGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.35);
      bgGrad.addColorStop(0,   `rgba(${glowR},${glowG},${glowB},${0.09 * gm})`);
      bgGrad.addColorStop(0.5, `rgba(${glowR},${glowG},${glowB},${0.04 * gm})`);
      bgGrad.addColorStop(1,   'transparent');
      ctx.fillStyle = bgGrad;
      ctx.beginPath(); ctx.arc(cx, cy, R * 1.35, 0, Math.PI * 2); ctx.fill();

      ctx.save();
      ctx.strokeStyle = `rgba(200,130,20,${0.14 * gm})`;
      ctx.lineWidth = 0.6; ctx.shadowBlur = 10; ctx.shadowColor = `rgba(232,155,28,0.25)`;
      ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke();
      ctx.restore();

      RING_DEFS.forEach((r, ri) => {
        ctx.save();
        ctx.translate(cx, cy); ctx.rotate(r.axisAngle * Math.PI / 180);
        ctx.shadowBlur = 5 * gm; ctx.shadowColor = `rgba(232,155,28,${r.alpha * 0.55})`;
        ctx.strokeStyle = `rgba(220,145,25,${r.alpha * 0.55})`; ctx.lineWidth = 0.8;
        ctx.beginPath(); ctx.ellipse(0, 0, R, R * r.flatness, 0, 0, Math.PI * 2); ctx.stroke();
        ctx.restore();

        ringParticles[ri].forEach(p => {
          p.theta += 0.009 * r.speed * cfg.speedMult;
          const pt = pointOnRing(r, p.theta, R, cx, cy);
          p.trail.push({ ...pt });
          if (p.trail.length > 22) p.trail.shift();
          if (p.trail.length > 2) {
            ctx.save();
            for (let k = 1; k < p.trail.length; k++) {
              const prog = k / p.trail.length;
              ctx.globalAlpha = prog * 0.65;
              ctx.strokeStyle = `rgba(245,195,60,${prog * 0.9})`; ctx.lineWidth = prog * 2.2;
              ctx.shadowBlur = 3; ctx.shadowColor = 'rgba(245,195,60,0.5)';
              ctx.beginPath(); ctx.moveTo(p.trail[k-1].x, p.trail[k-1].y); ctx.lineTo(pt.x, pt.y); ctx.stroke();
            }
            ctx.restore();
          }
          ctx.save();
          ctx.shadowBlur = 14 * gm; ctx.shadowColor = 'rgba(255,225,100,0.95)';
          ctx.fillStyle = '#fffbe8';
          ctx.beginPath(); ctx.arc(pt.x, pt.y, 2.4, 0, Math.PI * 2); ctx.fill();
          ctx.restore();
          if (Math.random() < 0.045 * cfg.speedMult) spawnSpark(pt.x, pt.y, st === 'thinking');
        });
      });

      for (let i = sparks.length - 1; i >= 0; i--) {
        const s = sparks[i];
        s.x += s.vx; s.y += s.vy; s.vx *= 0.968; s.vy *= 0.968; s.life -= s.decay;
        if (s.life <= 0) { sparks.splice(i, 1); continue; }
        ctx.save(); ctx.globalAlpha = s.life * 0.75;
        ctx.shadowBlur = 5; ctx.shadowColor = 'rgba(245,175,35,0.8)';
        ctx.fillStyle = `rgba(255,210,70,${s.life})`;
        ctx.beginPath(); ctx.arc(s.x, s.y, s.sz * s.life, 0, Math.PI * 2); ctx.fill(); ctx.restore();
      }

      const coreR = st === 'speaking'  ? 11 + Math.sin(t * 9) * 3.5
                  : st === 'listening' ? 10 + Math.sin(t * 6) * 2.5
                  : st === 'thinking'  ?  9 + Math.sin(t * 14) * 1.5
                  : 9;

      const haloGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR * 5);
      haloGrad.addColorStop(0,    `rgba(255,240,170,${0.38 * gm})`);
      haloGrad.addColorStop(0.35, `rgba(232,155,28,${0.20 * gm})`);
      haloGrad.addColorStop(1,    'transparent');
      ctx.fillStyle = haloGrad;
      ctx.beginPath(); ctx.arc(cx, cy, coreR * 5, 0, Math.PI * 2); ctx.fill();

      ctx.save(); ctx.shadowBlur = 28 * gm; ctx.shadowColor = 'rgba(255,215,80,0.95)';
      const coreGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR);
      coreGrad.addColorStop(0,   '#ffffff'); coreGrad.addColorStop(0.3, '#fff5b0');
      coreGrad.addColorStop(0.7, '#f5c030'); coreGrad.addColorStop(1,   'rgba(232,140,20,0)');
      ctx.fillStyle = coreGrad;
      ctx.beginPath(); ctx.arc(cx, cy, coreR, 0, Math.PI * 2); ctx.fill(); ctx.restore();

      ctx.save(); ctx.shadowBlur = 18; ctx.shadowColor = 'rgba(255,255,220,1)'; ctx.fillStyle = '#ffffff';
      ctx.beginPath(); ctx.arc(cx, cy, coreR * 0.3, 0, Math.PI * 2); ctx.fill(); ctx.restore();

      if (mutedRef.current) {
        ctx.save(); ctx.strokeStyle = 'rgba(224,85,85,0.75)'; ctx.lineWidth = 1.5;
        ctx.shadowBlur = 8; ctx.shadowColor = 'rgba(224,85,85,0.5)';
        ctx.beginPath(); ctx.arc(cx, cy, coreR * 1.8, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
      }

      animRef.current = requestAnimationFrame(draw);
    }

    animRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animRef.current);
  }, [size]);

  return <canvas ref={canvasRef} style={{ display: 'block', width: size + 'px', height: size + 'px' }} />;
}

function WaveBar({ i, color }: { i: number; color: string }) {
  const heights = [.35, .7, 1, .55, .9, .42, .75, .38, .65, .95, .5, .8];
  return (
    <div style={{ width: 2.5, borderRadius: 3, background: color, height: `${heights[i % heights.length] * 24}px`, animation: `waveBar ${.38 + (i % 4) * .14}s ease-in-out infinite`, animationDelay: `${i * .065}s`, opacity: .8 }} />
  );
}

function remoteStateToOrbState(state: string) {
  if (state === 'recording') return 'listening';
  if (state === 'processing') return 'thinking';
  if (state === 'speaking') return 'speaking';
  return 'idle';
}

type Exchange = { you: string; jarvis: string };

export function OrbScreen({ onNavigate, liveState = 'idle' }: { onNavigate: (screen: string) => void; liveState?: string }) {
  useJ();
  const [orbState, setOrbState]     = useState('idle');
  const [transcript, setTranscript] = useState('');
  const [response, setResponse]     = useState('');
  const [errorMsg, setErrorMsg]     = useState('');
  const [orbSize, setOrbSize]       = useState(260);
  const [hasMic, setHasMic]         = useState(true);
  const [muteTTS, setMuteTTS]       = useState(false);
  const [history, setHistory]       = useState<Exchange[]>([]);
  const [healthTier, setHealthTier] = useState<HealthTier>('good');

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef        = useRef<Blob[]>([]);
  const sessionRef       = useRef<string | null>(null);
  const audioRef         = useRef<HTMLAudioElement | null>(null);
  const muteTTSRef       = useRef(muteTTS);
  useEffect(() => { muteTTSRef.current = muteTTS; }, [muteTTS]);

  useEffect(() => {
    const update = () => setOrbSize(window.innerWidth <= 640 ? 200 : 260);
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  useEffect(() => {
    const fetchHealth = () => {
      getSystemMetrics()
        .then(m => setHealthTier(metricsToHealthTier({ cpu_percent: m.cpu.pct, ram_percent: m.ram.pct, disk_percent: m.disk.pct })))
        .catch(() => {});
    };
    fetchHealth();
    const interval = window.setInterval(fetchHealth, 30000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.code !== 'Space' || e.target !== document.body) return;
      e.preventDefault();
      handleMicToggle();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  });

  const stopAudio = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
  };

  const processAudio = async (blob: Blob) => {
    setOrbState('thinking');
    try {
      let sttResult: { text?: string };
      try {
        sttResult = await transcribeAudio(blob, 'orb');
      } catch (sttErr) {
        if (sttErr instanceof SttError) {
          const toastMsg =
            sttErr.kind === 'network' ? 'Voice input unavailable. Check your connection.' :
            sttErr.kind === 'rate_limit' ? 'Too many requests. Wait a moment and try again.' :
            'Transcription failed. Tap mic to retry.';
          showToast(toastMsg, 'error', 4000);
        } else {
          showToast('Transcription failed. Tap mic to retry.', 'error', 4000);
        }
        setErrorMsg('Transcription failed. Tap mic to retry.');
        setOrbState('error');
        return;
      }

      const text = sttResult.text?.trim();
      if (!text) {
        setErrorMsg('Could not understand audio. Try again.');
        setOrbState('error');
        return;
      }
      setTranscript(text);

      let fullReply = '';
      for await (const event of streamChatMessage(text, 'voice', 'orb', sessionRef.current)) {
        if (event.type === 'token') {
          fullReply += event.token;
          setResponse(fullReply + '▋');
        } else if (event.type === 'done') {
          fullReply = event.reply || fullReply;
          if (event.session_id) sessionRef.current = event.session_id;
        }
      }
      setResponse(fullReply);
      if (text && fullReply) {
        setHistory(h => [...h.slice(-4), { you: text, jarvis: fullReply }]);
      }

      if (fullReply && !muteTTSRef.current) {
        setOrbState('speaking');
        try {
          const audioBlob = await synthesizeSpeech(stripMarkdown(fullReply));
          const url = URL.createObjectURL(audioBlob);
          const audio = new Audio(url);
          audioRef.current = audio;
          audio.onended = () => { URL.revokeObjectURL(url); audioRef.current = null; setOrbState('idle'); };
          audio.onerror  = () => { URL.revokeObjectURL(url); audioRef.current = null; setOrbState('idle'); };
          await audio.play();
        } catch {
          setOrbState('idle');
        }
      } else {
        setOrbState('idle');
      }
    } catch (err) {
      setErrorMsg((err as Error).message || 'Processing failed.');
      setOrbState('error');
    }
  };

  const startRecording = async () => {
    setErrorMsg('');
    setTranscript('');
    setResponse('');
    stopAudio();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setHasMic(true);
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      recorder.onstop = () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        void processAudio(blob);
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setOrbState('listening');
    } catch {
      setHasMic(false);
      setErrorMsg('Microphone access denied. Check browser permissions.');
      setOrbState('error');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
  };

  const handleMicToggle = () => {
    if (orbState === 'listening') {
      stopRecording();
    } else if (orbState === 'speaking') {
      stopAudio();
      setOrbState('idle');
    } else {
      void startRecording();
    }
  };

  const remoteOrbState = remoteStateToOrbState(liveState);
  const displayState = orbState === 'error'
    ? 'error'
    : orbState === 'listening'
      ? 'listening'
      : remoteOrbState !== 'idle'
        ? remoteOrbState
        : orbState;
  const cfg = ORB_STATES[displayState] || ORB_STATES.idle;
  const micActive = displayState === 'listening';

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: J.bg0, position: 'relative', overflow: 'hidden', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 50, borderBottom: `1px solid ${J.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 20px', zIndex: 2, background: J.bg1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          <span style={{ fontSize: 14, fontWeight: 500, color: J.text }}>Voice</span>
          <StatusBadge status={displayState === 'error' ? 'error' : displayState === 'idle' ? 'local' : 'active'} size="xs" />
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button onClick={() => onNavigate('chat')} className="j-btn"
            style={{ background: J.bg2, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 7, padding: '5px 11px', fontSize: 12 }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = J.borderHover; e.currentTarget.style.color = J.text; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = J.border; e.currentTarget.style.color = J.textSec; }}>
            <IconChat size={13} /> Chat
          </button>
          <button onClick={() => onNavigate('settings')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: J.textMuted, padding: 5, display: 'flex' }}><IconSettings size={14} /></button>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 20, zIndex: 1, padding: '60px 24px 100px', width: '100%', maxWidth: 540 }}>
        <div style={{ position: 'relative', cursor: orbState === 'idle' || orbState === 'error' ? 'pointer' : 'default' }}
          onClick={() => { if (orbState === 'idle' || orbState === 'error') void startRecording(); }}>
          <OrbCanvas orbState={displayState} muted={!hasMic} size={orbSize} healthTier={healthTier} />
          {displayState === 'speaking' && (
            <div style={{ position: 'absolute', bottom: 20, left: '50%', transform: 'translateX(-50%)', display: 'flex', gap: 3, alignItems: 'flex-end' }}>
              {Array.from({ length: 9 }, (_, i) => <WaveBar key={i} i={i} color={J.amber} />)}
            </div>
          )}
          {displayState === 'listening' && (
            <div style={{ position: 'absolute', bottom: 20, left: '50%', transform: 'translateX(-50%)', display: 'flex', gap: 3, alignItems: 'flex-end' }}>
              {Array.from({ length: 9 }, (_, i) => <WaveBar key={i} i={i} color={J.success} />)}
            </div>
          )}
        </div>

        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 18, fontWeight: 500, color: J.text, marginBottom: 3 }}>{cfg.label}</div>
          <div style={{ fontSize: 13, color: errorMsg ? J.error : J.textMuted }}>{errorMsg || cfg.sub}</div>
        </div>

        {transcript && (
          <div style={{ width: '100%', padding: '12px 16px', background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 11, animation: 'fadeIn .3s ease' }}>
            <div style={{ fontSize: 10, color: J.textMuted, marginBottom: 4, letterSpacing: '0.05em', textTransform: 'uppercase', fontWeight: 600 }}>You</div>
            <div style={{ fontSize: 14, color: J.text }}>{transcript}</div>
          </div>
        )}

        {response && (
          <div style={{ width: '100%', padding: '12px 16px', background: J.bg2, border: `1px solid ${J.borderAccent}`, borderRadius: 11, animation: 'fadeIn .3s ease' }}>
            <div style={{ fontSize: 10, color: J.amber, marginBottom: 4, letterSpacing: '0.05em', textTransform: 'uppercase', fontWeight: 600 }}>J.A.R.V.I.S.</div>
            <MarkdownText text={response} style={{ fontSize: 14, color: J.text, lineHeight: 1.65 }} />
          </div>
        )}

        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <button onClick={() => onNavigate('settings')} className="j-btn" title="Settings" aria-label="Settings"
            style={{ width: 46, height: 46, borderRadius: '50%', background: J.bg2, border: `1px solid ${J.border}`, color: J.textSec, justifyContent: 'center' }}>
            <IconSettings size={15} />
          </button>
          <button onClick={handleMicToggle} className="j-btn"
            aria-label={micActive ? 'Stop recording' : 'Start recording'} aria-pressed={micActive}
            style={{ width: 68, height: 68, borderRadius: '50%', background: micActive ? 'rgba(61,186,132,0.15)' : J.amberDim, border: `1.5px solid ${micActive ? J.success : J.borderAccent}`, color: micActive ? J.success : J.amber, justifyContent: 'center', transition: 'all .25s', boxShadow: micActive ? `0 0 20px rgba(61,186,132,0.3)` : 'none' }}>
            <IconMic size={24} />
          </button>
          <button onClick={() => setMuteTTS(v => !v)} className="j-btn"
            title={muteTTS ? 'Voice muted — click to unmute' : 'Mute voice responses'}
            aria-label={muteTTS ? 'Unmute voice' : 'Mute voice'} aria-pressed={muteTTS}
            style={{ width: 46, height: 46, borderRadius: '50%', background: muteTTS ? J.errorDim : J.bg2, border: `1px solid ${muteTTS ? J.error : J.border}`, color: muteTTS ? J.error : J.textSec, justifyContent: 'center', transition: 'all .2s' }}>
            <IconVolume size={15} />
          </button>
        </div>
        <p style={{ fontSize: 11, color: J.textMuted }}>
          {hasMic ? 'Space · tap orb to start · tap again to send' : 'Microphone unavailable'}{muteTTS ? ' · voice muted' : ''}
        </p>
      </div>

      {history.length > 0 && (
        <div style={{ position: 'absolute', top: 58, right: 0, width: 240, maxHeight: 'calc(100% - 120px)', overflowY: 'auto', padding: '10px 12px', zIndex: 2, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {history.slice(-3).map((ex, i) => (
            <div key={i} style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 9, padding: '8px 11px', fontSize: 11, opacity: 0.7 + i * 0.1 }}>
              <div style={{ color: J.textMuted, marginBottom: 3 }}>You: <span style={{ color: J.textSec }}>{ex.you}</span></div>
              <div style={{ color: J.amber, opacity: 0.85 }}>J: <span style={{ color: J.text }}>{ex.jarvis.slice(0, 90)}{ex.jarvis.length > 90 ? '…' : ''}</span></div>
            </div>
          ))}
        </div>
      )}

      <div style={{ position: 'absolute', bottom: 20, left: '50%', transform: 'translateX(-50%)', display: 'flex', gap: 7, zIndex: 2 }}>
        {[
          { l: 'STT', s: hasMic ? 'online' : 'error' },
          { l: 'Chat', s: 'active' },
        ].map(item => (
          <div key={item.l} style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 8, padding: '5px 11px', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 11, color: J.textMuted }}>{item.l}</span>
            <StatusBadge status={item.s} size="xs" />
          </div>
        ))}
      </div>
    </div>
  );
}
