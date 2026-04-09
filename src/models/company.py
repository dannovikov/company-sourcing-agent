from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, IDMixin, TimestampMixin


class Company(Base, IDMixin, TimestampMixin):
    """A company discovered by the sourcing agent.

    Represents a company we've identified as potentially interesting for
    investment. Tracks basic info, discovery metadata, and links to the
    signals and scores associated with it.
    """

    __tablename__ = "companies"

    # Core info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    domain: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, doc="Primary website domain"
    )

    # URLs stored as JSON-compatible text (pipe-separated for simplicity)
    urls: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, doc="Pipe-separated list of relevant URLs"
    )

    # Discovery metadata
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Primary discovery source: hackernews, x_twitter, google, manual",
    )

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(50),
        default="discovered",
        nullable=False,
        doc="Pipeline status: discovered, researching, scored, archived",
    )

    # Relationships
    signals: Mapped[list["Signal"]] = relationship(  # noqa: F821
        "Signal", back_populates="company", cascade="all, delete-orphan"
    )
    scores: Mapped[list["Score"]] = relationship(  # noqa: F821
        "Score", back_populates="company", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_companies_name", "name"),
        Index("ix_companies_source", "source"),
        Index("ix_companies_status", "status"),
        Index("ix_companies_discovered_at", "discovered_at"),
        Index("ix_companies_domain", "domain", unique=True),
    )

    def __repr__(self) -> str:
        return f"<Company(name='{self.name}', source='{self.source}', status='{self.status}')>"
