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


def _is_local_mode() -> bool:
    app_env = (os.getenv("APP_ENV") or "").strip().lower()
    debug = (os.getenv("DEBUG") or "").strip().lower() in ("true", "1", "yes")
    return app_env == "local" or debug


def _check_admin_secret(secret_header: Optional[str], secret_query: Optional[str]) -> None:
    expected = (os.getenv("ADMIN_DASHBOARD_SECRET") or "").strip()
    if not expected:
        if _is_local_mode():
            return
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Admin dashboard secret not configured")
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


def _pct(v: Optional[float]) -> str:
    if v is None:
        return "-"
    try:
        return f"{float(v) * 100:.1f}%"
    except Exception:
        return "-"


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


@router.get("/kpi")
async def admin_feedback_kpi(
    x_admin_secret: Annotated[Optional[str], Header()] = None,
    secret: Optional[str] = Query(None),
    days: int = Query(7, ge=1, le=30),
):
    """Return alpha KPI snapshot (single-view operational metrics)."""
    _check_admin_secret(x_admin_secret, secret)
    repo = SupabaseRepo()
    return await asyncio.to_thread(repo.get_alpha_kpi_snapshot, days)


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
    alpha = data.get("alpha_kpis", {}) or {}
    activation = alpha.get("activation_proxy", {}) or {}
    retention = alpha.get("retention_proxy", {}) or {}
    cannot_answer = alpha.get("cannot_answer", {}) or {}
    feedback_volume = alpha.get("feedback_volume", {}) or {}
    rec_ratio = alpha.get("recommendation_action_ratio", {}) or {}
    summary = data.get("summary", {})
    totals = summary.get("totals", {})
    actions = summary.get("actions", {})
    cards_html = _cards_html([
        ("Window total", totals.get("all", 0)),
        ("Last 7 days", last_7.get("totals", {}).get("all", 0)),
        ("S2 summary", totals.get("summary_s2", 0)),
        ("S1 summary", totals.get("summary_s1", 0)),
        ("Recommendations", totals.get("recommendation", 0)),
        ("RAG answers", totals.get("rag_answer", 0)),
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
          <h2>Alpha KPI Snapshot</h2>
          <table>
            <thead><tr><th>KPI</th><th>Value</th><th>Definition</th></tr></thead>
            <tbody>
              <tr><td>Activation proxy</td><td>{int(activation.get("activated_new_users_24h", 0))} / {int(activation.get("new_users", 0))} ({_pct(activation.get("activation_rate"))})</td><td>new users who ingested within 24h</td></tr>
              <tr><td>D1 retention proxy</td><td>{int(retention.get("d1_retained_users", 0))} / {int(retention.get("d1_base_users", 0))} ({_pct(retention.get("d1_rate"))})</td><td>activity on day+1 from first active day</td></tr>
              <tr><td>D7 retention proxy</td><td>{int(retention.get("d7_retained_users", 0))} / {int(retention.get("d7_base_users", 0))} ({_pct(retention.get("d7_rate"))})</td><td>activity on day+7 from first active day</td></tr>
              <tr><td>failed jobs (24h)</td><td>{int(alpha.get("failed_jobs_24h", 0))}</td><td>jobs.state='failed' in last 24h</td></tr>
              <tr><td>cannot_answer rate</td><td>{int(cannot_answer.get("count", 0))} / {int(cannot_answer.get("base", 0))} ({_pct(cannot_answer.get("rate"))})</td><td>rag_events eval cannot_answer=true</td></tr>
              <tr><td>feedback volume</td><td>RAG={int(feedback_volume.get("rag_answer", 0))}, S2={int(feedback_volume.get("summary_s2", 0))}, Rec={int(feedback_volume.get("recommendation", 0))}</td><td>window target counts</td></tr>
              <tr><td>recommendation ratio</td><td>A={int(rec_ratio.get("accept_count", 0))} / P={int(rec_ratio.get("process_count", 0))} / R={int(rec_ratio.get("remove_count", 0))}</td><td>{html.escape(str(rec_ratio.get("definition", "")))}</td></tr>
            </tbody>
          </table>
        </div>

        <div class="section">
          <h2>Top Reasons</h2>
          <table>
            <thead><tr><th>Reason</th><th>Count</th></tr></thead>
            <tbody>{_reason_rows_html(data.get("top_reasons", []))}</tbody>
          </table>
        </div>

        <div class="section">
          <h2>Top RAG Reasons</h2>
          <p class="muted">RAG target_type=`rag_answer` 기준 상위 reason 집계.</p>
          <table>
            <thead><tr><th>Reason</th><th>Count</th></tr></thead>
            <tbody>{_reason_rows_html(data.get("rag_top_reasons", []))}</tbody>
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

