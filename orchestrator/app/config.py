"""Configuration module for environment variables."""

import os
import socket
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv


def _force_ipv4_db_url(url: str) -> str:
    """
    If the DB URL host is a hostname, resolve it to IPv4 and replace in the URL.
    Fixes 'Network is unreachable' when Docker (no IPv6) connects to Supabase (often resolves to IPv6).
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        p = urlparse(url)
        host = p.hostname
        if not host or _looks_like_ipv4(host):
            return url
        port = p.port or 5432
        ipv4 = _resolve_to_ipv4(host, port)
        if not ipv4:
            logger.warning("DB host %r resolved to no IPv4; connection may fail in Docker (IPv6 unreachable)", host)
            return url
        # Replace only the host part (after last @) so we don't touch userinfo/password
        if "@" in p.netloc:
            userinfo, hostport = p.netloc.rsplit("@", 1)
            if ":" in hostport:
                _, port_str = hostport.rsplit(":", 1)
                new_netloc = f"{userinfo}@{ipv4}:{port_str}"
            else:
                new_netloc = f"{userinfo}@{ipv4}"
        else:
            if ":" in p.netloc:
                _, port_str = p.netloc.rsplit(":", 1)
                new_netloc = f"{ipv4}:{port_str}"
            else:
                new_netloc = ipv4
        out = urlunparse((p.scheme, new_netloc, p.path, p.params, p.query, p.fragment))
        logger.info("DB URL host forced to IPv4: %s -> %s", host, ipv4)
        return out
    except Exception as e:
        logger.warning("Could not force IPv4 for DB URL: %s", e)
        return url


def _looks_like_ipv4(host: str) -> bool:
    try:
        socket.inet_pton(socket.AF_INET, host)
        return True
    except OSError:
        return False


def _resolve_to_ipv4(host: str, port: int) -> Optional[str]:
    """Resolve host to first IPv4 address, or None."""
    try:
        infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        if infos:
            return infos[0][4][0]
    except (socket.gaierror, OSError):
        pass
    return None


def load_env() -> str:
    """Load .env from orchestrator dir. Does not override existing shell env vars."""
    base_dir = Path(__file__).resolve().parents[1]
    dotenv_path = base_dir / ".env"
    load_dotenv(dotenv_path=dotenv_path, override=False)
    return str(dotenv_path)


def get_database_url() -> str:
    """
    Return DATABASE_URL or SUPABASE_DB_URL; raise if unset.
    Host is resolved to IPv4 when possible (for Docker). If DATABASE_URL_IPV4 is set, use it as-is (no resolve).
    """
    import logging
    _log = logging.getLogger(__name__)
    # Explicit IPv4 URL (e.g. for Docker when in-container DNS returns only IPv6)
    explicit_ipv4 = os.getenv("DATABASE_URL_IPV4")
    if explicit_ipv4 and explicit_ipv4.strip():
        return explicit_ipv4.strip()
    url = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError("DATABASE_URL or SUPABASE_DB_URL environment variable is not set")
    url = url.strip()
    # Log which host we're using (for debugging Docker env)
    try:
        host = urlparse(url).hostname or "?"
        _log.info("DB connection host: %s", host)
    except Exception:
        pass
    return _force_ipv4_db_url(url)


def get_judge_enabled() -> bool:
    """
    Get whether LLM judge is enabled from environment variable.
    
    Returns:
        bool: True if JUDGE_ENABLED is set to "true" (case-insensitive), False otherwise
    """
    value = os.getenv("JUDGE_ENABLED", "false")
    return value.lower() in ("true", "1", "yes")


def get_judge_model() -> str:
    """Resolve judge model via the central llm_client config."""
    from app.utils.llm_client import get_model
    return get_model("rag_judge")


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


def get_supabase_url() -> Optional[str]:
    """Supabase project URL for Storage API (e.g. https://xxx.supabase.co). None if not set."""
    return (os.getenv("SUPABASE_URL") or os.getenv("SUPABASE_SERVICE_URL") or "").strip() or None


def get_supabase_service_key() -> Optional[str]:
    """Supabase service_role key for server-side Storage (upload/delete). None if not set."""
    return (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY") or "").strip() or None


def get_ingest_storage_bucket() -> str:
    """Bucket name for PDF ingest files. Default ingest-files."""
    return (os.getenv("INGEST_STORAGE_BUCKET") or "ingest-files").strip()
