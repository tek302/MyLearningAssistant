import os
from typing import Dict, Any, Optional
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, auth

# Load environment variables
load_dotenv()

# Global flag to track initialization
_firebase_initialized = False


def init_firebase() -> None:
    """
    Initialize Firebase Admin SDK with lazy initialization.
    Safe to call multiple times - will only initialize once.
    """
    global _firebase_initialized
    
    # Check if already initialized
    if _firebase_initialized:
        return
    
    try:
        # Check if Firebase app already exists
        firebase_admin.get_app()
        _firebase_initialized = True
        return
    except ValueError:
        # App doesn't exist, proceed with initialization
        pass
    
    # Get service account JSON path from environment
    service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not service_account_path:
        raise ValueError("FIREBASE_SERVICE_ACCOUNT_JSON environment variable is not set")
    
    # Check if file exists
    if not os.path.exists(service_account_path):
        raise FileNotFoundError(f"Firebase service account file not found: {service_account_path}")
    
    # Initialize Firebase Admin SDK
    cred = credentials.Certificate(service_account_path)
    firebase_admin.initialize_app(cred)
    _firebase_initialized = True


def verify_id_token(id_token: str) -> Dict[str, Any]:
    """
    Verify a Firebase ID token and return decoded claims.
    
    Args:
        id_token: Firebase ID token string
        
    Returns:
        Dictionary containing decoded token claims
        
    Raises:
        ValueError: If token is invalid or expired
    """
    # Ensure Firebase is initialized
    init_firebase()
    
    # Verify and decode the token
    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except Exception as e:
        raise ValueError(f"Invalid or expired token: {str(e)}")

