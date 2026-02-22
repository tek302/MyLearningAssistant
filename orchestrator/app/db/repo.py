import os
import uuid
from typing import Optional, List, Dict, Any
import psycopg
from psycopg import errors as psycopg_errors
import psycopg.types.json

from app.config import get_database_url


class SupabaseRepo:
    """Repository for Supabase database operations."""

    def __init__(self):
        """Initialize the repository with database connection from env vars."""
        self.db_url = get_database_url()
        # Cache for column existence checks (lazy initialization)
        self._sources_has_meta: Optional[bool] = None
    
    def _get_connection(self):
        """Get a database connection."""
        return psycopg.connect(self.db_url)
    
    def ping(self) -> bool:
        """Check database connectivity by running 'select 1'."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    result = cur.fetchone()
                    return result[0] == 1
        except Exception:
            return False
    
    def _get_or_create_user_id(self, user_identifier: str) -> str:
        """
        Get user UUID from users table, or create if doesn't exist.
        
        If user_identifier is already a UUID, validate it exists.
        Otherwise, treat it as firebase_uid and lookup/create.
        
        Args:
            user_identifier: User identifier (UUID string or firebase_uid)
            
        Returns:
            user_id: UUID string of the user
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # Check if it's a valid UUID format
                try:
                    uuid_obj = uuid.UUID(user_identifier)
                    # It's a UUID, check if user exists by id
                    cur.execute(
                        "SELECT id FROM users WHERE id = %s",
                        (str(uuid_obj),)
                    )
                    result = cur.fetchone()
                    if result:
                        return str(result[0])
                    # UUID doesn't exist, create user with this UUID as id and firebase_uid
                    # Use ON CONFLICT on id (primary key) or just insert
                    try:
                        cur.execute(
                            """
                            INSERT INTO users (id, firebase_uid)
                            VALUES (%s, %s)
                            RETURNING id
                            """,
                            (str(uuid_obj), user_identifier)
                        )
                        result = cur.fetchone()
                        conn.commit()
                        return str(result[0])
                    except psycopg_errors.UniqueViolation:
                        # If id already exists, just return it
                        conn.rollback()
                        cur.execute(
                            "SELECT id FROM users WHERE id = %s",
                            (str(uuid_obj),)
                        )
                        result = cur.fetchone()
                        if result:
                            return str(result[0])
                        raise
                except ValueError:
                    # Not a UUID, treat as firebase_uid
                    cur.execute(
                        """
                        SELECT id FROM users WHERE firebase_uid = %s
                        """,
                        (user_identifier,)
                    )
                    result = cur.fetchone()
                    if result:
                        return str(result[0])
                    # User doesn't exist, create new user
                    # Try to insert, if it fails due to unique constraint, fetch again
                    try:
                        cur.execute(
                            """
                            INSERT INTO users (firebase_uid)
                            VALUES (%s)
                            RETURNING id
                            """,
                            (user_identifier,)
                        )
                        result = cur.fetchone()
                        conn.commit()
                        return str(result[0])
                    except psycopg_errors.UniqueViolation:
                        # If firebase_uid already exists (race condition), fetch it
                        conn.rollback()
                        cur.execute(
                            """
                            SELECT id FROM users WHERE firebase_uid = %s
                            """,
                            (user_identifier,)
                        )
                        result = cur.fetchone()
                        if result:
                            return str(result[0])
                        raise
    
    def insert_source(
        self, 
        user_id: str, 
        url: str, 
        title: str, 
        lang: str, 
        meta: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Insert a new source or return existing source_id if already exists.
        
        Args:
            user_id: User identifier (UUID string or firebase_uid)
            url: Source URL
            title: Source title
            lang: Language code
            meta: Optional metadata dictionary
            
        Returns:
            source_id: The ID of the inserted or existing source
        """
        # Get or create user UUID
        user_uuid = self._get_or_create_user_id(user_id)
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # First, try to find existing source
                cur.execute(
                    """
                    SELECT id FROM sources WHERE user_id = %s AND url = %s
                    """,
                    (user_uuid, url)
                )
                result = cur.fetchone()
                if result:
                    return str(result[0])
                
                # Source doesn't exist, insert new one
                try:
                    cur.execute(
                        """
                        INSERT INTO sources (user_id, url, title, lang, meta)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (user_uuid, url, title, lang, psycopg.types.json.Jsonb(meta) if meta else None)
                    )
                    result = cur.fetchone()
                    conn.commit()
                    return str(result[0])
                except psycopg_errors.UniqueViolation:
                    # Race condition: another request inserted the same source
                    conn.rollback()
                    cur.execute(
                        """
                        SELECT id FROM sources WHERE user_id = %s AND url = %s
                        """,
                        (user_uuid, url)
                    )
                    result = cur.fetchone()
                    if result:
                        return str(result[0])
                    raise
    
    def insert_chunks(self, source_id: str, chunks: List[str]) -> List[str]:
        """
        Insert chunks for a source and return list of chunk_ids.
        If chunks already exist for this source, they will be deleted first.
        
        Args:
            source_id: Source identifier
            chunks: List of chunk text content
            
        Returns:
            List of chunk_ids
        """
        chunk_ids = []
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # Delete existing chunks for this source (cascade will delete embeddings)
                cur.execute(
                    """
                    DELETE FROM chunks WHERE source_id = %s
                    """,
                    (source_id,)
                )
                
                # Insert new chunks
                for ord_idx, chunk in enumerate(chunks, start=1):
                    cur.execute(
                        """
                        INSERT INTO chunks (source_id, ord, text)
                        VALUES (%s, %s, %s)
                        RETURNING id
                        """,
                        (source_id, ord_idx, chunk)
                    )
                    result = cur.fetchone()
                    chunk_ids.append(str(result[0]))
                conn.commit()
        return chunk_ids
    
    def fetch_chunks_by_source(self, source_id: str) -> List[Dict[str, Any]]:
        """
        Fetch all chunks for a source.
        
        Args:
            source_id: Source identifier
            
        Returns:
            List of dictionaries with keys: id, text, ord
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, text, ord
                    FROM chunks
                    WHERE source_id = %s
                    ORDER BY ord
                    """,
                    (source_id,)
                )
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                return [dict(zip(columns, row)) for row in rows]
    
    def fetch_top_chunks_for_summary(self, source_id: str, n: int = 8) -> List[Dict[str, Any]]:
        """
        Fetch top N chunks for a source, ordered by ord.
        
        Args:
            source_id: Source identifier
            n: Number of chunks to fetch (default: 8)
            
        Returns:
            List of dictionaries with keys: id, text, ord
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, text, ord
                    FROM chunks
                    WHERE source_id = %s
                    ORDER BY ord
                    LIMIT %s
                    """,
                    (source_id, n)
                )
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                return [dict(zip(columns, row)) for row in rows]
    
    def insert_embeddings(self, chunk_ids: List[str], vectors: List[List[float]]) -> int:
        """
        Insert embeddings for chunks.
        
        Args:
            chunk_ids: List of chunk identifiers
            vectors: List of embedding vectors (1536 dimensions)
            
        Returns:
            Number of embeddings inserted
        """
        if len(chunk_ids) != len(vectors):
            raise ValueError("chunk_ids and vectors must have the same length")
        
        count = 0
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                for chunk_id, vector in zip(chunk_ids, vectors):
                    # Convert list to PostgreSQL vector type string format
                    # pgvector expects format: [1,2,3,...] as string
                    vector_str = "[" + ",".join(str(v) for v in vector) + "]"
                    
                    cur.execute(
                        """
                        INSERT INTO embeddings (chunk_id, embedding)
                        VALUES (%s, %s::vector)
                        ON CONFLICT (chunk_id) DO UPDATE SET embedding = EXCLUDED.embedding
                        """,
                        (chunk_id, vector_str)
                    )
                    count += 1
                conn.commit()
        return count
    
    def insert_summary_s1(
        self,
        user_id: str,
        source_id: str,
        tldr: str,
        bullets: List[str],
        extra: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Insert a stage 1 summary and return the summary_id.
        If a summary already exists for this source (scope='doc', kind='S1'), 
        it will be deleted first.
        
        Args:
            user_id: User identifier (UUID string or firebase_uid)
            source_id: Source identifier
            tldr: TLDR summary text (max 200 chars)
            bullets: List of bullet points (3-7 items)
            extra: Optional extra metadata (tags, model, chunk_count_used)
            
        Returns:
            summary_id: The ID of the inserted summary
        """
        # Get or create user UUID
        user_uuid = self._get_or_create_user_id(user_id)
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # Delete existing S1 summary for this source
                cur.execute(
                    """
                    DELETE FROM summaries 
                    WHERE source_id = %s AND scope = 'doc' AND kind = 'S1'
                    """,
                    (source_id,)
                )
                
                # Insert new summary
                cur.execute(
                    """
                    INSERT INTO summaries (user_id, scope, kind, source_id, tldr, bullets, extra)
                    VALUES (%s, 'doc', 'S1', %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        user_uuid,
                        source_id,
                        tldr,
                        psycopg.types.json.Jsonb(bullets),
                        psycopg.types.json.Jsonb(extra) if extra else None
                    )
                )
                result = cur.fetchone()
                conn.commit()
                return str(result[0])
    
    def _check_sources_has_meta(self, conn) -> bool:
        """
        Check if sources table has meta column (cached).
        
        Args:
            conn: Database connection
            
        Returns:
            True if sources.meta column exists, False otherwise
        """
        if self._sources_has_meta is not None:
            return self._sources_has_meta
        
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 
                        FROM information_schema.columns 
                        WHERE table_schema = 'public' 
                        AND table_name = 'sources' 
                        AND column_name = 'meta'
                    )
                """)
                result = cur.fetchone()
                self._sources_has_meta = result[0] if result else False
                return self._sources_has_meta
        except Exception:
            # On error, assume meta doesn't exist (safe fallback)
            self._sources_has_meta = False
            return False
    
    def search_similar_chunks(
        self,
        user_id: str,
        query_vec: List[float],
        k: int,
        topic: Optional[str] = None,
        lang: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search for chunks using pgvector.
        
        Args:
            user_id: User identifier (UUID string or firebase_uid)
            query_vec: Query embedding vector (1536 dimensions) - must be list[float]
            k: Number of results to return (will be clamped to 1-20)
            topic: Optional topic filter (checks sources.meta->>'topic' if exists)
            lang: Optional language filter (checks sources.lang)
            source_id: Optional document scope; restrict retrieval to this source (sources.id).
            
        Returns:
            List of dictionaries with keys: chunk_id, source_id, chunk_text, chunk_ord,
            url, title, similarity_score
        """
        # Hard cap k in repo layer too
        k = min(max(int(k), 1), 20)
        
        # Get user UUID (strict user scoping)
        user_uuid = self._get_or_create_user_id(user_id)
        
        # Ensure query_vec is list[float] for safe string conversion
        if not isinstance(query_vec, list):
            raise ValueError("query_vec must be a list[float]")
        if not all(isinstance(x, (int, float)) for x in query_vec):
            raise ValueError("query_vec must contain only numeric values")
        
        # Convert vector to pgvector format (safe string conversion)
        vector_str = "[" + ",".join(str(float(v)) for v in query_vec) + "]"
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # Check if sources.meta exists (cached check)
                has_meta = self._check_sources_has_meta(conn)
                
                # Use CTE to cast vector once and reuse for both SELECT and ORDER BY
                # This removes duplicate vector parameter usage
                base_query = """
                WITH query_vector AS (
                    SELECT %s::vector AS vec
                )
                SELECT 
                    c.id as chunk_id,
                    c.source_id,
                    c.text as chunk_text,
                    c.ord as chunk_ord,
                    s.url,
                    s.title,
                    1 - (e.embedding <=> qv.vec) as similarity_score
                FROM chunks c
                JOIN embeddings e ON c.id = e.chunk_id
                JOIN sources s ON c.source_id = s.id
                CROSS JOIN query_vector qv
                WHERE s.user_id = %s
                """
                
                params = [vector_str, user_uuid]
                
                # Add optional filters (best-effort, don't break if columns missing)
                # Include sources with lang IS NULL (e.g. PDFs ingested without lang) when filtering by lang
                if lang:
                    base_query += " AND (s.lang = %s OR s.lang IS NULL)"
                    params.append(lang)
                
                if topic and has_meta:
                    # Only add topic filter if meta column exists
                    base_query += " AND s.meta->>'topic' = %s"
                    params.append(topic)
                elif topic and not has_meta:
                    # If topic requested but meta doesn't exist, log but don't filter
                    # (best-effort: silently ignore the filter)
                    pass
                
                if source_id:
                    base_query += " AND s.id = %s"
                    params.append(source_id)
                
                # Order by similarity (cosine distance); tie-breaker: prefer early chunks (ord ASC)
                base_query += """
                ORDER BY (e.embedding <=> qv.vec) ASC, c.ord ASC
                LIMIT %s
                """
                params.append(k)
                
                cur.execute(base_query, params)
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                return [dict(zip(columns, row)) for row in rows]

    def create_job(
        self,
        user_id: str,
        job_type: str,
        source_id: Optional[str] = None,
    ) -> str:
        """Insert a job row and return job_id (UUID)."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO jobs (user_id, job_type, source_id)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (user_uuid, job_type, source_id),
                )
                row = cur.fetchone()
                conn.commit()
                return str(row[0])

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Load job by id. Returns dict with id, user_id, job_type, state, progress, source_id, error, created_at, updated_at or None."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, job_type, state, progress, source_id, error, created_at, updated_at
                    FROM jobs WHERE id = %s
                    """,
                    (job_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                cols = [d[0] for d in cur.description]
                out = dict(zip(cols, row))
                for k in ("id", "user_id", "source_id"):
                    if out.get(k) is not None:
                        out[k] = str(out[k])
                for k in ("created_at", "updated_at"):
                    if out.get(k) is not None:
                        out[k] = out[k].isoformat()
                return out

    def claim_one_queued_job(self) -> Optional[str]:
        """
        Claim one job with state='queued'; set state='running'.
        Uses FOR UPDATE SKIP LOCKED for concurrent tick safety.
        Returns job_id or None if no queued job.
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id FROM jobs
                    WHERE state = 'queued'
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """
                )
                row = cur.fetchone()
                if not row:
                    return None
                job_id = str(row[0])
                cur.execute(
                    "UPDATE jobs SET state = 'running', updated_at = now() WHERE id = %s",
                    (job_id,),
                )
                conn.commit()
                return job_id

    def get_job_for_user(self, user_uuid: str, job_id: str) -> Optional[Dict[str, Any]]:
        """Load job by id and user_id. Returns dict with id, state, progress, source_id, error or None.
        Ownership enforced: job must belong to current user.
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, state, progress, source_id, error
                    FROM jobs
                    WHERE id = %s AND user_id = %s
                    """,
                    (job_id, user_uuid),
                )
                row = cur.fetchone()
                if not row:
                    return None
                cols = [d[0] for d in cur.description]
                out = dict(zip(cols, row))
                for k in ("id", "source_id"):
                    if out.get(k) is not None:
                        out[k] = str(out[k])
                return out

    def update_job(
        self,
        job_id: str,
        state: Optional[str] = None,
        progress: Optional[int] = None,
        error: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> None:
        """Update job fields. Only non-None args are updated. updated_at set to now()."""
        updates: List[str] = ["updated_at = now()"]
        params: List[Any] = []
        if state is not None:
            updates.append("state = %s")
            params.append(state)
        if progress is not None:
            updates.append("progress = %s")
            params.append(progress)
        if error is not None:
            updates.append("error = %s")
            params.append(error)
        if source_id is not None:
            updates.append("source_id = %s")
            params.append(source_id)
        if len(params) == 0:
            return
        params.append(job_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE jobs SET {', '.join(updates)} WHERE id = %s",
                    params,
                )
                conn.commit()

    def get_source_by_id(self, source_id: str) -> Optional[Dict[str, Any]]:
        """Load source by id. Returns dict with id, user_id, url, source_type, status, title, lang, meta, etc. or None."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, url, source_type, status, title, lang, meta, pages, size_mb, char_count, fail_code
                    FROM sources WHERE id = %s
                    """,
                    (source_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                cols = [d[0] for d in cur.description]
                out = dict(zip(cols, row))
                out["id"] = str(out["id"])
                out["user_id"] = str(out["user_id"])
                if out.get("meta") is not None and hasattr(out["meta"], "copy"):
                    out["meta"] = dict(out["meta"])
                return out

    def update_source(
        self,
        source_id: str,
        title: Optional[str] = None,
        lang: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
        pages: Optional[int] = None,
        char_count: Optional[int] = None,
        size_mb: Optional[float] = None,
        fail_code: Optional[str] = None,
    ) -> None:
        """Update source fields. Only non-None args are updated."""
        updates: List[str] = []
        params: List[Any] = []
        if title is not None:
            updates.append("title = %s")
            params.append(title)
        if lang is not None:
            updates.append("lang = %s")
            params.append(lang)
        if meta is not None:
            updates.append("meta = %s")
            params.append(psycopg.types.json.Jsonb(meta))
        if status is not None:
            updates.append("status = %s")
            params.append(status)
        if pages is not None:
            updates.append("pages = %s")
            params.append(pages)
        if char_count is not None:
            updates.append("char_count = %s")
            params.append(char_count)
        if size_mb is not None:
            updates.append("size_mb = %s")
            params.append(size_mb)
        if fail_code is not None:
            updates.append("fail_code = %s")
            params.append(fail_code)
        if not updates:
            return
        params.append(source_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE sources SET updated_at = now(), {', '.join(updates)} WHERE id = %s",
                    params,
                )
                conn.commit()

