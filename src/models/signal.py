import enum
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, IDMixin, TimestampMixin


class SignalType(str, enum.Enum):
    """Types of signals that can indicate a company is worth watching."""

    FUNDING = "funding"
    PRODUCT_LAUNCH = "product_launch"
    HN_MENTION = "hn_mention"
    HN_TRENDING = "hn_trending"
    X_MENTION = "x_mention"
    X_TRENDING = "x_trending"
    GOOGLE_NEWS = "google_news"
    HIRING_SURGE = "hiring_surge"
    PARTNERSHIP = "partnership"
    AWARD = "award"
    OTHER = "other"


class Signal(Base, IDMixin, TimestampMixin):
    """A signal that drew attention to a company.

    Signals are individual data points — a funding announcement, an HN post,
    a trending tweet — that indicate a company might be worth investigating.
    Multiple signals can be linked to the same company.
    """

    __tablename__ = "signals"

    # Link to company
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )

    # Signal details
    signal_type: Mapped[SignalType] = mapped_column(
        Enum(SignalType), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, doc="Raw content or summary of the signal"
    )
    source_url: Mapped[Optional[str]] = mapped_column(
        String(2048), nullable=True, doc="URL where this signal was found"
    )

    # Metadata
    raw_data: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, doc="JSON blob of raw source data for debugging"
    )

    # Relationship
    company: Mapped["Company"] = relationship(  # noqa: F821
        "Company", back_populates="signals"
    )

    __table_args__ = (
        Index("ix_signals_company_id", "company_id"),
        Index("ix_signals_signal_type", "signal_type"),
        Index("ix_signals_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Signal(type='{self.signal_type.value}', title='{self.title[:50]}')>"
