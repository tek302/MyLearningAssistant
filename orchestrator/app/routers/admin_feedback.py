"""Admin feedback monitoring endpoints."""

from __future__ import annotations

import asyncio
import html
import os
from typing import Annotated, Optional

from fastapi import APIRouter, Header, HTTPException, Query, status
from fastapi.responses import HTMLResponse

from ..db.repo import SupabaseRepo

router = APIRouter(prefix="/admin/feedback", tags=["admin-feedback"])


def _check_admin_secret(secret_header: Optional[str], secret_query: Optional[str]) -> None:
    expected = (os.getenv("ADMIN_DASHBOARD_SECRET") or "").strip()
    if not expected:
        return
    if secret_header == expected or secret_query == expected:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _meta_cell(prompt_version: str, llm: str, embedding_model: str) -> str:
    parts = [
        f"prompt={html.escape(prompt_version or '-')}",
        f"llm={html.escape(llm or '-')}",
        f"embedding={html.escape(embedding_model or '-')}",
    ]
    return "<br>".join(parts)


def _cards_html(items: list[tuple[str, int]]) -> str:
    return "".join(
        f"<div class='card'><strong>{html.escape(label)}</strong><br>{value}</div>"
        for label, value in items
    )


def _negative_rows_html(items: list[dict]) -> str:
    return "".join(
        "<tr>"
        f"<td>{html.escape(item.get('created_at') or '')}</td>"
        f"<td>{html.escape(item.get('target_type') or '')}</td>"
        f"<td>{html.escape(item.get('action') or '')}</td>"
        f"<td>{html.escape(', '.join(item.get('reasons') or []))}</td>"
        f"<td>{html.escape(item.get('meta', {}).get('title') or item.get('meta', {}).get('topic_name') or '')}</td>"
        f"<td>{html.escape(item.get('week_start') or item.get('meta', {}).get('week_start') or '')}</td>"
        f"<td>{_meta_cell(item.get('meta', {}).get('prompt_version') or '', (item.get('meta', {}).get('model_snapshot') or {}).get('llm') or '', (item.get('meta', {}).get('model_snapshot') or {}).get('embedding_model') or '')}</td>"
        f"<td>{html.escape((item.get('comment') or '')[:160])}</td>"
        "</tr>"
        for item in items
    ) or "<tr><td colspan='8'>No recent negative feedback</td></tr>"


def _reason_rows_html(items: list[dict]) -> str:
    return "".join(
        "<tr>"
        f"<td>{html.escape(item.get('reason') or '')}</td>"
        f"<td>{int(item.get('count') or 0)}</td>"
        "</tr>"
        for item in items
    ) or "<tr><td colspan='2'>No reasons yet</td></tr>"


def _rollup_rows_html(items: list[dict], label_key: str) -> str:
    return "".join(
        "<tr>"
        f"<td>{html.escape(item.get(label_key) or '')}</td>"
        f"<td>{int(item.get('thumbs_down_count') or 0)}</td>"
        f"<td>{int(item.get('thumbs_up_count') or 0)}</td>"
        f"<td>{int(item.get('total_count') or 0)}</td>"
        f"<td>{_meta_cell(item.get('prompt_version') or '', item.get('llm') or '', item.get('embedding_model') or '')}</td>"
        f"<td>{html.escape(item.get('latest_created_at') or '')}</td>"
        "</tr>"
        for item in items
    ) or "<tr><td colspan='6'>No rollup data yet</td></tr>"


def _s2_rollup_rows_html(items: list[dict]) -> str:
    return "".join(
        "<tr>"
        f"<td>{html.escape(item.get('week_start') or '')}</td>"
        f"<td>{html.escape(item.get('topic_name') or '')}</td>"
        f"<td>{int(item.get('thumbs_down_count') or 0)}</td>"
        f"<td>{int(item.get('thumbs_up_count') or 0)}</td>"
        f"<td>{int(item.get('total_count') or 0)}</td>"
        f"<td>{_meta_cell(item.get('prompt_version') or '', item.get('llm') or '', item.get('embedding_model') or '')}</td>"
        f"<td>{html.escape(item.get('latest_created_at') or '')}</td>"
        "</tr>"
        for item in items
    ) or "<tr><td colspan='7'>No S2 rollup data yet</td></tr>"


@router.get("/summary")
async def admin_feedback_summary(
    x_admin_secret: Annotated[Optional[str], Header()] = None,
    secret: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
):
    """Return aggregate feedback summary for admin use."""
    _check_admin_secret(x_admin_secret, secret)
    repo = SupabaseRepo()
    return await asyncio.to_thread(repo.get_feedback_summary, days, 10)


@router.get("/events")
async def admin_feedback_events(
    x_admin_secret: Annotated[Optional[str], Header()] = None,
    secret: Optional[str] = Query(None),
    target_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Return recent feedback events for admin inspection."""
    _check_admin_secret(x_admin_secret, secret)
    repo = SupabaseRepo()
    items = await asyncio.to_thread(
        repo.list_feedback_events,
        None,
        target_type,
        None,
        limit,
        0,
    )
    return {"events": items}


@router.get("/dashboard-data")
async def admin_feedback_dashboard_data(
    x_admin_secret: Annotated[Optional[str], Header()] = None,
    secret: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
):
    """Return compact admin dashboard data for HTML and manual inspection."""
    _check_admin_secret(x_admin_secret, secret)
    repo = SupabaseRepo()
    data = await asyncio.to_thread(repo.get_feedback_dashboard_data, days, limit)
    last_7 = await asyncio.to_thread(repo.get_feedback_summary, 7, min(limit, 20))
    data["summary_last_7_days"] = last_7
    return data


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_feedback_dashboard(
    x_admin_secret: Annotated[Optional[str], Header()] = None,
    secret: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
):
    """Simple read-only HTML dashboard for feedback monitoring."""
    _check_admin_secret(x_admin_secret, secret)
    repo = SupabaseRepo()
    data = await asyncio.to_thread(repo.get_feedback_dashboard_data, days, limit)
    last_7 = await asyncio.to_thread(repo.get_feedback_summary, 7, min(limit, 20))
    summary = data.get("summary", {})
    totals = summary.get("totals", {})
    actions = summary.get("actions", {})
    cards_html = _cards_html([
        ("Window total", totals.get("all", 0)),
        ("Last 7 days", last_7.get("totals", {}).get("all", 0)),
        ("S2 summary", totals.get("summary_s2", 0)),
        ("S1 summary", totals.get("summary_s1", 0)),
        ("Recommendations", totals.get("recommendation", 0)),
        ("Thumbs up", actions.get("thumbs_up", 0)),
        ("Thumbs down", actions.get("thumbs_down", 0)),
    ])
    return f"""
    <html>
      <head>
        <title>Feedback Dashboard</title>
        <style>
          body {{ font-family: Arial, sans-serif; margin: 24px; }}
          .cards {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 24px; }}
          .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 16px; min-width: 180px; }}
          .section {{ margin-top: 24px; }}
          table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
          th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }}
          th {{ background: #f5f5f5; }}
          .muted {{ color: #666; }}
        </style>
      </head>
      <body>
        <h1>Feedback Dashboard</h1>
        <p>Window: last {days} days | Limit: {limit}</p>
        <div class="cards">{cards_html}</div>

        <div class="section">
          <h2>Top Reasons</h2>
          <table>
            <thead><tr><th>Reason</th><th>Count</th></tr></thead>
            <tbody>{_reason_rows_html(data.get("top_reasons", []))}</tbody>
          </table>
        </div>

        <div class="section">
          <h2>Recent Negative Feedback</h2>
          <p class="muted">Shows recent thumbs down / dismiss events with metadata snapshot.</p>
          <table>
            <thead>
              <tr>
                <th>Created</th>
                <th>Target</th>
                <th>Action</th>
                <th>Reasons</th>
                <th>Title/Topic</th>
                <th>Week</th>
                <th>Generation Meta</th>
                <th>Comment</th>
              </tr>
            </thead>
            <tbody>{_negative_rows_html(data.get("recent_negative", []))}</tbody>
          </table>
        </div>

        <div class="section">
          <h2>Recommendation Rollup</h2>
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>Thumbs Down</th>
                <th>Thumbs Up</th>
                <th>Total</th>
                <th>Generation Meta</th>
                <th>Latest Feedback</th>
              </tr>
            </thead>
            <tbody>{_rollup_rows_html(data.get("recommendation_rollup", []), "title")}</tbody>
          </table>
        </div>

        <div class="section">
          <h2>S2 Week Rollup</h2>
          <table>
            <thead>
              <tr>
                <th>Week Start</th>
                <th>Topic</th>
                <th>Thumbs Down</th>
                <th>Thumbs Up</th>
                <th>Total</th>
                <th>Generation Meta</th>
                <th>Latest Feedback</th>
              </tr>
            </thead>
            <tbody>{_s2_rollup_rows_html(data.get("s2_rollup", []))}</tbody>
          </table>
        </div>
      </body>
    </html>
    """

