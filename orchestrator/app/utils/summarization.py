import os
import time
import json
from typing import Dict, Any, List
from dotenv import load_dotenv

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# Load environment variables
load_dotenv()


def get_summary_model() -> str:
    """Get summary model from environment variable, defaulting to gpt-4o-mini."""
    return os.getenv("SUMMARY_MODEL", "gpt-4o-mini")


def get_s1_max_chunks() -> int:
    """Get maximum chunks for S1 summarization, defaulting to 8."""
    try:
        return int(os.getenv("S1_MAX_CHUNKS", "8"))
    except ValueError:
        return 8


def create_s1_summary(chunks_text: str, max_retries: int = 2) -> Dict[str, Any]:
    """
    Create S1 summary using OpenAI chat model.
    
    Args:
        chunks_text: Concatenated text from top N chunks
        max_retries: Maximum number of retry attempts (default: 2)
        
    Returns:
        Dictionary with keys: tldr, bullets, tags (optional)
        
    Raises:
        ValueError: If OpenAI is not installed or API key is missing
        RuntimeError: If summary creation fails after retries
    """
    if not HAS_OPENAI:
        raise ValueError("OpenAI package is not installed. Install with: pip install openai")
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    
    model = get_summary_model()
    client = OpenAI(api_key=api_key)
    
    # Build prompt
    prompt = f"""Summarize the following text content. Provide:
1. A concise TLDR (max 200 characters)
2. 3-7 key bullet points
3. Optional tags (max 6, comma-separated keywords)

Text content:
{chunks_text}

Respond in JSON format:
{{
  "tldr": "brief summary here",
  "bullets": ["point 1", "point 2", ...],
  "tags": ["tag1", "tag2", ...]
}}"""
    
    # Retry logic
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that creates concise summaries in JSON format."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )
            
            # Parse JSON response
            content = response.choices[0].message.content
            result = json.loads(content)
            
            # Validate and clean result
            tldr = result.get("tldr", "").strip()
            if len(tldr) > 200:
                tldr = tldr[:200].strip()
            
            bullets = result.get("bullets", [])
            if not isinstance(bullets, list):
                bullets = []
            # Ensure 3-7 bullets
            bullets = [str(b).strip() for b in bullets if b][:7]
            if len(bullets) < 3:
                # If too few, pad with empty strings (will be filtered)
                bullets = bullets + [""] * (3 - len(bullets))
            bullets = [b for b in bullets if b][:7]
            
            tags = result.get("tags", [])
            if not isinstance(tags, list):
                tags = []
            tags = [str(t).strip() for t in tags if t][:6]
            
            return {
                "tldr": tldr,
                "bullets": bullets,
                "tags": tags if tags else None
            }
            
        except json.JSONDecodeError as e:
            last_error = e
            if attempt < max_retries:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
            else:
                raise RuntimeError(f"Failed to parse JSON response after {max_retries + 1} attempts: {str(last_error)}")
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
            else:
                raise RuntimeError(f"Failed to create summary after {max_retries + 1} attempts: {str(last_error)}")
    
    # Should not reach here
    raise RuntimeError(f"Failed to create summary: {str(last_error)}")

