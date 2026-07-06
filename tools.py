"""LangChain tools for web search and URL scraping.

Provides two LangChain ``@tool``-decorated functions used by agents,
plus internal helpers for URL validation, parallel scraping, caching,
and retry logic.

Tools:
    web_search: Search the web using Tavily API.
    scrape_url: Scrape and extract clean text from a single URL.

Internal:
    scrape_urls_parallel: Scrape multiple URLs concurrently with aiohttp.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from urllib.parse import urlparse

import aiohttp
import requests
from bs4 import BeautifulSoup
from langchain.tools import tool
from tavily import TavilyClient
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import settings
from exceptions import ScrapeError, SearchError
from logger import get_logger
from models import ScrapedDocument, ScrapedResults, SearchResult, SearchResults

logger = get_logger(__name__)

# ── Clients ───────────────────────────────────────────────────────────────────

_tavily = TavilyClient(api_key=settings.tavily_api_key)

# ── Optional disk cache ──────────────────────────────────────────────────────

_cache = None
if settings.cache_enabled:
    try:
        import diskcache
        _cache = diskcache.Cache(".cache")
        logger.info("Disk cache enabled at .cache/")
    except ImportError:
        logger.warning("diskcache not installed — caching disabled")


def _cache_key(prefix: str, value: str) -> str:
    """Generate a deterministic cache key from a prefix and value."""
    h = hashlib.sha256(value.encode()).hexdigest()[:16]
    return f"{prefix}:{h}"


# ── URL validation ────────────────────────────────────────────────────────────

def validate_url(url: str) -> tuple[bool, str]:
    """Check that a URL is safe to scrape (prevents SSRF).

    Returns:
        (is_safe, reason) — if ``is_safe`` is False, ``reason`` explains why.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False, "Malformed URL"

    if parsed.scheme not in settings.scrape_allowed_schemes:
        return False, f"Scheme '{parsed.scheme}' not allowed. Use http or https."

    hostname = parsed.hostname or ""
    if not hostname:
        return False, "URL has no hostname"

    if hostname in settings.scrape_blocked_hosts:
        return False, f"Host '{hostname}' is blocked for security reasons"

    # Block private IP ranges
    if hostname.startswith(("10.", "192.168.", "172.")):
        return False, f"Private IP range '{hostname}' is not allowed"

    return True, ""


# ── Clean HTML helper ─────────────────────────────────────────────────────────

def _clean_html(html_text: str, max_chars: int) -> str:
    """Parse HTML and extract clean text, truncated at a word boundary."""
    soup = BeautifulSoup(html_text, "html.parser")

    # Remove non-content elements
    for tag in soup(["script", "style", "header", "footer", "nav", "aside", "iframe"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)

    if not text:
        return ""

    # Truncate at word boundary
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "…"

    return text


# ── LangChain tools ──────────────────────────────────────────────────────────

@tool
def web_search(query: str) -> str:
    """Search the web for recent and reliable information on a topic.

    Returns titles, URLs, and content snippets from top results.
    """
    logger.info("Searching for: %s", query)
    start = time.time()

    # Check cache first
    if _cache is not None:
        cache_key = _cache_key("search", query)
        cached = _cache.get(cache_key)
        if cached is not None:
            logger.info("Cache hit for search query")
            return cached

    try:
        raw = _tavily.search(query=query, max_results=settings.search_max_results)

        if not raw.get("results"):
            return "No results found for this query."

        # Build structured results
        results = SearchResults(
            query=query,
            results=[
                SearchResult(
                    title=r["title"],
                    url=r["url"],
                    snippet=r["content"],
                )
                for r in raw["results"]
            ],
        )

        text = results.to_text()
        elapsed = time.time() - start
        logger.info("Search returned %d results in %.1fs", len(results.results), elapsed)

        # Cache the text result
        if _cache is not None:
            _cache.set(cache_key, text, expire=settings.cache_search_ttl_seconds)

        return text

    except Exception as e:
        logger.exception("Web search failed for query: %s", query)
        raise SearchError(
            f"Search failed: {e}",
            user_message="Web search failed. Please try again.",
        ) from e


@tool
def scrape_url(url: str) -> str:
    """Scrape and return clean text content from a given URL for deeper reading.

    The URL must use http or https scheme and must not point to private networks.
    """
    # Validate before any request
    is_safe, reason = validate_url(url)
    if not is_safe:
        logger.warning("Blocked unsafe URL: %s — %s", url, reason)
        return f"Error: Cannot scrape this URL. {reason}"

    logger.info("Scraping URL: %s", url)

    # Check cache
    if _cache is not None:
        cache_key = _cache_key("scrape", url)
        cached = _cache.get(cache_key)
        if cached is not None:
            logger.info("Cache hit for URL: %s", url)
            return cached

    try:
        text = _scrape_single_url(url)

        # Cache the result
        if _cache is not None:
            _cache.set(cache_key, text, expire=settings.cache_scrape_ttl_seconds)

        return text

    except requests.exceptions.Timeout:
        logger.warning("Timeout scraping URL: %s", url)
        return f"Error: Request timed out after {settings.scrape_timeout_seconds}s."
    except requests.exceptions.HTTPError as e:
        logger.warning("HTTP error scraping URL %s: %s", url, e)
        return f"Error: HTTP {e.response.status_code} when fetching the URL."
    except requests.exceptions.ConnectionError:
        logger.warning("Connection error for URL: %s", url)
        return "Error: Could not connect to the URL."
    except Exception:
        logger.exception("Unexpected error scraping URL: %s", url)
        return "Error: Failed to scrape the URL."


# ── Internal scraping with retry ──────────────────────────────────────────────

@retry(
    retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    reraise=True,
)
def _scrape_single_url(url: str) -> str:
    """Scrape a single URL with retry logic. Returns clean text."""
    start = time.time()
    resp = requests.get(
        url,
        timeout=settings.scrape_timeout_seconds,
        headers={"User-Agent": "Mozilla/5.0 (ResearchMind Bot)"},
    )
    resp.raise_for_status()

    text = _clean_html(resp.text, settings.scrape_max_chars)
    elapsed = time.time() - start

    if not text:
        logger.warning("No extractable text from: %s", url)
        return "Error: Page contained no extractable text content."

    logger.info("Scraped %d chars from %s in %.1fs", len(text), url, elapsed)
    return text


# ── Parallel scraping with aiohttp ───────────────────────────────────────────

async def _fetch_url_async(
    session: aiohttp.ClientSession,
    url: str,
    max_chars: int,
    timeout: int,
    retries: int,
) -> ScrapedDocument:
    """Fetch and clean a single URL asynchronously with retry."""
    for attempt in range(1, retries + 2):  # +2 because range is exclusive and 1 attempt = 0 retries
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=timeout),
                headers={"User-Agent": "Mozilla/5.0 (ResearchMind Bot)"},
            ) as resp:
                if resp.status != 200:
                    if attempt <= retries:
                        logger.warning(
                            "HTTP %d for %s, retry %d/%d",
                            resp.status, url, attempt, retries,
                        )
                        await asyncio.sleep(attempt)  # Simple backoff
                        continue
                    return ScrapedDocument(
                        url=url, content="", error=f"HTTP {resp.status}"
                    )

                html_text = await resp.text()
                content = _clean_html(html_text, max_chars)

                if not content:
                    return ScrapedDocument(
                        url=url, content="", error="No extractable text"
                    )

                return ScrapedDocument(url=url, content=content)

        except asyncio.TimeoutError:
            if attempt <= retries:
                logger.warning("Timeout for %s, retry %d/%d", url, attempt, retries)
                await asyncio.sleep(attempt)
                continue
            return ScrapedDocument(url=url, content="", error="Timeout")
        except Exception as e:
            if attempt <= retries:
                logger.warning("Error for %s: %s, retry %d/%d", url, e, attempt, retries)
                await asyncio.sleep(attempt)
                continue
            return ScrapedDocument(url=url, content="", error=str(e))

    # Should never reach here, but safety fallback
    return ScrapedDocument(url=url, content="", error="Max retries exceeded")


async def _scrape_urls_async(urls: list[str]) -> ScrapedResults:
    """Scrape multiple URLs in parallel using aiohttp."""
    # Validate all URLs first
    valid_urls = []
    documents: list[ScrapedDocument] = []

    for url in urls:
        is_safe, reason = validate_url(url)
        if is_safe:
            valid_urls.append(url)
        else:
            logger.warning("Skipping unsafe URL: %s — %s", url, reason)
            documents.append(ScrapedDocument(url=url, content="", error=reason))

    if not valid_urls:
        return ScrapedResults(documents=documents)

    logger.info("Parallel scraping %d URLs", len(valid_urls))
    start = time.time()

    # Check cache for each URL
    uncached_urls = []
    for url in valid_urls:
        if _cache is not None:
            cache_key = _cache_key("scrape", url)
            cached = _cache.get(cache_key)
            if cached is not None:
                logger.info("Cache hit for URL: %s", url)
                documents.append(ScrapedDocument(url=url, content=cached))
                continue
        uncached_urls.append(url)

    # Fetch uncached URLs in parallel
    if uncached_urls:
        async with aiohttp.ClientSession() as session:
            tasks = [
                _fetch_url_async(
                    session, url,
                    max_chars=settings.scrape_max_chars,
                    timeout=settings.scrape_timeout_seconds,
                    retries=settings.scrape_retry_attempts,
                )
                for url in uncached_urls
            ]
            fetched = await asyncio.gather(*tasks)
            for doc in fetched:
                documents.append(doc)
                # Cache successful results
                if doc.success and _cache is not None:
                    cache_key = _cache_key("scrape", doc.url)
                    _cache.set(cache_key, doc.content, expire=settings.cache_scrape_ttl_seconds)

    elapsed = time.time() - start
    result = ScrapedResults(documents=documents)
    logger.info(
        "Parallel scrape complete: %d/%d successful in %.1fs",
        len(result.successful), len(documents), elapsed,
    )
    return result


def scrape_urls_parallel(urls: list[str]) -> ScrapedResults:
    """Scrape multiple URLs in parallel (sync wrapper).

    Uses asyncio.run() to execute the async scraping pipeline.
    Deduplicates URLs and limits to configured parallel count.

    Args:
        urls: List of URLs to scrape.

    Returns:
        ScrapedResults with all documents (successful and failed).
    """
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_urls: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    # Limit to configured count
    limited = unique_urls[: settings.scrape_parallel_count]

    if len(unique_urls) > len(limited):
        logger.info(
            "Limiting scrape from %d to %d URLs", len(unique_urls), len(limited)
        )

    try:
        return asyncio.run(_scrape_urls_async(limited))
    except Exception as e:
        logger.exception("Parallel scraping failed entirely")
        raise ScrapeError(
            f"Parallel scraping failed: {e}",
            user_message="Failed to scrape web pages. Please try again.",
        ) from e