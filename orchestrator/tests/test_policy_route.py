"""Unit tests for policy_route threshold boundaries (T2)."""

import pytest
from unittest.mock import Mock, patch
from app.rag.judge_schema import JudgeResult
from app.rag.nodes.policy import policy_route


def test_judge_disabled_returns_accept():
    """Test that policy_route returns 'accept' when judge_enabled=False."""
    state = {
        "judge_enabled": False,
        "eval_passed": True,
        "cannot_answer": False,
        "judge": None,
        "run_id": None
    }
    
    result = policy_route(state)
    assert result == "accept"


def test_cannot_answer_returns_accept():
    """Test that policy_route returns 'accept' when cannot_answer=True."""
    state = {
        "judge_enabled": True,
        "eval_passed": True,
        "cannot_answer": True,
        "judge": None,
        "run_id": None
    }
    
    result = policy_route(state)
    assert result == "accept"


def test_judge_missing_returns_accept():
    """Test that policy_route returns 'accept' when state.judge is None."""
    state = {
        "judge_enabled": True,
        "eval_passed": True,
        "cannot_answer": False,
        "judge": None,
        "run_id": None
    }
    
    result = policy_route(state)
    assert result == "accept"


def test_boundary_exact_pass_returns_accept():
    """Test that exact threshold values return 'accept'."""
    judge = JudgeResult(
        faithfulness=0.80,
        coverage=0.70,
        citation_correctness=0.75,
        overall=0.75,
        reasons=["Good answer"]
    )
    
    state = {
        "judge_enabled": True,
        "eval_passed": True,
        "cannot_answer": False,
        "judge": judge,
        "judge_threshold_overall": 0.75,
        "judge_threshold_faithfulness": 0.80,
        "judge_threshold_coverage": 0.70,
        "run_id": "test-run-123"
    }
    
    with patch('app.graphs.rag_graph._log_event') as mock_log:
        result = policy_route(state)
        assert result == "accept"
        # Verify event was logged
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args[0][2] == "policy"  # event_type
        assert call_args[0][3]["action"] == "accept"


def test_overall_below_threshold_returns_refine():
    """Test that overall < threshold returns 'refine'."""
    judge = JudgeResult(
        faithfulness=0.90,
        coverage=0.80,
        citation_correctness=0.85,
        overall=0.749,  # Below 0.75
        reasons=["Low overall"]
    )
    
    state = {
        "judge_enabled": True,
        "eval_passed": True,
        "cannot_answer": False,
        "judge": judge,
        "judge_threshold_overall": 0.75,
        "judge_threshold_faithfulness": 0.80,
        "judge_threshold_coverage": 0.70,
        "run_id": "test-run-123"
    }
    
    with patch('app.graphs.rag_graph._log_event') as mock_log:
        result = policy_route(state)
        assert result == "refine"
        # Verify event was logged
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args[0][2] == "policy"  # event_type
        assert call_args[0][3]["action"] == "refine"


def test_faithfulness_below_threshold_returns_refine():
    """Test that faithfulness < threshold returns 'refine'."""
    judge = JudgeResult(
        faithfulness=0.799,  # Below 0.80
        coverage=0.80,
        citation_correctness=0.85,
        overall=0.80,
        reasons=["Low faithfulness"]
    )
    
    state = {
        "judge_enabled": True,
        "eval_passed": True,
        "cannot_answer": False,
        "judge": judge,
        "judge_threshold_overall": 0.75,
        "judge_threshold_faithfulness": 0.80,
        "judge_threshold_coverage": 0.70,
        "run_id": "test-run-123"
    }
    
    with patch('app.graphs.rag_graph._log_event') as mock_log:
        result = policy_route(state)
        assert result == "refine"
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args[0][3]["action"] == "refine"


def test_coverage_below_threshold_returns_refine():
    """Test that coverage < threshold returns 'refine'."""
    judge = JudgeResult(
        faithfulness=0.85,
        coverage=0.699,  # Below 0.70
        citation_correctness=0.80,
        overall=0.80,
        reasons=["Low coverage"]
    )
    
    state = {
        "judge_enabled": True,
        "eval_passed": True,
        "cannot_answer": False,
        "judge": judge,
        "judge_threshold_overall": 0.75,
        "judge_threshold_faithfulness": 0.80,
        "judge_threshold_coverage": 0.70,
        "run_id": "test-run-123"
    }
    
    with patch('app.graphs.rag_graph._log_event') as mock_log:
        result = policy_route(state)
        assert result == "refine"
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args[0][3]["action"] == "refine"


def test_policy_event_only_when_judge_exists():
    """Test that policy event is written ONLY when judge_enabled=True AND judge exists."""
    # Case 1: judge_enabled=False - no event
    state1 = {
        "judge_enabled": False,
        "eval_passed": True,
        "cannot_answer": False,
        "judge": None,
        "run_id": "test-run-123"
    }
    
    with patch('app.graphs.rag_graph._log_event') as mock_log:
        policy_route(state1)
        mock_log.assert_not_called()
    
    # Case 2: judge=None - no event
    state2 = {
        "judge_enabled": True,
        "eval_passed": True,
        "cannot_answer": False,
        "judge": None,
        "run_id": "test-run-123"
    }
    
    with patch('app.graphs.rag_graph._log_event') as mock_log:
        policy_route(state2)
        mock_log.assert_not_called()
    
    # Case 3: judge exists - event written
    judge = JudgeResult(
        faithfulness=0.85,
        coverage=0.80,
        citation_correctness=0.90,
        overall=0.85,
        reasons=["Good"]
    )
    
    state3 = {
        "judge_enabled": True,
        "eval_passed": True,
        "cannot_answer": False,
        "judge": judge,
        "judge_threshold_overall": 0.75,
        "judge_threshold_faithfulness": 0.80,
        "judge_threshold_coverage": 0.70,
        "run_id": "test-run-123"
    }
    
    with patch('app.graphs.rag_graph._log_event') as mock_log:
        policy_route(state3)
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args[0][2] == "policy"
        event_data = call_args[0][3]
        assert "action" in event_data
        assert "thresholds" in event_data
        assert "observed" in event_data
        assert event_data["thresholds"]["overall"] == 0.75
        assert event_data["thresholds"]["faithfulness"] == 0.80
        assert event_data["thresholds"]["coverage"] == 0.70
        assert event_data["observed"]["overall"] == 0.85
        assert event_data["observed"]["faithfulness"] == 0.85
        assert event_data["observed"]["coverage"] == 0.80
        assert event_data["observed"]["citation_correctness"] == 0.90


def test_policy_route_simplified():
    """Test that policy_route is simplified (no rule_eval handling).
    
    Note: policy_route is now called ONLY when rule_eval_passed=True.
    Rule_eval failure handling is done at graph level, not in policy_route.
    """
    # policy_route should only handle judge-based decisions
    # This test verifies the simplified logic works correctly
    
    # Case: judge missing -> accept
    state1 = {
        "judge_enabled": True,
        "eval_passed": True,  # Must be True (graph-level gating)
        "cannot_answer": False,
        "judge": None,
        "run_id": None
    }
    
    result1 = policy_route(state1)
    assert result1 == "accept"
    
    # Case: cannot_answer=True -> accept
    state2 = {
        "judge_enabled": True,
        "eval_passed": True,
        "cannot_answer": True,
        "judge": None,
        "run_id": None
    }
    
    result2 = policy_route(state2)
    assert result2 == "accept"

