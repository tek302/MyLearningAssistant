"""
Week5 Day2: Standalone PDF ingest worker.

Runnable via: python -m app.worker.run_pdf_worker (from orchestrator dir).

Processes source_type='pdf_url' rows: fetch PDF, parse text, chunk, embed, persist.
Uses DB claim via sources.meta (claimed_at, claimed_by). Process at most 1 PDF at a time.
"""
from __future__ import annotations

import logging
import signal
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import requests

# Ensure app is importable when run as __main__
if __name__ == "__main__" and __package__ is None:
    # Add parent of orchestrator to path if needed; when run as -m app.worker.run_pdf_worker
    # __package__ is "app.worker", so this block is only when run as script. Prefer -m.
    pass

from app.config import load_env
from app.db.pool import close_pool, init_pool, with_connection
from app.utils.embeddings import create_embeddings

logger = logging.getLogger("pdf_worker")

# --- Constants (Week5) ---
FETCH_TIMEOUT_S = 15
MAX_PDF_MB = 30
MAX_PDF_BYTES = MAX_PDF_MB * 1024 * 1024
MAX_PAGES = 50
MIN_TEXT_CHARS = 500
CHUNK_TARGET_MIN, CHUNK_TARGET_MAX = 800, 1200
CHUNK_OVERLAP_MIN, CHUNK_OVERLAP_MAX = 100, 200
CLAIM_STALE_MINUTES = 20
POLL_INTERVAL_S = 2
SUMMARY_EVERY_N_LOOPS = 10
WORKER_ID = "pdf_worker"

# Fail codes
FAIL_FETCH_TIMEOUT = "FETCH_TIMEOUT"
FAIL_TOO_LARGE = "PDF_TOO_LARGE"
FAIL_TOO_LONG = "PDF_TOO_LONG"
FAIL_NO_TEXT = "PDF_NO_TEXT_LAYER"


def fetch_pdf(url: str) -> tuple[bytes, float]:
    """
    Stream PDF from url. Enforce max 30MB and 15s total timeout.
    Returns (pdf_bytes, size_mb). Raises ValueError with fail_code message.
    Note: requests timeout only covers connect/read per chunk; we enforce TOTAL elapsed time.
    """
    headers = {"User-Agent": "LearningAgent-PDFWorker/1.0"}
    buf: list[bytes] = []
    total = 0
    start = time.monotonic()

    with requests.get(url, headers=headers, timeout=FETCH_TIMEOUT_S, stream=True) as r:
        r.raise_for_status()
        for chunk in r.iter_content(chunk_size=65536):
            # Total timeout: abort if entire download exceeds 15s (not just per-chunk)
            if time.monotonic() - start > FETCH_TIMEOUT_S:
                raise ValueError(FAIL_FETCH_TIMEOUT)
            total += len(chunk)
            if total > MAX_PDF_BYTES:
                raise ValueError(FAIL_TOO_LARGE)
            buf.append(chunk)

    pdf_bytes = b"".join(buf)
    size_mb = len(pdf_bytes) / (1024.0 * 1024.0)
    return pdf_bytes, size_mb


def parse_pdf(pdf_bytes: bytes) -> tuple[str, int]:
    """
    Extract text and page count using PyMuPDF. Text-layer only.
    Returns (text, pages). Raises ValueError with fail_code.
    """
    try:
        import fitz
    except ImportError:
        raise RuntimeError("PyMuPDF (fitz) is required. pip install pymupdf")

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        pages = len(doc)
        if pages > MAX_PAGES:
            raise ValueError(FAIL_TOO_LONG)
        parts = []
        for i in range(pages):
            parts.append(doc[i].get_text("text") or "")
        text = "\n\n".join(parts).strip()
        if len(text) < MIN_TEXT_CHARS:
            raise ValueError(FAIL_NO_TEXT)
        return text, pages
    finally:
        doc.close()


def _find_word_boundary(text: str, start: int, end: int) -> int:
    """Find last break point (space/punct) in [start, end] to avoid mid-word split."""
    for i in range(end - 1, start - 1, -1):
        if text[i] in " \n\t.,;:!?":
            return i + 1
    return end


def chunk_text(text: str) -> list[str]:
    """
    Simple chunker: target 800–1200 chars, overlap 100–200.
    Produces list of chunk strings. Breaks at word boundaries to avoid mid-word truncation.
    """
    target = (CHUNK_TARGET_MIN + CHUNK_TARGET_MAX) // 2
    overlap = (CHUNK_OVERLAP_MIN + CHUNK_OVERLAP_MAX) // 2
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + target, n)
        if end < n:
            # Try to break at paragraph or sentence
            found = False
            for sep in ("\n\n", "\n", ". ", " "):
                last = text.rfind(sep, start, end + 1)
                if last != -1 and last > start:
                    end = last + len(sep)
                    found = True
                    break
            # Fallback: avoid mid-word break (e.g. "Finally" -> "tly")
            if not found:
                end = _find_word_boundary(text, start, end)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap if overlap < (end - start) else end
        if start <= 0:
            start = end
    return chunks


def claim_one_pending_pdf() -> dict[str, Any] | None:
    """
    Claim one pending pdf_url row using SELECT ... FOR UPDATE SKIP LOCKED,
    then set meta.claimed_at and meta.claimed_by. Returns row dict or None.
    """
    stale_interval = f"{CLAIM_STALE_MINUTES} minutes"
    with with_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.id, s.url, s.title, s.user_id, s.source_type, s.status,
                       s.meta->>'claimed_at' as claimed_at
                FROM sources s
                WHERE s.status = 'pending'
                  AND s.source_type = 'pdf_url'
                  AND COALESCE((s.meta->>'claimed_at')::timestamptz, '1970-01-01'::timestamptz)
                      < now() - %s::interval
                ORDER BY s.created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """,
                (stale_interval,),
            )
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            out = dict(zip(cols, row))
            out["id"] = str(out["id"])
            out["user_id"] = str(out["user_id"])
            source_id = out["id"]
            claimed_at_raw = out.pop("claimed_at", None)
            if claimed_at_raw:
                try:
                    prev_claimed = datetime.fromisoformat(claimed_at_raw.replace("Z", "+00:00"))
                    elapsed_mins = (datetime.now(timezone.utc) - prev_claimed).total_seconds() / 60
                    logger.warning(
                        "source_id=%s Reclaiming stale PDF job previously claimed_at=%s elapsed_min=%.1f",
                        source_id, claimed_at_raw, elapsed_mins,
                    )
                except (ValueError, TypeError):
                    pass
            cur.execute(
                """
                UPDATE sources
                SET meta = COALESCE(meta, '{}'::jsonb) ||
                  jsonb_build_object('claimed_at', now(), 'claimed_by', 'pdf_worker')
                WHERE id = %s
                """,
                (source_id,),
            )
            return out
    return None


def _row_to_sources_meta_ingest(success: bool, chunks_count: int = 0, reason: str | None = None) -> dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    if success:
        return {"ingest": {"worker": WORKER_ID, "finished_at": now_iso, "chunks": chunks_count}}
    return {"ingest": {"worker": WORKER_ID, "failed_at": now_iso, "reason": reason or "unknown"}}


def mark_ready(
    source_id: str,
    pages: int,
    size_mb: float,
    char_count: int,
    chunks_count: int,
) -> None:
    """Update sources to status=done, set pages/size_mb/char_count, clear fail_code, set meta.ingest."""
    import json
    meta_ingest = _row_to_sources_meta_ingest(True, chunks_count=chunks_count)
    with with_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE sources
                SET status = 'done', pages = %s, size_mb = %s, char_count = %s,
                    fail_code = NULL,
                    meta = COALESCE(meta, '{}') || %s::jsonb
                WHERE id = %s
                """,
                (pages, size_mb, char_count, json.dumps(meta_ingest), source_id),
            )


def mark_failed(source_id: str, fail_code: str) -> None:
    """Update sources to status=failed, set fail_code and meta.ingest."""
    import json
    meta_ingest = _row_to_sources_meta_ingest(False, reason=fail_code)
    with with_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE sources
                SET status = 'failed', fail_code = %s,
                    meta = COALESCE(meta, '{}') || %s::jsonb
                WHERE id = %s
                """,
                (fail_code, json.dumps(meta_ingest), source_id),
            )


def _persist_chunks_and_embeddings(source_id: str, chunks_list: list[str]) -> None:
    """Insert chunks (with new uuids), compute embeddings, insert embeddings. Single transaction."""
    if not chunks_list:
        return
    vectors = create_embeddings(chunks_list, max_retries=2)
    if len(vectors) != len(chunks_list):
        raise RuntimeError("embedding count mismatch")
    vector_str = lambda v: "[" + ",".join(str(x) for x in v) + "]"
    with with_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chunks WHERE source_id = %s", (source_id,))
            for ord_idx, (text, vec) in enumerate(zip(chunks_list, vectors), start=1):
                chunk_id = str(uuid.uuid4())
                cur.execute(
                    "INSERT INTO chunks (id, source_id, ord, text) VALUES (%s, %s, %s, %s)",
                    (chunk_id, source_id, ord_idx, text),
                )
                cur.execute(
                    "INSERT INTO embeddings (chunk_id, embedding) VALUES (%s, %s::vector) ON CONFLICT (chunk_id) DO UPDATE SET embedding = EXCLUDED.embedding",
                    (chunk_id, vector_str(vec)),
                )


def process_one(row: dict[str, Any]) -> bool:
    """
    Fetch PDF, parse, chunk, embed, persist; mark_ready or mark_failed.
    Returns True if ready, False if failed. Never raises; logs and marks failed on error.
    """
    source_id = row["id"]
    url = row.get("url") or ""
    log_ctx = f"source_id={source_id} url={url}"
    try:
        t0 = time.perf_counter()
        pdf_bytes, size_mb = fetch_pdf(url)
        pages: int
        text: str
        text, pages = parse_pdf(pdf_bytes)
        char_count = len(text)
        chunks_list = chunk_text(text)
        _persist_chunks_and_embeddings(source_id, chunks_list)
        mark_ready(source_id, pages=pages, size_mb=size_mb, char_count=char_count, chunks_count=len(chunks_list))
        elapsed = time.perf_counter() - t0
        logger.info("%s ready pages=%s size_mb=%.2f chunks=%s elapsed_s=%.2f", log_ctx, pages, size_mb, len(chunks_list), elapsed)
        return True
    except ValueError as e:
        fail_code = str(e)
        if fail_code not in (FAIL_FETCH_TIMEOUT, FAIL_TOO_LARGE, FAIL_TOO_LONG, FAIL_NO_TEXT):
            fail_code = "PDF_PARSE_ERROR"
        logger.warning("%s failed fail_code=%s", log_ctx, fail_code)
        mark_failed(source_id, fail_code)
        return False
    except Exception as e:
        logger.exception("%s error: %s", log_ctx, e)
        mark_failed(source_id, "PDF_PROCESS_ERROR")
        return False


_shutdown = False


def _on_signal(_signum, _frame):
    global _shutdown
    _shutdown = True


def main_loop() -> None:
    """Loop: claim one pending PDF, process it, sleep; exit on shutdown. Log claimed/ready/failed and periodic summary."""
    logger.info("pdf_worker starting (poll_interval=%ss)", POLL_INTERVAL_S)
    claimed = 0
    ready = 0
    failed = 0
    pending_seen = 0
    loop_count = 0
    times: list[float] = []
    max_times = 10

    while not _shutdown:
        loop_count += 1
        row = claim_one_pending_pdf()
        if row is None:
            pending_seen += 1
            if loop_count % SUMMARY_EVERY_N_LOOPS == 0:
                logger.info(
                    "summary pending_seen=%s claimed=%s ready=%s failed=%s",
                    pending_seen, claimed, ready, failed,
                )
            time.sleep(POLL_INTERVAL_S)
            continue
        claimed += 1
        t0 = time.perf_counter()
        ok = process_one(row)
        elapsed = time.perf_counter() - t0
        if ok:
            ready += 1
        else:
            failed += 1
        times.append(elapsed)
        if len(times) > max_times:
            times.pop(0)
        avg_s = sum(times) / len(times) if times else 0.0
        logger.info(
            "source_id=%s claimed=%s ready=%s failed=%s avg_elapsed_s=%.2f",
            row["id"], claimed, ready, failed, avg_s,
        )
        if loop_count % SUMMARY_EVERY_N_LOOPS == 0:
            logger.info(
                "summary pending_seen=%s claimed=%s ready=%s failed=%s",
                pending_seen, claimed, ready, failed,
            )

    logger.info("pdf_worker stopping (claimed=%s ready=%s failed=%s)", claimed, ready, failed)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    # Graceful shutdown
    signal.signal(signal.SIGINT, _on_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _on_signal)
    try:
        dotenv_path = load_env()
        logger.info("Loaded .env from %s (override=false)", dotenv_path)
        init_pool(min_size=1, max_size=2)
        main_loop()
    finally:
        close_pool()
    logger.info("pdf_worker exited")


if __name__ == "__main__":
    main()
    sys.exit(0)
