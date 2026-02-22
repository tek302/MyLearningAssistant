import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db.pool import resolve_user_id, with_connection
from ..db.repo import SupabaseRepo
from ..utils.deps import get_user_id

router = APIRouter(prefix="/ingest", tags=["ingest"])

SOURCE_TYPES = ("pdf_url", "url", "text")


class IngestEnqueueRequest(BaseModel):
    """Request for POST /ingest: queue a source for tick-driven async processing."""
    type: Literal["pdf_url", "url", "text"]
    content: str
    title: str | None = None


class IngestEnqueueResponse(BaseModel):
    """Immediate response from POST /ingest (Week6)."""
    job_id: str
    status: str = "queued"


def _upsert_source_pending(user_id: str, source_type: str, url: str | None, title: str | None) -> str:
    """Sync: resolve user, insert or update sources row (status=pending), return source_id.
    For pdf_url/url: ON CONFLICT (user_id, url) DO UPDATE. For text: plain INSERT.
    """
    with with_connection() as conn:
        with conn.cursor() as cur:
            user_uuid = resolve_user_id(cur, user_id)
            if source_type in ("pdf_url", "url") and url:
                cur.execute(
                    """
                    INSERT INTO sources (user_id, source_type, status, url, title, lang)
                    VALUES (%s, %s, 'pending', %s, COALESCE(%s, ''), 'en')
                    ON CONFLICT (user_id, url)
                    DO UPDATE SET updated_at = now(), status = 'pending', source_type = EXCLUDED.source_type,
                                    title = COALESCE(NULLIF(EXCLUDED.title, ''), sources.title)
                    RETURNING id
                    """,
                    (user_uuid, source_type, url, title),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO sources (user_id, source_type, status, url, title, lang)
                    VALUES (%s, %s, 'pending', %s, %s, 'en')
                    RETURNING id
                    """,
                    (user_uuid, source_type, url, title),
                )
            row = cur.fetchone()
            return str(row[0])


@router.post("", response_model=IngestEnqueueResponse)
async def ingest_enqueue(
    request: IngestEnqueueRequest,
    user_id: Annotated[str, Depends(get_user_id)],
):
    """
    Queue a source for async ingestion (tick-driven). Job is processed when POST /worker/tick runs.
    Returns job_id; poll GET /ingest/status?job_id=... for state.
    """
    if request.type not in SOURCE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"type must be one of {SOURCE_TYPES}",
        )
    content = (request.content or "").strip()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="content is required and must be non-empty",
        )
    url_value = content if request.type in ("pdf_url", "url") else None
    source_id = await asyncio.to_thread(
        _upsert_source_pending,
        user_id,
        request.type,
        url_value,
        request.title,
    )
    repo = SupabaseRepo()
    job_id = repo.create_job(user_id=user_id, job_type="ingest", source_id=source_id)
    return IngestEnqueueResponse(job_id=job_id, status="queued")

