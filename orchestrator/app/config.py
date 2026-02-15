"""Configuration module for environment variables."""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def load_env() -> str:
    """Load .env from orchestrator dir. Does not override existing shell env vars."""
    base_dir = Path(__file__).resolve().parents[1]
    dotenv_path = base_dir / ".env"
    load_dotenv(dotenv_path=dotenv_path, override=False)
    return str(dotenv_path)


def get_database_url() -> str:
    """Return DATABASE_URL or SUPABASE_DB_URL; raise if unset."""
    url = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError("DATABASE_URL or SUPABASE_DB_URL environment variable is not set")
    return url


def get_judge_enabled() -> bool:
    """
    Get whether LLM judge is enabled from environment variable.
    
    Returns:
        bool: True if JUDGE_ENABLED is set to "true" (case-insensitive), False otherwise
    """
    value = os.getenv("JUDGE_ENABLED", "false")
    return value.lower() in ("true", "1", "yes")


def get_judge_model() -> str:
    """
    Get judge model from environment variable.
    
    Defaults to existing cheap model setting if present (e.g., from SUMMARY_MODEL),
    otherwise uses a placeholder string.
    
    Returns:
        str: Model name for judge evaluation
    """
    # Try JUDGE_MODEL first
    judge_model = os.getenv("JUDGE_MODEL")
    if judge_model:
        return judge_model
    
    # Fallback to SUMMARY_MODEL if available (cheap model)
    summary_model = os.getenv("SUMMARY_MODEL")
    if summary_model:
        return summary_model
    
    # Default placeholder (can be overridden by env)
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def get_judge_threshold_overall() -> float:
    """
    Get overall judge threshold from environment variable.
    
    Returns:
        float: Overall score threshold (default: 0.75)
    """
    try:
        value = os.getenv("JUDGE_THRESHOLD_OVERALL")
        if value:
            return max(0.0, min(1.0, float(value)))
    except (ValueError, TypeError):
        pass
    return 0.75


def get_judge_threshold_faithfulness() -> float:
    """
    Get faithfulness judge threshold from environment variable.
    
    Returns:
        float: Faithfulness score threshold (default: 0.80)
    """
    try:
        value = os.getenv("JUDGE_THRESHOLD_FAITHFULNESS")
        if value:
            return max(0.0, min(1.0, float(value)))
    except (ValueError, TypeError):
        pass
    return 0.80


def get_judge_threshold_coverage() -> float:
    """
    Get coverage judge threshold from environment variable.
    
    Returns:
        float: Coverage score threshold (default: 0.70)
    """
    try:
        value = os.getenv("JUDGE_THRESHOLD_COVERAGE")
        if value:
            return max(0.0, min(1.0, float(value)))
    except (ValueError, TypeError):
        pass
    return 0.70


def get_graph_recursion_limit() -> int:
    """
    Get graph recursion limit from environment variable.
    
    This limit prevents runaway LangGraph loops by capping the maximum number
    of graph execution steps.
    
    Returns:
        int: Maximum recursion limit (default: 50)
    """
    try:
        value = os.getenv("GRAPH_RECURSION_LIMIT")
        if value:
            limit = int(value)
            # Ensure reasonable bounds (min 10, max 200)
            return max(10, min(200, limit))
    except (ValueError, TypeError):
        pass
    return 50

