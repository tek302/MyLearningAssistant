"""
GET /documents: list latest sources for the current user (Week5 Day1).
"""
import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from ..db.pool import resolve_user_id, with_connection
from ..utils.deps import get_user_id

router = APIRouter(prefix="/documents", tags=["documents"])


def _list_sources(
    user_id: str,
    limit: int,
    offset: int = 0,
    include_summary: bool = False,
) -> list[dict[str, Any]]:
    """Sync: return latest N sources for user with optional S1 summary (tldr, bullets)."""
    with with_connection() as conn:
        with conn.cursor() as cur:
            user_uuid = resolve_user_id(cur, user_id)
            if include_summary:
                cur.execute(
                    """
                    SELECT s.id, s.title, s.url, s.source_type, s.status, s.pages, s.size_mb, s.fail_code,
                           s.created_at, s.updated_at,
                           sm.tldr, sm.bullets
                    FROM sources s
                    LEFT JOIN summaries sm ON sm.source_id = s.id AND sm.scope = 'doc' AND sm.kind = 'S1'
                    WHERE s.user_id = %s
                    ORDER BY s.created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (user_uuid, limit, offset),
                )
            else:
                cur.execute(
                    """
                    SELECT id, title, url, source_type, status, pages, size_mb, fail_code,
                           created_at, updated_at
                    FROM sources
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (user_uuid, limit, offset),
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
                if include_summary and "bullets" in d and d["bullets"] is not None:
                    # bullets is jsonb; ensure list of strings
                    b = d["bullets"]
                    d["bullets"] = b if isinstance(b, list) else []
                elif include_summary:
                    d["tldr"] = d.get("tldr")
                    d["bullets"] = d.get("bullets") or []
                out.append(d)
            return out


@router.get("")
async def list_documents(
    user_id: Annotated[str, Depends(get_user_id)],
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_summary: bool = Query(False, description="Include S1 summary (tldr, bullets) per document"),
):
    """Return latest N sources for the current user, with optional pagination and summary."""
    items = await asyncio.to_thread(_list_sources, user_id, limit, offset, include_summary)
    return {"documents": items}
