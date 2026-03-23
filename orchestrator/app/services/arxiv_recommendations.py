"""
Weekly arXiv recommendations — 2-Stage Pipeline Stage 2.
Primary input: user's active keyword set (keyword-anchored profile).
Secondary signals: S2 text, notes, feedback — used to enrich search and reranking.
Records recommendation_generation_runs for full traceability.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import requests

from app.db.repo import SupabaseRepo
from app.feedback_types import NEGATIVE_FEEDBACK_ACTIONS, POSITIVE_FEEDBACK_ACTIONS
from app.utils.embeddings import create_embeddings, get_embedding_model

logger = logging.getLogger(__name__)

ARXIV_API_URL = "http://export.arxiv.org/api/query"
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}
MAX_CANDIDATES = 10
TOP_N = 3
USER_AGENT = "LearningAgent-Recommendations/1.0"
NOTES_DAYS_FOR_RECOMMENDATIONS = 30
NOTES_LIMIT_FOR_RECOMMENDATIONS = 50
FEEDBACK_DAYS_FOR_RECOMMENDATIONS = 30
FEEDBACK_LIMIT_FOR_RECOMMENDATIONS = 50
NEGATIVE_FEEDBACK_REASONS = {
    "not_relevant",
    "too_basic",
    "too_advanced",
    "not_interested",
    "wrong_focus",
    "too_generic",
    "too_long",
    "too_shallow",
}
POSITIVE_FEEDBACK_REASONS = {
    "want_more_like_this",
    "helpful",
    "relevant",
}
NEGATIVE_PENALTY_WEIGHT = 0.15
KEYWORD_MATCH_BONUS = 0.10
RECOMMENDATION_PROMPT_VERSION = "rec-arxiv-v3-keyword"


def get_recommendation_generation_meta() -> dict[str, Any]:
    """Snapshot minimal recommendation generation metadata for admin monitoring."""
    return {
        "prompt_version": RECOMMENDATION_PROMPT_VERSION,
        "model_snapshot": {
            "llm": None,
            "embedding_model": get_embedding_model(),
        },
    }


def _keywords_to_search_query(keywords: List[Dict[str, Any]], max_terms: int = 6) -> str:
    """Build arXiv search_query from keyword set, weighted by keyword weight."""
    if not keywords:
        return "all:machine+learning"
    sorted_kws = sorted(keywords, key=lambda k: float(k.get("weight", 0)), reverse=True)
    terms = []
    for kw in sorted_kws[:max_terms]:
        word = kw["keyword"].strip()
        if word:
            terms.append(quote_plus(word))
    if not terms:
        return "all:machine+learning"
    return "all:" + "+".join(terms)


def _s2_text_to_search_query(s2_text: str, max_terms: int = 5) -> str:
    """Build arXiv search_query from S2 text. Fallback when no keywords."""
    if not (s2_text and s2_text.strip()):
        return "all:machine+learning"
    text = re.sub(r"\s+", " ", s2_text.strip()).strip()
    words = [w for w in text.split() if len(w) > 1 and w.isalnum()][:max_terms]
    if not words:
        return "all:machine+learning"
    return "all:" + "+".join(quote_plus(w) for w in words)


def _compute_keyword_match_score(
    candidate_text: str,
    keywords: List[Dict[str, Any]],
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Compute keyword match bonus and identify triggering keywords.
    Returns (bonus_score, list of matched keywords with contribution).
    """
    if not keywords or not candidate_text:
        return 0.0, []
    text_lower = candidate_text.lower()
    matched = []
    total_weight = sum(float(k.get("weight", 0)) for k in keywords) or 1.0
    bonus = 0.0
    for kw in keywords:
        kw_text = kw["keyword"].lower()
        if kw_text in text_lower:
            w = float(kw.get("weight", 1.0))
            contribution = w / total_weight
            bonus += KEYWORD_MATCH_BONUS * contribution
            matched.append({
                "keyword": kw["keyword"],
                "weight": round(w, 4),
                "contribution": "primary" if contribution > 0.3 else "secondary",
            })
    return round(bonus, 4), matched


def _fetch_arxiv_search(search_query: str, max_results: int = MAX_CANDIDATES) -> List[Dict[str, Any]]:
    """Call arXiv API search, parse entries. Returns list of {title, abstract, url} (url = abs link)."""
    try:
        r = requests.get(
            ARXIV_API_URL,
            params={
                "search_query": search_query,
                "max_results": max_results,
                "sortBy": "relevance",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        r.raise_for_status()
    except Exception as e:
        logger.warning("arXiv search failed: %s", e)
        return []

    entries: List[Dict[str, Any]] = []
    try:
        root = ET.fromstring(r.content)
        for entry in root.findall("atom:entry", ARXIV_NS):
            title_el = entry.find("atom:title", ARXIV_NS)
            summary_el = entry.find("atom:summary", ARXIV_NS)
            id_el = entry.find("atom:id", ARXIV_NS)
            title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""
            abstract = (summary_el.text or "").strip().replace("\n", " ") if summary_el is not None else ""
            url = (id_el.text or "").strip() if id_el is not None else ""
            if not title or not url:
                continue
            entries.append({"title": title, "abstract": abstract, "url": url})
    except ET.ParseError as e:
        logger.warning("arXiv response parse error: %s", e)
        return []

    return entries


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors."""
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _feedback_event_text_parts(event: Dict[str, Any]) -> List[str]:
    """Extract useful text fields from a feedback event."""
    parts: List[str] = []
    meta = event.get("meta") or {}
    if not isinstance(meta, dict):
        meta = {}
    for key in ("title", "topic_name", "source", "tldr"):
        value = (meta.get(key) or "").strip() if isinstance(meta.get(key), str) else ""
        if value:
            parts.append(value)
    comment = (event.get("comment") or "").strip()
    if comment:
        parts.append(comment)
    return parts


def _collect_feedback_signals(events: List[Dict[str, Any]]) -> Tuple[str, str]:
    """
    Build positive/negative text signals from recent feedback events.
    Positive text is appended to recommendation input.
    Negative text is used as a penalty embedding.
    """
    positive_parts: List[str] = []
    negative_parts: List[str] = []
    for event in events:
        action = (event.get("action") or "").strip()
        reasons = {str(r).strip() for r in (event.get("reasons") or []) if str(r).strip()}
        text_parts = _feedback_event_text_parts(event)
        if not text_parts:
            continue
        joined = " ".join(text_parts).strip()
        if not joined:
            continue
        if action in POSITIVE_FEEDBACK_ACTIONS or reasons.intersection(POSITIVE_FEEDBACK_REASONS):
            positive_parts.append(joined)
        if action in NEGATIVE_FEEDBACK_ACTIONS or reasons.intersection(NEGATIVE_FEEDBACK_REASONS):
            negative_parts.append(joined)
    return "\n".join(positive_parts).strip(), "\n".join(negative_parts).strip()


def run_arxiv_recommendations_for_week(
    user_id: str,
    week_start: str,
    s2_text: Optional[str] = None,
    repo: Optional[SupabaseRepo] = None,
) -> Tuple[int, Optional[str]]:
    """
    Stage 2: Generate Top 3 arXiv recommendations for the week.
    Primary input: user's active keyword set.
    Secondary: S2 text + notes + feedback (enrichment signals).

    Pipeline:
    1. Load active keywords → build search query from keywords
    2. Fetch S2 + notes + feedback as enrichment context
    3. Search arXiv with keyword-based query
    4. Embed combined text (keywords + S2 + notes), rerank by cosine similarity
    5. Add keyword match bonus for each candidate
    6. Record recommendation_generation_run with full traceability
    7. Insert Top 3 into recommendations

    Returns (inserted_count, None) or (0, error_message).
    """
    repo = repo or SupabaseRepo()
    topic_name = "This Week"

    # ── 1. Load active keywords (primary input) ──
    active_keywords = repo.list_user_keywords(user_id, status="active")
    keyword_snapshot = repo.get_active_keyword_snapshot(user_id)
    has_keywords = len(active_keywords) > 0

    # ── 2. Load S2 text (secondary signal) ──
    if s2_text is None:
        s2_row = repo.get_s2_for_user_week(user_id, week_start)
        if not s2_row:
            if not has_keywords:
                return 0, "no S2 for week and no keywords"
        else:
            parts = []
            if s2_row.get("tldr"):
                parts.append(s2_row["tldr"])
            for b in (s2_row.get("bullets") or []):
                if b:
                    parts.append(str(b).strip())
            s2_text = "\n".join(parts) if parts else ""
    if not s2_text or not s2_text.strip():
        s2_text = ""

    # ── 3. Load notes (secondary signal) ──
    since_ts = datetime.now(timezone.utc) - timedelta(days=NOTES_DAYS_FOR_RECOMMENDATIONS)
    try:
        notes_list = repo.list_notes_for_user(
            user_id, since_ts=since_ts, limit=NOTES_LIMIT_FOR_RECOMMENDATIONS, offset=0,
        )
    except Exception as e:
        logger.warning("list_notes_for_user failed (continuing without notes): %s", e)
        notes_list = []
    interest_parts = []
    for n in notes_list:
        topic = (n.get("topic") or "").strip()
        content = (n.get("content") or "").strip()
        if topic or content:
            interest_parts.append(f"{topic} {content}".strip())
    interest_text = "\n".join(interest_parts) if interest_parts else ""

    # ── 4. Load feedback (secondary signal) ──
    feedback_since_ts = datetime.now(timezone.utc) - timedelta(days=FEEDBACK_DAYS_FOR_RECOMMENDATIONS)
    try:
        feedback_events = repo.list_recent_feedback_texts_for_user(
            user_id, since_ts=feedback_since_ts, limit=FEEDBACK_LIMIT_FOR_RECOMMENDATIONS,
        )
    except Exception as e:
        logger.warning("list_recent_feedback_texts_for_user failed: %s", e)
        feedback_events = []
    positive_feedback_text, negative_feedback_text = _collect_feedback_signals(feedback_events)

    # ── 5. Build combined text for embedding (keywords first, then S2 + notes) ──
    keyword_text = " ".join(k["keyword"] for k in active_keywords) if active_keywords else ""
    combined_parts = [part for part in (keyword_text, s2_text, interest_text, positive_feedback_text) if part and part.strip()]
    combined_text = "\n\n".join(combined_parts).strip()
    if not combined_text:
        return 0, "no keywords, S2, or notes"

    # ── 6. Build search query (keywords primary, S2 fallback) ──
    if has_keywords:
        search_query = _keywords_to_search_query(active_keywords)
    else:
        search_query = _s2_text_to_search_query(combined_text)

    candidates = _fetch_arxiv_search(search_query)
    if len(candidates) < TOP_N:
        logger.info("arxiv_recommendations: got %d candidates, need at least %d", len(candidates), TOP_N)
    if not candidates:
        return 0, "no arXiv candidates"

    # ── 7. Embed combined text + candidates ──
    try:
        combined_embedding = create_embeddings([combined_text[:8000]])[0]
    except Exception as e:
        logger.warning("Combined embedding failed: %s", e)
        return 0, f"embedding failed: {e}"

    negative_embedding = None
    if negative_feedback_text:
        try:
            negative_embedding = create_embeddings([negative_feedback_text[:8000]])[0]
        except Exception:
            negative_embedding = None

    texts_to_embed = [f"{c['title']} {c['abstract']}"[:8000] for c in candidates]
    try:
        candidate_embeddings = create_embeddings(texts_to_embed)
    except Exception as e:
        logger.warning("Candidate embeddings failed: %s", e)
        return 0, f"embedding failed: {e}"

    # ── 8. Score: embedding similarity + keyword match bonus - negative penalty ──
    scored = []
    for i, c in enumerate(candidates):
        if i >= len(candidate_embeddings):
            continue
        candidate_text = f"{c['title']} {c['abstract']}"
        base_score = _cosine_similarity(combined_embedding, candidate_embeddings[i])

        kw_bonus, matched_keywords = _compute_keyword_match_score(candidate_text, active_keywords)

        negative_penalty = 0.0
        if negative_embedding is not None:
            neg_sim = _cosine_similarity(negative_embedding, candidate_embeddings[i])
            negative_penalty = NEGATIVE_PENALTY_WEIGHT * neg_sim

        final_score = base_score + kw_bonus - negative_penalty
        scored.append({
            "candidate": c,
            "base_score": round(base_score, 4),
            "keyword_match": round(kw_bonus, 4),
            "negative_penalty": round(negative_penalty, 4),
            "final_score": round(final_score, 4),
            "matched_keywords": matched_keywords,
        })

    scored.sort(key=lambda x: x["final_score"], reverse=True)
    top = scored[:TOP_N]

    # ── 9. Record recommendation_generation_run for traceability ──
    selected_urls = [s["candidate"]["url"] for s in top]
    avg_breakdown = {
        "avg_base_score": round(sum(s["base_score"] for s in top) / max(len(top), 1), 4),
        "avg_keyword_match": round(sum(s["keyword_match"] for s in top) / max(len(top), 1), 4),
        "avg_negative_penalty": round(sum(s["negative_penalty"] for s in top) / max(len(top), 1), 4),
        "avg_final_score": round(sum(s["final_score"] for s in top) / max(len(top), 1), 4),
        "per_recommendation": [
            {
                "url": s["candidate"]["url"],
                "final_score": s["final_score"],
                "keyword_match": s["keyword_match"],
                "matched_keywords": s["matched_keywords"],
            }
            for s in top
        ],
    }

    recent_suggestions = repo.list_keyword_suggestions(user_id, status="accepted", week_start=week_start, limit=10)
    stage1_suggestion_ids = [s["id"] for s in recent_suggestions]

    run_id = repo.insert_recommendation_generation_run(
        user_id=user_id,
        week_start=week_start,
        stage="stage2",
        keyword_snapshot=keyword_snapshot,
        candidate_count=len(candidates),
        selected_count=len(top),
        query_text=search_query,
        selected_urls=selected_urls,
        score_breakdown=avg_breakdown,
        stage1_suggestion_ids=stage1_suggestion_ids,
        meta=get_recommendation_generation_meta(),
    )

    # ── 10. Insert recommendations ──
    inserted = 0
    for s in top:
        c = s["candidate"]
        try:
            repo.insert_recommendation(
                user_id=user_id,
                topic_name=topic_name,
                week_start=week_start,
                title=c["title"],
                abstract=c.get("abstract") or "",
                url=c["url"],
                source="arXiv",
                score=s["final_score"],
            )
            inserted += 1
        except Exception as e:
            logger.warning("insert_recommendation failed: %s", e)
            return inserted, str(e)

    logger.info(
        "arxiv_recommendations: user_id=%s week_start=%s inserted=%d keywords=%d run_id=%s",
        user_id, week_start, inserted, len(active_keywords), run_id,
    )
    return inserted, None
