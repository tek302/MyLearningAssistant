"""
Run Local PDF ingest locally without the server or Android app.
Uses a dedicated test user "local-pdf-test" so test data does not mix with real users.
Requires: .env (DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, bucket), and a PDF file path.

Usage (from orchestrator dir):
  python scripts/run_ingest_file_local.py path/to/sample.pdf
  python scripts/run_ingest_file_local.py path/to/sample.pdf "Optional title"
"""
from __future__ import annotations

import asyncio
import os
import sys

# Ensure app is importable when run as scripts/run_ingest_file_local.py from orchestrator
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_env

load_env()

# Test user: not used by the real app (Firebase users). Keeps local test data separate.
LOCAL_PDF_TEST_USER_ID = "local-pdf-test"


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_ingest_file_local.py <path-to-pdf> [title]")
        sys.exit(1)
    pdf_path = os.path.abspath(sys.argv[1])
    title = sys.argv[2] if len(sys.argv) > 2 else None
    if not os.path.isfile(pdf_path):
        print(f"Error: file not found: {pdf_path}")
        sys.exit(1)
    with open(pdf_path, "rb") as f:
        body = f.read()
    if len(body) < 4 or body[:4] != b"%PDF":
        print("Error: not a valid PDF (missing %PDF header)")
        sys.exit(1)

    from app.db.pool import init_pool, close_pool
    from app.db.repo import SupabaseRepo
    from app.services.storage import upload_pdf
    from app.worker.job_runner import process_job

    init_pool(min_size=1, max_size=2)
    try:
        repo = SupabaseRepo()
        user_uuid = repo._get_or_create_user_id(LOCAL_PDF_TEST_USER_ID)
        source_id = repo.insert_source_pdf_file(LOCAL_PDF_TEST_USER_ID, title)
        storage_path = f"{user_uuid}/{source_id}.pdf"
        original_filename = (title or os.path.basename(pdf_path) or "document.pdf").strip()
        print(f"Uploading to Storage: {storage_path} ...")
        upload_pdf(storage_path, body)
        repo.update_source(
            source_id,
            meta={"storage_path": storage_path, "original_filename": original_filename},
        )
        job_id = repo.create_job(
            user_id=LOCAL_PDF_TEST_USER_ID,
            job_type="ingest",
            source_id=source_id,
        )
        print(f"Job created: job_id={job_id}. Running process_job ...")
        asyncio.run(process_job(job_id))
        print(f"Done. source_id={source_id} (user={LOCAL_PDF_TEST_USER_ID})")
    finally:
        close_pool()


if __name__ == "__main__":
    main()
