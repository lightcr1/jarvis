import { useEffect, useState } from 'react';
import { J, useJ, Spinner, showToast, IconPlus, IconCheck, IconTrash, IconX } from './jarvis-shared';
import { OverlayDialog } from '../shared/ui/OverlayDialog';
import { Task, TaskPriority, TaskStatus, completeTask, createTask, deleteTask, fetchTasks } from '../shared/api/tasks';

const FILTERS: Array<{ id: 'all' | TaskStatus; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'open', label: 'Open' },
  { id: 'in_progress', label: 'In Progress' },
  { id: 'done', label: 'Done' },
];

const PRIORITY_COLOR: Record<TaskPriority, string> = { low: J.textSec, medium: J.warn, high: J.error };
const STATUS_COLOR: Record<TaskStatus, string> = { open: J.blue, in_progress: J.warn, done: J.success };

function Pill({ label, color }: { label: string; color: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: `${color}1a`, color, borderRadius: 5, padding: '2px 8px', fontSize: 11, fontWeight: 500, whiteSpace: 'nowrap' }}>
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: color, flexShrink: 0 }} />
      {label}
    </span>
  );
}

function CreateTaskModal({ onClose, onCreated }: { onClose: () => void; onCreated: (task: Task) => void }) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<TaskPriority>('medium');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    const trimmed = title.trim();
    if (!trimmed || saving) return;
    setSaving(true);
    try {
      const res = await createTask({ title: trimmed, description: description.trim() || undefined, priority });
      onCreated(res.task);
      showToast('Task added', 'success');
      onClose();
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to create task', 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <OverlayDialog
      title="New Task"
      onClose={onClose}
      actions={
        <>
          <button onClick={onClose} className="j-btn" style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '8px 16px', fontSize: 13 }}>Cancel</button>
          <button onClick={submit} disabled={!title.trim() || saving} className="j-btn"
            style={{ background: J.amber, color: J.bg0, borderRadius: 8, padding: '8px 20px', fontSize: 13, fontWeight: 600, opacity: title.trim() ? 1 : .5 }}>
            {saving ? <Spinner size={13} color={J.bg0} /> : 'Create'}
          </button>
        </>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div>
          <label style={{ fontSize: 12, color: J.textSec, display: 'block', marginBottom: 5 }}>Title</label>
          <input className="j-input" autoFocus value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Renew server certificate"
            onKeyDown={e => { if (e.key === 'Enter') submit(); }}
            style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
        </div>
        <div>
          <label style={{ fontSize: 12, color: J.textSec, display: 'block', marginBottom: 5 }}>Description (optional)</label>
          <textarea className="j-input" value={description} onChange={e => setDescription(e.target.value)} rows={3} placeholder="Details..."
            style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13, resize: 'vertical', fontFamily: 'inherit' }} />
        </div>
        <div>
          <label style={{ fontSize: 12, color: J.textSec, display: 'block', marginBottom: 5 }}>Priority</label>
          <div style={{ display: 'flex', gap: 6 }}>
            {(['low', 'medium', 'high'] as TaskPriority[]).map(p => (
              <button key={p} onClick={() => setPriority(p)}
                style={{ flex: 1, background: priority === p ? `${PRIORITY_COLOR[p]}1a` : J.bg3, border: `1px solid ${priority === p ? PRIORITY_COLOR[p] : J.border}`, color: priority === p ? PRIORITY_COLOR[p] : J.textSec, borderRadius: 7, padding: '8px 6px', fontSize: 12, fontWeight: priority === p ? 600 : 400, cursor: 'pointer', textTransform: 'capitalize' }}>
                {p}
              </button>
            ))}
          </div>
        </div>
      </div>
    </OverlayDialog>
  );
}

function TaskCard({ task, onComplete, onDelete }: { task: Task; onComplete: (id: string) => void; onDelete: (id: string) => void }) {
  const done = task.status === 'done';
  return (
    <div style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 12, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 8, opacity: done ? 0.6 : 1 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
        <div style={{ fontSize: 14, fontWeight: 500, color: J.text, textDecoration: done ? 'line-through' : 'none' }}>{task.title}</div>
        <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
          {!done && (
            <button onClick={() => onComplete(task.id)} title="Mark complete" aria-label="Mark complete"
              style={{ background: J.successDim, border: `1px solid ${J.success}`, color: J.success, borderRadius: 6, width: 26, height: 26, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
              <IconCheck size={13} />
            </button>
          )}
          <button onClick={() => onDelete(task.id)} title="Delete task" aria-label="Delete task"
            style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textMuted, borderRadius: 6, width: 26, height: 26, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
            <IconTrash size={13} />
          </button>
        </div>
      </div>
      {task.description && <div style={{ fontSize: 12, color: J.textSec, lineHeight: 1.5 }}>{task.description}</div>}
      {task.steps.length > 0 && (
        <ul style={{ margin: 0, padding: '0 0 0 16px', fontSize: 12, color: J.textSec, lineHeight: 1.6 }}>
          {task.steps.map((step, i) => <li key={i}>{step}</li>)}
        </ul>
      )}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <Pill label={task.status.replace('_', ' ')} color={STATUS_COLOR[task.status]} />
        <Pill label={task.priority} color={PRIORITY_COLOR[task.priority]} />
        {task.due_at && <Pill label={new Date(task.due_at * 1000).toLocaleDateString()} color={J.textSec} />}
      </div>
    </div>
  );
}

export function TasksScreen(_props: { onNavigate?: (screen: string) => void }) {
  useJ();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [filter, setFilter] = useState<'all' | TaskStatus>('open');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const load = () => {
    setLoading(true);
    setError(null);
    fetchTasks()
      .then(res => setTasks(res.tasks))
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load tasks'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleComplete = async (id: string) => {
    try {
      await completeTask(id);
      setTasks(prev => prev.map(t => (t.id === id ? { ...t, status: 'done' } : t)));
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to complete task', 'error');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteTask(id);
      setTasks(prev => prev.filter(t => t.id !== id));
      showToast('Task deleted', 'info');
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to delete task', 'error');
    }
  };

  const shown = filter === 'all' ? tasks : tasks.filter(t => t.status === filter);
  const openCount = tasks.filter(t => t.status !== 'done').length;

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: J.bg0 }}>
      <div style={{ height: 50, borderBottom: `1px solid ${J.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px', background: J.bg1, flexShrink: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 500, color: J.text }}>Tasks {openCount > 0 && <span style={{ color: J.textMuted, fontWeight: 400 }}>({openCount} open)</span>}</div>
        <button onClick={() => setShowCreate(true)} className="j-btn"
          style={{ background: J.amberDim, border: `1px solid ${J.borderAccent}`, color: J.amber, borderRadius: 8, padding: '6px 14px', fontSize: 13, fontWeight: 500 }}>
          <IconPlus size={13} /> New Task
        </button>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '22px 24px' }}>
        <div style={{ display: 'flex', gap: 6, marginBottom: 18, flexWrap: 'wrap' }}>
          {FILTERS.map(f => (
            <button key={f.id} onClick={() => setFilter(f.id)}
              style={{ background: filter === f.id ? J.amberDim : J.bg2, border: `1px solid ${filter === f.id ? J.borderAccent : J.border}`, color: filter === f.id ? J.amber : J.textSec, borderRadius: 7, padding: '4px 13px', fontSize: 12, fontWeight: filter === f.id ? 500 : 400, cursor: 'pointer', transition: 'all .1s' }}>
              {f.label}
            </button>
          ))}
        </div>

        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: J.textMuted, fontSize: 13, padding: '24px 0' }}>
            <Spinner size={14} /> Loading tasks...
          </div>
        )}

        {!loading && error && (
          <div style={{ background: J.errorDim, border: `1px solid ${J.error}`, borderRadius: 10, padding: '12px 16px', color: J.error, fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            {error}
            <button onClick={load} style={{ background: 'none', border: 'none', color: J.error, cursor: 'pointer', display: 'flex' }}><IconX size={14} /></button>
          </div>
        )}

        {!loading && !error && shown.length === 0 && (
          <div style={{ textAlign: 'center', color: J.textMuted, fontSize: 13, padding: '48px 0' }}>
            {filter === 'all' ? 'No tasks yet. Create one to get started.' : `No ${filter.replace('_', ' ')} tasks.`}
          </div>
        )}

        {!loading && !error && shown.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(260px,1fr))', gap: 10 }}>
            {shown.map(task => <TaskCard key={task.id} task={task} onComplete={handleComplete} onDelete={handleDelete} />)}
          </div>
        )}
      </div>
      {showCreate && (
        <CreateTaskModal
          onClose={() => setShowCreate(false)}
          onCreated={task => setTasks(prev => [task, ...prev])}
        />
      )}
    </div>
  );
}
