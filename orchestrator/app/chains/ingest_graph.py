from typing import TypedDict
from langgraph.graph import StateGraph, END
from ..utils.web_fetch import fetch_url_text
from ..utils.chunking import chunk_text
from ..utils.embeddings import create_embeddings
from ..utils.summarization import create_s1_summary, get_s1_max_chunks, get_summary_model
from ..db.repo import SupabaseRepo


class IngestState(TypedDict):
    """State for the ingest graph."""
    user_id: str
    url: str
    title: str
    lang: str
    text: str
    source_id: str
    chunk_count: int
    embedding_count: int
    summary_id: str
    tldr: str
    bullets_count: int
    content_type: str
    pages_used: int
    meta: dict


def node_fetch(state: IngestState) -> IngestState:
    """
    Fetch URL and extract text content.
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with url, title, text, lang, meta
    """
    url = state["url"]
    
    # Fetch URL content
    result = fetch_url_text(url)
    
    meta = result.get("meta", {})
    content_type = meta.get("content_type", "html")
    pages_used = meta.get("pages_used", 0) if content_type == "pdf" else 0
    
    return {
        **state,
        "url": result["url"],
        "title": result["title"] or "",
        "text": result["text"],
        "lang": result["lang"] or "en",
        "content_type": content_type,
        "pages_used": pages_used,
        "meta": meta
    }


def node_persist(state: IngestState) -> IngestState:
    """
    Persist source and chunks to Supabase.
    If state.source_id is already set (e.g. from POST /ingest), update existing source and insert chunks only.
    Otherwise insert new source then chunks.
    """
    repo = SupabaseRepo()
    user_id = state["user_id"]
    url = state["url"]
    title = state["title"]
    lang = state["lang"]
    text = state["text"]
    meta = state.get("meta", {})
    content_type = state.get("content_type", "")
    pages_used = state.get("pages_used", 0)

    chunks = chunk_text(text, max_chars=2000, overlap_chars=200)
    if not chunks:
        raise ValueError("No chunks created from text")

    source_id = (state.get("source_id") or "").strip()
    if source_id:
        # Update existing source (created by POST /ingest); do not insert again
        upd_meta = {**meta, "content_type": content_type, "pages_used": pages_used}
        repo.update_source(
            source_id,
            title=title,
            lang=lang,
            meta=upd_meta,
            status="running",
        )
    else:
        source_id = repo.insert_source(
            user_id=user_id,
            url=url,
            title=title,
            lang=lang,
            meta=meta,
        )

    chunk_ids = repo.insert_chunks(source_id=source_id, chunks=chunks)

    return {
        **state,
        "source_id": source_id,
        "chunk_count": len(chunk_ids),
        "embedding_count": 0,
    }


def node_embed(state: IngestState) -> IngestState:
    """
    Compute embeddings for chunks and persist to Supabase.
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with embedding_count
    """
    repo = SupabaseRepo()
    source_id = state["source_id"]
    
    # Fetch chunks for this source
    chunks = repo.fetch_chunks_by_source(source_id)
    
    if not chunks:
        return {
            **state,
            "embedding_count": 0
        }
    
    # Extract text from chunks
    chunk_texts = [chunk["text"] for chunk in chunks]
    chunk_ids = [str(chunk["id"]) for chunk in chunks]
    
    # Create embeddings
    vectors = create_embeddings(chunk_texts, max_retries=2)
    
    # Insert embeddings
    count = repo.insert_embeddings(chunk_ids, vectors)
    
    return {
        **state,
        "embedding_count": count
    }


def node_summarize_s1(state: IngestState) -> IngestState:
    """
    Create S1 summary for the ingested source.
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with summary_id, tldr, bullets_count
    """
    repo = SupabaseRepo()
    user_id = state["user_id"]
    source_id = state["source_id"]
    
    # Fetch top N chunks for summarization
    max_chunks = get_s1_max_chunks()
    chunks = repo.fetch_top_chunks_for_summary(source_id, n=max_chunks)
    
    if not chunks:
        return {
            **state,
            "summary_id": "",
            "tldr": "",
            "bullets_count": 0
        }
    
    # Concatenate chunks with separators
    chunks_text = "\n\n---\n\n".join([f"[Chunk {chunk['ord']}]\n{chunk['text']}" for chunk in chunks])
    
    # Create summary
    summary = create_s1_summary(chunks_text, max_retries=2)
    
    # Prepare extra metadata
    extra = {
        "model": get_summary_model(),
        "chunk_count_used": len(chunks)
    }
    if summary.get("tags"):
        extra["tags"] = summary["tags"]
    
    # Insert summary
    summary_id = repo.insert_summary_s1(
        user_id=user_id,
        source_id=source_id,
        tldr=summary["tldr"],
        bullets=summary["bullets"],
        extra=extra
    )
    
    return {
        **state,
        "summary_id": summary_id,
        "tldr": summary["tldr"],
        "bullets_count": len(summary["bullets"])
    }


def create_ingest_graph() -> StateGraph:
    """Create and compile the ingest graph."""
    graph = StateGraph(IngestState)
    
    # Add nodes
    graph.add_node("fetch", node_fetch)
    graph.add_node("persist", node_persist)
    graph.add_node("embed", node_embed)
    graph.add_node("summarize_s1", node_summarize_s1)
    
    # Set entry point
    graph.set_entry_point("fetch")
    
    # Add edges
    graph.add_edge("fetch", "persist")
    graph.add_edge("persist", "embed")
    graph.add_edge("embed", "summarize_s1")
    graph.add_edge("summarize_s1", END)
    
    # Compile and return
    return graph.compile()


# Create the compiled graph instance
ingest_graph = create_ingest_graph()

