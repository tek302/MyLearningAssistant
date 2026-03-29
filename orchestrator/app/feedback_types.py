"""Shared constants for feedback target types, actions, and reasons."""

from __future__ import annotations

FEEDBACK_TARGET_TYPES = (
    "summary_s1",
    "summary_s2",
    "recommendation",
    "rag_answer",
)

FEEDBACK_ACTIONS = (
    "thumbs_up",
    "thumbs_down",
    "save",
    "dismiss",
    "open",
    "process",
    "remove",
)

SUMMARY_FEEDBACK_REASONS = (
    "helpful",
    "not_helpful",
    "too_generic",
    "too_long",
    "too_shallow",
    "wrong_focus",
    "already_knew_this",
    "want_more_like_this",
)

RECOMMENDATION_FEEDBACK_REASONS = (
    "relevant",
    "not_relevant",
    "too_basic",
    "too_advanced",
    "want_more_like_this",
    "not_interested",
    "duplicate_interest",
)

RAG_FEEDBACK_REASONS = (
    "not_relevant",
    "hallucination_suspected",
    "too_shallow",
    "good_answer",
)

FEEDBACK_REASONS = SUMMARY_FEEDBACK_REASONS + tuple(
    reason for reason in RECOMMENDATION_FEEDBACK_REASONS if reason not in SUMMARY_FEEDBACK_REASONS
) + tuple(reason for reason in RAG_FEEDBACK_REASONS if reason not in SUMMARY_FEEDBACK_REASONS and reason not in RECOMMENDATION_FEEDBACK_REASONS)

POSITIVE_FEEDBACK_ACTIONS = ("thumbs_up", "save", "open", "process")
NEGATIVE_FEEDBACK_ACTIONS = ("thumbs_down", "dismiss", "remove")

