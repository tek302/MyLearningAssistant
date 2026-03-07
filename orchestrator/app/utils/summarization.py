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


# Feed-friendly: one sentence + 3 key points (configurable)
S1_TLDR_MAX_CHARS = 150  # One sentence; keep short for Feed card
S1_BULLETS_COUNT = 3     # Number of key points to show in Feed


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
    
    # Build prompt: one sentence + 3 key points for Feed (keep cards short)
    tldr_max = int(os.getenv("S1_TLDR_MAX_CHARS", str(S1_TLDR_MAX_CHARS)))
    bullets_count = int(os.getenv("S1_BULLETS_COUNT", str(S1_BULLETS_COUNT)))
    bullets_count = max(1, min(7, bullets_count))
    prompt = f"""Summarize the following text in JSON.

1. tldr: ONE short sentence only (max {tldr_max} characters). No multiple sentences.
2. bullets: Exactly {bullets_count} key points. Each point one short phrase or sentence.
3. tags: Optional, max 6 comma-separated keywords.

Text content:
{chunks_text}

Respond in JSON only:
{{
  "tldr": "one sentence summary here",
  "bullets": ["key point 1", "key point 2", "key point 3"],
  "tags": ["tag1", "tag2"]
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
            
            # Validate and clean: one-sentence tldr, fixed number of bullets (Feed-friendly)
            tldr_max = int(os.getenv("S1_TLDR_MAX_CHARS", str(S1_TLDR_MAX_CHARS)))
            bullets_count = int(os.getenv("S1_BULLETS_COUNT", str(S1_BULLETS_COUNT)))
            bullets_count = max(1, min(7, bullets_count))
            tldr = result.get("tldr", "").strip()
            if len(tldr) > tldr_max:
                tldr = tldr[:tldr_max].strip()
            bullets = result.get("bullets", [])
            if not isinstance(bullets, list):
                bullets = []
            bullets = [str(b).strip() for b in bullets if b][:bullets_count]
            if len(bullets) < bullets_count:
                bullets = bullets + [""] * (bullets_count - len(bullets))
            bullets = [b for b in bullets if b][:bullets_count]
            
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


def create_s2_summary(combined_s1_text: str, max_retries: int = 2) -> Dict[str, Any]:
    """
    Create S2 (weekly/topic) summary from combined S1 tldr + bullets text.
    One LLM call to produce a single tldr + 5--15 technical points for "this week".
    """
    if not HAS_OPENAI:
        raise ValueError("OpenAI package is not installed. Install with: pip install openai")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    model = get_summary_model()
    client = OpenAI(api_key=api_key)
    prompt = f"""You are summarizing the key technical points from multiple documents read this week.
Below is a concatenation of one-sentence summaries and bullet points from each document.

Produce a single weekly summary in JSON:
1. tldr: ONE short sentence (max 200 chars) capturing the main theme of the week's reading.
2. bullets: Between 5 and 15 technical points that are the most important across all documents. Each point one short phrase or sentence.

Combined document summaries:
{combined_s1_text[:12000]}

Respond in JSON only:
{{
  "tldr": "one sentence weekly summary",
  "bullets": ["point 1", "point 2", "point 3", ...]
}}"""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that creates concise technical summaries in JSON format."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )
            content = response.choices[0].message.content
            result = json.loads(content)
            tldr = (result.get("tldr") or "").strip()[:300]
            bullets = result.get("bullets", [])
            if not isinstance(bullets, list):
                bullets = []
            bullets = [str(b).strip() for b in bullets if b][:15]
            return {"tldr": tldr, "bullets": bullets}
        except (json.JSONDecodeError, Exception) as e:
            last_error = e
            if attempt < max_retries:
                time.sleep(2 ** attempt)
            else:
                raise RuntimeError(f"Failed to create S2 summary: {last_error}") from last_error
    raise RuntimeError(f"Failed to create S2 summary: {last_error}")


