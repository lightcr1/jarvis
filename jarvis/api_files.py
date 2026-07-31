from __future__ import annotations

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .router_dependencies import LiveRef


def build_files_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if isinstance(value, LiveRef) else value

    def _session_identity(x_jarvis_session: str | None) -> tuple[str, str]:
        session = deps["require_identity_session"](x_jarvis_session)
        user = session["user"]
        return user["id"], user["role"]

    @router.get("/files/browse")
    def browse(parent_id: str | None = None, x_jarvis_session: str | None = Header(default=None)):
        user_id, role = _session_identity(x_jarvis_session)
        try:
            return current("file_service").browse(parent_id, user_id=user_id, role=role)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/files/quota")
    def quota_status(x_jarvis_session: str | None = Header(default=None)):
        user_id, role = _session_identity(x_jarvis_session)
        try:
            return current("file_service").quota_status(user_id=user_id, role=role)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/files/folders")
    def create_folder(payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        user_id, role = _session_identity(x_jarvis_session)
        try:
            return current("file_service").create_folder(payload, user_id=user_id, role=role)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.patch("/files/folders/{folder_id}")
    def update_folder(folder_id: str, payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        user_id, role = _session_identity(x_jarvis_session)
        try:
            return current("file_service").update_folder(folder_id, payload, user_id=user_id, role=role)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.delete("/files/folders/{folder_id}")
    def delete_folder(folder_id: str, x_jarvis_session: str | None = Header(default=None)):
        user_id, role = _session_identity(x_jarvis_session)
        try:
            return current("file_service").delete_folder(folder_id, user_id=user_id, role=role)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.put("/files/folders/{folder_id}/jarvis-access")
    def set_jarvis_access(folder_id: str, payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        user_id, role = _session_identity(x_jarvis_session)
        granted = bool((payload or {}).get("granted", True))
        service = current("file_service")
        try:
            if granted:
                return service.grant_jarvis_folder_access(folder_id, user_id=user_id, role=role)
            return service.revoke_jarvis_folder_access(folder_id, user_id=user_id, role=role)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/files/upload")
    async def upload_file(
        file: UploadFile = File(...),
        folder_id: str | None = Form(default=None),
        x_jarvis_session: str | None = Header(default=None),
    ):
        user_id, role = _session_identity(x_jarvis_session)
        try:
            return await current("file_service").upload_file(
                folder_id=folder_id or None,
                filename=file.filename or "",
                reader=file,
                content_type=file.content_type,
                user_id=user_id,
                role=role,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/files/my-groups")
    def my_groups(x_jarvis_session: str | None = Header(default=None)):
        user_id, role = _session_identity(x_jarvis_session)
        try:
            return current("file_service").list_my_groups(user_id=user_id, role=role)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/files/shared-with-me")
    def shared_with_me(x_jarvis_session: str | None = Header(default=None)):
        user_id, role = _session_identity(x_jarvis_session)
        try:
            return current("file_service").list_shared_with_me(user_id=user_id, role=role)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/files/folders/{folder_id}/shares")
    def share_folder(folder_id: str, payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        user_id, role = _session_identity(x_jarvis_session)
        try:
            return current("file_service").share_folder(
                folder_id, str((payload or {}).get("group_id") or ""), str((payload or {}).get("permission") or ""),
                user_id=user_id, role=role,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/files/folders/{folder_id}/shares")
    def list_folder_shares(folder_id: str, x_jarvis_session: str | None = Header(default=None)):
        user_id, role = _session_identity(x_jarvis_session)
        try:
            return current("file_service").list_folder_shares(folder_id, user_id=user_id, role=role)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.delete("/files/shares/{share_id}")
    def unshare_folder(share_id: str, x_jarvis_session: str | None = Header(default=None)):
        user_id, role = _session_identity(x_jarvis_session)
        try:
            return current("file_service").unshare_folder(share_id, user_id=user_id, role=role)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/files/{file_id}/download")
    def download_file(file_id: str, x_jarvis_session: str | None = Header(default=None)):
        user_id, role = _session_identity(x_jarvis_session)
        try:
            result = current("file_service").resolve_download(file_id, user_id=user_id, role=role)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        file_meta = result["file"]
        return FileResponse(
            path=str(result["disk_path"]),
            filename=file_meta["filename"],
            media_type=file_meta.get("mime_type") or "application/octet-stream",
        )

    @router.patch("/files/{file_id}")
    def update_file(file_id: str, payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        user_id, role = _session_identity(x_jarvis_session)
        try:
            return current("file_service").update_file(file_id, payload, user_id=user_id, role=role)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.delete("/files/{file_id}")
    def delete_file(file_id: str, x_jarvis_session: str | None = Header(default=None)):
        user_id, role = _session_identity(x_jarvis_session)
        try:
            return current("file_service").delete_file(file_id, user_id=user_id, role=role)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    return router
