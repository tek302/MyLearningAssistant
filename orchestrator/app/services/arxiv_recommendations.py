"""
Weekly arXiv recommendations: fetch S2 text, search arXiv, re-rank by S2 embedding similarity, store Top 3.
Called from S2 consolidation after S2 is created.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, List, Optional, Tuple
from urllib.parse import quote_plus

import requests

from app.db.repo import SupabaseRepo
from app.utils.embeddings import create_embeddings

logger = logging.getLogger(__name__)

ARXIV_API_URL = "http://export.arxiv.org/api/query"
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}
MAX_CANDIDATES = 10
TOP_N = 3
USER_AGENT = "LearningAgent-Recommendations/1.0"


def _s2_text_to_search_query(s2_text: str, max_terms: int = 5) -> str:
    """Build arXiv search_query from S2 text. Simple: take first meaningful words, join with +."""
    if not (s2_text and s2_text.strip()):
        return "all:machine+learning"
    text = re.sub(r"\s+", " ", s2_text.strip()).strip()
    words = [w for w in text.split() if len(w) > 1 and w.isalnum()][:max_terms]
    if not words:
        return "all:machine+learning"
    return "all:" + "+".join(quote_plus(w) for w in words)


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


def run_arxiv_recommendations_for_week(
    user_id: str,
    week_start: str,
    s2_text: Optional[str] = None,
    repo: Optional[SupabaseRepo] = None,
) -> Tuple[int, Optional[str]]:
    """
    Generate Top 3 arXiv recommendations for the week from S2 text.
    - If s2_text is None, fetches S2 for user_id+week_start from DB and builds text from tldr+bullets.
    - Builds search query from s2_text, fetches candidates from arXiv.
    - Embeds S2 text and each candidate (title+abstract), re-ranks by cosine similarity.
    - Inserts Top 3 into recommendations.
    Returns (inserted_count, None) or (0, error_message).
    """
    repo = repo or SupabaseRepo()
    topic_name = "This Week"

    if s2_text is None:
        s2_row = repo.get_s2_for_user_week(user_id, week_start)
        if not s2_row:
            return 0, "no S2 for week"
        parts = []
        if s2_row.get("tldr"):
            parts.append(s2_row["tldr"])
        for b in (s2_row.get("bullets") or []):
            if b:
                parts.append(str(b).strip())
        s2_text = "\n".join(parts) if parts else ""
    if not s2_text.strip():
        return 0, "S2 has no text"

    search_query = _s2_text_to_search_query(s2_text)
    candidates = _fetch_arxiv_search(search_query)
    if len(candidates) < TOP_N:
        logger.info("arxiv_recommendations: got %d candidates, need at least %d", len(candidates), TOP_N)

    if not candidates:
        return 0, "no arXiv candidates"

    try:
        s2_embedding = create_embeddings([s2_text[:8000]])[0]
    except Exception as e:
        logger.warning("S2 embedding failed: %s", e)
        return 0, f"embedding failed: {e}"

    texts_to_embed = [f"{c['title']} {c['abstract']}"[:8000] for c in candidates]
    try:
        candidate_embeddings = create_embeddings(texts_to_embed)
    except Exception as e:
        logger.warning("Candidate embeddings failed: %s", e)
        return 0, f"embedding failed: {e}"

    scored = [
        (c, _cosine_similarity(s2_embedding, candidate_embeddings[i]))
        for i, c in enumerate(candidates)
        if i < len(candidate_embeddings)
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    top = [x[0] for x in scored[:TOP_N]]

    inserted = 0
    for c in top:
        try:
            repo.insert_recommendation(
                user_id=user_id,
                topic_name=topic_name,
                week_start=week_start,
                title=c["title"],
                abstract=c.get("abstract") or "",
                url=c["url"],
                source="arXiv",
                score=None,
            )
            inserted += 1
        except Exception as e:
            logger.warning("insert_recommendation failed: %s", e)
            return inserted, str(e)

    logger.info("arxiv_recommendations: user_id=%s week_start=%s inserted=%d", user_id, week_start, inserted)
    return inserted, None
