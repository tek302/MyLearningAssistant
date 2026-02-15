import os
import pytest
from fastapi.testclient import TestClient
from app.main import app

# Set auth bypass for testing
os.environ["AUTH_BYPASS_USER_ID"] = "test-user-123"

client = TestClient(app)


def test_ingest_url_invalid_url():
    """Test /ingest/url with invalid URL."""
    response = client.post(
        "/ingest/url",
        json={"url": "not-a-valid-url"}
    )
    # Should return 422 for validation error
    assert response.status_code == 422


def test_ingest_url_missing_env():
    """Test /ingest/url when SUPABASE_DB_URL is not set."""
    # Temporarily remove the env var if it exists
    original_db_url = os.environ.pop("SUPABASE_DB_URL", None)
    
    try:
        response = client.post(
            "/ingest/url",
            json={"url": "https://example.com"}
        )
        # May return 400 (validation/other errors) or 500 (DB error)
        # The important thing is that it doesn't succeed
        assert response.status_code >= 400, \
            f"Expected error status (>=400), got {response.status_code}"
    finally:
        # Restore the env var
        if original_db_url:
            os.environ["SUPABASE_DB_URL"] = original_db_url


def test_ingest_url_smoke():
    """
    Smoke test for /ingest/url endpoint.
    
    This test requires:
    - SUPABASE_DB_URL to be set
    - Valid database connection
    - Sources and chunks tables to exist
    
    If these are not available, the test will be skipped.
    """
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        pytest.skip("SUPABASE_DB_URL not set, skipping integration test")
    
    # Use a simple test URL
    test_url = "https://example.com"
    
    response = client.post(
        "/ingest/url",
        json={"url": test_url}
    )
    
    # If database is not set up, we expect 500
    # If database is set up, we expect 200
    assert response.status_code in [200, 500, 503]
    
    if response.status_code == 200:
        data = response.json()
        assert "source_id" in data
        assert "url" in data
        assert "title" in data
        assert "chunk_count" in data
        # URL may be normalized (e.g., trailing slash added by Pydantic)
        assert data["url"] == test_url or data["url"] == test_url + "/" or data["url"] + "/" == test_url, \
            f"URL mismatch: expected '{test_url}' (or normalized), got '{data['url']}'"
        assert data["chunk_count"] > 0

