from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from .router_dependencies import LiveRef


def build_tasks_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if isinstance(value, LiveRef) else value

    @router.get("/tasks")
    def list_tasks(status: str | None = None, x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("task_service").list_tasks(
                user_id=session["user"]["id"],
                role=session["user"]["role"],
                status=status,
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/tasks")
    def create_task(payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("task_service").create_task(
                payload,
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.patch("/tasks/{task_id}")
    def update_task(task_id: str, payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("task_service").update_task(
                task_id,
                payload,
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.delete("/tasks/{task_id}")
    def delete_task(task_id: str, x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("task_service").delete_task(
                task_id,
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/tasks/{task_id}/complete")
    def complete_task(task_id: str, x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("task_service").complete_task(
                task_id,
                user_id=session["user"]["id"],
                role=session["user"]["role"],
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/tasks/assignable-users")
    def assignable_users(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("task_service").list_assignable_users(
                user_id=session["user"]["id"], role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/tasks/my-groups")
    def my_groups(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("task_service").list_my_groups(
                user_id=session["user"]["id"], role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/tasks/shared-with-me")
    def shared_with_me(x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("task_service").list_shared_with_me(
                user_id=session["user"]["id"], role=session["user"]["role"],
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/tasks/{task_id}/shares")
    def share_task(task_id: str, payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("task_service").share_task(
                task_id, str((payload or {}).get("group_id") or ""), str((payload or {}).get("permission") or ""),
                user_id=session["user"]["id"], role=session["user"]["role"],
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.get("/tasks/{task_id}/shares")
    def list_task_shares(task_id: str, x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("task_service").list_task_shares(
                task_id, user_id=session["user"]["id"], role=session["user"]["role"],
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.delete("/tasks/shares/{share_id}")
    def unshare_task(share_id: str, x_jarvis_session: str | None = Header(default=None)):
        session = deps["require_identity_session"](x_jarvis_session)
        try:
            return current("task_service").unshare_task(
                share_id, user_id=session["user"]["id"], role=session["user"]["role"],
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    return router
