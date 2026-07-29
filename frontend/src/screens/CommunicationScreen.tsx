import { useState } from 'react';
import { J, useJ, IconMail, IconCalendar } from './jarvis-shared';
import { EmailScreen } from './EmailScreen';
import { CalendarScreen } from './CalendarScreen';

type Tab = 'email' | 'calendar';

export function CommunicationScreen() {
  useJ();
  const [tab, setTab] = useState<Tab>('email');

  const tabs: Array<{ id: Tab; label: string; icon: (p: { size?: number }) => JSX.Element }> = [
    { id: 'email', label: 'Email', icon: IconMail },
    { id: 'calendar', label: 'Calendar', icon: IconCalendar },
  ];

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: J.bg0 }}>
      <div style={{ display: 'flex', gap: 4, padding: '10px 20px 0', borderBottom: `1px solid ${J.border}`, background: J.bg1, flexShrink: 0 }}>
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', fontSize: 13, fontWeight: tab === t.id ? 600 : 400,
              background: 'none', border: 'none', borderBottom: `2px solid ${tab === t.id ? J.amber : 'transparent'}`,
              color: tab === t.id ? J.amber : J.textSec, cursor: 'pointer', transition: 'all .12s',
            }}
          >
            <t.icon size={14} /> {t.label}
          </button>
        ))}
      </div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {tab === 'email' ? <EmailScreen /> : <CalendarScreen />}
      </div>
    </div>
  );
}
