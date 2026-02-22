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
_firebase_skipped = False  # True when bypass allowed and no creds (no init)


def _bypass_allowed() -> bool:
    """Same logic as deps: bypass when AUTH_BYPASS_USER_ID set and APP_ENV=local or DEBUG=true."""
    if not os.getenv("AUTH_BYPASS_USER_ID"):
        return False
    app_env = (os.getenv("APP_ENV") or "").strip().lower()
    debug = (os.getenv("DEBUG") or "").strip().lower() in ("true", "1", "yes")
    return app_env == "local" or debug


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
    When auth bypass is allowed (AUTH_BYPASS_USER_ID + local/DEBUG) and no credentials
    are set, skips init so the app can start without Firebase (local testing only).
    """
    global _firebase_initialized, _firebase_skipped
    if _firebase_initialized:
        return
    try:
        firebase_admin.get_app()
        _firebase_initialized = True
        return
    except ValueError:
        pass
    try:
        cred = _get_credentials()
    except ValueError:
        if _bypass_allowed():
            _firebase_initialized = True
            _firebase_skipped = True
            return
        raise
    firebase_admin.initialize_app(cred)
    _firebase_initialized = True


def verify_bearer_token(token: str) -> dict[str, Any]:
    """
    Verify a Firebase ID token (Bearer token) and return decoded claims.
    Call init_firebase() internally if needed.
    Returns dict with at least 'uid' (firebase_uid). Do not log the token.
    """
    init_firebase()
    if _firebase_skipped:
        raise ValueError(
            "Firebase not configured (auth bypass mode). Use Authorization: Bearer <AUTH_BYPASS_USER_ID> for local testing."
        )
    try:
        decoded = auth.verify_id_token(token)
        return decoded
    except Exception as e:
        raise ValueError(f"Invalid or expired token: {e}") from e


def verify_id_token(id_token: str) -> dict[str, Any]:
    """Alias for verify_bearer_token (backward compatibility)."""
    return verify_bearer_token(id_token)
