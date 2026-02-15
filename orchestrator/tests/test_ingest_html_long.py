"""Test HTML URL ingest endpoint with long content."""

import pytest


def test_ingest_html_long(client, db_connection, cleanup_after_test, test_user_id):
    """Test ingesting a long HTML page (Wikipedia)."""
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
    
    # Call ingest endpoint
    response = client.post(
        "/ingest/url",
        json={"url": test_url}
    )
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    data = response.json()
    
    # Assert response structure
    assert "source_id" in data, f"Response missing 'source_id': {data}"
    assert "chunk_count" in data, f"Response missing 'chunk_count': {data}"
    assert "embedding_count" in data, f"Response missing 'embedding_count': {data}"
    assert "content_type" in data, f"Response missing 'content_type': {data}"
    
    # Assert values
    assert data["chunk_count"] > 0, f"Expected chunk_count > 0, got {data['chunk_count']}"
    assert data["embedding_count"] > 0, f"Expected embedding_count > 0, got {data['embedding_count']}"
    assert data["content_type"] == "html", f"Expected content_type='html', got '{data['content_type']}'"
    
    source_id = data["source_id"]
    
    # Verify in database
    with db_connection.cursor() as cur:
        # Check chunks count
        cur.execute(
            "SELECT COUNT(*) FROM chunks WHERE source_id = %s",
            (source_id,)
        )
        chunks_count = cur.fetchone()[0]
        assert chunks_count == data["chunk_count"], \
            f"DB chunks count {chunks_count} != response chunk_count {data['chunk_count']}"
        
        # Check embeddings count
        cur.execute(
            """
            SELECT COUNT(*) FROM embeddings 
            WHERE chunk_id IN (SELECT id FROM chunks WHERE source_id = %s)
            """,
            (source_id,)
        )
        embeddings_count = cur.fetchone()[0]
        assert embeddings_count == data["embedding_count"], \
            f"DB embeddings count {embeddings_count} != response embedding_count {data['embedding_count']}"

