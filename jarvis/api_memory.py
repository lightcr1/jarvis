from fastapi import APIRouter, Header, HTTPException

from .api_models import (
    MemoryAliasCreate,
    MemoryAliasResponse,
    MemoryNoteCreate,
    MemoryNoteResponse,
    MemorySummaryResponse,
)
from .router_dependencies import LiveRef


def build_memory_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if isinstance(value, LiveRef) else value

    require_identity_session = deps["require_identity_session"]

    @router.get("/memory/notes", response_model=list[MemoryNoteResponse])
    def list_notes(x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        user_id: str = session["user"]["id"]
        notes = current("memory_store").get_notes(user_id)
        return [MemoryNoteResponse(id=n["id"], text=n["text"], created_at=n["created_at"]) for n in notes]

    @router.post("/memory/notes", response_model=MemoryNoteResponse, status_code=201)
    def create_note(payload: MemoryNoteCreate, x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        user_id: str = session["user"]["id"]
        text = (payload.text or "").strip()
        if not text:
            raise HTTPException(422, "Note text cannot be empty.")
        note = current("memory_store").add_note(user_id, text)
        return MemoryNoteResponse(id=note["id"], text=note["text"], created_at=note["created_at"])

    @router.delete("/memory/notes/{note_id}", status_code=204)
    def delete_note(note_id: str, x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        user_id: str = session["user"]["id"]
        deleted = current("memory_store").delete_note(user_id, note_id)
        if not deleted:
            raise HTTPException(404, "Note not found.")

    @router.get("/memory/aliases", response_model=list[MemoryAliasResponse])
    def list_aliases(x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        user_id: str = session["user"]["id"]
        aliases = current("memory_store").get_aliases(user_id)
        return [
            MemoryAliasResponse(alias=k, target=v["target"], created_at=v["created_at"])
            for k, v in aliases.items()
        ]

    @router.post("/memory/aliases", response_model=MemoryAliasResponse, status_code=201)
    def create_alias(payload: MemoryAliasCreate, x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        user_id: str = session["user"]["id"]
        alias = (payload.alias or "").strip()
        target = (payload.target or "").strip()
        if not alias or not target:
            raise HTTPException(422, "Alias and target cannot be empty.")
        entry = current("memory_store").set_alias(user_id, alias, target)
        return MemoryAliasResponse(alias=alias, target=entry["target"], created_at=entry["created_at"])

    @router.delete("/memory/aliases/{alias}", status_code=204)
    def delete_alias(alias: str, x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        user_id: str = session["user"]["id"]
        deleted = current("memory_store").delete_alias(user_id, alias)
        if not deleted:
            raise HTTPException(404, "Alias not found.")

    @router.get("/memory/summary", response_model=MemorySummaryResponse)
    def memory_summary(x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        user_id: str = session["user"]["id"]
        store = current("memory_store")
        notes = store.get_notes(user_id)
        aliases = store.get_aliases(user_id)
        note_list = [MemoryNoteResponse(id=n["id"], text=n["text"], created_at=n["created_at"]) for n in notes]
        alias_list = [
            MemoryAliasResponse(alias=k, target=v["target"], created_at=v["created_at"])
            for k, v in aliases.items()
        ]
        return MemorySummaryResponse(
            notes=note_list,
            aliases=alias_list,
            note_count=len(note_list),
            alias_count=len(alias_list),
        )

    @router.delete("/memory/all", status_code=204)
    def clear_all_memory(
        confirm: bool = False,
        x_jarvis_session: str | None = Header(default=None),
    ):
        session = require_identity_session(x_jarvis_session)
        if not confirm:
            raise HTTPException(422, "Pass ?confirm=true to clear all memory.")
        user_id: str = session["user"]["id"]
        current("memory_store").clear_user(user_id)

    return router
