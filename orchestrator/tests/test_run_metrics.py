"""Unit tests for run metrics computation."""

import pytest
from app.graphs.run_metrics import compute_run_metrics
from app.rag.judge_schema import JudgeResult


def test_run_metrics_no_judge_no_refine():
    """Test that no metrics are computed when judge is disabled and refine not used."""
    state = {
        "judge_enabled": False,
        "refine_used": False
    }
    result = compute_run_metrics(state)
    assert result is None


def test_run_metrics_judge_enabled_no_refine():
    """Test metrics when judge enabled but no refine."""
    state = {
        "judge_enabled": True,
        "refine_used": False,
        "judge": JudgeResult(
            faithfulness=0.85,
            coverage=0.80,
            citation_correctness=0.90,
            overall=0.86,
            reasons=["Good answer"]
        ),
        "judge_phase": "pre",
        "fallback_used": False,
        "cannot_answer": False
    }
    result = compute_run_metrics(state)
    assert result is not None
    assert result["judge_enabled"] is True
    assert result["refined"] is False
    assert result["pre_overall"] == 0.86
    assert result["post_overall"] is None
    assert result["delta_overall"] is None
    assert result["final_action"] == "accept"
    assert result["accepted_after_refine"] is False


def test_run_metrics_refine_with_pre_post():
    """Test metrics when refine happened with both pre and post scores."""
    pre_judge = JudgeResult(
        faithfulness=0.60,
        coverage=0.50,
        citation_correctness=0.55,
        overall=0.55,
        reasons=["Low coverage"]
    )
    post_judge = JudgeResult(
        faithfulness=0.85,
        coverage=0.80,
        citation_correctness=0.90,
        overall=0.86,
        reasons=["Improved after refine"]
    )
    
    state = {
        "judge_enabled": True,
        "refine_used": True,
        "pre_judge": pre_judge,
        "judge": post_judge,
        "judge_phase": "post",
        "fallback_used": False,
        "cannot_answer": False
    }
    result = compute_run_metrics(state)
    assert result is not None
    assert result["judge_enabled"] is True
    assert result["refined"] is True
    assert result["pre_overall"] == 0.55
    assert result["post_overall"] == 0.86
    assert result["delta_overall"] == pytest.approx(0.31)
    assert result["final_action"] == "accept"
    assert result["accepted_after_refine"] is True


def test_run_metrics_refine_fallback():
    """Test metrics when refine happened but still falls back."""
    pre_judge = JudgeResult(
        faithfulness=0.60,
        coverage=0.50,
        citation_correctness=0.55,
        overall=0.55,
        reasons=["Low scores"]
    )
    post_judge = JudgeResult(
        faithfulness=0.65,
        coverage=0.60,
        citation_correctness=0.70,
        overall=0.65,
        reasons=["Still low"]
    )
    
    state = {
        "judge_enabled": True,
        "refine_used": True,
        "pre_judge": pre_judge,
        "judge": post_judge,
        "judge_phase": "post",
        "fallback_used": True,
        "cannot_answer": True
    }
    result = compute_run_metrics(state)
    assert result is not None
    assert result["refined"] is True
    assert result["pre_overall"] == 0.55
    assert result["post_overall"] == 0.65
    assert result["delta_overall"] == pytest.approx(0.10)
    assert result["final_action"] == "fallback"
    assert result["accepted_after_refine"] is False

