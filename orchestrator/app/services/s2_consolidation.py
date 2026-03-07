"""
S2 consolidation: aggregate recent S1 summaries into one weekly (topic-scope) S2 summary.
Option B: single "This Week" S2 per user per week.
Trigger: POST /jobs/s2 (per user) or POST /worker/s2-schedule (scheduler, all users).
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

from app.db.repo import SupabaseRepo
from app.utils.summarization import create_s2_summary

logger = logging.getLogger(__name__)


def _week_start_monday(dt: datetime) -> str:
    """Return ISO date (YYYY-MM-DD) of Monday of the week containing dt (ISO week)."""
    weekday = dt.weekday()
    monday = dt - timedelta(days=weekday)
    return monday.strftime("%Y-%m-%d")


def _parse_week_start(week_start: str) -> Tuple[datetime, datetime]:
    """Parse YYYY-MM-DD to (Monday 00:00 UTC, Monday+7d 00:00 UTC) for that week."""
    dt = datetime.fromisoformat(week_start.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    monday_str = _week_start_monday(dt)
    start_ts = datetime.fromisoformat(monday_str).replace(tzinfo=timezone.utc)
    end_ts = start_ts + timedelta(days=7)
    return start_ts, end_ts


def run_s2_consolidation(user_id: str, week_start: Optional[str] = None, days: int = 7) -> Tuple[bool, Optional[str]]:
    """
    Build one S2 summary for the user.
    - If week_start is provided (YYYY-MM-DD): use sources created in that week [Monday, Monday+7d). Idempotency key = that Monday.
    - If week_start is None: use sources in last `days` days; idempotency key = Monday of current week.
    Returns (True, None) if S2 was created, (False, reason) if skipped (reason for job error / log).
    """
    repo = SupabaseRepo()
    if week_start is None:
        week_start = _week_start_monday(datetime.now(timezone.utc))
        since = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        sources = repo.get_sources_for_user_since(user_id, since_ts=since, days=days)
        window_desc = f"last {days} days"
    else:
        start_ts, end_ts = _parse_week_start(week_start)
        week_start = _week_start_monday(start_ts)  # normalize to Monday
        sources = repo.get_sources_for_user_between(user_id, start_ts, end_ts)
        window_desc = f"week {week_start}"

    if not sources:
        reason = f"no sources in {window_desc}"
        logger.info("s2 user_id=%s week_start=%s %s, skip", user_id, week_start, reason)
        return False, reason

    source_ids = [str(s["id"]) for s in sources]
    s1_list = repo.get_s1_summaries_for_sources(source_ids)
    if not s1_list:
        reason = "no S1 summaries for sources"
        logger.info("s2 user_id=%s week_start=%s %s, skip", user_id, week_start, reason)
        return False, reason

    combined_parts = []
    for row in s1_list:
        tldr = (row.get("tldr") or "").strip()
        if tldr:
            combined_parts.append(tldr)
        bullets = row.get("bullets") or []
        if isinstance(bullets, list):
            for b in bullets:
                if b:
                    combined_parts.append(str(b).strip())
    combined_text = "\n".join(combined_parts)
    if not combined_text.strip():
        reason = "S1 had no text"
        logger.info("s2 user_id=%s week_start=%s %s, skip", user_id, week_start, reason)
        return False, reason

    summary = create_s2_summary(combined_text)
    repo.delete_s2_for_user_week(user_id, week_start)
    repo.insert_summary_s2(
        user_id=user_id,
        week_start=week_start,
        tldr=summary["tldr"],
        bullets=summary["bullets"],
        source_ids=source_ids,
        topic_name="This Week",
    )
    logger.info("s2 user_id=%s week_start=%s created S2 bullets=%s", user_id, week_start, len(summary["bullets"]))
    return True, None
