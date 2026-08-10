import { ReactNode, useEffect, useRef, useState } from 'react';
import { J, useJ, IconX, IconCalendar, IconActivity, IconJarvisMark } from './jarvis-shared';
import { useJarvisLiveStatus } from '../shared/api/status';
import { fetchWeather, WeatherResult } from '../shared/api/weather';
import { fetchCalendarEvents, CalendarEvent } from '../shared/api/calendar';
import { fetchHomeAssistantOverview, HomeAssistantOverview } from '../shared/api/homeAssistant';
import { synthesizeSpeech } from '../shared/api/chat';
import type { JarvisAlert } from '../shared/api/alerts';

const SPEAKABLE_ALERT_LEVELS = new Set(['warning', 'critical']);

// Ambient Display has no listening/thinking/speaking state machine like OrbScreen —
// it's a passive kiosk display, so the only gate is "not already mid-speech."
export function pickAmbientAlertToSpeak(alerts: JarvisAlert[], alreadySpoken: Set<string>): JarvisAlert | null {
  return alerts.find(a => SPEAKABLE_ALERT_LEVELS.has(a.level) && !alreadySpoken.has(a.id)) ?? null;
}

const WEATHER_REFRESH_MS = 15 * 60 * 1000;
const CALENDAR_REFRESH_MS = 5 * 60 * 1000;
const OVERVIEW_REFRESH_MS = 60 * 1000;

function fmtClock(d: Date): string {
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function fmtDate(d: Date): string {
  return d.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' });
}

function fmtEventTime(ts: number): string {
  const d = new Date(ts * 1000);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (sameDay) return `Today · ${time}`;
  return `${d.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' })} · ${time}`;
}

function Tile({ label, children, J }: { label: string; children: ReactNode; J: ReturnType<typeof useJ> }) {
  return (
    <div style={{
      background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 16,
      padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 10, minHeight: 140,
    }}>
      <div style={{ fontSize: 13, color: J.textMuted, textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600 }}>{label}</div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>{children}</div>
    </div>
  );
}

export function AmbientDisplayScreen({ onExit, alerts = [] }: { onExit: () => void; alerts?: JarvisAlert[] }) {
  const J = useJ();
  const liveStatus = useJarvisLiveStatus();
  const [now, setNow] = useState(new Date());
  const [weather, setWeather] = useState<WeatherResult | null>(null);
  const [weatherError, setWeatherError] = useState('');
  const [nextEvent, setNextEvent] = useState<CalendarEvent | null>(null);
  const [overview, setOverview] = useState<HomeAssistantOverview | null>(null);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const spokenAlertIdsRef = useRef<Set<string>>(new Set());
  const isSpeakingRef = useRef(false);

  useEffect(() => {
    const tick = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(tick);
  }, []);

  // Speaks unprompted, the way a real ambient JARVIS presence in a room would —
  // there's no mic/mute UI here since this screen is meant to run unattended.
  useEffect(() => {
    if (isSpeakingRef.current) return;
    const next = pickAmbientAlertToSpeak(alerts, spokenAlertIdsRef.current);
    if (!next) return;
    spokenAlertIdsRef.current.add(next.id);
    isSpeakingRef.current = true;
    (async () => {
      try {
        const audioBlob = await synthesizeSpeech(`Sir, ${next.message}`);
        const url = URL.createObjectURL(audioBlob);
        await new Promise<void>((resolve) => {
          const audio = new Audio(url);
          audioRef.current = audio;
          audio.onended = () => { URL.revokeObjectURL(url); audioRef.current = null; resolve(); };
          audio.onerror = () => { URL.revokeObjectURL(url); audioRef.current = null; resolve(); };
          audio.play().catch(() => resolve());
        });
      } catch {
        // TTS synthesis failed — nothing to play, just clean up below.
      } finally {
        isSpeakingRef.current = false;
      }
    })();
  }, [alerts]);

  useEffect(() => {
    return () => {
      if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      fetchWeather()
        .then(res => { if (!cancelled) { setWeather(res.weather); setWeatherError(''); } })
        .catch((err: Error) => { if (!cancelled) { setWeather(null); setWeatherError(err.message || 'Weather unavailable'); } });
    };
    load();
    const interval = window.setInterval(load, WEATHER_REFRESH_MS);
    return () => { cancelled = true; window.clearInterval(interval); };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      const start = Math.floor(new Date(new Date().setHours(0, 0, 0, 0)).getTime() / 1000);
      const end = start + 2 * 24 * 60 * 60;
      fetchCalendarEvents(start, end)
        .then(res => {
          if (cancelled) return;
          const nowSec = Date.now() / 1000;
          const upcoming = (res.events || [])
            .filter(e => e.end >= nowSec)
            .sort((a, b) => a.start - b.start);
          setNextEvent(upcoming[0] || null);
        })
        .catch(() => { if (!cancelled) setNextEvent(null); });
    };
    load();
    const interval = window.setInterval(load, CALENDAR_REFRESH_MS);
    return () => { cancelled = true; window.clearInterval(interval); };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      fetchHomeAssistantOverview()
        .then(res => { if (!cancelled) setOverview(res); })
        .catch(() => { if (!cancelled) setOverview(null); });
    };
    load();
    const interval = window.setInterval(load, OVERVIEW_REFRESH_MS);
    return () => { cancelled = true; window.clearInterval(interval); };
  }, []);

  return (
    <div style={{
      position: 'fixed', inset: 0, background: J.bg0, color: J.text,
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      padding: '5vh 6vw', overflow: 'hidden', zIndex: 1000,
    }}>
      <button
        onClick={onExit}
        aria-label="Exit ambient display"
        title="Exit ambient display"
        style={{
          position: 'absolute', top: 18, right: 18, width: 38, height: 38, borderRadius: 10,
          background: 'transparent', border: `1px solid ${J.border}`, color: J.textMuted,
          cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
          opacity: 0.4, transition: 'opacity .15s, color .15s, border-color .15s',
        }}
        onMouseEnter={e => { e.currentTarget.style.opacity = '1'; e.currentTarget.style.color = J.amber; e.currentTarget.style.borderColor = J.borderAccent; }}
        onMouseLeave={e => { e.currentTarget.style.opacity = '0.4'; e.currentTarget.style.color = J.textMuted; e.currentTarget.style.borderColor = J.border; }}
      >
        <IconX size={16} />
      </button>

      <div style={{
        position: 'absolute', bottom: 22, left: 24, display: 'flex', alignItems: 'center', gap: 8,
        color: J.amber, opacity: 0.4,
      }}>
        <IconJarvisMark size={20} />
        <span style={{ fontSize: 12, fontWeight: 600, letterSpacing: '0.14em', color: J.textMuted, textTransform: 'uppercase' }}>J.A.R.V.I.S.</span>
      </div>

      <div style={{ textAlign: 'center', marginBottom: '6vh' }}>
        <div style={{ fontSize: 'clamp(64px, 14vw, 148px)', fontWeight: 700, lineHeight: 1, letterSpacing: '-0.02em', color: J.text, fontVariantNumeric: 'tabular-nums' }}>
          {fmtClock(now)}
        </div>
        <div style={{ fontSize: 'clamp(16px, 2.2vw, 24px)', color: J.textSec, marginTop: 12, fontWeight: 500 }}>
          {fmtDate(now)}
        </div>
      </div>

      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 18,
        width: '100%', maxWidth: 1100,
      }}>
        <Tile label="Weather" J={J}>
          {weather ? (
            <div>
              <div style={{ fontSize: 44, fontWeight: 700, color: J.amber }}>
                {weather.temp !== null ? `${Math.round(weather.temp)}°C` : '—'}
              </div>
              <div style={{ fontSize: 15, color: J.textSec, marginTop: 4, textTransform: 'capitalize' }}>
                {weather.condition} · {weather.city}
              </div>
              {(weather.high !== null || weather.low !== null) && (
                <div style={{ fontSize: 13, color: J.textMuted, marginTop: 6 }}>
                  H {weather.high !== null ? `${Math.round(weather.high)}°` : '—'} · L {weather.low !== null ? `${Math.round(weather.low)}°` : '—'}
                </div>
              )}
            </div>
          ) : (
            <div style={{ fontSize: 14, color: J.textMuted }}>{weatherError || 'Loading…'}</div>
          )}
        </Tile>

        <Tile label="Next Event" J={J}>
          {nextEvent ? (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <span style={{ color: J.amber, display: 'flex' }}><IconCalendar size={16} /></span>
                <div style={{ fontSize: 20, fontWeight: 600, color: J.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{nextEvent.title}</div>
              </div>
              <div style={{ fontSize: 14, color: J.textSec }}>{fmtEventTime(nextEvent.start)}</div>
              {nextEvent.location && <div style={{ fontSize: 12, color: J.textMuted, marginTop: 4 }}>{nextEvent.location}</div>}
            </div>
          ) : (
            <div style={{ fontSize: 14, color: J.textMuted }}>Nothing scheduled</div>
          )}
        </Tile>

        <Tile label="System" J={J}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span style={{
                width: 9, height: 9, borderRadius: '50%',
                background: liveStatus.state === 'idle' ? J.success : J.amber,
                boxShadow: liveStatus.state === 'idle' ? `0 0 8px ${J.success}` : `0 0 8px ${J.amber}`,
              }} />
              <div style={{ fontSize: 18, fontWeight: 600, color: J.text, textTransform: 'capitalize' }}>{liveStatus.state}</div>
            </div>
            {overview ? (
              <div style={{ fontSize: 13, color: J.textSec, display: 'flex', flexDirection: 'column', gap: 3 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ color: overview.reachable ? J.success : J.textMuted, display: 'flex' }}><IconActivity size={12} /></span>
                  Home Assistant {overview.reachable ? 'online' : 'offline'}
                </div>
                <div>{overview.counts.managed_entities} devices · {overview.counts.control_requests} pending</div>
              </div>
            ) : (
              <div style={{ fontSize: 13, color: J.textMuted }}>Home Assistant unavailable</div>
            )}
          </div>
        </Tile>
      </div>
    </div>
  );
}
