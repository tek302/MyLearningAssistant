import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import psycopg
from psycopg import errors as psycopg_errors
import psycopg.types.json

from app.config import get_database_url
from app.feedback_types import NEGATIVE_FEEDBACK_ACTIONS


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

    def insert_source_pdf_file(self, user_id: str, title: Optional[str] = None) -> str:
        """
        Insert a new source for Local PDF upload (source_type=pdf_file, url=NULL).
        Caller must then upload to Storage and update meta (storage_path, original_filename).
        Returns source_id (UUID string).
        """
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sources (user_id, source_type, status, url, title, lang)
                    VALUES (%s, 'pdf_file', 'pending', NULL, %s, 'en')
                    RETURNING id
                    """,
                    (user_uuid, title or ""),
                )
                row = cur.fetchone()
                conn.commit()
                return str(row[0])

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

    def get_sources_for_user_since(
        self, user_id: str, since_ts: Optional[datetime] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        """Return sources for user with created_at >= since_ts, or last `days` days if since_ts is None. For S2 consolidation."""
        user_uuid = self._get_or_create_user_id(user_id)
        if since_ts is None:
            since_ts = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, created_at FROM sources
                    WHERE user_id = %s AND created_at >= %s
                    ORDER BY created_at ASC
                    """,
                    (user_uuid, since_ts),
                )
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                return [dict(zip(cols, row)) for row in rows]

    def get_sources_for_user_between(
        self, user_id: str, start_ts: datetime, end_ts: datetime
    ) -> List[Dict[str, Any]]:
        """Return sources for user where start_ts <= created_at < end_ts. For week-based S2."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, created_at FROM sources
                    WHERE user_id = %s AND created_at >= %s AND created_at < %s
                    ORDER BY created_at ASC
                    """,
                    (user_uuid, start_ts, end_ts),
                )
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                return [dict(zip(cols, row)) for row in rows]

    def get_user_ids_with_sources_since(self, days: int = 7) -> List[str]:
        """Return distinct user_id (UUID string) that have at least one source created in the last `days` days. For S2 schedule."""
        since = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT user_id FROM sources
                    WHERE created_at >= %s
                    """,
                    (since,),
                )
                rows = cur.fetchall()
                return [str(row[0]) for row in rows]

    def get_s1_summaries_for_sources(self, source_ids: List[str]) -> List[Dict[str, Any]]:
        """Return S1 summaries (tldr, bullets) for the given source ids. For S2 input."""
        if not source_ids:
            return []
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT source_id, tldr, bullets
                    FROM summaries
                    WHERE source_id = ANY(%s::uuid[]) AND scope = 'doc' AND kind = 'S1'
                    ORDER BY source_id
                    """,
                    (source_ids,),
                )
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                out = [dict(zip(cols, row)) for row in rows]
                for o in out:
                    if o.get("source_id") is not None:
                        o["source_id"] = str(o["source_id"])
                return out

    def delete_s2_for_user_week(self, user_id: str, week_start: str) -> int:
        """Delete existing S2 summary for user and week_start. Returns deleted count."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM summaries
                    WHERE user_id = %s AND scope = 'topic' AND kind = 'S2'
                    AND extra->>'week_start' = %s
                    """,
                    (user_uuid, week_start),
                )
                deleted = cur.rowcount
                conn.commit()
                return deleted

    def insert_summary_s2(
        self,
        user_id: str,
        week_start: str,
        tldr: str,
        bullets: List[str],
        source_ids: Optional[List[str]] = None,
        topic_name: str = "This Week",
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Insert S2 (topic-scope) summary. source_id is NULL. extra has week_start, topic_name, source_ids."""
        user_uuid = self._get_or_create_user_id(user_id)
        extra = {"week_start": week_start, "topic_name": topic_name}
        if source_ids:
            extra["source_ids"] = source_ids
        if extra_meta:
            extra.update(extra_meta)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO summaries (user_id, scope, kind, source_id, tldr, bullets, extra)
                    VALUES (%s, 'topic', 'S2', NULL, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_uuid, tldr, psycopg.types.json.Jsonb(bullets), psycopg.types.json.Jsonb(extra)),
                )
                row = cur.fetchone()
                conn.commit()
                return str(row[0])

    def get_s2_for_user_week(self, user_id: str, week_start: str) -> Optional[Dict[str, Any]]:
        """Return S2 summary for user and week_start (tldr, bullets, id). None if not found. For arXiv recommendations."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, tldr, bullets, extra
                    FROM summaries
                    WHERE user_id = %s AND scope = 'topic' AND kind = 'S2'
                    AND extra->>'week_start' = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (user_uuid, week_start),
                )
                row = cur.fetchone()
                if not row:
                    return None
                cols = [d[0] for d in cur.description]
                out = dict(zip(cols, row))
                out["id"] = str(out["id"])
                if out.get("bullets") is not None and hasattr(out["bullets"], "__iter__") and not isinstance(out["bullets"], str):
                    out["bullets"] = list(out["bullets"])
                return out

    def get_summary_by_id(self, summary_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get one summary row by id if owned by user. Supports S1/S2 feedback enrichment."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, scope, kind, source_id, tldr, bullets, extra, created_at
                    FROM summaries
                    WHERE id = %s AND user_id = %s
                    """,
                    (summary_id, user_uuid),
                )
                row = cur.fetchone()
                if not row:
                    return None
                cols = [d[0] for d in cur.description]
                out = dict(zip(cols, row))
                out["id"] = str(out["id"])
                if out.get("source_id") is not None:
                    out["source_id"] = str(out["source_id"])
                if out.get("bullets") is not None and hasattr(out["bullets"], "__iter__") and not isinstance(out["bullets"], str):
                    out["bullets"] = list(out["bullets"])
                if out.get("extra") is None:
                    out["extra"] = {}
                if out.get("created_at") is not None:
                    out["created_at"] = out["created_at"].isoformat() if hasattr(out["created_at"], "isoformat") else str(out["created_at"])
                return out
    
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
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Insert a job row and return job_id (UUID). payload is optional (e.g. {\"week_start\": \"YYYY-MM-DD\"} for s2)."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO jobs (user_id, job_type, source_id, payload)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_uuid, job_type, source_id, psycopg.types.json.Jsonb(payload) if payload else None),
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
                    SELECT id, user_id, job_type, state, progress, source_id, error, payload, created_at, updated_at
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
                if out.get("payload") is not None and hasattr(out["payload"], "copy"):
                    out["payload"] = dict(out["payload"])
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

    def cleanup_stale_running_jobs(self, max_age_minutes: int = 15, limit: int = 1) -> List[Dict[str, Any]]:
        """
        Mark stale running jobs as failed.
        A stale job is state='running' with updated_at older than max_age_minutes.
        Also marks the linked source failed when source_id is present.
        Returns cleaned job metadata for logging/response.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max(1, max_age_minutes))
        cleaned: List[Dict[str, Any]] = []
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, job_type, source_id
                    FROM jobs
                    WHERE state = 'running'
                      AND updated_at < %s
                    ORDER BY updated_at ASC
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                    """,
                    (cutoff, max(1, limit)),
                )
                rows = cur.fetchall()
                if not rows:
                    return cleaned

                for row in rows:
                    job_id = str(row[0])
                    user_id = str(row[1]) if row[1] is not None else None
                    job_type = str(row[2]) if row[2] is not None else None
                    source_id = str(row[3]) if row[3] is not None else None

                    cur.execute(
                        """
                        UPDATE jobs
                        SET state = 'failed',
                            error = 'stale_running',
                            updated_at = now()
                        WHERE id = %s
                        """,
                        (job_id,),
                    )

                    if source_id:
                        cur.execute(
                            """
                            UPDATE sources
                            SET status = 'failed',
                                fail_code = 'STALE_RUNNING'
                            WHERE id = %s AND status = 'running'
                            """,
                            (source_id,),
                        )

                    cleaned.append(
                        {
                            "job_id": job_id,
                            "user_id": user_id,
                            "job_type": job_type,
                            "source_id": source_id,
                        }
                    )

                conn.commit()
        return cleaned

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
        payload_merge: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update job fields. Only non-None args are updated. updated_at set to now().
        payload_merge: merge into existing payload (e.g. {"recommendations_failed": True})."""
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
        if payload_merge is not None:
            updates.append("payload = COALESCE(payload, '{}'::jsonb) || %s::jsonb")
            params.append(psycopg.types.json.Jsonb(payload_merge))
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

    # --- Recommendations (weekly arXiv) ---

    def insert_recommendation(
        self,
        user_id: str,
        topic_name: str,
        week_start: str,
        title: str,
        abstract: Optional[str],
        url: str,
        source: str = "arXiv",
        score: Optional[float] = None,
    ) -> str:
        """Insert one recommendation row. Returns recommendation id."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO recommendations (user_id, topic_name, week_start, title, abstract, url, source, score)
                    VALUES (%s, %s, %s::date, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_uuid, topic_name, week_start, title, abstract or "", url, source, score),
                )
                row = cur.fetchone()
                conn.commit()
                return str(row[0])

    def list_recommendations(
        self,
        user_id: str,
        week_start: Optional[str] = None,
        topic_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List recommendations for user, newest first. Optional filter by week_start, topic_name."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                q = """
                    SELECT id, topic_name, week_start, title, abstract, url, source, score, created_at
                    FROM recommendations
                    WHERE user_id = %s
                """
                params: List[Any] = [user_uuid]
                if week_start:
                    q += " AND week_start = %s::date"
                    params.append(week_start)
                if topic_name:
                    q += " AND topic_name = %s"
                    params.append(topic_name)
                q += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)
                cur.execute(q, params)
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                out = []
                for row in rows:
                    d = dict(zip(cols, row))
                    d["id"] = str(d["id"])
                    if d.get("week_start") is not None:
                        d["week_start"] = d["week_start"].isoformat() if hasattr(d["week_start"], "isoformat") else str(d["week_start"])
                    if d.get("created_at") is not None:
                        d["created_at"] = d["created_at"].isoformat() if hasattr(d["created_at"], "isoformat") else str(d["created_at"])
                    out.append(d)
                return out

    def get_recommendation_by_id(self, recommendation_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get one recommendation by id if owned by user. None otherwise."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, topic_name, week_start, title, abstract, url, source, score, created_at
                    FROM recommendations
                    WHERE id = %s AND user_id = %s
                    """,
                    (recommendation_id, user_uuid),
                )
                row = cur.fetchone()
                if not row:
                    return None
                cols = [d[0] for d in cur.description]
                d = dict(zip(cols, row))
                d["id"] = str(d["id"])
                if d.get("week_start") is not None:
                    d["week_start"] = d["week_start"].isoformat() if hasattr(d["week_start"], "isoformat") else str(d["week_start"])
                if d.get("created_at") is not None:
                    d["created_at"] = d["created_at"].isoformat() if hasattr(d["created_at"], "isoformat") else str(d["created_at"])
                return d

    def delete_recommendation(self, recommendation_id: str, user_id: str) -> bool:
        """Delete recommendation by id if owned by user. Returns True if a row was deleted."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM recommendations WHERE id = %s AND user_id = %s",
                    (recommendation_id, user_uuid),
                )
                deleted = cur.rowcount
                conn.commit()
                return deleted > 0

    # --- Notes (user notes, used in recommendations) ---

    def list_notes_for_user(
        self,
        user_id: str,
        source_id: Optional[str] = None,
        since_ts: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List notes for user, newest first. Optional filter by source_id or created_at >= since_ts."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                q = """
                    SELECT id, source_id, chunk_id, topic, content, created_at
                    FROM notes
                    WHERE user_id = %s
                """
                params: List[Any] = [user_uuid]
                if source_id:
                    try:
                        uuid.UUID(source_id)
                        q += " AND source_id = %s"
                        params.append(source_id)
                    except ValueError:
                        pass
                if since_ts is not None:
                    q += " AND created_at >= %s"
                    params.append(since_ts)
                q += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
                params.append(limit)
                params.append(offset)
                cur.execute(q, params)
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                out = []
                for row in rows:
                    d = dict(zip(cols, row))
                    d["id"] = str(d["id"])
                    for col in ("source_id", "chunk_id"):
                        if d.get(col) is not None:
                            d[col] = str(d[col])
                    if d.get("created_at") is not None:
                        d["created_at"] = d["created_at"].isoformat() if hasattr(d["created_at"], "isoformat") else str(d["created_at"])
                    out.append(d)
                return out

    def insert_note(
        self,
        user_id: str,
        content: str,
        source_id: Optional[str] = None,
        chunk_id: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> str:
        """Insert one note. Returns note id."""
        user_uuid = self._get_or_create_user_id(user_id)
        source_uuid = None
        if source_id:
            try:
                source_uuid = uuid.UUID(source_id)
            except ValueError:
                pass
        chunk_uuid = None
        if chunk_id:
            try:
                chunk_uuid = uuid.UUID(chunk_id)
            except ValueError:
                pass
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO notes (user_id, source_id, chunk_id, topic, content, created_at)
                    VALUES (%s, %s, %s, %s, %s, now())
                    RETURNING id
                    """,
                    (user_uuid, source_uuid, chunk_uuid, topic or None, content),
                )
                row = cur.fetchone()
                conn.commit()
                return str(row[0])

    def delete_note(self, note_id: str, user_id: str) -> bool:
        """Delete a note by id if owned by user. Returns True if a row was deleted."""
        try:
            note_uuid = uuid.UUID(note_id)
        except ValueError:
            return False
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM notes WHERE id = %s AND user_id = %s",
                    (note_uuid, user_uuid),
                )
                deleted = cur.rowcount
                conn.commit()
                return deleted > 0

    # --- Feedback events ---

    def insert_feedback_event(
        self,
        user_id: str,
        target_type: str,
        target_id: str,
        action: str,
        reasons: Optional[List[str]] = None,
        comment: Optional[str] = None,
        source_id: Optional[str] = None,
        week_start: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        client_event_id: Optional[str] = None,
    ) -> str:
        """Insert one feedback event. Returns feedback event id. Dedupes by client_event_id when provided."""
        user_uuid = self._get_or_create_user_id(user_id)
        target_uuid = uuid.UUID(target_id)
        source_uuid = None
        if source_id:
            try:
                source_uuid = uuid.UUID(source_id)
            except ValueError:
                source_uuid = None
        cleaned_reasons = [str(r).strip() for r in (reasons or []) if str(r).strip()]
        cleaned_comment = (comment or "").strip() or None
        cleaned_meta = meta or None
        cleaned_client_event_id = (client_event_id or "").strip() or None
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                if cleaned_client_event_id:
                    cur.execute(
                        "SELECT id FROM feedback_events WHERE client_event_id = %s",
                        (cleaned_client_event_id,),
                    )
                    existing = cur.fetchone()
                    if existing:
                        return str(existing[0])
                cur.execute(
                    """
                    INSERT INTO feedback_events (
                        user_id, target_type, target_id, action, reasons, comment,
                        source_id, week_start, meta, client_event_id, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s::date, %s::jsonb, %s, now())
                    RETURNING id
                    """,
                    (
                        user_uuid,
                        target_type,
                        str(target_uuid),
                        action,
                        psycopg.types.json.Json(cleaned_reasons) if cleaned_reasons else None,
                        cleaned_comment,
                        source_uuid,
                        week_start,
                        psycopg.types.json.Json(cleaned_meta) if cleaned_meta is not None else None,
                        cleaned_client_event_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return str(row[0])

    def list_feedback_events(
        self,
        user_id: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List feedback events. When user_id is set, limits to that user's events."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                q = """
                    SELECT id, user_id, target_type, target_id, action, reasons, comment,
                           source_id, week_start, meta, client_event_id, created_at
                    FROM feedback_events
                    WHERE 1=1
                """
                params: List[Any] = []
                if user_id:
                    q += " AND user_id = %s"
                    params.append(self._get_or_create_user_id(user_id))
                if target_type:
                    q += " AND target_type = %s"
                    params.append(target_type)
                if target_id:
                    try:
                        q += " AND target_id = %s"
                        params.append(str(uuid.UUID(target_id)))
                    except ValueError:
                        return []
                q += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])
                cur.execute(q, params)
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                out = []
                for row in rows:
                    d = dict(zip(cols, row))
                    for col in ("id", "user_id", "target_id", "source_id"):
                        if d.get(col) is not None:
                            d[col] = str(d[col])
                    if d.get("week_start") is not None:
                        d["week_start"] = d["week_start"].isoformat() if hasattr(d["week_start"], "isoformat") else str(d["week_start"])
                    if d.get("created_at") is not None:
                        d["created_at"] = d["created_at"].isoformat() if hasattr(d["created_at"], "isoformat") else str(d["created_at"])
                    if d.get("reasons") is None:
                        d["reasons"] = []
                    if d.get("meta") is None:
                        d["meta"] = {}
                    out.append(d)
                return out

    def get_feedback_summary(self, days: int = 30, limit_reasons: int = 10) -> Dict[str, Any]:
        """Return aggregate feedback summary for admin dashboards."""
        since_ts = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT target_type, COUNT(*)
                    FROM feedback_events
                    WHERE created_at >= %s
                    GROUP BY target_type
                    """,
                    (since_ts,),
                )
                totals_by_target = {str(row[0]): int(row[1]) for row in cur.fetchall()}

                cur.execute(
                    """
                    SELECT action, COUNT(*)
                    FROM feedback_events
                    WHERE created_at >= %s
                    GROUP BY action
                    """,
                    (since_ts,),
                )
                actions = {str(row[0]): int(row[1]) for row in cur.fetchall()}

                cur.execute(
                    """
                    SELECT reason, COUNT(*)
                    FROM (
                        SELECT jsonb_array_elements_text(reasons) AS reason
                        FROM feedback_events
                        WHERE created_at >= %s AND reasons IS NOT NULL
                    ) r
                    GROUP BY reason
                    ORDER BY COUNT(*) DESC, reason ASC
                    LIMIT %s
                    """,
                    (since_ts, limit_reasons),
                )
                top_reasons = [{"reason": str(row[0]), "count": int(row[1])} for row in cur.fetchall()]

                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM feedback_events
                    WHERE created_at >= %s
                    """,
                    (since_ts,),
                )
                total = int(cur.fetchone()[0])

                return {
                    "window_days": days,
                    "totals": {
                        "all": total,
                        **totals_by_target,
                    },
                    "actions": actions,
                    "top_reasons": top_reasons,
                }

    def list_recent_feedback_texts_for_user(
        self,
        user_id: str,
        since_ts: Optional[datetime] = None,
        limit: int = 50,
        target_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return recent feedback rows for text extraction in recommendation generation."""
        user_uuid = self._get_or_create_user_id(user_id)
        if since_ts is None:
            since_ts = datetime.now(timezone.utc) - timedelta(days=30)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                q = """
                    SELECT target_type, action, reasons, comment, meta, created_at
                    FROM feedback_events
                    WHERE user_id = %s AND created_at >= %s
                """
                params: List[Any] = [user_uuid, since_ts]
                if target_type:
                    q += " AND target_type = %s"
                    params.append(target_type)
                q += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)
                cur.execute(q, params)
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                out = []
                for row in rows:
                    d = dict(zip(cols, row))
                    if d.get("created_at") is not None:
                        d["created_at"] = d["created_at"].isoformat() if hasattr(d["created_at"], "isoformat") else str(d["created_at"])
                    if d.get("reasons") is None:
                        d["reasons"] = []
                    if d.get("meta") is None:
                        d["meta"] = {}
                    out.append(d)
                return out

    def list_recent_negative_feedback_events(self, days: int = 30, limit: int = 20) -> List[Dict[str, Any]]:
        """Return recent negative feedback events for dashboard inspection."""
        since_ts = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT target_type, action, reasons, comment, week_start, meta, created_at
                    FROM feedback_events
                    WHERE created_at >= %s
                      AND action = ANY(%s)
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (since_ts, list(NEGATIVE_FEEDBACK_ACTIONS), limit),
                )
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                out: List[Dict[str, Any]] = []
                for row in rows:
                    d = dict(zip(cols, row))
                    if d.get("created_at") is not None:
                        d["created_at"] = d["created_at"].isoformat() if hasattr(d["created_at"], "isoformat") else str(d["created_at"])
                    if d.get("week_start") is not None:
                        d["week_start"] = d["week_start"].isoformat() if hasattr(d["week_start"], "isoformat") else str(d["week_start"])
                    if d.get("reasons") is None:
                        d["reasons"] = []
                    if d.get("meta") is None:
                        d["meta"] = {}
                    out.append(d)
                return out

    def get_feedback_reason_breakdown(self, days: int = 30, limit: int = 10) -> List[Dict[str, Any]]:
        """Return top feedback reasons in the time window."""
        since_ts = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT reason, COUNT(*)
                    FROM (
                        SELECT jsonb_array_elements_text(reasons) AS reason
                        FROM feedback_events
                        WHERE created_at >= %s AND reasons IS NOT NULL
                    ) r
                    GROUP BY reason
                    ORDER BY COUNT(*) DESC, reason ASC
                    LIMIT %s
                    """,
                    (since_ts, limit),
                )
                return [{"reason": str(row[0]), "count": int(row[1])} for row in cur.fetchall()]

    def get_feedback_target_type_breakdown(self, days: int = 30) -> List[Dict[str, Any]]:
        """Return target_type counts for dashboard cards."""
        since_ts = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT target_type, COUNT(*)
                    FROM feedback_events
                    WHERE created_at >= %s
                    GROUP BY target_type
                    ORDER BY COUNT(*) DESC, target_type ASC
                    """,
                    (since_ts,),
                )
                return [{"target_type": str(row[0]), "count": int(row[1])} for row in cur.fetchall()]

    def get_recommendation_feedback_rollup(self, days: int = 30, limit: int = 20) -> List[Dict[str, Any]]:
        """Aggregate recommendation feedback by title and snapshot metadata."""
        since_ts = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        COALESCE(meta->>'title', '(unknown)') AS title,
                        COALESCE(meta->>'prompt_version', '') AS prompt_version,
                        COALESCE(meta->'model_snapshot'->>'llm', '') AS llm,
                        COALESCE(meta->'model_snapshot'->>'embedding_model', '') AS embedding_model,
                        COUNT(*) AS total_count,
                        COUNT(*) FILTER (WHERE action = 'thumbs_up') AS thumbs_up_count,
                        COUNT(*) FILTER (WHERE action = 'thumbs_down') AS thumbs_down_count,
                        MAX(created_at) AS latest_created_at
                    FROM feedback_events
                    WHERE created_at >= %s
                      AND target_type = 'recommendation'
                    GROUP BY 1, 2, 3, 4
                    ORDER BY thumbs_down_count DESC, total_count DESC, latest_created_at DESC
                    LIMIT %s
                    """,
                    (since_ts, limit),
                )
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                out: List[Dict[str, Any]] = []
                for row in rows:
                    d = dict(zip(cols, row))
                    if d.get("latest_created_at") is not None:
                        d["latest_created_at"] = d["latest_created_at"].isoformat() if hasattr(d["latest_created_at"], "isoformat") else str(d["latest_created_at"])
                    out.append(d)
                return out

    def get_s2_feedback_rollup(self, days: int = 30, limit: int = 20) -> List[Dict[str, Any]]:
        """Aggregate S2 feedback by week_start and snapshot metadata."""
        since_ts = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        COALESCE(week_start::text, meta->>'week_start', '(unknown)') AS week_start,
                        COALESCE(meta->>'topic_name', '(unknown)') AS topic_name,
                        COALESCE(meta->>'prompt_version', '') AS prompt_version,
                        COALESCE(meta->'model_snapshot'->>'llm', '') AS llm,
                        COALESCE(meta->'model_snapshot'->>'embedding_model', '') AS embedding_model,
                        COUNT(*) AS total_count,
                        COUNT(*) FILTER (WHERE action = 'thumbs_up') AS thumbs_up_count,
                        COUNT(*) FILTER (WHERE action = 'thumbs_down') AS thumbs_down_count,
                        MAX(created_at) AS latest_created_at
                    FROM feedback_events
                    WHERE created_at >= %s
                      AND target_type = 'summary_s2'
                    GROUP BY 1, 2, 3, 4, 5
                    ORDER BY thumbs_down_count DESC, total_count DESC, latest_created_at DESC
                    LIMIT %s
                    """,
                    (since_ts, limit),
                )
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                out: List[Dict[str, Any]] = []
                for row in rows:
                    d = dict(zip(cols, row))
                    if d.get("latest_created_at") is not None:
                        d["latest_created_at"] = d["latest_created_at"].isoformat() if hasattr(d["latest_created_at"], "isoformat") else str(d["latest_created_at"])
                    out.append(d)
                return out

    def get_feedback_dashboard_data(self, days: int = 30, limit: int = 20) -> Dict[str, Any]:
        """Return compact admin dashboard data for HTML and JSON endpoints."""
        summary = self.get_feedback_summary(days=days, limit_reasons=min(limit, 20))
        recent_negative = self.list_recent_negative_feedback_events(days=days, limit=limit)
        return {
            "window_days": days,
            "summary": summary,
            "target_breakdown": self.get_feedback_target_type_breakdown(days=days),
            "recent_negative": recent_negative,
            "top_reasons": self.get_feedback_reason_breakdown(days=days, limit=min(limit, 20)),
            "recommendation_rollup": self.get_recommendation_feedback_rollup(days=days, limit=limit),
            "s2_rollup": self.get_s2_feedback_rollup(days=days, limit=limit),
        }

