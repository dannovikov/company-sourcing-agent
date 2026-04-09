"""Configuration for X/Twitter monitoring."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class TwitterConfig:
    """Twitter/X API credentials.

    Set TWITTER_BEARER_TOKEN env var for API access.
    Free tier ($0/mo): 500K tweet reads, recent search (7 days).
    Basic tier ($100/mo): full archive search, more endpoints.
    """

    bearer_token: str | None = field(
        default_factory=lambda: os.environ.get("TWITTER_BEARER_TOKEN")
    )

    @property
    def has_api_access(self) -> bool:
        return self.bearer_token is not None


@dataclass
class MonitorConfig:
    """Top-level configuration for the Twitter/X monitor."""

    twitter: TwitterConfig = field(default_factory=TwitterConfig)

    # Max tweets to fetch per query per run (10-100)
    max_results_per_query: int = 50

    # Keywords to search for (OR'd together in API queries)
    search_keywords: list[str] = field(default_factory=lambda: [
        "startup launched",
        "just launched",
        "launching today",
        "we're building",
        "our startup",
        "seed round",
        "pre-seed",
        "series A",
        "funding announced",
        "raised funding",
        "YC W26",
        "YC S26",
        "YC S25",
        "YC W25",
        "backed by",
        "#buildinpublic",
        "#startup",
        "#launched",
    ])

    # High-signal accounts to monitor directly
    monitored_accounts: list[str] = field(default_factory=lambda: [
        "ycombinator",
        "paulg",
        "garrytan",
        "sama",
        "pmarca",
        "benedictevans",
        "jason",          # Jason Calacanis
        "chrissacca",
        "naval",
        "VCBrags",
        "techcrunch",
        "ProductHunt",
        "andrewchen",
        "hunterwalk",
        "saranormous",    # Sarah Guo
        "gustaf",         # Gustaf Alstromer (YC)
        "daltonc",        # Dalton Caldwell (YC)
        "michaelseibel",
    ])
