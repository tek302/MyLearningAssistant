"""Unit tests for refine_plan node strategy selection (Part 6A)."""

import pytest
from unittest.mock import patch, MagicMock
from app.rag.nodes.refine_plan import refine_plan
from app.rag.judge_schema import JudgeResult


@pytest.fixture
def base_state():
    """Base state for refine_plan tests."""
    return {
        "user_id": "test-user",
        "query": "What is LangGraph?",
        "query_current": "What is LangGraph?",
        "top_k": 8,
        "k_current": 8,
        "run_id": "test-run-123",
        "attempt": 1,
        "refine_used": False,
        "refine_strategy": None,
        "refine_info": None
    }


def test_refine_plan_coverage_less_than_faithfulness_chooses_expand_k(base_state):
    """Test: coverage < faithfulness -> choose expand_k, k increases by +4 up to max 20."""
    # Setup: coverage < faithfulness
    judge = JudgeResult(
        faithfulness=0.85,
        coverage=0.60,  # Lower than faithfulness
        citation_correctness=0.70,
        overall=0.70,
        reasons=["Low coverage"]
    )
    state = {
        **base_state,
        "judge": judge
    }
    
    with patch('app.graphs.rag_graph._log_event'), \
         patch('app.graphs.rag_graph._get_repo'):
        result = refine_plan(state)
    
    # Assert strategy is expand_k
    assert result["refine_strategy"] == "expand_k"
    assert result["refine_used"] is True
    
    # Assert k increased by 4 (8 -> 12)
    assert result["k_current"] == 12
    assert result["refine_info"]["k_before"] == 8
    assert result["refine_info"]["k_after"] == 12
    assert result["refine_info"]["rewrite_applied"] is False


def test_refine_plan_k_caps_at_20(base_state):
    """Test: k increase caps at 20."""
    # Setup: k_current = 18, should cap at 20
    judge = JudgeResult(
        faithfulness=0.85,
        coverage=0.60,  # Lower than faithfulness
        citation_correctness=0.70,
        overall=0.70,
        reasons=["Low coverage"]
    )
    state = {
        **base_state,
        "k_current": 18,
        "judge": judge
    }
    
    with patch('app.graphs.rag_graph._log_event'), \
         patch('app.graphs.rag_graph._get_repo'):
        result = refine_plan(state)
    
    # Assert k capped at 20
    assert result["k_current"] == 20
    assert result["refine_info"]["k_before"] == 18
    assert result["refine_info"]["k_after"] == 20


def test_refine_plan_citation_correctness_low_chooses_expand_k(base_state):
    """Test: citation_correctness < 0.5 -> choose expand_k."""
    # Setup: citation_correctness < 0.5
    judge = JudgeResult(
        faithfulness=0.85,
        coverage=0.80,  # Higher than faithfulness
        citation_correctness=0.40,  # Below 0.5 threshold
        overall=0.70,
        reasons=["Low citation correctness"]
    )
    state = {
        **base_state,
        "judge": judge
    }
    
    with patch('app.graphs.rag_graph._log_event'), \
         patch('app.graphs.rag_graph._get_repo'):
        result = refine_plan(state)
    
    # Assert strategy is expand_k (not rewrite_query)
    assert result["refine_strategy"] == "expand_k"
    assert result["refine_used"] is True
    assert result["k_current"] == 12  # 8 + 4


def test_refine_plan_faithfulness_limiting_chooses_rewrite_query(base_state):
    """Test: faithfulness <= coverage and faithfulness is limiting -> choose rewrite_query."""
    # Setup: faithfulness <= coverage (faithfulness is limiting)
    judge = JudgeResult(
        faithfulness=0.60,  # Lower, limiting factor
        coverage=0.80,  # Higher than faithfulness
        citation_correctness=0.70,  # Above 0.5 threshold
        overall=0.70,
        reasons=["Low faithfulness"]
    )
    state = {
        **base_state,
        "judge": judge
    }
    
    with patch('app.graphs.rag_graph._log_event'), \
         patch('app.graphs.rag_graph._get_repo'):
        result = refine_plan(state)
    
    # Assert strategy is rewrite_query
    assert result["refine_strategy"] == "rewrite_query"
    assert result["refine_used"] is True
    
    # Assert k does not change
    assert result["k_current"] == 8
    assert result["refine_info"]["k_before"] == 8
    assert result["refine_info"]["k_after"] == 8
    assert result["refine_info"]["rewrite_applied"] is False  # Will be set after rewrite
    assert "query_hash" in result["refine_info"]


def test_refine_plan_already_used_skips_strategy(base_state):
    """Test: refine_used already True -> refine_plan does not choose a new strategy."""
    # Setup: refine_used is True
    judge = JudgeResult(
        faithfulness=0.60,
        coverage=0.80,
        citation_correctness=0.70,
        overall=0.70,
        reasons=["Test"]
    )
    state = {
        **base_state,
        "refine_used": True,  # Already used
        "judge": judge
    }
    
    with patch('app.graphs.rag_graph._log_event'), \
         patch('app.graphs.rag_graph._get_repo'):
        result = refine_plan(state)
    
    # Assert refine_info indicates skip
    assert result["refine_info"]["skipped"] == "already_used"
    
    # Assert strategy is NOT set
    assert result.get("refine_strategy") is None
    
    # Assert refine_used remains True
    assert result["refine_used"] is True
    
    # Assert k_current unchanged
    assert result["k_current"] == 8


def test_refine_plan_no_judge_skips(base_state):
    """Test: refine_plan called without judge -> skip."""
    # Setup: no judge
    state = {
        **base_state,
        "judge": None
    }
    
    with patch('app.graphs.rag_graph._log_event'), \
         patch('app.graphs.rag_graph._get_repo'):
        result = refine_plan(state)
    
    # Assert refine_info indicates skip
    assert result["refine_info"]["skipped"] == "no_judge"
    
    # Assert strategy is NOT set
    assert result.get("refine_strategy") is None


def test_refine_plan_logs_refine_event(base_state):
    """Test: refine_plan logs refine event with correct data."""
    judge = JudgeResult(
        faithfulness=0.60,
        coverage=0.80,
        citation_correctness=0.70,
        overall=0.70,
        reasons=["Test"]
    )
    state = {
        **base_state,
        "judge": judge
    }
    
    captured_events = []
    
    def capture_log(repo, run_id, event_type, data):
        captured_events.append({
            "event_type": event_type,
            "data": data
        })
    
    with patch('app.graphs.rag_graph._log_event', side_effect=capture_log), \
         patch('app.graphs.rag_graph._get_repo'):
        result = refine_plan(state)
    
    # Assert refine event was logged
    assert len(captured_events) == 1
    assert captured_events[0]["event_type"] == "refine"
    assert captured_events[0]["data"]["strategy"] == "rewrite_query"  # faithfulness <= coverage
    assert captured_events[0]["data"]["refine_step"] == 1
    assert captured_events[0]["data"]["attempt"] == 1

