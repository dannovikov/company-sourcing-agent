from typing import Optional

from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, IDMixin, TimestampMixin


class Score(Base, IDMixin, TimestampMixin):
    """An investment-potential score for a company.

    Scores are computed from signals and research. We keep a history of
    scores so we can track how a company's perceived potential changes
    over time. Each score captures a point-in-time assessment.
    """

    __tablename__ = "scores"

    # Link to company
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )

    # Overall score (0-100)
    overall: Mapped[float] = mapped_column(
        Float, nullable=False, doc="Overall investment potential score (0-100)"
    )

    # Dimension scores (0-100 each, all optional)
    signal_strength: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, doc="How strong/numerous the signals are (0-100)"
    )
    market_potential: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, doc="Estimated market opportunity (0-100)"
    )
    momentum: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, doc="Growth velocity / buzz trend (0-100)"
    )
    team_quality: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, doc="Team background and strength (0-100)"
    )

    # Explanation
    reasoning: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, doc="Human-readable explanation of the score"
    )
    scored_by: Mapped[str] = mapped_column(
        String(100),
        default="agent",
        nullable=False,
        doc="Who/what generated this score: agent, manual, model_v1, etc.",
    )

    # Relationship
    company: Mapped["Company"] = relationship(  # noqa: F821
        "Company", back_populates="scores"
    )

    __table_args__ = (
        Index("ix_scores_company_id", "company_id"),
        Index("ix_scores_overall", "overall"),
        Index("ix_scores_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Score(overall={self.overall}, scored_by='{self.scored_by}')>"
