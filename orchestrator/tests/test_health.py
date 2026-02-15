"""Test health check endpoint."""


def test_health(client):
    """Test the /health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    data = response.json()
    assert "status" in data, f"Response missing 'status' field: {data}"
    assert data["status"] == "healthy", f"Expected 'healthy', got '{data['status']}'"
