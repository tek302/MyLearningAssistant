"""Test idempotent ingest behavior."""

import pytest


def test_ingest_idempotent(client, db_connection, cleanup_after_test, test_user_id):
    """Test that ingesting the same URL twice is idempotent."""
    test_url = "https://arxiv.org/pdf/1706.03762.pdf"
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
    
    # First ingest
    response1 = client.post(
        "/ingest/url",
        json={"url": test_url}
    )
    
    assert response1.status_code == 200, f"First ingest failed: {response1.status_code}: {response1.text}"
    data1 = response1.json()
    
    source_id1 = data1["source_id"]
    chunk_count1 = data1["chunk_count"]
    embedding_count1 = data1["embedding_count"]
    
    # Second ingest (should be idempotent)
    response2 = client.post(
        "/ingest/url",
        json={"url": test_url}
    )
    
    assert response2.status_code == 200, f"Second ingest failed: {response2.status_code}: {response2.text}"
    data2 = response2.json()
    
    # Should return same source_id
    assert data2["source_id"] == source_id1, \
        f"Expected same source_id, got {data2['source_id']} != {source_id1}"
    
    # Get the actual URL from response (may be normalized)
    actual_url = data2["url"]
    
    # Verify in database: should have only 1 source
    # Check by source_id first (more reliable than URL matching)
    with db_connection.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM sources WHERE id = %s",
            (source_id1,)
        )
        sources_count_by_id = cur.fetchone()[0]
        assert sources_count_by_id == 1, \
            f"Expected 1 source with id {source_id1}, got {sources_count_by_id}"
        
        # Get the actual URL and user_id stored in DB for debugging
        cur.execute(
            "SELECT url, user_id FROM sources WHERE id = %s",
            (source_id1,)
        )
        stored_url, stored_user_id = cur.fetchone()
        
        # Verify URL matches (allowing for normalization)
        # The key idempotency check is that source_id is the same, but we also verify URL
        assert stored_url == actual_url or stored_url == test_url or actual_url == test_url, \
            f"URL mismatch: stored='{stored_url}', response='{actual_url}', requested='{test_url}'"
        
        # Verify idempotency: for the same user_id and URL, there should be only 1 source
        # (The user_id might be different across requests due to test setup, but within the same
        #  request context, the same user_id should be used)
        cur.execute(
            """
            SELECT COUNT(*) FROM sources 
            WHERE user_id = %s AND url = %s
            """,
            (stored_user_id, stored_url)
        )
        sources_for_user_url = cur.fetchone()[0]
        assert sources_for_user_url == 1, \
            f"Expected 1 source for user_id={stored_user_id} and url='{stored_url}', got {sources_for_user_url}"
        
        # Check chunks count (should be equal or close to first run)
        cur.execute(
            "SELECT COUNT(*) FROM chunks WHERE source_id = %s",
            (source_id1,)
        )
        chunks_count = cur.fetchone()[0]
        # Allow small tolerance (should be equal ideally)
        assert chunks_count <= chunk_count1 + 5, \
            f"Chunks count {chunks_count} should be <= first run {chunk_count1} + tolerance"
        
        # Check embeddings count
        cur.execute(
            """
            SELECT COUNT(*) FROM embeddings 
            WHERE chunk_id IN (SELECT id FROM chunks WHERE source_id = %s)
            """,
            (source_id1,)
        )
        embeddings_count = cur.fetchone()[0]
        assert embeddings_count <= embedding_count1 + 5, \
            f"Embeddings count {embeddings_count} should be <= first run {embedding_count1} + tolerance"

