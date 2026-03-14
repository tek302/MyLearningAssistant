"""
Tick-driven worker: POST /worker/tick claims one queued job from DB and processes it.
POST /worker/s2-schedule: enqueue one S2 job per user with sources in last 7 days (Cloud Scheduler, Friday 00:00 ET).
Secured by X-Worker-Tick-Secret when WORKER_TICK_SECRET is set.
"""
import logging
import os
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request, HTTPException, status

from app.db.repo import SupabaseRepo
from app.worker.job_runner import process_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/worker", tags=["worker"])
STALE_RUNNING_JOB_MAX_AGE_MINUTES = 15


def _week_start_monday(dt: datetime) -> str:
    """Return ISO date (YYYY-MM-DD) of Monday of the week containing dt."""
    weekday = dt.weekday()
    monday = dt - timedelta(days=weekday)
    return monday.strftime("%Y-%m-%d")


def _check_worker_secret(request: Request) -> None:
    secret = os.getenv("WORKER_TICK_SECRET")
    if secret:
        if request.headers.get("X-Worker-Tick-Secret") != secret:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _cleanup_stale_jobs(repo: SupabaseRepo, limit: int = 1) -> list[dict]:
    """Clean a small number of stale running jobs before processing new work."""
    try:
        max_age_minutes = int(os.getenv("STALE_RUNNING_JOB_MAX_AGE_MINUTES", str(STALE_RUNNING_JOB_MAX_AGE_MINUTES)))
    except ValueError:
        max_age_minutes = STALE_RUNNING_JOB_MAX_AGE_MINUTES
    cleaned = repo.cleanup_stale_running_jobs(max_age_minutes=max_age_minutes, limit=limit)
    if cleaned:
        logger.warning(
            "worker: cleaned stale running jobs count=%d max_age_minutes=%d jobs=%s",
            len(cleaned),
            max_age_minutes,
            cleaned,
        )
    return cleaned


@router.post("/tick")
async def worker_tick(request: Request):
    """
    Claim one queued job from DB and process it (tick-driven ingest).
    When WORKER_TICK_SECRET is set, request must include header X-Worker-Tick-Secret matching it.
    Returns 200 with { "status": "ok", "processed": true|false [, "job_id": "..." ] }.
    """
    _check_worker_secret(request)
    repo = SupabaseRepo()
    cleaned = _cleanup_stale_jobs(repo, limit=1)
    job_id = repo.claim_one_queued_job()
    if job_id:
        logger.info("worker_tick: claimed job_id=%s", job_id)
        await process_job(job_id)
        return {"status": "ok", "processed": True, "job_id": job_id, "cleaned_stale_jobs": cleaned}
    return {"status": "ok", "processed": False, "cleaned_stale_jobs": cleaned}


@router.post("/cleanup-stale-jobs")
async def cleanup_stale_jobs(
    request: Request,
    limit: int = 10,
):
    """
    Mark stale running jobs as failed.
    For Cloud Scheduler or manual recovery when jobs were left running after a crash.
    Same auth as /worker/tick.
    """
    _check_worker_secret(request)
    repo = SupabaseRepo()
    cleaned = _cleanup_stale_jobs(repo, limit=max(1, min(limit, 100)))
    return {"status": "ok", "cleaned_count": len(cleaned), "jobs": cleaned}


@router.post("/s2-schedule")
async def worker_s2_schedule(request: Request):
    """
    Enqueue one S2 consolidation job per user that has at least one source in the last 7 days.
    For Cloud Scheduler: Friday 00:00 US Eastern (cron 0 0 * * 5, America/New_York).
    Same auth as /worker/tick: X-Worker-Tick-Secret when WORKER_TICK_SECRET is set.
    Returns { "status": "ok", "enqueued": N, "user_ids": [...] }.
    """
    _check_worker_secret(request)
    repo = SupabaseRepo()
    user_ids = repo.get_user_ids_with_sources_since(days=7)
    now = datetime.now(timezone.utc)
    week_start = _week_start_monday(now)
    enqueued = 0
    for uid in user_ids:
        repo.create_job(user_id=uid, job_type="s2", source_id=None, payload={"week_start": week_start})
        enqueued += 1
    logger.info("s2-schedule: week_start=%s enqueued=%d user_ids=%s", week_start, enqueued, user_ids)
    return {"status": "ok", "enqueued": enqueued, "user_ids": user_ids}
