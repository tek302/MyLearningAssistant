"""
Week6: Job runner for tick-driven ingest. process_job() is invoked by POST /worker/tick.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from app.db.repo import SupabaseRepo
from app.chains.ingest_graph import ingest_graph, IngestState

logger = logging.getLogger(__name__)


def _week_start_monday(dt: datetime) -> str:
    """Return ISO date (YYYY-MM-DD) of Monday of the week containing dt."""
    monday = dt - timedelta(days=dt.weekday())
    return monday.strftime("%Y-%m-%d")


async def process_job(job_id: str) -> None:
    """Load job and source, run ingest (pdf_url or url) or S2 consolidation, update job/source state. One at a time."""
    repo = SupabaseRepo()
    job = repo.get_job(job_id)
    if not job:
        logger.warning("job_id=%s not found", job_id)
        return
    job_type = (job.get("job_type") or "").strip()
    source_id = job.get("source_id")

    if job_type == "s2":
        user_id = job.get("user_id")
        if not user_id:
            repo.update_job(job_id, state="failed", error="missing user_id")
            return
        payload = job.get("payload") or {}
        week_start = payload.get("week_start") if isinstance(payload, dict) else None
        week_start_used = week_start if week_start else _week_start_monday(datetime.now(timezone.utc))
        repo.update_job(job_id, state="running", progress=10)
        try:
            from app.services.s2_consolidation import run_s2_consolidation
            ok, reason = await asyncio.to_thread(run_s2_consolidation, user_id, week_start=week_start, days=7)
            if ok:
                from app.services.arxiv_recommendations import run_arxiv_recommendations_for_week
                try:
                    count, rec_error = await asyncio.to_thread(
                        run_arxiv_recommendations_for_week, user_id, week_start_used, None
                    )
                    if count == 0 and rec_error:
                        repo.update_job(job_id, state="done", progress=100, payload_merge={"recommendations_failed": True})
                    else:
                        repo.update_job(job_id, state="done", progress=100)
                except Exception as rec_ex:
                    logger.warning("job_id=%s recommendations failed (S2 succeeded): %s", job_id, rec_ex)
                    repo.update_job(job_id, state="done", progress=100, payload_merge={"recommendations_failed": True})
            else:
                repo.update_job(job_id, state="done", progress=100, error=reason or "s2 skipped")
        except Exception as e:
            logger.exception("job_id=%s s2 consolidation failed: %s", job_id, e)
            repo.update_job(job_id, state="failed", error=str(e))
        return

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
            "title": (source.get("title") or "").strip(),
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

    if source_type == "pdf_file":
        repo.update_job(job_id, state="running", progress=10)
        repo.update_source(source_id, status="running")
        meta = source.get("meta") or {}
        storage_path = (meta.get("storage_path") or "").strip()
        if not storage_path:
            repo.update_job(job_id, state="failed", error="pdf_file source missing meta.storage_path")
            repo.update_source(source_id, status="failed", fail_code="MISSING_STORAGE_PATH")
            return
        from app.services.storage import delete_pdf, get_pdf
        from app.worker.run_pdf_worker import process_pdf_bytes

        try:
            pdf_bytes = await asyncio.to_thread(get_pdf, storage_path)
        except (FileNotFoundError, RuntimeError) as e:
            repo.update_job(job_id, state="failed", error=str(e)[:500])
            repo.update_source(source_id, status="failed", fail_code="STORAGE_FETCH_FAILED")
            return
        title = (source.get("title") or meta.get("original_filename") or "").strip()
        ok = await asyncio.to_thread(process_pdf_bytes, source_id, user_id, pdf_bytes, title or None)
        if ok:
            await asyncio.to_thread(delete_pdf, storage_path)
            repo.update_job(job_id, state="done", progress=100)
        else:
            repo.update_job(job_id, state="failed", error="PDF processing failed")
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
            err_msg = str(e)
            # Log type and message first so they are visible even if traceback is truncated
            logger.error(
                "job_id=%s url ingest failed: type=%s message=%s",
                job_id,
                type(e).__name__,
                err_msg[:500] + ("..." if len(err_msg) > 500 else ""),
            )
            logger.exception("job_id=%s url ingest full traceback", job_id)
            # Store truncated error for job/source (DB column may have limit)
            repo.update_job(job_id, state="failed", error=err_msg[:2000] if len(err_msg) > 2000 else err_msg)
            repo.update_source(source_id, status="failed", fail_code="URL_INGEST_ERROR")
        return

    repo.update_job(job_id, state="failed", error=f"unknown source_type={source_type}")
    repo.update_source(source_id, status="failed", fail_code="UNKNOWN_SOURCE_TYPE")

