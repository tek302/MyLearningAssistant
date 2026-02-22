"""
Tick-driven worker: POST /worker/tick claims one queued job from DB and processes it.
For Cloud Scheduler (1–2 min interval). Secured by X-Worker-Tick-Secret when WORKER_TICK_SECRET is set.
"""
import logging
import os

from fastapi import APIRouter, Request, HTTPException, status

from app.db.repo import SupabaseRepo
from app.worker.job_runner import process_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/worker", tags=["worker"])


@router.post("/tick")
async def worker_tick(request: Request):
    """
    Claim one queued job from DB and process it (tick-driven ingest).
    When WORKER_TICK_SECRET is set, request must include header X-Worker-Tick-Secret matching it.
    Returns 200 with { "status": "ok", "processed": true|false [, "job_id": "..." ] }.
    """
    secret = os.getenv("WORKER_TICK_SECRET")
    if secret:
        header_secret = request.headers.get("X-Worker-Tick-Secret")
        if header_secret != secret:
            logger.warning("worker_tick: forbidden (secret mismatch)")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    repo = SupabaseRepo()
    job_id = repo.claim_one_queued_job()
    if job_id:
        logger.info("worker_tick: claimed job_id=%s", job_id)
        await process_job(job_id)
        return {"status": "ok", "processed": True, "job_id": job_id}
    return {"status": "ok", "processed": False}
