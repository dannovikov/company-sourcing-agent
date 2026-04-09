"""Tests for the dashboard API endpoints."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import Base, Company, Signal, SignalType, Score
from src.dashboard.app import create_app, _get_session


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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


@pytest.fixture
def client(session):
    """Create a test client with the session dependency overridden."""
    app = create_app()

    def _override_session():
        yield session

    app.dependency_overrides[_get_session] = _override_session
    return TestClient(app)


def _seed_company(session, name="TestCo", source="hackernews", signal_types=None, signal_age_days=None):
    """Helper to create a company with signals."""
    c = Company(name=name, source=source, status="discovered")
    session.add(c)
    session.flush()

    signal_types = signal_types or [SignalType.HN_MENTION]
    signal_age_days = signal_age_days or [1]

    now = datetime.now(timezone.utc)
    for st, age in zip(signal_types, signal_age_days):
        sig = Signal(
            company_id=c.id,
            signal_type=st,
            title=f"{st.value} signal for {name}",
            created_at=now - timedelta(days=age),
        )
        session.add(sig)
    session.flush()
    return c


class TestDashboardUI:
    def test_serves_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Company Sourcing Agent" in resp.text


class TestListCompanies:
    def test_empty_database(self, client):
        resp = client.get("/api/companies")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_companies(self, client, session):
        _seed_company(session, "AlphaCo", signal_types=[SignalType.FUNDING])
        _seed_company(session, "BetaCo", signal_types=[SignalType.HN_MENTION])

        resp = client.get("/api/companies")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

        # Check structure
        company = data[0]
        assert "id" in company
        assert "name" in company
        assert "overall_score" in company
        assert "signal_strength" in company
        assert "momentum" in company
        assert "signal_count" in company
        assert "trending" in company

    def test_sorted_by_score(self, client, session):
        _seed_company(session, "LowCo", signal_types=[SignalType.OTHER], signal_age_days=[30])
        _seed_company(
            session, "HighCo",
            signal_types=[SignalType.FUNDING, SignalType.PRODUCT_LAUNCH],
            signal_age_days=[1, 2],
        )

        resp = client.get("/api/companies?sort=score")
        data = resp.json()
        assert data[0]["name"] == "HighCo"
        assert data[0]["overall_score"] >= data[1]["overall_score"]

    def test_limit_parameter(self, client, session):
        for i in range(5):
            _seed_company(session, f"Co{i}")

        resp = client.get("/api/companies?limit=2")
        assert len(resp.json()) == 2

    def test_direction_filter(self, client, session):
        # Company with only old signals → likely stable/down
        _seed_company(session, "OldCo", signal_types=[SignalType.HN_MENTION], signal_age_days=[25])
        # Company with recent signals → likely up
        _seed_company(
            session, "HotCo",
            signal_types=[SignalType.FUNDING, SignalType.PRODUCT_LAUNCH],
            signal_age_days=[1, 2],
        )

        resp = client.get("/api/companies?direction=all")
        assert len(resp.json()) == 2

    def test_sort_by_name(self, client, session):
        _seed_company(session, "Zebra")
        _seed_company(session, "Alpha")

        resp = client.get("/api/companies?sort=name")
        data = resp.json()
        assert data[0]["name"] == "Alpha"

    def test_sort_by_signals(self, client, session):
        _seed_company(session, "FewSignals", signal_types=[SignalType.HN_MENTION], signal_age_days=[1])
        _seed_company(
            session, "ManySignals",
            signal_types=[SignalType.FUNDING, SignalType.PRODUCT_LAUNCH, SignalType.HN_MENTION],
            signal_age_days=[1, 2, 3],
        )

        resp = client.get("/api/companies?sort=signals")
        data = resp.json()
        assert data[0]["name"] == "ManySignals"


class TestCompanyDetail:
    def test_not_found(self, client):
        resp = client.get("/api/companies/nonexistent-id")
        assert resp.status_code == 404

    def test_returns_detail(self, client, session):
        c = _seed_company(
            session, "DetailCo",
            signal_types=[SignalType.FUNDING, SignalType.HN_MENTION],
            signal_age_days=[1, 5],
        )

        resp = client.get(f"/api/companies/{c.id}")
        assert resp.status_code == 200
        data = resp.json()

        assert data["name"] == "DetailCo"
        assert data["source"] == "hackernews"
        assert "score" in data
        assert data["score"]["overall"] > 0
        assert data["signal_count"] == 2
        assert len(data["signals"]) == 2

        # Signals should have structure
        sig = data["signals"][0]
        assert "type" in sig
        assert "title" in sig
        assert "created_at" in sig

    def test_signals_ordered_by_recency(self, client, session):
        c = _seed_company(
            session, "OrderCo",
            signal_types=[SignalType.HN_MENTION, SignalType.FUNDING],
            signal_age_days=[10, 1],
        )

        resp = client.get(f"/api/companies/{c.id}")
        data = resp.json()

        # Most recent first
        dates = [s["created_at"] for s in data["signals"]]
        assert dates == sorted(dates, reverse=True)


class TestRefreshScores:
    def test_refresh_creates_scores(self, client, session):
        _seed_company(session, "RefreshCo", signal_types=[SignalType.FUNDING])

        resp = client.post("/api/score/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scored"] == 1
        assert len(data["top_5"]) == 1

    def test_refresh_empty_db(self, client):
        resp = client.post("/api/score/refresh")
        assert resp.status_code == 200
        assert resp.json()["scored"] == 0


class TestStats:
    def test_empty_stats(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_companies"] == 0
        assert data["total_signals"] == 0

    def test_populated_stats(self, client, session):
        _seed_company(
            session, "StatCo",
            signal_types=[SignalType.FUNDING, SignalType.HN_MENTION],
            signal_age_days=[1, 3],
        )
        _seed_company(session, "StatCo2", signal_types=[SignalType.PRODUCT_LAUNCH])

        resp = client.get("/api/stats")
        data = resp.json()
        assert data["total_companies"] == 2
        assert data["total_signals"] == 3
        assert data["top_score"] > 0
