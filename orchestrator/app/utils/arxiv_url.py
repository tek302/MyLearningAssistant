"""
Normalize arXiv URLs so that abs and pdf links for the same paper are treated as one source.
Only converts arxiv.org/abs/<id> -> arxiv.org/pdf/<id>; all other URLs are returned unchanged.
"""
from urllib.parse import urlparse, urlunparse
import re

# arXiv abs path: /abs/1706.03762 or /abs/1706.03762v2 (optional version suffix)
_ARXIV_ABS_PATH_RE = re.compile(r"^/abs/([0-9]+\.[0-9]+)(v[0-9]+)?$", re.IGNORECASE)


def normalize_arxiv_url(url: str) -> str:
    """
    If url is an arXiv abstract page (arxiv.org/abs/<id>), return the corresponding
    PDF URL (arxiv.org/pdf/<id>). Otherwise return url unchanged.

    Only arxiv.org / www.arxiv.org and path /abs/<arxiv_id> are normalized;
    no other URLs are modified to avoid mis-classification.
    """
    if not url or not url.strip():
        return url
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return url
    host = (parsed.netloc or "").lower()
    if host not in ("arxiv.org", "www.arxiv.org"):
        return url
    path = (parsed.path or "").strip()
    if not _ARXIV_ABS_PATH_RE.match(path):
        return url
    # Replace /abs/ with /pdf/; keep the same arxiv id (and optional version)
    new_path = path.replace("/abs/", "/pdf/", 1)
    new_parsed = (
        parsed.scheme or "https",
        parsed.netloc,
        new_path,
        parsed.params,
        parsed.query,
        parsed.fragment,
    )
    return urlunparse(new_parsed)
