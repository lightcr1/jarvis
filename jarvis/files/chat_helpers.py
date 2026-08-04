from __future__ import annotations

# Personal file drive — JARVIS may only read folders explicitly granted via
# the Files screen (FileService.jarvis_can_access_folder). A folder that does
# not exist and a folder that exists but was never granted MUST produce the
# exact same denial reply — anything else lets chat be used to probe for
# folder names the caller can't see. Shared by the legacy regex skill
# (assistant_domain.py::_handle_file_drive_skill) and the list_folder/read_file
# tool-calling handlers (tool_registry_tools.py) so denial behavior never drifts.
DENIAL_TEMPLATE = "I don't have access to a folder called '{name}'. You can grant it from the Files screen."
READ_CAP_CHARS = 20000
TEXT_MIME_PREFIXES = ("text/",)
TEXT_MIME_EXACT = {"application/json"}


def resolve_granted_folder(file_service, user_id: str, folder_name: str) -> dict | None:
    # v1 limitation: only top-level folders are resolved by name (parent_id=None).
    # Nested-path resolution (e.g. "Documents/Reports") is not supported here —
    # grants are per-folder and not inherited, so a child folder must be asked
    # about by its own name, which this skill cannot do yet.
    lowered = folder_name.strip().lower()
    folder = next(
        (f for f in file_service.store.list_child_folders(user_id, None) if (f.get("name") or "").lower() == lowered),
        None,
    )
    if not folder or not file_service.jarvis_can_access_folder(folder["id"]):
        return None
    return folder


def format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def list_folder(file_service, folder: dict, folder_name: str) -> dict[str, object]:
    files = file_service.store.list_files_in_folder(folder["owner_user_id"], folder["id"])
    if not files:
        return {"reply": f"Your '{folder_name}' folder is empty, sir.", "data": {"route": "file_drive_list", "folder_id": folder["id"], "files": []}}
    lines = [f"  • {f['filename']} ({format_size(f.get('size_bytes') or 0)})" for f in files[:15]]
    reply = f"On it. Here's what's in '{folder_name}':\n" + "\n".join(lines)
    return {"reply": reply, "data": {"route": "file_drive_list", "folder_id": folder["id"], "files": files}}


def list_all_folders(file_service, user_id: str) -> dict[str, object]:
    all_folders = file_service.store.list_child_folders(user_id, None)
    granted = [f for f in all_folders if file_service.jarvis_can_access_folder(f["id"])]
    if not granted:
        return {
            "reply": "I don't have access to any of your folders yet. You can grant one from the Files screen.",
            "data": {"route": "file_drive_list_all", "folders": []},
        }
    lines = []
    for folder in granted:
        count = len(file_service.store.list_files_in_folder(folder["owner_user_id"], folder["id"]))
        lines.append(f"  • {folder['name']} ({count} item{'s' if count != 1 else ''})")
    reply = "On it. Here's what I have access to:\n" + "\n".join(lines)
    return {"reply": reply, "data": {"route": "file_drive_list_all", "folders": [f["name"] for f in granted]}}


def find_file(file_service, folder: dict, filename: str) -> dict | None:
    lowered = filename.strip().lower()
    return next(
        (f for f in file_service.store.list_files_in_folder(folder["owner_user_id"], folder["id"]) if (f.get("filename") or "").lower() == lowered),
        None,
    )


def read_file(file_service, folder: dict, folder_name: str, filename: str) -> dict[str, object]:
    file_meta = find_file(file_service, folder, filename)
    if not file_meta:
        return {"reply": f"I can't find a file called '{filename}' in your '{folder_name}' folder.", "data": {"error": "file_not_found", "route": "file_drive_read"}}
    mime_type = file_meta.get("mime_type") or ""
    if not (mime_type.startswith(TEXT_MIME_PREFIXES) or mime_type in TEXT_MIME_EXACT):
        return {
            "reply": "I can see that file but can't read its content aloud — it's not a text file.",
            "data": {"route": "file_drive_read_refused", "file_id": file_meta["id"], "mime_type": mime_type},
        }
    disk_path = file_service.store.file_disk_path(file_meta)
    if not disk_path.is_file():
        return {"reply": f"'{filename}' is on record but missing from disk.", "data": {"error": "missing_on_disk", "route": "file_drive_read"}}
    content = disk_path.read_text(encoding="utf-8", errors="replace")[:READ_CAP_CHARS]
    return {"reply": f"Here's '{filename}':\n\n{content}", "data": {"route": "file_drive_read", "file_id": file_meta["id"]}}
