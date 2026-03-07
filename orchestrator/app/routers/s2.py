"""
POST /jobs/s2: enqueue S2 consolidation job for current user.
"""
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..db.repo import SupabaseRepo
from ..utils.deps import get_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])


class S2JobRequest(BaseModel):
    week_start: Optional[str] = None  # YYYY-MM-DD, optional; server uses current week if omitted


@router.post("/s2")
async def create_s2_job(
    body: S2JobRequest = S2JobRequest(),
    user_id: Annotated[str, Depends(get_user_id)] = None,
):
    """Enqueue one S2 consolidation job for the current user. Optional body: { \"week_start\": \"YYYY-MM-DD\" }."""
    repo = SupabaseRepo()
    payload = {"week_start": body.week_start} if body.week_start else None
    job_id = repo.create_job(user_id=user_id, job_type="s2", source_id=None, payload=payload)
    logger.info("s2 job created user_id=%s job_id=%s week_start=%s", user_id, job_id, body.week_start)
    return {"job_id": job_id, "status": "queued"}
