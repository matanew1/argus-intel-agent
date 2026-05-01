"""NewsAPI client for fetching recent articles matching a query."""
import os
from dataclasses import dataclass

import requests

from argus.core.logger import get_logger

log = get_logger(__name__)

_NEWSAPI_BASE = "https://newsapi.org/v2/everything"


@dataclass
class Article:
    """A single news article returned by the NewsAPI."""

    title: str
    description: str
    url: str
    published_at: str
    source: str


def fetch_news(query: str, max_results: int = 10) -> list[Article]:
    """Fetch recent articles matching query from NewsAPI.

    Args:
        query: Search string passed to NewsAPI ``q`` parameter.
        max_results: Maximum number of articles to return (default 10).

    Returns:
        List of Article dataclass instances, ordered by publication date descending.

    Raises:
        requests.RequestException: If the HTTP request fails.
    """
    try:
        resp = requests.get(
            _NEWSAPI_BASE,
            params={
                "q": query,
                "sortBy": "publishedAt",
                "pageSize": max_results,
                "language": "en",
            },
            headers={"X-Api-Key": os.environ["NEWSAPI_KEY"]},
            timeout=15,
        )
        resp.raise_for_status()
        articles = [
            Article(
                title=a.get("title") or "",
                description=a.get("description") or "",
                url=a["url"],
                published_at=a.get("publishedAt") or "",
                source=a.get("source", {}).get("name") or "",
            )
            for a in resp.json().get("articles", [])
            if a.get("url")
        ]
        log.info("NewsAPI returned %d articles for query: %s", len(articles), query)
        return articles
    except requests.RequestException as exc:
        log.error("NewsAPI request failed: %s", exc)
        raise
