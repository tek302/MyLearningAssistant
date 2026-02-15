"""Test RAG answer endpoint."""

import os
import pytest
import time
import re


def test_rag_answer_basic(client, db_connection, cleanup_after_test, test_user_id):
    """Test basic RAG answer functionality after ingesting a source."""
    # First, ingest a test URL to have data to query
    test_url = "https://en.wikipedia.org/wiki/FastAPI"
    cleanup_after_test.append(test_url)
    
    # Clean up any existing data
    with db_connection.cursor() as cur:
        cur.execute(
            "SELECT id FROM sources WHERE user_id IN (SELECT id FROM users WHERE firebase_uid = %s) AND url = %s",
            (test_user_id, test_url)
        )
        if cur.fetchone():
            # Clean up existing data
            cur.execute(
                """
                DELETE FROM embeddings WHERE chunk_id IN (
                    SELECT id FROM chunks WHERE source_id IN (
                        SELECT id FROM sources WHERE user_id IN (SELECT id FROM users WHERE firebase_uid = %s) AND url = %s
                    )
                )
                """,
                (test_user_id, test_url)
            )
            cur.execute(
                "DELETE FROM chunks WHERE source_id IN (SELECT id FROM sources WHERE user_id IN (SELECT id FROM users WHERE firebase_uid = %s) AND url = %s)",
                (test_user_id, test_url)
            )
            cur.execute(
                "DELETE FROM summaries WHERE source_id IN (SELECT id FROM sources WHERE user_id IN (SELECT id FROM users WHERE firebase_uid = %s) AND url = %s)",
                (test_user_id, test_url)
            )
            cur.execute(
                "DELETE FROM sources WHERE user_id IN (SELECT id FROM users WHERE firebase_uid = %s) AND url = %s",
                (test_user_id, test_url)
            )
            db_connection.commit()
    
    # Ingest the URL (user_id is handled by dependency injection via AUTH_BYPASS_USER_ID)
    ingest_response = client.post(
        "/ingest/url",
        json={"url": test_url}
    )
    assert ingest_response.status_code == 200, \
        f"Ingest failed: {ingest_response.status_code}: {ingest_response.text}"
    
    ingest_data = ingest_response.json()
    assert ingest_data["chunk_count"] > 0, "Expected chunks to be created"
    
    # Wait a bit for embeddings to be ready (if async)
    time.sleep(1)
    
    # Now test RAG answer (user_id is handled by dependency injection via AUTH_BYPASS_USER_ID)
    rag_response = client.post(
        "/rag/answer",
        json={
            "query": "What is FastAPI?",
            "top_k": 5
        }
    )
    
    assert rag_response.status_code == 200, \
        f"RAG answer failed: {rag_response.status_code}: {rag_response.text}"
    
    data = rag_response.json()
    
    # Assert response structure
    assert "answer" in data, f"Response missing 'answer': {data}"
    assert "citations" in data, f"Response missing 'citations': {data}"
    assert "meta" in data, f"Response missing 'meta': {data}"
    
    # Assert answer is non-empty
    assert len(data["answer"]) > 0, "Answer should not be empty"
    
    # Assert citations
    assert isinstance(data["citations"], list), "Citations should be a list"
    
    # Policy: Citations should be empty if fallback was used or answer is cannot-answer
    fallback_used = data["meta"].get("fallback_used", False)
    is_cannot_answer = "I cannot answer this question based on the provided context." in data["answer"]
    
    if fallback_used or is_cannot_answer:
        # Policy: citations must be [] when fallback/cannot-answer
        assert len(data["citations"]) == 0, \
            f"Citations should be empty when fallback_used={fallback_used} or cannot_answer={is_cannot_answer}. " \
            f"Got {len(data['citations'])} citations. Answer: {data['answer'][:200]}"
    else:
        # Normal success case: should have citations
        assert len(data["citations"]) > 0, \
            f"Should have at least one citation when not fallback. Answer: {data['answer'][:200]}, Meta: {data['meta']}"
    assert len(data["citations"]) <= 5, f"Should have <= top_k citations, got {len(data['citations'])}"
    
    # Assert citation structure
    for idx, cit in enumerate(data["citations"], start=1):
        assert "citation_number" in cit, "Citation missing 'citation_number'"
        assert cit["citation_number"] == idx, f"Citation number should be {idx}, got {cit['citation_number']}"
        assert "chunk_id" in cit, "Citation missing 'chunk_id'"
        assert "source_id" in cit, "Citation missing 'source_id'"
        assert "score" in cit, "Citation missing 'score'"
        assert "quote" in cit, "Citation missing 'quote'"
        assert isinstance(cit["score"], (int, float)), "Score should be numeric"
        assert len(cit["quote"]) > 0, "Quote should not be empty"
        assert len(cit["quote"]) <= 240, f"Quote should be <= 240 chars, got {len(cit['quote'])}"
    
    # Assert citations are sorted by relevance (non-increasing scores)
    if len(data["citations"]) > 1:
        scores = [cit["score"] for cit in data["citations"]]
        assert scores[0] >= scores[-1], \
            f"Citations should be sorted by relevance (non-increasing), first={scores[0]}, last={scores[-1]}"
    
    # Assert citation marker reliability: if citations exist, answer should contain at least one marker
    if len(data["citations"]) > 0:
        has_markers = bool(re.search(r'\[\d+\]', data["answer"]))
        assert has_markers, \
            f"Answer should contain citation markers like [1], [2], etc. when citations exist. Answer: {data['answer'][:200]}"
    
    # Assert meta
    assert "top_k" in data["meta"], "Meta missing 'top_k'"
    assert "latency_ms" in data["meta"], "Meta missing 'latency_ms'"
    assert "model" in data["meta"], "Meta missing 'model'"
    assert data["meta"]["top_k"] == 5, f"Expected top_k=5, got {data['meta']['top_k']}"


def test_rag_answer_latency(client, db_connection, cleanup_after_test, test_user_id):
    """Test RAG answer latency (sanity check, skip in CI)."""
    # Skip if CI environment variable is set
    if os.getenv("CI"):
        pytest.skip("Skipping latency test in CI environment")
    
    # First, ingest a test URL
    test_url = "https://en.wikipedia.org/wiki/FastAPI"
    cleanup_after_test.append(test_url)
    
    # Clean up any existing data
    with db_connection.cursor() as cur:
        cur.execute(
            "SELECT id FROM sources WHERE user_id IN (SELECT id FROM users WHERE firebase_uid = %s) AND url = %s",
            (test_user_id, test_url)
        )
        if cur.fetchone():
            cur.execute(
                """
                DELETE FROM embeddings WHERE chunk_id IN (
                    SELECT id FROM chunks WHERE source_id IN (
                        SELECT id FROM sources WHERE user_id IN (SELECT id FROM users WHERE firebase_uid = %s) AND url = %s
                    )
                )
                """,
                (test_user_id, test_url)
            )
            cur.execute(
                "DELETE FROM chunks WHERE source_id IN (SELECT id FROM sources WHERE user_id IN (SELECT id FROM users WHERE firebase_uid = %s) AND url = %s)",
                (test_user_id, test_url)
            )
            cur.execute(
                "DELETE FROM summaries WHERE source_id IN (SELECT id FROM sources WHERE user_id IN (SELECT id FROM users WHERE firebase_uid = %s) AND url = %s)",
                (test_user_id, test_url)
            )
            cur.execute(
                "DELETE FROM sources WHERE user_id IN (SELECT id FROM users WHERE firebase_uid = %s) AND url = %s",
                (test_user_id, test_url)
            )
            db_connection.commit()
    
    # Ingest the URL (user_id is handled by dependency injection via AUTH_BYPASS_USER_ID)
    ingest_response = client.post(
        "/ingest/url",
        json={"url": test_url}
    )
    assert ingest_response.status_code == 200
    
    # Wait a bit
    time.sleep(1)
    
    # Test RAG answer and measure latency (user_id is handled by dependency injection via AUTH_BYPASS_USER_ID)
    start_time = time.time()
    rag_response = client.post(
        "/rag/answer",
        json={
            "query": "What is FastAPI?",
            "top_k": 3
        }
    )
    elapsed_ms = (time.time() - start_time) * 1000
    
    assert rag_response.status_code == 200
    
    data = rag_response.json()
    
    # Assert latency is reasonable (less than 8000ms locally)
    assert elapsed_ms < 8000, \
        f"RAG answer took {elapsed_ms:.0f}ms, expected < 8000ms"
    
    # Also check reported latency in meta
    assert data["meta"]["latency_ms"] < 8000, \
        f"Reported latency {data['meta']['latency_ms']}ms, expected < 8000ms"


def test_rag_answer_no_results(client, db_connection, test_user_id, monkeypatch):
    """Test RAG answer when no chunks are found using a dedicated user with no data."""
    # Use a dedicated user_id that has no ingested data
    no_data_user_id = f"{test_user_id}_no_data"
    
    # Temporarily set AUTH_BYPASS_USER_ID to use a user with no data
    original_bypass = os.environ.get("AUTH_BYPASS_USER_ID")
    monkeypatch.setenv("AUTH_BYPASS_USER_ID", no_data_user_id)
    
    try:
        # Verify this user has no chunks in the database
        with db_connection.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM chunks c
                JOIN sources s ON c.source_id = s.id
                JOIN users u ON s.user_id = u.id
                WHERE u.firebase_uid = %s
                """,
                (no_data_user_id,)
            )
            chunk_count = cur.fetchone()[0]
            # If chunks exist, clean them up to ensure deterministic test
            if chunk_count > 0:
                cur.execute(
                    """
                    DELETE FROM embeddings WHERE chunk_id IN (
                        SELECT c.id FROM chunks c
                        JOIN sources s ON c.source_id = s.id
                        JOIN users u ON s.user_id = u.id
                        WHERE u.firebase_uid = %s
                    )
                    """,
                    (no_data_user_id,)
                )
                cur.execute(
                    """
                    DELETE FROM chunks WHERE source_id IN (
                        SELECT s.id FROM sources s
                        JOIN users u ON s.user_id = u.id
                        WHERE u.firebase_uid = %s
                    )
                    """,
                    (no_data_user_id,)
                )
                cur.execute(
                    """
                    DELETE FROM summaries WHERE source_id IN (
                        SELECT s.id FROM sources s
                        JOIN users u ON s.user_id = u.id
                        WHERE u.firebase_uid = %s
                    )
                    """,
                    (no_data_user_id,)
                )
                cur.execute(
                    """
                    DELETE FROM sources WHERE user_id IN (
                        SELECT id FROM users WHERE firebase_uid = %s
                    )
                    """,
                    (no_data_user_id,)
                )
                db_connection.commit()
        
        # Query with a user that has no data
        rag_response = client.post(
            "/rag/answer",
            json={
                "query": "test query for user with no data",
                "top_k": 5
            }
        )
        
        assert rag_response.status_code == 200, \
            f"RAG answer should return 200 even with no results: {rag_response.status_code}: {rag_response.text}"
        
        data = rag_response.json()
        
        # Should have a message indicating no results
        assert "answer" in data
        assert len(data["answer"]) > 0  # Should have a message
        assert len(data["citations"]) == 0, "Should have no citations when no chunks found"
        
        # Verify that the answer indicates no results were found
        assert "couldn't find" in data["answer"].lower() or "no relevant" in data["answer"].lower(), \
            f"Answer should indicate no results found: {data['answer']}"
    finally:
        # Restore original AUTH_BYPASS_USER_ID
        if original_bypass is not None:
            monkeypatch.setenv("AUTH_BYPASS_USER_ID", original_bypass)
        else:
            monkeypatch.delenv("AUTH_BYPASS_USER_ID", raising=False)


def test_rag_answer_validation(client):
    """Test RAG answer request validation."""
    # Test empty query
    response = client.post(
        "/rag/answer",
        json={"query": ""}
    )
    assert response.status_code == 422, "Should return 422 for empty query"
    
    # Test missing query
    response = client.post(
        "/rag/answer",
        json={}
    )
    assert response.status_code == 422, "Should return 422 for missing query"
    
    # Note: user_id is provided via dependency injection (get_user_id),
    # so we can't test missing user_id in the request body.
    # However, if user_id validation fails in the dependency, it would return 400 or 401.
    # Since we're using AUTH_BYPASS_USER_ID in tests, user_id is always available.
    
    # Test invalid top_k
    response = client.post(
        "/rag/answer",
        json={"query": "test", "top_k": 0}
    )
    assert response.status_code == 422, "Should return 422 for top_k < 1"
    
    response = client.post(
        "/rag/answer",
        json={"query": "test", "top_k": 100}
    )
    assert response.status_code == 422, "Should return 422 for top_k > 20"
    
    # Test valid top_k range
    response = client.post(
        "/rag/answer",
        json={"query": "test", "top_k": 20}
    )
    # Should not return 422 for valid top_k=20
    assert response.status_code != 422, "Should accept top_k=20"

