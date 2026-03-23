"""Admin user debug endpoints."""

from __future__ import annotations

import asyncio
import os
from typing import Annotated, Optional

from fastapi import APIRouter, Header, HTTPException, Path, Query, status

from ..db.repo import SupabaseRepo

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


def _is_local_mode() -> bool:
    app_env = (os.getenv("APP_ENV") or "").strip().lower()
    debug = (os.getenv("DEBUG") or "").strip().lower() in ("true", "1", "yes")
    return app_env == "local" or debug


def _check_admin_secret(secret_header: Optional[str], secret_query: Optional[str]) -> None:
    expected = (os.getenv("ADMIN_DASHBOARD_SECRET") or "").strip()
    if not expected:
        if _is_local_mode():
            return
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Admin dashboard secret not configured")
    if secret_header == expected or secret_query == expected:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


@router.get("/{user_identifier}/debug")
async def admin_user_debug(
    user_identifier: Annotated[str, Path(description="User UUID or firebase_uid")],
    x_admin_secret: Annotated[Optional[str], Header()] = None,
    secret: Optional[str] = Query(None),
    jobs_limit: int = Query(20, ge=1, le=100),
    feedback_limit: int = Query(20, ge=1, le=100),
    ingest_failure_days: int = Query(7, ge=1, le=90),
):
    """Return read-only jobs + feedback debug data for a single user."""
    _check_admin_secret(x_admin_secret, secret)
    repo = SupabaseRepo()
    resolved_user_id = await asyncio.to_thread(repo.get_existing_user_id, user_identifier)
    if not resolved_user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    jobs = await asyncio.to_thread(repo.list_jobs_for_user, resolved_user_id, jobs_limit, 0, None)
    feedback = await asyncio.to_thread(
        repo.list_feedback_events,
        resolved_user_id,
        None,
        None,
        feedback_limit,
        0,
    )
    active_ingest_jobs = await asyncio.to_thread(repo.count_jobs_for_user, resolved_user_id, "ingest", ["queued", "running"])
    active_s2_jobs = await asyncio.to_thread(repo.count_jobs_for_user, resolved_user_id, "s2", ["queued", "running"])
    ingest_failure_summary = await asyncio.to_thread(
        repo.get_ingest_failure_summary_for_user,
        resolved_user_id,
        ingest_failure_days,
        5,
        3,
    )
    return {
        "user_identifier": user_identifier,
        "resolved_user_id": resolved_user_id,
        "active_counts": {
            "ingest_jobs": active_ingest_jobs,
            "s2_jobs": active_s2_jobs,
        },
        "ingest_failure_summary": ingest_failure_summary,
        "recent_jobs": jobs,
        "recent_feedback": feedback,
    }
