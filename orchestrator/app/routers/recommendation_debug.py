"""
Recommendation explanation + generation run debug endpoints.
Corresponds to PERSONALIZED_MEMORY_EXECUTION_PLAN.md §4.3.
"""
import asyncio
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from ..db.repo import SupabaseRepo
from ..utils.deps import get_user_id

logger = logging.getLogger(__name__)
router = APIRouter(tags=["recommendations"])


@router.get("/recommendations/{recommendation_id}/explanation")
async def get_recommendation_explanation(
    user_id: Annotated[str, Depends(get_user_id)],
    recommendation_id: Annotated[str, Path()],
):
    """
    Keyword-traceable explanation: which keywords triggered this recommendation,
    score breakdown, and Stage 1 context.
    """
    repo = SupabaseRepo()
    explanation = await asyncio.to_thread(
        repo.get_recommendation_explanation, recommendation_id, user_id,
    )
    if explanation is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return explanation


@router.get("/recommendation-runs")
async def list_recommendation_runs(
    user_id: Annotated[str, Depends(get_user_id)],
    week_start: Optional[str] = Query(None),
    stage: Optional[str] = Query(None, pattern="^(stage1|stage2)$"),
    limit: int = Query(10, ge=1, le=50),
):
    """List recent recommendation generation runs (Stage 1 / Stage 2)."""
    repo = SupabaseRepo()
    runs = await asyncio.to_thread(
        repo.list_recommendation_generation_runs,
        user_id, week_start=week_start, stage=stage, limit=limit,
    )
    return {"runs": runs}
