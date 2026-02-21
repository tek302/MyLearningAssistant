"""
FastAPI dependency: get_user_id from Authorization Bearer (Firebase ID token).
Bypass allowed only when AUTH_BYPASS_USER_ID is set and env is local/dev.
"""
import os
from typing import Annotated

from fastapi import Header, HTTPException, status

from .firebase_auth import verify_bearer_token


def _is_bypass_allowed() -> bool:
    """Bypass only in local/dev: AUTH_BYPASS_USER_ID set and (APP_ENV=local or DEBUG=true)."""
    if not os.getenv("AUTH_BYPASS_USER_ID"):
        return False
    app_env = (os.getenv("APP_ENV") or "").strip().lower()
    debug = (os.getenv("DEBUG") or "").strip().lower() in ("true", "1", "yes")
    return app_env == "local" or debug


async def get_user_id(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """
    Resolve user from Authorization: Bearer <Firebase ID Token>.
    Returns firebase_uid (uid from token); DB layer maps to users.id via resolve_user_id.
    Bypass: only when AUTH_BYPASS_USER_ID is set and APP_ENV=local or DEBUG=true.
    """
    if _is_bypass_allowed():
        bypass = (os.getenv("AUTH_BYPASS_USER_ID") or "").strip()
        if bypass:
            return bypass

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is missing",
        )
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization format. Expected: Bearer <token>",
        )
    token = parts[1]
    try:
        decoded = verify_bearer_token(token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from e
    uid = decoded.get("uid")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain uid",
        )
    return str(uid)
