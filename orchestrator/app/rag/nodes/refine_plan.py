"""Refine planning node for Week4.4: choose refine strategy based on judge scores."""

import logging
import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...graphs.rag_graph import RAGState

logger = logging.getLogger(__name__)


def refine_plan(state: "RAGState") -> "RAGState":
    """
    Plan refine strategy based on judge scores.
    
    This node is called only when policy_route returned "refine".
    
    Behavior:
    - If refine_used is True: skip and route to fallback
    - Otherwise choose strategy based on judge scores:
      - expand_k: when coverage < faithfulness OR citation_correctness < 0.50
      - rewrite_query: when faithfulness <= coverage and faithfulness is limiting
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with refine strategy and parameters
    """
    # Import here to avoid circular dependency
    from ...graphs.rag_graph import _get_repo, _log_event
    
    # Check if refine was already used
    refine_used = state.get("refine_used", False)
    if refine_used:
        # Already used refine, skip and route to fallback
        refine_info = {
            "skipped": "already_used"
        }
        return {
            **state,
            "refine_info": refine_info
        }
    
    # Get judge result (must exist if we're here)
    judge = state.get("judge")
    if not judge:
        logger.warning("refine_plan called but judge is None, routing to fallback")
        refine_info = {
            "skipped": "no_judge"
        }
        return {
            **state,
            "refine_info": refine_info
        }
    
    # Get current k value (default to top_k if k_current not set)
    k_current = state.get("k_current")
    if k_current is None:
        k_current = state.get("top_k", 8)
    
    # Get current query
    query_current = state.get("query_current")
    if query_current is None:
        query_current = state.get("query", "")
    
    # Choose strategy based on judge scores
    coverage = judge.coverage
    faithfulness = judge.faithfulness
    citation_correctness = judge.citation_correctness
    
    # Strategy selection logic
    if coverage < faithfulness or citation_correctness < 0.50:
        # Prefer expand_k when:
        # - coverage is worse than faithfulness (need more context)
        # - citation correctness is very low (need more chunks to find correct citations)
        strategy = "expand_k"
        k_before = k_current
        k_after = min(k_before + 4, 20)  # Increase by 4, cap at 20
        
        refine_info = {
            "strategy": strategy,
            "k_before": k_before,
            "k_after": k_after,
            "rewrite_applied": False
        }
        
        # Log refine event
        _log_event(
            _get_repo(),
            state.get("run_id"),
            "refine",
            {
                "strategy": strategy,
                "k_before": k_before,
                "k_after": k_after,
                "rewrite_applied": False,
                "attempt": state.get("attempt", 1),
                "refine_step": 1
            }
        )
        
        return {
            **state,
            "refine_used": True,
            "refine_strategy": strategy,
            "k_current": k_after,
            "refine_info": refine_info
        }
    
    else:
        # Prefer rewrite_query when:
        # - faithfulness <= coverage and faithfulness is the limiting factor
        # (coverage is better or equal, but faithfulness needs improvement)
        strategy = "rewrite_query"
        
        # Compute query hash for persistence (short hash)
        query_hash = hashlib.md5(query_current.encode()).hexdigest()[:8]
        
        refine_info = {
            "strategy": strategy,
            "k_before": k_current,
            "k_after": k_current,  # k doesn't change for rewrite
            "rewrite_applied": False,  # Will be set to True after rewrite
            "query_hash": query_hash
        }
        
        # Log refine event
        _log_event(
            _get_repo(),
            state.get("run_id"),
            "refine",
            {
                "strategy": strategy,
                "k_before": k_current,
                "k_after": k_current,
                "rewrite_applied": False,
                "attempt": state.get("attempt", 1),
                "refine_step": 1,
                "query_hash": query_hash
            }
        )
        
        return {
            **state,
            "refine_used": True,
            "refine_strategy": strategy,
            "k_current": k_current,  # k doesn't change
            "refine_info": refine_info
        }

