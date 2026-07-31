from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .path_safety import resolve_within_root


class FileStore:
    def __init__(self) -> None:
        configured_meta = os.getenv("JARVIS_FILES_STORE_PATH")
        self.metadata_path = Path(configured_meta) if configured_meta else Path("/var/lib/jarvis/files_metadata.json")
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)

        configured_root = os.getenv("JARVIS_USER_FILES_PATH")
        self.storage_root = Path(configured_root) if configured_root else Path("/var/lib/jarvis/user_files")
        self.storage_root.mkdir(parents=True, exist_ok=True)

        self.data = self._load()

    def _empty(self) -> dict:
        return {"folders": [], "files": [], "quota_usage": {}, "updated_at": 0}

    def _load(self) -> dict:
        if not self.metadata_path.exists():
            return self._empty()
        try:
            content = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            merged = {**self._empty(), **content}
            if not isinstance(merged.get("folders"), list):
                merged["folders"] = []
            if not isinstance(merged.get("files"), list):
                merged["files"] = []
            if not isinstance(merged.get("quota_usage"), dict):
                merged["quota_usage"] = {}
            return merged
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        self.data["updated_at"] = int(time.time())
        self.metadata_path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Disk path resolution — the on-disk tree is the source of truth for
    # structure; this is the only place that turns metadata into paths.
    # ------------------------------------------------------------------

    def user_root_path(self, owner_user_id: str) -> Path:
        root = resolve_within_root(self.storage_root, owner_user_id)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _ancestor_segments(self, owner_user_id: str, folder_id: str) -> list[str]:
        segments: list[str] = []
        current_id: str | None = folder_id
        seen: set[str] = set()
        while current_id:
            if current_id in seen:
                raise ValueError("folder hierarchy contains a cycle")
            seen.add(current_id)
            folder = self.get_folder(current_id)
            if not folder or folder.get("owner_user_id") != owner_user_id:
                raise LookupError("folder not found")
            segments.append(folder["name"])
            current_id = folder.get("parent_id")
        segments.reverse()
        return segments

    def folder_ancestor_ids(self, folder_id: str) -> list[dict]:
        """Walks parent_id up to the root, self first — unlike _ancestor_segments,
        does NOT assert a single owner_user_id, since this is used to check
        cross-owner share grants at every level of a folder's ancestor chain.
        """
        chain: list[dict] = []
        current_id: str | None = folder_id
        seen: set[str] = set()
        while current_id:
            if current_id in seen:
                break
            seen.add(current_id)
            folder = self.get_folder(current_id)
            if not folder:
                break
            chain.append(folder)
            current_id = folder.get("parent_id")
        return chain

    def folder_disk_path(self, owner_user_id: str, folder_id: str | None) -> Path:
        root = self.user_root_path(owner_user_id)
        if folder_id is None:
            return root
        segments = self._ancestor_segments(owner_user_id, folder_id)
        return resolve_within_root(root, *segments)

    def file_disk_path(self, file_meta: dict) -> Path:
        folder_dir = self.folder_disk_path(file_meta["owner_user_id"], file_meta.get("folder_id"))
        return resolve_within_root(folder_dir, file_meta["filename"])

    # ------------------------------------------------------------------
    # Folders
    # ------------------------------------------------------------------

    def list_child_folders(self, owner_user_id: str, parent_id: str | None) -> list[dict]:
        return [
            dict(item)
            for item in self.data.get("folders", [])
            if item.get("owner_user_id") == owner_user_id and item.get("parent_id") == parent_id
        ]

    def get_folder(self, folder_id: str) -> dict | None:
        for item in self.data.get("folders", []):
            if item.get("id") == folder_id:
                return dict(item)
        return None

    def find_folder_by_name(self, owner_user_id: str, parent_id: str | None, name: str) -> dict | None:
        for item in self.data.get("folders", []):
            if (
                item.get("owner_user_id") == owner_user_id
                and item.get("parent_id") == parent_id
                and item.get("name") == name
            ):
                return dict(item)
        return None

    def add_folder(self, folder: dict) -> dict:
        self.data.setdefault("folders", []).append(folder)
        self._save()
        return folder

    def update_folder(self, folder_id: str, patch: dict) -> dict | None:
        folders = self.data.setdefault("folders", [])
        for idx, item in enumerate(folders):
            if item.get("id") != folder_id:
                continue
            updated = {**item, **patch}
            folders[idx] = updated
            self._save()
            return updated
        return None

    def delete_folder(self, folder_id: str) -> bool:
        folders = self.data.setdefault("folders", [])
        for idx, item in enumerate(folders):
            if item.get("id") == folder_id:
                folders.pop(idx)
                self._save()
                return True
        return False

    def is_descendant(self, folder_id: str, maybe_ancestor_id: str) -> bool:
        current = self.get_folder(folder_id)
        seen: set[str] = set()
        while current and current.get("parent_id"):
            pid = current["parent_id"]
            if pid == maybe_ancestor_id:
                return True
            if pid in seen:
                break
            seen.add(pid)
            current = self.get_folder(pid)
        return False

    def collect_descendant_folder_ids(self, owner_user_id: str, folder_id: str) -> list[str]:
        collected = [folder_id]
        frontier = [folder_id]
        while frontier:
            current_id = frontier.pop()
            children = self.list_child_folders(owner_user_id, current_id)
            for child in children:
                collected.append(child["id"])
                frontier.append(child["id"])
        return collected

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    def list_files_in_folder(self, owner_user_id: str, folder_id: str | None) -> list[dict]:
        return [
            dict(item)
            for item in self.data.get("files", [])
            if item.get("owner_user_id") == owner_user_id and item.get("folder_id") == folder_id
        ]

    def get_file(self, file_id: str) -> dict | None:
        for item in self.data.get("files", []):
            if item.get("id") == file_id:
                return dict(item)
        return None

    def find_file_by_name(self, owner_user_id: str, folder_id: str | None, filename: str) -> dict | None:
        for item in self.data.get("files", []):
            if (
                item.get("owner_user_id") == owner_user_id
                and item.get("folder_id") == folder_id
                and item.get("filename") == filename
            ):
                return dict(item)
        return None

    def add_file(self, file_meta: dict) -> dict:
        self.data.setdefault("files", []).append(file_meta)
        self._save()
        return file_meta

    def update_file(self, file_id: str, patch: dict) -> dict | None:
        files = self.data.setdefault("files", [])
        for idx, item in enumerate(files):
            if item.get("id") != file_id:
                continue
            updated = {**item, **patch}
            files[idx] = updated
            self._save()
            return updated
        return None

    def delete_file(self, file_id: str) -> bool:
        files = self.data.setdefault("files", [])
        for idx, item in enumerate(files):
            if item.get("id") == file_id:
                files.pop(idx)
                self._save()
                return True
        return False

    def delete_files_in_folder(self, owner_user_id: str, folder_id: str | None) -> int:
        files = self.data.setdefault("files", [])
        remaining = []
        removed = 0
        for item in files:
            if item.get("owner_user_id") == owner_user_id and item.get("folder_id") == folder_id:
                removed += 1
            else:
                remaining.append(item)
        if removed:
            self.data["files"] = remaining
            self._save()
        return removed

    # ------------------------------------------------------------------
    # Quota usage — a maintained running total so requests don't need a
    # recursive filesystem walk to answer "how much has this user used".
    # ------------------------------------------------------------------

    def get_quota_usage_bytes(self, owner_user_id: str) -> int:
        return int(self.data.get("quota_usage", {}).get(owner_user_id, 0))

    def adjust_quota_usage_bytes(self, owner_user_id: str, delta_bytes: int) -> int:
        usage = self.data.setdefault("quota_usage", {})
        current = int(usage.get(owner_user_id, 0))
        updated = max(0, current + int(delta_bytes))
        usage[owner_user_id] = updated
        self._save()
        return updated
