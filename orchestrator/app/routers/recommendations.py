"""
GET /recommendations: list recommendations for current user.
DELETE /recommendations/{id}: remove one recommendation (ownership enforced).
"""
import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from ..db.repo import SupabaseRepo
from ..utils.deps import get_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("")
async def list_recommendations(
    user_id: Annotated[str, Depends(get_user_id)],
    week_start: str | None = Query(None, description="Filter by week_start (YYYY-MM-DD)"),
    topic_name: str | None = Query(None, description="Filter by topic_name"),
    limit: int = Query(50, ge=1, le=100),
):
    """Return recommendations for the current user (newest first). Optional week_start, topic_name filter."""
    repo = SupabaseRepo()
    items = await asyncio.to_thread(
        repo.list_recommendations,
        user_id,
        week_start=week_start,
        topic_name=topic_name,
        limit=limit,
    )
    return {"recommendations": items}


@router.delete("/{recommendation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recommendation(
    user_id: Annotated[str, Depends(get_user_id)],
    recommendation_id: Annotated[str, Path(description="Recommendation ID")],
):
    """Remove one recommendation from the list. Ownership enforced."""
    repo = SupabaseRepo()
    deleted = await asyncio.to_thread(repo.delete_recommendation, recommendation_id, user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")
