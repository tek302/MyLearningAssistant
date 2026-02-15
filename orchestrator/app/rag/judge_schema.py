"""Pydantic schema for LLM judge evaluation results."""

from typing import List
from pydantic import BaseModel, Field, field_validator


class JudgeResult(BaseModel):
    """
    Result from LLM judge evaluation of RAG answer quality.
    
    All scores are in [0, 1] range, with higher values indicating better quality.
    """
    
    faithfulness: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="How faithful the answer is to the retrieved context (0-1)"
    )
    coverage: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="How well the answer covers the query (0-1)"
    )
    citation_correctness: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="How correct the citation markers are (0-1)"
    )
    overall: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall quality score (0-1)"
    )
    reasons: List[str] = Field(
        default_factory=list,
        description="List of evaluation reasons (1-4 items, each <= 80 chars)"
    )
    
    @field_validator('faithfulness', 'coverage', 'citation_correctness', 'overall', mode='before')
    @classmethod
    def clamp_scores(cls, v: float) -> float:
        """Clamp all scores to [0, 1] deterministically."""
        if not isinstance(v, (int, float)):
            return 0.0
        return max(0.0, min(1.0, float(v)))
    
    @field_validator('reasons', mode='before')
    @classmethod
    def validate_reasons(cls, v) -> List[str]:
        """Trim reasons to max 4 and truncate each to 80 chars."""
        if not isinstance(v, list):
            return []
        
        # Convert all items to strings and trim
        reasons = [str(r).strip() for r in v if r]
        
        # Limit to max 4 items
        reasons = reasons[:4]
        
        # Truncate each to 80 chars
        reasons = [r[:80] if len(r) > 80 else r for r in reasons]
        
        return reasons
    
    def model_dump(self) -> dict:
        """
        Convert to dictionary suitable for persistence.
        
        Returns:
            Dictionary with all fields, ready for JSON serialization
        """
        return {
            "faithfulness": self.faithfulness,
            "coverage": self.coverage,
            "citation_correctness": self.citation_correctness,
            "overall": self.overall,
            "reasons": self.reasons
        }
    
    def to_dict(self) -> dict:
        """Alias for model_dump() for backward compatibility."""
        return self.model_dump()

