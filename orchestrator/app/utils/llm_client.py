"""
Central LLM client factory.

Supports per-function model selection and provider switching (OpenAI / Gemini).
Gemini uses the OpenAI-compatible endpoint so the same `openai` SDK works for both.

Priority for model resolution:
  1. Function-specific env var (e.g. S1_MODEL)
  2. SUMMARY_MODEL (global fallback for backward compat)
  3. Hardcoded per-function default

Provider: LLM_PROVIDER env var ("openai" or "gemini"). Default "openai".
Embeddings always use OpenAI regardless of LLM_PROVIDER (to avoid re-embedding).

Timeouts: LLM_TIMEOUT_SECONDS env var (default 120). Keeps individual API calls
from blocking the entire Cloud Run request budget.
"""

import os

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_LLM_TIMEOUT_SECONDS = 120

_DEFAULTS = {
    "s1_summary":        "gpt-4.1",
    "s2_summary":        "gpt-4.1",
    "keyword_expansion": "gpt-4.1",
    "rag_synthesis":     "gpt-4.1-mini",
    "rag_retry":         "gpt-4.1-mini",
    "rag_judge":         "gpt-4.1-mini",
    "rag_rewrite":       "gpt-4.1-mini",
    "default":           "gpt-4.1-mini",
}

_ENV_VARS = {
    "s1_summary":        "S1_MODEL",
    "s2_summary":        "S2_MODEL",
    "keyword_expansion": "KEYWORD_EXPANSION_MODEL",
    "rag_synthesis":     "RAG_SYNTHESIS_MODEL",
    "rag_retry":         "RAG_SYNTHESIS_MODEL",
    "rag_judge":         "JUDGE_MODEL",
    "rag_rewrite":       "RAG_REWRITE_MODEL",
}


def get_model(purpose: str = "default") -> str:
    """Resolve model name for a given purpose."""
    env_var = _ENV_VARS.get(purpose)
    if env_var:
        val = os.getenv(env_var, "").strip()
        if val:
            return val
    global_val = os.getenv("SUMMARY_MODEL", "").strip()
    if global_val:
        return global_val
    return _DEFAULTS.get(purpose, _DEFAULTS["default"])


def get_provider() -> str:
    return os.getenv("LLM_PROVIDER", "openai").strip().lower()


def _get_timeout() -> float:
    try:
        return float(os.getenv("LLM_TIMEOUT_SECONDS", str(DEFAULT_LLM_TIMEOUT_SECONDS)))
    except (ValueError, TypeError):
        return float(DEFAULT_LLM_TIMEOUT_SECONDS)


def get_chat_client() -> "OpenAI":
    """Return OpenAI-compatible client for chat completions (OpenAI or Gemini)."""
    if not HAS_OPENAI:
        raise ValueError("openai package is not installed. Install with: pip install openai")
    timeout = _get_timeout()
    provider = get_provider()
    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set")
        return OpenAI(api_key=api_key, base_url=GEMINI_BASE_URL, timeout=timeout)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    return OpenAI(api_key=api_key, timeout=timeout)


def get_embedding_client() -> "OpenAI":
    """Return OpenAI client for embeddings (always OpenAI to avoid re-embedding DB)."""
    if not HAS_OPENAI:
        raise ValueError("openai package is not installed. Install with: pip install openai")
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    return OpenAI(api_key=api_key, timeout=60.0)
