"""
CRUD for interest_threads (multi-thread learning tracks).
"""
import asyncio
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..db.repo import SupabaseRepo
from ..utils.deps import get_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/threads", tags=["threads"])


class CreateThreadBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    is_default: bool = False


class PatchThreadBody(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)


@router.get("")
async def list_threads(
    user_id: Annotated[str, Depends(get_user_id)],
    include_archived: bool = False,
):
    repo = SupabaseRepo()
    items = await asyncio.to_thread(repo.list_interest_threads, user_id, include_archived)
    return {"threads": items}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_thread(
    user_id: Annotated[str, Depends(get_user_id)],
    body: CreateThreadBody,
):
    repo = SupabaseRepo()
    try:
        tid = await asyncio.to_thread(
            repo.create_interest_thread,
            user_id,
            body.name,
            body.description,
            body.is_default,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    row = await asyncio.to_thread(repo.get_interest_thread, tid, user_id)
    return row or {"id": tid}


@router.patch("/{thread_id}")
async def patch_thread(
    user_id: Annotated[str, Depends(get_user_id)],
    thread_id: str,
    body: PatchThreadBody,
):
    repo = SupabaseRepo()
    ok = await asyncio.to_thread(
        repo.update_interest_thread,
        thread_id,
        user_id,
        name=body.name,
        description=body.description,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    row = await asyncio.to_thread(repo.get_interest_thread, thread_id, user_id)
    return row


@router.post("/{thread_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
async def archive_thread(
    user_id: Annotated[str, Depends(get_user_id)],
    thread_id: str,
):
    repo = SupabaseRepo()
    ok = await asyncio.to_thread(repo.archive_interest_thread, thread_id, user_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot archive (not found, or default thread)",
        )


@router.get("/{thread_id}/keyword-weights")
async def list_thread_keyword_weights(
    user_id: Annotated[str, Depends(get_user_id)],
    thread_id: str,
):
    repo = SupabaseRepo()
    if not await asyncio.to_thread(repo.get_interest_thread, thread_id, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    items = await asyncio.to_thread(repo.list_thread_keyword_weights, thread_id, user_id)
    return {"weights": items}


class UpsertWeightBody(BaseModel):
    user_keyword_id: str
    activation: float = Field(1.0, ge=0.0, le=1.0)
    weight_multiplier: float = Field(1.0, gt=0.0)


@router.put("/{thread_id}/keyword-weights")
async def put_thread_keyword_weight(
    user_id: Annotated[str, Depends(get_user_id)],
    thread_id: str,
    body: UpsertWeightBody,
):
    repo = SupabaseRepo()
    if not await asyncio.to_thread(repo.get_interest_thread, thread_id, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    try:
        await asyncio.to_thread(
            repo.upsert_thread_keyword_weight,
            thread_id,
            body.user_keyword_id,
            user_id,
            body.activation,
            body.weight_multiplier,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {"status": "ok"}
