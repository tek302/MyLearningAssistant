"""LangGraph pipeline for RAG (Retrieval-Augmented Generation)."""

import os
import re
import time
import logging
from typing import TypedDict, Optional, List, Dict, Any
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from ..db.repo import SupabaseRepo
from ..utils.embeddings import create_embeddings
from ..utils.summarization import get_summary_model
from ..rag.judge_schema import JudgeResult
from ..config import (
    get_judge_enabled,
    get_judge_threshold_overall,
    get_judge_threshold_faithfulness,
    get_judge_threshold_coverage
)

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Context limits (matching rag_service.py)
MAX_CONTEXT_CHUNKS = 12
MAX_CONTEXT_CHARS = 12000
MAX_QUOTE_LENGTH = 240

# Module-level singleton repo (reduce repeated object creation)
_REPO: Optional[SupabaseRepo] = None

# Module-level cached OpenAI client (reduce repeated object creation)
_OPENAI_CLIENT: Optional[Any] = None


def _get_repo() -> SupabaseRepo:
    """Get or create module-level SupabaseRepo singleton."""
    global _REPO
    if _REPO is None:
        _REPO = SupabaseRepo()
    return _REPO


def _get_openai_client():
    """Get or create module-level OpenAI client singleton."""
    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is None:
        if not HAS_OPENAI:
            raise ValueError("OpenAI package is not installed. Install with: pip install openai")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        _OPENAI_CLIENT = OpenAI(api_key=api_key)
    return _OPENAI_CLIENT


class RAGState(TypedDict, total=False):
    """State for the RAG graph."""
    user_id: str
    query: str
    top_k: int
    document_id: Optional[str]  # Optional document scope (source_id); restricts retrieval to this source
    topic: Optional[str]
    lang: Optional[str]
    query_vec: Optional[List[float]]
    retrieved_chunks: List[Dict[str, Any]]
    context_text: str
    included_chunks: List[tuple]  # List of (chunk_dict, chunk_text_used) tuples
    answer: str
    citations: List[Dict[str, Any]]
    run_id: Optional[str]
    started_at: float
    latency_ms: int
    model: str
    user_requested_top_k: int  # Original user-requested top_k (before clamping)
    attempt: int  # Current LLM attempt number (starts at 1)
    max_attempts: int  # Maximum number of LLM attempts (default 2)
    eval_passed: bool  # Whether evaluation passed
    eval_reasons: List[str]  # List of evaluation failure reasons
    fallback_used: bool  # Whether fallback answer was used
    cannot_answer: bool  # Whether answer is a cannot-answer/fallback response
    # Week4.2/4.3: Judge fields
    judge_enabled: bool  # Whether LLM judge is enabled
    judge_threshold_overall: float  # Overall score threshold (default 0.75)
    judge_threshold_faithfulness: float  # Faithfulness threshold (default 0.80)
    judge_threshold_coverage: float  # Coverage threshold (default 0.70)
    judge: Optional[JudgeResult]  # Judge evaluation result
    judge_phase: Optional[str]  # Judge phase: "pre" or "post"
    judge_run_count: int  # Number of times judge has run (1=pre, 2=post)
    # Week4.4: Refine fields
    refine_used: bool  # Whether refine loop was used
    refine_strategy: Optional[str]  # Refine strategy: "expand_k" | "rewrite_query"
    k_current: Optional[int]  # Current retrieval k value (initialized from top_k)
    query_current: Optional[str]  # Current query (initialized from query, may be rewritten)
    refine_info: Optional[Dict[str, Any]]  # Refine persistence info: strategy, k_before, k_after, rewrite_applied, query_hash
    pre_judge: Optional[JudgeResult]  # First judge result (pre-refine) for metrics


def _normalize_embedding(embedding) -> List[float]:
    """
    Normalize embedding output to a plain Python list[float].
    
    Args:
        embedding: Embedding vector (may be list, numpy array, etc.)
        
    Returns:
        list[float]: Normalized embedding as plain Python list
        
    Raises:
        ValueError: If embedding is not a 1-D numeric sequence
    """
    # Try .tolist() if available (numpy arrays, etc.)
    if hasattr(embedding, 'tolist'):
        try:
            result = embedding.tolist()
            if isinstance(result, list) and all(isinstance(x, (int, float)) for x in result):
                return [float(x) for x in result]
        except Exception:
            pass
    
    # If already a list, validate and convert
    if isinstance(embedding, (list, tuple)):
        try:
            return [float(x) for x in embedding]
        except (ValueError, TypeError):
            pass
    
    raise ValueError(f"Embedding must be a 1-D numeric sequence, got {type(embedding)}")


def _log_run_start(
    repo: SupabaseRepo,
    user_id: str,
    query: str,
    top_k: int,
    topic: Optional[str],
    lang: Optional[str]
) -> Optional[str]:
    """Log RAG run start. Returns run_id if logging succeeds, None otherwise."""
    try:
        with repo._get_connection() as conn:
            with conn.cursor() as cur:
                # Check if rag_runs table exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = 'rag_runs'
                    )
                """)
                if not cur.fetchone()[0]:
                    logger.info("rag_runs table does not exist, skipping DB logging")
                    return None
                
                # Insert run record
                user_uuid = repo._get_or_create_user_id(user_id)
                cur.execute("""
                    INSERT INTO rag_runs (user_id, query, top_k, topic, lang, status)
                    VALUES (%s, %s, %s, %s, %s, 'running')
                    RETURNING id
                """, (user_uuid, query, top_k, topic, lang))
                run_id = str(cur.fetchone()[0])
                conn.commit()
                return run_id
    except Exception as e:
        logger.warning(f"Failed to log run start: {str(e)}")
        return None


def _log_event(repo: SupabaseRepo, run_id: Optional[str], event_type: str, data: Dict[str, Any]):
    """Log RAG event. Silently fails if table doesn't exist."""
    if not run_id:
        return
    
    try:
        import psycopg.types.json
        with repo._get_connection() as conn:
            with conn.cursor() as cur:
                # Check if rag_events table exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = 'rag_events'
                    )
                """)
                if not cur.fetchone()[0]:
                    logger.debug("rag_events table does not exist, skipping event logging")
                    return
                
                # Insert event
                cur.execute("""
                    INSERT INTO rag_events (run_id, event_type, data)
                    VALUES (%s, %s, %s)
                """, (run_id, event_type, psycopg.types.json.Jsonb(data)))
                conn.commit()
    except Exception as e:
        logger.debug(f"Failed to log event: {str(e)}")


def _log_run_complete(repo: SupabaseRepo, run_id: Optional[str], latency_ms: int):
    """Log RAG run completion."""
    if not run_id:
        return
    
    try:
        with repo._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE rag_runs 
                    SET status = 'completed', latency_ms = %s, completed_at = NOW()
                    WHERE id = %s
                """, (latency_ms, run_id))
                conn.commit()
    except Exception as e:
        logger.warning(f"Failed to log run completion: {str(e)}")


def _log_run_error(repo: SupabaseRepo, run_id: Optional[str], error_msg: str):
    """Log RAG run error."""
    if not run_id:
        return
    
    try:
        with repo._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE rag_runs 
                    SET status = 'error', error_message = %s, completed_at = NOW()
                    WHERE id = %s
                """, (error_msg[:500], run_id))  # Limit error message length
                conn.commit()
    except Exception as e:
        logger.warning(f"Failed to log run error: {str(e)}")


def node_start_run(state: RAGState) -> RAGState:
    """
    Start RAG run: log run start, store run_id and started_at.
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with run_id and started_at
    """
    repo = _get_repo()
    user_id = state["user_id"]
    query = state["query"]
    
    # Read originally requested value BEFORE clamping
    requested_top_k = int(state.get("top_k", 8))
    
    # Clamp top_k for safety (do not rely only on request validation)
    clamped_top_k = min(max(requested_top_k, 1), 20)
    
    topic = state.get("topic")
    lang = state.get("lang")
    
    # Log run start (use clamped value for logging)
    run_id = _log_run_start(repo, user_id, query, clamped_top_k, topic, lang)
    started_at = time.time()
    
    # Initialize retry/eval fields
    attempt = state.get("attempt", 1)
    max_attempts = state.get("max_attempts", 2)
    
    # Initialize judge fields with safe defaults
    judge_enabled = state.get("judge_enabled", get_judge_enabled())
    judge_threshold_overall = state.get("judge_threshold_overall", get_judge_threshold_overall())
    judge_threshold_faithfulness = state.get("judge_threshold_faithfulness", get_judge_threshold_faithfulness())
    judge_threshold_coverage = state.get("judge_threshold_coverage", get_judge_threshold_coverage())
    
    # Initialize refine fields with safe defaults
    refine_used = state.get("refine_used", False)
    refine_strategy = state.get("refine_strategy")
    k_current = state.get("k_current", clamped_top_k)  # Initialize from clamped top_k
    query_current = state.get("query_current", query)  # Initialize from incoming query
    refine_info = state.get("refine_info")
    
    # Initialize pre_judge for metrics (stored by judge node on first run)
    pre_judge = state.get("pre_judge", None)
    
    return {
        **state,
        "top_k": clamped_top_k,  # Store clamped value for actual work
        "user_requested_top_k": requested_top_k,  # Store original requested value
        "run_id": run_id,
        "started_at": started_at,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "eval_passed": False,
        "eval_reasons": [],
        "fallback_used": False,
        "cannot_answer": False,
        # Week4.2/4.3: Initialize judge fields
        "judge_enabled": judge_enabled,
        "judge_threshold_overall": judge_threshold_overall,
        "judge_threshold_faithfulness": judge_threshold_faithfulness,
        "judge_threshold_coverage": judge_threshold_coverage,
        "judge": None,
        "judge_phase": None,
        "judge_run_count": 0,  # Week4.4: Track judge run count
        # Week4.4: Initialize refine fields
        "refine_used": refine_used,
        "refine_strategy": refine_strategy,
        "k_current": k_current,
        "query_current": query_current,
        "refine_info": refine_info,
        "pre_judge": pre_judge
    }


def node_embed_query(state: RAGState) -> RAGState:
    """
    Embed query: create embeddings and normalize to list[float].
    
    Uses query_current if available (for refine path), otherwise uses query.
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with query_vec
    """
    try:
        # Use query_current if available (refine path), otherwise use original query
        query = state.get("query_current") or state["query"]
        
        logger.info(f"Embedding query for user {state['user_id']}")
        query_embeddings = create_embeddings([query], max_retries=2)
        query_vec_raw = query_embeddings[0]
        # Normalize to plain Python list[float]
        query_vec = _normalize_embedding(query_vec_raw)
        
        return {
            **state,
            "query_vec": query_vec
        }
    except Exception as e:
        # Log error best-effort
        _log_run_error(_get_repo(), state.get("run_id"), str(e))
        raise


def _is_contribution_query(query: str) -> bool:
    """True if query mentions contribution-style keywords."""
    q = (query or "").lower()
    return any(kw in q for kw in ("contribution", "contributions", "main contributions", "key contributions"))


def _get_retrieval_k(k_to_use: int, query: str) -> int:
    """Retrieval k: boost to 16-20 for contribution queries."""
    if _is_contribution_query(query):
        return min(max(k_to_use, 16), 20)
    return min(k_to_use, MAX_CONTEXT_CHUNKS)


def node_retrieve_chunks(state: RAGState) -> RAGState:
    """
    Retrieve similar chunks: search using pgvector with clamped k.
    Contribution-style queries get retrieval_k boost and optional fallback retrieval.
    
    Uses k_current if available (for refine path), otherwise uses top_k.
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with retrieved_chunks
    """
    try:
        repo = _get_repo()
        user_id = state["user_id"]
        query_vec = state["query_vec"]
        query = state.get("query_current") or state["query"]
        # Use k_current if available (refine path), otherwise use top_k
        k_to_use = state.get("k_current")
        if k_to_use is None:
            k_to_use = state["top_k"]  # Use clamped value
        topic = state.get("topic")
        lang = state.get("lang")
        source_id = state.get("document_id")
        
        retrieval_k = _get_retrieval_k(k_to_use, query)
        logger.info(f"Retrieving top {retrieval_k} chunks for user {user_id}" + (f" (source_id={source_id})" if source_id else ""))
        
        chunks = repo.search_similar_chunks(
            user_id=user_id,
            query_vec=query_vec,
            k=retrieval_k,
            topic=topic,
            lang=lang,
            source_id=source_id,
        )
        
        # Fallback: if contribution query but chunks lack "contribution", retry with " contributions"
        if chunks and _is_contribution_query(query):
            ctx_lower = "".join(_chunk_text(ch) for ch in chunks).lower()
            if "contribution" not in ctx_lower:
                fallback_query = query.strip() + " contributions"
                fallback_vecs = create_embeddings([fallback_query], max_retries=2)
                fallback_vec = _normalize_embedding(fallback_vecs[0])
                fallback_chunks = repo.search_similar_chunks(
                    user_id=user_id, query_vec=fallback_vec, k=16, topic=topic, lang=lang, source_id=source_id
                )
                # Merge by chunk_id, keep best similarity_score
                by_id: Dict[Any, Dict] = {ch["chunk_id"]: ch for ch in chunks}
                for ch in fallback_chunks:
                    cid = ch["chunk_id"]
                    score = ch.get("similarity_score") or 0.0
                    if cid not in by_id or (by_id[cid].get("similarity_score") or 0.0) < score:
                        by_id[cid] = ch
                chunks = sorted(by_id.values(), key=lambda c: -(c.get("similarity_score") or 0.0))
                logger.info(f"Fallback retrieval merged to {len(chunks)} chunks")
        
        # Log retrieval event
        _log_event(repo, state.get("run_id"), "retrieve", {"chunks_found": len(chunks)})
        
        return {
            **state,
            "retrieved_chunks": chunks
        }
    except Exception as e:
        # Log error best-effort
        _log_run_error(_get_repo(), state.get("run_id"), str(e))
        raise


def _chunk_text(ch: Dict[str, Any]) -> str:
    """Extract text from chunk; compatible with chunk_text or text keys."""
    return ch.get("chunk_text") or ch.get("text") or ""


def _chunk_ord(ch: Dict[str, Any]):
    """Extract ord from chunk; compatible with chunk_ord or ord keys."""
    o = ch.get("chunk_ord")
    return o if o is not None else ch.get("ord")


def _chunk_id(ch: Dict[str, Any]) -> str:
    """Extract chunk_id; compatible with chunk_id or id keys."""
    cid = ch.get("chunk_id") or ch.get("id")
    return str(cid) if cid is not None else ""


def node_build_context(state: RAGState) -> RAGState:
    """
    Build context: apply MAX_CONTEXT_CHUNKS and MAX_CONTEXT_CHARS limits.
    Compatible with repo keys: chunk_text, chunk_ord, chunk_id, source_id, url, title, similarity_score.
    """
    try:
        chunks = state["retrieved_chunks"]

        # Filter: include only chunks with non-empty text
        eligible = [(ch, _chunk_text(ch)) for ch in chunks if _chunk_text(ch).strip()]
        context_chunks = eligible[:MAX_CONTEXT_CHUNKS]

        logger.info(
            "build_context retrieved=%s included=%s first_chunk_keys=%s",
            len(chunks),
            len(context_chunks),
            sorted(chunks[0].keys()) if chunks else [],
        )

        context_parts = []
        included_chunks = []
        total_chars = 0

        for chunk, chunk_text in context_chunks:
            chunk_len = len(chunk_text)

            if total_chars + chunk_len > MAX_CONTEXT_CHARS:
                remaining = MAX_CONTEXT_CHARS - total_chars
                if remaining > 100:
                    truncated_text = chunk_text[:remaining]
                    last_space = truncated_text.rfind(" ")
                    if last_space > remaining * 0.8:
                        truncated_text = truncated_text[:last_space]
                    context_parts.append(truncated_text)
                    included_chunks.append((chunk, truncated_text))
                break

            context_parts.append(chunk_text)
            included_chunks.append((chunk, chunk_text))
            total_chars += chunk_len

        context_text = "\n\n---\n\n".join(context_parts)
        if len(context_text) > MAX_CONTEXT_CHARS:
            context_text = context_text[:MAX_CONTEXT_CHARS]
            if included_chunks:
                included_chunks.pop()

        return {
            **state,
            "context_text": context_text,
            "included_chunks": included_chunks
        }
    except Exception as e:
        _log_run_error(_get_repo(), state.get("run_id"), str(e))
        raise


def node_synthesize_answer(state: RAGState) -> RAGState:
    """
    Synthesize answer: call OpenAI LLM, ensure citation markers.
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with answer
    """
    try:
        query = state["query"]
        context_text = state["context_text"]
        num_chunks = len(state["included_chunks"])
        model = get_summary_model()
        
        client = _get_openai_client()
        
        # Build prompt with citation markers and hallucination prevention
        prompt = f"""You are a helpful assistant that answers questions based on the provided context.

Context (from {num_chunks} document chunks):
{context_text}

Question: {query}

Instructions:
1. Answer the question based ONLY on the context provided. Do not use any external knowledge or make assumptions.
2. When referencing information from the context, use citation markers [1], [2], [3], etc. in your answer.
3. The citations correspond to the chunks in order (first chunk is [1], second is [2], etc.).
4. Be concise but comprehensive.
5. CRITICAL: If the context doesn't contain enough information to answer the question, you MUST say so clearly. Do not guess or make up information.
6. CRITICAL: Do not include citation markers for information that is not in the context. Only cite what you actually see in the provided context.
7. If you cannot answer the question based on the context, respond with: "I cannot answer this question based on the provided context."

Answer:"""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that provides accurate answers with proper citations."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        
        answer_text = response.choices[0].message.content.strip()
        
        # Improve citation marker reliability
        # Check if answer contains citation markers [1], [2], etc.
        has_markers = bool(re.search(r'\[\d+\]', answer_text))
        
        # If citations are non-empty but answer has no markers, append suffix
        if state["included_chunks"] and not has_markers:
            num_citations = len(state["included_chunks"])
            marker_suffix = " Sources: " + "".join(f"[{i}]" for i in range(1, num_citations + 1))
            answer_text = answer_text + marker_suffix
        
        # Check if answer is cannot-answer and propagate to state
        cannot_answer = _is_cannot_answer(answer_text)
        
        # Log synthesis event
        attempt = state.get("attempt", 1)
        _log_event(_get_repo(), state.get("run_id"), "synthesize", {"answer_length": len(answer_text), "attempt": attempt})
        
        return {
            **state,
            "answer": answer_text,
            "model": model,
            "cannot_answer": cannot_answer
        }
        
    except Exception as e:
        # Log error best-effort
        _log_run_error(_get_repo(), state.get("run_id"), str(e))
        raise RuntimeError(f"Failed to synthesize answer: {str(e)}")


def _is_cannot_answer(answer: str) -> bool:
    """
    Check if answer is a cannot-answer/fallback response.
    
    Args:
        answer: Answer text to check
        
    Returns:
        True if answer matches cannot-answer pattern
    """
    fallback = "I cannot answer this question based on the provided context."
    a = (answer or "").strip().lower()
    return a == fallback.lower() or ("cannot answer" in a and "provided context" in a)


def node_eval_answer(state: RAGState) -> RAGState:
    """
    Evaluate answer using rule-based checks.
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with eval_passed and eval_reasons
    """
    try:
        answer = state.get("answer", "").strip()
        included_chunks = state.get("included_chunks", [])
        attempt = state.get("attempt", 1)
        N = len(included_chunks)
        
        eval_passed = True
        eval_reasons = []
        
        # Preserve cannot_answer from state if already set (don't overwrite True)
        cannot_answer = state.get("cannot_answer")
        if cannot_answer is None:
            # Compute if not already set
            cannot_answer = _is_cannot_answer(answer)
        cannot_answer = bool(cannot_answer)
        
        # Check if answer is empty
        if not answer:
            eval_passed = False
            eval_reasons.append("empty_answer")
            # Early return if empty
            _log_event(
                _get_repo(),
                state.get("run_id"),
                "eval",
                {
                    "passed": False,
                    "reasons": eval_reasons,
                    "attempt": attempt,
                    "n": N,
                    "cannot_answer": cannot_answer
                }
            )
            return {
                **state,
                "eval_passed": False,
                "eval_reasons": eval_reasons,
                "cannot_answer": cannot_answer
            }
        
        # If cannot_answer is True, treat as valid completion (pass eval, skip other checks)
        if cannot_answer:
            eval_passed = True
            eval_reasons = []  # Clear reasons since this is a valid response
        else:
            # Check if answer is too short
            if len(answer) < 20:
                eval_passed = False
                eval_reasons.append("too_short")
            
            # If we have citations, check citation markers
            if N > 0:
                # Check for citation markers
                marker_pattern = r'\[(\d+)\]'
                markers = re.findall(marker_pattern, answer)
                
                if not markers:
                    eval_passed = False
                    eval_reasons.append("missing_markers")
                else:
                    # Check if all markers are within valid range [1..N]
                    marker_ints = [int(m) for m in markers]
                    invalid_markers = [m for m in marker_ints if m < 1 or m > N]
                    if invalid_markers:
                        eval_passed = False
                        eval_reasons.append("marker_out_of_range")
        
        # Log evaluation event
        _log_event(
            _get_repo(),
            state.get("run_id"),
            "eval",
            {
                "passed": eval_passed,
                "reasons": eval_reasons,
                "attempt": attempt,
                "n": N,
                "cannot_answer": cannot_answer
            }
        )
        
        return {
            **state,
            "eval_passed": eval_passed,
            "eval_reasons": eval_reasons,
            "cannot_answer": cannot_answer
        }
    except Exception as e:
        # Log error best-effort
        _log_run_error(_get_repo(), state.get("run_id"), str(e))
        # On eval error, fail evaluation but preserve cannot_answer from state
        return {
            **state,
            "eval_passed": False,
            "eval_reasons": ["eval_error"],
            "cannot_answer": bool(state.get("cannot_answer", False))
        }


def node_retry_synthesize(state: RAGState) -> RAGState:
    """
    Retry synthesis with stricter settings.
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with new answer and incremented attempt
    """
    try:
        query = state["query"]
        context_text = state["context_text"]
        num_chunks = len(state["included_chunks"])
        model = get_summary_model()
        attempt = state.get("attempt", 1)
        eval_reasons = state.get("eval_reasons", [])
        
        # Increment attempt
        new_attempt = attempt + 1
        
        client = _get_openai_client()
        
        # Build stricter prompt with emphasis on citation markers
        prompt = f"""You are a helpful assistant that answers questions based on the provided context.

Context (from {num_chunks} document chunks):
{context_text}

Question: {query}

Instructions:
1. Answer the question based ONLY on the context provided. Do not use any external knowledge or make assumptions.
2. CRITICAL: You MUST include citation markers [1], [2], [3], etc. in your answer when referencing information from the context.
3. The citations correspond to the chunks in order (first chunk is [1], second is [2], etc., up to [{num_chunks}]).
4. Rewrite to include correct citation markers [1]..[{num_chunks}]. If not possible, say "I cannot answer this question based on the provided context."
5. Be concise but comprehensive.
6. CRITICAL: If the context doesn't contain enough information to answer the question, you MUST say so clearly. Do not guess or make up information.
7. CRITICAL: Do not include citation markers for information that is not in the context. Only cite what you actually see in the provided context.

Answer:"""
        
        # Use stricter settings: temperature=0.0, lower max_tokens
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that provides accurate answers with proper citations. Always include citation markers [1], [2], etc. when referencing the context."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,  # Stricter: deterministic
            max_tokens=800  # Slightly lower
        )
        
        answer_text = response.choices[0].message.content.strip()
        
        # Improve citation marker reliability
        has_markers = bool(re.search(r'\[\d+\]', answer_text))
        
        # If citations are non-empty but answer has no markers, append suffix
        if state["included_chunks"] and not has_markers:
            num_citations = len(state["included_chunks"])
            marker_suffix = " Sources: " + "".join(f"[{i}]" for i in range(1, num_citations + 1))
            answer_text = answer_text + marker_suffix
        
        # Check if answer is cannot-answer and propagate to state
        cannot_answer = _is_cannot_answer(answer_text)
        
        # Log retry event
        _log_event(
            _get_repo(),
            state.get("run_id"),
            "retry",
            {
                "attempt": new_attempt,
                "reasons": eval_reasons
            }
        )
        
        # Log synthesis event
        _log_event(_get_repo(), state.get("run_id"), "synthesize", {"answer_length": len(answer_text), "attempt": new_attempt})
        
        return {
            **state,
            "answer": answer_text,
            "attempt": new_attempt,
            "model": model,
            "cannot_answer": cannot_answer
        }
        
    except Exception as e:
        # Log error best-effort
        _log_run_error(_get_repo(), state.get("run_id"), str(e))
        raise RuntimeError(f"Failed to retry synthesis: {str(e)}")




def node_fallback_answer(state: RAGState) -> RAGState:
    """
    Generate fallback answer when retry budget is exhausted.
    
    Policy: Always return "I cannot answer..." message with citations=[].
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with fallback answer and empty citations
    """
    eval_reasons = state.get("eval_reasons", [])
    attempt = state.get("attempt", 1)
    
    # Log fallback event
    _log_event(
        _get_repo(),
        state.get("run_id"),
        "fallback",
        {
            "reasons": eval_reasons,
            "attempt": attempt
        }
    )
    
    # Policy: Always return cannot-answer message with empty citations
    fallback_answer_text = "I cannot answer this question based on the provided context."
    
    return {
        **state,
        "answer": fallback_answer_text,
        "citations": [],  # Always empty per policy
        "fallback_used": True,
        "cannot_answer": True
    }


def node_format_citations(state: RAGState) -> RAGState:
    """
    Format citations: quote <=240, use chunk_text_used if truncated.
    
    Policy: Clear citations if answer is cannot-answer/fallback.
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with citations (empty if cannot_answer is True)
    """
    try:
        # Policy: Clear citations if answer is cannot-answer/fallback
        cannot_answer = state.get("cannot_answer", False)
        answer = state.get("answer", "")
        if cannot_answer or _is_cannot_answer(answer):
            return {
                **state,
                "citations": []
            }
        
        included_chunks = state["included_chunks"]
        
        citations = []
        for idx, (chunk, chunk_text_used) in enumerate(included_chunks, start=1):
            quote_source = chunk_text_used if chunk_text_used else _chunk_text(chunk)
            if len(quote_source) > MAX_QUOTE_LENGTH:
                truncated = quote_source[:MAX_QUOTE_LENGTH]
                last_space = truncated.rfind(" ")
                if last_space > MAX_QUOTE_LENGTH * 0.8:
                    quote = truncated[:last_space] + "..."
                else:
                    quote = quote_source[:MAX_QUOTE_LENGTH - 3] + "..."
            else:
                quote = quote_source
            if len(quote) > MAX_QUOTE_LENGTH:
                quote = quote[:MAX_QUOTE_LENGTH - 3] + "..."

            sid = chunk.get("source_id")
            score_val = chunk.get("similarity_score") or chunk.get("score") or 0.0
            citations.append({
                "citation_number": idx,
                "chunk_id": _chunk_id(chunk),
                "source_id": str(sid) if sid is not None else "",
                "url": chunk.get("url"),
                "title": chunk.get("title"),
                "chunk_index": _chunk_ord(chunk),
                "score": float(score_val),
                "quote": quote
            })
        
        return {
            **state,
            "citations": citations
        }
    except Exception as e:
        # Log error best-effort
        _log_run_error(_get_repo(), state.get("run_id"), str(e))
        raise


def node_finalize_run(state: RAGState) -> RAGState:
    """
    Finalize run: compute latency_ms, log completion, log run metrics, return final state.
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with latency_ms
    """
    try:
        started_at = state["started_at"]
        latency_ms = int((time.time() - started_at) * 1000)
        
        # Log run completion
        _log_run_complete(_get_repo(), state.get("run_id"), latency_ms)
        
        # Compute and log run metrics (for refine effectiveness tracking)
        try:
            from .run_metrics import compute_run_metrics
            metrics = compute_run_metrics(state)
            if metrics:
                _log_event(
                    _get_repo(),
                    state.get("run_id"),
                    "run_metrics",
                    metrics
                )
        except Exception as metrics_error:
            # Log metrics error but don't fail the run
            logging.warning(f"Failed to compute run metrics: {metrics_error}")
        
        return {
            **state,
            "latency_ms": latency_ms
        }
    except Exception as e:
        # Log error best-effort
        _log_run_error(_get_repo(), state.get("run_id"), str(e))
        raise


def node_no_results_finalize(state: RAGState) -> RAGState:
    """
    Finalize run when no chunks found: compute latency_ms, log completion, log run metrics, return no-results answer.
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with no-results answer, empty citations, and latency_ms
    """
    started_at = state["started_at"]
    latency_ms = int((time.time() - started_at) * 1000)
    model = get_summary_model()
    
    # Log run completion to ensure status doesn't remain 'running'
    _log_run_complete(_get_repo(), state.get("run_id"), latency_ms)
    
    # Compute and log run metrics (for refine effectiveness tracking)
    try:
        from .run_metrics import compute_run_metrics
        metrics = compute_run_metrics(state)
        if metrics:
            _log_event(
                _get_repo(),
                state.get("run_id"),
                "run_metrics",
                metrics
            )
    except Exception as metrics_error:
        # Log metrics error but don't fail the run
        logging.warning(f"Failed to compute run metrics: {metrics_error}")
    
    return {
        **state,
        "answer": "I couldn't find any relevant information in your ingested sources to answer this query.",
        "citations": [],
        "latency_ms": latency_ms,
        "model": model
    }


def should_continue(state: RAGState) -> str:
    """
    Conditional routing: check if chunks were retrieved.
    
    Args:
        state: Current graph state
        
    Returns:
        "no_results" if no chunks, "continue" otherwise
    """
    if not state.get("retrieved_chunks"):
        return "no_results"
    return "continue"


def should_continue_after_context(state: RAGState) -> str:
    """
    Conditional routing: check if context was built successfully (non-empty included_chunks).
    
    Args:
        state: Current graph state
        
    Returns:
        "no_results" if context is empty, "continue" otherwise
    """
    included_chunks = state.get("included_chunks", [])
    context_text = state.get("context_text", "").strip()
    
    # If no chunks included or context is empty/whitespace, route to no-results
    if not included_chunks or not context_text:
        return "no_results"
    return "continue"


def should_continue_after_eval(state: RAGState) -> str:
    """
    Conditional routing after evaluation: check if eval passed and retry budget.
    
    Week3 logic: handles retry/fallback when eval fails.
    Cannot_answer handling is done in check_judge_gate, not here.
    
    Args:
        state: Current graph state
        
    Returns:
        "pass" if eval passed, "retry" if should retry, "fallback" if budget exhausted
    """
    eval_passed = state.get("eval_passed", False)
    attempt = state.get("attempt", 1)
    max_attempts = state.get("max_attempts", 2)
    
    if eval_passed:
        return "pass"
    
    # If eval failed, check retry budget (Week3 logic)
    if attempt < max_attempts:
        return "retry"
    else:
        return "fallback"


def should_run_judge_or_accept(state: RAGState) -> str:
    """
    Graph-level gating: decide whether to run judge or go directly to accept.
    
    This function is called ONLY when rule_eval_passed == True.
    
    Returns:
        "judge" if judge should run, "accept" to skip judge and go directly to format_citations
    """
    # If cannot_answer is True, skip judge and accept directly
    if state.get("cannot_answer", False):
        return "accept"
    
    # If judge is disabled, skip judge and accept directly
    judge_enabled = state.get("judge_enabled", False)
    if not judge_enabled:
        return "accept"
    
    # All conditions met: run judge
    return "judge"


def should_route_after_refine_plan(state: RAGState) -> str:
    """
    Conditional routing after refine_plan: decide whether to rewrite query or skip.
    
    Args:
        state: Current graph state
        
    Returns:
        "rewrite" if rewrite_query needed, "skip_rewrite" to skip, "fallback" if refine already used
    """
    refine_used_before = state.get("refine_used", False)
    refine_info = state.get("refine_info", {})
    
    # If refine was already used before refine_plan, route to fallback
    if refine_info.get("skipped") == "already_used":
        return "fallback"
    
    # Check strategy
    refine_strategy = state.get("refine_strategy")
    if refine_strategy == "rewrite_query":
        return "rewrite"
    else:
        # expand_k strategy: skip rewrite, go directly to rerun
        return "skip_rewrite"


def should_route_after_refine_policy(state: RAGState) -> str:
    """
    Conditional routing after second policy_route (post-refine).
    
    Args:
        state: Current graph state
        
    Returns:
        "accept" to finalize, "fallback" if refine/fallback
    """
    # Import here to avoid circular dependency
    from ..rag.nodes.policy import policy_route
    
    action = policy_route(state)
    
    # After refine, if policy says refine again, route to fallback (max one refine)
    if action == "refine":
        return "fallback"
    
    return action


def create_rag_graph() -> StateGraph:
    """Create and compile the RAG graph."""
    # Lazy import to avoid circular dependency
    from ..rag.nodes.judge import judge_answer
    from ..rag.nodes.policy import policy_route
    from ..rag.nodes.refine_plan import refine_plan
    from ..rag.nodes.rewrite_query import rewrite_query
    
    graph = StateGraph(RAGState)
    
    # Add nodes
    graph.add_node("start_run", node_start_run)
    graph.add_node("embed_query", node_embed_query)
    graph.add_node("retrieve_chunks", node_retrieve_chunks)
    graph.add_node("build_context", node_build_context)
    graph.add_node("synthesize_answer", node_synthesize_answer)
    graph.add_node("eval_answer", node_eval_answer)
    graph.add_node("check_judge_gate", lambda state: state)  # No-op node for conditional routing
    graph.add_node("judge_answer", judge_answer)  # Week4.2: LLM judge
    graph.add_node("refine_plan", refine_plan)  # Week4.4: Refine planning
    graph.add_node("rewrite_query", rewrite_query)  # Week4.4: Query rewrite
    graph.add_node("refine_embed_query", node_embed_query)  # Re-run embed after refine
    graph.add_node("refine_retrieve_chunks", node_retrieve_chunks)  # Re-run retrieve after refine
    graph.add_node("refine_build_context", node_build_context)  # Re-run build_context after refine
    graph.add_node("refine_synthesize_answer", node_synthesize_answer)  # Re-run synthesize after refine
    graph.add_node("refine_eval_answer", node_eval_answer)  # Re-run eval after refine
    graph.add_node("refine_check_judge_gate", lambda state: state)  # Check judge gate after refine
    graph.add_node("refine_judge_answer", judge_answer)  # Re-run judge after refine (post phase)
    graph.add_node("retry_synthesize", node_retry_synthesize)
    graph.add_node("fallback_answer", node_fallback_answer)
    graph.add_node("format_citations", node_format_citations)
    graph.add_node("finalize_run", node_finalize_run)
    graph.add_node("no_results_finalize", node_no_results_finalize)
    
    # Set entry point
    graph.set_entry_point("start_run")
    
    # Add edges
    graph.add_edge("start_run", "embed_query")
    graph.add_edge("embed_query", "retrieve_chunks")
    
    # Conditional routing after retrieve_chunks
    graph.add_conditional_edges(
        "retrieve_chunks",
        should_continue,
        {
            "no_results": "no_results_finalize",
            "continue": "build_context"
        }
    )
    
    # Conditional routing after build_context (avoid LLM call when context is empty)
    graph.add_conditional_edges(
        "build_context",
        should_continue_after_context,
        {
            "no_results": "no_results_finalize",
            "continue": "synthesize_answer"
        }
    )
    
    # After synthesis, evaluate answer
    graph.add_edge("synthesize_answer", "eval_answer")
    
    # Conditional routing after eval_answer (Week3 logic: retry/fallback)
    graph.add_conditional_edges(
        "eval_answer",
        should_continue_after_eval,
        {
            "pass": "check_judge_gate",  # If eval passed, check if judge should run
            "retry": "retry_synthesize",
            "fallback": "fallback_answer"
        }
    )
    
    # Graph-level gating: decide judge vs accept (called ONLY when eval passed)
    graph.add_conditional_edges(
        "check_judge_gate",
        should_run_judge_or_accept,
        {
            "judge": "judge_answer",  # Run judge
            "accept": "format_citations"  # Skip judge, go directly to accept
        }
    )
    
    # Week4.3: After judge_answer, route based on policy
    graph.add_conditional_edges(
        "judge_answer",
        policy_route,
        {
            "accept": "format_citations",
            "refine": "refine_plan"  # Week4.4: Route to refine_plan instead of placeholder
        }
    )
    
    # Week4.4: After refine_plan, route based on strategy
    graph.add_conditional_edges(
        "refine_plan",
        should_route_after_refine_plan,
        {
            "rewrite": "rewrite_query",
            "skip_rewrite": "refine_embed_query",  # expand_k: skip rewrite, go to rerun
            "fallback": "fallback_answer"  # Already used refine, go to fallback
        }
    )
    
    # Week4.4: After rewrite_query, go to rerun pipeline
    graph.add_edge("rewrite_query", "refine_embed_query")
    
    # Week4.4: Re-run pipeline after refine (using query_current and k_current)
    graph.add_edge("refine_embed_query", "refine_retrieve_chunks")
    
    # Conditional routing after refine_retrieve_chunks
    graph.add_conditional_edges(
        "refine_retrieve_chunks",
        should_continue,
        {
            "no_results": "no_results_finalize",
            "continue": "refine_build_context"
        }
    )
    
    # Conditional routing after refine_build_context
    graph.add_conditional_edges(
        "refine_build_context",
        should_continue_after_context,
        {
            "no_results": "no_results_finalize",
            "continue": "refine_synthesize_answer"
        }
    )
    
    # After refine synthesis, evaluate answer
    graph.add_edge("refine_synthesize_answer", "refine_eval_answer")
    
    # Conditional routing after refine_eval_answer (Week3 logic: retry/fallback)
    graph.add_conditional_edges(
        "refine_eval_answer",
        should_continue_after_eval,
        {
            "pass": "refine_check_judge_gate",  # If eval passed, check if judge should run
            "retry": "retry_synthesize",  # Week3 retry logic still applies
            "fallback": "fallback_answer"
        }
    )
    
    # Graph-level gating after refine: decide judge vs accept
    graph.add_conditional_edges(
        "refine_check_judge_gate",
        should_run_judge_or_accept,
        {
            "judge": "refine_judge_answer",  # Run judge (post phase)
            "accept": "format_citations"  # Skip judge, go directly to accept
        }
    )
    
    # Week4.4: After refine_judge_answer, route based on second policy_route
    graph.add_conditional_edges(
        "refine_judge_answer",
        should_route_after_refine_policy,
        {
            "accept": "format_citations",
            "fallback": "fallback_answer"  # If refine again or fallback, go to fallback
        }
    )
    
    # Retry loop: retry_synthesize -> eval_answer
    graph.add_edge("retry_synthesize", "eval_answer")
    
    # Fallback path: fallback_answer -> finalize_run
    graph.add_edge("fallback_answer", "finalize_run")
    
    # Normal flow (when eval passes)
    graph.add_edge("format_citations", "finalize_run")
    graph.add_edge("finalize_run", END)
    
    # No results flow
    graph.add_edge("no_results_finalize", END)
    
    # Compile and return
    return graph.compile()


# Lazy singleton cache for the compiled graph
_GRAPH_CACHE = None


def get_rag_graph(reset: bool = False):
    """
    Get the compiled RAG graph instance (lazy singleton).
    
    In production, this returns a cached graph instance for performance.
    In tests, set reset=True to create a fresh graph after monkeypatching.
    
    Args:
        reset: If True, force creation of a new graph instance (for tests)
        
    Returns:
        Compiled RAG graph instance
    """
    global _GRAPH_CACHE
    if reset or _GRAPH_CACHE is None:
        _GRAPH_CACHE = create_rag_graph()
    return _GRAPH_CACHE


# Backward compatibility: export rag_graph for existing code
# Production code should use get_rag_graph() instead
rag_graph = None  # Will be lazily initialized on first access via get_rag_graph()

