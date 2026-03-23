"""
S2 consolidation: aggregate recent S1 summaries into one weekly (topic-scope) S2 summary.
Option B: single "This Week" S2 per user per week.
Trigger: POST /jobs/s2 (per user) or POST /worker/s2-schedule (scheduler, all users).

Weekly window (new): America/New_York, [start Fri 00:00 ET, start+7d Fri 00:00 ET).
  Aligns with Cloud Scheduler "0 0 * * 5" (Friday midnight ET): each run summarizes the
  7-day ET window that *just ended* at that instant.

Legacy: week_start strings that are Mondays (YYYY-MM-DD) still use UTC Monday 00:00 — UTC+7d
  for source selection, so old rows/API remain interpretable.
"""
import logging
from datetime import datetime, timezone, timedelta, time
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import os

from app.db.repo import SupabaseRepo
from app.utils.summarization import create_s2_summary, create_s2_summary_v2, get_summary_model

logger = logging.getLogger(__name__)

NOTES_DAYS = 30
NOTES_LIMIT = 30
FEEDBACK_DAYS = 30
FEEDBACK_LIMIT = 30


def _s2_summary_version() -> str:
    return os.getenv("S2_SUMMARY_VERSION", "v2").strip().lower()


def _prompt_version() -> str:
    ver = _s2_summary_version()
    return f"s2-summary-{ver}"
S2_ET = ZoneInfo("America/New_York")


def get_s2_generation_meta() -> Dict[str, Any]:
    """Snapshot minimal generation metadata for admin monitoring."""
    return {
        "prompt_version": _prompt_version(),
        "model_snapshot": {
            "llm": get_summary_model(),
            "embedding_model": None,
        },
    }


def _week_start_monday_utc(dt: datetime) -> str:
    """Return ISO date (YYYY-MM-DD) of Monday of the week containing dt (UTC calendar)."""
    weekday = dt.weekday()
    monday = dt - timedelta(days=weekday)
    return monday.strftime("%Y-%m-%d")


def _parse_week_start_legacy_monday_utc(week_start: str) -> Tuple[datetime, datetime]:
    """Parse legacy Monday key: UTC Monday 00:00 to next Monday 00:00."""
    dt = datetime.fromisoformat(week_start.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    monday_str = _week_start_monday_utc(dt)
    start_ts = datetime.fromisoformat(monday_str).replace(tzinfo=timezone.utc)
    end_ts = start_ts + timedelta(days=7)
    return start_ts, end_ts


def last_friday_midnight_et(now_et: datetime) -> datetime:
    """Most recent Friday 00:00 America/New_York on or before now_et (date-wise in ET)."""
    today_midnight = now_et.replace(hour=0, minute=0, second=0, microsecond=0)
    wd = now_et.weekday()
    if wd >= 4:
        delta = wd - 4
    else:
        delta = wd + 3
    return today_midnight - timedelta(days=delta)


def etf_completed_week_bounds_for_scheduler(now_utc: datetime) -> Tuple[str, datetime, datetime]:
    """
    Closed window [prev Fri 00:00 ET, this Fri 00:00 ET) ending at the most recent Fri 00:00 ET.
    Used when Cloud Scheduler fires Friday ~00:00 ET so Sat/Sun before next run are not dropped.
    Returns (week_start_key, start_utc, end_utc_exclusive) — key is the *start* Friday YYYY-MM-DD (ET).
    """
    now_et = now_utc.astimezone(S2_ET)
    end_exclusive = last_friday_midnight_et(now_et)
    start_exclusive = end_exclusive - timedelta(days=7)
    week_start_key = start_exclusive.date().isoformat()
    return (
        week_start_key,
        start_exclusive.astimezone(timezone.utc),
        end_exclusive.astimezone(timezone.utc),
    )


def etf_week_start_key_when_payload_none(now_utc: datetime) -> str:
    """
    week_start for POST /jobs/s2 with no body: open ET week [last Fri 00:00, next Fri 00:00).
    On Friday 00:00–00:09 ET, use the *closed* week that just ended (same as scheduler) so manual
    re-runs near cron match scheduled behavior.
    """
    now_et = now_utc.astimezone(S2_ET)
    lf = last_friday_midnight_et(now_et)
    if now_et.weekday() == 4 and now_et.hour == 0 and now_et.minute < 10:
        end_exclusive = lf
        start_exclusive = end_exclusive - timedelta(days=7)
        return start_exclusive.date().isoformat()
    start_exclusive = lf
    return start_exclusive.date().isoformat()


def _parse_week_start_fri_et(week_start: str) -> Tuple[datetime, datetime]:
    """Friday YYYY-MM-DD (ET) -> [Fri 00:00 ET, Fri+7d 00:00 ET) in UTC."""
    d = datetime.fromisoformat(week_start.replace("Z", "+00:00")).date()
    start_et = datetime.combine(d, time.min, tzinfo=S2_ET)
    end_et = start_et + timedelta(days=7)
    return start_et.astimezone(timezone.utc), end_et.astimezone(timezone.utc)


def _period_display_et(start_utc: datetime, end_utc_exclusive: datetime) -> Dict[str, str]:
    """Inclusive calendar dates in ET for UI (end is day before exclusive end at ET midnight)."""
    last_instant = end_utc_exclusive - timedelta(microseconds=1)
    end_inc = last_instant.astimezone(S2_ET).date().isoformat()
    start_inc = start_utc.astimezone(S2_ET).date().isoformat()
    return {
        "period_start_et": start_inc,
        "period_end_et_inclusive": end_inc,
        "period_tz": "America/New_York",
    }


def _resolve_bounds(
    week_start: Optional[str], now_utc: datetime
) -> Tuple[str, datetime, datetime, bool]:
    """
    Returns (normalized_key, start_utc, end_utc_exclusive, legacy_monday).
    """
    if week_start is None:
        key = etf_week_start_key_when_payload_none(now_utc)
        start_ts, end_ts = _parse_week_start_fri_et(key)
        return key, start_ts, end_ts, False

    raw = datetime.fromisoformat(week_start.replace("Z", "+00:00")).date()
    if raw.weekday() == 0:
        start_ts, end_ts = _parse_week_start_legacy_monday_utc(week_start)
        norm = _week_start_monday_utc(datetime.fromisoformat(week_start.replace("Z", "+00:00")).replace(tzinfo=timezone.utc))
        return norm, start_ts, end_ts, True

    start_ts, end_ts = _parse_week_start_fri_et(week_start)
    norm = raw.isoformat()
    return norm, start_ts, end_ts, False


def resolve_s2_week_start_key(week_start: Optional[str], now_utc: Optional[datetime] = None) -> str:
    """Same normalization as run_s2_consolidation (for job_runner / recommendations)."""
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    norm, _, _, _ = _resolve_bounds(week_start, now_utc)
    return norm


def run_s2_consolidation(
    user_id: str,
    week_start: Optional[str] = None,
    days: int = 7,
    now_utc: Optional[datetime] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Build one S2 summary for the user.
    - week_start omitted: ET Friday-aligned open week (see etf_week_start_key_when_payload_none).
    - week_start YYYY-MM-DD: if Monday (legacy), UTC Mon–Mon week; otherwise Friday ET start of window.
    Returns (True, None) if S2 was created, (False, reason) if skipped.
    """
    repo = SupabaseRepo()
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    norm_key, start_ts, end_ts, legacy_monday = _resolve_bounds(week_start, now_utc)
    week_start = norm_key

    sources = repo.get_sources_for_user_between(user_id, start_ts, end_ts)
    window_desc = f"week {week_start}" + (" (legacy UTC Mon)" if legacy_monday else " (ET Fri)")

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

    use_v2 = _s2_summary_version() == "v2"

    if use_v2:
        summary = _run_s2_v2(repo, user_id, week_start, start_ts, combined_text)
    else:
        summary = create_s2_summary(combined_text)

    repo.delete_s2_for_user_week(user_id, week_start)
    period_extra = _period_display_et(start_ts, end_ts)

    v2_extra = {}
    if use_v2:
        for key in ("sections", "emerging_topics", "connections", "trajectory", "reflection"):
            if summary.get(key) is not None:
                v2_extra[key] = summary[key]

    repo.insert_summary_s2(
        user_id=user_id,
        week_start=week_start,
        tldr=summary["tldr"],
        bullets=summary["bullets"],
        source_ids=source_ids,
        topic_name="This Week",
        extra_meta={**get_s2_generation_meta(), **period_extra, **v2_extra},
    )
    logger.info(
        "s2 user_id=%s week_start=%s version=%s sections=%d bullets=%d",
        user_id, week_start, _s2_summary_version(),
        len(summary.get("sections") or []), len(summary.get("bullets") or []),
    )
    return True, None


def _run_s2_v2(
    repo: SupabaseRepo, user_id: str, week_start: str, start_ts: datetime, s1_text: str,
) -> Dict[str, Any]:
    """Load personalization context and call create_s2_summary_v2."""
    keywords = []
    try:
        keywords = repo.list_user_keywords(user_id, status="active")
    except Exception as e:
        logger.warning("s2 v2: list_user_keywords failed (continuing): %s", e)

    notes_text = ""
    try:
        since_ts = datetime.now(timezone.utc) - timedelta(days=NOTES_DAYS)
        notes_list = repo.list_notes_for_user(user_id, since_ts=since_ts, limit=NOTES_LIMIT, offset=0)
        parts = []
        for n in notes_list:
            topic = (n.get("topic") or "").strip()
            content = (n.get("content") or "").strip()
            if topic or content:
                parts.append(f"{topic} {content}".strip())
        notes_text = "\n".join(parts)
    except Exception as e:
        logger.warning("s2 v2: list_notes_for_user failed (continuing): %s", e)

    feedback_text = ""
    try:
        fb_since = datetime.now(timezone.utc) - timedelta(days=FEEDBACK_DAYS)
        fb_events = repo.list_recent_feedback_texts_for_user(user_id, since_ts=fb_since, limit=FEEDBACK_LIMIT)
        fb_parts = []
        for ev in fb_events:
            action = (ev.get("action") or "").strip()
            comment = (ev.get("comment") or "").strip()
            reasons = ev.get("reasons") or []
            if isinstance(reasons, list):
                reasons = ", ".join(str(r) for r in reasons if r)
            else:
                reasons = str(reasons)
            line = f"[{action}] {reasons} {comment}".strip()
            if line and line != "[]":
                fb_parts.append(line)
        feedback_text = "\n".join(fb_parts)
    except Exception as e:
        logger.warning("s2 v2: list_recent_feedback_texts_for_user failed (continuing): %s", e)

    prev_s2_text = ""
    try:
        prev_key = (datetime.fromisoformat(week_start) - timedelta(days=7)).date().isoformat()
        prev_s2 = repo.get_s2_for_user_week(user_id, prev_key)
        if prev_s2:
            parts = []
            if prev_s2.get("tldr"):
                parts.append(prev_s2["tldr"])
            for b in (prev_s2.get("bullets") or []):
                if b:
                    parts.append(str(b).strip())
            prev_s2_text = "\n".join(parts)
    except Exception as e:
        logger.warning("s2 v2: get prev S2 failed (continuing): %s", e)

    return create_s2_summary_v2(
        s1_text=s1_text,
        keywords=keywords,
        notes_text=notes_text,
        feedback_text=feedback_text,
        prev_s2_text=prev_s2_text,
    )
