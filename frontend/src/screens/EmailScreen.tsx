import { useEffect, useState } from 'react';
import { J, useJ, Spinner, showToast, IconMail, IconRefresh, IconX, IconSend, IconTrash, IconPencil, IconSettings, IconChevDown, IconPlus, IconCheck } from './jarvis-shared';
import { OverlayDialog } from '../shared/ui/OverlayDialog';
import {
  EmailAccount, EmailAccountFields, EmailDraft, EmailMessage, addEmailAccount, createEmailDraft, deleteEmailAccount, discardEmailDraft,
  fetchEmailAccounts, fetchEmailBody, fetchEmailDrafts, fetchEmailMessages, sendEmailDraft, setEmailCredentials, setPrimaryEmailAccount,
  summarizeEmail, syncEmail, updateEmailAccount,
} from '../shared/api/email';

type Tab = 'inbox' | 'drafts';

function ConnectEmailPanel({ onConnected }: { onConnected: () => void }) {
  const [fields, setFields] = useState({ imap_host: '', imap_port: '993', imap_username: '', imap_password: '', smtp_host: '', smtp_port: '587', smtp_username: '', smtp_password: '' });
  const [saving, setSaving] = useState(false);
  const set = (key: keyof typeof fields) => (e: React.ChangeEvent<HTMLInputElement>) => setFields(prev => ({ ...prev, [key]: e.target.value }));
  const ready = Object.values(fields).every(v => v.trim());

  const submit = async () => {
    if (!ready || saving) return;
    setSaving(true);
    try {
      await setEmailCredentials(fields);
      showToast('Email connected', 'success');
      onConnected();
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to connect email', 'error');
    } finally {
      setSaving(false);
    }
  };

  const field = (key: keyof typeof fields, label: string, type = 'text') => (
    <div style={{ flex: key.includes('port') ? '0 0 90px' : 1 }}>
      <label style={{ fontSize: 11.5, color: J.textSec, display: 'block', marginBottom: 4 }}>{label}</label>
      <input className="j-input" type={type} value={fields[key]} onChange={set(key)} style={{ width: '100%', borderRadius: 7, padding: '8px 10px', fontSize: 12.5 }} />
    </div>
  );

  return (
    <div style={{ maxWidth: 460, margin: '40px auto', background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 14, padding: 28 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
        <IconMail size={20} />
        <div style={{ fontSize: 16, fontWeight: 600, color: J.text }}>Connect your email</div>
      </div>
      <div style={{ fontSize: 12.5, color: J.textSec, marginBottom: 20, lineHeight: 1.6 }}>
        Generic IMAP/SMTP — works with Gmail (app password), iCloud, self-hosted, or any provider.
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ fontSize: 11, color: J.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.04em' }}>IMAP (incoming)</div>
        <div style={{ display: 'flex', gap: 8 }}>{field('imap_host', 'Host')}{field('imap_port', 'Port')}</div>
        <div style={{ display: 'flex', gap: 8 }}>{field('imap_username', 'Username')}{field('imap_password', 'Password', 'password')}</div>
        <div style={{ fontSize: 11, color: J.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.04em', marginTop: 6 }}>SMTP (outgoing)</div>
        <div style={{ display: 'flex', gap: 8 }}>{field('smtp_host', 'Host')}{field('smtp_port', 'Port')}</div>
        <div style={{ display: 'flex', gap: 8 }}>{field('smtp_username', 'Username')}{field('smtp_password', 'Password', 'password')}</div>
        <button onClick={submit} disabled={!ready || saving} className="j-btn"
          style={{ background: J.amber, color: J.bg0, borderRadius: 8, padding: '10px 16px', fontSize: 13, fontWeight: 600, justifyContent: 'center', opacity: ready ? 1 : .5, marginTop: 8 }}>
          {saving ? <Spinner size={13} color={J.bg0} /> : 'Connect'}
        </button>
      </div>
    </div>
  );
}

function ManageEmailDialog({ accountId, initialLabel, onClose, onUpdated, onDisconnected }: {
  accountId: string; initialLabel: string; onClose: () => void; onUpdated: () => void; onDisconnected: (accountId: string) => void;
}) {
  const [label, setLabel] = useState(initialLabel);
  const [fields, setFields] = useState({ imap_host: '', imap_port: '993', imap_username: '', imap_password: '', smtp_host: '', smtp_port: '587', smtp_username: '', smtp_password: '' });
  const [saving, setSaving] = useState(false);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const set = (key: keyof typeof fields) => (e: React.ChangeEvent<HTMLInputElement>) => setFields(prev => ({ ...prev, [key]: e.target.value }));
  const ready = label.trim() && Object.values(fields).every(v => v.trim());

  const submit = async () => {
    if (!ready || saving) return;
    setSaving(true);
    try {
      await updateEmailAccount(accountId, label.trim(), fields);
      showToast('Email connection updated', 'success');
      onUpdated();
      onClose();
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to update email', 'error');
    } finally {
      setSaving(false);
    }
  };

  const disconnect = async () => {
    setDisconnecting(true);
    try {
      await deleteEmailAccount(accountId);
      showToast('Email disconnected', 'info');
      onDisconnected(accountId);
      onClose();
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to disconnect email', 'error');
    } finally {
      setDisconnecting(false);
    }
  };

  const field = (key: keyof typeof fields, fieldLabel: string, type = 'text') => (
    <div style={{ flex: key.includes('port') ? '0 0 90px' : 1 }}>
      <label style={{ fontSize: 11.5, color: J.textSec, display: 'block', marginBottom: 4 }}>{fieldLabel}</label>
      <input className="j-input" type={type} value={fields[key]} onChange={set(key)} style={{ width: '100%', borderRadius: 7, padding: '8px 10px', fontSize: 12.5 }} />
    </div>
  );

  return (
    <OverlayDialog
      title="Manage Email Connection"
      onClose={onClose}
      actions={
        <>
          <button onClick={onClose} className="j-btn" style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '8px 16px', fontSize: 13 }}>Cancel</button>
          <button onClick={submit} disabled={!ready || saving} className="j-btn"
            style={{ background: J.amber, color: J.bg0, borderRadius: 8, padding: '8px 20px', fontSize: 13, fontWeight: 600, opacity: ready ? 1 : .5 }}>
            {saving ? <Spinner size={13} color={J.bg0} /> : 'Save'}
          </button>
        </>
      }
    >
      <div style={{ fontSize: 12.5, color: J.textSec, marginBottom: 16, lineHeight: 1.6 }}>
        Re-enter your IMAP/SMTP details to change this connected account, or disconnect below.
        For security, existing credentials are never shown here.
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div>
          <label style={{ fontSize: 11.5, color: J.textSec, display: 'block', marginBottom: 4 }}>Label</label>
          <input className="j-input" value={label} onChange={e => setLabel(e.target.value)} style={{ width: '100%', borderRadius: 7, padding: '8px 10px', fontSize: 12.5 }} />
        </div>
        <div style={{ fontSize: 11, color: J.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.04em' }}>IMAP (incoming)</div>
        <div style={{ display: 'flex', gap: 8 }}>{field('imap_host', 'Host')}{field('imap_port', 'Port')}</div>
        <div style={{ display: 'flex', gap: 8 }}>{field('imap_username', 'Username')}{field('imap_password', 'Password', 'password')}</div>
        <div style={{ fontSize: 11, color: J.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.04em', marginTop: 6 }}>SMTP (outgoing)</div>
        <div style={{ display: 'flex', gap: 8 }}>{field('smtp_host', 'Host')}{field('smtp_port', 'Port')}</div>
        <div style={{ display: 'flex', gap: 8 }}>{field('smtp_username', 'Username')}{field('smtp_password', 'Password', 'password')}</div>
      </div>
      <div style={{ marginTop: 20, paddingTop: 16, borderTop: `1px solid ${J.border}` }}>
        {!confirmDisconnect ? (
          <button onClick={() => setConfirmDisconnect(true)} className="j-btn"
            style={{ background: 'none', border: `1px solid ${J.error}30`, color: J.error, borderRadius: 8, padding: '8px 14px', fontSize: 12.5 }}>
            <IconTrash size={12} /> Disconnect email
          </button>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 12.5, color: J.textSec }}>Remove this email connection?</span>
            <button onClick={disconnect} disabled={disconnecting} className="j-btn"
              style={{ background: J.error, color: '#fff', borderRadius: 7, padding: '6px 14px', fontSize: 12.5, fontWeight: 600 }}>
              {disconnecting ? <Spinner size={12} color="#fff" /> : 'Yes, disconnect'}
            </button>
            <button onClick={() => setConfirmDisconnect(false)} className="j-btn"
              style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 7, padding: '6px 14px', fontSize: 12.5 }}>
              Cancel
            </button>
          </div>
        )}
      </div>
    </OverlayDialog>
  );
}

function AddAccountDialog({ onClose, onAdded }: { onClose: () => void; onAdded: (accountId: string) => void }) {
  const [label, setLabel] = useState('');
  const [fields, setFields] = useState<EmailAccountFields>({ imap_host: '', imap_port: '993', imap_username: '', imap_password: '', smtp_host: '', smtp_port: '587', smtp_username: '', smtp_password: '' });
  const [saving, setSaving] = useState(false);
  const set = (key: keyof EmailAccountFields) => (e: React.ChangeEvent<HTMLInputElement>) => setFields(prev => ({ ...prev, [key]: e.target.value }));
  const ready = label.trim() && Object.values(fields).every(v => String(v).trim());

  const submit = async () => {
    if (!ready || saving) return;
    setSaving(true);
    try {
      const res = await addEmailAccount(label.trim(), fields);
      showToast('Account added', 'success');
      onAdded(res.account.account_id);
      onClose();
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to add account', 'error');
    } finally {
      setSaving(false);
    }
  };

  const field = (key: keyof EmailAccountFields, fieldLabel: string, type = 'text') => (
    <div style={{ flex: key.includes('port') ? '0 0 90px' : 1 }}>
      <label style={{ fontSize: 11.5, color: J.textSec, display: 'block', marginBottom: 4 }}>{fieldLabel}</label>
      <input className="j-input" type={type} value={fields[key]} onChange={set(key)} style={{ width: '100%', borderRadius: 7, padding: '8px 10px', fontSize: 12.5 }} />
    </div>
  );

  return (
    <OverlayDialog
      title="Add Email Account"
      onClose={onClose}
      actions={
        <>
          <button onClick={onClose} className="j-btn" style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '8px 16px', fontSize: 13 }}>Cancel</button>
          <button onClick={submit} disabled={!ready || saving} className="j-btn"
            style={{ background: J.amber, color: J.bg0, borderRadius: 8, padding: '8px 20px', fontSize: 13, fontWeight: 600, opacity: ready ? 1 : .5 }}>
            {saving ? <Spinner size={13} color={J.bg0} /> : 'Add account'}
          </button>
        </>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div>
          <label style={{ fontSize: 11.5, color: J.textSec, display: 'block', marginBottom: 4 }}>Label</label>
          <input className="j-input" placeholder="e.g. Personal" value={label} onChange={e => setLabel(e.target.value)} style={{ width: '100%', borderRadius: 7, padding: '8px 10px', fontSize: 12.5 }} />
        </div>
        <div style={{ fontSize: 11, color: J.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.04em' }}>IMAP (incoming)</div>
        <div style={{ display: 'flex', gap: 8 }}>{field('imap_host', 'Host')}{field('imap_port', 'Port')}</div>
        <div style={{ display: 'flex', gap: 8 }}>{field('imap_username', 'Username')}{field('imap_password', 'Password', 'password')}</div>
        <div style={{ fontSize: 11, color: J.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.04em', marginTop: 6 }}>SMTP (outgoing)</div>
        <div style={{ display: 'flex', gap: 8 }}>{field('smtp_host', 'Host')}{field('smtp_port', 'Port')}</div>
        <div style={{ display: 'flex', gap: 8 }}>{field('smtp_username', 'Username')}{field('smtp_password', 'Password', 'password')}</div>
      </div>
    </OverlayDialog>
  );
}

function AccountSwitcher({ accounts, activeAccountId, onSelect, onAdd, onManage, onSetPrimary, onClose }: {
  accounts: EmailAccount[]; activeAccountId: string | null; onSelect: (id: string) => void; onAdd: () => void;
  onManage: (account: EmailAccount) => void; onSetPrimary: (id: string) => void; onClose: () => void;
}) {
  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 40 }} />
      <div style={{ position: 'absolute', top: 'calc(100% + 8px)', right: 0, width: 280, background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 10, zIndex: 41, overflow: 'hidden', boxShadow: '0 8px 24px rgba(0,0,0,0.4)' }}>
        <div style={{ padding: '9px 14px 7px', fontSize: 10, color: J.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Email accounts</div>
        {accounts.map(acct => {
          const isActive = acct.account_id === activeAccountId;
          return (
            <div key={acct.account_id} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '2px 8px 2px 6px' }}>
              <button
                onClick={() => onSelect(acct.account_id)}
                style={{ flex: 1, textAlign: 'left', padding: '8px 8px', background: isActive ? J.amberGlow : 'none', border: 'none', borderRadius: 7, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}
              >
                {isActive ? <IconCheck size={13} /> : <span style={{ width: 13, flexShrink: 0 }} />}
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 12.5, color: isActive ? J.amber : J.text, fontWeight: isActive ? 600 : 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{acct.label}</div>
                </div>
                {acct.is_primary && (
                  <span style={{ fontSize: 9.5, color: J.textMuted, background: J.bg3, border: `1px solid ${J.border}`, borderRadius: 5, padding: '1px 6px', flexShrink: 0 }}>Primary</span>
                )}
              </button>
              <button onClick={() => onManage(acct)} title="Manage account" aria-label="Manage account"
                style={{ background: 'none', border: 'none', color: J.textMuted, cursor: 'pointer', padding: 6, display: 'flex', flexShrink: 0 }}>
                <IconSettings size={12} />
              </button>
            </div>
          );
        })}
        <div style={{ padding: '4px 14px 8px' }}>
          {accounts.find(a => a.account_id === activeAccountId && !a.is_primary) && (
            <button onClick={() => onSetPrimary(activeAccountId as string)}
              style={{ width: '100%', textAlign: 'left', background: 'none', border: 'none', color: J.textSec, fontSize: 11.5, cursor: 'pointer', padding: '4px 0' }}>
              Set active account as primary
            </button>
          )}
        </div>
        <div style={{ borderTop: `1px solid ${J.border}` }}>
          <button onClick={onAdd} style={{ width: '100%', textAlign: 'left', padding: '10px 14px', background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8, color: J.amber, fontSize: 12.5, fontWeight: 500 }}>
            <IconPlus size={13} /> Add account
          </button>
        </div>
      </div>
    </>
  );
}

function ComposeModal({ to, subject, replyToId, accountId, onClose, onCreated }: { to: string; subject: string; replyToId?: string; accountId: string | null; onClose: () => void; onCreated: (draft: EmailDraft) => void }) {
  const [toValue, setToValue] = useState(to);
  const [subjectValue, setSubjectValue] = useState(subject);
  const [body, setBody] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!toValue.trim() || !body.trim() || saving) return;
    setSaving(true);
    try {
      const res = await createEmailDraft({ to: toValue.trim(), subject: subjectValue.trim(), body: body.trim(), in_reply_to_message_id: replyToId, account_id: accountId || undefined });
      onCreated(res.draft);
      showToast('Draft saved — review and send from the Drafts tab', 'success');
      onClose();
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to save draft', 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <OverlayDialog
      title={replyToId ? 'Reply' : 'New Message'}
      onClose={onClose}
      actions={
        <>
          <button onClick={onClose} className="j-btn" style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '8px 16px', fontSize: 13 }}>Cancel</button>
          <button onClick={submit} disabled={!toValue.trim() || !body.trim() || saving} className="j-btn"
            style={{ background: J.amber, color: J.bg0, borderRadius: 8, padding: '8px 20px', fontSize: 13, fontWeight: 600, opacity: toValue.trim() && body.trim() ? 1 : .5 }}>
            {saving ? <Spinner size={13} color={J.bg0} /> : 'Save Draft'}
          </button>
        </>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div>
          <label style={{ fontSize: 12, color: J.textSec, display: 'block', marginBottom: 5 }}>To</label>
          <input className="j-input" value={toValue} onChange={e => setToValue(e.target.value)} style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
        </div>
        <div>
          <label style={{ fontSize: 12, color: J.textSec, display: 'block', marginBottom: 5 }}>Subject</label>
          <input className="j-input" value={subjectValue} onChange={e => setSubjectValue(e.target.value)} style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
        </div>
        <div>
          <label style={{ fontSize: 12, color: J.textSec, display: 'block', marginBottom: 5 }}>Message</label>
          <textarea className="j-input" autoFocus value={body} onChange={e => setBody(e.target.value)} rows={8}
            style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13, resize: 'vertical', fontFamily: 'inherit' }} />
        </div>
      </div>
    </OverlayDialog>
  );
}

function MessageDetail({ message, onClose, onReply }: { message: EmailMessage; onClose: () => void; onReply: () => void }) {
  const [body, setBody] = useState<string | null>(null);
  const [summary, setSummary] = useState<string | null>(message.summary);
  const [loading, setLoading] = useState(true);
  const [summarizing, setSummarizing] = useState(false);

  useEffect(() => {
    fetchEmailBody(message.id).then(res => setBody(res.body)).catch(() => setBody('(failed to load message body)')).finally(() => setLoading(false));
  }, [message.id]);

  const summarize = async () => {
    setSummarizing(true);
    try {
      const res = await summarizeEmail(message.id);
      setSummary(res.message.summary);
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Summarize failed', 'error');
    } finally {
      setSummarizing(false);
    }
  };

  return (
    <OverlayDialog
      title={message.subject || '(no subject)'}
      onClose={onClose}
      actions={
        <>
          <button onClick={onClose} className="j-btn" style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '8px 16px', fontSize: 13 }}>Close</button>
          <button onClick={onReply} className="j-btn" style={{ background: J.amber, color: J.bg0, borderRadius: 8, padding: '8px 20px', fontSize: 13, fontWeight: 600 }}>
            <IconPencil size={13} /> Reply
          </button>
        </>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ fontSize: 12.5, color: J.textSec }}>From {message.sender} · {new Date(message.date * 1000).toLocaleString()}</div>
        {summary && (
          <div style={{ background: J.amberDim, border: `1px solid ${J.borderAccent}`, borderRadius: 8, padding: '10px 12px', fontSize: 12.5, color: J.text, lineHeight: 1.5 }}>
            {summary}
          </div>
        )}
        {!summary && (
          <button onClick={summarize} disabled={summarizing || loading} className="j-btn"
            style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 7, padding: '6px 12px', fontSize: 12, alignSelf: 'flex-start' }}>
            {summarizing ? <Spinner size={12} /> : null} Summarize
          </button>
        )}
        {loading ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: J.textMuted, fontSize: 13 }}><Spinner size={13} /> Loading message...</div>
        ) : (
          <div style={{ fontSize: 13, color: J.text, lineHeight: 1.6, whiteSpace: 'pre-wrap', maxHeight: 320, overflowY: 'auto' }}>{body}</div>
        )}
      </div>
    </OverlayDialog>
  );
}

function DraftCard({ draft, onSend, onDiscard }: { draft: EmailDraft; onSend: (draft: EmailDraft) => void; onDiscard: (id: string) => void }) {
  return (
    <div style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 12, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ fontSize: 13, color: J.textSec }}>To: <span style={{ color: J.text }}>{draft.to}</span></div>
      <div style={{ fontSize: 14, fontWeight: 500, color: J.text }}>{draft.subject}</div>
      <div style={{ fontSize: 12.5, color: J.textSec, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{draft.body}</div>
      <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
        <button onClick={() => onSend(draft)} className="j-btn"
          style={{ background: J.amberDim, border: `1px solid ${J.borderAccent}`, color: J.amber, borderRadius: 7, padding: '6px 14px', fontSize: 12.5, fontWeight: 500 }}>
          <IconSend size={12} /> Send
        </button>
        <button onClick={() => onDiscard(draft.id)} className="j-btn"
          style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textMuted, borderRadius: 7, padding: '6px 14px', fontSize: 12.5 }}>
          <IconTrash size={12} /> Discard
        </button>
      </div>
    </div>
  );
}

export function EmailScreen(_props: { onNavigate?: (screen: string) => void }) {
  useJ();
  const [accounts, setAccounts] = useState<EmailAccount[]>([]);
  const [activeAccountId, setActiveAccountId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('inbox');
  const [messages, setMessages] = useState<EmailMessage[]>([]);
  const [drafts, setDrafts] = useState<EmailDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [openMessage, setOpenMessage] = useState<EmailMessage | null>(null);
  const [compose, setCompose] = useState<{ to: string; subject: string; replyToId?: string } | null>(null);
  const [pendingSend, setPendingSend] = useState<EmailDraft | null>(null);
  const [manageAccount, setManageAccount] = useState<EmailAccount | null>(null);
  const [addAccountOpen, setAddAccountOpen] = useState(false);
  const [switcherOpen, setSwitcherOpen] = useState(false);

  const configured = accounts.length > 0;

  const loadMessages = (accountId: string) => fetchEmailMessages({ accountId }).then(res => setMessages(res.messages));
  const loadDrafts = (accountId: string) => fetchEmailDrafts(undefined, accountId).then(res => setDrafts(res.drafts));

  const loadForAccount = (accountId: string) => {
    setLoading(true);
    setError(null);
    Promise.all([loadMessages(accountId), loadDrafts(accountId)])
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load email'))
      .finally(() => setLoading(false));
  };

  const load = () => {
    setLoading(true);
    setError(null);
    fetchEmailAccounts()
      .then(res => {
        setAccounts(res.accounts);
        if (res.accounts.length === 0) { setActiveAccountId(null); setMessages([]); setDrafts([]); setLoading(false); return; }
        const preferred = res.accounts.find(a => a.account_id === activeAccountId) || res.accounts.find(a => a.is_primary) || res.accounts[0];
        setActiveAccountId(preferred.account_id);
        return Promise.all([loadMessages(preferred.account_id), loadDrafts(preferred.account_id)]);
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load email'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const refreshAccounts = () => fetchEmailAccounts().then(res => setAccounts(res.accounts));

  const handleSwitchAccount = (accountId: string) => {
    setSwitcherOpen(false);
    if (accountId === activeAccountId) return;
    setActiveAccountId(accountId);
    loadForAccount(accountId);
  };

  const handleAccountAdded = (accountId: string) => {
    setAddAccountOpen(false);
    refreshAccounts().then(() => { setActiveAccountId(accountId); loadForAccount(accountId); });
  };

  const handleAccountUpdated = () => { refreshAccounts(); };

  const handleAccountDisconnected = (deletedId: string) => {
    setManageAccount(null);
    fetchEmailAccounts().then(res => {
      setAccounts(res.accounts);
      if (res.accounts.length === 0) { setActiveAccountId(null); setMessages([]); setDrafts([]); return; }
      if (deletedId === activeAccountId) {
        const next = res.accounts.find(a => a.is_primary) || res.accounts[0];
        setActiveAccountId(next.account_id);
        loadForAccount(next.account_id);
      }
    });
  };

  const handleSetPrimary = (accountId: string) => {
    setPrimaryEmailAccount(accountId)
      .then(() => { refreshAccounts(); showToast('Primary account updated', 'success'); })
      .catch(err => showToast(err instanceof Error ? err.message : 'Failed to set primary', 'error'));
  };

  const handleSync = async () => {
    if (!activeAccountId) return;
    setSyncing(true);
    try {
      await syncEmail(activeAccountId);
      await loadMessages(activeAccountId);
      showToast('Inbox synced', 'success');
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Sync failed', 'error');
    } finally {
      setSyncing(false);
    }
  };

  const requestSend = async (draft: EmailDraft) => {
    try {
      const res = await sendEmailDraft(draft.id, false);
      if (res.status === 'confirmation_required') { setPendingSend(res.draft); return; }
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Send failed', 'error');
    }
  };

  const confirmSend = async () => {
    if (!pendingSend) return;
    try {
      await sendEmailDraft(pendingSend.id, true);
      setDrafts(prev => prev.filter(d => d.id !== pendingSend.id));
      showToast('Message sent', 'success');
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Send failed', 'error');
    } finally {
      setPendingSend(null);
    }
  };

  const handleDiscard = async (id: string) => {
    try {
      await discardEmailDraft(id);
      setDrafts(prev => prev.filter(d => d.id !== id));
      showToast('Draft discarded', 'info');
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to discard draft', 'error');
    }
  };

  const pendingDraftCount = drafts.filter(d => d.status === 'pending_approval').length;
  const activeAccount = accounts.find(a => a.account_id === activeAccountId) || null;

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: J.bg0 }}>
      <div style={{ height: 50, borderBottom: `1px solid ${J.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px', background: J.bg1, flexShrink: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 500, color: J.text }}>Email</div>
        {configured && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <div style={{ position: 'relative' }}>
              <button onClick={() => setSwitcherOpen(v => !v)} className="j-btn"
                style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.text, borderRadius: 8, padding: '6px 12px', fontSize: 13, maxWidth: 180 }}>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{activeAccount?.label || 'Account'}</span>
                <IconChevDown size={13} />
              </button>
              {switcherOpen && (
                <AccountSwitcher
                  accounts={accounts}
                  activeAccountId={activeAccountId}
                  onSelect={handleSwitchAccount}
                  onAdd={() => { setSwitcherOpen(false); setAddAccountOpen(true); }}
                  onManage={acct => { setSwitcherOpen(false); setManageAccount(acct); }}
                  onSetPrimary={handleSetPrimary}
                  onClose={() => setSwitcherOpen(false)}
                />
              )}
            </div>
            <button onClick={handleSync} disabled={syncing} className="j-btn"
              style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '6px 12px', fontSize: 13 }}>
              {syncing ? <Spinner size={13} /> : <IconRefresh size={13} />} Sync
            </button>
            <button onClick={() => setCompose({ to: '', subject: '' })} className="j-btn"
              style={{ background: J.amberDim, border: `1px solid ${J.borderAccent}`, color: J.amber, borderRadius: 8, padding: '6px 14px', fontSize: 13, fontWeight: 500 }}>
              <IconPencil size={13} /> Compose
            </button>
          </div>
        )}
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '22px 24px' }}>
        {configured && (
          <div style={{ display: 'flex', gap: 6, marginBottom: 18 }}>
            {(['inbox', 'drafts'] as Tab[]).map(id => (
              <button key={id} onClick={() => setTab(id)}
                style={{ background: tab === id ? J.amberDim : J.bg2, border: `1px solid ${tab === id ? J.borderAccent : J.border}`, color: tab === id ? J.amber : J.textSec, borderRadius: 7, padding: '4px 13px', fontSize: 12, fontWeight: tab === id ? 500 : 400, cursor: 'pointer', textTransform: 'capitalize' }}>
                {id}{id === 'drafts' && pendingDraftCount > 0 ? ` (${pendingDraftCount})` : ''}
              </button>
            ))}
          </div>
        )}

        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: J.textMuted, fontSize: 13, padding: '24px 0' }}>
            <Spinner size={14} /> Loading email...
          </div>
        )}

        {!loading && error && (
          <div style={{ background: J.errorDim, border: `1px solid ${J.error}`, borderRadius: 10, padding: '12px 16px', color: J.error, fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            {error}
            <button onClick={load} style={{ background: 'none', border: 'none', color: J.error, cursor: 'pointer', display: 'flex' }}><IconX size={14} /></button>
          </div>
        )}

        {!loading && !error && !configured && <ConnectEmailPanel onConnected={load} />}

        {!loading && !error && configured && tab === 'inbox' && (
          messages.length === 0 ? (
            <div style={{ textAlign: 'center', color: J.textMuted, fontSize: 13, padding: '48px 0' }}>Inbox is empty. Try syncing.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {messages.map(m => (
                <button key={m.id} onClick={() => setOpenMessage(m)}
                  style={{ textAlign: 'left', background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 10, padding: '11px 14px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 12 }}>
                  {!m.read && <span style={{ width: 6, height: 6, borderRadius: '50%', background: J.amber, flexShrink: 0 }} />}
                  <span style={{ fontSize: 13, color: J.text, fontWeight: m.read ? 400 : 600, minWidth: 160, flexShrink: 0 }}>{m.sender}</span>
                  <span style={{ fontSize: 13, color: J.textSec, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.subject}</span>
                  <span style={{ fontSize: 11.5, color: J.textMuted, flexShrink: 0 }}>{new Date(m.date * 1000).toLocaleDateString()}</span>
                </button>
              ))}
            </div>
          )
        )}

        {!loading && !error && configured && tab === 'drafts' && (
          drafts.length === 0 ? (
            <div style={{ textAlign: 'center', color: J.textMuted, fontSize: 13, padding: '48px 0' }}>No drafts.</div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(300px,1fr))', gap: 10 }}>
              {drafts.map(d => <DraftCard key={d.id} draft={d} onSend={requestSend} onDiscard={handleDiscard} />)}
            </div>
          )
        )}
      </div>

      {openMessage && (
        <MessageDetail
          message={openMessage}
          onClose={() => setOpenMessage(null)}
          onReply={() => {
            const addrMatch = openMessage.sender.match(/<([^>]+)>/);
            const to = addrMatch ? addrMatch[1] : openMessage.sender;
            const subject = openMessage.subject.toLowerCase().startsWith('re:') ? openMessage.subject : `Re: ${openMessage.subject}`;
            setCompose({ to, subject, replyToId: openMessage.id });
            setOpenMessage(null);
          }}
        />
      )}

      {compose && (
        <ComposeModal
          to={compose.to}
          subject={compose.subject}
          replyToId={compose.replyToId}
          accountId={activeAccountId}
          onClose={() => setCompose(null)}
          onCreated={draft => { setDrafts(prev => [draft, ...prev]); setTab('drafts'); }}
        />
      )}

      {pendingSend && (
        <OverlayDialog
          title="Confirm send"
          onClose={() => setPendingSend(null)}
          actions={
            <>
              <button onClick={() => setPendingSend(null)} className="j-btn" style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '8px 16px', fontSize: 13 }}>Cancel</button>
              <button onClick={confirmSend} className="j-btn" style={{ background: J.amber, color: J.bg0, borderRadius: 8, padding: '8px 20px', fontSize: 13, fontWeight: 600 }}>
                <IconSend size={13} /> Confirm Send
              </button>
            </>
          }
        >
          <div style={{ fontSize: 13, color: J.text, lineHeight: 1.6 }}>
            Send this message to <strong>{pendingSend.to}</strong>?
            <div style={{ marginTop: 10, background: J.bg3, borderRadius: 8, padding: '10px 12px', fontSize: 12.5, color: J.textSec, whiteSpace: 'pre-wrap' }}>{pendingSend.body}</div>
          </div>
        </OverlayDialog>
      )}

      {manageAccount && (
        <ManageEmailDialog
          accountId={manageAccount.account_id}
          initialLabel={manageAccount.label}
          onClose={() => setManageAccount(null)}
          onUpdated={handleAccountUpdated}
          onDisconnected={handleAccountDisconnected}
        />
      )}

      {addAccountOpen && (
        <AddAccountDialog
          onClose={() => setAddAccountOpen(false)}
          onAdded={handleAccountAdded}
        />
      )}
    </div>
  );
}
