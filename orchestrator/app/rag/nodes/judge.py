"""LLM judge node for evaluating RAG answer quality."""

import json
import re
import logging
from typing import Dict, Any, Optional, TYPE_CHECKING

from ...rag.judge_schema import JudgeResult
from ...config import get_judge_model

if TYPE_CHECKING:
    from ...graphs.rag_graph import RAGState

logger = logging.getLogger(__name__)


def _extract_json_from_text(text: str) -> Optional[str]:
    """
    Extract the first JSON object from text, handling markdown code blocks.
    
    Args:
        text: Text that may contain JSON
        
    Returns:
        Extracted JSON string or None if not found
    """
    # Remove markdown code blocks if present
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    text = text.strip()
    
    # Try to find JSON object boundaries
    # Look for first { and matching }
    start_idx = text.find('{')
    if start_idx == -1:
        return None
    
    # Find matching closing brace
    brace_count = 0
    for i in range(start_idx, len(text)):
        if text[i] == '{':
            brace_count += 1
        elif text[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                return text[start_idx:i+1]
    
    return None


def judge_answer(state: "RAGState") -> "RAGState":
    """
    Evaluate answer quality using LLM judge.
    
    Behavior:
    - If judge_enabled is False: skip judge and return
    - If cannot_answer is True or answer is missing: skip judge and return
    - Otherwise: call LLM judge with rubric and parse JSON result
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with judge result (or None if skipped/failed)
    """
    # Import here to avoid circular dependency
    from ...graphs.rag_graph import _get_repo, _get_openai_client, _log_event
    
    # Check if judge is enabled
    judge_enabled = state.get("judge_enabled", False)
    if not judge_enabled:
        return {
            **state,
            "judge": None,
            "judge_phase": None,
            "judge_run_count": state.get("judge_run_count", 0)  # Preserve count
        }
    
    # Skip judge if cannot_answer is True or answer is missing
    cannot_answer = state.get("cannot_answer", False)
    answer = state.get("answer")
    answer_text = (answer or "").strip()
    
    if cannot_answer or not answer_text:
        return {
            **state,
            "judge": None,
            "judge_phase": None,
            "judge_run_count": state.get("judge_run_count", 0)  # Preserve count
        }
    
    # Get context chunks and citations
    included_chunks = state.get("included_chunks", [])
    query = state.get("query", "")
    attempt = state.get("attempt", 1)
    top_k = state.get("top_k", 8)
    
    # Build context excerpts with IDs
    context_excerpts = []
    for idx, (chunk_dict, chunk_text_used) in enumerate(included_chunks, start=1):
        chunk_id = chunk_dict.get("chunk_id") or chunk_dict.get("id") or f"chunk_{idx}"
        context_excerpts.append({
            "id": chunk_id,
            "text": chunk_text_used[:1000]  # Limit excerpt length for judge prompt
        })
    
    # Get judge model
    judge_model = get_judge_model()
    
    # Build judge prompt
    context_text = "\n\n".join([
        f"[{idx}] {excerpt['text']}"
        for idx, excerpt in enumerate(context_excerpts, start=1)
    ])
    
    prompt = f"""You are an expert evaluator assessing the quality of an AI-generated answer.

Question: {query}

Context excerpts (with citation IDs):
{context_text}

Answer to evaluate:
{answer_text}

Evaluate the answer on three dimensions (each scored 0.0 to 1.0):

1. **faithfulness**: How faithful is the answer to the provided context?
   - Claims must be supported by the context excerpts
   - Hallucination (information not in context) => heavy penalty (0.0-0.3)
   - Minor inaccuracies => moderate penalty (0.4-0.6)
   - Mostly faithful => good score (0.7-0.9)
   - Perfectly faithful => 1.0

2. **coverage**: How well does the answer address the user's question?
   - Missing major parts of the question => penalty (0.0-0.5)
   - Partial coverage => moderate score (0.5-0.7)
   - Good coverage => high score (0.7-0.9)
   - Comprehensive coverage => 1.0

3. **citation_correctness**: Are citation markers [1], [2], etc. used correctly?
   - Missing citations when needed => penalty (0.0-0.4)
   - Citations point to irrelevant chunks => penalty (0.3-0.6)
   - Citations mostly correct => good score (0.7-0.9)
   - Perfect citations => 1.0

4. **overall**: Weighted average = 0.50*faithfulness + 0.35*coverage + 0.15*citation_correctness

Provide 1-4 brief reasons (each <= 80 characters) explaining your scores.

Respond ONLY with valid JSON in this exact format:
{{
  "faithfulness": 0.85,
  "coverage": 0.90,
  "citation_correctness": 0.80,
  "overall": 0.86,
  "reasons": ["Reason 1", "Reason 2"]
}}"""

    try:
        client = _get_openai_client()
        
        # Call judge LLM with temperature=0 for deterministic output
        response = client.chat.completions.create(
            model=judge_model,
            messages=[
                {"role": "system", "content": "You are an expert evaluator. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
        
        raw_output = response.choices[0].message.content.strip()
        
        # Parse JSON: first attempt
        judge_result_dict = None
        try:
            judge_result_dict = json.loads(raw_output)
        except json.JSONDecodeError:
            # Second attempt: extract JSON substring
            json_str = _extract_json_from_text(raw_output)
            if json_str:
                try:
                    judge_result_dict = json.loads(json_str)
                except json.JSONDecodeError:
                    pass
        
        # If parsing failed, log error and continue without judge
        if judge_result_dict is None:
            logger.warning(f"Failed to parse judge JSON output. Raw snippet: {raw_output[:200]}")
            
            # Determine phase for logging
            judge_run_count = state.get("judge_run_count", 0)
            judge_phase = "post" if judge_run_count > 0 else "pre"
            
            _log_event(
                _get_repo(),
                state.get("run_id"),
                "judge",
                {
                    "phase": judge_phase,
                    "judge_parse_error": True,
                    "model": judge_model,
                    "raw_snippet": raw_output[:200] if raw_output else ""
                }
            )
            return {
                **state,
                "judge": None,
                "judge_phase": judge_phase,
                "judge_run_count": state.get("judge_run_count", 0)  # Preserve count
            }
        
        # Create JudgeResult from parsed dict (validation/clamping handled by Pydantic)
        try:
            judge_result = JudgeResult(**judge_result_dict)
        except Exception as e:
            logger.warning(f"Failed to create JudgeResult from parsed dict: {str(e)}")
            
            # Determine phase for logging
            judge_run_count = state.get("judge_run_count", 0)
            judge_phase = "post" if judge_run_count > 0 else "pre"
            
            _log_event(
                _get_repo(),
                state.get("run_id"),
                "judge",
                {
                    "phase": judge_phase,
                    "judge_parse_error": True,
                    "model": judge_model,
                    "raw_snippet": raw_output[:200] if raw_output else "",
                    "validation_error": str(e)[:200]
                }
            )
            return {
                **state,
                "judge": None,
                "judge_phase": judge_phase,
                "judge_run_count": state.get("judge_run_count", 0)  # Preserve count
            }
        
        # Determine judge phase using judge_run_count
        # Increment judge_run_count
        judge_run_count = state.get("judge_run_count", 0) + 1
        
        # Phase determination:
        # - count == 1: first judge run (pre-refine) -> phase="pre"
        # - count == 2: second judge run (post-refine) -> phase="post"
        if judge_run_count == 1:
            judge_phase = "pre"
        elif judge_run_count == 2:
            judge_phase = "post"
        else:
            # Fallback: use refine_used as indicator
            refine_used = state.get("refine_used", False)
            judge_phase = "post" if refine_used else "pre"
        
        # Store pre_judge for metrics computation (only on first run)
        pre_judge = state.get("pre_judge")
        if judge_run_count == 1:
            pre_judge = judge_result  # Store first judge result for metrics
        
        # Log successful judge event
        _log_event(
            _get_repo(),
            state.get("run_id"),
            "judge",
            {
                "phase": judge_phase,
                "attempt": attempt,
                "model": judge_model,
                "scores": {
                    "faithfulness": judge_result.faithfulness,
                    "coverage": judge_result.coverage,
                    "citation_correctness": judge_result.citation_correctness,
                    "overall": judge_result.overall
                },
                "reasons": judge_result.reasons,
                "k": top_k
            }
        )
        
        # Build return state
        return_state = {
            **state,
            "judge": judge_result,
            "judge_phase": judge_phase,
            "judge_run_count": judge_run_count
        }
        
        # Store pre_judge for metrics computation (only on first run)
        if judge_run_count == 1:
            return_state["pre_judge"] = judge_result
        
        return return_state
        
    except Exception as e:
        # Log error and continue without judge (do NOT throw)
        logger.warning(f"Judge evaluation failed: {str(e)}")
        
        # Determine phase even on error (for logging)
        judge_run_count = state.get("judge_run_count", 0)
        if judge_run_count == 0:
            judge_phase = "pre"
        else:
            judge_phase = "post"
        
        _log_event(
            _get_repo(),
            state.get("run_id"),
            "judge",
            {
                "phase": judge_phase,
                "judge_error": True,
                "model": judge_model,
                "error": str(e)[:200]
            }
        )
        return {
            **state,
            "judge": None,
            "judge_phase": judge_phase  # Preserve phase even on error
        }

