"""Twitter/X API v2 client for fetching company signals.

Uses tweepy for clean OAuth2 Bearer token auth. Requires TWITTER_BEARER_TOKEN
environment variable. Free tier: 500K tweet reads/month, search limited to 7 days.

See: https://developer.twitter.com/en/docs/twitter-api/tweets/search/introduction
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import tweepy

from src.sources.config import MonitorConfig

logger = logging.getLogger(__name__)


@dataclass
class FetchedTweet:
    """Intermediate representation of a fetched tweet before DB persistence."""

    tweet_id: str
    author: str
    content: str
    url: str
    published_at: datetime
    author_followers: int | None = None
    raw_data: dict = field(default_factory=dict)


class TwitterAPIClient:
    """Fetches tweets via Twitter API v2 using Bearer token auth."""

    def __init__(self, config: MonitorConfig) -> None:
        self.config = config
        if not config.twitter.has_api_access:
            raise ValueError(
                "Twitter API requires TWITTER_BEARER_TOKEN. "
                "Get one at https://developer.twitter.com/en/portal/dashboard. "
                "Free tier ($0): 500K reads/mo. Basic ($100/mo): full search."
            )
        self._client = tweepy.Client(
            bearer_token=config.twitter.bearer_token,
            wait_on_rate_limit=True,
        )

    def search_recent(
        self,
        query: str,
        since_id: Optional[str] = None,
        max_results: int = 50,
    ) -> list[FetchedTweet]:
        """Search recent tweets (up to 7 days) matching a query.

        Args:
            query: Twitter search query (supports operators like OR, -is:retweet).
            since_id: Only return tweets newer than this ID (for pagination).
            max_results: Max tweets to return (10-100 for free tier).

        Returns:
            List of FetchedTweet objects.
        """
        max_results = min(max(max_results, 10), 100)

        try:
            response = self._client.search_recent_tweets(
                query=query,
                since_id=since_id,
                max_results=max_results,
                tweet_fields=["created_at", "author_id", "public_metrics", "entities"],
                user_fields=["username", "public_metrics"],
                expansions=["author_id"],
            )
        except tweepy.TooManyRequests:
            logger.warning("Rate limited on search query: %s", query)
            return []
        except tweepy.TwitterServerError as exc:
            logger.error("Twitter server error: %s", exc)
            return []

        if not response.data:
            logger.debug("No results for query: %s", query)
            return []

        # Build author lookup from includes
        users_by_id: dict[str, tweepy.User] = {}
        if response.includes and "users" in response.includes:
            for user in response.includes["users"]:
                users_by_id[str(user.id)] = user

        tweets: list[FetchedTweet] = []
        for tweet in response.data:
            author = users_by_id.get(str(tweet.author_id))
            username = author.username if author else "unknown"
            followers = (
                author.public_metrics.get("followers_count")
                if author and author.public_metrics
                else None
            )

            tweets.append(
                FetchedTweet(
                    tweet_id=str(tweet.id),
                    author=username,
                    author_followers=followers,
                    content=tweet.text,
                    url=f"https://x.com/{username}/status/{tweet.id}",
                    published_at=tweet.created_at or datetime.now(timezone.utc),
                    raw_data={
                        "public_metrics": (
                            dict(tweet.public_metrics) if tweet.public_metrics else {}
                        ),
                        "entities": (
                            dict(tweet.entities) if tweet.entities else {}
                        ),
                    },
                )
            )

        logger.info("Fetched %d tweets for query: %s", len(tweets), query)
        return tweets

    def get_user_tweets(
        self,
        username: str,
        since_id: Optional[str] = None,
        max_results: int = 20,
    ) -> list[FetchedTweet]:
        """Get recent tweets from a specific user.

        Args:
            username: Twitter handle (without @).
            since_id: Only return tweets newer than this ID.
            max_results: Max tweets to return.

        Returns:
            List of FetchedTweet objects.
        """
        max_results = min(max(max_results, 5), 100)

        # First resolve username to user ID
        try:
            user_resp = self._client.get_user(username=username)
        except tweepy.TooManyRequests:
            logger.warning("Rate limited resolving user: %s", username)
            return []
        except tweepy.TwitterServerError as exc:
            logger.error("Twitter server error resolving user %s: %s", username, exc)
            return []

        if not user_resp or not user_resp.data:
            logger.warning("User not found: %s", username)
            return []

        user = user_resp.data
        followers = None
        if hasattr(user, "public_metrics") and user.public_metrics:
            followers = user.public_metrics.get("followers_count")

        try:
            tweets_resp = self._client.get_users_tweets(
                id=user.id,
                since_id=since_id,
                max_results=max_results,
                tweet_fields=["created_at", "public_metrics", "entities"],
                exclude=["retweets", "replies"],
            )
        except tweepy.TooManyRequests:
            logger.warning("Rate limited fetching tweets for: %s", username)
            return []
        except tweepy.TwitterServerError as exc:
            logger.error("Twitter server error for user %s: %s", username, exc)
            return []

        if not tweets_resp.data:
            return []

        tweets: list[FetchedTweet] = []
        for tweet in tweets_resp.data:
            tweets.append(
                FetchedTweet(
                    tweet_id=str(tweet.id),
                    author=username,
                    author_followers=followers,
                    content=tweet.text,
                    url=f"https://x.com/{username}/status/{tweet.id}",
                    published_at=tweet.created_at or datetime.now(timezone.utc),
                    raw_data={
                        "public_metrics": (
                            dict(tweet.public_metrics) if tweet.public_metrics else {}
                        ),
                        "entities": (
                            dict(tweet.entities) if tweet.entities else {}
                        ),
                    },
                )
            )

        logger.info("Fetched %d tweets from @%s", len(tweets), username)
        return tweets

    def build_search_queries(self) -> list[str]:
        """Build Twitter search queries from configured keywords.

        Groups keywords into queries that fit Twitter's max query length (512 chars).
        Adds quality filters to reduce noise.
        """
        filters = " -is:retweet lang:en"
        max_query_len = 512 - len(filters)

        queries: list[str] = []
        current_terms: list[str] = []
        current_len = 0

        for keyword in self.config.search_keywords:
            # Each term needs quotes + " OR " separator
            term = f'"{keyword}"'
            separator_len = len(" OR ") if current_terms else 0
            term_len = len(term) + separator_len

            if current_len + term_len > max_query_len and current_terms:
                query_body = " OR ".join(current_terms)
                queries.append(f"({query_body}){filters}")
                current_terms = []
                current_len = 0

            current_terms.append(term)
            current_len += term_len

        if current_terms:
            query_body = " OR ".join(current_terms)
            queries.append(f"({query_body}){filters}")

        return queries
