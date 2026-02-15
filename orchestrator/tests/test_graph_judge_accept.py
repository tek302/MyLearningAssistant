"""Integration test for judge enabled → accept path (T4) - DB/ingest-free."""

import os
import pytest
import json
from unittest.mock import patch, MagicMock
from app.graphs.rag_graph import get_rag_graph


@pytest.fixture
def mock_judge_high_scores():
    """Mock judge LLM response with high scores that pass thresholds."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "faithfulness": 0.85,
        "coverage": 0.80,
        "citation_correctness": 0.90,
        "overall": 0.86,
        "reasons": ["Good answer", "Well cited"]
    })
    return mock_response


@pytest.fixture
def mock_synthesis_response():
    """Mock synthesis LLM response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "FastAPI is a web framework for building APIs [1]."
    return mock_response


@pytest.fixture
def fixed_chunks():
    """Fixed chunks for stub retrieval."""
    return [
        {
            "chunk_id": "1",
            "source_id": "source-1",
            "chunk_index": 0,
            "chunk_text": "LangGraph is a library for building agent workflows.",
            "url": "https://example.com/langgraph",
            "title": "LangGraph Docs",
            "score": 0.95
        },
        {
            "chunk_id": "2",
            "source_id": "source-1",
            "chunk_index": 1,
            "chunk_text": "A judge node evaluates answers using faithfulness and coverage.",
            "url": "https://example.com/judge",
            "title": "Judge Node",
            "score": 0.90
        }
    ]


def test_judge_enabled_accept_path(mock_judge_high_scores, mock_synthesis_response, fixed_chunks):
    """Test integration: judge enabled with high scores → accept path."""
    # Capture events
    captured_events = []
    
    def capture_event(repo, run_id, event_type, data):
        captured_events.append({
            "event_type": event_type,
            "data": data
        })
    
    # Mock OpenAI client
    def mock_create(*args, **kwargs):
        messages = kwargs.get('messages', [])
        content = str(messages[-1].get('content', '')) if messages else ''
        
        # Judge call detection
        if 'evaluator' in content.lower() or 'evaluate' in content.lower():
            return mock_judge_high_scores
        # Synthesis call
        return mock_synthesis_response
    
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = mock_create
    
    # Mock embeddings (return fixed embedding vector)
    def mock_create_embeddings(texts, max_retries=2):
        # Return fixed embedding for each text
        return [[0.1] * 1536 for _ in texts]
    
    # Stub retrieve_chunks to return fixed chunks
    # Note: The graph node is named "retrieve_chunks" but the function is node_retrieve_chunks
    def stub_retrieve_chunks(state):
        from app.graphs.rag_graph import RAGState
        # Also need to set query_vec for consistency
        return {
            **state,
            "retrieved_chunks": fixed_chunks,
            "query_vec": [0.1] * 1536  # Mock query vector
        }
    
    # Stub build_context to use fixed chunks
    def stub_build_context(state):
        from app.graphs.rag_graph import RAGState
        chunk_texts = [chunk["chunk_text"] for chunk in fixed_chunks]
        context_text = "\n\n".join([f"[{i+1}] {text}" for i, text in enumerate(chunk_texts)])
        included_chunks = [
            (chunk, chunk["chunk_text"]) for chunk in fixed_chunks
        ]
        return {
            **state,
            "context_text": context_text,
            "included_chunks": included_chunks
        }
    
    # Stub synthesize_answer to return a valid answer
    def stub_synthesize_answer(state):
        from app.graphs.rag_graph import RAGState
        return {
            **state,
            "answer": "FastAPI is a web framework for building APIs [1].",
            "model": "gpt-4o-mini",
            "cannot_answer": False
        }
    
    # Stub eval_answer to always pass
    def stub_eval_answer(state):
        from app.graphs.rag_graph import RAGState
        return {
            **state,
            "eval_passed": True,
            "eval_reasons": [],
            "cannot_answer": False
        }
    
    # Initial state with judge enabled
    initial_state = {
        "user_id": "test-user",
        "query": "What is LangGraph?",
        "top_k": 3,
        "topic": None,
        "lang": None,
        "query_vec": None,
        "retrieved_chunks": [],
        "context_text": "",
        "included_chunks": [],
        "answer": "",
        "citations": [],
        "run_id": None,
        "started_at": 0.0,
        "latency_ms": 0,
        "model": "",
        "user_requested_top_k": 3,
        "attempt": 1,
        "max_attempts": 2,
        "eval_passed": False,
        "eval_reasons": [],
        "fallback_used": False,
        "cannot_answer": False,
        "judge_enabled": True,
        "judge_threshold_overall": 0.75,
        "judge_threshold_faithfulness": 0.80,
        "judge_threshold_coverage": 0.70,
        "judge": None,
        "judge_phase": None
    }
    
    with patch('app.graphs.rag_graph._get_openai_client', return_value=mock_client), \
         patch('app.graphs.rag_graph.create_embeddings', side_effect=mock_create_embeddings), \
         patch('app.graphs.rag_graph.node_retrieve_chunks', side_effect=stub_retrieve_chunks), \
         patch('app.graphs.rag_graph.node_build_context', side_effect=stub_build_context), \
         patch('app.graphs.rag_graph.node_synthesize_answer', side_effect=stub_synthesize_answer), \
         patch('app.graphs.rag_graph.node_eval_answer', side_effect=stub_eval_answer), \
         patch('app.graphs.rag_graph._log_event', side_effect=capture_event), \
         patch('app.graphs.rag_graph._log_run_start', return_value="test-run-123"), \
         patch('app.graphs.rag_graph._log_run_complete'), \
         patch('app.graphs.rag_graph._log_run_error'), \
         patch('app.graphs.rag_graph._get_repo'):
        
        # Get fresh graph after monkeypatching
        graph = get_rag_graph(reset=True)
        
        # Run graph
        final_state = graph.invoke(initial_state)
        
        # Debug: print all captured events
        print(f"\nCaptured events: {captured_events}")
        
        # Assert response is successful (non-fallback)
        assert final_state.get("answer", ""), "Answer should not be empty"
        assert not final_state.get("fallback_used", False), "Should not use fallback when judge accepts"
        
        # Assert events: exactly one judge event and one policy event
        judge_events = [e for e in captured_events if e["event_type"] == "judge"]
        policy_events = [e for e in captured_events if e["event_type"] == "policy"]
        
        assert len(judge_events) == 1, f"Expected 1 judge event, got {len(judge_events)}: {judge_events}. All events: {captured_events}"
        assert judge_events[0]["data"]["phase"] == "pre"
        
        assert len(policy_events) == 1, f"Expected 1 policy event, got {len(policy_events)}: {policy_events}. All events: {captured_events}"
        assert policy_events[0]["data"]["action"] == "accept"
        
        # Verify no refine action
        refine_events = [e for e in policy_events if e["data"].get("action") == "refine"]
        assert len(refine_events) == 0, "Should not have refine action"
