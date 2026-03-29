"""User feedback API."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from ..db.repo import SupabaseRepo
from ..feedback_types import FEEDBACK_ACTIONS, FEEDBACK_REASONS, FEEDBACK_TARGET_TYPES
from ..services.arxiv_recommendations import get_recommendation_generation_meta
from ..services.s2_consolidation import get_s2_generation_meta
from ..utils.deps import get_user_id

router = APIRouter(prefix="/feedback", tags=["feedback"])
logger = logging.getLogger(__name__)


def _merge_meta(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        if value is None:
            continue
        if key == "model_snapshot" and isinstance(value, dict):
            existing = merged.get("model_snapshot")
            snapshot = dict(existing) if isinstance(existing, dict) else {}
            for sub_key, sub_value in value.items():
                if sub_value is not None:
                    snapshot[sub_key] = sub_value
            if snapshot:
                merged["model_snapshot"] = snapshot
            continue
        merged[key] = value
    return merged


def _enrich_feedback_target(
    repo: SupabaseRepo,
    user_id: str,
    body: "FeedbackCreateBody",
) -> tuple[dict[str, Any], Optional[str], Optional[str]]:
    meta = dict(body.meta or {})

    if body.target_type == "rag_answer":
        try:
            rag_run = repo.get_rag_run_for_user(user_id, body.target_id)
        except Exception as e:
            logger.warning("get_rag_run_for_user failed (continuing without enrich): %s", e)
            rag_run = None
        if rag_run:
            meta = _merge_meta(
                meta,
                {
                    "run_id": rag_run.get("id"),
                    "query_snapshot": rag_run.get("query"),
                    "top_k": rag_run.get("top_k"),
                    "status": rag_run.get("status"),
                    "latency_ms": rag_run.get("latency_ms"),
                    "error_message": rag_run.get("error_message"),
                    "created_at": rag_run.get("created_at"),
                    "completed_at": rag_run.get("completed_at"),
                },
            )
        else:
            # Keep feedback ingestion resilient even when rag_runs logging is unavailable
            # (e.g. missing optional table or run log insertion failure).
            meta = _merge_meta(
                meta,
                {
                    "run_id": body.target_id,
                    "rag_run_lookup": "not_found",
                },
            )
        return meta, None, None

    if body.target_type == "recommendation":
        target = repo.get_recommendation_by_id(body.target_id, user_id)
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")
        meta = _merge_meta(
            meta,
            {
                "title": target.get("title"),
                "url": target.get("url"),
                "source": target.get("source"),
                "topic_name": target.get("topic_name"),
                "week_start": target.get("week_start"),
                **get_recommendation_generation_meta(),
            },
        )
        return meta, None, target.get("week_start")

    target = repo.get_summary_by_id(body.target_id, user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Summary not found")

    expected_kind = "S2" if body.target_type == "summary_s2" else "S1"
    if (target.get("kind") or "").upper() != expected_kind:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Summary target type mismatch")

    extra = target.get("extra") or {}
    if not isinstance(extra, dict):
        extra = {}
    summary_meta = {
        "topic_name": extra.get("topic_name"),
        "week_start": extra.get("week_start"),
        "tldr": target.get("tldr"),
        "source_id": target.get("source_id"),
        "prompt_version": extra.get("prompt_version"),
        "model_snapshot": extra.get("model_snapshot"),
    }
    if body.target_type == "summary_s2" and not summary_meta.get("prompt_version"):
        summary_meta = _merge_meta(summary_meta, get_s2_generation_meta())
    derived_week_start = extra.get("week_start")
    derived_source_id = target.get("source_id")
    return _merge_meta(meta, summary_meta), derived_source_id, derived_week_start


class FeedbackCreateBody(BaseModel):
    target_type: str = Field(..., description="summary_s1 | summary_s2 | recommendation")
    target_id: str = Field(..., description="UUID of summary or recommendation")
    action: str = Field(..., description="thumbs_up | thumbs_down | save | dismiss | open")
    reasons: list[str] = Field(default_factory=list)
    comment: Optional[str] = Field(default=None, max_length=2000)
    source_id: Optional[str] = Field(default=None)
    week_start: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    meta: dict[str, Any] = Field(default_factory=dict)
    client_event_id: Optional[str] = Field(default=None, max_length=100)

    @field_validator("target_type")
    @classmethod
    def validate_target_type(cls, value: str) -> str:
        if value not in FEEDBACK_TARGET_TYPES:
            raise ValueError(f"target_type must be one of {FEEDBACK_TARGET_TYPES}")
        return value

    @field_validator("target_id")
    @classmethod
    def validate_target_id(cls, value: str) -> str:
        s = (value or "").strip()
        uuid.UUID(s)
        return s

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        if value not in FEEDBACK_ACTIONS:
            raise ValueError(f"action must be one of {FEEDBACK_ACTIONS}")
        return value

    @field_validator("reasons")
    @classmethod
    def validate_reasons(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip() for v in value if v and v.strip()]
        if len(cleaned) > 10:
            raise ValueError("reasons must contain at most 10 items")
        invalid = [v for v in cleaned if v not in FEEDBACK_REASONS]
        if invalid:
            raise ValueError(f"invalid reasons: {invalid}")
        return cleaned

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, value: Optional[str]) -> Optional[str]:
        if value:
            uuid.UUID(value)
        return value

    @field_validator("week_start")
    @classmethod
    def normalize_week_start(cls, value: Optional[str]) -> Optional[str]:
        """Avoid empty string reaching SQL ::date (invalid)."""
        if value is None:
            return None
        s = value.strip()
        return s if s else None


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_feedback(
    user_id: Annotated[str, Depends(get_user_id)],
    body: FeedbackCreateBody,
):
    """Create a feedback event for summary, recommendation, or RAG answer."""
    repo = SupabaseRepo()
    enriched_meta, derived_source_id, derived_week_start = _enrich_feedback_target(repo, user_id, body)
    try:
        feedback_id = await asyncio.to_thread(
            repo.insert_feedback_event,
            user_id,
            target_type=body.target_type,
            target_id=body.target_id,
            action=body.action,
            reasons=body.reasons,
            comment=body.comment,
            source_id=derived_source_id,
            week_start=derived_week_start or body.week_start,
            meta=enriched_meta,
            client_event_id=body.client_event_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create feedback: {e}",
        ) from e
    return {"id": feedback_id, "status": "ok"}


@router.get("")
async def list_feedback(
    user_id: Annotated[str, Depends(get_user_id)],
    target_type: Optional[str] = Query(None),
    target_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List current user's feedback events."""
    if target_type is not None and target_type not in FEEDBACK_TARGET_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid target_type")
    repo = SupabaseRepo()
    items = await asyncio.to_thread(
        repo.list_feedback_events,
        user_id=user_id,
        target_type=target_type,
        target_id=target_id,
        limit=limit,
        offset=offset,
    )
    return {"events": items}

