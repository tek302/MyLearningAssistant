import os
import re
import time
import json
from typing import Dict, Any, List
from dotenv import load_dotenv

from app.utils.llm_client import get_chat_client, get_model

# Load environment variables
load_dotenv()


def get_summary_model() -> str:
    """Backward-compat wrapper. Prefer get_model(purpose) for new code."""
    return get_model("default")


def get_s1_max_chunks() -> int:
    """Get maximum chunks for S1 summarization, defaulting to 12."""
    try:
        return int(os.getenv("S1_MAX_CHUNKS", "12"))
    except ValueError:
        return 12


# Feed-friendly: short tldr (up to 3 sentences) + key points (configurable)
S1_TLDR_MAX_CHARS = 250
S1_TLDR_MAX_SENTENCES = 3
S1_BULLETS_COUNT = 3


def _truncate_tldr(tldr: str, max_chars: int, max_sentences: int) -> str:
    """Cap tldr by sentence count, then by character length."""
    tldr = tldr.strip()
    if not tldr:
        return tldr
    max_sentences = max(1, max_sentences)
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", tldr) if p.strip()]
    if len(parts) > max_sentences:
        tldr = " ".join(parts[:max_sentences])
    if len(tldr) > max_chars:
        tldr = tldr[:max_chars].strip()
    return tldr


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
    model = get_model("s1_summary")
    client = get_chat_client()

    tldr_max = int(os.getenv("S1_TLDR_MAX_CHARS", str(S1_TLDR_MAX_CHARS)))
    tldr_max_sentences = int(os.getenv("S1_TLDR_MAX_SENTENCES", str(S1_TLDR_MAX_SENTENCES)))
    tldr_max_sentences = max(1, min(5, tldr_max_sentences))
    bullets_count = int(os.getenv("S1_BULLETS_COUNT", str(S1_BULLETS_COUNT)))
    bullets_count = max(1, min(7, bullets_count))
    prompt = f"""Summarize the following document text in JSON.

1. tldr: Up to {tldr_max_sentences} sentences (max {tldr_max} characters total). Cover the main topic and, for research papers, state the primary contribution, achievement, or key findings.
2. bullets: Exactly {bullets_count} key points. Each point one short phrase or sentence; include method, results, or impact where relevant.
3. tags: Optional, max 6 comma-separated keywords.

Text content:
{chunks_text}

Respond in JSON only:
{{
  "tldr": "summary with contribution or findings when applicable",
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
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful assistant that creates concise document summaries in JSON format. "
                            "For research papers, highlight the main contribution or achievement in the tldr."
                        ),
                    },
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )
            
            # Parse JSON response
            content = response.choices[0].message.content
            result = json.loads(content)
            
            tldr_max = int(os.getenv("S1_TLDR_MAX_CHARS", str(S1_TLDR_MAX_CHARS)))
            tldr_max_sentences = int(os.getenv("S1_TLDR_MAX_SENTENCES", str(S1_TLDR_MAX_SENTENCES)))
            tldr_max_sentences = max(1, min(5, tldr_max_sentences))
            bullets_count = int(os.getenv("S1_BULLETS_COUNT", str(S1_BULLETS_COUNT)))
            bullets_count = max(1, min(7, bullets_count))
            tldr = _truncate_tldr(result.get("tldr", ""), tldr_max, tldr_max_sentences)
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
    (v1 — kept for fallback when S2_SUMMARY_VERSION=v1)
    """
    model = get_model("s2_summary")
    client = get_chat_client()
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


# ---------------------------------------------------------------------------
# S2 v2: Keyword-conditioned + cross-week trajectory
# ---------------------------------------------------------------------------

def _build_s2_v2_prompt(
    s1_text: str,
    keywords: List[Dict[str, Any]],
    notes_text: str,
    feedback_text: str,
    prev_s2_text: str,
) -> str:
    kw_block = ", ".join(k["keyword"] for k in keywords) if keywords else ""
    has_keywords = bool(kw_block)

    keyword_instruction = (
        f"""The user's active research keywords (ordered by importance):
{kw_block}

Organize the summary into SECTIONS, one per keyword that appeared in this week's reading.
If a document's content does not match any keyword, include it under an appropriate keyword or list the topic in "emerging_topics"."""
        if has_keywords
        else """The user has no registered keywords yet.
Identify the main topics from the documents yourself and create sections for each topic.
List all identified topics in "emerging_topics" so the user can register them as keywords."""
    )

    trajectory_block = ""
    if prev_s2_text:
        trajectory_block = f"""
--- PREVIOUS WEEK'S SUMMARY ---
{prev_s2_text[:3000]}

Compare this week's reading with the previous week:
- "deepened": topics that continued and went deeper this week
- "new_this_week": topics that appeared for the first time this week
- "paused": topics from last week that had no related documents this week"""
    else:
        trajectory_block = """
No previous week summary is available. Set "trajectory" to null."""

    notes_block = f"\n--- USER NOTES (recent) ---\n{notes_text[:1500]}" if notes_text else ""
    feedback_block = f"\n--- USER FEEDBACK (recent) ---\n{feedback_text[:1000]}" if feedback_text else ""

    return f"""You are a personal learning advisor creating a structured weekly reading summary.

{keyword_instruction}
{notes_block}
{feedback_block}

--- THIS WEEK'S DOCUMENT SUMMARIES ---
{s1_text[:10000]}
{trajectory_block}

Produce JSON with these fields:

1. "tldr": ONE sentence (max 250 chars) capturing the overall theme, written in second person ("You explored…" or "This week you…").
2. "bullets": 5-10 key technical points across all documents (flat list, for backward compatibility).
3. "sections": array of objects, each with:
   - "keyword": the keyword or identified topic name
   - "insights": array of 1-4 short insight strings for that topic
   - "doc_count": number of documents related to this keyword
4. "emerging_topics": array of topic strings that don't match any existing keyword.
5. "connections": array of objects with "docs" (array of 2 doc descriptions) and "insight" (string) — cross-document connections. Empty array if none found.
6. "trajectory": object with "deepened" (array of strings), "new_this_week" (array of strings), "paused" (array of strings). Each string is "topic: one-sentence description". null if no previous week data.
7. "reflection": 1-2 sentences of learning reflection and what might be interesting to explore next week. Written in second person.

Respond in JSON only."""


def _parse_s2_v2_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize the LLM JSON output for v2."""
    tldr = (result.get("tldr") or "").strip()[:300]

    bullets = result.get("bullets", [])
    if not isinstance(bullets, list):
        bullets = []
    bullets = [str(b).strip() for b in bullets if b][:15]

    sections = result.get("sections", [])
    if not isinstance(sections, list):
        sections = []
    clean_sections = []
    for s in sections[:10]:
        if not isinstance(s, dict):
            continue
        kw = (s.get("keyword") or "").strip()
        if not kw:
            continue
        insights = s.get("insights", [])
        if not isinstance(insights, list):
            insights = [str(insights).strip()] if insights else []
        insights = [str(i).strip() for i in insights if i][:4]
        doc_count = s.get("doc_count", 0)
        if not isinstance(doc_count, int):
            try:
                doc_count = int(doc_count)
            except (ValueError, TypeError):
                doc_count = 0
        clean_sections.append({"keyword": kw, "insights": insights, "doc_count": doc_count})

    emerging = result.get("emerging_topics", [])
    if not isinstance(emerging, list):
        emerging = []
    emerging = [str(t).strip() for t in emerging if t][:10]

    connections = result.get("connections", [])
    if not isinstance(connections, list):
        connections = []
    clean_conns = []
    for c in connections[:5]:
        if not isinstance(c, dict):
            continue
        docs = c.get("docs", [])
        if not isinstance(docs, list):
            docs = []
        docs = [str(d).strip() for d in docs if d][:3]
        insight = (c.get("insight") or "").strip()
        if docs and insight:
            clean_conns.append({"docs": docs, "insight": insight})

    trajectory = result.get("trajectory")
    clean_traj = None
    if isinstance(trajectory, dict):
        clean_traj = {}
        for key in ("deepened", "new_this_week", "paused"):
            val = trajectory.get(key, [])
            if not isinstance(val, list):
                val = []
            clean_traj[key] = [str(v).strip() for v in val if v][:5]
        if not any(clean_traj.values()):
            clean_traj = None

    reflection = (result.get("reflection") or "").strip()[:500]

    return {
        "tldr": tldr,
        "bullets": bullets,
        "sections": clean_sections,
        "emerging_topics": emerging,
        "connections": clean_conns,
        "trajectory": clean_traj,
        "reflection": reflection,
    }


def create_s2_summary_v2(
    s1_text: str,
    keywords: List[Dict[str, Any]],
    notes_text: str = "",
    feedback_text: str = "",
    prev_s2_text: str = "",
    max_retries: int = 2,
) -> Dict[str, Any]:
    """
    S2 v2: keyword-conditioned, cross-week trajectory, cross-document connections.
    Returns dict with: tldr, bullets, sections, emerging_topics, connections, trajectory, reflection.
    """
    model = get_model("s2_summary")
    client = get_chat_client()
    prompt = _build_s2_v2_prompt(s1_text, keywords, notes_text, feedback_text, prev_s2_text)

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a personal learning advisor that produces structured weekly reading summaries in JSON."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.4,
            )
            content = response.choices[0].message.content
            result = json.loads(content)
            return _parse_s2_v2_result(result)
        except (json.JSONDecodeError, Exception) as e:
            last_error = e
            if attempt < max_retries:
                time.sleep(2 ** attempt)
            else:
                raise RuntimeError(f"Failed to create S2 v2 summary: {last_error}") from last_error
    raise RuntimeError(f"Failed to create S2 v2 summary: {last_error}")


