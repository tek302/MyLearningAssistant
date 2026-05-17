"""
GET /s2: list S2 (topic-scope) summaries for current user.
"""
import asyncio
import logging
from typing import Annotated, Any, List

from fastapi import APIRouter, Depends, Query

from ..db.pool import resolve_user_id, with_connection
from ..utils.deps import get_user_id

logger = logging.getLogger(__name__)
router = APIRouter(tags=["s2"])


def _list_s2_for_user(
    user_id: str, week_start: str | None, thread_id: str | None, limit: int,
) -> List[dict[str, Any]]:
    """Sync: return S2 summaries for user, optionally filtered by week_start and/or thread_id (extra.thread_id)."""
    import uuid as _uuid
    with with_connection() as conn:
        with conn.cursor() as cur:
            user_uuid = resolve_user_id(cur, user_id)
            thread_clause = ""
            params: list = [user_uuid]
            if week_start:
                thread_clause += " AND extra->>'week_start' = %s"
                params.append(week_start)
            if thread_id:
                try:
                    _uuid.UUID(thread_id)
                    thread_clause += " AND extra->>'thread_id' = %s"
                    params.append(thread_id)
                except ValueError:
                    pass
            params.append(limit)
            cur.execute(
                f"""
                SELECT id, tldr, bullets, extra, created_at
                FROM summaries
                WHERE user_id = %s AND scope = 'topic' AND kind = 'S2'
                {thread_clause}
                ORDER BY (extra->>'week_start') DESC NULLS LAST, created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            out = []
            for row in rows:
                d = dict(zip(cols, row))
                d["id"] = str(d["id"])
                if d.get("created_at") is not None:
                    d["created_at"] = d["created_at"].isoformat()
                if d.get("extra") is not None and hasattr(d["extra"], "copy"):
                    d["extra"] = dict(d["extra"])
                out.append(d)
            return out


@router.get("/s2")
async def list_s2(
    user_id: Annotated[str, Depends(get_user_id)],
    week_start: str | None = Query(None, description="Filter by summaries.extra.week_start (ET Friday or legacy UTC Monday)"),
    thread_id: str | None = Query(None, description="Filter by summaries.extra.thread_id"),
    limit: int = Query(10, ge=1, le=50),
):
    """Return S2 summaries for the current user. Optional week_start and thread_id filters."""
    items = await asyncio.to_thread(_list_s2_for_user, user_id, week_start, thread_id, limit)
    return {"summaries": items}
