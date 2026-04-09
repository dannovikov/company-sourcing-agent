"""Scoring engine that ranks companies by investment potential.

Aggregates signals per company, weights them by type and recency,
and computes a composite score (0-100) with sub-dimension breakdowns.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from src.models.company import Company
from src.models.signal import Signal, SignalType
from src.models.score import Score


# ---------------------------------------------------------------------------
# Signal weights: how important each signal type is (higher = stronger)
# ---------------------------------------------------------------------------
SIGNAL_WEIGHTS: dict[SignalType, float] = {
    SignalType.FUNDING: 10.0,
    SignalType.PRODUCT_LAUNCH: 7.0,
    SignalType.PARTNERSHIP: 6.0,
    SignalType.HIRING_SURGE: 5.0,
    SignalType.AWARD: 4.0,
    SignalType.HN_TRENDING: 4.0,
    SignalType.X_TRENDING: 4.0,
    SignalType.GOOGLE_NEWS: 3.0,
    SignalType.HN_MENTION: 2.0,
    SignalType.X_MENTION: 2.0,
    SignalType.OTHER: 1.0,
}

# How quickly signals decay in importance (half-life in days)
RECENCY_HALF_LIFE_DAYS = 14.0

# Maximum raw signal score before normalization (caps outliers)
MAX_RAW_SIGNAL_SCORE = 60.0

# Weights for the overall composite score
DIMENSION_WEIGHTS = {
    "signal_strength": 0.40,
    "momentum": 0.35,
    "source_diversity": 0.25,
}


@dataclass
class SignalSummary:
    """Summary of a single signal for scoring purposes."""

    signal_type: SignalType
    created_at: datetime
    weight: float
    recency_factor: float
    effective_weight: float


@dataclass
class CompanyScore:
    """Computed score for a company with full breakdown."""

    company_id: str
    company_name: str
    overall: float
    signal_strength: float
    momentum: float
    source_diversity: float
    signal_count: int
    signal_summaries: list[SignalSummary] = field(default_factory=list)
    reasoning: str = ""
    trending_direction: str = "stable"  # "up", "down", "stable"


def _recency_factor(signal_created: datetime, now: datetime) -> float:
    """Exponential decay based on signal age. Returns 0.0-1.0."""
    if signal_created.tzinfo is None:
        signal_created = signal_created.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    age_days = max((now - signal_created).total_seconds() / 86400, 0)
    return math.pow(0.5, age_days / RECENCY_HALF_LIFE_DAYS)


def _compute_momentum(signals: list[Signal], now: datetime) -> float:
    """Compare recent signal activity (last 7 days) vs prior period (8-30 days).

    Returns 0-100 where:
      - 50 = stable (same activity in both windows)
      - >50 = accelerating (more recent activity)
      - <50 = decelerating
    """
    recent_cutoff = now - timedelta(days=7)
    prior_cutoff = now - timedelta(days=30)

    recent_weight = 0.0
    prior_weight = 0.0

    for sig in signals:
        created = sig.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        w = SIGNAL_WEIGHTS.get(sig.signal_type, 1.0)
        if created >= recent_cutoff:
            recent_weight += w
        elif created >= prior_cutoff:
            prior_weight += w

    # Normalize prior period to same 7-day window (it covers ~23 days)
    prior_normalized = prior_weight * (7.0 / 23.0) if prior_weight > 0 else 0

    if recent_weight == 0 and prior_normalized == 0:
        return 50.0  # No data = stable

    # Ratio of recent to total activity
    total = recent_weight + prior_normalized
    if total == 0:
        return 50.0
    ratio = recent_weight / total  # 0.0 to 1.0

    # Map to 0-100 scale: 0.5 ratio = 50 (stable)
    return min(max(ratio * 100, 0), 100)


def _compute_source_diversity(signals: list[Signal]) -> float:
    """Score based on how many distinct signal types and sources a company has.

    More diverse signals = higher confidence. Returns 0-100.
    """
    if not signals:
        return 0.0

    signal_types = set()
    source_categories = set()

    for sig in signals:
        signal_types.add(sig.signal_type)
        # Group into broad source categories
        if sig.signal_type in (SignalType.HN_MENTION, SignalType.HN_TRENDING):
            source_categories.add("hackernews")
        elif sig.signal_type in (SignalType.X_MENTION, SignalType.X_TRENDING):
            source_categories.add("twitter")
        elif sig.signal_type == SignalType.GOOGLE_NEWS:
            source_categories.add("google")
        else:
            source_categories.add("other")

    # More signal types = better (diminishing returns)
    type_score = min(len(signal_types) / 5.0, 1.0) * 60

    # Multiple source categories = much better
    diversity_score = min(len(source_categories) / 3.0, 1.0) * 40

    return min(type_score + diversity_score, 100.0)


def _trending_direction(momentum: float) -> str:
    """Classify momentum into a trending direction label."""
    if momentum >= 65:
        return "up"
    elif momentum <= 35:
        return "down"
    return "stable"


def _build_reasoning(cs: CompanyScore) -> str:
    """Generate a human-readable explanation of the score."""
    parts = []

    parts.append(
        f"Score {cs.overall:.0f}/100 based on {cs.signal_count} signal(s)."
    )

    if cs.signal_strength >= 70:
        parts.append("Strong signals detected (e.g. funding or major launch).")
    elif cs.signal_strength >= 40:
        parts.append("Moderate signal activity.")
    else:
        parts.append("Limited signal activity so far.")

    if cs.trending_direction == "up":
        parts.append("Trending UP — recent activity is accelerating.")
    elif cs.trending_direction == "down":
        parts.append("Activity is slowing down compared to earlier.")

    if cs.source_diversity >= 60:
        parts.append("Signals come from multiple independent sources — higher confidence.")
    elif cs.source_diversity < 30:
        parts.append("Signals from a single source only — needs more confirmation.")

    return " ".join(parts)


class ScoringEngine:
    """Scores companies based on their signals."""

    def __init__(self, session: Session):
        self.session = session

    def score_company(
        self,
        company: Company,
        now: datetime | None = None,
    ) -> CompanyScore:
        """Compute investment-potential score for a single company."""
        now = now or datetime.now(timezone.utc)
        signals = company.signals or []

        # -- Signal strength: sum of weighted signals with recency decay --
        raw_score = 0.0
        summaries: list[SignalSummary] = []

        for sig in signals:
            base_weight = SIGNAL_WEIGHTS.get(sig.signal_type, 1.0)
            recency = _recency_factor(sig.created_at, now)
            effective = base_weight * recency

            summaries.append(
                SignalSummary(
                    signal_type=sig.signal_type,
                    created_at=sig.created_at,
                    weight=base_weight,
                    recency_factor=round(recency, 3),
                    effective_weight=round(effective, 3),
                )
            )
            raw_score += effective

        # Normalize to 0-100 with diminishing returns
        signal_strength = min(raw_score / MAX_RAW_SIGNAL_SCORE * 100, 100)

        # -- Momentum --
        momentum = _compute_momentum(signals, now)

        # -- Source diversity --
        source_diversity = _compute_source_diversity(signals)

        # -- Overall composite --
        overall = (
            DIMENSION_WEIGHTS["signal_strength"] * signal_strength
            + DIMENSION_WEIGHTS["momentum"] * momentum
            + DIMENSION_WEIGHTS["source_diversity"] * source_diversity
        )
        overall = min(max(overall, 0), 100)

        cs = CompanyScore(
            company_id=company.id,
            company_name=company.name,
            overall=round(overall, 1),
            signal_strength=round(signal_strength, 1),
            momentum=round(momentum, 1),
            source_diversity=round(source_diversity, 1),
            signal_count=len(signals),
            signal_summaries=summaries,
            trending_direction=_trending_direction(momentum),
        )
        cs.reasoning = _build_reasoning(cs)
        return cs

    def score_all(
        self,
        now: datetime | None = None,
        persist: bool = True,
    ) -> list[CompanyScore]:
        """Score every company in the database and optionally persist results.

        Returns companies sorted by overall score descending.
        """
        now = now or datetime.now(timezone.utc)

        companies = self.session.query(Company).all()
        results: list[CompanyScore] = []

        for company in companies:
            cs = self.score_company(company, now=now)
            results.append(cs)

            if persist:
                score_record = Score(
                    company_id=company.id,
                    overall=cs.overall,
                    signal_strength=cs.signal_strength,
                    market_potential=None,  # Future: add market analysis
                    momentum=cs.momentum,
                    team_quality=None,  # Future: add team analysis
                    reasoning=cs.reasoning,
                    scored_by="scoring_engine_v1",
                )
                self.session.add(score_record)
                company.status = "scored"

        if persist:
            self.session.commit()

        results.sort(key=lambda c: c.overall, reverse=True)
        return results

    def get_ranked_companies(
        self,
        limit: int = 50,
        now: datetime | None = None,
    ) -> list[CompanyScore]:
        """Score all companies and return the top N."""
        all_scores = self.score_all(now=now, persist=False)
        return all_scores[:limit]
