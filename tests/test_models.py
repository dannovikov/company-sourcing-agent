from datetime import datetime, timezone

from src.models import Company, Score, Signal, SignalType


class TestCompany:
    def test_create_company(self, session):
        company = Company(
            name="Acme Corp",
            description="A promising AI startup",
            domain="acme.ai",
            source="hackernews",
        )
        session.add(company)
        session.commit()

        result = session.query(Company).first()
        assert result is not None
        assert result.name == "Acme Corp"
        assert result.description == "A promising AI startup"
        assert result.domain == "acme.ai"
        assert result.source == "hackernews"
        assert result.status == "discovered"
        assert result.id is not None
        assert result.created_at is not None

    def test_company_with_urls(self, session):
        company = Company(
            name="Test Co",
            urls="https://test.co|https://github.com/testco",
            source="google",
        )
        session.add(company)
        session.commit()

        result = session.query(Company).first()
        urls = result.urls.split("|")
        assert len(urls) == 2
        assert "https://test.co" in urls

    def test_company_status_lifecycle(self, session):
        company = Company(name="Lifecycle Co", source="manual")
        session.add(company)
        session.commit()
        assert company.status == "discovered"

        company.status = "researching"
        session.commit()
        assert session.query(Company).first().status == "researching"

    def test_unique_domain_constraint(self, session):
        c1 = Company(name="First", domain="unique.com", source="hackernews")
        c2 = Company(name="Second", domain="unique.com", source="google")
        session.add(c1)
        session.commit()
        session.add(c2)

        from sqlalchemy.exc import IntegrityError
        import pytest

        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


class TestSignal:
    def test_create_signal(self, session):
        company = Company(name="Signal Co", source="hackernews")
        session.add(company)
        session.commit()

        signal = Signal(
            company_id=company.id,
            signal_type=SignalType.HN_MENTION,
            title="Show HN: Signal Co - a new way to do X",
            source_url="https://news.ycombinator.com/item?id=12345",
        )
        session.add(signal)
        session.commit()

        result = session.query(Signal).first()
        assert result.signal_type == SignalType.HN_MENTION
        assert result.title == "Show HN: Signal Co - a new way to do X"
        assert result.company_id == company.id

    def test_signal_types(self):
        """Verify all expected signal types exist."""
        expected = {
            "funding", "product_launch", "hn_mention", "hn_trending",
            "x_mention", "x_trending", "google_news", "hiring_surge",
            "partnership", "award", "other",
        }
        actual = {t.value for t in SignalType}
        assert actual == expected

    def test_signal_company_relationship(self, session):
        company = Company(name="Rel Co", source="x_twitter")
        session.add(company)
        session.commit()

        s1 = Signal(
            company_id=company.id,
            signal_type=SignalType.FUNDING,
            title="Series A announced",
        )
        s2 = Signal(
            company_id=company.id,
            signal_type=SignalType.X_TRENDING,
            title="Trending on X",
        )
        session.add_all([s1, s2])
        session.commit()

        session.refresh(company)
        assert len(company.signals) == 2
        assert s1.company.name == "Rel Co"

    def test_cascade_delete_signals(self, session):
        company = Company(name="Delete Co", source="manual")
        session.add(company)
        session.commit()

        signal = Signal(
            company_id=company.id,
            signal_type=SignalType.OTHER,
            title="Some signal",
        )
        session.add(signal)
        session.commit()

        session.delete(company)
        session.commit()

        assert session.query(Signal).count() == 0


class TestScore:
    def test_create_score(self, session):
        company = Company(name="Score Co", source="hackernews")
        session.add(company)
        session.commit()

        score = Score(
            company_id=company.id,
            overall=85.5,
            signal_strength=90.0,
            market_potential=80.0,
            momentum=75.0,
            reasoning="Strong signals and large TAM",
        )
        session.add(score)
        session.commit()

        result = session.query(Score).first()
        assert result.overall == 85.5
        assert result.signal_strength == 90.0
        assert result.market_potential == 80.0
        assert result.momentum == 75.0
        assert result.team_quality is None  # optional
        assert result.scored_by == "agent"
        assert result.reasoning == "Strong signals and large TAM"

    def test_multiple_scores_history(self, session):
        company = Company(name="History Co", source="google")
        session.add(company)
        session.commit()

        s1 = Score(company_id=company.id, overall=60.0, scored_by="model_v1")
        s2 = Score(company_id=company.id, overall=75.0, scored_by="model_v2")
        session.add_all([s1, s2])
        session.commit()

        session.refresh(company)
        assert len(company.scores) == 2
        scores = sorted(company.scores, key=lambda s: s.overall)
        assert scores[0].overall == 60.0
        assert scores[1].overall == 75.0

    def test_cascade_delete_scores(self, session):
        company = Company(name="Cascade Co", source="manual")
        session.add(company)
        session.commit()

        score = Score(company_id=company.id, overall=50.0)
        session.add(score)
        session.commit()

        session.delete(company)
        session.commit()

        assert session.query(Score).count() == 0


class TestDatabaseInit:
    def test_init_db(self):
        """Test that init_db creates all tables."""
        from src.db.session import init_db
        from sqlalchemy import inspect

        engine = init_db("sqlite:///:memory:")
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        assert "companies" in tables
        assert "signals" in tables
        assert "scores" in tables
        engine.dispose()
