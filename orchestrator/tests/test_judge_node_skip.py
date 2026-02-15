"""Unit tests for judge node skip logic (T3)."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from app.rag.nodes.judge import judge_answer


def test_judge_disabled_skips_llm_call():
    """Test that judge_answer skips LLM call when judge_enabled=False."""
    state = {
        "judge_enabled": False,
        "cannot_answer": False,
        "answer": "Test answer",
        "run_id": None
    }
    
    with patch('app.graphs.rag_graph._get_openai_client') as mock_get_client:
        result = judge_answer(state)
        
        # Verify LLM client was never called
        mock_get_client.assert_not_called()
        
        # Verify state.judge is None
        assert result["judge"] is None
        assert result["judge_phase"] is None


def test_cannot_answer_skips_llm_call():
    """Test that judge_answer skips LLM call when cannot_answer=True."""
    state = {
        "judge_enabled": True,
        "cannot_answer": True,
        "answer": "Test answer",
        "run_id": None
    }
    
    with patch('app.graphs.rag_graph._get_openai_client') as mock_get_client:
        result = judge_answer(state)
        
        # Verify LLM client was never called
        mock_get_client.assert_not_called()
        
        # Verify state.judge is None
        assert result["judge"] is None
        assert result["judge_phase"] is None


def test_missing_answer_skips_llm_call():
    """Test that judge_answer skips LLM call when answer is None or empty."""
    # Case 1: answer is None
    state1 = {
        "judge_enabled": True,
        "cannot_answer": False,
        "answer": None,
        "run_id": None
    }
    
    with patch('app.graphs.rag_graph._get_openai_client') as mock_get_client:
        result1 = judge_answer(state1)
        mock_get_client.assert_not_called()
        assert result1["judge"] is None
        assert result1["judge_phase"] is None
    
    # Case 2: answer is empty string
    state2 = {
        "judge_enabled": True,
        "cannot_answer": False,
        "answer": "",
        "run_id": None
    }
    
    with patch('app.graphs.rag_graph._get_openai_client') as mock_get_client:
        result2 = judge_answer(state2)
        mock_get_client.assert_not_called()
        assert result2["judge"] is None
        assert result2["judge_phase"] is None
    
    # Case 3: answer is whitespace only
    state3 = {
        "judge_enabled": True,
        "cannot_answer": False,
        "answer": "   ",
        "run_id": None
    }
    
    with patch('app.graphs.rag_graph._get_openai_client') as mock_get_client:
        result3 = judge_answer(state3)
        mock_get_client.assert_not_called()
        assert result3["judge"] is None
        assert result3["judge_phase"] is None


def test_skip_cases_no_judge_event():
    """Test that no judge event is written when judge is skipped."""
    # Mock _log_event
    with patch('app.graphs.rag_graph._log_event') as mock_log_event, \
         patch('app.graphs.rag_graph._get_openai_client'):
        
        # Case 1: judge_enabled=False
        state1 = {
            "judge_enabled": False,
            "cannot_answer": False,
            "answer": "Test answer",
            "run_id": "test-run-123"
        }
        judge_answer(state1)
        mock_log_event.assert_not_called()
        
        # Case 2: cannot_answer=True
        state2 = {
            "judge_enabled": True,
            "cannot_answer": True,
            "answer": "Test answer",
            "run_id": "test-run-123"
        }
        judge_answer(state2)
        mock_log_event.assert_not_called()
        
        # Case 3: missing answer
        state3 = {
            "judge_enabled": True,
            "cannot_answer": False,
            "answer": None,
            "run_id": "test-run-123"
        }
        judge_answer(state3)
        mock_log_event.assert_not_called()


def test_judge_enabled_with_valid_answer_calls_llm():
    """Test that judge_answer calls LLM when conditions are met."""
    state = {
        "judge_enabled": True,
        "cannot_answer": False,
        "answer": "This is a test answer with [1] citation.",
        "query": "Test query",
        "included_chunks": [
            ({"chunk_id": "chunk-1", "id": "chunk-1"}, "Context text here"),
        ],
        "attempt": 1,
        "top_k": 5,
        "run_id": "test-run-123"
    }
    
    # Mock OpenAI client response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"faithfulness": 0.85, "coverage": 0.90, "citation_correctness": 0.80, "overall": 0.86, "reasons": ["Good answer"]}'
    
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    
    with patch('app.graphs.rag_graph._get_openai_client', return_value=mock_client), \
         patch('app.graphs.rag_graph._log_event') as mock_log_event, \
         patch('app.graphs.rag_graph._get_repo'):
        
        result = judge_answer(state)
        
        # Verify LLM was called
        mock_client.chat.completions.create.assert_called_once()
        
        # Verify judge result was set
        assert result["judge"] is not None
        assert result["judge_phase"] == "pre"
        assert result["judge"].overall == 0.86
        
        # Verify event was logged
        mock_log_event.assert_called_once()
        call_args = mock_log_event.call_args
        assert call_args[0][2] == "judge"  # event_type
        assert call_args[0][3]["phase"] == "pre"

