"""Tracks crawl progress per source to enable idempotent monitoring runs."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, IDMixin, TimestampMixin


class CrawlState(Base, IDMixin, TimestampMixin):
    """Tracks the last-crawled position for each monitoring source.

    This enables idempotent runs — if the monitor runs twice, it picks up
    where it left off instead of re-processing old data.
    """

    __tablename__ = "crawl_states"

    source: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True,
        doc="Source identifier, e.g. 'twitter_api', 'twitter_scrape'",
    )
    last_external_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
        doc="Last processed external ID (e.g. tweet ID) for pagination",
    )
    last_crawled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    metadata_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        doc="JSON blob for source-specific state",
    )

    def __repr__(self) -> str:
        return f"<CrawlState(source='{self.source}', last_id='{self.last_external_id}')>"
