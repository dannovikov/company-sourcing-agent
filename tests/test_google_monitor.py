"""Tests for the Google News monitor integration."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.google.client import GoogleNewsClient, NewsArticle
from src.google.config import GoogleNewsConfig
from src.google.monitor import GoogleNewsMonitor
from src.models import Base
from src.models.company import Company
from src.models.signal import Signal, SignalType


@pytest.fixture
def engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def mock_client():
    return AsyncMock(spec=GoogleNewsClient)


@pytest.fixture
def config():
    return GoogleNewsConfig(max_results_per_query=10)


def _make_article(title: str, url: str = "https://example.com/article", **kwargs) -> NewsArticle:
    defaults = dict(
        source="TechCrunch",
        published_at=datetime(2025, 4, 9, tzinfo=timezone.utc),
        query="startup funding",
    )
    defaults.update(kwargs)
    return NewsArticle(title=title, url=url, **defaults)


class TestGoogleNewsMonitor:
    async def test_full_run_with_funding(self, mock_client, session, config):
        articles = [
            _make_article(
                "Acme raises $10M Series A",
                url="https://tc.com/acme",
            ),
            _make_article(
                "Some random tech news about nothing",
                url="https://example.com/random",
            ),
            _make_article(
                "BetaCo secures $5M seed funding",
                url="https://vb.com/betaco",
            ),
        ]
        mock_client.fetch_all.return_value = articles

        monitor = GoogleNewsMonitor(client=mock_client, session=session, config=config)
        result = await monitor.run()

        assert result.articles_fetched == 3
        assert result.signals_found == 2
        assert result.new_signals_stored == 2
        assert result.new_companies == 2
        assert len(result.errors) == 0

        companies = session.query(Company).all()
        names = {c.name for c in companies}
        assert "Acme" in names
        assert "BetaCo" in names

        for c in companies:
            assert c.source == "google"

        signals = session.query(Signal).all()
        assert len(signals) == 2
        assert all(s.signal_type == SignalType.FUNDING for s in signals)

    async def test_deduplicates_on_second_run(self, mock_client, session, config):
        articles = [
            _make_article("Acme raises $10M Series A", url="https://tc.com/acme"),
        ]
        mock_client.fetch_all.return_value = articles

        monitor = GoogleNewsMonitor(client=mock_client, session=session, config=config)

        r1 = await monitor.run()
        assert r1.new_signals_stored == 1

        r2 = await monitor.run()
        assert r2.signals_found == 1
        assert r2.new_signals_stored == 0  # duplicate

    async def test_handles_fetch_error(self, mock_client, session, config):
        mock_client.fetch_all.side_effect = Exception("network error")

        monitor = GoogleNewsMonitor(client=mock_client, session=session, config=config)
        result = await monitor.run()

        assert result.articles_fetched == 0
        assert len(result.errors) == 1
        assert "network error" in result.errors[0]

    async def test_stores_raw_data(self, mock_client, session, config):
        articles = [
            _make_article(
                "Acme raises $10M Series A",
                url="https://tc.com/acme",
                source="TechCrunch",
            ),
        ]
        mock_client.fetch_all.return_value = articles

        monitor = GoogleNewsMonitor(client=mock_client, session=session, config=config)
        await monitor.run()

        signal = session.query(Signal).first()
        assert signal is not None
        assert signal.raw_data is not None

        import json
        raw = json.loads(signal.raw_data)
        assert raw["title"] == "Acme raises $10M Series A"
        assert raw["url"] == "https://tc.com/acme"
        assert raw["source"] == "TechCrunch"
        assert raw["query"] == "startup funding"

    async def test_updates_existing_company(self, mock_client, session, config):
        """If a company already exists, we should update it rather than create a duplicate."""
        # Create existing company
        existing = Company(name="Acme", source="hackernews", description="From HN")
        session.add(existing)
        session.commit()

        articles = [
            _make_article(
                "Acme raises $10M Series A",
                url="https://tc.com/acme",
            ),
        ]
        mock_client.fetch_all.return_value = articles

        monitor = GoogleNewsMonitor(client=mock_client, session=session, config=config)
        result = await monitor.run()

        assert result.new_companies == 0
        assert result.new_signals_stored == 1

        companies = session.query(Company).all()
        assert len(companies) == 1
        assert companies[0].source == "hackernews"  # original source preserved
        assert "tc.com" in companies[0].urls

    async def test_mixed_signal_types(self, mock_client, session, config):
        articles = [
            _make_article(
                "Acme raises $10M seed",
                url="https://tc.com/acme-funding",
            ),
            _make_article(
                "BetaCo launches new AI platform",
                url="https://vb.com/betaco-launch",
            ),
            _make_article(
                "GammaCo partners with Microsoft",
                url="https://cnbc.com/gammaco-partner",
            ),
        ]
        mock_client.fetch_all.return_value = articles

        monitor = GoogleNewsMonitor(client=mock_client, session=session, config=config)
        result = await monitor.run()

        assert result.signals_found == 3
        assert result.new_companies == 3

        signals = session.query(Signal).all()
        types = {s.signal_type for s in signals}
        assert SignalType.FUNDING in types
        assert SignalType.PRODUCT_LAUNCH in types
        assert SignalType.PARTNERSHIP in types

    async def test_handles_individual_article_error(self, mock_client, session, config):
        """If one article fails processing, others should still be stored."""
        articles = [
            _make_article("Acme raises $10M seed", url="https://tc.com/acme"),
            _make_article("BetaCo launches product", url="https://vb.com/betaco"),
        ]
        mock_client.fetch_all.return_value = articles

        monitor = GoogleNewsMonitor(client=mock_client, session=session, config=config)

        # Patch extract_from_article to fail on first call then succeed
        import src.google.monitor as monitor_module
        original_extract = monitor_module.extract_from_article
        call_count = 0

        def patched_extract(article):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("parse error")
            return original_extract(article)

        monitor_module.extract_from_article = patched_extract
        try:
            result = await monitor.run()
            assert result.new_signals_stored == 1
            assert len(result.errors) == 1
        finally:
            monitor_module.extract_from_article = original_extract
