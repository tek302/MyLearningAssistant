"""
GET /ingest/status?job_id=...: job state for async ingest (Week6).
1 DB connection per request (resolve user + job SELECT in same connection).
"""
import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..db.pool import resolve_user_id, with_connection
from ..utils.deps import get_user_id

router = APIRouter(prefix="/ingest", tags=["ingest"])


def _get_job_status_for_user(user_id: str, job_id: str):
    """Sync: one connection — resolve user then SELECT job by id and user_id. Ownership enforced: job must belong to current user."""
    with with_connection() as conn:
        with conn.cursor() as cur:
            user_uuid = resolve_user_id(cur, user_id)
            cur.execute(
                """
                SELECT id, state, progress, source_id, error
                FROM jobs
                WHERE id = %s AND user_id = %s
                """,
                (job_id, user_uuid),
            )
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            out = dict(zip(cols, row))
            for k in ("id", "source_id"):
                if out.get(k) is not None:
                    out[k] = str(out[k])
            return out


@router.get("/status")
async def get_ingest_status(
    user_id: Annotated[str, Depends(get_user_id)],
    job_id: str = Query(..., description="Job ID from POST /ingest"),
):
    """
    Return job state: { state, progress, source_id, error? }.
    Ownership enforced: job must belong to current user.
    """
    if not job_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="job_id required")
    job = await asyncio.to_thread(_get_job_status_for_user, user_id, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return {
        "state": job.get("state", "queued"),
        "progress": job.get("progress", 0),
        "source_id": job.get("source_id"),
        "error": job.get("error"),
    }
