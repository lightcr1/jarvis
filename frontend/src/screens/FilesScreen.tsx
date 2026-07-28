import { useCallback, useEffect, useRef, useState } from 'react';
import { J, useJ, Spinner, showToast, IconPlus, IconUpload, IconFolder, IconFile, IconTrash, IconPencil, IconX, IconZap, IconDownload, IconChevRight } from './jarvis-shared';
import { OverlayDialog } from '../shared/ui/OverlayDialog';
import {
  BreadcrumbItem, FileEntry, FileFolder,
  browseFiles, createFolder, deleteFile, deleteFolder, downloadFile, fetchQuotaStatus,
  formatBytes, moveFile, moveFolder, renameFile, renameFolder, setJarvisFolderAccess, uploadFile,
} from '../shared/api/files';

function errMsg(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

function IconButton({ onClick, title, children, danger }: { onClick: () => void; title: string; children: React.ReactNode; danger?: boolean }) {
  const color = danger ? J.error : J.textMuted;
  return (
    <button onClick={onClick} title={title} aria-label={title}
      style={{ background: J.bg3, border: `1px solid ${J.border}`, color, borderRadius: 6, width: 26, height: 26, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0 }}>
      {children}
    </button>
  );
}

function CreateFolderModal({ onClose, onCreated }: { onClose: () => void; onCreated: (folder: FileFolder) => void }) {
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed || saving) return;
    setSaving(true);
    try {
      const res = await createFolder(trimmed, null);
      onCreated(res.folder);
      showToast('Folder created', 'success');
      onClose();
    } catch (err) {
      showToast(errMsg(err, 'Failed to create folder'), 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <OverlayDialog
      title="New Folder"
      onClose={onClose}
      actions={
        <>
          <button onClick={onClose} className="j-btn" style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '8px 16px', fontSize: 13 }}>Cancel</button>
          <button onClick={submit} disabled={!name.trim() || saving} className="j-btn"
            style={{ background: J.amber, color: J.bg0, borderRadius: 8, padding: '8px 20px', fontSize: 13, fontWeight: 600, opacity: name.trim() ? 1 : .5 }}>
            {saving ? <Spinner size={13} color={J.bg0} /> : 'Create'}
          </button>
        </>
      }
    >
      <input className="j-input" autoFocus value={name} onChange={e => setName(e.target.value)} placeholder="Folder name"
        onKeyDown={e => { if (e.key === 'Enter') submit(); }}
        style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
    </OverlayDialog>
  );
}

function RenameModal({ initialName, kind, onClose, onSubmit }: { initialName: string; kind: 'folder' | 'file'; onClose: () => void; onSubmit: (name: string) => Promise<void> }) {
  const [name, setName] = useState(initialName);
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed || saving) return;
    setSaving(true);
    try {
      await onSubmit(trimmed);
      onClose();
    } catch (err) {
      showToast(errMsg(err, 'Rename failed'), 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <OverlayDialog
      title={`Rename ${kind === 'folder' ? 'Folder' : 'File'}`}
      onClose={onClose}
      actions={
        <>
          <button onClick={onClose} className="j-btn" style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '8px 16px', fontSize: 13 }}>Cancel</button>
          <button onClick={submit} disabled={!name.trim() || saving} className="j-btn"
            style={{ background: J.amber, color: J.bg0, borderRadius: 8, padding: '8px 20px', fontSize: 13, fontWeight: 600, opacity: name.trim() ? 1 : .5 }}>
            {saving ? <Spinner size={13} color={J.bg0} /> : 'Save'}
          </button>
        </>
      }
    >
      <input className="j-input" autoFocus value={name} onChange={e => setName(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') submit(); }}
        style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
    </OverlayDialog>
  );
}

function MoveModal({ excludeFolderId, onClose, onPick }: { excludeFolderId?: string; onClose: () => void; onPick: (folderId: string | null) => Promise<void> }) {
  const [parentId, setParentId] = useState<string | null>(null);
  const [breadcrumb, setBreadcrumb] = useState<BreadcrumbItem[]>([]);
  const [folders, setFolders] = useState<FileFolder[]>([]);
  const [loading, setLoading] = useState(true);
  const [moving, setMoving] = useState(false);

  const load = useCallback((id: string | null) => {
    setLoading(true);
    browseFiles(id)
      .then(res => {
        setBreadcrumb(res.breadcrumb);
        setFolders(res.folders.filter(f => f.id !== excludeFolderId));
      })
      .catch(err => showToast(errMsg(err, 'Failed to browse'), 'error'))
      .finally(() => setLoading(false));
  }, [excludeFolderId]);

  useEffect(() => { load(parentId); }, [parentId, load]);

  const confirmMove = async () => {
    setMoving(true);
    try {
      await onPick(parentId);
      onClose();
    } catch (err) {
      showToast(errMsg(err, 'Move failed'), 'error');
    } finally {
      setMoving(false);
    }
  };

  return (
    <OverlayDialog
      title="Move to..."
      onClose={onClose}
      actions={
        <>
          <button onClick={onClose} className="j-btn" style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '8px 16px', fontSize: 13 }}>Cancel</button>
          <button onClick={confirmMove} disabled={moving} className="j-btn"
            style={{ background: J.amber, color: J.bg0, borderRadius: 8, padding: '8px 20px', fontSize: 13, fontWeight: 600 }}>
            {moving ? <Spinner size={13} color={J.bg0} /> : 'Move here'}
          </button>
        </>
      }
    >
      <div style={{ fontSize: 12, color: J.textSec, marginBottom: 10, display: 'flex', gap: 4, flexWrap: 'wrap', alignItems: 'center' }}>
        <span onClick={() => setParentId(null)} style={{ cursor: 'pointer', color: parentId === null ? J.amber : J.textSec }}>Home</span>
        {breadcrumb.map(b => (
          <span key={b.id} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <IconChevRight size={11} />
            <span onClick={() => setParentId(b.id)} style={{ cursor: 'pointer', color: b.id === parentId ? J.amber : J.textSec }}>{b.name}</span>
          </span>
        ))}
      </div>
      <div style={{ maxHeight: 220, overflowY: 'auto', border: `1px solid ${J.border}`, borderRadius: 8 }}>
        {loading && <div style={{ padding: 16, color: J.textMuted, fontSize: 12 }}><Spinner size={13} /> Loading...</div>}
        {!loading && folders.length === 0 && <div style={{ padding: 16, color: J.textMuted, fontSize: 12 }}>No subfolders here.</div>}
        {!loading && folders.map(f => (
          <div key={f.id} onClick={() => setParentId(f.id)}
            style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', cursor: 'pointer', borderBottom: `1px solid ${J.border}`, fontSize: 13, color: J.text }}>
            <IconFolder size={15} /> {f.name}
          </div>
        ))}
      </div>
    </OverlayDialog>
  );
}

function QuotaBar({ used, total }: { used: number; total: number }) {
  const pct = total > 0 ? Math.min(100, (used / total) * 100) : 0;
  const color = pct > 90 ? J.error : pct > 70 ? J.warn : J.success;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 200 }}>
      <div style={{ flex: 1, height: 6, background: J.bg3, borderRadius: 3, overflow: 'hidden', minWidth: 90 }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 3, transition: 'width .2s' }} />
      </div>
      <div style={{ fontSize: 11, color: J.textMuted, whiteSpace: 'nowrap' }}>{formatBytes(used)} / {formatBytes(total)}</div>
    </div>
  );
}

export function FilesScreen(_props: { onNavigate?: (screen: string) => void }) {
  useJ();
  const [parentId, setParentId] = useState<string | null>(null);
  const [breadcrumb, setBreadcrumb] = useState<BreadcrumbItem[]>([]);
  const [folders, setFolders] = useState<FileFolder[]>([]);
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [quota, setQuota] = useState<{ used_bytes: number; quota_bytes: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [renameTarget, setRenameTarget] = useState<{ kind: 'folder' | 'file'; id: string; name: string } | null>(null);
  const [moveTarget, setMoveTarget] = useState<{ kind: 'folder' | 'file'; id: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadQuota = () => fetchQuotaStatus().then(res => setQuota({ used_bytes: res.used_bytes, quota_bytes: res.quota_bytes })).catch(() => {});

  const load = useCallback((id: string | null) => {
    setLoading(true);
    setError(null);
    browseFiles(id)
      .then(res => {
        setBreadcrumb(res.breadcrumb);
        setFolders(res.folders);
        setFiles(res.files);
      })
      .catch(err => setError(errMsg(err, 'Failed to load files')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(parentId); }, [parentId, load]);
  useEffect(() => { loadQuota(); }, [parentId]);

  const navigateTo = (id: string | null) => setParentId(id);

  const doUpload = async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) return;
    setUploading(true);
    try {
      for (const file of Array.from(fileList)) {
        const res = await uploadFile(file, parentId);
        setFiles(prev => [...prev, res.file].sort((a, b) => a.filename.localeCompare(b.filename)));
      }
      showToast(fileList.length > 1 ? `${fileList.length} files uploaded` : 'File uploaded', 'success');
      loadQuota();
    } catch (err) {
      showToast(errMsg(err, 'Upload failed'), 'error');
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteFolder = async (folder: FileFolder) => {
    if (!window.confirm(`Delete "${folder.name}" and everything inside it? This cannot be undone.`)) return;
    try {
      await deleteFolder(folder.id);
      setFolders(prev => prev.filter(f => f.id !== folder.id));
      showToast('Folder deleted', 'info');
      loadQuota();
    } catch (err) {
      showToast(errMsg(err, 'Delete failed'), 'error');
    }
  };

  const handleDeleteFile = async (file: FileEntry) => {
    if (!window.confirm(`Delete "${file.filename}"? This cannot be undone.`)) return;
    try {
      await deleteFile(file.id);
      setFiles(prev => prev.filter(f => f.id !== file.id));
      showToast('File deleted', 'info');
      loadQuota();
    } catch (err) {
      showToast(errMsg(err, 'Delete failed'), 'error');
    }
  };

  const handleToggleJarvis = async (folder: FileFolder) => {
    try {
      const res = await setJarvisFolderAccess(folder.id, !folder.jarvis_access_granted);
      setFolders(prev => prev.map(f => (f.id === folder.id ? res.folder : f)));
      showToast(res.folder.jarvis_access_granted ? 'JARVIS can now access this folder' : 'JARVIS access revoked', 'info');
    } catch (err) {
      showToast(errMsg(err, 'Failed to update JARVIS access'), 'error');
    }
  };

  const handleDownload = async (file: FileEntry) => {
    try {
      await downloadFile(file.id, file.filename);
    } catch (err) {
      showToast(errMsg(err, 'Download failed'), 'error');
    }
  };

  const empty = !loading && !error && folders.length === 0 && files.length === 0;

  return (
    <div
      style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: J.bg0, position: 'relative' }}
      onDragOver={e => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={e => { e.preventDefault(); setDragOver(false); }}
      onDrop={e => { e.preventDefault(); setDragOver(false); void doUpload(e.dataTransfer.files); }}
    >
      <div style={{ minHeight: 50, borderBottom: `1px solid ${J.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 24px', background: J.bg1, flexShrink: 0, flexWrap: 'wrap', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, flexWrap: 'wrap' }}>
          <span onClick={() => navigateTo(null)} style={{ cursor: 'pointer', color: parentId === null ? J.text : J.textSec, fontWeight: parentId === null ? 600 : 400 }}>My Files</span>
          {breadcrumb.map(b => (
            <span key={b.id} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <IconChevRight size={11} />
              <span onClick={() => navigateTo(b.id)} style={{ cursor: 'pointer', color: b.id === parentId ? J.text : J.textSec, fontWeight: b.id === parentId ? 600 : 400 }}>{b.name}</span>
            </span>
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          {quota && <QuotaBar used={quota.used_bytes} total={quota.quota_bytes} />}
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => setShowCreate(true)} className="j-btn"
              style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '6px 12px', fontSize: 12, fontWeight: 500 }}>
              <IconPlus size={13} /> Folder
            </button>
            <button onClick={() => fileInputRef.current?.click()} disabled={uploading} className="j-btn"
              style={{ background: J.amberDim, border: `1px solid ${J.borderAccent}`, color: J.amber, borderRadius: 8, padding: '6px 14px', fontSize: 12, fontWeight: 500 }}>
              {uploading ? <Spinner size={13} /> : <IconUpload size={13} />} Upload
            </button>
            <input ref={fileInputRef} type="file" multiple style={{ display: 'none' }} onChange={e => { void doUpload(e.target.files); e.target.value = ''; }} />
          </div>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '22px 24px' }}>
        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: J.textMuted, fontSize: 13, padding: '24px 0' }}>
            <Spinner size={14} /> Loading...
          </div>
        )}

        {!loading && error && (
          <div style={{ background: J.errorDim, border: `1px solid ${J.error}`, borderRadius: 10, padding: '12px 16px', color: J.error, fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            {error}
            <button onClick={() => load(parentId)} style={{ background: 'none', border: 'none', color: J.error, cursor: 'pointer', display: 'flex' }}><IconX size={14} /></button>
          </div>
        )}

        {empty && (
          <div style={{ textAlign: 'center', color: J.textMuted, fontSize: 13, padding: '48px 0' }}>
            Empty. Drag and drop files here, or use Upload / Folder above.
          </div>
        )}

        {!loading && !error && folders.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(220px,1fr))', gap: 10, marginBottom: files.length > 0 ? 18 : 0 }}>
            {folders.map(folder => (
              <div key={folder.id} style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 12, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
                  <div onClick={() => navigateTo(folder.id)} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', overflow: 'hidden' }}>
                    <IconFolder size={17} />
                    <span style={{ fontSize: 13, fontWeight: 500, color: J.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{folder.name}</span>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                  <button onClick={() => handleToggleJarvis(folder)} title={folder.jarvis_access_granted ? 'JARVIS can access this folder — click to revoke' : 'Give JARVIS access to this folder'}
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 4, borderRadius: 5, padding: '2px 8px', fontSize: 10.5, fontWeight: 500, cursor: 'pointer', border: `1px solid ${folder.jarvis_access_granted ? J.borderAccent : J.border}`,
                      background: folder.jarvis_access_granted ? J.amberDim : 'transparent', color: folder.jarvis_access_granted ? J.amber : J.textMuted,
                    }}>
                    <IconZap size={10} /> {folder.jarvis_access_granted ? 'JARVIS' : 'Private'}
                  </button>
                  <div style={{ display: 'flex', gap: 5, marginLeft: 'auto' }}>
                    <IconButton onClick={() => setRenameTarget({ kind: 'folder', id: folder.id, name: folder.name })} title="Rename"><IconPencil size={12} /></IconButton>
                    <IconButton onClick={() => setMoveTarget({ kind: 'folder', id: folder.id })} title="Move"><IconFolder size={12} /></IconButton>
                    <IconButton onClick={() => handleDeleteFolder(folder)} title="Delete" danger><IconTrash size={12} /></IconButton>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {!loading && !error && files.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {files.map(file => (
              <div key={file.id} style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 10, padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
                <IconFile size={16} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, color: J.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{file.filename}</div>
                  <div style={{ fontSize: 11, color: J.textMuted }}>{formatBytes(file.size_bytes)}</div>
                </div>
                <div style={{ display: 'flex', gap: 5, flexShrink: 0 }}>
                  <IconButton onClick={() => handleDownload(file)} title="Download"><IconDownload size={12} /></IconButton>
                  <IconButton onClick={() => setRenameTarget({ kind: 'file', id: file.id, name: file.filename })} title="Rename"><IconPencil size={12} /></IconButton>
                  <IconButton onClick={() => setMoveTarget({ kind: 'file', id: file.id })} title="Move"><IconFolder size={12} /></IconButton>
                  <IconButton onClick={() => handleDeleteFile(file)} title="Delete" danger><IconTrash size={12} /></IconButton>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {dragOver && (
        <div style={{ position: 'absolute', inset: 0, background: J.amberGlow, border: `2px dashed ${J.amber}`, display: 'flex', alignItems: 'center', justifyContent: 'center', pointerEvents: 'none', zIndex: 20 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: J.amber, display: 'flex', alignItems: 'center', gap: 8 }}>
            <IconUpload size={18} /> Drop to upload
          </div>
        </div>
      )}

      {showCreate && (
        <CreateFolderModal
          onClose={() => setShowCreate(false)}
          onCreated={folder => { if (folder.parent_id === parentId) setFolders(prev => [...prev, folder].sort((a, b) => a.name.localeCompare(b.name))); }}
        />
      )}

      {renameTarget && (
        <RenameModal
          initialName={renameTarget.name}
          kind={renameTarget.kind}
          onClose={() => setRenameTarget(null)}
          onSubmit={async name => {
            if (renameTarget.kind === 'folder') {
              const res = await renameFolder(renameTarget.id, name);
              setFolders(prev => prev.map(f => (f.id === renameTarget.id ? res.folder : f)));
            } else {
              const res = await renameFile(renameTarget.id, name);
              setFiles(prev => prev.map(f => (f.id === renameTarget.id ? res.file : f)));
            }
            showToast('Renamed', 'success');
          }}
        />
      )}

      {moveTarget && (
        <MoveModal
          excludeFolderId={moveTarget.kind === 'folder' ? moveTarget.id : undefined}
          onClose={() => setMoveTarget(null)}
          onPick={async destinationId => {
            if (moveTarget.kind === 'folder') {
              await moveFolder(moveTarget.id, destinationId);
              setFolders(prev => prev.filter(f => f.id !== moveTarget.id));
            } else {
              await moveFile(moveTarget.id, destinationId);
              setFiles(prev => prev.filter(f => f.id !== moveTarget.id));
            }
            showToast('Moved', 'success');
          }}
        />
      )}
    </div>
  );
}
