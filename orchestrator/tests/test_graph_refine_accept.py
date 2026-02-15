"""Integration test for refine loop: pre low -> refine -> post high -> accept (Part 6B)."""

import os
import pytest
import json
from unittest.mock import patch, MagicMock
from app.graphs.rag_graph import get_rag_graph


@pytest.fixture
def mock_judge_low_scores():
    """Mock judge LLM response with low scores that trigger refine (pre phase)."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "faithfulness": 0.70,
        "coverage": 0.50,  # Low coverage to trigger expand_k
        "citation_correctness": 0.60,
        "overall": 0.60,  # Below 0.75 threshold
        "reasons": ["Low coverage", "Needs more context"]
    })
    return mock_response


@pytest.fixture
def mock_judge_high_scores():
    """Mock judge LLM response with high scores that pass thresholds (post phase)."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "faithfulness": 0.85,
        "coverage": 0.80,  # Improved after expand_k
        "citation_correctness": 0.90,
        "overall": 0.86,  # Above 0.75 threshold
        "reasons": ["Good answer", "Well cited"]
    })
    return mock_response


@pytest.fixture
def mock_synthesis_response():
    """Mock synthesis LLM response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "LangGraph is a library for building agent workflows [1]."
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
        },
        {
            "chunk_id": "3",
            "source_id": "source-1",
            "chunk_index": 2,
            "chunk_text": "Refine loops improve answer quality by expanding context.",
            "url": "https://example.com/refine",
            "title": "Refine Loop",
            "score": 0.85
        },
        {
            "chunk_id": "4",
            "source_id": "source-1",
            "chunk_index": 3,
            "chunk_text": "Policy routing decides whether to accept, refine, or fallback.",
            "url": "https://example.com/policy",
            "title": "Policy Routing",
            "score": 0.80
        }
    ]


def test_refine_loop_accept_path(mock_judge_low_scores, mock_judge_high_scores, mock_synthesis_response, fixed_chunks):
    """Test integration: pre low -> refine -> post high -> accept."""
    # Capture events
    captured_events = []
    
    def capture_event(repo, run_id, event_type, data):
        captured_events.append({
            "event_type": event_type,
            "data": data
        })
    
    # Track judge call count to return different scores
    judge_call_count = [0]
    
    def mock_create(*args, **kwargs):
        messages = kwargs.get('messages', [])
        content = str(messages[-1].get('content', '')) if messages else ''
        
        # Judge call detection
        if 'evaluator' in content.lower() or 'evaluate' in content.lower():
            judge_call_count[0] += 1
            # First call (pre): return low scores
            if judge_call_count[0] == 1:
                return mock_judge_low_scores
            # Second call (post): return high scores
            else:
                return mock_judge_high_scores
        # Synthesis call
        return mock_synthesis_response
    
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = mock_create
    
    # Mock embeddings (return fixed embedding vector)
    # This is used by both embed_query and refine_embed_query nodes
    def mock_create_embeddings(texts, max_retries=2):
        return [[0.1] * 1536 for _ in texts]
    
    # Stub embed_query to set query_vec (works for both initial and refine paths)
    def stub_embed_query(state):
        from app.graphs.rag_graph import RAGState
        query = state.get("query_current", state.get("query", ""))
        return {
            **state,
            "query_vec": [0.1] * 1536
        }
    
    # Stub retrieve_chunks to return fixed chunks (more chunks after expand_k)
    # Capture fixed_chunks in closure to ensure it's accessible
    chunks_list = list(fixed_chunks)
    
    def stub_retrieve_chunks(state):
        from app.graphs.rag_graph import RAGState, _get_repo, _log_event
        k = state.get("k_current", state.get("top_k", 8))
        # Return k chunks (or all if k > len(chunks_list))
        if k and k > 0:
            chunks_to_return = chunks_list[:k] if k <= len(chunks_list) else chunks_list
        else:
            chunks_to_return = chunks_list  # Default to all chunks
        # Log retrieve event (matching node_retrieve_chunks behavior)
        _log_event(_get_repo(), state.get("run_id"), "retrieve", {"chunks_found": len(chunks_to_return)})
        return {
            **state,
            "retrieved_chunks": chunks_to_return,
            "query_vec": [0.1] * 1536
        }
    
    # Stub build_context to use fixed chunks (works for both initial and refine paths)
    def stub_build_context(state):
        chunks = state.get("retrieved_chunks", [])
        if not chunks:
            # If no chunks, return empty context (should route to no_results)
            return {
                **state,
                "context_text": "",
                "included_chunks": []
            }
        chunk_texts = [chunk["chunk_text"] for chunk in chunks]
        context_text = "\n\n".join([f"[{i+1}] {text}" for i, text in enumerate(chunk_texts)])
        included_chunks = [
            (chunk, chunk["chunk_text"]) for chunk in chunks
        ]
        return {
            **state,
            "context_text": context_text,
            "included_chunks": included_chunks
        }
    
    # Stub synthesize_answer to return a valid answer (works for both initial and refine paths)
    def stub_synthesize_answer(state):
        # Ensure answer has valid citation markers
        included_chunks = state.get("included_chunks", [])
        if included_chunks:
            citation_marker = "[1]"
        else:
            citation_marker = ""
        return {
            **state,
            "answer": f"LangGraph is a library for building agent workflows {citation_marker}.",
            "model": "gpt-4o-mini",
            "cannot_answer": False
        }
    
    # Stub eval_answer to always pass (prevent retry loops)
    # This ensures both pre and post refine passes never enter Week3 retry loop
    def stub_eval_answer(state):
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
        "top_k": 8,
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
        "user_requested_top_k": 8,
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
        "judge_phase": None,
        "judge_run_count": 0,
        "refine_used": False,
        "refine_strategy": None,
        "k_current": None,
        "query_current": None,
        "refine_info": None
    }
    
    with patch('app.graphs.rag_graph._get_openai_client', return_value=mock_client), \
         patch('app.graphs.rag_graph.create_embeddings', side_effect=mock_create_embeddings), \
         patch('app.graphs.rag_graph.node_embed_query', side_effect=stub_embed_query), \
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
        
        # Run graph with recursion limit for safety
        # Note: refine loop tests may hit recursion limits due to graph complexity
        # This is a known issue and may require graph structure fixes
        try:
            final_state = graph.invoke(initial_state, config={"recursion_limit": 50})
        except Exception as e:
            # If recursion limit hit, provide helpful debugging info
            error_msg = f"Graph hit recursion limit. Events captured: {len(captured_events)}. Last events: {captured_events[-5:]}"
            # Check if we at least got through the refine step
            refine_events = [e for e in captured_events if e["event_type"] == "refine"]
            if len(refine_events) > 0:
                error_msg += f"\nRefine event found: {refine_events[0]}"
            raise AssertionError(error_msg) from e
        
        # Safety assertion: ensure bounded number of events (prevent infinite loops)
        assert len(captured_events) < 20, f"Too many events captured ({len(captured_events)}), possible infinite loop. Events: {captured_events}"
        
        # Assert response is successful (non-fallback)
        assert final_state.get("answer", ""), "Answer should not be empty"
        assert not final_state.get("fallback_used", False), "Should not use fallback when judge accepts after refine"
        
        # Assert events: judge(pre), policy(refine), refine, judge(post), policy(accept)
        judge_events = [e for e in captured_events if e["event_type"] == "judge"]
        policy_events = [e for e in captured_events if e["event_type"] == "policy"]
        refine_events = [e for e in captured_events if e["event_type"] == "refine"]
        
        # Should have 2 judge events (pre and post)
        assert len(judge_events) == 2, f"Expected 2 judge events, got {len(judge_events)}: {judge_events}"
        assert judge_events[0]["data"]["phase"] == "pre", "First judge should be pre phase"
        assert judge_events[1]["data"]["phase"] == "post", "Second judge should be post phase"
        
        # Should have 2 policy events (refine and accept)
        assert len(policy_events) == 2, f"Expected 2 policy events, got {len(policy_events)}: {policy_events}"
        assert policy_events[0]["data"]["action"] == "refine", "First policy should be refine"
        assert policy_events[1]["data"]["action"] == "accept", "Second policy should be accept"
        
        # Should have 1 refine event (expand_k strategy)
        assert len(refine_events) == 1, f"Expected 1 refine event, got {len(refine_events)}: {refine_events}"
        assert refine_events[0]["data"]["strategy"] == "expand_k", "Refine should use expand_k strategy"
        assert refine_events[0]["data"]["k_before"] == 8, "k_before should be 8"
        assert refine_events[0]["data"]["k_after"] == 12, "k_after should be 12 (8 + 4)"
        
        # Verify refine_used is True
        assert final_state.get("refine_used", False), "refine_used should be True"
        assert final_state.get("refine_strategy") == "expand_k", "refine_strategy should be expand_k"
        
        # Verify exactly ONE refine event (max one refine iteration)
        assert len(refine_events) == 1, f"Expected exactly 1 refine event, got {len(refine_events)}: {refine_events}"

