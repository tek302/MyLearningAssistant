"""Policy routing node for Week4.3: decide accept/refine/fallback after judge."""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...graphs.rag_graph import RAGState

logger = logging.getLogger(__name__)


def policy_route(state: "RAGState") -> str:
    """
    Policy routing after judge evaluation.
    
    This function is called ONLY when:
    - rule_eval_passed == True
    - cannot_answer == False
    - judge_enabled == True
    
    Returns one of: "accept", "refine"
    
    Logic:
    - If cannot_answer=True: return "accept"
    - If judge is disabled OR state.judge is None: return "accept"
    - Else apply thresholds from state:
      - if any threshold fails: return "refine"
      - else: return "accept"
    
    Args:
        state: Current graph state
        
    Returns:
        "accept" or "refine"
    """
    # Import here to avoid circular dependency
    from ...graphs.rag_graph import _get_repo, _log_event
    
    # If cannot_answer=True: return "accept"
    cannot_answer = state.get("cannot_answer", False)
    if cannot_answer:
        return "accept"
    
    # If judge is disabled OR state.judge is None: return "accept"
    judge_enabled = state.get("judge_enabled", False)
    judge = state.get("judge")
    
    if not judge_enabled or judge is None:
        return "accept"
    
    # Apply thresholds from state
    judge_threshold_overall = state.get("judge_threshold_overall", 0.75)
    judge_threshold_faithfulness = state.get("judge_threshold_faithfulness", 0.80)
    judge_threshold_coverage = state.get("judge_threshold_coverage", 0.70)
    
    # Check thresholds
    overall = judge.overall
    faithfulness = judge.faithfulness
    coverage = judge.coverage
    
    if (overall < judge_threshold_overall) or \
       (faithfulness < judge_threshold_faithfulness) or \
       (coverage < judge_threshold_coverage):
        action = "refine"
    else:
        action = "accept"
    
    # Persist policy decision when judge exists and judge_enabled
    _log_event(
        _get_repo(),
        state.get("run_id"),
        "policy",
        {
            "action": action,
            "thresholds": {
                "overall": judge_threshold_overall,
                "faithfulness": judge_threshold_faithfulness,
                "coverage": judge_threshold_coverage
            },
            "observed": {
                "overall": overall,
                "faithfulness": faithfulness,
                "coverage": coverage,
                "citation_correctness": judge.citation_correctness
            }
        }
    )
    
    return action

