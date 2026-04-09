"""Async client for fetching Google News RSS feeds.

Google News exposes RSS feeds at:
  https://news.google.com/rss/search?q=QUERY&hl=LANG&gl=COUNTRY&ceid=COUNTRY:LANG

No API key is required.  Each feed returns up to ~100 recent articles as
standard RSS 2.0 XML with <item> elements.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS_BASE = "https://news.google.com/rss/search"


@dataclass
class NewsArticle:
    """A single article parsed from a Google News RSS feed."""

    title: str
    url: str
    source: str  # publisher name
    published_at: datetime | None
    query: str  # the search query that found this article

    @property
    def unique_key(self) -> str:
        """Stable deduplication key (URL is unique per article)."""
        return self.url


class GoogleNewsClient:
    """Fetches and parses Google News RSS feeds."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        language: str = "en",
        country: str = "US",
    ) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=30,
            headers={"User-Agent": "CompanySourcingAgent/0.1"},
        )
        self._owns_client = client is None
        self._language = language
        self._country = country

    def _build_url(self, query: str) -> str:
        """Build a Google News RSS URL for the given search query."""
        ceid = f"{self._country}:{self._language}"
        return (
            f"{GOOGLE_NEWS_RSS_BASE}"
            f"?q={httpx.QueryParams({'': query}).get('')}"
            f"&hl={self._language}"
            f"&gl={self._country}"
            f"&ceid={ceid}"
        )

    @staticmethod
    def _parse_feed(xml_text: str, query: str) -> list[NewsArticle]:
        """Parse RSS XML into NewsArticle objects."""
        articles: list[NewsArticle] = []
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            logger.warning("Failed to parse RSS XML for query=%s", query)
            return articles

        for item in root.iter("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            source_el = item.find("source")
            pub_date_el = item.find("pubDate")

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link = link_el.text.strip() if link_el is not None and link_el.text else ""
            source_name = source_el.text.strip() if source_el is not None and source_el.text else ""

            published_at = None
            if pub_date_el is not None and pub_date_el.text:
                try:
                    published_at = parsedate_to_datetime(pub_date_el.text.strip())
                except (ValueError, TypeError):
                    pass

            if title and link:
                articles.append(
                    NewsArticle(
                        title=title,
                        url=link,
                        source=source_name,
                        published_at=published_at,
                        query=query,
                    )
                )

        return articles

    async def search(self, query: str, max_results: int = 20) -> list[NewsArticle]:
        """Fetch Google News RSS for *query* and return parsed articles.

        Args:
            query: Free-text search query.
            max_results: Maximum articles to return per query.
        """
        url = self._build_url(query)
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("HTTP error fetching Google News RSS for %r: %s", query, exc)
            return []

        articles = self._parse_feed(resp.text, query)
        return articles[:max_results]

    async def fetch_all(
        self, queries: list[str], max_per_query: int = 20
    ) -> list[NewsArticle]:
        """Run multiple queries and return deduplicated articles."""
        seen_urls: set[str] = set()
        all_articles: list[NewsArticle] = []

        for query in queries:
            articles = await self.search(query, max_results=max_per_query)
            for article in articles:
                if article.url not in seen_urls:
                    seen_urls.add(article.url)
                    all_articles.append(article)

        logger.info(
            "Fetched %d unique articles across %d queries",
            len(all_articles),
            len(queries),
        )
        return all_articles

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
