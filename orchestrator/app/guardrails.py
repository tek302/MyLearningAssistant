from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.db.repo import SupabaseRepo

DEFAULT_MAX_ACTIVE_INGEST_JOBS_PER_USER = 3
DEFAULT_MAX_ACTIVE_S2_JOBS_PER_USER = 1
DEFAULT_MIN_S2_JOB_INTERVAL_SECONDS = 300


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def max_active_ingest_jobs_per_user() -> int:
    return max(0, _int_env("MAX_ACTIVE_INGEST_JOBS_PER_USER", DEFAULT_MAX_ACTIVE_INGEST_JOBS_PER_USER))


def max_active_s2_jobs_per_user() -> int:
    return max(0, _int_env("MAX_ACTIVE_S2_JOBS_PER_USER", DEFAULT_MAX_ACTIVE_S2_JOBS_PER_USER))


def min_s2_job_interval_seconds() -> int:
    return max(0, _int_env("MIN_S2_JOB_INTERVAL_SECONDS", DEFAULT_MIN_S2_JOB_INTERVAL_SECONDS))


def enforce_ingest_guardrails(repo: SupabaseRepo, user_id: str) -> None:
    """Reject new ingest enqueue when the user already has too many active ingest jobs."""
    max_active = max_active_ingest_jobs_per_user()
    if max_active <= 0:
        return
    active = repo.count_jobs_for_user(user_id, job_type="ingest", states=["queued", "running"])
    if active >= max_active:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many active ingest jobs. Limit is {max_active} per user.",
        )


def enforce_s2_guardrails(repo: SupabaseRepo, user_id: str) -> None:
    """Reject new S2 enqueue when there is already an active S2 job or the last *successful* job was too recent."""
    max_active = max_active_s2_jobs_per_user()
    if max_active > 0:
        active = repo.count_jobs_for_user(user_id, job_type="s2", states=["queued", "running"])
        if active >= max_active:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many active S2 jobs. Limit is {max_active} per user.",
            )

    min_interval = min_s2_job_interval_seconds()
    if min_interval <= 0:
        return
    latest = repo.get_latest_job_created_at_for_user(
        user_id, job_type="s2", exclude_states=["failed"],
    )
    if latest is None:
        return
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - latest).total_seconds()
    if elapsed < min_interval:
        wait_seconds = int(min_interval - elapsed)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"S2 job was requested too recently. Try again in about {wait_seconds} seconds.",
        )
