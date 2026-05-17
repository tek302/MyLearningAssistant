"""
Merge global user_keywords with per-thread junction weights (design B).
Used by Stage1/Stage2/S2 v2 context when thread_id is set.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

# Keywords with no junction row for this thread still contribute at reduced weight.
THREAD_KEYWORD_FALLBACK_FACTOR = 0.35


def parse_thread_weights(rows: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float]]:
    """Map user_keyword_id -> (activation, weight_multiplier)."""
    out: Dict[str, Tuple[float, float]] = {}
    for r in rows:
        kid = r.get("user_keyword_id")
        if kid is None:
            continue
        act = float(r.get("activation") or 0.0)
        mult = float(r.get("weight_multiplier") or 1.0)
        out[str(kid)] = (act, mult)
    return out


def build_effective_keywords(
    global_keywords: List[Dict[str, Any]],
    thread_weights: Dict[str, Tuple[float, float]],
) -> List[Dict[str, Any]]:
    """
    Return copies of keyword dicts with `weight` adjusted for thread context.
    Sorted by effective weight descending.
    """
    merged: List[Dict[str, Any]] = []
    for k in global_keywords:
        kid = str(k.get("id") or "")
        base_w = float(k.get("weight") or 1.0)
        row = dict(k)
        if kid in thread_weights:
            act, mult = thread_weights[kid]
            row["weight"] = base_w * mult * max(float(act), 0.05)
        else:
            row["weight"] = base_w * THREAD_KEYWORD_FALLBACK_FACTOR
        merged.append(row)
    merged.sort(key=lambda x: float(x.get("weight") or 0), reverse=True)
    return merged
