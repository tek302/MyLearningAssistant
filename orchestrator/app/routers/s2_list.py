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


def _list_s2_for_user(user_id: str, week_start: str | None, limit: int) -> List[dict[str, Any]]:
    """Sync: return S2 summaries for user, optionally filtered by week_start."""
    with with_connection() as conn:
        with conn.cursor() as cur:
            user_uuid = resolve_user_id(cur, user_id)
            if week_start:
                cur.execute(
                    """
                    SELECT id, tldr, bullets, extra, created_at
                    FROM summaries
                    WHERE user_id = %s AND scope = 'topic' AND kind = 'S2'
                    AND extra->>'week_start' = %s
                    ORDER BY (extra->>'week_start') DESC NULLS LAST, created_at DESC
                    LIMIT %s
                    """,
                    (user_uuid, week_start, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT id, tldr, bullets, extra, created_at
                    FROM summaries
                    WHERE user_id = %s AND scope = 'topic' AND kind = 'S2'
                    ORDER BY (extra->>'week_start') DESC NULLS LAST, created_at DESC
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
    limit: int = Query(10, ge=1, le=50),
):
    """Return S2 summaries for the current user. Optional week_start filter."""
    items = await asyncio.to_thread(_list_s2_for_user, user_id, week_start, limit)
    return {"summaries": items}
