"""Admin evaluation endpoints for S2 and recommendation quality analysis."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Header, Query, status
from pydantic import BaseModel

from ..db.repo import SupabaseRepo
from ..utils.llm_client import get_chat_client, get_model
from ..utils.summarization import create_s2_summary, create_s2_summary_v2

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/eval", tags=["admin-eval"])


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
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin secret")


JUDGE_SYSTEM = """You are an expert evaluator comparing two weekly learning summaries.
You will receive the SOURCE MATERIAL (S1 document summaries) and the USER CONTEXT
(keywords, notes), then two candidate summaries labeled [A] and [B].

Score each on 6 dimensions (1-5 scale):
- coverage: Does it cover all important topics from the source documents?
- insight_depth: Does it go beyond surface-level bullets to provide deeper understanding?
- personalization: Is it tailored to the user's keywords and learning interests?
- actionability: Does it suggest what to explore or learn next?
- structure: Is it well-organized and easy to read?
- coherence: Are cross-document connections and learning trajectory logical?

Respond in JSON only:
{
  "scores_a": {"coverage": N, "insight_depth": N, "personalization": N, "actionability": N, "structure": N, "coherence": N},
  "scores_b": {"coverage": N, "insight_depth": N, "personalization": N, "actionability": N, "structure": N, "coherence": N},
  "winner": "A" | "B" | "tie",
  "reasoning": "2-3 sentence explanation of why one is better"
}"""


def _format_summary(s: Dict[str, Any]) -> str:
    parts = []
    if s.get("tldr"):
        parts.append(f"TLDR: {s['tldr']}")
    for b in s.get("bullets", []):
        parts.append(f"• {b}")
    for sec in s.get("sections", []):
        parts.append(f"\n[{sec.get('keyword', '?')}] ({sec.get('doc_count', 0)} docs)")
        for ins in sec.get("insights", []):
            parts.append(f"  - {ins}")
    if s.get("emerging_topics"):
        parts.append(f"\nEmerging: {', '.join(s['emerging_topics'])}")
    for conn in s.get("connections", []):
        parts.append(f"\nConnection ({' ↔ '.join(conn.get('docs', []))}): {conn.get('insight', '')}")
    traj = s.get("trajectory")
    if isinstance(traj, dict):
        for k in ("deepened", "new_this_week", "paused"):
            items = traj.get(k, [])
            if items:
                parts.append(f"\nTrajectory [{k}]: {'; '.join(items)}")
    if s.get("reflection"):
        parts.append(f"\nReflection: {s['reflection']}")
    return "\n".join(parts)


def _load_s2_context(repo: SupabaseRepo, user_id: str, week_start: str) -> Dict[str, Any]:
    from ..services.s2_consolidation import _resolve_bounds
    now_utc = datetime.now(timezone.utc)
    norm_key, start_ts, end_ts, _ = _resolve_bounds(week_start, now_utc)

    sources = repo.get_sources_for_user_between(user_id, start_ts, end_ts)
    source_ids = [str(s["id"]) for s in sources]
    s1_list = repo.get_s1_summaries_for_sources(source_ids) if source_ids else []

    combined = []
    for row in s1_list:
        tldr = (row.get("tldr") or "").strip()
        if tldr:
            combined.append(tldr)
        for b in row.get("bullets") or []:
            if b:
                combined.append(str(b).strip())
    s1_text = "\n".join(combined)

    keywords = []
    try:
        keywords = repo.list_user_keywords(user_id, status="active")
    except Exception:
        pass

    notes_text = ""
    try:
        since = datetime.now(timezone.utc) - timedelta(days=30)
        notes = repo.list_notes_for_user(user_id, since_ts=since, limit=30, offset=0)
        notes_text = "\n".join(
            f"{(n.get('topic') or '')} {(n.get('content') or '')}".strip()
            for n in notes if (n.get("topic") or n.get("content"))
        )
    except Exception:
        pass

    feedback_text = ""
    try:
        fb_since = datetime.now(timezone.utc) - timedelta(days=30)
        fb_events = repo.list_recent_feedback_texts_for_user(user_id, since_ts=fb_since, limit=30)
        fb_parts = []
        for ev in fb_events:
            action = (ev.get("action") or "").strip()
            comment = (ev.get("comment") or "").strip()
            reasons = ev.get("reasons") or []
            if isinstance(reasons, list):
                reasons = ", ".join(str(r) for r in reasons if r)
            line = f"[{action}] {reasons} {comment}".strip()
            if line and line != "[]":
                fb_parts.append(line)
        feedback_text = "\n".join(fb_parts)
    except Exception:
        pass

    prev_s2_text = ""
    try:
        prev_key = (datetime.fromisoformat(norm_key) - timedelta(days=7)).date().isoformat()
        prev_s2 = repo.get_s2_for_user_week(user_id, prev_key)
        if prev_s2:
            parts = []
            if prev_s2.get("tldr"):
                parts.append(prev_s2["tldr"])
            for b in prev_s2.get("bullets") or []:
                if b:
                    parts.append(str(b).strip())
            prev_s2_text = "\n".join(parts)
    except Exception:
        pass

    return {
        "user_id": user_id,
        "week_start": norm_key,
        "s1_text": s1_text,
        "source_count": len(source_ids),
        "s1_count": len(s1_list),
        "keywords": keywords,
        "keyword_names": [k["keyword"] for k in keywords],
        "notes_text": notes_text,
        "feedback_text": feedback_text,
        "prev_s2_text": prev_s2_text,
    }


class S2EvalResponse(BaseModel):
    user_id: str
    week_start: str
    context_summary: Dict[str, Any]
    v1_summary: Dict[str, Any]
    v2_summary: Dict[str, Any]
    judge: Dict[str, Any]
    v1_gen_time_s: Optional[float] = None
    v2_gen_time_s: Optional[float] = None


@router.post("/s2", response_model=S2EvalResponse)
async def eval_s2(
    user_id: str = Query(..., description="Firebase UID or internal user_id"),
    week_start: str = Query(..., description="Week start YYYY-MM-DD"),
    x_admin_secret: Annotated[Optional[str], Header(alias="x-admin-secret")] = None,
    admin_secret: Optional[str] = Query(None, alias="secret"),
):
    """Generate v1 and v2 S2 summaries and run LLM-as-judge comparison."""
    _check_admin_secret(x_admin_secret, admin_secret)
    repo = SupabaseRepo()

    ctx = _load_s2_context(repo, user_id, week_start)
    if not ctx["s1_text"].strip():
        raise HTTPException(status_code=404, detail="No S1 text found for this user/week")

    t0 = time.time()
    v1 = create_s2_summary(ctx["s1_text"])
    v1_time = round(time.time() - t0, 1)

    t0 = time.time()
    v2 = create_s2_summary_v2(
        s1_text=ctx["s1_text"],
        keywords=ctx["keywords"],
        notes_text=ctx["notes_text"],
        feedback_text=ctx["feedback_text"],
        prev_s2_text=ctx["prev_s2_text"],
    )
    v2_time = round(time.time() - t0, 1)

    client = get_chat_client()
    model = get_model("s2_summary")
    kw_block = ", ".join(ctx["keyword_names"]) if ctx["keyword_names"] else "(no keywords)"
    a_text = _format_summary(v1)
    b_text = _format_summary(v2)
    prompt = f"""=== SOURCE MATERIAL ===
{ctx['s1_text'][:6000]}

=== USER KEYWORDS ===
{kw_block}

=== SUMMARY [A] ===
{a_text}

=== SUMMARY [B] ===
{b_text}

Score both summaries on the 6 dimensions and pick a winner. Respond in JSON only."""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    judge_result = json.loads(response.choices[0].message.content)

    for key in ("scores_a", "scores_b"):
        scores = judge_result.get(key, {})
        total = sum(scores.get(d, 0) for d in ("coverage", "insight_depth", "personalization", "actionability", "structure", "coherence"))
        scores["_total"] = total

    return S2EvalResponse(
        user_id=user_id,
        week_start=ctx["week_start"],
        context_summary={
            "source_count": ctx["source_count"],
            "s1_count": ctx["s1_count"],
            "keywords": ctx["keyword_names"],
            "has_notes": bool(ctx["notes_text"]),
            "has_feedback": bool(ctx["feedback_text"]),
            "has_prev_s2": bool(ctx["prev_s2_text"]),
        },
        v1_summary=v1,
        v2_summary=v2,
        judge=judge_result,
        v1_gen_time_s=v1_time,
        v2_gen_time_s=v2_time,
    )


class RecEvalResponse(BaseModel):
    user_id: str
    days: int
    generation_runs: Dict[str, Any]
    feedback: Dict[str, Any]
    keyword_impact: Dict[str, Any]
    keyword_hit_rate: Dict[str, Any]


@router.get("/recommendations", response_model=RecEvalResponse)
async def eval_recommendations(
    user_id: str = Query(..., description="Firebase UID or internal user_id"),
    days: int = Query(60, description="Analysis window in days"),
    x_admin_secret: Annotated[Optional[str], Header(alias="x-admin-secret")] = None,
    admin_secret: Optional[str] = Query(None, alias="secret"),
):
    """Analyze recommendation quality: scores, keyword impact, feedback correlation."""
    _check_admin_secret(x_admin_secret, admin_secret)
    repo = SupabaseRepo()

    from collections import defaultdict

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    runs = repo.list_recommendation_generation_runs(user_id, limit=100)
    runs = [r for r in runs if r.get("created_at") and r["created_at"] >= cutoff]

    feedback_events = repo.list_feedback_events(user_id=user_id, target_type="recommendation", limit=500)
    feedback_events = [e for e in feedback_events if e.get("created_at") and e["created_at"] >= cutoff]

    recommendations = repo.list_recommendations(user_id, limit=200)

    # ── Run analysis ──
    score_data: Dict[str, List[float]] = defaultdict(list)
    kw_counts = []
    has_kw = 0
    no_kw = 0
    for r in runs:
        snap = r.get("keyword_snapshot") or []
        kw_counts.append(len(snap))
        if snap:
            has_kw += 1
        else:
            no_kw += 1
        bd = r.get("score_breakdown") or {}
        for key in ("avg_base_score", "avg_keyword_match", "avg_negative_penalty", "avg_final_score"):
            if key in bd:
                score_data[key].append(bd[key])

    def _stats(vals):
        if not vals:
            return {}
        return {"count": len(vals), "mean": round(sum(vals)/len(vals), 4), "min": round(min(vals), 4), "max": round(max(vals), 4)}

    gen_analysis = {
        "total_runs": len(runs),
        "has_keyword_runs": has_kw,
        "no_keyword_runs": no_kw,
        "avg_keywords_per_run": round(sum(kw_counts)/len(kw_counts), 1) if kw_counts else 0,
        "score_stats": {k: _stats(v) for k, v in score_data.items()},
    }

    # ── Feedback analysis ──
    positive_actions = {"thumbs_up", "save", "bookmark"}
    negative_actions = {"thumbs_down", "dismiss", "not_relevant"}
    pos = neg = 0
    reason_counts: Dict[str, int] = defaultdict(int)
    for ev in feedback_events:
        action = (ev.get("action") or "").lower()
        if action in positive_actions:
            pos += 1
        elif action in negative_actions:
            neg += 1
        for r in (ev.get("reasons") or []):
            if r:
                reason_counts[str(r)] += 1

    rec_ids_with_fb = {str(ev.get("target_id", "")) for ev in feedback_events}
    fb_analysis = {
        "total_feedback": len(feedback_events),
        "positive": pos,
        "negative": neg,
        "positive_rate": round(pos / len(feedback_events), 3) if feedback_events else 0,
        "negative_rate": round(neg / len(feedback_events), 3) if feedback_events else 0,
        "total_recommendations": len(recommendations),
        "recommendations_with_feedback": len(rec_ids_with_fb),
        "coverage_rate": round(len(rec_ids_with_fb) / len(recommendations), 3) if recommendations else 0,
        "reason_distribution": dict(sorted(reason_counts.items(), key=lambda x: -x[1])[:15]),
    }

    # ── Keyword impact ──
    def _avg_scores(subset):
        if not subset:
            return {}
        keys = ("avg_base_score", "avg_keyword_match", "avg_negative_penalty", "avg_final_score")
        result = {}
        for k in keys:
            vals = [r.get("score_breakdown", {}).get(k, 0) for r in subset if r.get("score_breakdown")]
            if vals:
                result[k] = round(sum(vals)/len(vals), 4)
        return result

    kw_runs = [r for r in runs if r.get("keyword_snapshot")]
    no_kw_runs = [r for r in runs if not r.get("keyword_snapshot")]
    kw_impact = {
        "with_keywords": {"count": len(kw_runs), "scores": _avg_scores(kw_runs)},
        "without_keywords": {"count": len(no_kw_runs), "scores": _avg_scores(no_kw_runs)},
    }

    # ── Hit rate ──
    total_recs_scored = 0
    total_hits = 0
    kw_hit_counts: Dict[str, int] = defaultdict(int)
    for r in runs:
        for pr in (r.get("score_breakdown") or {}).get("per_recommendation") or []:
            total_recs_scored += 1
            matched = pr.get("matched_keywords") or []
            if matched:
                total_hits += 1
            for kw in matched:
                name = kw.get("keyword", str(kw)) if isinstance(kw, dict) else str(kw)
                kw_hit_counts[name] += 1

    hit_rate = {
        "total_scored": total_recs_scored,
        "with_match": total_hits,
        "hit_rate": round(total_hits / total_recs_scored, 3) if total_recs_scored else 0,
        "keyword_distribution": dict(sorted(kw_hit_counts.items(), key=lambda x: -x[1])[:20]),
    }

    return RecEvalResponse(
        user_id=user_id,
        days=days,
        generation_runs=gen_analysis,
        feedback=fb_analysis,
        keyword_impact=kw_impact,
        keyword_hit_rate=hit_rate,
    )
