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

    def get_existing_user_id(self, user_identifier: str) -> Optional[str]:
        """Return existing user UUID for a UUID or firebase_uid identifier, without creating a new row."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    uuid_obj = uuid.UUID(user_identifier)
                    cur.execute("SELECT id FROM users WHERE id = %s", (str(uuid_obj),))
                    row = cur.fetchone()
                    return str(row[0]) if row else None
                except ValueError:
                    cur.execute("SELECT id FROM users WHERE firebase_uid = %s", (user_identifier,))
                    row = cur.fetchone()
                    return str(row[0]) if row else None

    # --- Interest threads (multi-thread + global keyword pool B) ---

    def get_or_create_default_thread_id(self, user_id: str) -> str:
        """Return the user's default interest_thread id, creating 'General' if missing."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id FROM interest_threads
                    WHERE user_id = %s AND is_default = true
                    LIMIT 1
                    """,
                    (user_uuid,),
                )
                row = cur.fetchone()
                if row:
                    return str(row[0])
                cur.execute(
                    """
                    INSERT INTO interest_threads (user_id, name, description, is_default)
                    VALUES (%s, 'General', 'Default research thread', true)
                    RETURNING id
                    """,
                    (user_uuid,),
                )
                row = cur.fetchone()
                conn.commit()
                return str(row[0])

    def list_interest_threads(
        self, user_id: str, include_archived: bool = False
    ) -> List[Dict[str, Any]]:
        """List threads for user, newest first. Omits archived unless include_archived."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                q = """
                    SELECT id, name, description, is_default, archived_at, created_at, updated_at
                    FROM interest_threads
                    WHERE user_id = %s
                """
                params: List[Any] = [user_uuid]
                if not include_archived:
                    q += " AND archived_at IS NULL"
                q += " ORDER BY is_default DESC, created_at ASC"
                cur.execute(q, params)
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                out: List[Dict[str, Any]] = []
                for row in rows:
                    d = dict(zip(cols, row))
                    d["id"] = str(d["id"])
                    for ts_col in ("archived_at", "created_at", "updated_at"):
                        if d.get(ts_col) is not None:
                            d[ts_col] = d[ts_col].isoformat() if hasattr(d[ts_col], "isoformat") else str(d[ts_col])
                    out.append(d)
                return out

    def get_interest_thread(self, thread_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Return one thread if owned by user."""
        try:
            tid = uuid.UUID(thread_id)
        except ValueError:
            return None
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, description, is_default, archived_at, created_at, updated_at
                    FROM interest_threads
                    WHERE id = %s AND user_id = %s
                    """,
                    (tid, user_uuid),
                )
                row = cur.fetchone()
                if not row:
                    return None
                cols = [d[0] for d in cur.description]
                d = dict(zip(cols, row))
                d["id"] = str(d["id"])
                for ts_col in ("archived_at", "created_at", "updated_at"):
                    if d.get(ts_col) is not None:
                        d[ts_col] = d[ts_col].isoformat() if hasattr(d[ts_col], "isoformat") else str(d[ts_col])
                return d

    def create_interest_thread(
        self, user_id: str, name: str, description: Optional[str] = None, is_default: bool = False
    ) -> str:
        """Create a thread. If is_default, clears default flag on other rows for this user."""
        user_uuid = self._get_or_create_user_id(user_id)
        nm = (name or "").strip()
        if not nm:
            raise ValueError("name is required")
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                if is_default:
                    cur.execute(
                        "UPDATE interest_threads SET is_default = false, updated_at = now() WHERE user_id = %s",
                        (user_uuid,),
                    )
                cur.execute(
                    """
                    INSERT INTO interest_threads (user_id, name, description, is_default)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_uuid, nm, (description or "").strip() or None, is_default),
                )
                row = cur.fetchone()
                conn.commit()
                return str(row[0])

    def update_interest_thread(
        self,
        thread_id: str,
        user_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> bool:
        """Patch name/description. Returns True if updated."""
        try:
            tid = uuid.UUID(thread_id)
        except ValueError:
            return False
        user_uuid = self._get_or_create_user_id(user_id)
        sets: List[str] = ["updated_at = now()"]
        params: List[Any] = []
        if name is not None:
            sets.append("name = %s")
            params.append((name or "").strip() or "Untitled")
        if description is not None:
            sets.append("description = %s")
            params.append((description or "").strip() or None)
        if len(sets) <= 1:
            return False
        params.extend([tid, user_uuid])
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE interest_threads SET {', '.join(sets)} WHERE id = %s AND user_id = %s",
                    params,
                )
                n = cur.rowcount
                conn.commit()
                return n > 0

    def archive_interest_thread(self, thread_id: str, user_id: str) -> bool:
        """Soft-archive thread (cannot archive sole default without another default — caller avoids)."""
        try:
            tid = uuid.UUID(thread_id)
        except ValueError:
            return False
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE interest_threads
                    SET archived_at = now(), updated_at = now()
                    WHERE id = %s AND user_id = %s AND is_default = false
                    """,
                    (tid, user_uuid),
                )
                n = cur.rowcount
                conn.commit()
                return n > 0

    def list_thread_keyword_weights(self, thread_id: str, user_id: str) -> List[Dict[str, Any]]:
        """Junction rows for a thread (ownership via thread.user_id)."""
        try:
            tid = uuid.UUID(thread_id)
        except ValueError:
            return []
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT w.id, w.thread_id, w.user_keyword_id, w.weight_multiplier, w.activation,
                           w.created_at, w.updated_at
                    FROM thread_keyword_weights w
                    INNER JOIN interest_threads t ON t.id = w.thread_id
                    WHERE w.thread_id = %s AND t.user_id = %s
                    """,
                    (tid, user_uuid),
                )
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                out: List[Dict[str, Any]] = []
                for row in rows:
                    d = dict(zip(cols, row))
                    d["id"] = str(d["id"])
                    d["thread_id"] = str(d["thread_id"])
                    d["user_keyword_id"] = str(d["user_keyword_id"])
                    for ts_col in ("created_at", "updated_at"):
                        if d.get(ts_col) is not None:
                            d[ts_col] = d[ts_col].isoformat() if hasattr(d[ts_col], "isoformat") else str(d[ts_col])
                    out.append(d)
                return out

    def upsert_thread_keyword_weight(
        self,
        thread_id: str,
        user_keyword_id: str,
        user_id: str,
        activation: float = 1.0,
        weight_multiplier: float = 1.0,
    ) -> None:
        """Ensure junction row exists; clamp activation to [0,1]."""
        try:
            tid = uuid.UUID(thread_id)
            kwid = uuid.UUID(user_keyword_id)
        except ValueError:
            raise ValueError("invalid thread_id or user_keyword_id")
        user_uuid = self._get_or_create_user_id(user_id)
        act = max(0.0, min(1.0, float(activation)))
        mult = max(0.01, float(weight_multiplier))
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM interest_threads t
                    INNER JOIN user_keywords k ON k.user_id = t.user_id
                    WHERE t.id = %s AND t.user_id = %s AND k.id = %s
                    """,
                    (tid, user_uuid, kwid),
                )
                if not cur.fetchone():
                    raise ValueError("thread or keyword not owned by user")
                cur.execute(
                    """
                    INSERT INTO thread_keyword_weights (thread_id, user_keyword_id, activation, weight_multiplier)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (thread_id, user_keyword_id)
                    DO UPDATE SET
                        activation = EXCLUDED.activation,
                        weight_multiplier = EXCLUDED.weight_multiplier,
                        updated_at = now()
                    """,
                    (tid, kwid, act, mult),
                )
                conn.commit()

    def insert_source(
        self,
        user_id: str,
        url: str,
        title: str,
        lang: str,
        meta: Optional[Dict[str, Any]] = None,
        thread_id: Optional[str] = None,
    ) -> str:
        """
        Insert a new source or return existing source_id if already exists.
        
        Args:
            user_id: User identifier (UUID string or firebase_uid)
            url: Source URL
            title: Source title
            lang: Language code
            meta: Optional metadata dictionary
            thread_id: Optional interest_thread id; defaults to user's General thread when omitted
            
        Returns:
            source_id: The ID of the inserted or existing source
        """
        # Get or create user UUID
        user_uuid = self._get_or_create_user_id(user_id)
        default_tid = uuid.UUID(self.get_or_create_default_thread_id(user_id))
        thread_uuid = default_tid
        if thread_id:
            try:
                candidate = uuid.UUID(thread_id)
            except ValueError:
                candidate = default_tid
            else:
                thread_uuid = candidate

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                if thread_uuid != default_tid:
                    cur.execute(
                        "SELECT 1 FROM interest_threads WHERE id = %s AND user_id = %s",
                        (thread_uuid, user_uuid),
                    )
                    if not cur.fetchone():
                        thread_uuid = default_tid
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
                        INSERT INTO sources (user_id, url, title, lang, meta, thread_id)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            user_uuid,
                            url,
                            title,
                            lang,
                            psycopg.types.json.Jsonb(meta) if meta else None,
                            thread_uuid,
                        ),
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

    def insert_source_pdf_file(
        self, user_id: str, title: Optional[str] = None, thread_id: Optional[str] = None
    ) -> str:
        """
        Insert a new source for Local PDF upload (source_type=pdf_file, url=NULL).
        Caller must then upload to Storage and update meta (storage_path, original_filename).
        Returns source_id (UUID string).
        """
        user_uuid = self._get_or_create_user_id(user_id)
        default_tid = uuid.UUID(self.get_or_create_default_thread_id(user_id))
        thread_uuid = default_tid
        if thread_id:
            try:
                thread_uuid = uuid.UUID(thread_id)
            except ValueError:
                thread_uuid = default_tid
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                if thread_uuid != default_tid:
                    cur.execute(
                        "SELECT 1 FROM interest_threads WHERE id = %s AND user_id = %s",
                        (thread_uuid, user_uuid),
                    )
                    if not cur.fetchone():
                        thread_uuid = default_tid
                cur.execute(
                    """
                    INSERT INTO sources (user_id, source_type, status, url, title, lang, thread_id)
                    VALUES (%s, 'pdf_file', 'pending', NULL, %s, 'en', %s)
                    RETURNING id
                    """,
                    (user_uuid, title or "", thread_uuid),
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
        self,
        user_id: str,
        start_ts: datetime,
        end_ts: datetime,
        thread_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return sources for user where start_ts <= created_at < end_ts. For week-based S2.
        When thread_id is set, only sources with that interest_threads.id are included."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                q = """
                    SELECT id, created_at, thread_id FROM sources
                    WHERE user_id = %s AND created_at >= %s AND created_at < %s
                """
                params: List[Any] = [user_uuid, start_ts, end_ts]
                if thread_id:
                    try:
                        tid = uuid.UUID(thread_id)
                        q += " AND thread_id = %s"
                        params.append(tid)
                    except ValueError:
                        pass
                q += " ORDER BY created_at ASC"
                cur.execute(q, params)
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                out = []
                for row in rows:
                    d = dict(zip(cols, row))
                    d["id"] = str(d["id"])
                    if d.get("thread_id") is not None:
                        d["thread_id"] = str(d["thread_id"])
                    out.append(d)
                return out

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

    def delete_s2_for_user_week(self, user_id: str, week_start: str, thread_id: Optional[str] = None) -> int:
        """Delete existing S2 for user, week_start, and optional thread_id (extra.thread_id). Returns deleted count."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                if thread_id:
                    cur.execute(
                        """
                        DELETE FROM summaries
                        WHERE user_id = %s AND scope = 'topic' AND kind = 'S2'
                        AND extra->>'week_start' = %s AND extra->>'thread_id' = %s
                        """,
                        (user_uuid, week_start, thread_id),
                    )
                else:
                    cur.execute(
                        """
                        DELETE FROM summaries
                        WHERE user_id = %s AND scope = 'topic' AND kind = 'S2'
                        AND extra->>'week_start' = %s
                        AND (extra->>'thread_id' IS NULL OR extra->>'thread_id' = '')
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
        thread_id: Optional[str] = None,
    ) -> str:
        """Insert S2 (topic-scope) summary. source_id is NULL. extra has week_start, topic_name, source_ids, thread_id."""
        user_uuid = self._get_or_create_user_id(user_id)
        tid = thread_id or self.get_or_create_default_thread_id(user_id)
        extra = {"week_start": week_start, "topic_name": topic_name, "thread_id": tid}
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

    def get_s2_for_user_week(
        self, user_id: str, week_start: str, thread_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Return S2 for user, week_start, and thread_id (extra.thread_id). Uses default thread when thread_id is None."""
        user_uuid = self._get_or_create_user_id(user_id)
        tid = thread_id or self.get_or_create_default_thread_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, tldr, bullets, extra
                    FROM summaries
                    WHERE user_id = %s AND scope = 'topic' AND kind = 'S2'
                    AND extra->>'week_start' = %s
                    AND extra->>'thread_id' = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (user_uuid, week_start, tid),
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

    def get_source_by_id_for_user(self, source_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Load source by id if owned by the given user."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, url, source_type, status, title, lang, meta, pages, size_mb, char_count, fail_code, thread_id
                    FROM sources
                    WHERE id = %s AND user_id = %s
                    """,
                    (source_id, user_uuid),
                )
                row = cur.fetchone()
                if not row:
                    return None
                cols = [d[0] for d in cur.description]
                out = dict(zip(cols, row))
                out["id"] = str(out["id"])
                out["user_id"] = str(out["user_id"])
                if out.get("thread_id") is not None:
                    out["thread_id"] = str(out["thread_id"])
                if out.get("meta") is not None and hasattr(out["meta"], "copy"):
                    out["meta"] = dict(out["meta"])
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

    def claim_one_queued_job_for_user(self, user_id: str) -> Optional[str]:
        """Claim one queued job owned by the given user; set state='running'."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id FROM jobs
                    WHERE state = 'queued' AND user_id = %s
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """,
                    (user_uuid,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                job_id = str(row[0])
                cur.execute(
                    "UPDATE jobs SET state = 'running', updated_at = now() WHERE id = %s AND user_id = %s",
                    (job_id, user_uuid),
                )
                conn.commit()
                return job_id

    def count_jobs_for_user(
        self,
        user_id: str,
        job_type: Optional[str] = None,
        states: Optional[List[str]] = None,
    ) -> int:
        """Count jobs for a user, optionally filtered by type and states."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                q = "SELECT COUNT(*) FROM jobs WHERE user_id = %s"
                params: List[Any] = [user_uuid]
                if job_type:
                    q += " AND job_type = %s"
                    params.append(job_type)
                if states:
                    q += " AND state = ANY(%s)"
                    params.append(states)
                cur.execute(q, params)
                row = cur.fetchone()
                return int(row[0]) if row else 0

    def get_latest_job_created_at_for_user(
        self,
        user_id: str,
        job_type: Optional[str] = None,
        exclude_states: Optional[List[str]] = None,
    ) -> Optional[datetime]:
        """Return latest job created_at for a user, optionally filtered by type and excluding certain states."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                q = "SELECT created_at FROM jobs WHERE user_id = %s"
                params: List[Any] = [user_uuid]
                if job_type:
                    q += " AND job_type = %s"
                    params.append(job_type)
                if exclude_states:
                    placeholders = ", ".join(["%s"] * len(exclude_states))
                    q += f" AND state NOT IN ({placeholders})"
                    params.extend(exclude_states)
                q += " ORDER BY created_at DESC LIMIT 1"
                cur.execute(q, params)
                row = cur.fetchone()
                if not row or row[0] is None:
                    return None
                return row[0]

    def list_jobs_for_user(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        job_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List jobs for a user, newest first."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                q = """
                    SELECT id, user_id, job_type, state, progress, source_id, error, payload, created_at, updated_at
                    FROM jobs
                    WHERE user_id = %s
                """
                params: List[Any] = [user_uuid]
                if job_type:
                    q += " AND job_type = %s"
                    params.append(job_type)
                q += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])
                cur.execute(q, params)
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                out: List[Dict[str, Any]] = []
                for row in rows:
                    d = dict(zip(cols, row))
                    for key in ("id", "user_id", "source_id"):
                        if d.get(key) is not None:
                            d[key] = str(d[key])
                    for key in ("created_at", "updated_at"):
                        if d.get(key) is not None:
                            d[key] = d[key].isoformat() if hasattr(d[key], "isoformat") else str(d[key])
                    if d.get("payload") is not None and hasattr(d["payload"], "copy"):
                        d["payload"] = dict(d["payload"])
                    out.append(d)
                return out

    def get_ingest_failure_summary_for_user(
        self,
        user_id: str,
        days: int = 7,
        limit_recent: int = 5,
        limit_fail_codes: int = 3,
    ) -> Dict[str, Any]:
        """Return compact ingest failure summary for admin/debug use."""
        user_uuid = self._get_or_create_user_id(user_id)
        since_ts = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*), MAX(updated_at)
                    FROM sources
                    WHERE user_id = %s
                      AND status = 'failed'
                      AND updated_at >= %s
                    """,
                    (user_uuid, since_ts),
                )
                count_row = cur.fetchone()
                recent_failed_count = int(count_row[0]) if count_row and count_row[0] is not None else 0
                last_failed_at = count_row[1]

                cur.execute(
                    """
                    SELECT COALESCE(fail_code, 'UNKNOWN'), COUNT(*)
                    FROM sources
                    WHERE user_id = %s
                      AND status = 'failed'
                      AND updated_at >= %s
                    GROUP BY COALESCE(fail_code, 'UNKNOWN')
                    ORDER BY COUNT(*) DESC, COALESCE(fail_code, 'UNKNOWN') ASC
                    LIMIT %s
                    """,
                    (user_uuid, since_ts, limit_fail_codes),
                )
                top_fail_codes = [
                    {"fail_code": str(row[0]), "count": int(row[1])}
                    for row in cur.fetchall()
                ]

                cur.execute(
                    """
                    SELECT
                        s.id,
                        s.title,
                        s.url,
                        s.source_type,
                        s.fail_code,
                        s.updated_at,
                        j.id AS job_id,
                        j.error AS job_error,
                        j.updated_at AS job_updated_at
                    FROM sources s
                    LEFT JOIN LATERAL (
                        SELECT id, error, updated_at
                        FROM jobs
                        WHERE source_id = s.id AND job_type = 'ingest'
                        ORDER BY created_at DESC
                        LIMIT 1
                    ) j ON TRUE
                    WHERE s.user_id = %s
                      AND s.status = 'failed'
                      AND s.updated_at >= %s
                    ORDER BY s.updated_at DESC
                    LIMIT %s
                    """,
                    (user_uuid, since_ts, limit_recent),
                )
                cols = [d[0] for d in cur.description]
                recent_failures: List[Dict[str, Any]] = []
                for row in cur.fetchall():
                    d = dict(zip(cols, row))
                    for key in ("id", "job_id"):
                        if d.get(key) is not None:
                            d[key] = str(d[key])
                    for key in ("updated_at", "job_updated_at"):
                        if d.get(key) is not None:
                            d[key] = d[key].isoformat() if hasattr(d[key], "isoformat") else str(d[key])
                    recent_failures.append(
                        {
                            "source_id": d.get("id"),
                            "title": d.get("title"),
                            "url": d.get("url"),
                            "source_type": d.get("source_type"),
                            "fail_code": d.get("fail_code"),
                            "updated_at": d.get("updated_at"),
                            "job_id": d.get("job_id"),
                            "job_error": d.get("job_error"),
                        }
                    )

                return {
                    "window_days": days,
                    "recent_failed_count": recent_failed_count,
                    "last_failed_at": last_failed_at.isoformat() if hasattr(last_failed_at, "isoformat") else (str(last_failed_at) if last_failed_at else None),
                    "top_fail_codes": top_fail_codes,
                    "recent_failures": recent_failures,
                }

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
                    SELECT id, user_id, url, source_type, status, title, lang, meta, pages, size_mb, char_count, fail_code, thread_id
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
                if out.get("thread_id") is not None:
                    out["thread_id"] = str(out["thread_id"])
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
        thread_id: Optional[str] = None,
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
        if thread_id is not None:
            updates.append("thread_id = %s")
            if thread_id == "":
                params.append(None)
            else:
                try:
                    params.append(uuid.UUID(thread_id))
                except ValueError:
                    params.append(None)
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
        thread_id: Optional[str] = None,
    ) -> str:
        """Insert one recommendation row. Returns recommendation id."""
        user_uuid = self._get_or_create_user_id(user_id)
        tid = None
        if thread_id:
            try:
                tid = uuid.UUID(thread_id)
            except ValueError:
                tid = None
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO recommendations (user_id, topic_name, week_start, title, abstract, url, source, score, thread_id)
                    VALUES (%s, %s, %s::date, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_uuid, topic_name, week_start, title, abstract or "", url, source, score, tid),
                )
                row = cur.fetchone()
                conn.commit()
                return str(row[0])

    def list_recommendations(
        self,
        user_id: str,
        week_start: Optional[str] = None,
        topic_name: Optional[str] = None,
        thread_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List recommendations for user, newest first. Optional filter by week_start, topic_name, thread_id."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                q = """
                    SELECT id, topic_name, week_start, title, abstract, url, source, score, thread_id, created_at
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
                if thread_id:
                    try:
                        q += " AND thread_id = %s"
                        params.append(uuid.UUID(thread_id))
                    except ValueError:
                        pass
                q += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)
                cur.execute(q, params)
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                out = []
                for row in rows:
                    d = dict(zip(cols, row))
                    d["id"] = str(d["id"])
                    if d.get("thread_id") is not None:
                        d["thread_id"] = str(d["thread_id"])
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
                    SELECT id, topic_name, week_start, title, abstract, url, source, score, thread_id, created_at
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
                if d.get("thread_id") is not None:
                    d["thread_id"] = str(d["thread_id"])
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
        thread_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List notes for user, newest first. Optional filter by source_id, thread_id, or created_at >= since_ts."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                q = """
                    SELECT id, source_id, chunk_id, topic, content, thread_id, created_at
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
                if thread_id:
                    try:
                        q += " AND thread_id = %s"
                        params.append(uuid.UUID(thread_id))
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
                    for col in ("source_id", "chunk_id", "thread_id"):
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
        thread_id: Optional[str] = None,
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
        thread_uuid = None
        if thread_id:
            try:
                thread_uuid = uuid.UUID(thread_id)
            except ValueError:
                thread_uuid = None
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO notes (user_id, source_id, chunk_id, topic, content, thread_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, now())
                    RETURNING id
                    """,
                    (user_uuid, source_uuid, chunk_uuid, topic or None, content, thread_uuid),
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
        """Insert one feedback event. Returns feedback event id. Dedupes by (user_id, client_event_id) when provided."""
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
        ws = (week_start or "").strip() if week_start else None
        cleaned_week_start = ws if ws else None
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # ON CONFLICT: uq_feedback_events_client_event_id is partial (WHERE client_event_id IS NOT NULL).
                # Avoids race between SELECT-dedupe and INSERT that could raise UniqueViolation.
                cur.execute(
                    """
                    INSERT INTO feedback_events (
                        user_id, target_type, target_id, action, reasons, comment,
                        source_id, week_start, meta, client_event_id, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s::date, %s::jsonb, %s, now())
                    ON CONFLICT (client_event_id) WHERE client_event_id IS NOT NULL
                    DO NOTHING
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
                        cleaned_week_start,
                        psycopg.types.json.Json(cleaned_meta) if cleaned_meta is not None else None,
                        cleaned_client_event_id,
                    ),
                )
                row = cur.fetchone()
                if row is not None:
                    conn.commit()
                    return str(row[0])
                if cleaned_client_event_id:
                    cur.execute(
                        "SELECT id FROM feedback_events WHERE client_event_id = %s AND user_id = %s",
                        (cleaned_client_event_id, user_uuid),
                    )
                    existing = cur.fetchone()
                    conn.commit()
                    if existing:
                        return str(existing[0])
                conn.rollback()
                raise RuntimeError("feedback insert returned no id (unexpected)")

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

    def get_rag_run_for_user(self, user_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        """Return a rag_runs row for the user if run_id exists."""
        user_uuid = self._get_or_create_user_id(user_id)
        try:
            run_uuid = uuid.UUID(run_id)
        except ValueError:
            return None

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, query, top_k, topic, lang, status, latency_ms, error_message, created_at, completed_at
                    FROM rag_runs
                    WHERE id = %s AND user_id = %s
                    LIMIT 1
                    """,
                    (str(run_uuid), user_uuid),
                )
                row = cur.fetchone()
                if not row:
                    return None
                cols = [d[0] for d in cur.description]
                result = dict(zip(cols, row))
                for col in ("id", "user_id"):
                    if result.get(col) is not None:
                        result[col] = str(result[col])
                for col in ("created_at", "completed_at"):
                    if result.get(col) is not None and hasattr(result[col], "isoformat"):
                        result[col] = result[col].isoformat()
                return result

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

    def get_feedback_reason_breakdown(
        self,
        days: int = 30,
        limit: int = 10,
        target_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return top feedback reasons in the time window."""
        since_ts = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                query = """
                    SELECT reason, COUNT(*)
                    FROM (
                        SELECT jsonb_array_elements_text(reasons) AS reason
                        FROM feedback_events
                        WHERE created_at >= %s AND reasons IS NOT NULL
                """
                params: List[Any] = [since_ts]
                if target_type:
                    query += " AND target_type = %s"
                    params.append(target_type)
                query += """
                    ) r
                    GROUP BY reason
                    ORDER BY COUNT(*) DESC, reason ASC
                    LIMIT %s
                    """
                params.append(limit)
                cur.execute(query, params)
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

    def _table_exists(self, conn, table_name: str) -> bool:
        """Return True when the table exists in public schema."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = %s
                )
                """,
                (table_name,),
            )
            row = cur.fetchone()
            return bool(row and row[0])

    def get_alpha_kpi_snapshot(self, days: int = 7) -> Dict[str, Any]:
        """
        Return compact alpha KPI snapshot for dashboard use.

        KPI definitions are proxy metrics for operational monitoring.
        """
        window_days = max(1, int(days))
        since_ts = datetime.now(timezone.utc) - timedelta(days=window_days)
        since_retention_ts = since_ts - timedelta(days=8)

        with self._get_connection() as conn:
            rag_runs_exists = self._table_exists(conn, "rag_runs")
            rag_events_exists = self._table_exists(conn, "rag_events")

            with conn.cursor() as cur:
                # 1) Activation proxy: new users who ingested within 24h of signup.
                cur.execute(
                    """
                    SELECT
                        COUNT(*) AS new_users,
                        COUNT(*) FILTER (WHERE s_first.user_id IS NOT NULL) AS activated_new_users
                    FROM users u
                    LEFT JOIN LATERAL (
                        SELECT s.user_id
                        FROM sources s
                        WHERE s.user_id = u.id
                          AND s.created_at >= u.created_at
                          AND s.created_at < (u.created_at + INTERVAL '1 day')
                        LIMIT 1
                    ) s_first ON TRUE
                    WHERE u.created_at >= %s
                    """,
                    (since_ts,),
                )
                activation_row = cur.fetchone() or (0, 0)
                new_users = int(activation_row[0] or 0)
                activated_new_users = int(activation_row[1] or 0)
                activation_rate = round((activated_new_users / new_users), 4) if new_users else 0.0

                # 2) D1 / D7 retention proxy from first observed activity day.
                activity_union = """
                    SELECT user_id, DATE(created_at) AS day FROM sources WHERE created_at >= %s
                    UNION
                    SELECT user_id, DATE(created_at) AS day FROM jobs WHERE created_at >= %s
                    UNION
                    SELECT user_id, DATE(created_at) AS day FROM feedback_events WHERE created_at >= %s
                    UNION
                    SELECT user_id, DATE(created_at) AS day FROM recommendation_generation_runs WHERE created_at >= %s
                """
                activity_params: List[Any] = [since_retention_ts, since_retention_ts, since_retention_ts, since_retention_ts]
                if rag_runs_exists:
                    activity_union += """
                    UNION
                    SELECT user_id, DATE(created_at) AS day FROM rag_runs WHERE created_at >= %s
                    """
                    activity_params.append(since_retention_ts)

                retention_query = f"""
                    WITH activity_days AS (
                        {activity_union}
                    ),
                    first_day AS (
                        SELECT user_id, MIN(day) AS day0
                        FROM activity_days
                        GROUP BY user_id
                    ),
                    d1_base AS (
                        SELECT user_id, day0
                        FROM first_day
                        WHERE day0 <= (CURRENT_DATE - 2)
                    ),
                    d7_base AS (
                        SELECT user_id, day0
                        FROM first_day
                        WHERE day0 <= (CURRENT_DATE - 8)
                    ),
                    d1_retained AS (
                        SELECT COUNT(*) AS cnt
                        FROM d1_base b
                        WHERE EXISTS (
                            SELECT 1
                            FROM activity_days a
                            WHERE a.user_id = b.user_id
                              AND a.day >= (b.day0 + 1)
                              AND a.day < (b.day0 + 2)
                        )
                    ),
                    d7_retained AS (
                        SELECT COUNT(*) AS cnt
                        FROM d7_base b
                        WHERE EXISTS (
                            SELECT 1
                            FROM activity_days a
                            WHERE a.user_id = b.user_id
                              AND a.day >= (b.day0 + 7)
                              AND a.day < (b.day0 + 8)
                        )
                    )
                    SELECT
                        (SELECT COUNT(*) FROM d1_base) AS d1_base_count,
                        (SELECT cnt FROM d1_retained) AS d1_retained_count,
                        (SELECT COUNT(*) FROM d7_base) AS d7_base_count,
                        (SELECT cnt FROM d7_retained) AS d7_retained_count
                """
                cur.execute(retention_query, activity_params)
                d1_base, d1_retained, d7_base, d7_retained = cur.fetchone() or (0, 0, 0, 0)
                d1_base = int(d1_base or 0)
                d1_retained = int(d1_retained or 0)
                d7_base = int(d7_base or 0)
                d7_retained = int(d7_retained or 0)
                d1_rate = round((d1_retained / d1_base), 4) if d1_base else 0.0
                d7_rate = round((d7_retained / d7_base), 4) if d7_base else 0.0

                # 3) failed jobs in last 24h.
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM jobs
                    WHERE created_at >= (NOW() - INTERVAL '24 hours')
                      AND state = 'failed'
                    """
                )
                failed_jobs_24h = int((cur.fetchone() or [0])[0] or 0)

                # 4) cannot_answer rate (eval event based).
                cannot_answer_count = 0
                cannot_answer_base = 0
                cannot_answer_rate = None
                if rag_events_exists:
                    cur.execute(
                        """
                        SELECT
                            COUNT(*) FILTER (WHERE LOWER(COALESCE(data->>'cannot_answer', 'false')) = 'true') AS cannot_answer_count,
                            COUNT(*) AS total_eval_events
                        FROM rag_events
                        WHERE event_type = 'eval'
                          AND created_at >= %s
                        """,
                        (since_ts,),
                    )
                    c_row = cur.fetchone() or (0, 0)
                    cannot_answer_count = int(c_row[0] or 0)
                    cannot_answer_base = int(c_row[1] or 0)
                    cannot_answer_rate = round((cannot_answer_count / cannot_answer_base), 4) if cannot_answer_base else 0.0

                # 5) feedback volume by target type in window.
                cur.execute(
                    """
                    SELECT target_type, COUNT(*)
                    FROM feedback_events
                    WHERE created_at >= %s
                    GROUP BY target_type
                    """,
                    (since_ts,),
                )
                feedback_by_target = {str(row[0]): int(row[1]) for row in cur.fetchall()}

                # 6) recommendation action ratio from exact action events.
                cur.execute(
                    """
                    SELECT action, COUNT(*)
                    FROM feedback_events
                    WHERE created_at >= %s
                      AND target_type = 'recommendation'
                      AND action = ANY(%s)
                    GROUP BY action
                    """,
                    (since_ts, ["thumbs_up", "process", "remove"]),
                )
                rec_action_counts = {str(row[0]): int(row[1]) for row in cur.fetchall()}
                rec_accept = rec_action_counts.get("thumbs_up", 0)
                rec_process = rec_action_counts.get("process", 0)
                rec_remove = rec_action_counts.get("remove", 0)
                rec_total = rec_accept + rec_process + rec_remove
                recommendation_action_ratio = {
                    "accept_count": rec_accept,
                    "process_count": rec_process,
                    "remove_count": rec_remove,
                    "total": rec_total,
                    "accept_rate": round((rec_accept / rec_total), 4) if rec_total else 0.0,
                    "process_rate": round((rec_process / rec_total), 4) if rec_total else 0.0,
                    "remove_rate": round((rec_remove / rec_total), 4) if rec_total else 0.0,
                    "definition": "exact: accept=thumbs_up, process=process button, remove=remove button",
                }

                return {
                    "window_days": window_days,
                    "activation_proxy": {
                        "new_users": new_users,
                        "activated_new_users_24h": activated_new_users,
                        "activation_rate": activation_rate,
                    },
                    "retention_proxy": {
                        "d1_base_users": d1_base,
                        "d1_retained_users": d1_retained,
                        "d1_rate": d1_rate,
                        "d7_base_users": d7_base,
                        "d7_retained_users": d7_retained,
                        "d7_rate": d7_rate,
                    },
                    "failed_jobs_24h": failed_jobs_24h,
                    "cannot_answer": {
                        "available": rag_events_exists,
                        "count": cannot_answer_count,
                        "base": cannot_answer_base,
                        "rate": cannot_answer_rate,
                    },
                    "feedback_volume": {
                        "rag_answer": feedback_by_target.get("rag_answer", 0),
                        "summary_s2": feedback_by_target.get("summary_s2", 0),
                        "recommendation": feedback_by_target.get("recommendation", 0),
                    },
                    "recommendation_action_ratio": recommendation_action_ratio,
                }

    def get_feedback_dashboard_data(self, days: int = 30, limit: int = 20) -> Dict[str, Any]:
        """Return compact admin dashboard data for HTML and JSON endpoints."""
        summary = self.get_feedback_summary(days=days, limit_reasons=min(limit, 20))
        recent_negative = self.list_recent_negative_feedback_events(days=days, limit=limit)
        rag_top_reasons = self.get_feedback_reason_breakdown(
            days=days,
            limit=min(limit, 20),
            target_type="rag_answer",
        )
        return {
            "window_days": days,
            "summary": summary,
            "target_breakdown": self.get_feedback_target_type_breakdown(days=days),
            "recent_negative": recent_negative,
            "top_reasons": self.get_feedback_reason_breakdown(days=days, limit=min(limit, 20)),
            "rag_top_reasons": rag_top_reasons,
            "recommendation_rollup": self.get_recommendation_feedback_rollup(days=days, limit=limit),
            "s2_rollup": self.get_s2_feedback_rollup(days=days, limit=limit),
            "alpha_kpis": self.get_alpha_kpi_snapshot(days=min(days, 30)),
        }

    # ─── User Keywords (2-Stage Pipeline) ───

    def list_user_keywords(
        self, user_id: str, status: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List keywords for a user, optionally filtered by status."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                q = """
                    SELECT id, keyword, weight, source, status,
                           parent_keyword_id, accept_count,
                           paper_feedback_up, paper_feedback_down,
                           last_activity, rejected_at, created_at, updated_at
                    FROM user_keywords
                    WHERE user_id = %s
                """
                params: List[Any] = [user_uuid]
                if status:
                    q += " AND status = %s"
                    params.append(status)
                q += " ORDER BY weight DESC, updated_at DESC LIMIT %s"
                params.append(limit)
                cur.execute(q, params)
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                out = []
                for row in rows:
                    d = dict(zip(cols, row))
                    d["id"] = str(d["id"])
                    if d.get("parent_keyword_id") is not None:
                        d["parent_keyword_id"] = str(d["parent_keyword_id"])
                    for ts_col in ("last_activity", "rejected_at", "created_at", "updated_at"):
                        if d.get(ts_col) is not None:
                            d[ts_col] = d[ts_col].isoformat() if hasattr(d[ts_col], "isoformat") else str(d[ts_col])
                    out.append(d)
                return out

    def insert_user_keyword(
        self,
        user_id: str,
        keyword: str,
        source: str = "user_explicit",
        parent_keyword_id: Optional[str] = None,
        weight: float = 1.0,
    ) -> str:
        """Insert a user keyword. Returns keyword id."""
        user_uuid = self._get_or_create_user_id(user_id)
        parent_uuid = None
        if parent_keyword_id:
            try:
                parent_uuid = uuid.UUID(parent_keyword_id)
            except ValueError:
                pass
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_keywords (user_id, keyword, weight, source, parent_keyword_id)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_uuid, keyword.strip(), weight, source, parent_uuid),
                )
                row = cur.fetchone()
                conn.commit()
                return str(row[0])

    def update_user_keyword(
        self,
        keyword_id: str,
        user_id: str,
        weight: Optional[float] = None,
        status: Optional[str] = None,
        last_activity: Optional[datetime] = None,
        paper_feedback_up_incr: int = 0,
        paper_feedback_down_incr: int = 0,
        accept_count_incr: int = 0,
    ) -> bool:
        """Update keyword fields. Increments are added atomically. Returns True if updated."""
        try:
            kw_uuid = uuid.UUID(keyword_id)
        except ValueError:
            return False
        user_uuid = self._get_or_create_user_id(user_id)
        sets: List[str] = ["updated_at = now()"]
        params: List[Any] = []
        if weight is not None:
            sets.append("weight = %s")
            params.append(weight)
        if status is not None:
            sets.append("status = %s")
            params.append(status)
        if last_activity is not None:
            sets.append("last_activity = %s")
            params.append(last_activity)
        if paper_feedback_up_incr:
            sets.append("paper_feedback_up = paper_feedback_up + %s")
            params.append(paper_feedback_up_incr)
        if paper_feedback_down_incr:
            sets.append("paper_feedback_down = paper_feedback_down + %s")
            params.append(paper_feedback_down_incr)
        if accept_count_incr:
            sets.append("accept_count = accept_count + %s")
            params.append(accept_count_incr)
        params.extend([kw_uuid, user_uuid])
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE user_keywords SET {', '.join(sets)} WHERE id = %s AND user_id = %s",
                    params,
                )
                updated = cur.rowcount
                conn.commit()
                return updated > 0

    def archive_user_keyword(self, keyword_id: str, user_id: str) -> bool:
        """Soft-delete: set status='archived'. Returns True if updated."""
        return self.update_user_keyword(keyword_id, user_id, status="archived")

    # ─── Keyword Suggestions (Stage 1) ───

    def list_keyword_suggestions(
        self,
        user_id: str,
        status: Optional[str] = None,
        week_start: Optional[str] = None,
        thread_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """List keyword suggestions for a user."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                q = """
                    SELECT id, keyword, parent_keyword, suggestion_type, reason,
                           confidence, status, responded_at, source_run_id,
                           week_start, thread_id, created_at
                    FROM keyword_suggestions
                    WHERE user_id = %s
                """
                params: List[Any] = [user_uuid]
                if status:
                    q += " AND status = %s"
                    params.append(status)
                if week_start:
                    q += " AND week_start = %s"
                    params.append(week_start)
                if thread_id:
                    try:
                        q += " AND thread_id = %s"
                        params.append(uuid.UUID(thread_id))
                    except ValueError:
                        pass
                q += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)
                cur.execute(q, params)
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                out = []
                for row in rows:
                    d = dict(zip(cols, row))
                    d["id"] = str(d["id"])
                    if d.get("source_run_id") is not None:
                        d["source_run_id"] = str(d["source_run_id"])
                    if d.get("thread_id") is not None:
                        d["thread_id"] = str(d["thread_id"])
                    if d.get("week_start") is not None:
                        d["week_start"] = str(d["week_start"])
                    for ts_col in ("responded_at", "created_at"):
                        if d.get(ts_col) is not None:
                            d[ts_col] = d[ts_col].isoformat() if hasattr(d[ts_col], "isoformat") else str(d[ts_col])
                    out.append(d)
                return out

    def insert_keyword_suggestions(
        self,
        user_id: str,
        suggestions: List[Dict[str, Any]],
        week_start: str,
        source_run_id: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> List[str]:
        """Batch-insert keyword suggestions. Returns list of created ids."""
        user_uuid = self._get_or_create_user_id(user_id)
        run_uuid = None
        if source_run_id:
            try:
                run_uuid = uuid.UUID(source_run_id)
            except ValueError:
                pass
        thread_uuid = None
        if thread_id:
            try:
                thread_uuid = uuid.UUID(thread_id)
            except ValueError:
                thread_uuid = None
        ids = []
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                for s in suggestions:
                    cur.execute(
                        """
                        INSERT INTO keyword_suggestions
                            (user_id, keyword, parent_keyword, suggestion_type, reason,
                             confidence, week_start, source_run_id, thread_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            user_uuid,
                            s["keyword"],
                            s.get("parent_keyword"),
                            s.get("type", "derivative"),
                            s.get("reason", ""),
                            s.get("confidence", 0.5),
                            week_start,
                            run_uuid,
                            thread_uuid,
                        ),
                    )
                    row = cur.fetchone()
                    ids.append(str(row[0]))
                conn.commit()
        return ids

    def accept_keyword_suggestion(self, suggestion_id: str, user_id: str) -> Optional[str]:
        """Accept a suggestion: update status, create user_keyword, link thread_keyword_weights. Returns keyword_id or None."""
        try:
            sug_uuid = uuid.UUID(suggestion_id)
        except ValueError:
            return None
        user_uuid = self._get_or_create_user_id(user_id)
        kw_id_str: Optional[str] = None
        junction_thread_uuid: Optional[uuid.UUID] = None
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE keyword_suggestions
                    SET status = 'accepted', responded_at = now()
                    WHERE id = %s AND user_id = %s AND status = 'pending'
                    RETURNING keyword, parent_keyword, thread_id
                    """,
                    (sug_uuid, user_uuid),
                )
                row = cur.fetchone()
                if not row:
                    conn.rollback()
                    return None
                keyword, parent_keyword, sug_thread_id = row[0], row[1], row[2]
                junction_thread_uuid = sug_thread_id
                if junction_thread_uuid is None:
                    cur.execute(
                        "SELECT id FROM interest_threads WHERE user_id = %s AND is_default = true LIMIT 1",
                        (user_uuid,),
                    )
                    drow = cur.fetchone()
                    junction_thread_uuid = drow[0] if drow else None
                parent_kw_id = None
                if parent_keyword:
                    cur.execute(
                        "SELECT id FROM user_keywords WHERE user_id = %s AND lower(keyword) = lower(%s) AND status IN ('active','declining')",
                        (user_uuid, parent_keyword),
                    )
                    prow = cur.fetchone()
                    if prow:
                        parent_kw_id = prow[0]
                cur.execute(
                    "SELECT id FROM user_keywords WHERE user_id = %s AND lower(keyword) = lower(%s) AND status IN ('active','declining')",
                    (user_uuid, keyword),
                )
                existing = cur.fetchone()
                if existing:
                    cur.execute(
                        "UPDATE user_keywords SET accept_count = accept_count + 1, last_activity = now(), updated_at = now() WHERE id = %s RETURNING id",
                        (existing[0],),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO user_keywords (user_id, keyword, source, parent_keyword_id, weight)
                        VALUES (%s, %s, 'stage1_accepted', %s, 1.0)
                        RETURNING id
                        """,
                        (user_uuid, keyword, parent_kw_id),
                    )
                kw_row = cur.fetchone()
                if not kw_row:
                    conn.rollback()
                    return None
                kw_id_str = str(kw_row[0])
                if junction_thread_uuid is not None:
                    cur.execute(
                        """
                        INSERT INTO thread_keyword_weights (thread_id, user_keyword_id, activation, weight_multiplier)
                        VALUES (%s, %s, 1.0, 1.0)
                        ON CONFLICT (thread_id, user_keyword_id)
                        DO UPDATE SET
                            activation = GREATEST(thread_keyword_weights.activation, EXCLUDED.activation),
                            weight_multiplier = GREATEST(thread_keyword_weights.weight_multiplier, EXCLUDED.weight_multiplier),
                            updated_at = now()
                        """,
                        (junction_thread_uuid, kw_row[0]),
                    )
                conn.commit()
        return kw_id_str

    def reject_keyword_suggestion(self, suggestion_id: str, user_id: str) -> bool:
        """Reject a suggestion. Returns True if updated."""
        try:
            sug_uuid = uuid.UUID(suggestion_id)
        except ValueError:
            return False
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE keyword_suggestions
                    SET status = 'rejected', responded_at = now()
                    WHERE id = %s AND user_id = %s AND status = 'pending'
                    """,
                    (sug_uuid, user_uuid),
                )
                updated = cur.rowcount
                conn.commit()
                return updated > 0

    def get_rejected_keywords_within_days(self, user_id: str, days: int = 30) -> List[str]:
        """Get keywords rejected within last N days (for re-suggestion filtering)."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT lower(keyword)
                    FROM keyword_suggestions
                    WHERE user_id = %s AND status = 'rejected'
                      AND responded_at > now() - make_interval(days => %s)
                    """,
                    (user_uuid, days),
                )
                return [row[0] for row in cur.fetchall()]

    # ─── Recommendation Generation Runs ───

    def insert_recommendation_generation_run(
        self,
        user_id: str,
        week_start: str,
        stage: str,
        keyword_snapshot: List[Dict[str, Any]],
        candidate_count: int = 0,
        selected_count: int = 0,
        query_text: Optional[str] = None,
        selected_urls: Optional[List[str]] = None,
        score_breakdown: Optional[Dict[str, Any]] = None,
        stage1_suggestion_ids: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Insert a recommendation generation run. Returns run id."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO recommendation_generation_runs
                        (user_id, week_start, stage, keyword_snapshot,
                         candidate_count, selected_count, query_text,
                         selected_urls, score_breakdown, stage1_suggestion_ids, meta)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        user_uuid,
                        week_start,
                        stage,
                        psycopg.types.json.Jsonb(keyword_snapshot),
                        candidate_count,
                        selected_count,
                        query_text,
                        psycopg.types.json.Jsonb(selected_urls or []),
                        psycopg.types.json.Jsonb(score_breakdown or {}),
                        psycopg.types.json.Jsonb(stage1_suggestion_ids or []),
                        psycopg.types.json.Jsonb(meta or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return str(row[0])

    def get_active_keyword_snapshot(self, user_id: str) -> List[Dict[str, Any]]:
        """Get current active keyword set as a lightweight snapshot for runs/pipeline."""
        keywords = self.list_user_keywords(user_id, status="active")
        return [
            {"keyword": k["keyword"], "weight": float(k["weight"]), "source": k["source"]}
            for k in keywords
        ]

    # ─── Recommendation Generation Runs (Explanation / Debug) ───

    def list_recommendation_generation_runs(
        self, user_id: str, week_start: Optional[str] = None, stage: Optional[str] = None, limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """List recent recommendation generation runs for a user."""
        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                q = """
                    SELECT id, week_start, stage, keyword_snapshot,
                           candidate_count, selected_count, query_text,
                           selected_urls, score_breakdown, stage1_suggestion_ids,
                           meta, created_at
                    FROM recommendation_generation_runs
                    WHERE user_id = %s
                """
                params: List[Any] = [user_uuid]
                if week_start:
                    q += " AND week_start = %s::date"
                    params.append(week_start)
                if stage:
                    q += " AND stage = %s"
                    params.append(stage)
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

    def get_recommendation_explanation(
        self, recommendation_id: str, user_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Build explanation for a recommendation by matching its URL/week_start
        to a recommendation_generation_run's score_breakdown.
        """
        rec = self.get_recommendation_by_id(recommendation_id, user_id)
        if not rec:
            return None

        rec_url = (rec.get("url") or "").strip()
        rec_week = rec.get("week_start")

        user_uuid = self._get_or_create_user_id(user_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, week_start, stage, keyword_snapshot,
                           selected_urls, score_breakdown, stage1_suggestion_ids, meta, created_at
                    FROM recommendation_generation_runs
                    WHERE user_id = %s AND stage = 'stage2'
                      AND week_start = %s::date
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (user_uuid, rec_week),
                )
                row = cur.fetchone()
                if not row:
                    return {"recommendation_id": recommendation_id, "explanation": "no generation run found"}
                cols = [d[0] for d in cur.description]
                run = dict(zip(cols, row))

        score_breakdown = run.get("score_breakdown") or {}
        per_rec = score_breakdown.get("per_recommendation") or []
        matched_entry = next((p for p in per_rec if p.get("url") == rec_url), None)

        keyword_snapshot = run.get("keyword_snapshot") or []
        stage1_ids = run.get("stage1_suggestion_ids") or []

        return {
            "recommendation_id": recommendation_id,
            "week_start": str(run.get("week_start", "")),
            "stage": run.get("stage", "stage2"),
            "triggering_keywords": matched_entry.get("matched_keywords", []) if matched_entry else [],
            "keyword_snapshot": keyword_snapshot,
            "stage1_context": {
                "suggestion_ids": stage1_ids,
            },
            "score_breakdown": {
                "final_score": matched_entry.get("final_score") if matched_entry else None,
                "keyword_match": matched_entry.get("keyword_match") if matched_entry else None,
                "aggregate": {
                    "avg_base_score": score_breakdown.get("avg_base_score"),
                    "avg_keyword_match": score_breakdown.get("avg_keyword_match"),
                    "avg_final_score": score_breakdown.get("avg_final_score"),
                },
            },
            "meta": {
                "source": rec.get("source", "arXiv"),
                "run_id": str(run["id"]),
                "prompt_version": (run.get("meta") or {}).get("prompt_version"),
            },
        }

