"""
Keyword weight recalculation with FuXi-γ time decay.
Corresponds to MEMORY_EVOLUTION_DESIGN.md §5 (D3) and EXECUTION_PLAN §5.2.

user_explicit keywords: no decay (feedback only adjusts weight)
stage1_accepted / s2_derived: exp(-(age/τ)^β) decay applied
Declining threshold: weight < 0.3 → status='declining'
"""
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db.repo import SupabaseRepo

logger = logging.getLogger(__name__)

TAU = 60.0    # τ: characteristic time in days
BETA = 1.5    # β: shape parameter (>1 = faster late decay)
DECLINING_THRESHOLD = 0.3
FEEDBACK_SMOOTHING = 1  # Laplace smoothing for feedback ratio


def _compute_time_decay(age_days: float) -> float:
    """FuXi-γ style decay: exp(-(age/τ)^β)"""
    if age_days <= 0:
        return 1.0
    return math.exp(-((age_days / TAU) ** BETA))


def _compute_feedback_factor(up: int, down: int) -> float:
    """Feedback factor: ratio of positive feedback with smoothing. Range ~0.5-1.0"""
    total = up + down + FEEDBACK_SMOOTHING
    return (up + FEEDBACK_SMOOTHING * 0.5) / total


def recalc_keyword_weights(
    user_id: str,
    repo: Optional[SupabaseRepo] = None,
) -> Dict[str, Any]:
    """
    Recalculate weights for all active keywords of a user.
    Returns summary dict with counts of updated/declining keywords.
    """
    repo = repo or SupabaseRepo()
    keywords = repo.list_user_keywords(user_id, status="active")
    keywords += repo.list_user_keywords(user_id, status="declining")

    now = datetime.now(timezone.utc)
    updated_count = 0
    declining_count = 0
    reactivated_count = 0

    for kw in keywords:
        source = kw.get("source", "")
        old_weight = float(kw.get("weight", 1.0))
        old_status = kw.get("status", "active")

        if source == "user_explicit":
            feedback_factor = _compute_feedback_factor(
                kw.get("paper_feedback_up", 0),
                kw.get("paper_feedback_down", 0),
            )
            new_weight = max(0.5, feedback_factor)
        else:
            last_activity_str = kw.get("last_activity") or kw.get("created_at")
            if last_activity_str:
                if isinstance(last_activity_str, str):
                    try:
                        last_activity = datetime.fromisoformat(last_activity_str)
                    except ValueError:
                        last_activity = now
                else:
                    last_activity = last_activity_str
            else:
                last_activity = now

            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=timezone.utc)

            age_days = (now - last_activity).total_seconds() / 86400.0
            decay = _compute_time_decay(age_days)

            feedback_factor = _compute_feedback_factor(
                kw.get("paper_feedback_up", 0),
                kw.get("paper_feedback_down", 0),
            )

            new_weight = decay * feedback_factor

        new_weight = round(new_weight, 4)
        if new_weight < DECLINING_THRESHOLD:
            new_status = "declining"
        else:
            new_status = "active"

        weight_changed = abs(new_weight - old_weight) > 0.001
        status_changed = new_status != old_status

        if weight_changed or status_changed:
            repo.update_user_keyword(
                kw["id"], user_id,
                weight=new_weight if weight_changed else None,
                status=new_status if status_changed else None,
            )
            updated_count += 1

        if new_status == "declining" and old_status != "declining":
            declining_count += 1
        if new_status == "active" and old_status == "declining":
            reactivated_count += 1

    logger.info(
        "keyword_weight_recalc: user=%s total=%d updated=%d declining=%d reactivated=%d",
        user_id, len(keywords), updated_count, declining_count, reactivated_count,
    )
    return {
        "total": len(keywords),
        "updated": updated_count,
        "newly_declining": declining_count,
        "reactivated": reactivated_count,
    }
