"""Query rewrite node for Week4.4: rewrite query for better retrieval."""

import json
import logging
import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...graphs.rag_graph import RAGState

logger = logging.getLogger(__name__)


def _extract_json_from_text(text: str) -> dict:
    """
    Extract JSON object from text, handling markdown code blocks.
    
    Args:
        text: Text that may contain JSON
        
    Returns:
        Extracted JSON dict or empty dict if parsing fails
    """
    import re
    
    # Remove markdown code blocks if present
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    text = text.strip()
    
    # Try to find JSON object boundaries
    start_idx = text.find('{')
    if start_idx == -1:
        return {}
    
    # Find matching closing brace
    brace_count = 0
    for i in range(start_idx, len(text)):
        if text[i] == '{':
            brace_count += 1
        elif text[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                json_str = text[start_idx:i+1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    return {}
    
    return {}


def rewrite_query(state: "RAGState") -> "RAGState":
    """
    Rewrite query for better retrieval using LLM.
    
    This node is called only when refine_strategy == "rewrite_query".
    
    Behavior:
    - If query_current is None, set it from original query
    - Call LLM with temperature=0 to rewrite query
    - Preserve user intent, do not add new requirements
    - Output should be concise (<= 2 sentences)
    - Update state.query_current with rewritten query
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with rewritten query_current
    """
    # Import here to avoid circular dependency
    from ...graphs.rag_graph import _get_repo, _get_openai_client, _log_event
    from ...utils.llm_client import get_model
    
    # Only run when refine_strategy is "rewrite_query"
    refine_strategy = state.get("refine_strategy")
    if refine_strategy != "rewrite_query":
        logger.warning(f"rewrite_query called but refine_strategy is {refine_strategy}, skipping")
        return state
    
    # Get current query (fallback to original query if not set)
    query_current = state.get("query_current")
    if query_current is None:
        query_current = state.get("query", "")
    
    if not query_current:
        logger.warning("rewrite_query called but query is empty, skipping")
        return state
    
    # Get original query for reference
    original_query = state.get("query", query_current)
    
    try:
        client = _get_openai_client()
        model = get_model("rag_rewrite")
        
        # Build rewrite prompt
        prompt = f"""Rewrite the following search query to improve retrieval of relevant information, while preserving the user's original intent.

Original query: {original_query}

Requirements:
- Preserve the user's intent exactly. Do not add new requirements or change the meaning.
- Make the query more specific and clear for information retrieval.
- Keep it concise (maximum 2 sentences).
- Focus on key terms that would help find relevant documents.

Respond ONLY with valid JSON in this exact format:
{{
  "rewritten_query": "<rewritten query text>"
}}"""

        # Call LLM with temperature=0 for deterministic output
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that rewrites queries for better information retrieval. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
        
        raw_output = response.choices[0].message.content.strip()
        
        # Parse JSON: first attempt
        rewrite_result = None
        try:
            rewrite_result = json.loads(raw_output)
        except json.JSONDecodeError:
            # Second attempt: extract JSON substring
            rewrite_result = _extract_json_from_text(raw_output)
        
        # Extract rewritten query
        rewritten_query = None
        if rewrite_result and isinstance(rewrite_result, dict):
            rewritten_query = rewrite_result.get("rewritten_query", "").strip()
        
        # Fallback to original query if parsing failed or result is empty
        if not rewritten_query:
            logger.warning(f"Failed to parse rewritten query from LLM output, using original query. Raw output: {raw_output[:200]}")
            rewritten_query = original_query
        
        # Compute short hash for persistence
        query_hash = hashlib.md5(rewritten_query.encode()).hexdigest()[:8]
        query_preview = rewritten_query[:50] if len(rewritten_query) > 50 else rewritten_query
        
        # Update refine_info
        refine_info = state.get("refine_info", {})
        refine_info = {
            **refine_info,
            "rewrite_applied": True,
            "query_hash": query_hash,
            "query_preview": query_preview
        }
        
        # Optionally log rewrite event
        _log_event(
            _get_repo(),
            state.get("run_id"),
            "rewrite_query",
            {
                "query_hash": query_hash,
                "query_preview": query_preview,
                "rewrite_applied": True,
                "attempt": state.get("attempt", 1)
            }
        )
        
        return {
            **state,
            "query_current": rewritten_query,
            "refine_info": refine_info
        }
        
    except Exception as e:
        # On error, fall back to original query (no crash)
        logger.warning(f"Query rewrite failed: {str(e)}, using original query")
        refine_info = state.get("refine_info", {})
        refine_info = {
            **refine_info,
            "rewrite_applied": False,
            "rewrite_error": str(e)[:100]
        }
        
        return {
            **state,
            "query_current": original_query,  # Fallback to original
            "refine_info": refine_info
        }

