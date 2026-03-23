"""
Supabase Storage for Local PDF Ingest.
Upload, download, and delete PDFs at path {user_id}/{source_id}.pdf.
Uses SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY; no-op or error when not configured.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

import httpx

from app.config import get_ingest_storage_bucket, get_supabase_service_key, get_supabase_url

logger = logging.getLogger(__name__)

# Max 25MB for upload (align with API limit)
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def canonical_pdf_storage_path(user_id: str, source_id: str) -> str:
    """Return canonical storage path for a user's uploaded PDF."""
    return f"{UUID(str(user_id))}/{UUID(str(source_id))}.pdf"


def _base_url() -> Optional[str]:
    url = get_supabase_url()
    key = get_supabase_service_key()
    if not url or not key:
        return None
    return url.rstrip("/") + "/storage/v1"


def _headers() -> dict[str, str]:
    key = get_supabase_service_key()
    if not key:
        return {}
    return {
        "Authorization": f"Bearer {key}",
        "apikey": key,
    }


def upload_pdf(storage_path: str, body: bytes, content_type: str = "application/pdf") -> None:
    """
    Upload PDF bytes to Storage at the given path (e.g. user_id/source_id.pdf).
    Raises RuntimeError if Storage is not configured or upload fails.
    Uses multipart/form-data as required by Supabase Storage API.
    """
    base = _base_url()
    if not base:
        raise RuntimeError("Supabase Storage not configured: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
    bucket = get_ingest_storage_bucket()
    if len(body) > MAX_UPLOAD_BYTES:
        raise ValueError("File too large")
    url = f"{base}/object/{bucket}/{storage_path}"
    headers = _headers()
    # Supabase expects multipart/form-data with file field
    files = {"file": (storage_path.split("/")[-1] or "document.pdf", body, content_type)}
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, files=files, headers=headers)
    if resp.status_code >= 400:
        logger.warning("Storage upload failed path=%s status=%s body=%s", storage_path, resp.status_code, resp.text[:500])
        raise RuntimeError(f"Storage upload failed: {resp.status_code} {resp.text[:200]}")


def get_pdf(storage_path: str) -> bytes:
    """
    Download PDF bytes from Storage. Raises RuntimeError if not configured or not found.
    """
    base = _base_url()
    if not base:
        raise RuntimeError("Supabase Storage not configured: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
    bucket = get_ingest_storage_bucket()
    url = f"{base}/object/{bucket}/{storage_path}"
    with httpx.Client(timeout=60.0) as client:
        resp = client.get(url, headers=_headers())
    if resp.status_code == 404:
        raise FileNotFoundError(f"Storage object not found: {storage_path}")
    if resp.status_code >= 400:
        raise RuntimeError(f"Storage get failed: {resp.status_code} {resp.text[:200]}")
    return resp.content


def delete_pdf(storage_path: str) -> None:
    """
    Delete the object at storage_path. Logs and returns on failure (e.g. 404); does not raise.
    """
    base = _base_url()
    if not base:
        logger.warning("Supabase Storage not configured; skip delete path=%s", storage_path)
        return
    bucket = get_ingest_storage_bucket()
    url = f"{base}/object/{bucket}/{storage_path}"
    with httpx.Client(timeout=30.0) as client:
        resp = client.delete(url, headers=_headers())
    if resp.status_code >= 400:
        logger.warning("Storage delete failed path=%s status=%s %s", storage_path, resp.status_code, resp.text[:200])
