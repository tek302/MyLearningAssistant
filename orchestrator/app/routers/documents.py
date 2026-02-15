"""
GET /documents: list latest sources for the current user (Week5 Day1).
"""
import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from ..db.pool import resolve_user_id, with_connection
from ..utils.deps import get_user_id

router = APIRouter(prefix="/documents", tags=["documents"])


def _list_sources(user_id: str, limit: int) -> list[dict[str, Any]]:
    """Sync: return latest N sources for user. Fields: id, title, url, source_type, status, pages, size_mb, fail_code, created_at, updated_at."""
    with with_connection() as conn:
        with conn.cursor() as cur:
            user_uuid = resolve_user_id(cur, user_id)
            cur.execute(
                """
                SELECT id, title, url, source_type, status, pages, size_mb, fail_code, created_at, updated_at
                FROM sources
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user_uuid, limit),
            )
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            out = []
            for row in rows:
                d = dict(zip(cols, row))
                d["id"] = str(d["id"])
                for ts in ("created_at", "updated_at"):
                    if d.get(ts) is not None:
                        d[ts] = d[ts].isoformat()
                out.append(d)
            return out


@router.get("")
async def list_documents(
    user_id: Annotated[str, Depends(get_user_id)],
    limit: int = Query(20, ge=1, le=100),
):
    """Return latest N sources for the current user."""
    items = await asyncio.to_thread(_list_sources, user_id, limit)
    return {"documents": items}
