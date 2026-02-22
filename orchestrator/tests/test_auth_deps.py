"""
Tests for get_user_id dependency: bypass (dev only) and Bearer token verification.
Mocks verify_bearer_token to avoid real Firebase calls. Uses a minimal app (no DB) to test auth only.
"""
from typing import Annotated
from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.utils.deps import get_user_id

# Minimal app that only tests get_user_id (no DB/lifespan)
_auth_test_app = FastAPI()

@_auth_test_app.get("/whoami")
async def whoami(user_id: Annotated[str, Depends(get_user_id)]):
    return {"user_id": user_id}


@pytest.fixture
def client():
    return TestClient(_auth_test_app)


def test_get_user_id_bypass_when_local_and_header(client, monkeypatch):
    """With AUTH_BYPASS_USER_ID set and APP_ENV=local, Bearer dev-user returns user_id."""
    monkeypatch.setenv("AUTH_BYPASS_USER_ID", "dev-user")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("DEBUG", raising=False)
    response = client.get(
        "/whoami",
        headers={"Authorization": "Bearer dev-user"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == "dev-user"


def test_get_user_id_401_when_no_auth_and_no_bypass(client, monkeypatch):
    """With bypass disabled, missing header -> 401."""
    monkeypatch.delenv("AUTH_BYPASS_USER_ID", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DEBUG", raising=False)
    response = client.get("/whoami")
    assert response.status_code == 401
    assert "Authorization" in response.json().get("detail", "")


def test_get_user_id_401_with_invalid_bearer_mocked(client, monkeypatch):
    """With bypass off, invalid token -> 401; verify_bearer_token mocked."""
    monkeypatch.delenv("AUTH_BYPASS_USER_ID", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    with patch("app.utils.deps.verify_bearer_token", side_effect=ValueError("bad token")):
        response = client.get(
            "/whoami",
            headers={"Authorization": "Bearer invalid-token"},
        )
    assert response.status_code == 401


def test_get_user_id_200_with_valid_token_mocked(client, monkeypatch):
    """With bypass off and valid token (mocked), returns firebase uid."""
    monkeypatch.delenv("AUTH_BYPASS_USER_ID", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    with patch("app.utils.deps.verify_bearer_token", return_value={"uid": "firebase-uid-123"}):
        response = client.get(
            "/whoami",
            headers={"Authorization": "Bearer any-valid-token"},
        )
    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == "firebase-uid-123"
