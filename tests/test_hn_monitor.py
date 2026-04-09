"""Tests for the HN monitor integration."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.hn.client import HNClient, HNItem
from src.hn.monitor import HNMonitor
from src.models import Base
from src.models.company import Company
from src.models.signal import Signal


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
    return AsyncMock(spec=HNClient)


def _make_hn_item(**kwargs) -> HNItem:
    defaults = dict(id=1, type="story", title="", score=10, descendants=5)
    defaults.update(kwargs)
    return HNItem(**defaults)


class TestHNMonitor:
    async def test_full_run_with_show_hn(self, mock_client, session):
        mock_client.get_top_story_ids.return_value = [1, 2]
        mock_client.get_new_story_ids.return_value = [2, 3]
        mock_client.get_show_hn_ids.return_value = [1]

        items = [
            _make_hn_item(id=1, title="Show HN: Acme – AI widgets", url="https://acme.com", score=50),
            _make_hn_item(id=2, title="Some random tech article"),
            _make_hn_item(id=3, title="Show HN: BetaCo – fast database", url="https://beta.co", score=30),
        ]
        mock_client.get_items.return_value = items

        monitor = HNMonitor(client=mock_client, session=session)
        result = await monitor.run(fetch_limit=10)

        assert result.stories_fetched == 3
        assert result.signals_found == 2
        assert result.new_signals_stored == 2
        assert result.new_companies == 2
        assert len(result.errors) == 0

        # Verify DB state
        companies = session.query(Company).all()
        names = {c.name for c in companies}
        assert "Acme" in names
        assert "BetaCo" in names

        signals = session.query(Signal).all()
        assert len(signals) == 2

    async def test_deduplicates_on_second_run(self, mock_client, session):
        mock_client.get_top_story_ids.return_value = [1]
        mock_client.get_new_story_ids.return_value = []
        mock_client.get_show_hn_ids.return_value = []
        mock_client.get_items.return_value = [
            _make_hn_item(id=1, title="Show HN: Acme – widgets", score=50),
        ]

        monitor = HNMonitor(client=mock_client, session=session)

        r1 = await monitor.run(fetch_limit=10)
        assert r1.new_signals_stored == 1

        r2 = await monitor.run(fetch_limit=10)
        assert r2.signals_found == 1
        assert r2.new_signals_stored == 0  # duplicate

    async def test_handles_fetch_error(self, mock_client, session):
        mock_client.get_top_story_ids.side_effect = Exception("network error")

        monitor = HNMonitor(client=mock_client, session=session)
        result = await monitor.run()

        assert result.stories_fetched == 0
        assert len(result.errors) == 1
        assert "network error" in result.errors[0]

    async def test_stores_raw_data(self, mock_client, session):
        """Verify raw HN data is stored on the signal for debugging."""
        mock_client.get_top_story_ids.return_value = [1]
        mock_client.get_new_story_ids.return_value = []
        mock_client.get_show_hn_ids.return_value = []
        mock_client.get_items.return_value = [
            _make_hn_item(id=42, title="Show HN: Acme – widgets", by="pg", score=99, descendants=50),
        ]

        monitor = HNMonitor(client=mock_client, session=session)
        await monitor.run(fetch_limit=10)

        signal = session.query(Signal).first()
        assert signal is not None
        assert signal.raw_data is not None
        import json
        raw = json.loads(signal.raw_data)
        assert raw["hn_id"] == 42
        assert raw["by"] == "pg"
        assert raw["score"] == 99

    async def test_extracts_domain_from_url(self, mock_client, session):
        """Verify domain is extracted from item URL."""
        mock_client.get_top_story_ids.return_value = [1]
        mock_client.get_new_story_ids.return_value = []
        mock_client.get_show_hn_ids.return_value = []
        mock_client.get_items.return_value = [
            _make_hn_item(id=1, title="Show HN: Acme – AI tools", url="https://www.acme.com/product"),
        ]

        monitor = HNMonitor(client=mock_client, session=session)
        await monitor.run(fetch_limit=10)

        company = session.query(Company).first()
        assert company is not None
        assert company.domain == "acme.com"
        assert company.source == "hackernews"
