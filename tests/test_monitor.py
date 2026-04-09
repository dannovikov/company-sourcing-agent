"""Tests for the Twitter monitor orchestrator."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models import Base
from src.models.company import Company
from src.models.crawl_state import CrawlState
from src.models.signal import Signal
from src.sources.config import MonitorConfig, TwitterConfig
from src.sources.monitor import TwitterMonitor
from src.sources.twitter_api import FetchedTweet


@pytest.fixture
def db_session():
    """Create an in-memory DB session with all tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def config():
    return MonitorConfig(
        twitter=TwitterConfig(bearer_token=None),
        search_keywords=["startup launched", "seed round"],
        monitored_accounts=["ycombinator"],
    )


def _make_tweet(tweet_id: str, content: str) -> FetchedTweet:
    return FetchedTweet(
        tweet_id=tweet_id,
        author="testuser",
        content=content,
        url=f"https://x.com/testuser/status/{tweet_id}",
        published_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )


class TestTwitterMonitor:
    def test_uses_scraper_when_no_api_key(self, db_session, config):
        monitor = TwitterMonitor(session=db_session, config=config)
        assert monitor._scraper is not None
        assert monitor._api_client is None
        monitor.close()

    @patch("src.sources.monitor.TwitterScraper")
    def test_run_stores_signals_and_companies(self, mock_scraper_cls, db_session):
        config = MonitorConfig(
            twitter=TwitterConfig(bearer_token=None),
            search_keywords=["test"],
            monitored_accounts=[],
        )

        mock_scraper = MagicMock()
        mock_scraper.search.return_value = [
            _make_tweet("1", "@AcmeAI raised $5M in seed funding"),
            _make_tweet("2", "Check out @BetaTech - just launched today"),
        ]
        mock_scraper.get_user_rss.return_value = []
        mock_scraper.get_user_tweets.return_value = []
        mock_scraper_cls.return_value = mock_scraper

        monitor = TwitterMonitor(session=db_session, config=config)
        monitor._scraper = mock_scraper

        result = monitor.run()

        assert result.tweets_fetched == 2
        assert result.signals_created > 0
        assert result.companies_created > 0

        # Verify data is in the DB
        companies = db_session.query(Company).all()
        assert len(companies) > 0

        signals = db_session.query(Signal).all()
        assert len(signals) > 0

        monitor.close()

    @patch("src.sources.monitor.TwitterScraper")
    def test_run_is_idempotent(self, mock_scraper_cls, db_session):
        config = MonitorConfig(
            twitter=TwitterConfig(bearer_token=None),
            search_keywords=["test"],
            monitored_accounts=[],
        )

        tweets = [_make_tweet("1", "@AcmeAI launched today")]

        mock_scraper = MagicMock()
        mock_scraper.search.return_value = tweets
        mock_scraper.get_user_rss.return_value = []
        mock_scraper.get_user_tweets.return_value = []
        mock_scraper_cls.return_value = mock_scraper

        monitor = TwitterMonitor(session=db_session, config=config)
        monitor._scraper = mock_scraper

        result1 = monitor.run()
        result2 = monitor.run()

        assert result1.signals_created >= 1
        assert result2.duplicates_skipped >= 1
        assert result2.signals_created == 0

        monitor.close()

    @patch("src.sources.monitor.TwitterScraper")
    def test_crawl_state_is_updated(self, mock_scraper_cls, db_session):
        config = MonitorConfig(
            twitter=TwitterConfig(bearer_token=None),
            search_keywords=["test"],
            monitored_accounts=[],
        )

        mock_scraper = MagicMock()
        mock_scraper.search.return_value = [
            _make_tweet("42", "@AcmeAI just launched"),
        ]
        mock_scraper.get_user_rss.return_value = []
        mock_scraper.get_user_tweets.return_value = []
        mock_scraper_cls.return_value = mock_scraper

        monitor = TwitterMonitor(session=db_session, config=config)
        monitor._scraper = mock_scraper
        monitor.run()

        state = (
            db_session.query(CrawlState)
            .filter(CrawlState.source == "x_twitter")
            .first()
        )
        assert state is not None
        assert state.last_external_id == "42"
        assert state.last_crawled_at is not None

        monitor.close()

    @patch("src.sources.monitor.TwitterScraper")
    def test_existing_company_is_reused(self, mock_scraper_cls, db_session):
        """If a company already exists, we link the signal to it instead of creating a dupe."""
        config = MonitorConfig(
            twitter=TwitterConfig(bearer_token=None),
            search_keywords=["test"],
            monitored_accounts=[],
        )

        # Pre-create a company
        existing = Company(name="AcmeAI", source="manual")
        db_session.add(existing)
        db_session.commit()
        existing_id = existing.id

        mock_scraper = MagicMock()
        mock_scraper.search.return_value = [
            _make_tweet("99", "@AcmeAI raised $10M in Series A"),
        ]
        mock_scraper.get_user_rss.return_value = []
        mock_scraper.get_user_tweets.return_value = []
        mock_scraper_cls.return_value = mock_scraper

        monitor = TwitterMonitor(session=db_session, config=config)
        monitor._scraper = mock_scraper
        result = monitor.run()

        # Should create a signal but not a new company
        assert result.signals_created >= 1
        companies = db_session.query(Company).all()
        assert len(companies) == 1
        assert companies[0].id == existing_id

        monitor.close()
