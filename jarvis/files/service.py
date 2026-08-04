from __future__ import annotations

import mimetypes
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Protocol

from .path_safety import PathSafetyError, resolve_within_root, sanitize_segment

DEFAULT_STORAGE_QUOTA_MB = 12000
DEFAULT_MAX_UPLOAD_MB = 2048
UPLOAD_CHUNK_BYTES = 1024 * 1024


def _emergency_stop_active() -> bool:
    return (os.getenv("JARVIS_EMERGENCY_STOP") or "0").strip().lower() in {"1", "true", "yes", "on"}


class FileAccessError(PermissionError):
    pass


class AsyncChunkReader(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


class FileService:
    def __init__(
        self,
        *,
        store,
        user_store,
        membership_store,
        permission_store,
        resolve_effective_permissions,
        normalize_role,
        user_limits_store,
        admin_settings_store,
        share_store=None,
        group_store=None,
        link_share_store=None,
        audit_log=None,
    ) -> None:
        self.store = store
        self.user_store = user_store
        self.membership_store = membership_store
        self.permission_store = permission_store
        self.resolve_effective_permissions = resolve_effective_permissions
        self.normalize_role = normalize_role
        self.user_limits_store = user_limits_store
        self.admin_settings_store = admin_settings_store
        self.share_store = share_store
        self.group_store = group_store
        self.link_share_store = link_share_store
        self.audit_log = audit_log

    def _write_audit(self, event: str, *, actor_user_id: str | None, actor_role: str | None, payload: dict | None = None) -> None:
        if not self.audit_log:
            return
        body = {
            "actor_user_id": actor_user_id,
            "actor_role": self.normalize_role(actor_role),
            **(payload or {}),
        }
        try:
            self.audit_log.write(event, body)
        except Exception:
            return

    def _effective_permissions(self, user_id: str | None, role: str | None) -> set[str]:
        return set(self.resolve_effective_permissions(self.normalize_role(role), user_id, self.membership_store, self.permission_store))

    def require_access(self, *, user_id: str | None, role: str | None, required_permission: str) -> dict[str, object]:
        normalized_role = self.normalize_role(role)
        effective = self._effective_permissions(user_id, role)
        if normalized_role != "admin" and required_permission not in effective:
            raise FileAccessError(f"missing permission: {required_permission}")
        return {"role": normalized_role, "effective_permissions": sorted(effective)}

    def _owned_folder(self, folder_id: str, *, user_id: str | None, role: str | None) -> dict:
        folder = self.store.get_folder(folder_id)
        if not folder:
            raise LookupError("folder not found")
        if folder.get("owner_user_id") != user_id and self.normalize_role(role) != "admin":
            raise LookupError("folder not found")
        return folder

    def _owned_file(self, file_id: str, *, user_id: str | None, role: str | None) -> dict:
        file_meta = self.store.get_file(file_id)
        if not file_meta:
            raise LookupError("file not found")
        if file_meta.get("owner_user_id") != user_id and self.normalize_role(role) != "admin":
            raise LookupError("file not found")
        return file_meta

    def _accessible_folder(self, folder_id: str, *, user_id: str | None, role: str | None) -> tuple[dict, str]:
        """Returns (folder, access) where access is 'owner' | 'write' | 'read'.
        Raises LookupError (404, not 403 — preserves existing existence-hiding
        behavior) if the folder doesn't exist or the caller has no access at all.
        Cascading: a share on any ancestor of this folder (including itself)
        grants access to this folder too — unlike jarvis_access_granted, which
        is deliberately non-cascading (see test_jarvis_access_is_per_folder_not_inherited).
        """
        folder = self.store.get_folder(folder_id)
        if not folder:
            raise LookupError("folder not found")
        if folder.get("owner_user_id") == user_id or self.normalize_role(role) == "admin":
            return folder, "owner"
        if self.share_store is None:
            raise LookupError("folder not found")
        user_group_ids = set(self.membership_store.list_user_groups(user_id or ""))
        best: str | None = None
        for ancestor in self.store.folder_ancestor_ids(folder_id):
            for share in self.share_store.list_shares_for_folder(ancestor["id"]):
                if share.get("group_id") not in user_group_ids:
                    continue
                if share.get("permission") == "write":
                    best = "write"
                elif best is None and share.get("permission") == "read":
                    best = "read"
        if best is None:
            raise LookupError("folder not found")
        return folder, best

    @staticmethod
    def _sanitize_name(raw: str) -> str:
        try:
            return sanitize_segment(raw)
        except PathSafetyError as exc:
            raise ValueError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Quota
    # ------------------------------------------------------------------

    def resolve_quota_bytes(self, user_id: str) -> int:
        limits = self.user_limits_store.get(user_id) if self.user_limits_store else {}
        override_mb = int((limits or {}).get("storage_quota_mb") or 0)
        if override_mb > 0:
            return override_mb * 1024 * 1024
        settings = self.admin_settings_store.get() if self.admin_settings_store else {}
        files_settings = (settings or {}).get("files") or {}
        default_mb = int(files_settings.get("default_storage_quota_mb") or DEFAULT_STORAGE_QUOTA_MB)
        return default_mb * 1024 * 1024

    def _max_upload_bytes(self) -> int:
        raw = os.getenv("JARVIS_FILES_MAX_UPLOAD_MB") or str(DEFAULT_MAX_UPLOAD_MB)
        try:
            mb = max(1, int(raw))
        except (TypeError, ValueError):
            mb = DEFAULT_MAX_UPLOAD_MB
        return mb * 1024 * 1024

    def quota_status(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="files.read")
        used = self.store.get_quota_usage_bytes(user_id or "")
        quota = self.resolve_quota_bytes(user_id or "")
        return {"policy": policy, "used_bytes": used, "quota_bytes": quota}

    # ------------------------------------------------------------------
    # Browsing
    # ------------------------------------------------------------------

    def _breadcrumb(self, owner_user_id: str, folder_id: str | None) -> list[dict]:
        trail: list[dict] = []
        current_id = folder_id
        seen: set[str] = set()
        while current_id:
            if current_id in seen:
                break
            seen.add(current_id)
            folder = self.store.get_folder(current_id)
            if not folder or folder.get("owner_user_id") != owner_user_id:
                break
            trail.append({"id": folder["id"], "name": folder["name"]})
            current_id = folder.get("parent_id")
        trail.reverse()
        return trail

    def browse(self, parent_id: str | None, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="files.read")
        owner_user_id = user_id or ""
        access = "owner"
        if parent_id:
            folder, access = self._accessible_folder(parent_id, user_id=user_id, role=role)
            owner_user_id = folder["owner_user_id"]
        folders = sorted(self.store.list_child_folders(owner_user_id, parent_id), key=lambda item: item.get("name", ""))
        files = sorted(self.store.list_files_in_folder(owner_user_id, parent_id), key=lambda item: item.get("filename", ""))
        breadcrumb = self._breadcrumb(owner_user_id, parent_id)
        owner_user = self.user_store.get_user(owner_user_id)
        return {
            "policy": policy, "parent_id": parent_id, "breadcrumb": breadcrumb, "folders": folders, "files": files,
            "owner_user_id": owner_user_id, "owner_username": (owner_user or {}).get("username"),
            "access": access,
        }

    # ------------------------------------------------------------------
    # Folder CRUD
    # ------------------------------------------------------------------

    def create_folder(self, payload: dict[str, object], *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="files.write")
        name = self._sanitize_name(str((payload or {}).get("name") or ""))
        parent_id = (payload or {}).get("parent_id") or None
        owner = user_id or ""
        if parent_id:
            parent_folder, access = self._accessible_folder(str(parent_id), user_id=user_id, role=role)
            if access == "read":
                raise FileAccessError("read-only access to this shared folder")
            owner = parent_folder["owner_user_id"]
        if self.store.find_folder_by_name(owner, parent_id, name):
            raise ValueError("a folder with this name already exists here")
        if self.store.find_file_by_name(owner, parent_id, name):
            raise ValueError("a file with this name already exists here")

        parent_dir = self.store.folder_disk_path(owner, parent_id)
        disk_path = resolve_within_root(parent_dir, name)
        try:
            disk_path.mkdir(parents=False, exist_ok=False)
        except FileExistsError as exc:
            raise ValueError("a file or folder with this name already exists here") from exc

        now = int(time.time())
        folder = self.store.add_folder(
            {
                "id": f"folder-{uuid.uuid4().hex[:12]}",
                "parent_id": parent_id,
                "name": name,
                "owner_user_id": owner,
                "jarvis_access_granted": False,
                "created_at": now,
                "updated_at": now,
            }
        )
        self._write_audit("file_folder_created", actor_user_id=user_id, actor_role=role, payload={"folder_id": folder["id"], "name": name})
        return {"policy": policy, "folder": folder}

    def update_folder(self, folder_id: str, payload: dict[str, object], *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="files.write")
        folder = self._owned_folder(folder_id, user_id=user_id, role=role)
        owner = folder["owner_user_id"]
        old_dir = self.store.folder_disk_path(owner, folder_id)

        new_name = folder["name"]
        new_parent_id = folder.get("parent_id")
        payload = payload or {}
        if "name" in payload:
            new_name = self._sanitize_name(str(payload["name"] or ""))
        if "parent_id" in payload:
            candidate_parent = payload["parent_id"] or None
            if candidate_parent == folder_id:
                raise ValueError("a folder cannot be moved into itself")
            if candidate_parent:
                self._owned_folder(str(candidate_parent), user_id=user_id, role=role)
                if self.store.is_descendant(str(candidate_parent), folder_id):
                    raise ValueError("cannot move a folder into its own subfolder")
            new_parent_id = candidate_parent

        sibling_folder = self.store.find_folder_by_name(owner, new_parent_id, new_name)
        if sibling_folder and sibling_folder["id"] != folder_id:
            raise ValueError("a folder with this name already exists there")
        sibling_file = self.store.find_file_by_name(owner, new_parent_id, new_name)
        if sibling_file:
            raise ValueError("a file with this name already exists there")

        new_parent_dir = self.store.folder_disk_path(owner, new_parent_id)
        new_dir = resolve_within_root(new_parent_dir, new_name)
        if new_dir != old_dir:
            if new_dir.exists():
                raise ValueError("target path already exists")
            os.rename(old_dir, new_dir)

        updated = self.store.update_folder(folder_id, {"name": new_name, "parent_id": new_parent_id, "updated_at": int(time.time())})
        self._write_audit("file_folder_updated", actor_user_id=user_id, actor_role=role, payload={"folder_id": folder_id})
        return {"policy": policy, "folder": updated}

    def delete_folder(self, folder_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="files.manage")
        folder = self._owned_folder(folder_id, user_id=user_id, role=role)
        owner = folder["owner_user_id"]
        disk_path = self.store.folder_disk_path(owner, folder_id)

        descendant_ids = self.store.collect_descendant_folder_ids(owner, folder_id)
        freed_bytes = 0
        for fid in descendant_ids:
            for file_meta in self.store.list_files_in_folder(owner, fid):
                freed_bytes += int(file_meta.get("size_bytes") or 0)

        if disk_path.exists():
            shutil.rmtree(disk_path)

        for fid in descendant_ids:
            self.store.delete_files_in_folder(owner, fid)
        for fid in reversed(descendant_ids):
            self.store.delete_folder(fid)
        if self.share_store is not None:
            for fid in descendant_ids:
                self.share_store.remove_shares_for_folder(fid)

        if freed_bytes:
            self.store.adjust_quota_usage_bytes(owner, -freed_bytes)

        self._write_audit(
            "file_folder_deleted",
            actor_user_id=user_id,
            actor_role=role,
            payload={"folder_id": folder_id, "freed_bytes": freed_bytes},
        )
        return {"policy": policy, "deleted": True, "freed_bytes": freed_bytes}

    # ------------------------------------------------------------------
    # JARVIS per-folder access grants — distinct from files.read/write/manage.
    # Owner (or admin) only; this is the primitive future chat/skill code
    # must call via jarvis_can_access_folder() before touching file content.
    # ------------------------------------------------------------------

    def grant_jarvis_folder_access(self, folder_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="files.write")
        self._owned_folder(folder_id, user_id=user_id, role=role)
        updated = self.store.update_folder(folder_id, {"jarvis_access_granted": True, "updated_at": int(time.time())})
        self._write_audit("file_jarvis_access_granted", actor_user_id=user_id, actor_role=role, payload={"folder_id": folder_id})
        return {"policy": policy, "folder": updated}

    def revoke_jarvis_folder_access(self, folder_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="files.write")
        self._owned_folder(folder_id, user_id=user_id, role=role)
        updated = self.store.update_folder(folder_id, {"jarvis_access_granted": False, "updated_at": int(time.time())})
        self._write_audit("file_jarvis_access_revoked", actor_user_id=user_id, actor_role=role, payload={"folder_id": folder_id})
        return {"policy": policy, "folder": updated}

    def jarvis_can_access_folder(self, folder_id: str) -> bool:
        folder = self.store.get_folder(folder_id)
        return bool(folder and folder.get("jarvis_access_granted"))

    # ------------------------------------------------------------------
    # File CRUD
    # ------------------------------------------------------------------

    async def upload_file(
        self,
        *,
        folder_id: str | None,
        filename: str,
        reader: AsyncChunkReader,
        content_type: str | None,
        user_id: str | None,
        role: str | None,
    ) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="files.write")
        clean_name = self._sanitize_name(filename or "")
        owner = user_id or ""
        if folder_id:
            folder, access = self._accessible_folder(folder_id, user_id=user_id, role=role)
            if access == "read":
                raise FileAccessError("read-only access to this shared folder")
            owner = folder["owner_user_id"]
        if self.store.find_file_by_name(owner, folder_id, clean_name):
            raise ValueError("a file with this name already exists in this folder")
        if self.store.find_folder_by_name(owner, folder_id, clean_name):
            raise ValueError("a folder with this name already exists here")

        target_dir = self.store.folder_disk_path(owner, folder_id)
        target_dir.mkdir(parents=True, exist_ok=True)

        used_bytes = self.store.get_quota_usage_bytes(owner)
        quota_bytes = self.resolve_quota_bytes(owner)
        remaining = quota_bytes - used_bytes
        if remaining <= 0:
            raise ValueError("storage quota exceeded")
        max_upload_bytes = self._max_upload_bytes()
        limit = min(remaining, max_upload_bytes)

        fd, tmp_path_str = tempfile.mkstemp(dir=str(target_dir), prefix=".upload-")
        tmp_path = Path(tmp_path_str)
        total = 0
        try:
            with os.fdopen(fd, "wb") as handle:
                while True:
                    chunk = await reader.read(UPLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limit:
                        reason = "upload exceeds remaining storage quota" if remaining < max_upload_bytes else "upload exceeds maximum upload size"
                        raise ValueError(reason)
                    handle.write(chunk)

            final_path = resolve_within_root(target_dir, clean_name)
            if final_path.exists():
                raise ValueError("a file with this name already exists in this folder")
            os.replace(tmp_path, final_path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

        now = int(time.time())
        mime_type = content_type or mimetypes.guess_type(clean_name)[0] or "application/octet-stream"
        file_meta = self.store.add_file(
            {
                "id": f"file-{uuid.uuid4().hex[:12]}",
                "folder_id": folder_id,
                "filename": clean_name,
                "size_bytes": total,
                "mime_type": mime_type,
                "owner_user_id": owner,
                "created_at": now,
                "updated_at": now,
            }
        )
        self.store.adjust_quota_usage_bytes(owner, total)
        self._write_audit(
            "file_uploaded",
            actor_user_id=user_id,
            actor_role=role,
            payload={"file_id": file_meta["id"], "filename": clean_name, "size_bytes": total},
        )
        return {"policy": policy, "file": file_meta}

    def update_file(self, file_id: str, payload: dict[str, object], *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="files.write")
        file_meta = self._owned_file(file_id, user_id=user_id, role=role)
        owner = file_meta["owner_user_id"]
        old_path = self.store.file_disk_path(file_meta)

        new_filename = file_meta["filename"]
        new_folder_id = file_meta.get("folder_id")
        payload = payload or {}
        if "filename" in payload:
            new_filename = self._sanitize_name(str(payload["filename"] or ""))
        if "folder_id" in payload:
            candidate = payload["folder_id"] or None
            if candidate:
                self._owned_folder(str(candidate), user_id=user_id, role=role)
            new_folder_id = candidate

        existing_file = self.store.find_file_by_name(owner, new_folder_id, new_filename)
        if existing_file and existing_file["id"] != file_id:
            raise ValueError("a file with this name already exists there")
        if self.store.find_folder_by_name(owner, new_folder_id, new_filename):
            raise ValueError("a folder with this name already exists there")

        new_dir = self.store.folder_disk_path(owner, new_folder_id)
        new_path = resolve_within_root(new_dir, new_filename)
        if new_path != old_path:
            if new_path.exists():
                raise ValueError("target file already exists")
            os.rename(old_path, new_path)

        updated = self.store.update_file(file_id, {"filename": new_filename, "folder_id": new_folder_id, "updated_at": int(time.time())})
        self._write_audit("file_updated", actor_user_id=user_id, actor_role=role, payload={"file_id": file_id})
        return {"policy": policy, "file": updated}

    def delete_file(self, file_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="files.manage")
        file_meta = self._owned_file(file_id, user_id=user_id, role=role)
        disk_path = self.store.file_disk_path(file_meta)
        if disk_path.exists():
            disk_path.unlink()
        self.store.delete_file(file_id)
        self.store.adjust_quota_usage_bytes(file_meta["owner_user_id"], -int(file_meta.get("size_bytes") or 0))
        self._write_audit("file_deleted", actor_user_id=user_id, actor_role=role, payload={"file_id": file_id})
        return {"policy": policy, "deleted": True}

    def resolve_download(self, file_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="files.read")
        file_meta = self.store.get_file(file_id)
        if not file_meta:
            raise LookupError("file not found")
        is_owner = file_meta.get("owner_user_id") == user_id or self.normalize_role(role) == "admin"
        if not is_owner:
            folder_id = file_meta.get("folder_id")
            if not folder_id:
                raise LookupError("file not found")
            self._accessible_folder(folder_id, user_id=user_id, role=role)
        disk_path = self.store.file_disk_path(file_meta)
        if not disk_path.is_file():
            raise LookupError("file content missing on disk")
        return {"policy": policy, "file": file_meta, "disk_path": disk_path}

    # ------------------------------------------------------------------
    # Folder sharing via existing Groups — resource-scoped grants, distinct
    # from files.read/write/manage/share (the global permission gates).
    # ------------------------------------------------------------------

    def list_my_groups(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        """All groups' id/name (no description, no membership) — the picker for
        "share with group X" needs every group that exists, not just ones the
        sharer happens to belong to (e.g. sharing with a "Kids" group the owner
        administers but isn't a member of). Membership itself stays private —
        this never reveals who's in a group, only that the group exists.
        """
        policy = self.require_access(user_id=user_id, role=role, required_permission="files.read")
        groups = [{"id": g["id"], "name": g["name"]} for g in self.group_store.list_groups()]
        groups.sort(key=lambda g: g["name"])
        return {"policy": policy, "groups": groups}

    def share_folder(self, folder_id: str, group_id: str, permission: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="files.share")
        self._owned_folder(folder_id, user_id=user_id, role=role)
        if permission not in ("read", "write"):
            raise ValueError("permission must be 'read' or 'write'")
        if not self.group_store.get_group(group_id):
            raise ValueError("group not found")
        share = self.share_store.add_share(folder_id, group_id, permission, user_id or "")
        self._write_audit(
            "files_folder_shared", actor_user_id=user_id, actor_role=role,
            payload={"folder_id": folder_id, "group_id": group_id, "permission": permission},
        )
        return {"policy": policy, "share": share}

    def unshare_folder(self, share_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="files.share")
        share = self.share_store.get_share(share_id)
        if not share:
            raise LookupError("share not found")
        self._owned_folder(share["folder_id"], user_id=user_id, role=role)
        deleted = self.share_store.remove_share(share_id)
        self._write_audit(
            "files_folder_unshared", actor_user_id=user_id, actor_role=role,
            payload={"share_id": share_id, "folder_id": share["folder_id"]},
        )
        return {"policy": policy, "deleted": deleted}

    def list_folder_shares(self, folder_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="files.share")
        self._owned_folder(folder_id, user_id=user_id, role=role)
        enriched = []
        for share in self.share_store.list_shares_for_folder(folder_id):
            group = self.group_store.get_group(share.get("group_id"))
            enriched.append({**share, "group_name": (group or {}).get("name") or "(deleted group)"})
        enriched.sort(key=lambda s: s.get("created_at", 0))
        return {"policy": policy, "shares": enriched}

    def list_shared_with_me(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="files.read")
        seen_folder_ids: set[str] = set()
        entries = []
        for group_id in self.membership_store.list_user_groups(user_id or ""):
            for share in self.share_store.list_shares_for_group(group_id):
                folder_id = share.get("folder_id")
                if folder_id in seen_folder_ids:
                    continue
                folder = self.store.get_folder(folder_id)
                if not folder:
                    continue
                seen_folder_ids.add(folder_id)
                owner_user = self.user_store.get_user(folder["owner_user_id"])
                entries.append({
                    "folder": folder,
                    "owner_username": (owner_user or {}).get("username"),
                    "access": share.get("permission"),
                })
        entries.sort(key=lambda e: e["folder"].get("name", ""))
        return {"policy": policy, "shared": entries}

    # ── Public single-file share links ─────────────────────────────────────
    def create_share_link(self, file_id: str, payload: dict[str, object], *, user_id: str | None, role: str | None) -> dict[str, object]:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="files.share")
        self._owned_file(file_id, user_id=user_id, role=role)
        expires_at = (payload or {}).get("expires_at")
        password = (payload or {}).get("password") or None
        share = self.link_share_store.create_share(
            file_id, user_id or "", expires_at=int(expires_at) if expires_at else None, password=password,
        )
        self._write_audit(
            "files_share_link_created", actor_user_id=user_id, actor_role=role,
            payload={"file_id": file_id, "share_id": share["id"]},
        )
        return {"policy": policy, "share": self._sanitize_share(share)}

    def list_share_links(self, file_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="files.share")
        self._owned_file(file_id, user_id=user_id, role=role)
        shares = self.link_share_store.list_shares_for_file(file_id)
        shares.sort(key=lambda s: s.get("created_at", 0))
        return {"policy": policy, "shares": [self._sanitize_share(s) for s in shares]}

    @staticmethod
    def _sanitize_share(share: dict) -> dict:
        # password_hash carries the salted PBKDF2 hash — never send it to the
        # client, only whether a password is set.
        sanitized = {k: v for k, v in share.items() if k != "password_hash"}
        sanitized["has_password"] = bool(share.get("password_hash"))
        return sanitized

    def revoke_share_link(self, share_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="files.share")
        share = self.link_share_store.get_share(share_id)
        if not share:
            raise LookupError("share not found")
        self._owned_file(share["file_id"], user_id=user_id, role=role)
        deleted = self.link_share_store.remove_share(share_id)
        self._write_audit(
            "files_share_link_revoked", actor_user_id=user_id, actor_role=role,
            payload={"share_id": share_id, "file_id": share["file_id"]},
        )
        return {"policy": policy, "deleted": deleted}

    def get_public_share_info(self, token: str) -> dict[str, object]:
        share = self.link_share_store.get_by_token(token)
        if not share or self.link_share_store.is_expired(share):
            raise LookupError("share not found")
        file_meta = self.store.get_file(share["file_id"])
        if not file_meta:
            raise LookupError("share not found")
        return {
            "filename": file_meta["filename"],
            "size_bytes": file_meta.get("size_bytes"),
            "mime_type": file_meta.get("mime_type"),
            "requires_password": bool(share.get("password_hash")),
        }

    def resolve_public_download(self, token: str, *, password: str | None = None) -> tuple[Path, dict]:
        share = self.link_share_store.get_by_token(token)
        if not share or self.link_share_store.is_expired(share):
            raise LookupError("share not found")
        if not self.link_share_store.verify_password(share, password):
            raise PermissionError("incorrect password")
        file_meta = self.store.get_file(share["file_id"])
        if not file_meta:
            raise LookupError("share not found")
        disk_path = self.store.file_disk_path(file_meta)
        if not disk_path.is_file():
            raise LookupError("file missing from disk")
        self.link_share_store.record_download(share["id"])
        return disk_path, file_meta
