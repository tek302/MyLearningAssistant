"""RAG router for query answering."""

import os
import uuid
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv
from starlette.concurrency import run_in_threadpool

from ..services.rag_service import RAGService
from ..utils.deps import get_user_id

# Load environment variables
load_dotenv()

# Check if LangGraph should be used (default: True)
USE_LANGGRAPH = os.getenv("RAG_USE_LANGGRAPH", "true").lower() == "true"

if USE_LANGGRAPH:
    try:
        from ..graphs.rag_graph import get_rag_graph
        HAS_LANGGRAPH = True
    except ImportError:
        HAS_LANGGRAPH = False
        # Fallback to direct service if graph import fails
        USE_LANGGRAPH = False
else:
    HAS_LANGGRAPH = False

router = APIRouter(prefix="/rag", tags=["rag"])


class RAGAnswerRequest(BaseModel):
    """Request model for RAG answer endpoint."""
    query: str = Field(..., min_length=1, max_length=1000, description="User query")
    top_k: int = Field(default=12, ge=1, le=20, description="Number of chunks to retrieve (1-20)")
    document_id: Optional[str] = Field(default=None, max_length=36, description="Optional document (source) scope; restricts retrieval to this source_id")
    topic: Optional[str] = Field(default=None, max_length=100, description="Optional topic filter")
    lang: Optional[str] = Field(default=None, max_length=10, description="Optional language filter")
    include_citations: bool = Field(default=True, description="If False, response citations list is empty (saves payload)")

    @field_validator("document_id")
    @classmethod
    def document_id_must_be_uuid_if_present(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        try:
            uuid.UUID(v.strip())
            return v.strip()
        except ValueError:
            raise ValueError("document_id must be a valid UUID")


class Citation(BaseModel):
    """Citation model."""
    citation_number: int  # 1-based index matching [1], [2] markers in answer
    chunk_id: str
    source_id: str
    url: Optional[str] = None
    title: Optional[str] = None
    chunk_index: Optional[int] = None
    score: float
    quote: str


class RAGAnswerResponse(BaseModel):
    """Response model for RAG answer endpoint."""
    answer: str
    citations: list[Citation]
    meta: dict


@router.post("/answer", response_model=RAGAnswerResponse)
async def answer_query(
    request: RAGAnswerRequest,
    user_id: Annotated[str, Depends(get_user_id)]
):
    """
    Answer a query using RAG (Retrieval-Augmented Generation).
    
    Retrieves relevant chunks from ingested sources using vector similarity,
    then synthesizes an answer using an LLM with citation markers.
    
    Args:
        request: Request body with query and optional filters
        user_id: User ID from authentication token
        
    Returns:
        RAGAnswerResponse with answer, citations, and metadata
        
    Raises:
        HTTPException: If query processing fails
    """
    # Validate user_id and query (additional check beyond Pydantic)
    if not user_id or not user_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id is required and cannot be empty"
        )
    if not request.query or not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="query is required and cannot be empty"
        )
    
    try:
        if USE_LANGGRAPH and HAS_LANGGRAPH:
            # Use LangGraph pipeline
            initial_state = {
                "user_id": user_id,
                "query": request.query,
                "top_k": request.top_k,  # Original requested value (will be clamped in node_start_run)
                "document_id": request.document_id,
                "topic": request.topic,
                "lang": request.lang,
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
                "user_requested_top_k": request.top_k,
                "attempt": 1,  # Start with first attempt
                "max_attempts": 2,  # Maximum retry attempts
                "eval_passed": False,
                "eval_reasons": [],
                "fallback_used": False,
                "cannot_answer": False
            }
            
            # Execute graph in threadpool to avoid blocking async event loop
            # Error logging handled within graph nodes
            from ..graphs.rag_graph import get_rag_graph, _get_repo, _log_event
            from ..config import get_graph_recursion_limit
            
            graph = get_rag_graph()
            recursion_limit = get_graph_recursion_limit()
            
            # Apply recursion limit guard to prevent runaway loops
            # LangGraph invoke signature: invoke(input, config=None)
            # config is a dict with optional keys like "recursion_limit"
            recursion_limit_hit = False
            try:
                # Use functools.partial or lambda to pass config
                from functools import partial
                invoke_func = partial(graph.invoke, config={"recursion_limit": recursion_limit})
                final_state = await run_in_threadpool(invoke_func, initial_state)
            except Exception as e:
                # Check if this is a recursion limit violation
                error_str = str(e)
                error_type = type(e).__name__
                if "recursion" in error_str.lower() or "GraphRecursionError" in error_type:
                    # Log graph guard event
                    repo = _get_repo()
                    run_id = initial_state.get("run_id")
                    _log_event(
                        repo,
                        run_id,
                        "graph_guard",
                        {
                            "reason": "recursion_limit",
                            "limit": recursion_limit,
                            "partial_state_summary": {
                                "query": initial_state.get("query", "")[:50],
                                "judge_enabled": initial_state.get("judge_enabled", False),
                                "refine_used": initial_state.get("refine_used", False)
                            }
                        }
                    )
                    # Set flag to return fallback response
                    recursion_limit_hit = True
                else:
                    # Re-raise other exceptions
                    raise
            
            # Handle recursion limit fallback
            if recursion_limit_hit:
                result = {
                    "answer": "I cannot answer this question based on the provided context.",
                    "citations": [],
                    "meta": {
                        "impl": "langgraph",
                        "top_k": initial_state.get("top_k", 8),
                        "requested_top_k": initial_state.get("user_requested_top_k", initial_state.get("top_k", 8)),
                        "latency_ms": 0,
                        "model": "",
                        "run_id": initial_state.get("run_id") or str(uuid.uuid4()),
                        "attempts_used": 1,
                        "fallback_used": True,
                        "cannot_answer": True,
                        "error": "graph_execution_limit_exceeded"
                    }
                }
            else:
                # Extract cannot_answer and enforce citations policy as final safety net
                cannot_answer = bool(final_state.get("cannot_answer", False))
                citations = [] if (cannot_answer or not request.include_citations) else final_state["citations"]
                run_id = final_state.get("run_id") or str(uuid.uuid4())
                
                # Build meta
                meta = {
                    "impl": "langgraph",
                    "top_k": final_state["top_k"],
                    "requested_top_k": final_state["user_requested_top_k"],
                    "latency_ms": final_state["latency_ms"],
                    "model": final_state.get("model", ""),
                    "run_id": run_id,
                    "attempts_used": final_state.get("attempt", 1),
                    "fallback_used": bool(final_state.get("fallback_used", False)),
                    "cannot_answer": cannot_answer
                }
                if os.getenv("RAG_DEBUG", "").lower() in ("true", "1", "yes"):
                    ctx = final_state.get("context_text") or ""
                    meta["debug"] = {
                        "context_preview": ctx[:800] + ("..." if len(ctx) > 800 else ""),
                        "context_length": len(ctx),
                        "num_included_chunks": len(final_state.get("included_chunks", [])),
                        "eval_passed": final_state.get("eval_passed"),
                        "eval_reasons": final_state.get("eval_reasons", []),
                    }
                result = {
                    "answer": final_state["answer"],
                    "citations": citations,
                    "meta": meta
                }
        else:
            # Fallback to direct service
            service = RAGService()
            result = service.answer_query(
                user_id=user_id,
                query=request.query,
                top_k=request.top_k,
                document_id=request.document_id,
                topic=request.topic,
                lang=request.lang
            )
            # Add impl and requested_top_k for consistency
            result["meta"]["impl"] = "direct"
            result["meta"]["requested_top_k"] = request.top_k
            result["meta"]["attempts_used"] = result["meta"].get("attempts_used", 1)
            result["meta"]["fallback_used"] = bool(result["meta"].get("fallback_used", False))
            result["meta"]["run_id"] = result["meta"].get("run_id") or str(uuid.uuid4())
            
            # Infer cannot_answer from answer text if not provided by service
            answer = result.get("answer", "")
            cannot_answer = bool(result["meta"].get("cannot_answer", 
                ("cannot answer" in answer.lower() and "provided context" in answer.lower())))
            result["meta"]["cannot_answer"] = cannot_answer
            
            # Enforce citations policy: if cannot_answer or not requested, citations must be []
            if cannot_answer or not request.include_citations:
                result["citations"] = []
        
        return RAGAnswerResponse(
            answer=result["answer"],
            citations=[Citation(**cit) for cit in result["citations"]],
            meta=result["meta"]
        )
        
    except ValueError as e:
        # Bad input (e.g., missing API key)
        # Error logging is handled within graph nodes for LangGraph path
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # Internal error
        # Error logging is handled within graph nodes for LangGraph path
        # Do not leak internal exception details in 500 responses
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to answer query"
        )

