"""Tests for the scoring engine."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models import Base, Company, Signal, SignalType, Score
from src.scoring.engine import (
    ScoringEngine,
    _recency_factor,
    _compute_momentum,
    _compute_source_diversity,
    _trending_direction,
    SIGNAL_WEIGHTS,
    RECENCY_HALF_LIFE_DAYS,
    CompanyScore,
)


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def session(engine):
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def _make_company(session, name="TestCo", source="hackernews"):
    c = Company(name=name, source=source, status="discovered")
    session.add(c)
    session.flush()
    return c


def _make_signal(session, company, signal_type=SignalType.HN_MENTION, title="Test signal", age_days=0):
    now = datetime.now(timezone.utc)
    sig = Signal(
        company_id=company.id,
        signal_type=signal_type,
        title=title,
        created_at=now - timedelta(days=age_days),
    )
    session.add(sig)
    session.flush()
    return sig


# --- Unit tests for helper functions ---


class TestRecencyFactor:
    def test_brand_new_signal(self):
        now = datetime.now(timezone.utc)
        assert _recency_factor(now, now) == pytest.approx(1.0)

    def test_one_half_life_old(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=RECENCY_HALF_LIFE_DAYS)
        assert _recency_factor(old, now) == pytest.approx(0.5, abs=0.01)

    def test_two_half_lives_old(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=RECENCY_HALF_LIFE_DAYS * 2)
        assert _recency_factor(old, now) == pytest.approx(0.25, abs=0.01)

    def test_naive_datetime_handled(self):
        """Naive datetimes should be treated as UTC."""
        now = datetime(2024, 1, 15, 12, 0, 0)
        old = datetime(2024, 1, 1, 12, 0, 0)
        result = _recency_factor(old, now)
        assert 0 < result < 1

    def test_future_signal_clamped(self):
        now = datetime.now(timezone.utc)
        future = now + timedelta(days=1)
        assert _recency_factor(future, now) == pytest.approx(1.0)


class TestComputeMomentum:
    def test_no_signals(self):
        assert _compute_momentum([], datetime.now(timezone.utc)) == 50.0

    def test_all_recent_signals(self, session):
        """All signals in last 7 days = high momentum."""
        c = _make_company(session)
        _make_signal(session, c, SignalType.FUNDING, age_days=1)
        _make_signal(session, c, SignalType.PRODUCT_LAUNCH, age_days=3)
        session.flush()

        result = _compute_momentum(c.signals, datetime.now(timezone.utc))
        assert result > 60  # Should be high

    def test_all_old_signals(self, session):
        """All signals 10-20 days ago = low momentum."""
        c = _make_company(session)
        _make_signal(session, c, SignalType.FUNDING, age_days=15)
        _make_signal(session, c, SignalType.HN_MENTION, age_days=20)
        session.flush()

        result = _compute_momentum(c.signals, datetime.now(timezone.utc))
        assert result < 40  # Should be low


class TestSourceDiversity:
    def test_no_signals(self):
        assert _compute_source_diversity([]) == 0.0

    def test_single_signal_type(self, session):
        c = _make_company(session)
        _make_signal(session, c, SignalType.HN_MENTION)
        session.flush()
        result = _compute_source_diversity(c.signals)
        assert 0 < result < 50  # Low diversity

    def test_multiple_sources(self, session):
        c = _make_company(session)
        _make_signal(session, c, SignalType.HN_MENTION)
        _make_signal(session, c, SignalType.X_MENTION)
        _make_signal(session, c, SignalType.FUNDING)
        session.flush()
        result = _compute_source_diversity(c.signals)
        assert result > 50  # Good diversity


class TestTrendingDirection:
    def test_up(self):
        assert _trending_direction(75) == "up"

    def test_down(self):
        assert _trending_direction(25) == "down"

    def test_stable(self):
        assert _trending_direction(50) == "stable"

    def test_boundaries(self):
        assert _trending_direction(65) == "up"
        assert _trending_direction(64.9) == "stable"
        assert _trending_direction(35) == "down"
        assert _trending_direction(35.1) == "stable"


# --- Integration tests for ScoringEngine ---


class TestScoringEngine:
    def test_score_company_no_signals(self, session):
        c = _make_company(session)
        session.flush()

        engine = ScoringEngine(session)
        result = engine.score_company(c)

        assert result.overall >= 0
        assert result.signal_count == 0
        assert result.company_name == "TestCo"

    def test_score_company_with_funding(self, session):
        c = _make_company(session)
        _make_signal(session, c, SignalType.FUNDING, "Series A", age_days=1)
        session.flush()

        engine = ScoringEngine(session)
        result = engine.score_company(c)

        assert result.overall > 0
        assert result.signal_strength > 0
        assert result.signal_count == 1
        assert "signal" in result.reasoning.lower()

    def test_funding_scores_higher_than_mention(self, session):
        """Funding signals should produce higher scores than simple mentions."""
        c1 = _make_company(session, name="FundedCo")
        _make_signal(session, c1, SignalType.FUNDING, "Big raise", age_days=1)
        session.flush()

        c2 = _make_company(session, name="MentionedCo")
        _make_signal(session, c2, SignalType.HN_MENTION, "Just mentioned", age_days=1)
        session.flush()

        engine = ScoringEngine(session)
        s1 = engine.score_company(c1)
        s2 = engine.score_company(c2)

        assert s1.signal_strength > s2.signal_strength

    def test_recent_signals_score_higher(self, session):
        """Recent signals should produce higher scores than old ones."""
        c1 = _make_company(session, name="RecentCo")
        _make_signal(session, c1, SignalType.FUNDING, "New raise", age_days=1)
        session.flush()

        c2 = _make_company(session, name="OldCo")
        _make_signal(session, c2, SignalType.FUNDING, "Old raise", age_days=60)
        session.flush()

        engine = ScoringEngine(session)
        s1 = engine.score_company(c1)
        s2 = engine.score_company(c2)

        assert s1.signal_strength > s2.signal_strength

    def test_multiple_signals_boost_score(self, session):
        c1 = _make_company(session, name="MultipleCo")
        _make_signal(session, c1, SignalType.FUNDING, "Raised A", age_days=1)
        _make_signal(session, c1, SignalType.HN_TRENDING, "Trending on HN", age_days=2)
        _make_signal(session, c1, SignalType.X_MENTION, "Tweeted about", age_days=3)
        session.flush()

        c2 = _make_company(session, name="SingleCo")
        _make_signal(session, c2, SignalType.HN_MENTION, "Mentioned once", age_days=1)
        session.flush()

        engine = ScoringEngine(session)
        s1 = engine.score_company(c1)
        s2 = engine.score_company(c2)

        assert s1.overall > s2.overall

    def test_score_all_returns_sorted(self, session):
        c1 = _make_company(session, name="LowCo")
        _make_signal(session, c1, SignalType.OTHER, "low", age_days=30)

        c2 = _make_company(session, name="HighCo")
        _make_signal(session, c2, SignalType.FUNDING, "high", age_days=1)
        _make_signal(session, c2, SignalType.PRODUCT_LAUNCH, "launch", age_days=2)
        session.flush()

        engine = ScoringEngine(session)
        results = engine.score_all(persist=False)

        assert len(results) == 2
        assert results[0].company_name == "HighCo"
        assert results[0].overall >= results[1].overall

    def test_score_all_persists(self, session):
        c = _make_company(session)
        _make_signal(session, c, SignalType.FUNDING, "raise", age_days=1)
        session.flush()

        engine = ScoringEngine(session)
        engine.score_all(persist=True)

        scores = session.query(Score).filter(Score.company_id == c.id).all()
        assert len(scores) == 1
        assert scores[0].overall > 0
        assert scores[0].scored_by == "scoring_engine_v1"

        # Company status updated
        session.refresh(c)
        assert c.status == "scored"

    def test_score_all_no_persist(self, session):
        c = _make_company(session)
        _make_signal(session, c, SignalType.FUNDING, "raise", age_days=1)
        session.flush()

        engine = ScoringEngine(session)
        engine.score_all(persist=False)

        scores = session.query(Score).filter(Score.company_id == c.id).all()
        assert len(scores) == 0

    def test_get_ranked_companies_limit(self, session):
        for i in range(5):
            c = _make_company(session, name=f"Co{i}")
            _make_signal(session, c, SignalType.HN_MENTION, f"sig{i}", age_days=i)
        session.flush()

        engine = ScoringEngine(session)
        results = engine.get_ranked_companies(limit=3)

        assert len(results) == 3

    def test_signal_summaries_populated(self, session):
        c = _make_company(session)
        _make_signal(session, c, SignalType.FUNDING, "raise", age_days=1)
        _make_signal(session, c, SignalType.HN_MENTION, "mention", age_days=5)
        session.flush()

        engine = ScoringEngine(session)
        result = engine.score_company(c)

        assert len(result.signal_summaries) == 2
        for s in result.signal_summaries:
            assert s.weight > 0
            assert 0 < s.recency_factor <= 1.0
            assert s.effective_weight > 0

    def test_trending_direction_set(self, session):
        c = _make_company(session)
        _make_signal(session, c, SignalType.FUNDING, "raise", age_days=1)
        _make_signal(session, c, SignalType.PRODUCT_LAUNCH, "launch", age_days=2)
        session.flush()

        engine = ScoringEngine(session)
        result = engine.score_company(c)
        assert result.trending_direction in ("up", "down", "stable")

    def test_empty_database(self, session):
        engine = ScoringEngine(session)
        results = engine.score_all(persist=False)
        assert results == []
