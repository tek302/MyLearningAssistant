"""
Firebase Admin SDK: singleton init and ID token verification.
Credentials via GOOGLE_APPLICATION_CREDENTIALS (file path) or
FIREBASE_SERVICE_ACCOUNT_JSON (file path or JSON string).
"""
import json
import os
from typing import Any

import firebase_admin
from firebase_admin import auth, credentials

_firebase_initialized = False


def _get_credentials():
    """Build credentials from env: GOOGLE_APPLICATION_CREDENTIALS first, then FIREBASE_SERVICE_ACCOUNT_JSON."""
    # (a) GOOGLE_APPLICATION_CREDENTIALS file path (recommended for Cloud Run)
    path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if path and os.path.isfile(path):
        return credentials.Certificate(path)

    # (b) FIREBASE_SERVICE_ACCOUNT_JSON: file path or JSON string
    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not raw or not raw.strip():
        raise ValueError(
            "Firebase credentials required: set GOOGLE_APPLICATION_CREDENTIALS (file path) "
            "or FIREBASE_SERVICE_ACCOUNT_JSON (file path or JSON string)"
        )
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            return credentials.Certificate(json.loads(raw))
        except json.JSONDecodeError as e:
            raise ValueError(f"FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON: {e}") from e
    if os.path.isfile(raw):
        return credentials.Certificate(raw)
    raise ValueError(
        "FIREBASE_SERVICE_ACCOUNT_JSON must be a path to an existing file or a JSON string"
    )


def init_firebase() -> None:
    """
    Initialize Firebase Admin SDK (singleton). Safe to call multiple times.
    Uses GOOGLE_APPLICATION_CREDENTIALS or FIREBASE_SERVICE_ACCOUNT_JSON.
    """
    global _firebase_initialized
    if _firebase_initialized:
        return
    try:
        firebase_admin.get_app()
        _firebase_initialized = True
        return
    except ValueError:
        pass
    cred = _get_credentials()
    firebase_admin.initialize_app(cred)
    _firebase_initialized = True


def verify_bearer_token(token: str) -> dict[str, Any]:
    """
    Verify a Firebase ID token (Bearer token) and return decoded claims.
    Call init_firebase() internally if needed.
    Returns dict with at least 'uid' (firebase_uid). Do not log the token.
    """
    init_firebase()
    try:
        decoded = auth.verify_id_token(token)
        return decoded
    except Exception as e:
        raise ValueError(f"Invalid or expired token: {e}") from e


def verify_id_token(id_token: str) -> dict[str, Any]:
    """Alias for verify_bearer_token (backward compatibility)."""
    return verify_bearer_token(id_token)
