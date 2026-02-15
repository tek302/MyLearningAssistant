"""Unit tests for JudgeResult schema validation (T1)."""

import pytest
from app.rag.judge_schema import JudgeResult


def test_score_clamping():
    """Test that out-of-range scores are clamped to [0.0, 1.0]."""
    result = JudgeResult(
        faithfulness=1.2,
        coverage=-0.1,
        citation_correctness=2.0,
        overall=-5,
        reasons=[]
    )
    
    assert result.faithfulness == 1.0, "faithfulness should be clamped to 1.0"
    assert result.coverage == 0.0, "coverage should be clamped to 0.0"
    assert result.citation_correctness == 1.0, "citation_correctness should be clamped to 1.0"
    assert result.overall == 0.0, "overall should be clamped to 0.0"


def test_reasons_trimming():
    """Test that reasons list is trimmed to max 4 items."""
    long_reasons = [f"Reason {i}" for i in range(6)]
    result = JudgeResult(
        faithfulness=0.8,
        coverage=0.7,
        citation_correctness=0.9,
        overall=0.8,
        reasons=long_reasons
    )
    
    assert len(result.reasons) == 4, f"Expected 4 reasons, got {len(result.reasons)}"
    assert result.reasons == ["Reason 0", "Reason 1", "Reason 2", "Reason 3"]


def test_reason_truncation():
    """Test that individual reasons are truncated to 80 characters."""
    long_reason = "A" * 100  # 100 characters
    result = JudgeResult(
        faithfulness=0.8,
        coverage=0.7,
        citation_correctness=0.9,
        overall=0.8,
        reasons=[long_reason]
    )
    
    assert len(result.reasons) == 1, "Should have one reason"
    assert len(result.reasons[0]) == 80, f"Reason should be truncated to 80 chars, got {len(result.reasons[0])}"
    assert result.reasons[0] == "A" * 80


def test_stable_serialization():
    """Test that model_dump()/to_dict() returns correct structure."""
    result = JudgeResult(
        faithfulness=0.85,
        coverage=0.90,
        citation_correctness=0.80,
        overall=0.86,
        reasons=["Reason 1", "Reason 2"]
    )
    
    # Test model_dump()
    dumped = result.model_dump()
    assert isinstance(dumped, dict), "model_dump() should return dict"
    assert set(dumped.keys()) == {"faithfulness", "coverage", "citation_correctness", "overall", "reasons"}
    assert dumped["faithfulness"] == 0.85
    assert dumped["coverage"] == 0.90
    assert dumped["citation_correctness"] == 0.80
    assert dumped["overall"] == 0.86
    assert dumped["reasons"] == ["Reason 1", "Reason 2"]
    assert isinstance(dumped["faithfulness"], float)
    assert isinstance(dumped["reasons"], list)
    
    # Test to_dict() alias
    to_dict_result = result.to_dict()
    assert to_dict_result == dumped, "to_dict() should return same as model_dump()"

