"""
GET /ingest/status?job_id=...: job state for async ingest (Week6).
1 DB connection per request (resolve user + job SELECT in same connection).
Returns state, progress, source_id, error (full message), error_code (simple code for 403/404/timeout),
and fail_code from sources when the job is tied to a source (PDF/url pipeline).
"""
import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..db.pool import resolve_user_id, with_connection
from ..utils.deps import get_user_id

router = APIRouter(prefix="/ingest", tags=["ingest"])
logger = logging.getLogger(__name__)


def _error_code_from_message(error: str | None) -> str | None:
    """Derive simple error_code from error message for client (403, 404, timeout)."""
    if not error:
        return None
    err = error.lower()
    if "403" in err:
        return "fetch_403"
    if "404" in err:
        return "fetch_404"
    if "timeout" in err or "timed out" in err:
        return "timeout"
    return "unknown"


def _get_job_status_for_user(user_id: str, job_id: str):
    """Sync: one connection — resolve user then SELECT job by id and user_id. Ownership enforced: job must belong to current user."""
    with with_connection() as conn:
        with conn.cursor() as cur:
            user_uuid = resolve_user_id(cur, user_id)
            cur.execute(
                """
                SELECT j.id, j.state, j.progress, j.source_id, j.error, s.fail_code AS source_fail_code
                FROM jobs j
                LEFT JOIN sources s
                  ON s.id = j.source_id AND s.user_id = j.user_id
                WHERE j.id = %s AND j.user_id = %s
                """,
                (job_id, user_uuid),
            )
            row = cur.fetchone()
            if not row:
                # Debug: check if job exists at all (any user) to distinguish 404 causes
                cur.execute(
                    "SELECT id, user_id FROM jobs WHERE id = %s",
                    (job_id,),
                )
                any_row = cur.fetchone()
                if any_row:
                    logger.warning(
                        "ingest_status: job_id=%s found but user_id mismatch (resolved_user=%s, job_owner=%s)",
                        job_id,
                        user_uuid,
                        any_row[1],
                    )
                else:
                    logger.warning(
                        "ingest_status: job_id=%s not found in DB (resolved_user=%s)",
                        job_id,
                        user_uuid,
                    )
                return None
            cols = [d[0] for d in cur.description]
            out = dict(zip(cols, row))
            for k in ("id", "source_id"):
                if out.get(k) is not None:
                    out[k] = str(out[k])
            # Expose as fail_code for clients (matches sources.fail_code)
            fc = out.pop("source_fail_code", None)
            out["fail_code"] = fc if fc is None or fc == "" else str(fc)
            return out


@router.get("/status")
async def get_ingest_status(
    user_id: Annotated[str, Depends(get_user_id)],
    job_id: str = Query(..., description="Job ID from POST /ingest"),
):
    """
    Return job state: { state, progress, source_id, error?, error_code?, fail_code? }.
    error_code is one of fetch_403, fetch_404, timeout, unknown (only when error is set).
    fail_code is the sources.fail_code when present (e.g. PDF_TOO_LARGE, URL_INGEST_ERROR).
    Ownership enforced: job must belong to current user.
    """
    if not job_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="job_id required")
    logger.info("ingest_status: request job_id=%s user_id=%s", job_id, user_id)
    job = await asyncio.to_thread(_get_job_status_for_user, user_id, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    error = job.get("error")
    out = {
        "state": job.get("state", "queued"),
        "progress": job.get("progress", 0),
        "source_id": job.get("source_id"),
        "error": error,
        "fail_code": job.get("fail_code"),
    }
    if error:
        out["error_code"] = _error_code_from_message(error)
    return out
