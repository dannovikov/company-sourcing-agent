"""FastAPI dashboard application for viewing scored companies."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from src.db.session import get_session_factory
from src.models.company import Company
from src.models.signal import Signal
from src.models.score import Score
from src.scoring.engine import ScoringEngine


def _get_session():
    """Dependency that yields a database session."""
    SessionFactory = get_session_factory()
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI dashboard application."""
    app = FastAPI(
        title="Company Sourcing Agent — Dashboard",
        description="View and rank discovered companies by investment potential",
        version="0.1.0",
    )

    @app.get("/", response_class=HTMLResponse)
    def dashboard_ui():
        """Serve the single-page dashboard."""
        from src.dashboard.ui import DASHBOARD_HTML

        return HTMLResponse(content=DASHBOARD_HTML)

    @app.get("/api/companies")
    def list_companies(
        limit: int = Query(50, ge=1, le=200),
        sort: str = Query("score", pattern="^(score|name|recent|signals)$"),
        direction: str = Query("all", pattern="^(up|down|stable|all)$"),
        session: Session = Depends(_get_session),
    ) -> list[dict[str, Any]]:
        """List companies ranked by investment potential.

        Query params:
          - limit: max results (default 50)
          - sort: sort by 'score', 'name', 'recent', or 'signals'
          - direction: filter by trending direction ('up', 'down', 'stable', 'all')
        """
        engine = ScoringEngine(session)
        scored = engine.get_ranked_companies(limit=200)

        # Filter by trending direction
        if direction != "all":
            scored = [c for c in scored if c.trending_direction == direction]

        # Sort
        if sort == "name":
            scored.sort(key=lambda c: c.company_name.lower())
        elif sort == "recent":
            scored.sort(key=lambda c: max(
                (s.created_at for s in _get_signals(session, c.company_id)),
                default=datetime.min.replace(tzinfo=timezone.utc),
            ), reverse=True)
        elif sort == "signals":
            scored.sort(key=lambda c: c.signal_count, reverse=True)
        # default 'score' is already sorted

        scored = scored[:limit]

        return [
            {
                "id": cs.company_id,
                "name": cs.company_name,
                "overall_score": cs.overall,
                "signal_strength": cs.signal_strength,
                "momentum": cs.momentum,
                "source_diversity": cs.source_diversity,
                "signal_count": cs.signal_count,
                "trending": cs.trending_direction,
                "reasoning": cs.reasoning,
            }
            for cs in scored
        ]

    @app.get("/api/companies/{company_id}")
    def company_detail(
        company_id: str,
        session: Session = Depends(_get_session),
    ) -> dict[str, Any]:
        """Get detailed info for a single company including all signals."""
        company = session.query(Company).filter(Company.id == company_id).first()
        if not company:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Company not found")

        engine = ScoringEngine(session)
        cs = engine.score_company(company)

        signals_data = []
        for sig in sorted(company.signals, key=lambda s: s.created_at, reverse=True):
            signals_data.append(
                {
                    "id": sig.id,
                    "type": sig.signal_type.value,
                    "title": sig.title,
                    "content": sig.content,
                    "source_url": sig.source_url,
                    "created_at": sig.created_at.isoformat() if sig.created_at else None,
                }
            )

        # Score history
        score_history = []
        for sc in sorted(company.scores, key=lambda s: s.created_at):
            score_history.append(
                {
                    "overall": sc.overall,
                    "signal_strength": sc.signal_strength,
                    "momentum": sc.momentum,
                    "scored_by": sc.scored_by,
                    "created_at": sc.created_at.isoformat() if sc.created_at else None,
                }
            )

        return {
            "id": company.id,
            "name": company.name,
            "description": company.description,
            "domain": company.domain,
            "urls": company.urls.split("|") if company.urls else [],
            "source": company.source,
            "status": company.status,
            "discovered_at": company.discovered_at.isoformat()
            if company.discovered_at
            else None,
            "score": {
                "overall": cs.overall,
                "signal_strength": cs.signal_strength,
                "momentum": cs.momentum,
                "source_diversity": cs.source_diversity,
                "trending": cs.trending_direction,
                "reasoning": cs.reasoning,
            },
            "signals": signals_data,
            "signal_count": len(signals_data),
            "score_history": score_history,
        }

    @app.post("/api/score/refresh")
    def refresh_scores(
        session: Session = Depends(_get_session),
    ) -> dict[str, Any]:
        """Recompute and persist scores for all companies."""
        engine = ScoringEngine(session)
        results = engine.score_all(persist=True)
        return {
            "scored": len(results),
            "top_5": [
                {"name": r.company_name, "score": r.overall}
                for r in results[:5]
            ],
        }

    @app.get("/api/stats")
    def dashboard_stats(
        session: Session = Depends(_get_session),
    ) -> dict[str, Any]:
        """Summary statistics for the dashboard."""
        total_companies = session.query(Company).count()
        total_signals = session.query(Signal).count()

        engine = ScoringEngine(session)
        scored = engine.get_ranked_companies(limit=200)

        trending_up = sum(1 for c in scored if c.trending_direction == "up")
        trending_down = sum(1 for c in scored if c.trending_direction == "down")

        return {
            "total_companies": total_companies,
            "total_signals": total_signals,
            "trending_up": trending_up,
            "trending_down": trending_down,
            "top_score": scored[0].overall if scored else 0,
        }

    return app


def _get_signals(session: Session, company_id: str) -> list[Signal]:
    """Fetch signals for a company."""
    return session.query(Signal).filter(Signal.company_id == company_id).all()
