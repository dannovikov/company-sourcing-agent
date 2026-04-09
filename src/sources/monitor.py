"""Main Twitter/X monitor: orchestrates fetching, parsing, and storing signals.

This is the entry point called by the scheduler/orchestrator. It's designed
to be idempotent — running it multiple times won't create duplicate signals.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from src.models.company import Company
from src.models.crawl_state import CrawlState
from src.models.signal import Signal, SignalType
from src.sources.config import MonitorConfig
from src.sources.parser import ParsedMention, extract_mentions
from src.sources.twitter_api import FetchedTweet, TwitterAPIClient
from src.sources.twitter_scraper import TwitterScraper

logger = logging.getLogger(__name__)


class MonitorResult:
    """Summary of a monitoring run."""

    def __init__(self) -> None:
        self.tweets_fetched: int = 0
        self.signals_created: int = 0
        self.companies_created: int = 0
        self.duplicates_skipped: int = 0

    def __repr__(self) -> str:
        return (
            f"MonitorResult(fetched={self.tweets_fetched}, "
            f"signals={self.signals_created}, "
            f"companies={self.companies_created}, "
            f"dupes={self.duplicates_skipped})"
        )


class TwitterMonitor:
    """Orchestrates Twitter/X monitoring: fetch -> parse -> store.

    Uses the existing SQLAlchemy models (Company, Signal) for persistence.
    """

    SOURCE_KEY = "x_twitter"

    def __init__(
        self,
        session: Session,
        config: Optional[MonitorConfig] = None,
    ) -> None:
        self.session = session
        self.config = config or MonitorConfig()

        # Choose source: API if credentials available, otherwise scraper
        self._api_client: Optional[TwitterAPIClient] = None
        self._scraper: Optional[TwitterScraper] = None

        if self.config.twitter.has_api_access:
            logger.info("Using Twitter API v2 (bearer token found)")
            self._api_client = TwitterAPIClient(self.config)
        else:
            logger.info(
                "No Twitter API credentials found. Using nitter scraper fallback. "
                "Set TWITTER_BEARER_TOKEN for API access."
            )
            self._scraper = TwitterScraper()

    def run(self) -> MonitorResult:
        """Execute a full monitoring cycle.

        1. Fetch tweets from keyword searches
        2. Fetch tweets from monitored accounts
        3. Parse company mentions from all tweets
        4. Create/update Company and Signal records
        5. Update crawl state

        Returns:
            MonitorResult with summary statistics.
        """
        logger.info("Starting Twitter monitoring cycle")
        result = MonitorResult()

        crawl_state = self._get_or_create_crawl_state()
        since_id = crawl_state.last_external_id

        # Phase 1: Keyword search
        search_tweets = self._fetch_search_tweets(since_id)
        result.tweets_fetched += len(search_tweets)

        # Phase 2: Monitored accounts
        account_tweets = self._fetch_account_tweets()
        result.tweets_fetched += len(account_tweets)

        # Phase 3: Process all tweets
        all_tweets = search_tweets + account_tweets
        for tweet in all_tweets:
            self._process_tweet(tweet, result)

        # Phase 4: Update crawl state
        if all_tweets:
            newest = max(all_tweets, key=lambda t: t.published_at)
            crawl_state.last_external_id = newest.tweet_id
            crawl_state.last_crawled_at = datetime.now(timezone.utc)

        self.session.commit()

        logger.info(
            "Monitoring cycle complete: %d fetched, %d signals, %d companies, %d dupes",
            result.tweets_fetched,
            result.signals_created,
            result.companies_created,
            result.duplicates_skipped,
        )
        return result

    def _process_tweet(self, tweet: FetchedTweet, result: MonitorResult) -> None:
        """Parse a tweet and create Company + Signal records."""
        # Check if we already have a signal from this tweet (idempotency)
        source_url = tweet.url
        existing = (
            self.session.query(Signal)
            .filter(Signal.source_url == source_url)
            .first()
        )
        if existing:
            result.duplicates_skipped += 1
            return

        mentions = extract_mentions(tweet)
        if not mentions:
            return

        for mention in mentions:
            company, created = self._get_or_create_company(mention, tweet)
            if created:
                result.companies_created += 1

            signal = Signal(
                company_id=company.id,
                signal_type=mention.signal_type,
                title=f"@{tweet.author}: {tweet.content[:200]}",
                content=tweet.content,
                source_url=source_url,
                raw_data=json.dumps(tweet.raw_data) if tweet.raw_data else None,
            )
            self.session.add(signal)
            result.signals_created += 1

    def _get_or_create_company(
        self, mention: ParsedMention, tweet: FetchedTweet
    ) -> tuple[Company, bool]:
        """Find existing company or create a new one."""
        # Try to find by name (case-insensitive)
        company = (
            self.session.query(Company)
            .filter(Company.name.ilike(mention.company_name))
            .first()
        )

        if company:
            # Update URL if we found a new one
            if mention.company_url and not company.domain:
                company.domain = mention.company_url
            return company, False

        # Try to find by domain if we have a URL
        if mention.company_url:
            domain = mention.company_url.split("//")[-1].split("/")[0].replace("www.", "")
            company = (
                self.session.query(Company)
                .filter(Company.domain == domain)
                .first()
            )
            if company:
                return company, False

        # Create new company
        domain = None
        if mention.company_url:
            domain = mention.company_url.split("//")[-1].split("/")[0].replace("www.", "")

        company = Company(
            name=mention.company_name,
            description=mention.context[:500] if mention.context else None,
            domain=domain,
            source=self.SOURCE_KEY,
        )
        self.session.add(company)
        self.session.flush()  # Get the ID assigned
        return company, True

    def _get_or_create_crawl_state(self) -> CrawlState:
        """Get or create crawl state for this source."""
        state = (
            self.session.query(CrawlState)
            .filter(CrawlState.source == self.SOURCE_KEY)
            .first()
        )
        if state is None:
            state = CrawlState(source=self.SOURCE_KEY)
            self.session.add(state)
            self.session.flush()
        return state

    def _fetch_search_tweets(self, since_id: str | None) -> list[FetchedTweet]:
        """Fetch tweets matching configured keywords."""
        tweets: list[FetchedTweet] = []

        if self._api_client:
            queries = self._api_client.build_search_queries()
            for query in queries:
                try:
                    batch = self._api_client.search_recent(
                        query=query,
                        since_id=since_id,
                        max_results=self.config.max_results_per_query,
                    )
                    tweets.extend(batch)
                except Exception:
                    logger.error("Error searching query: %s", query, exc_info=True)
        elif self._scraper:
            for keyword in self.config.search_keywords[:10]:
                try:
                    batch = self._scraper.search(
                        query=keyword,
                        max_results=self.config.max_results_per_query,
                    )
                    tweets.extend(batch)
                except Exception:
                    logger.error("Error scraping keyword: %s", keyword, exc_info=True)

        logger.info("Search phase: fetched %d tweets", len(tweets))
        return tweets

    def _fetch_account_tweets(self) -> list[FetchedTweet]:
        """Fetch recent tweets from monitored accounts."""
        tweets: list[FetchedTweet] = []

        for account in self.config.monitored_accounts:
            try:
                if self._api_client:
                    batch = self._api_client.get_user_tweets(username=account, max_results=20)
                elif self._scraper:
                    batch = self._scraper.get_user_rss(account, max_results=20)
                    if not batch:
                        batch = self._scraper.get_user_tweets(account, max_results=20)
                else:
                    batch = []
                tweets.extend(batch)
            except Exception:
                logger.error("Error fetching @%s", account, exc_info=True)

        logger.info("Account phase: fetched %d tweets", len(tweets))
        return tweets

    def close(self) -> None:
        """Clean up resources."""
        if self._scraper:
            self._scraper.close()
