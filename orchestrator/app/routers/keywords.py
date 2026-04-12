"""
Keyword CRUD + Stage 1 suggestion accept/reject + keyword history.
Corresponds to PERSONALIZED_MEMORY_EXECUTION_PLAN.md §4.1, §4.1.B, §4.1.C.
"""
import asyncio
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from ..constants.keywords import USER_KEYWORD_MAX_CHARS
from ..db.repo import SupabaseRepo
from ..utils.deps import get_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/keywords", tags=["keywords"])


class CreateKeywordBody(BaseModel):
    """Raw keyword from client; strip + `USER_KEYWORD_MAX_CHARS` enforced in handler."""
    keyword: str = Field(..., min_length=1, max_length=2000)
    parent_keyword_id: Optional[str] = None


class UpdateKeywordBody(BaseModel):
    status: Optional[str] = Field(None, pattern="^(active|declining|archived)$")


# ─── Keyword CRUD ───


@router.get("")
async def list_keywords(
    user_id: Annotated[str, Depends(get_user_id)],
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=200),
):
    repo = SupabaseRepo()
    items = await asyncio.to_thread(
        repo.list_user_keywords, user_id, status=status_filter, limit=limit,
    )
    active = [k for k in items if k.get("status") == "active"]
    declining = [k for k in items if k.get("status") == "declining"]
    return {
        "items": items,
        "total_active": len(active),
        "total_declining": len(declining),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_keyword(
    user_id: Annotated[str, Depends(get_user_id)],
    body: CreateKeywordBody,
):
    s = body.keyword.strip()
    if not s:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Keyword cannot be empty")
    if len(s) > USER_KEYWORD_MAX_CHARS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Keyword must be at most {USER_KEYWORD_MAX_CHARS} characters. "
                "Use a short phrase; split long topics into multiple keywords."
            ),
        )
    repo = SupabaseRepo()
    try:
        kw_id = await asyncio.to_thread(
            repo.insert_user_keyword,
            user_id,
            keyword=s,
            source="user_explicit",
            parent_keyword_id=body.parent_keyword_id,
        )
    except Exception as e:
        if "uq_user_keywords_user_keyword_active" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Keyword already exists")
        logger.exception("create_keyword failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create keyword") from e
    return {"id": kw_id, "keyword": s, "status": "active"}


@router.patch("/{keyword_id}")
async def update_keyword(
    user_id: Annotated[str, Depends(get_user_id)],
    keyword_id: Annotated[str, Path()],
    body: UpdateKeywordBody,
):
    repo = SupabaseRepo()
    updated = await asyncio.to_thread(
        repo.update_user_keyword, keyword_id, user_id, status=body.status,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Keyword not found")
    return {"id": keyword_id, "updated": True}


@router.delete("/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_keyword(
    user_id: Annotated[str, Depends(get_user_id)],
    keyword_id: Annotated[str, Path()],
):
    repo = SupabaseRepo()
    archived = await asyncio.to_thread(repo.archive_user_keyword, keyword_id, user_id)
    if not archived:
        raise HTTPException(status_code=404, detail="Keyword not found")


# ─── Stage 1: Keyword Suggestions ───


@router.get("/suggestions")
async def list_suggestions(
    user_id: Annotated[str, Depends(get_user_id)],
    status_filter: Optional[str] = Query(None, alias="status"),
    week_start: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    repo = SupabaseRepo()
    items = await asyncio.to_thread(
        repo.list_keyword_suggestions, user_id,
        status=status_filter, week_start=week_start, limit=limit,
    )
    return {"items": items}


@router.post("/suggestions/{suggestion_id}/accept")
async def accept_suggestion(
    user_id: Annotated[str, Depends(get_user_id)],
    suggestion_id: Annotated[str, Path()],
):
    repo = SupabaseRepo()
    kw_id = await asyncio.to_thread(repo.accept_keyword_suggestion, suggestion_id, user_id)
    if kw_id is None:
        raise HTTPException(status_code=404, detail="Suggestion not found or already responded")
    return {"suggestion_id": suggestion_id, "status": "accepted", "created_keyword_id": kw_id}


@router.post("/suggestions/{suggestion_id}/reject")
async def reject_suggestion(
    user_id: Annotated[str, Depends(get_user_id)],
    suggestion_id: Annotated[str, Path()],
):
    repo = SupabaseRepo()
    ok = await asyncio.to_thread(repo.reject_keyword_suggestion, suggestion_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Suggestion not found or already responded")
    return {"suggestion_id": suggestion_id, "status": "rejected"}


# ─── Keyword History ───


@router.get("/history")
async def keyword_history(
    user_id: Annotated[str, Depends(get_user_id)],
    limit: int = Query(50, ge=1, le=200),
):
    """Combined timeline of keyword additions, suggestion accepts/rejects."""
    repo = SupabaseRepo()
    keywords = await asyncio.to_thread(repo.list_user_keywords, user_id, limit=limit)
    suggestions = await asyncio.to_thread(
        repo.list_keyword_suggestions, user_id, limit=limit,
    )
    events = []
    for k in keywords:
        events.append({
            "date": k.get("created_at"),
            "type": "user_added" if k["source"] == "user_explicit" else "suggestion_accepted",
            "keyword": k["keyword"],
            "weight_at_time": float(k["weight"]),
            "source": k["source"],
        })
    for s in suggestions:
        if s["status"] == "rejected":
            events.append({
                "date": s.get("responded_at") or s.get("created_at"),
                "type": "suggestion_rejected",
                "keyword": s["keyword"],
                "reason": s.get("reason", ""),
            })
        elif s["status"] == "pending":
            events.append({
                "date": s.get("created_at"),
                "type": "suggestion_pending",
                "keyword": s["keyword"],
                "reason": s.get("reason", ""),
            })
    events.sort(key=lambda e: e.get("date") or "", reverse=True)
    return {"events": events[:limit]}
