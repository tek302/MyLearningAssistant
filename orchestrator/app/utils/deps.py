import os
from typing import Annotated
from fastapi import Header, HTTPException, status
from .firebase_auth import verify_id_token


async def get_user_id(
    authorization: Annotated[str | None, Header()] = None
) -> str:
    """
    FastAPI dependency to extract and verify user ID from Authorization bearer token.
    
    For testing, set AUTH_BYPASS_USER_ID environment variable to bypass Firebase auth.
    
    Args:
        authorization: Authorization header value (Bearer token)
        
    Returns:
        user_id: User ID from decoded token (uid field) or AUTH_BYPASS_USER_ID
        
    Raises:
        HTTPException: If authorization header is missing or invalid
    """
    # Check for auth bypass (for testing only)
    bypass_user_id = os.getenv("AUTH_BYPASS_USER_ID")
    if bypass_user_id:
        return bypass_user_id
    
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is missing"
        )
    
    # Extract bearer token
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected: Bearer <token>"
        )
    
    id_token = parts[1]
    
    try:
        # Verify token and get decoded claims
        decoded = verify_id_token(id_token)
        
        # Extract user ID from uid field
        user_id = decoded.get("uid")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token does not contain uid"
            )
        
        return user_id
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )

