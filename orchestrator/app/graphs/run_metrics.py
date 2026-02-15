"""Helper functions for computing run metrics."""

from typing import Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .rag_graph import RAGState
else:
    # Avoid circular import at runtime
    RAGState = Dict[str, Any]


def compute_run_metrics(state: "RAGState") -> Optional[Dict[str, Any]]:
    """
    Compute run metrics for refine effectiveness tracking.
    
    Metrics computed:
    - judge_enabled: Whether judge was enabled
    - refined: Whether refine loop was used
    - pre_overall: First judge overall score (phase="pre")
    - post_overall: Second judge overall score (phase="post")
    - delta_overall: post_overall - pre_overall (if both exist)
    - final_action: "accept" | "fallback" (from last policy decision or fallback status)
    - accepted_after_refine: refined==True AND final_action=="accept"
    
    Args:
        state: Final graph state after run completion
        
    Returns:
        Dict with metrics if judge_enabled=True OR refined=True, None otherwise
    """
    judge_enabled = state.get("judge_enabled", False)
    refined = state.get("refine_used", False)
    
    # Only compute metrics if judge was enabled or refine was used
    if not judge_enabled and not refined:
        return None
    
    # Extract judge scores from state (we need to track judge events or store in state)
    # For now, we'll extract from state.judge if available, but we need to track pre/post
    # Since judge_run_count tracks this, we can infer:
    judge_run_count = state.get("judge_run_count", 0)
    judge_phase = state.get("judge_phase")
    current_judge = state.get("judge")
    
    # We need to track pre and post scores separately
    # For now, we'll use a simple approach: if judge_run_count == 2, we have both
    # But we need to store pre_overall separately. Let's check if we can infer from state.
    # Actually, we should store pre_judge in state during refine_plan or after first judge.
    
    # For minimal implementation, we'll compute what we can:
    pre_overall = None
    post_overall = None
    delta_overall = None
    
    # If we have a judge result and know the phase, use it (fallback if pre_judge not stored)
    if current_judge and judge_phase:
        if judge_phase == "pre" and pre_overall is None:
            if hasattr(current_judge, 'overall'):
                pre_overall = float(current_judge.overall)
        elif judge_phase == "post":
            if hasattr(current_judge, 'overall'):
                post_overall = float(current_judge.overall)
    
    # Get pre_overall from stored pre_judge (stored by judge node on first run)
    pre_judge = state.get("pre_judge")
    if pre_judge:
        # pre_judge is a JudgeResult object
        if hasattr(pre_judge, 'overall'):
            pre_overall = float(pre_judge.overall)
        elif isinstance(pre_judge, dict):
            pre_overall = pre_judge.get("overall")
            if pre_overall is not None:
                pre_overall = float(pre_overall)
    
    # If we have both, compute delta
    if pre_overall is not None and post_overall is not None:
        delta_overall = post_overall - pre_overall
    
    # Determine final_action from last policy decision or fallback status
    final_action = "fallback"  # Default
    fallback_used = state.get("fallback_used", False)
    cannot_answer = state.get("cannot_answer", False)
    
    if not fallback_used and not cannot_answer:
        # Check if we have a policy event or can infer from state
        # For now, if not fallback, assume accept
        final_action = "accept"
    
    # Compute accepted_after_refine
    accepted_after_refine = refined and (final_action == "accept")
    
    return {
        "judge_enabled": judge_enabled,
        "refined": refined,
        "pre_overall": pre_overall,
        "post_overall": post_overall,
        "delta_overall": delta_overall,
        "final_action": final_action,
        "accepted_after_refine": accepted_after_refine
    }

