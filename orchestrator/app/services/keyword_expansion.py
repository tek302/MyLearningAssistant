"""
Stage 1: Keyword Expansion — LLM suggests new research keywords based on user's
current keyword set, recent S2 summary, and notes.
Corresponds to MEMORY_EVOLUTION_DESIGN.md §4 (D2) and EXECUTION_PLAN §5.3.
"""
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.constants.keywords import USER_KEYWORD_MAX_CHARS
from app.db.repo import SupabaseRepo
from app.utils.llm_client import get_chat_client, get_model

logger = logging.getLogger(__name__)

MAX_SUGGESTIONS_PER_WEEK = 3
REJECT_COOLDOWN_DAYS = 30
NOTES_DAYS = 30
NOTES_LIMIT = 30


def _normalize_suggested_keyword(kw: str) -> str:
    """Keep suggested labels short for search/UI; LLM should already comply (stage1-v2)."""
    s = (kw or "").strip()
    if len(s) <= USER_KEYWORD_MAX_CHARS:
        return s
    cut = s[:USER_KEYWORD_MAX_CHARS]
    if " " in cut:
        return cut.rsplit(" ", 1)[0].strip() or cut.strip()
    return cut.strip()


def _build_stage1_prompt(
    keywords: List[Dict[str, Any]],
    s2_text: str,
    notes_text: str,
    rejected_recently: List[str],
) -> str:
    kw_lines = "\n".join(
        f"- {k['keyword']} (weight={k['weight']:.2f}, source={k['source']})"
        for k in keywords
    )
    reject_note = ""
    if rejected_recently:
        reject_note = f"\n\nDo NOT suggest these (rejected recently): {', '.join(rejected_recently)}"

    return f"""You are a research advisor. Based on the user's current research keyword set and recent learning activity, suggest exactly {MAX_SUGGESTIONS_PER_WEEK} new research keywords they should explore.

Each suggestion must be one of these types:
- derivative: a keyword derived from an existing keyword (specify parent)
- emerging: a topic gaining traction in the user's research area
- cross_domain: a keyword connecting two different areas the user studies
- deepening: a more specific sub-topic of an existing keyword (specify parent)

**keyword format (required):** `keyword` must be a SHORT search-friendly label: at most ~6 words and 80 characters, no full sentences. Put explanations only in `reason`.

Current keyword set:
{kw_lines}

Recent weekly summary (S2):
{s2_text[:2000] if s2_text else '(none)'}

Recent notes:
{notes_text[:1500] if notes_text else '(none)'}
{reject_note}

Respond with a JSON array of exactly {MAX_SUGGESTIONS_PER_WEEK} objects:
[
  {{"keyword": "...", "parent_keyword": "..." or null, "type": "derivative|emerging|cross_domain|deepening", "reason": "one sentence why", "confidence": 0.0-1.0}}
]

Only return the JSON array, no other text."""


def run_keyword_expansion(
    user_id: str,
    week_start: str,
    repo: Optional[SupabaseRepo] = None,
    thread_id: Optional[str] = None,
) -> Tuple[List[str], Optional[str]]:
    """
    Run Stage 1 keyword expansion for a user (scoped to one interest thread).
    Returns (list of suggestion ids, error_message or None).
    """
    from app.services.thread_effective_keywords import build_effective_keywords, parse_thread_weights

    repo = repo or SupabaseRepo()
    tid = thread_id or repo.get_or_create_default_thread_id(user_id)

    global_kw = repo.list_user_keywords(user_id, status="active")
    if not global_kw:
        return [], "no active keywords"
    try:
        tw_rows = repo.list_thread_keyword_weights(tid, user_id)
        keywords = build_effective_keywords(global_kw, parse_thread_weights(tw_rows))
    except Exception:
        keywords = global_kw

    s2_row = repo.get_s2_for_user_week(user_id, week_start, thread_id=tid)
    s2_text = ""
    if s2_row:
        parts = []
        if s2_row.get("tldr"):
            parts.append(s2_row["tldr"])
        for b in (s2_row.get("bullets") or []):
            if b:
                parts.append(str(b).strip())
        s2_text = "\n".join(parts)

    since_ts = datetime.now(timezone.utc) - timedelta(days=NOTES_DAYS)
    try:
        notes_list = repo.list_notes_for_user(
            user_id, since_ts=since_ts, limit=NOTES_LIMIT, offset=0, thread_id=tid,
        )
        if not notes_list:
            notes_list = repo.list_notes_for_user(user_id, since_ts=since_ts, limit=NOTES_LIMIT, offset=0)
    except Exception:
        notes_list = []
    notes_text = "\n".join(
        f"{(n.get('topic') or '')} {(n.get('content') or '')}".strip()
        for n in notes_list if n.get("content")
    )

    rejected_recently = repo.get_rejected_keywords_within_days(user_id, days=REJECT_COOLDOWN_DAYS)

    prompt = _build_stage1_prompt(keywords, s2_text, notes_text, rejected_recently)

    keyword_snapshot = repo.get_active_keyword_snapshot(user_id)
    run_id = repo.insert_recommendation_generation_run(
        user_id=user_id,
        week_start=week_start,
        stage="stage1",
        keyword_snapshot=keyword_snapshot,
        meta={
            "prompt_version": "stage1-v2",
            "model": get_model("keyword_expansion"),
            "thread_id": tid,
        },
    )

    try:
        client = get_chat_client()
        response = client.chat.completions.create(
            model=get_model("keyword_expansion"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500,
        )
        raw = response.choices[0].message.content.strip()
    except Exception as e:
        logger.exception("Stage 1 LLM call failed: %s", e)
        return [], f"LLM call failed: {e}"

    try:
        suggestions = json.loads(raw)
        if not isinstance(suggestions, list):
            return [], f"LLM returned non-array: {raw[:200]}"
    except json.JSONDecodeError:
        start = raw.find("[")
        end = raw.rfind("]")
        if start >= 0 and end > start:
            try:
                suggestions = json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                return [], f"Failed to parse LLM response: {raw[:200]}"
        else:
            return [], f"No JSON array in LLM response: {raw[:200]}"

    existing_kw_lower = {k["keyword"].lower() for k in global_kw}
    rejected_lower = {r.lower() for r in rejected_recently}
    filtered = []
    for s in suggestions[:MAX_SUGGESTIONS_PER_WEEK]:
        kw = _normalize_suggested_keyword((s.get("keyword") or "").strip())
        if not kw:
            continue
        if kw.lower() in existing_kw_lower or kw.lower() in rejected_lower:
            continue
        s = {**s, "keyword": kw}
        filtered.append(s)

    if not filtered:
        return [], "all suggestions filtered out"

    suggestion_ids = repo.insert_keyword_suggestions(
        user_id=user_id,
        suggestions=filtered,
        week_start=week_start,
        source_run_id=run_id,
        thread_id=tid,
    )

    logger.info(
        "stage1_keyword_expansion: user=%s week=%s thread=%s suggestions=%d",
        user_id, week_start, tid, len(suggestion_ids),
    )
    return suggestion_ids, None
