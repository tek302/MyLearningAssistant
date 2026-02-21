"""
Connection pool for PostgreSQL using psycopg_pool.ConnectionPool.

Uses get_database_url from config. Context managers only; no ORM.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Optional

from psycopg import Cursor
from psycopg_pool import ConnectionPool

from app.config import get_database_url

_pool: Optional[ConnectionPool] = None


def init_pool(min_size: int = 1, max_size: int = 10, **kwargs) -> ConnectionPool:
    """Create and open the connection pool. Call once at app startup."""
    global _pool
    if _pool is not None:
        return _pool
    _pool = ConnectionPool(
        conninfo=get_database_url(),
        min_size=min_size,
        max_size=max_size,
        open=True,
        **kwargs,
    )
    return _pool


def close_pool() -> None:
    """Close the pool. Call at app shutdown."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def get_pool() -> ConnectionPool:
    """Return the global pool. Raises if init_pool() was not called."""
    if _pool is None:
        raise RuntimeError("Connection pool not initialized; call init_pool() first")
    return _pool


@contextmanager
def with_connection():
    """Context manager: yields a connection from the pool. Commits on exit, rolls back on exception."""
    pool = get_pool()
    with pool.connection() as conn:
        yield conn


def resolve_user_id(cur: Cursor, firebase_uid: str) -> str:
    """
    Get user UUID from users table, or create if missing.
    Treats firebase_uid as the canonical user identifier.
    Returns UUID string.
    """
    cur.execute(
        """
        INSERT INTO users (firebase_uid)
        VALUES (%s)
        ON CONFLICT (firebase_uid)
        DO UPDATE SET firebase_uid = EXCLUDED.firebase_uid
        RETURNING id
        """,
        (firebase_uid,),
    )
    row = cur.fetchone()
    return str(row[0])
