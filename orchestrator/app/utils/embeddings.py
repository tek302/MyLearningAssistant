import os
import time
from typing import List
from dotenv import load_dotenv

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# Load environment variables
load_dotenv()


def get_embedding_model() -> str:
    """Get embedding model from environment variable, defaulting to text-embedding-3-small."""
    return os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")


def create_embeddings(texts: List[str], max_retries: int = 2) -> List[List[float]]:
    """
    Create embeddings for a list of texts using OpenAI API.
    
    Args:
        texts: List of text strings to embed
        max_retries: Maximum number of retry attempts (default: 2)
        
    Returns:
        List of embedding vectors (1536 dimensions for text-embedding-3-small)
        
    Raises:
        ValueError: If OpenAI is not installed or API key is missing
        RuntimeError: If embedding creation fails after retries
    """
    if not HAS_OPENAI:
        raise ValueError("OpenAI package is not installed. Install with: pip install openai")
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    
    model = get_embedding_model()
    client = OpenAI(api_key=api_key)
    
    # Retry logic
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = client.embeddings.create(
                model=model,
                input=texts
            )
            
            # Extract embeddings from response
            embeddings = [item.embedding for item in response.data]
            return embeddings
            
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                # Exponential backoff: wait 1s, 2s, 4s...
                wait_time = 2 ** attempt
                time.sleep(wait_time)
            else:
                raise RuntimeError(f"Failed to create embeddings after {max_retries + 1} attempts: {str(last_error)}")
    
    # Should not reach here, but just in case
    raise RuntimeError(f"Failed to create embeddings: {str(last_error)}")

