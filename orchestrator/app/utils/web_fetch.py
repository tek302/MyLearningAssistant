import os
import re
import logging
from typing import Dict, Any
from urllib.parse import quote, urlparse
from dotenv import load_dotenv
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

# Load environment variables
load_dotenv()

# Browser-like headers to reduce 404/403 from sites that block minimal User-Agents (e.g. Medium, some CDNs).
# Incomplete UA (e.g. no "Chrome/xxx") often triggers bot detection.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def get_max_pdf_mb() -> int:
    """Get maximum PDF size in MB, defaulting to 25."""
    try:
        return int(os.getenv("MAX_PDF_MB", "25"))
    except ValueError:
        return 25


def get_max_pdf_pages() -> int:
    """Get maximum PDF pages to process, defaulting to 100."""
    try:
        return int(os.getenv("MAX_PDF_PAGES", "100"))
    except ValueError:
        return 100


def get_min_text_length() -> int:
    """Get minimum text length required, defaulting to 100."""
    try:
        return int(os.getenv("MIN_TEXT_LENGTH", "100"))
    except ValueError:
        return 100


def _fetch_pdf_text(url: str, timeout: int = 30) -> Dict[str, Any]:
    """
    Fetch PDF and extract text content using PyMuPDF.
    
    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        
    Returns:
        Dictionary with keys: url, title, text, lang, meta
        
    Raises:
        ValueError: If PyMuPDF is not available or PDF processing fails
        requests.RequestException: If request fails
    """
    if not HAS_PYMUPDF:
        raise ValueError("PyMuPDF is not installed. Install with: pip install pymupdf")
    
    # Create session with retry strategy
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.3,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Use browser-like headers so sites (e.g. Medium) don't return 404 for bot-like requests
    headers = {**BROWSER_HEADERS}
    max_size_bytes = get_max_pdf_mb() * 1024 * 1024
    response = session.get(url, headers=headers, timeout=timeout, stream=True)
    response.raise_for_status()
    
    # Check content length if available
    content_length = response.headers.get("Content-Length")
    if content_length and int(content_length) > max_size_bytes:
        raise ValueError(f"PDF size ({int(content_length) / 1024 / 1024:.1f} MB) exceeds maximum ({get_max_pdf_mb()} MB)")
    
    # Download with size cap
    pdf_bytes = b""
    for chunk in response.iter_content(chunk_size=8192):
        pdf_bytes += chunk
        if len(pdf_bytes) > max_size_bytes:
            raise ValueError(f"PDF size exceeds maximum ({get_max_pdf_mb()} MB)")
    
    if not pdf_bytes:
        raise ValueError("No PDF content received")
    
    # Extract text using PyMuPDF
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = len(doc)
        max_pages = get_max_pdf_pages()
        pages_used = min(total_pages, max_pages)
        
        # Extract text from pages
        text_parts = []
        for page_num in range(pages_used):
            page = doc[page_num]
            page_text = page.get_text("text")
            if page_text:
                text_parts.append(page_text)
        
        doc.close()
        
        text = "\n\n".join(text_parts)
        
        return {
            "url": url,
            "title": None,
            "text": text,
            "lang": None,
            "meta": {
                "content_type": "pdf",
                "pages_used": pages_used,
                "total_pages": total_pages
            }
        }
    except Exception as e:
        raise ValueError(f"Failed to extract text from PDF: {str(e)}")


def _fetch_html_text(url: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Fetch HTML and extract text content using BeautifulSoup.
    
    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        
    Returns:
        Dictionary with keys: url, title, text, lang, meta
        
    Raises:
        requests.RequestException: If request fails
        ValueError: If no text content could be extracted
    """
    # Create session with retry strategy
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.3,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Use browser-like headers so sites (e.g. Medium) don't return 404 for bot-like requests
    headers = {**BROWSER_HEADERS}
    # Some sites (e.g. Medium) return 403 without Referer; set origin from URL
    try:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
    except Exception:
        pass
    
    # Fetch the URL
    response = session.get(url, headers=headers, timeout=timeout)
    if not response.ok:
        logging.getLogger(__name__).warning(
            "HTML fetch failed: url=%s status=%s final_url=%s",
            url, response.status_code, response.url
        )
    response.raise_for_status()
    
    content_type = response.headers.get("Content-Type", "").lower()
    html_content = response.text
    
    # Extract title and text
    if HAS_BS4:
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Extract title
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else "Untitled"
        
        # Remove script and style elements
        for script in soup(["script", "style", "meta", "link", "noscript"]):
            script.decompose()
        
        # Extract text
        text = soup.get_text(separator="\n", strip=True)
        
        # Extract language from html tag
        html_tag = soup.find("html")
        lang = html_tag.get("lang", "en") if html_tag else "en"
        
        # Extract meta information
        meta = {
            "content_type": "html",
            "charset": response.encoding
        }
        
    else:
        # Fallback to regex extraction
        # Extract title
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else "Untitled"
        # Clean HTML tags from title
        title = re.sub(r"<[^>]+>", "", title)
        
        # Extract text by removing HTML tags
        text = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<noscript[^>]*>.*?</noscript>", "", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        
        # Extract language
        lang_match = re.search(r'<html[^>]*lang=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
        lang = lang_match.group(1) if lang_match else "en"
        
        meta = {
            "content_type": "html",
            "charset": response.encoding,
            "extraction_method": "regex"
        }
    
    # Clean and normalize text
    text = re.sub(r"\n\s*\n", "\n\n", text)  # Normalize multiple newlines
    text = text.strip()
    
    if not text:
        raise ValueError(f"No text content could be extracted from URL: {url}")
    
    return {
        "url": url,
        "title": title or "Untitled",
        "text": text,
        "lang": lang[:10] if lang else "en",  # Limit lang code length
        "meta": meta
    }


def _is_x_twitter_url(url: str) -> bool:
    """True if URL is a Twitter/X tweet (e.g. twitter.com/user/status/123 or x.com/user/status/123)."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        netloc = (parsed.netloc or "").lower()
        path = (parsed.path or "").lower()
        if "twitter.com" not in netloc and "x.com" not in netloc:
            return False
        return "/status/" in path
    except Exception:
        return False


def _fetch_x_oembed_text(url: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Fetch tweet content via X/Twitter oEmbed API (no auth required).
    Returns same shape as _fetch_html_text: url, title, text, lang, meta.
    """
    oembed_url = f"https://publish.twitter.com/oembed?url={quote(url, safe='')}"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; LearningAgent/1.0; +https://github.com/learning-agent)",
    }
    response = requests.get(oembed_url, headers=headers, timeout=timeout)
    response.raise_for_status()
    data = response.json()

    html = data.get("html") or ""
    author_name = data.get("author_name") or "Unknown"
    # Strip HTML to get plain text
    if HAS_BS4 and html:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
    else:
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()

    if not text or len(text) < 20:
        raise ValueError("Could not extract tweet text from oEmbed response")

    title = f"Tweet by {author_name}"

    return {
        "url": url,
        "title": title,
        "text": text,
        "lang": "en",
        "meta": {"content_type": "x_oembed", "author_name": author_name},
    }


def fetch_url_text(url: str, timeout: int = 30) -> Dict[str, Any]:
    """
    Fetch URL and extract text content.
    
    Automatically detects content type (PDF or HTML) and uses appropriate extraction method.
    
    Args:
        url: URL to fetch
        timeout: Request timeout in seconds (default: 30, longer for PDFs)
        
    Returns:
        Dictionary with keys: url, title, text, lang, meta
        
    Raises:
        requests.RequestException: If request fails
        ValueError: If no text content could be extracted or text is too short (default minimum: 100 chars, configurable via MIN_TEXT_LENGTH)
    """
    # First, make a HEAD request to check content type (if possible)
    # Otherwise, we'll check during GET
    session = requests.Session()
    headers = {**BROWSER_HEADERS}
    
    # Check if URL ends with .pdf
    is_pdf_url = url.lower().endswith(".pdf")
    
    # Try HEAD request first to check content type
    content_type = None
    try:
        head_response = session.head(url, headers=headers, timeout=10, allow_redirects=True)
        content_type = head_response.headers.get("Content-Type", "").lower()
    except:
        # If HEAD fails, we'll check during GET
        pass
    
    # Determine if PDF
    is_pdf = is_pdf_url or (content_type and "application/pdf" in content_type)

    # X/Twitter tweet URL: use oEmbed (no JS render needed)
    if _is_x_twitter_url(url):
        try:
            return _fetch_x_oembed_text(url, timeout=min(timeout, 10))
        except Exception as e:
            raise ValueError(f"X/Twitter URL could not be fetched: {e}") from e

    # Fetch and extract based on content type
    if is_pdf:
        result = _fetch_pdf_text(url, timeout=timeout)
    else:
        result = _fetch_html_text(url, timeout=min(timeout, 10))
    
    # Validate minimum text length
    min_length = get_min_text_length()
    text_length = len(result.get("text", ""))
    if text_length < min_length:
        raise ValueError(f"Extracted text is too short ({text_length} chars). Minimum {min_length} characters required.")
    
    return result
