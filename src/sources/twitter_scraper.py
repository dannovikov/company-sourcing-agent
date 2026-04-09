"""Fallback Twitter/X scraper using httpx + BeautifulSoup.

This module provides a best-effort scraper for when Twitter API credentials
are not available. It uses nitter (privacy-friendly Twitter frontend) instances
that expose HTML pages and RSS feeds parseable without authentication.

Note: These methods are fragile and may break if nitter instances change.
The Twitter API client should be preferred when credentials are available.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from src.sources.twitter_api import FetchedTweet

logger = logging.getLogger(__name__)

# Public nitter instances (try in order, fall back on failure)
NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.woodland.cafe",
]


class TwitterScraper:
    """Fallback scraper for Twitter/X data without API credentials.

    Uses nitter (a privacy-friendly Twitter frontend) for search and user
    timeline scraping. Nitter instances expose RSS feeds and HTML pages
    that can be parsed without authentication.
    """

    def __init__(self, timeout: float = 15.0) -> None:
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
        )
        self._working_instance: Optional[str] = None

    def _find_working_instance(self) -> Optional[str]:
        """Find a nitter instance that's currently responsive."""
        if self._working_instance:
            try:
                resp = self._client.head(self._working_instance, timeout=5.0)
                if resp.status_code < 500:
                    return self._working_instance
            except httpx.HTTPError:
                pass

        for instance in NITTER_INSTANCES:
            try:
                resp = self._client.head(instance, timeout=5.0)
                if resp.status_code < 500:
                    self._working_instance = instance
                    logger.info("Using nitter instance: %s", instance)
                    return instance
            except httpx.HTTPError:
                continue

        logger.warning("No nitter instances available")
        return None

    def search(self, query: str, max_results: int = 50) -> list[FetchedTweet]:
        """Search for tweets matching a query via nitter.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return.

        Returns:
            List of FetchedTweet objects parsed from search results.
        """
        instance = self._find_working_instance()
        if not instance:
            logger.error("No nitter instances available for search")
            return []

        url = f"{instance}/search?f=tweets&q={quote_plus(query)}"
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Failed to search nitter: %s", exc)
            return []

        return self._parse_timeline_page(resp.text, max_results)

    def get_user_tweets(
        self, username: str, max_results: int = 20
    ) -> list[FetchedTweet]:
        """Get recent tweets from a user via nitter HTML scraping.

        Args:
            username: Twitter handle (without @).
            max_results: Maximum number of results to return.

        Returns:
            List of FetchedTweet objects.
        """
        instance = self._find_working_instance()
        if not instance:
            logger.error("No nitter instances available for user timeline")
            return []

        url = f"{instance}/{username}"
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Failed to fetch user %s from nitter: %s", username, exc)
            return []

        return self._parse_timeline_page(resp.text, max_results, default_author=username)

    def get_user_rss(self, username: str, max_results: int = 20) -> list[FetchedTweet]:
        """Get recent tweets from a user via nitter RSS feed.

        RSS is more stable than HTML scraping as the format changes less often.

        Args:
            username: Twitter handle (without @).
            max_results: Maximum number of results to return.

        Returns:
            List of FetchedTweet objects.
        """
        instance = self._find_working_instance()
        if not instance:
            return []

        url = f"{instance}/{username}/rss"
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Failed to fetch RSS for %s: %s", username, exc)
            return []

        return self._parse_rss(resp.text, max_results, default_author=username)

    def _parse_timeline_page(
        self,
        html: str,
        max_results: int,
        default_author: str = "unknown",
    ) -> list[FetchedTweet]:
        """Parse tweets from a nitter HTML page."""
        soup = BeautifulSoup(html, "html.parser")
        tweets: list[FetchedTweet] = []

        tweet_items = soup.select(".timeline-item")
        for item in tweet_items[:max_results]:
            try:
                tweet = self._parse_tweet_item(item, default_author)
                if tweet:
                    tweets.append(tweet)
            except Exception:
                logger.debug("Failed to parse tweet item", exc_info=True)
                continue

        logger.info("Scraped %d tweets from nitter page", len(tweets))
        return tweets

    def _parse_tweet_item(
        self, item: BeautifulSoup, default_author: str
    ) -> Optional[FetchedTweet]:
        """Parse a single tweet from nitter HTML."""
        # Extract username
        username_el = item.select_one(".username")
        username = (
            username_el.get_text(strip=True).lstrip("@")
            if username_el
            else default_author
        )

        # Extract tweet content
        content_el = item.select_one(".tweet-content")
        if not content_el:
            return None
        content = content_el.get_text(strip=True)
        if not content:
            return None

        # Extract tweet link (contains the tweet ID)
        link_el = item.select_one(".tweet-link")
        tweet_path = link_el.get("href", "") if link_el else ""
        tweet_id = tweet_path.rstrip("/").split("/")[-1] if tweet_path else ""

        # Some nitter instances use the status link differently
        if not tweet_id or not tweet_id.isdigit():
            status_link = item.select_one('a[href*="/status/"]')
            if status_link:
                href = status_link.get("href", "")
                match = re.search(r"/status/(\d+)", href)
                if match:
                    tweet_id = match.group(1)

        if not tweet_id:
            return None

        # Extract timestamp
        time_el = item.select_one(".tweet-date a")
        published_at = datetime.now(timezone.utc)
        if time_el:
            title = time_el.get("title", "")
            if title:
                try:
                    published_at = datetime.strptime(
                        title, "%b %d, %Y · %I:%M %p %Z"
                    ).replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

        # Extract stats
        stats = {}
        for stat_el in item.select(".tweet-stat"):
            icon = stat_el.select_one(".icon-container")
            value_el = stat_el.select_one(".tweet-stat-value")
            if icon and value_el:
                icon_classes = icon.get("class", [])
                value_text = value_el.get_text(strip=True).replace(",", "")
                try:
                    value = int(value_text) if value_text else 0
                except ValueError:
                    value = 0
                for cls in icon_classes:
                    if "comment" in cls:
                        stats["reply_count"] = value
                    elif "retweet" in cls:
                        stats["retweet_count"] = value
                    elif "heart" in cls or "like" in cls:
                        stats["like_count"] = value

        return FetchedTweet(
            tweet_id=tweet_id,
            author=username,
            content=content,
            url=f"https://x.com/{username}/status/{tweet_id}",
            published_at=published_at,
            raw_data={"stats": stats, "scrape_method": "nitter_html"},
        )

    def _parse_rss(
        self, xml_text: str, max_results: int, default_author: str = "unknown"
    ) -> list[FetchedTweet]:
        """Parse tweets from a nitter RSS feed."""
        soup = BeautifulSoup(xml_text, "html.parser")
        tweets: list[FetchedTweet] = []

        items = soup.find_all("item")
        for item in items[:max_results]:
            try:
                # Extract creator/author
                creator = item.find("dc:creator")
                username = (
                    creator.get_text(strip=True).lstrip("@")
                    if creator
                    else default_author
                )

                # Extract content from description
                desc = item.find("description")
                if not desc:
                    continue
                content_html = desc.get_text()
                content_soup = BeautifulSoup(content_html, "html.parser")
                content = content_soup.get_text(strip=True)
                if not content:
                    continue

                # Extract link and tweet ID
                link = item.find("link")
                url = link.get_text(strip=True) if link else ""
                tweet_id = ""
                if url:
                    match = re.search(r"/status/(\d+)", url)
                    if match:
                        tweet_id = match.group(1)
                    # Convert nitter URL to x.com URL
                    url = re.sub(
                        r"https?://[^/]+/([^/]+)/status/(\d+)",
                        r"https://x.com/\1/status/\2",
                        url,
                    )

                if not tweet_id:
                    continue

                # Extract timestamp
                pub_date = item.find("pubdate")
                published_at = datetime.now(timezone.utc)
                if pub_date:
                    try:
                        from email.utils import parsedate_to_datetime

                        published_at = parsedate_to_datetime(
                            pub_date.get_text(strip=True)
                        )
                    except (ValueError, TypeError):
                        pass

                tweets.append(
                    FetchedTweet(
                        tweet_id=tweet_id,
                        author=username,
                        content=content,
                        url=url,
                        published_at=published_at,
                        raw_data={"scrape_method": "nitter_rss"},
                    )
                )
            except Exception:
                logger.debug("Failed to parse RSS item", exc_info=True)
                continue

        logger.info("Parsed %d tweets from RSS feed", len(tweets))
        return tweets

    def close(self) -> None:
        self._client.close()
