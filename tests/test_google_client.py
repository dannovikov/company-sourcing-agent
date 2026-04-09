"""Tests for the Google News RSS client."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from src.google.client import GOOGLE_NEWS_RSS_BASE, GoogleNewsClient, NewsArticle

SAMPLE_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>startup raises seed round - Google News</title>
    <item>
      <title>Acme raises $10M seed round to build AI tools</title>
      <link>https://techcrunch.com/acme-raises-10m</link>
      <source url="https://techcrunch.com">TechCrunch</source>
      <pubDate>Wed, 09 Apr 2025 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>BetaCo secures $5M in Series A funding</title>
      <link>https://venturebeat.com/betaco-series-a</link>
      <source url="https://venturebeat.com">VentureBeat</source>
      <pubDate>Tue, 08 Apr 2025 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

EMPTY_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>no results - Google News</title>
  </channel>
</rss>
"""


class TestGoogleNewsClient:
    async def test_search_parses_rss(self):
        async with respx.mock:
            respx.get(url__startswith=GOOGLE_NEWS_RSS_BASE).respond(
                200, text=SAMPLE_RSS
            )

            client = GoogleNewsClient()
            articles = await client.search("startup raises seed round")
            await client.close()

        assert len(articles) == 2
        assert articles[0].title == "Acme raises $10M seed round to build AI tools"
        assert articles[0].url == "https://techcrunch.com/acme-raises-10m"
        assert articles[0].source == "TechCrunch"
        assert articles[0].published_at is not None
        assert articles[1].title == "BetaCo secures $5M in Series A funding"

    async def test_search_respects_max_results(self):
        async with respx.mock:
            respx.get(url__startswith=GOOGLE_NEWS_RSS_BASE).respond(
                200, text=SAMPLE_RSS
            )

            client = GoogleNewsClient()
            articles = await client.search("test", max_results=1)
            await client.close()

        assert len(articles) == 1

    async def test_search_handles_http_error(self):
        async with respx.mock:
            respx.get(url__startswith=GOOGLE_NEWS_RSS_BASE).respond(500)

            client = GoogleNewsClient()
            articles = await client.search("test")
            await client.close()

        assert articles == []

    async def test_search_handles_invalid_xml(self):
        async with respx.mock:
            respx.get(url__startswith=GOOGLE_NEWS_RSS_BASE).respond(
                200, text="not xml at all"
            )

            client = GoogleNewsClient()
            articles = await client.search("test")
            await client.close()

        assert articles == []

    async def test_fetch_all_deduplicates_by_url(self):
        async with respx.mock:
            respx.get(url__startswith=GOOGLE_NEWS_RSS_BASE).respond(
                200, text=SAMPLE_RSS
            )

            client = GoogleNewsClient()
            # Two queries should hit the same mock, returning same articles
            articles = await client.fetch_all(["query1", "query2"])
            await client.close()

        # Same 2 articles returned by both queries, so we get 2 (deduplicated)
        assert len(articles) == 2

    async def test_empty_feed_returns_empty_list(self):
        async with respx.mock:
            respx.get(url__startswith=GOOGLE_NEWS_RSS_BASE).respond(
                200, text=EMPTY_RSS
            )

            client = GoogleNewsClient()
            articles = await client.search("test")
            await client.close()

        assert articles == []

    def test_parse_feed_extracts_pub_date(self):
        articles = GoogleNewsClient._parse_feed(SAMPLE_RSS, "test")
        assert articles[0].published_at is not None
        assert articles[0].published_at.year == 2025

    def test_article_unique_key(self):
        article = NewsArticle(
            title="Test",
            url="https://example.com/article",
            source="Example",
            published_at=None,
            query="test",
        )
        assert article.unique_key == "https://example.com/article"
