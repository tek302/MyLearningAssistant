"""
GET /notes: list notes for current user (optional filter by source_id).
POST /notes: create a note (body: source_id?, topic?, content).
DELETE /notes/{note_id}: delete a note (ownership enforced).
"""
import asyncio
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from ..db.repo import SupabaseRepo
from ..utils.deps import get_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notes", tags=["notes"])


class CreateNoteBody(BaseModel):
    """Request body for POST /notes."""

    content: str = Field(..., min_length=1, description="Note content (required)")
    source_id: Optional[str] = Field(None, description="Document (source) ID this note is attached to")
    topic: Optional[str] = Field(None, description="Short title/topic for the note")


@router.get("")
async def list_notes(
    user_id: Annotated[str, Depends(get_user_id)],
    source_id: Optional[str] = Query(None, description="Filter by document (source) ID"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Return notes for the current user (newest first). Optional source_id filter."""
    repo = SupabaseRepo()
    items = await asyncio.to_thread(
        repo.list_notes_for_user,
        user_id,
        source_id=source_id,
        limit=limit,
        offset=offset,
    )
    return {"notes": items}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_note(
    user_id: Annotated[str, Depends(get_user_id)],
    body: CreateNoteBody,
):
    """Create a note. Optionally attach to a document via source_id."""
    repo = SupabaseRepo()
    try:
        note_id = await asyncio.to_thread(
            repo.insert_note,
            user_id,
            content=body.content,
            source_id=body.source_id,
            topic=body.topic,
        )
    except Exception as e:
        logger.exception("create_note failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create note",
        ) from e
    # Return created note (fetch so we return full object with created_at)
    notes = await asyncio.to_thread(
        repo.list_notes_for_user,
        user_id,
        limit=1,
        offset=0,
    )
    created = next((n for n in notes if n["id"] == note_id), None)
    if created:
        return created
    return {"id": note_id, "source_id": body.source_id, "topic": body.topic, "content": body.content, "created_at": None}


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    user_id: Annotated[str, Depends(get_user_id)],
    note_id: Annotated[str, Path(description="Note ID to delete")],
):
    """Delete a note. Ownership enforced."""
    repo = SupabaseRepo()
    deleted = await asyncio.to_thread(repo.delete_note, note_id, user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
