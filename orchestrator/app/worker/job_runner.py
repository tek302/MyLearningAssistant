"""
Week6: Job runner for tick-driven ingest. process_job() is invoked by POST /worker/tick.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.db.repo import SupabaseRepo
from app.services.s2_consolidation import resolve_s2_week_start_key
from app.services.storage import canonical_pdf_storage_path
from app.chains.ingest_graph import ingest_graph, IngestState

logger = logging.getLogger(__name__)
EXPECTED_URL_INGEST_ERROR_MARKERS = (
    "403",
    "404",
    "429",
    "forbidden",
    "not found",
    "timeout",
    "timed out",
    "connection aborted",
    "connection reset",
    "too many requests",
)


def _is_expected_url_ingest_error(error: Exception) -> bool:
    """Return True for common fetch/timeout failures that should not emit full ERROR tracebacks."""
    message = str(error).lower()
    return any(marker in message for marker in EXPECTED_URL_INGEST_ERROR_MARKERS)


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
        now = datetime.now(timezone.utc)
        week_start_used = resolve_s2_week_start_key(week_start, now)
        repo.update_job(job_id, state="running", progress=10)
        try:
            from app.services.s2_consolidation import run_s2_consolidation
            ok, reason = await asyncio.to_thread(run_s2_consolidation, user_id, week_start, 7, now)
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

                # 2-Stage Pipeline chain: S2 → keyword_weight_recalc → stage1_keyword_expansion
                await _run_keyword_pipeline_after_s2(repo, user_id, week_start_used)
            else:
                repo.update_job(job_id, state="done", progress=100, error=reason or "s2 skipped")
        except Exception as e:
            logger.exception("job_id=%s s2 consolidation failed: %s", job_id, e)
            repo.update_job(job_id, state="failed", error=str(e))
        return

    # ─── 2-Stage Pipeline job types ───

    if job_type == "keyword_weight_recalc":
        user_id = job.get("user_id")
        if not user_id:
            repo.update_job(job_id, state="failed", error="missing user_id")
            return
        repo.update_job(job_id, state="running", progress=10)
        try:
            from app.services.keyword_weight import recalc_keyword_weights
            result = await asyncio.to_thread(recalc_keyword_weights, user_id, repo)
            repo.update_job(job_id, state="done", progress=100, payload_merge=result)
        except Exception as e:
            logger.exception("job_id=%s keyword_weight_recalc failed: %s", job_id, e)
            repo.update_job(job_id, state="failed", error=str(e)[:2000])
        return

    if job_type == "stage1_keyword_expansion":
        user_id = job.get("user_id")
        if not user_id:
            repo.update_job(job_id, state="failed", error="missing user_id")
            return
        payload = job.get("payload") or {}
        week_start = payload.get("week_start") if isinstance(payload, dict) else None
        if not week_start:
            week_start = resolve_s2_week_start_key(None, datetime.now(timezone.utc))
        repo.update_job(job_id, state="running", progress=10)
        try:
            from app.services.keyword_expansion import run_keyword_expansion
            suggestion_ids, error = await asyncio.to_thread(
                run_keyword_expansion, user_id, week_start, repo
            )
            if error:
                repo.update_job(job_id, state="done", progress=100, payload_merge={
                    "suggestion_ids": suggestion_ids, "error": error,
                })
            else:
                repo.update_job(job_id, state="done", progress=100, payload_merge={
                    "suggestion_ids": suggestion_ids,
                })
        except Exception as e:
            logger.exception("job_id=%s stage1_keyword_expansion failed: %s", job_id, e)
            repo.update_job(job_id, state="failed", error=str(e)[:2000])
        return

    if not source_id:
        repo.update_job(job_id, state="failed", error="missing source_id")
        return
    source = repo.get_source_by_id(source_id)
    if not source:
        repo.update_job(job_id, state="failed", error="source not found")
        return

    user_id = source.get("user_id") or ""
    job_user_id = job.get("user_id") or ""
    if job_user_id and user_id and str(job_user_id) != str(user_id):
        logger.error("job_id=%s source/user mismatch job_user_id=%s source_user_id=%s", job_id, job_user_id, user_id)
        repo.update_job(job_id, state="failed", error="job source ownership mismatch")
        if source_id:
            repo.update_source(source_id, status="failed", fail_code="USER_MISMATCH")
        return
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
        storage_path = canonical_pdf_storage_path(user_id, source_id)
        meta_storage_path = (meta.get("storage_path") or "").strip()
        if meta_storage_path and meta_storage_path != storage_path:
            logger.warning(
                "job_id=%s pdf_file storage path mismatch; using canonical path. meta=%s canonical=%s",
                job_id,
                meta_storage_path,
                storage_path,
            )
        if not storage_path:
            repo.update_job(job_id, state="failed", error="pdf_file source missing canonical storage path")
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
            await asyncio.to_thread(delete_pdf, storage_path)
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
            short_msg = err_msg[:500] + ("..." if len(err_msg) > 500 else "")
            if _is_expected_url_ingest_error(e):
                logger.warning(
                    "job_id=%s url ingest failed (expected fetch failure): type=%s message=%s",
                    job_id,
                    type(e).__name__,
                    short_msg,
                )
                logger.debug("job_id=%s url ingest traceback", job_id, exc_info=True)
            else:
                logger.error(
                    "job_id=%s url ingest failed (unexpected): type=%s message=%s",
                    job_id,
                    type(e).__name__,
                    short_msg,
                )
                logger.exception("job_id=%s url ingest full traceback", job_id)
            # Store truncated error for job/source (DB column may have limit)
            repo.update_job(job_id, state="failed", error=err_msg[:2000] if len(err_msg) > 2000 else err_msg)
            repo.update_source(source_id, status="failed", fail_code="URL_INGEST_ERROR")
        return

    repo.update_job(job_id, state="failed", error=f"unknown source_type={source_type}")
    repo.update_source(source_id, status="failed", fail_code="UNKNOWN_SOURCE_TYPE")


async def _run_keyword_pipeline_after_s2(repo: SupabaseRepo, user_id: str, week_start: str) -> None:
    """Chain: keyword_weight_recalc → stage1_keyword_expansion, triggered after S2 completes."""
    try:
        from app.services.keyword_weight import recalc_keyword_weights
        result = await asyncio.to_thread(recalc_keyword_weights, user_id, repo)
        logger.info("post-S2 keyword_weight_recalc done: %s", result)
    except Exception as e:
        logger.warning("post-S2 keyword_weight_recalc failed (continuing to stage1): %s", e)

    try:
        from app.services.keyword_expansion import run_keyword_expansion
        suggestion_ids, error = await asyncio.to_thread(run_keyword_expansion, user_id, week_start, repo)
        if error:
            logger.info("post-S2 stage1_keyword_expansion partial: %s", error)
        else:
            logger.info("post-S2 stage1_keyword_expansion done: %d suggestions", len(suggestion_ids))
    except Exception as e:
        logger.warning("post-S2 stage1_keyword_expansion failed: %s", e)

