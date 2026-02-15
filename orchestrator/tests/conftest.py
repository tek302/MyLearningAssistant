import os
import pytest
from fastapi.testclient import TestClient
from dotenv import load_dotenv
import psycopg
from app.main import app

# Load environment variables
load_dotenv()

# Set auth bypass for tests
os.environ["AUTH_BYPASS_USER_ID"] = "dev-user"


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    return TestClient(app)


@pytest.fixture
def db_connection():
    """Database connection fixture using SUPABASE_DB_URL."""
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        pytest.skip("SUPABASE_DB_URL not set, skipping integration tests")
    
    conn = psycopg.connect(db_url)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def test_user_id():
    """Test user ID for cleanup."""
    return "dev-user"


def cleanup_test_data(conn, user_id: str, url: str):
    """
    Clean up test data for a given user_id and url.
    Deletes in order: embeddings -> chunks -> summaries -> sources
    """
    with conn.cursor() as cur:
        # Get source_id for this user and url
        cur.execute(
            "SELECT id FROM sources WHERE user_id IN (SELECT id FROM users WHERE firebase_uid = %s) AND url = %s",
            (user_id, url)
        )
        source_result = cur.fetchone()
        
        if not source_result:
            conn.commit()
            return
        
        source_id = source_result[0]
        
        # Delete embeddings (via chunks)
        cur.execute(
            """
            DELETE FROM embeddings 
            WHERE chunk_id IN (SELECT id FROM chunks WHERE source_id = %s)
            """,
            (source_id,)
        )
        
        # Delete chunks
        cur.execute(
            "DELETE FROM chunks WHERE source_id = %s",
            (source_id,)
        )
        
        # Delete summaries
        cur.execute(
            "DELETE FROM summaries WHERE source_id = %s",
            (source_id,)
        )
        
        # Delete source
        cur.execute(
            "DELETE FROM sources WHERE id = %s",
            (source_id,)
        )
        
        conn.commit()


@pytest.fixture
def cleanup_after_test(db_connection, test_user_id):
    """Fixture to clean up test data after each test."""
    urls_to_cleanup = []
    
    yield urls_to_cleanup
    
    # Cleanup after test
    for url in urls_to_cleanup:
        cleanup_test_data(db_connection, test_user_id, url)

