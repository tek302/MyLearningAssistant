"""
Week6: Job runner for tick-driven ingest. process_job() is invoked by POST /worker/tick.
"""
import asyncio
import logging
from typing import Any

from app.db.repo import SupabaseRepo
from app.chains.ingest_graph import ingest_graph, IngestState

logger = logging.getLogger(__name__)


async def process_job(job_id: str) -> None:
    """Load job and source, run ingest (pdf_url or url), update job/source state. One at a time."""
    repo = SupabaseRepo()
    job = repo.get_job(job_id)
    if not job:
        logger.warning("job_id=%s not found", job_id)
        return
    source_id = job.get("source_id")
    if not source_id:
        repo.update_job(job_id, state="failed", error="missing source_id")
        return
    source = repo.get_source_by_id(source_id)
    if not source:
        repo.update_job(job_id, state="failed", error="source not found")
        return

    user_id = source.get("user_id") or ""
    url = (source.get("url") or "").strip()
    source_type = (source.get("source_type") or "").strip() or "pdf_url"

    if source_type == "text":
        repo.update_job(job_id, state="failed", error="text ingest not supported in Week6")
        repo.update_source(source_id, status="failed", fail_code="TEXT_NOT_SUPPORTED")
        return

    if source_type == "pdf_url":
        repo.update_job(job_id, state="running", progress=10)
        repo.update_source(source_id, status="running")
        row: dict[str, Any] = {
            "id": source_id,
            "url": url,
            "user_id": user_id,
            "source_type": source_type,
            "status": "running",
        }
        from app.worker.run_pdf_worker import process_one

        ok = await asyncio.to_thread(process_one, row)
        if ok:
            repo.update_job(job_id, state="done", progress=100)
            # process_one already set sources.status='done' via mark_ready
        else:
            repo.update_job(job_id, state="failed", error="PDF processing failed")
            # process_one already set sources.status='failed'
        return

    if source_type == "url":
        repo.update_job(job_id, state="running", progress=10)
        repo.update_source(source_id, status="running")
        initial_state: IngestState = {
            "user_id": user_id,
            "url": url,
            "title": "",
            "lang": "en",
            "text": "",
            "source_id": source_id,
            "chunk_count": 0,
            "embedding_count": 0,
            "summary_id": "",
            "tldr": "",
            "bullets_count": 0,
            "content_type": "",
            "pages_used": 0,
            "meta": {},
        }
        try:
            await asyncio.to_thread(ingest_graph.invoke, initial_state)
            repo.update_job(job_id, state="done", progress=100)
            repo.update_source(source_id, status="done")
        except Exception as e:
            logger.exception("job_id=%s url ingest failed: %s", job_id, e)
            repo.update_job(job_id, state="failed", error=str(e))
            repo.update_source(source_id, status="failed", fail_code="URL_INGEST_ERROR")
        return

    repo.update_job(job_id, state="failed", error=f"unknown source_type={source_type}")
    repo.update_source(source_id, status="failed", fail_code="UNKNOWN_SOURCE_TYPE")

