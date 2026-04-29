import difflib
import hashlib

import feedparser
import requests
from bs4 import BeautifulSoup

from argus.core.logger import get_logger

log = get_logger(__name__)

_HEADERS = {"User-Agent": "ArgusIntelBot/1.0"}


def fetch_page_text(url: str) -> str:
    """Fetch URL, strip boilerplate HTML, return normalized text."""
    resp = requests.get(url, timeout=20, headers=_HEADERS)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "meta"]):
        tag.decompose()
    return " ".join(soup.get_text().split())


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def unified_diff(old_text: str, new_text: str, context_lines: int = 3) -> str:
    """Return unified diff string. Empty string means no change."""
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = list(
        difflib.unified_diff(old_lines, new_lines, lineterm="", n=context_lines)
    )
    return "".join(diff)


def scrape_jobs_html(url: str) -> list[dict]:
    """Heuristic HTML scrape for job listings. Returns [{id, title, location}]."""
    try:
        resp = requests.get(url, timeout=20, headers=_HEADERS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        jobs = []
        for a in soup.find_all("a", href=True):
            href: str = a["href"]
            text = a.get_text(strip=True)
            if any(kw in href.lower() for kw in ["/job", "/career", "/position", "/role", "/opening", "/vacancy"]):
                full_url = href if href.startswith("http") else url.rstrip("/") + "/" + href.lstrip("/")
                if text and len(text) > 3:
                    jobs.append({"id": full_url, "title": text, "location": ""})
        log.info("Scraped %d job links from %s", len(jobs), url)
        return jobs
    except Exception as exc:
        log.error("Job scrape failed for %s: %s", url, exc)
        return []


def scrape_jobs_rss(rss_url: str) -> list[dict]:
    """Parse RSS feed for job listings."""
    feed = feedparser.parse(rss_url)
    jobs = [
        {
            "id": entry.get("link") or entry.get("id") or "",
            "title": entry.get("title") or "",
            "location": "",
        }
        for entry in feed.entries
        if entry.get("link") or entry.get("id")
    ]
    log.info("RSS returned %d jobs from %s", len(jobs), rss_url)
    return jobs
