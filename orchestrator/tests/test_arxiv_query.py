"""Unit tests for arXiv search query construction (OR + clauses)."""
import pytest

from app.services.arxiv_recommendations import (
    DEFAULT_ARXIV_BROAD_QUERY,
    _join_arxiv_or_clauses,
    _keywords_to_search_query,
    _s2_text_to_search_query,
)


def test_keywords_to_search_query_uses_or_between_terms():
    kws = [
        {"keyword": "memory systems", "weight": 0.9},
        {"keyword": "retrieval", "weight": 0.5},
    ]
    q = _keywords_to_search_query(kws)
    assert " OR " in q
    assert "memory systems" in q or "memory" in q
    assert "retrieval" in q.lower()


def test_single_keyword_no_parens():
    kws = [{"keyword": "transformer", "weight": 1.0}]
    q = _keywords_to_search_query(kws)
    assert "(" not in q or q.count("all:") >= 1
    assert "transformer" in q


def test_s2_text_to_search_query_or():
    q = _s2_text_to_search_query("We study multi agent systems and memory.")
    assert " OR " in q


def test_join_arxiv_or_clauses_empty_defaults():
    assert _join_arxiv_or_clauses([]) == DEFAULT_ARXIV_BROAD_QUERY
