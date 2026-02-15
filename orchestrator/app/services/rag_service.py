"""RAG service for query answering using vector similarity search."""

import os
import re
import time
import logging
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from ..db.repo import SupabaseRepo
from ..utils.embeddings import create_embeddings, get_embedding_model
from ..utils.summarization import get_summary_model

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Context limits
MAX_CONTEXT_CHUNKS = 12
MAX_CONTEXT_CHARS = 12000
MAX_QUOTE_LENGTH = 240


def _is_contribution_query(query: str) -> bool:
    """True if query mentions contribution-style keywords."""
    q = (query or "").lower()
    return any(kw in q for kw in ("contribution", "contributions", "main contributions", "key contributions"))


def _get_retrieval_k(top_k: int, query: str) -> int:
    """Retrieval k: boost to 16-20 for contribution queries."""
    if _is_contribution_query(query):
        return min(max(top_k, 16), 20)
    return min(top_k, MAX_CONTEXT_CHUNKS)


class RAGService:
    """Service for RAG (Retrieval-Augmented Generation) operations."""
    
    def __init__(self, repo: Optional[SupabaseRepo] = None):
        """Initialize RAG service with repository."""
        self.repo = repo or SupabaseRepo()
        self.embedding_model = get_embedding_model()
        self.summary_model = get_summary_model()
    
    def _normalize_embedding(self, embedding) -> List[float]:
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
    
    def answer_query(
        self,
        user_id: str,
        query: str,
        top_k: int = 8,
        topic: Optional[str] = None,
        lang: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Answer a query using RAG.
        
        Args:
            user_id: User identifier
            query: User query string
            top_k: Number of chunks to retrieve (default: 8)
            topic: Optional topic filter
            lang: Optional language filter
            
        Returns:
            Dictionary with answer, citations, and meta
        """
        start_time = time.time()
        run_id = None
        
        try:
            # Clamp top_k for safety (do not rely only on request validation)
            top_k = min(max(int(top_k), 1), 20)
            user_requested_top_k = top_k  # Keep original for meta response
            
            # Log run start
            run_id = self._log_run_start(user_id, query, top_k, topic, lang)
            
            # Step 1: Embed query
            logger.info(f"Embedding query for user {user_id}")
            query_embeddings = create_embeddings([query], max_retries=2)
            query_vec_raw = query_embeddings[0]
            # Normalize to plain Python list[float]
            query_vec = self._normalize_embedding(query_vec_raw)
            
            # Step 2: Retrieve similar chunks
            retrieval_k = _get_retrieval_k(top_k, query)
            logger.info(f"Retrieving top {retrieval_k} chunks for user {user_id}")
            chunks = self.repo.search_similar_chunks(
                user_id=user_id,
                query_vec=query_vec,
                k=retrieval_k,
                topic=topic,
                lang=lang
            )
            
            # Fallback: if contribution query but chunks lack "contribution", retry with " contributions"
            if chunks and _is_contribution_query(query):
                ctx_lower = "".join((ch.get("chunk_text") or ch.get("text") or "") for ch in chunks).lower()
                if "contribution" not in ctx_lower:
                    fallback_query = query.strip() + " contributions"
                    fallback_vecs = create_embeddings([fallback_query], max_retries=2)
                    fallback_vec = self._normalize_embedding(fallback_vecs[0])
                    fallback_chunks = self.repo.search_similar_chunks(
                        user_id=user_id, query_vec=fallback_vec, k=16, topic=topic, lang=lang
                    )
                    by_id = {ch["chunk_id"]: ch for ch in chunks}
                    for ch in fallback_chunks:
                        cid = ch["chunk_id"]
                        score = ch.get("similarity_score") or 0.0
                        if cid not in by_id or (by_id[cid].get("similarity_score") or 0.0) < score:
                            by_id[cid] = ch
                    chunks = sorted(by_id.values(), key=lambda c: -(c.get("similarity_score") or 0.0))
                    logger.info(f"Fallback retrieval merged to {len(chunks)} chunks")
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            if not chunks:
                # Log retrieval event (0 chunks found)
                self._log_event(run_id, "retrieve", {"chunks_found": 0})
                # Record completion to ensure status doesn't remain 'running'
                self._log_run_complete(run_id, latency_ms)
                
                return {
                    "answer": "I couldn't find any relevant information in your ingested sources to answer this query.",
                    "citations": [],
                    "meta": {
                        "top_k": user_requested_top_k,
                        "latency_ms": latency_ms,
                        "model": self.summary_model
                    }
                }
            
            # Log retrieval event
            self._log_event(run_id, "retrieve", {"chunks_found": len(chunks)})
            
            # Step 3: Build context (cap at MAX_CONTEXT_CHUNKS and MAX_CONTEXT_CHARS)
            # Track which chunks are actually included in context
            context_chunks = chunks[:MAX_CONTEXT_CHUNKS]
            context_parts = []
            included_chunks = []  # Track chunks that made it into context
            total_chars = 0
            
            for chunk in context_chunks:
                chunk_text = chunk["chunk_text"]
                chunk_len = len(chunk_text)
                
                if total_chars + chunk_len > MAX_CONTEXT_CHARS:
                    # Truncate last chunk if there's meaningful space left
                    remaining = MAX_CONTEXT_CHARS - total_chars
                    if remaining > 100:  # Only include if meaningful
                        truncated_text = chunk_text[:remaining]
                        # Try to break at word boundary
                        last_space = truncated_text.rfind(" ")
                        if last_space > remaining * 0.8:  # If we can break at a reasonable point
                            truncated_text = truncated_text[:last_space]
                        context_parts.append(truncated_text)
                        # Include truncated chunk in citations
                        included_chunks.append((chunk, truncated_text))
                    break
                
                context_parts.append(chunk_text)
                included_chunks.append((chunk, chunk_text))
                total_chars += chunk_len
            
            # Ensure context doesn't exceed limit (safety check)
            context_text = "\n\n---\n\n".join(context_parts)
            if len(context_text) > MAX_CONTEXT_CHARS:
                context_text = context_text[:MAX_CONTEXT_CHARS]
                # Remove last incomplete chunk from included_chunks if truncated
                if included_chunks:
                    included_chunks.pop()
            
            # Step 4: Synthesize answer with citations
            logger.info(f"Synthesizing answer using {self.summary_model}")
            answer_result = self._synthesize_answer(query, context_text, len(included_chunks))
            
            # Step 5: Format citations (only for chunks actually included in context)
            citations = []
            for idx, (chunk, chunk_text_used) in enumerate(included_chunks, start=1):
                # Generate quote from the actual text used in context (chunk_text_used),
                # not always from the full original chunk text, to avoid mismatches
                quote_source = chunk_text_used if chunk_text_used else chunk["chunk_text"]
                quote = quote_source[:MAX_QUOTE_LENGTH]
                if len(quote_source) > MAX_QUOTE_LENGTH:
                    # Try to break at word boundary
                    last_space = quote.rfind(" ")
                    if last_space > MAX_QUOTE_LENGTH * 0.8:
                        quote = quote[:last_space] + "..."
                    else:
                        quote = quote[:MAX_QUOTE_LENGTH - 3] + "..."
                
                citations.append({
                    "citation_number": idx,  # 1-based index matching [1], [2] in answer
                    "chunk_id": str(chunk["chunk_id"]),
                    "source_id": str(chunk["source_id"]),
                    "url": chunk.get("url"),
                    "title": chunk.get("title"),
                    "chunk_index": chunk.get("chunk_ord"),
                    "score": float(chunk.get("similarity_score", 0.0)),
                    "quote": quote
                })
            
            # Step 6: Improve citation marker reliability
            answer_text = answer_result["answer"]
            # Check if answer contains citation markers [1], [2], etc.
            has_markers = bool(re.search(r'\[\d+\]', answer_text))
            
            # If citations are non-empty but answer has no markers, append suffix
            if citations and not has_markers:
                num_citations = len(citations)
                marker_suffix = " Sources: " + "".join(f"[{i}]" for i in range(1, num_citations + 1))
                answer_text = answer_text + marker_suffix
            
            # Log synthesis event
            self._log_event(run_id, "synthesize", {"answer_length": len(answer_text)})
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Log run completion
            self._log_run_complete(run_id, latency_ms)
            
            return {
                "answer": answer_text,
                "citations": citations,
                "meta": {
                    "top_k": user_requested_top_k,  # Use original user-requested value
                    "latency_ms": latency_ms,
                    "model": self.summary_model
                }
            }
            
        except Exception as e:
            logger.error(f"Error in RAG query: {str(e)}", exc_info=True)
            if run_id:
                self._log_run_error(run_id, str(e))
            raise
    
    def _synthesize_answer(self, query: str, context: str, num_chunks: int) -> Dict[str, Any]:
        """
        Synthesize answer from context using LLM.
        
        Args:
            query: User query
            context: Context text from retrieved chunks
            num_chunks: Number of chunks used
            
        Returns:
            Dictionary with answer text
        """
        if not HAS_OPENAI:
            raise ValueError("OpenAI package is not installed. Install with: pip install openai")
        
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        client = OpenAI(api_key=api_key)
        
        # Build prompt with citation markers and hallucination prevention
        prompt = f"""You are a helpful assistant that answers questions based on the provided context.

Context (from {num_chunks} document chunks):
{context}

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
        
        try:
            response = client.chat.completions.create(
                model=self.summary_model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that provides accurate answers with proper citations."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            answer = response.choices[0].message.content.strip()
            
            return {"answer": answer}
            
        except Exception as e:
            raise RuntimeError(f"Failed to synthesize answer: {str(e)}")
    
    def _log_run_start(
        self,
        user_id: str,
        query: str,
        top_k: int,
        topic: Optional[str],
        lang: Optional[str]
    ) -> Optional[str]:
        """Log RAG run start. Returns run_id if logging succeeds, None otherwise."""
        try:
            with self.repo._get_connection() as conn:
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
                    user_uuid = self.repo._get_or_create_user_id(user_id)
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
    
    def _log_event(self, run_id: Optional[str], event_type: str, data: Dict[str, Any]):
        """Log RAG event. Silently fails if table doesn't exist."""
        if not run_id:
            return
        
        try:
            import psycopg.types.json
            with self.repo._get_connection() as conn:
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
    
    def _log_run_complete(self, run_id: Optional[str], latency_ms: int):
        """Log RAG run completion."""
        if not run_id:
            return
        
        try:
            with self.repo._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE rag_runs 
                        SET status = 'completed', latency_ms = %s, completed_at = NOW()
                        WHERE id = %s
                    """, (latency_ms, run_id))
                    conn.commit()
        except Exception as e:
            logger.warning(f"Failed to log run completion: {str(e)}")
    
    def _log_run_error(self, run_id: Optional[str], error_msg: str):
        """Log RAG run error."""
        if not run_id:
            return
        
        try:
            with self.repo._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE rag_runs 
                        SET status = 'error', error_message = %s, completed_at = NOW()
                        WHERE id = %s
                    """, (error_msg[:500], run_id))  # Limit error message length
                    conn.commit()
        except Exception as e:
            logger.warning(f"Failed to log run error: {str(e)}")

