"""Tavily web search, restricted to research domains. Fallback when the curated cards are thin."""

import logging

from tavily import TavilyClient

from app.config import get_settings
from app.models import ExternalSource

logger = logging.getLogger(__name__)

RESEARCH_DOMAINS = [
    "pubmed.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
    "journals.lww.com",
    "link.springer.com",
]
MAX_RESULTS = 5


def search_research(query: str) -> list[ExternalSource]:
    """Return up to 5 web sources. Never raises: no key or a failed search gives an empty list,
    and the verdict then simply has less evidence."""
    key = get_settings().tavily_api_key
    if not key:
        logger.warning("TAVILY_API_KEY missing, skipping web search")
        return []
    try:
        response = TavilyClient(api_key=key).search(
            query, include_domains=RESEARCH_DOMAINS, max_results=MAX_RESULTS
        )
    except Exception as exc:  # network, quota, ...: degrade, don't fail the analysis
        logger.warning("Tavily search failed: %s", exc)
        return []
    return [
        ExternalSource(id=f"web-{i}", title=r.get("title", ""), url=r.get("url", ""), snippet=r.get("content", ""))
        for i, r in enumerate(response.get("results", [])[:MAX_RESULTS], start=1)
        if r.get("content")
    ]
