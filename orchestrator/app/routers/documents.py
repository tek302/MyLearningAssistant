"""
GET /documents: list latest sources for the current user (Week5 Day1).
DELETE /documents/{document_id}: delete a document (source) and its chunks/embeddings/summaries. DB cascade.
POST /documents/{document_id}/reprocess: re-queue document for processing and run worker once (e.g. to refresh title).
"""
import asyncio
import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from ..db.pool import resolve_user_id, with_connection
from ..db.repo import SupabaseRepo
from ..utils.deps import get_user_id
from ..worker.job_runner import process_job

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


def _list_sources(
    user_id: str,
    limit: int,
    offset: int = 0,
    include_summary: bool = False,
) -> list[dict[str, Any]]:
    """Sync: return latest N sources for user with optional S1 summary (tldr, bullets)."""
    with with_connection() as conn:
        with conn.cursor() as cur:
            user_uuid = resolve_user_id(cur, user_id)
            if include_summary:
                cur.execute(
                    """
                    SELECT s.id, s.title, s.url, s.source_type, s.status, s.pages, s.size_mb, s.fail_code,
                           s.created_at, s.updated_at,
                           sm.tldr, sm.bullets
                    FROM sources s
                    LEFT JOIN summaries sm ON sm.source_id = s.id AND sm.scope = 'doc' AND sm.kind = 'S1'
                    WHERE s.user_id = %s
                    ORDER BY s.created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (user_uuid, limit, offset),
                )
            else:
                cur.execute(
                    """
                    SELECT id, title, url, source_type, status, pages, size_mb, fail_code,
                           created_at, updated_at
                    FROM sources
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (user_uuid, limit, offset),
                )
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            out = []
            for row in rows:
                d = dict(zip(cols, row))
                d["id"] = str(d["id"])
                for ts in ("created_at", "updated_at"):
                    if d.get(ts) is not None:
                        d[ts] = d[ts].isoformat()
                if include_summary and "bullets" in d and d["bullets"] is not None:
                    # bullets is jsonb; ensure list of strings
                    b = d["bullets"]
                    d["bullets"] = b if isinstance(b, list) else []
                elif include_summary:
                    d["tldr"] = d.get("tldr")
                    d["bullets"] = d.get("bullets") or []
                out.append(d)
            return out


@router.get("")
async def list_documents(
    user_id: Annotated[str, Depends(get_user_id)],
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_summary: bool = Query(False, description="Include S1 summary (tldr, bullets) per document"),
):
    """Return latest N sources for the current user, with optional pagination and summary."""
    items = await asyncio.to_thread(_list_sources, user_id, limit, offset, include_summary)
    return {"documents": items}


def _delete_source_by_id(user_id: str, document_id: str) -> bool:
    """Delete source (document) if it belongs to the user. Returns True if deleted, False if not found or not owner.
    Deletes in order: summaries, chunks (embeddings cascade), then source. Works even if sources FK has no CASCADE.
    """
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        return False
    with with_connection() as conn:
        with conn.cursor() as cur:
            user_uuid_str = resolve_user_id(cur, user_id)
            try:
                user_uuid = uuid.UUID(user_uuid_str)
            except ValueError:
                logger.warning("delete_document: invalid user_uuid from resolve_user_id: %s", user_uuid_str)
                return False
            # Ensure the source belongs to the user before deleting
            cur.execute(
                "SELECT id FROM sources WHERE id = %s AND user_id = %s",
                (doc_uuid, user_uuid),
            )
            if cur.fetchone() is None:
                return False
            # Match actual DB: notes, users.active_source_id, jobs, then summaries/embeddings/chunks/source
            cur.execute("UPDATE users SET active_source_id = NULL WHERE active_source_id = %s", (doc_uuid,))
            cur.execute("DELETE FROM notes WHERE source_id = %s", (doc_uuid,))
            cur.execute(
                "DELETE FROM notes WHERE chunk_id IN (SELECT id FROM chunks WHERE source_id = %s)",
                (doc_uuid,),
            )
            cur.execute("DELETE FROM jobs WHERE source_id = %s", (doc_uuid,))
            cur.execute("DELETE FROM summaries WHERE source_id = %s", (doc_uuid,))
            cur.execute(
                "DELETE FROM embeddings WHERE chunk_id IN (SELECT id FROM chunks WHERE source_id = %s)",
                (doc_uuid,),
            )
            cur.execute("DELETE FROM chunks WHERE source_id = %s", (doc_uuid,))
            cur.execute("DELETE FROM sources WHERE id = %s AND user_id = %s", (doc_uuid, user_uuid))
            return cur.rowcount > 0


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: Annotated[str, Path(description="Document (source) ID to delete")],
    user_id: Annotated[str, Depends(get_user_id)],
):
    """Delete an ingested document (source) for the current user. Removes source, chunks, embeddings, summaries from DB."""
    try:
        deleted = await asyncio.to_thread(_delete_source_by_id, user_id, document_id)
    except Exception as e:
        logger.exception("delete_document failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document",
        ) from e
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found or not owned by you")


def _reprocess_source(user_id: str, document_id: str) -> str | None:
    """Set source back to pending, clear title so worker can re-fetch, create a new job. Returns job_id or None."""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        return None
    with with_connection() as conn:
        with conn.cursor() as cur:
            user_uuid_str = resolve_user_id(cur, user_id)
            try:
                user_uuid = uuid.UUID(user_uuid_str)
            except ValueError:
                return None
            cur.execute(
                "SELECT id, source_type FROM sources WHERE id = %s AND user_id = %s",
                (doc_uuid, user_uuid),
            )
            row = cur.fetchone()
            if row is None:
                return None
            source_id_val, source_type = row
            if source_type != "pdf_url":
                return None
            cur.execute(
                """
                UPDATE sources
                SET status = 'pending', title = '', updated_at = now()
                WHERE id = %s AND user_id = %s
                """,
                (doc_uuid, user_uuid),
            )
            if cur.rowcount == 0:
                return None
    repo = SupabaseRepo()
    job_id = repo.create_job(user_id=user_id, job_type="ingest", source_id=document_id)
    logger.info("reprocess document_id=%s job_id=%s", document_id, job_id)
    return job_id


@router.post("/{document_id}/reprocess", status_code=status.HTTP_200_OK)
async def reprocess_document(
    document_id: Annotated[str, Path(description="Document (source) ID to reprocess")],
    user_id: Annotated[str, Depends(get_user_id)],
):
    """Re-queue a PDF document for processing and run the worker once so it is processed immediately (e.g. title may be set)."""
    try:
        job_id = await asyncio.to_thread(_reprocess_source, user_id, document_id)
    except Exception as e:
        logger.exception("reprocess_document failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reprocess document",
        ) from e
    if job_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found, not owned by you, or not a PDF (only pdf_url can be reprocessed)",
        )
    await process_job(job_id)
    return {"job_id": job_id, "processed": True}
