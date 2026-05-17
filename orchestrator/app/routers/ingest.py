import asyncio
import uuid
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from ..db.pool import resolve_user_id, with_connection
from ..db.repo import SupabaseRepo
from ..guardrails import enforce_ingest_guardrails
from ..services.storage import MAX_UPLOAD_BYTES, canonical_pdf_storage_path, upload_pdf
from ..utils.deps import get_user_id
from ..utils.arxiv_url import normalize_arxiv_url

router = APIRouter(prefix="/ingest", tags=["ingest"])

SOURCE_TYPES = ("pdf_url", "url", "text")
MAX_PDF_FILE_BYTES = MAX_UPLOAD_BYTES  # 25MB
PDF_MAGIC = b"%PDF"


class IngestEnqueueRequest(BaseModel):
    """Request for POST /ingest: queue a source for tick-driven async processing."""
    type: Literal["pdf_url", "url", "text"]
    content: str
    title: str | None = None
    thread_id: Optional[str] = Field(None, description="interest_threads id (default: General)")


class IngestEnqueueResponse(BaseModel):
    """Immediate response from POST /ingest (Week6)."""
    job_id: str
    status: str = "queued"


def _upsert_source_pending(
    user_id: str,
    source_type: str,
    url: str | None,
    title: str | None,
    thread_id: Optional[str] = None,
) -> str:
    """Sync: resolve user, insert or update sources row (status=pending), return source_id.
    For pdf_url/url: ON CONFLICT (user_id, url) DO UPDATE. For text: plain INSERT.
    """
    repo = SupabaseRepo()
    tid = thread_id
    if tid and not repo.get_interest_thread(tid, user_id):
        tid = None
    if not tid:
        tid = repo.get_or_create_default_thread_id(user_id)
    thread_uuid = uuid.UUID(tid)
    with with_connection() as conn:
        with conn.cursor() as cur:
            user_uuid = resolve_user_id(cur, user_id)
            if source_type in ("pdf_url", "url") and url:
                cur.execute(
                    """
                    INSERT INTO sources (user_id, source_type, status, url, title, lang, thread_id)
                    VALUES (%s, %s, 'pending', %s, COALESCE(%s, ''), 'en', %s)
                    ON CONFLICT (user_id, url)
                    DO UPDATE SET updated_at = now(), status = 'pending', source_type = EXCLUDED.source_type,
                                    title = COALESCE(NULLIF(EXCLUDED.title, ''), sources.title),
                                    thread_id = EXCLUDED.thread_id
                    RETURNING id
                    """,
                    (user_uuid, source_type, url, title, thread_uuid),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO sources (user_id, source_type, status, url, title, lang, thread_id)
                    VALUES (%s, %s, 'pending', %s, %s, 'en', %s)
                    RETURNING id
                    """,
                    (user_uuid, source_type, url, title, thread_uuid),
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
    if request.type == "pdf_url" and url_value:
        url_value = normalize_arxiv_url(url_value)
    repo = SupabaseRepo()
    await asyncio.to_thread(enforce_ingest_guardrails, repo, user_id)
    source_id = await asyncio.to_thread(
        _upsert_source_pending,
        user_id,
        request.type,
        url_value,
        request.title,
        request.thread_id,
    )
    job_id = repo.create_job(user_id=user_id, job_type="ingest", source_id=source_id)
    return IngestEnqueueResponse(job_id=job_id, status="queued")


@router.post("/file", response_model=IngestEnqueueResponse)
async def ingest_file(
    background_tasks: BackgroundTasks,
    user_id: Annotated[str, Depends(get_user_id)],
    file: Annotated[UploadFile, File(description="PDF file")],
    title: Annotated[str | None, Form()] = None,
    thread_id: Annotated[str | None, Form()] = None,
):
    """Upload a local PDF for ingest. Storage + source (pdf_file) + job; process_job runs in background (B)."""
    body = await file.read()
    if len(body) < 4 or body[:4] != PDF_MAGIC:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not a valid PDF")
    if len(body) > MAX_PDF_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY,
            detail=f"File too large (max {MAX_PDF_FILE_BYTES // (1024*1024)}MB)",
        )
    repo = SupabaseRepo()
    await asyncio.to_thread(enforce_ingest_guardrails, repo, user_id)
    user_uuid = repo._get_or_create_user_id(user_id)
    source_id = await asyncio.to_thread(repo.insert_source_pdf_file, user_id, title or None, thread_id)
    storage_path = canonical_pdf_storage_path(user_uuid, source_id)
    try:
        await asyncio.to_thread(upload_pdf, storage_path, body)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    original_filename = (title or (file.filename or "document.pdf")).strip() or "document.pdf"
    repo.update_source(source_id, meta={"storage_path": storage_path, "original_filename": original_filename})
    job_id = repo.create_job(user_id=user_id, job_type="ingest", source_id=source_id)
    from app.worker.job_runner import process_job
    background_tasks.add_task(process_job, job_id)
    return IngestEnqueueResponse(job_id=job_id, status="queued")

