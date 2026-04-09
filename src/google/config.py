"""Configuration for Google News monitoring searches."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GoogleNewsConfig:
    """Configurable search queries and settings for Google News monitoring."""

    # Queries targeting startup funding announcements
    funding_queries: list[str] = field(
        default_factory=lambda: [
            "startup raises seed round",
            "startup series A funding",
            "startup series B funding",
            "startup seed funding announced",
            "venture capital investment startup",
            "YC startup funding",
        ]
    )

    # Queries targeting product launches
    launch_queries: list[str] = field(
        default_factory=lambda: [
            "startup launches product",
            "startup product launch",
            "tech startup launch",
            "new AI startup launch",
            "ProductHunt launch",
        ]
    )

    # Queries targeting stealth startups
    stealth_queries: list[str] = field(
        default_factory=lambda: [
            "stealth startup emerges",
            "startup out of stealth",
            "stealth mode startup reveals",
        ]
    )

    # Queries for general company announcements
    announcement_queries: list[str] = field(
        default_factory=lambda: [
            "startup announces partnership",
            "tech startup hiring",
            "startup expansion announcement",
        ]
    )

    # Google News language and region
    language: str = "en"
    country: str = "US"

    # Maximum articles to fetch per query
    max_results_per_query: int = 20

    @property
    def all_queries(self) -> list[str]:
        """Return all configured search queries."""
        return (
            self.funding_queries
            + self.launch_queries
            + self.stealth_queries
            + self.announcement_queries
        )
