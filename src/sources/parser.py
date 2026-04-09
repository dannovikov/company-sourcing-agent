"""Signal parser: extracts company mentions from tweet text.

Uses heuristic pattern matching to identify company names, funding events,
product launches, and other investable signals. Intentionally rule-based
(no LLM dependency) for speed and cost. A downstream analysis module can
use an LLM for deeper scoring.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from src.models.signal import SignalType
from src.sources.twitter_api import FetchedTweet

logger = logging.getLogger(__name__)


@dataclass
class ParsedMention:
    """A company mention extracted from a tweet, before DB persistence."""

    company_name: str
    context: str
    signal_type: SignalType
    company_url: str | None = None


# ── Category detection patterns ──────────────────────────────────────────

SIGNAL_PATTERNS: list[tuple[SignalType, re.Pattern]] = [
    (SignalType.FUNDING, re.compile(
        r"(?:raised|raises|raising|secured|closed|announced?)\s+"
        r"(?:\$[\d.,]+[MBKmk]?|(?:seed|pre-seed|series\s+[A-Z])\s+(?:round|funding))",
        re.IGNORECASE,
    )),
    (SignalType.FUNDING, re.compile(
        r"(?:seed|pre-seed|series\s+[A-Z])\s+(?:round|funding|investment)",
        re.IGNORECASE,
    )),
    (SignalType.FUNDING, re.compile(
        r"\$[\d.,]+\s*[MBK]\s+(?:round|funding|raised|investment|valuation)",
        re.IGNORECASE,
    )),
    (SignalType.PRODUCT_LAUNCH, re.compile(
        r"(?:just\s+)?launch(?:ed|ing)\s+(?:today|on|our|the|a|my)",
        re.IGNORECASE,
    )),
    (SignalType.PRODUCT_LAUNCH, re.compile(
        r"(?:we(?:'re| are)\s+)?launch(?:ed|ing)|now\s+(?:live|available)|open\s+beta",
        re.IGNORECASE,
    )),
    (SignalType.X_MENTION, re.compile(
        r"YC\s*[WSws]\d{2,4}|Y\s*Combinator\s+(?:batch|company|startup)",
        re.IGNORECASE,
    )),
    (SignalType.PRODUCT_LAUNCH, re.compile(
        r"(?:shipped|releasing|released|announcing|introduced)\s+(?:our|the|a|new|v\d)",
        re.IGNORECASE,
    )),
    (SignalType.HIRING_SURGE, re.compile(
        r"(?:we(?:'re| are)\s+)?hiring|join\s+(?:our|the)\s+team|open\s+roles?",
        re.IGNORECASE,
    )),
    (SignalType.OTHER, re.compile(
        r"(?:acquired|acquires|acquisition|acquiring)\s+",
        re.IGNORECASE,
    )),
]

# ── Company name extraction patterns ────────────────────────────────────

# Pattern: "@company just launched..."
AT_MENTION_PATTERN = re.compile(r"@(\w{2,30})")

# Pattern: "Company Name raised $X" — capitalized words before action verbs
COMPANY_ACTION_PATTERN = re.compile(
    r"(?:^|\.\s+|\n)([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){0,3})\s+"
    r"(?:raised|raises|launched|launches|announces|announced|shipped|closes|closed|secured|introduces)",
    re.MULTILINE,
)

# Pattern: "congrats to Company", "check out Company"
CONGRATS_PATTERN = re.compile(
    r"(?:congrats?\s+(?:to\s+)?|check\s+out\s+|excited\s+(?:about|for)\s+|"
    r"backed\s+|invested\s+in\s+|announcing\s+)"
    r"@?([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){0,2})",
    re.IGNORECASE,
)

# Common words that look like company names but aren't
STOPWORDS = {
    "the", "this", "that", "these", "those", "they", "their", "them",
    "just", "now", "new", "our", "your", "been", "being", "have", "has",
    "will", "would", "could", "should", "from", "into", "with", "about",
    "very", "really", "great", "good", "best", "most", "also", "more",
    "some", "any", "all", "each", "every", "both", "few", "many",
    "today", "tomorrow", "here", "there", "not", "yes", "and", "but",
    "super", "excited", "amazing", "incredible", "awesome", "happy",
    "proud", "huge", "big", "team", "company", "startup", "product",
    "congrats", "congratulations", "check", "looking", "building",
    "launching", "launched", "raised", "raising", "funding", "funded",
    "series", "seed", "round", "million", "billion", "backed",
    "investors", "investor", "portfolio", "batch",
    # Social media terms
    "thread", "breaking", "update", "icymi", "fyi",
    # Common false positives
    "silicon", "valley", "san", "francisco", "new", "york",
    "monday", "tuesday", "wednesday", "thursday", "friday",
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
}

# URL pattern to extract company URLs from tweet text
URL_PATTERN = re.compile(r"https?://(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,})[^\s]*")


def extract_mentions(tweet: FetchedTweet) -> list[ParsedMention]:
    """Extract company mentions from a fetched tweet.

    Uses multiple heuristics in parallel and deduplicates results.

    Args:
        tweet: The fetched tweet to parse.

    Returns:
        List of ParsedMention objects found in the tweet.
    """
    text = tweet.content
    signal_type = _detect_signal_type(text)
    candidates: dict[str, str] = {}  # name -> context

    # Strategy 1: @ mentions (high signal for company accounts)
    for match in AT_MENTION_PATTERN.finditer(text):
        name = match.group(1)
        if not _is_stopword(name) and len(name) > 2:
            context = _extract_context(text, match.start(), match.end())
            candidates[name] = context

    # Strategy 2: Capitalized names before action verbs
    for match in COMPANY_ACTION_PATTERN.finditer(text):
        name = match.group(1).strip()
        if not _is_stopword(name):
            context = _extract_context(text, match.start(), match.end())
            candidates[name] = context

    # Strategy 3: Names after signal phrases like "congrats to", "check out"
    for match in CONGRATS_PATTERN.finditer(text):
        name = match.group(1).strip().lstrip("@")
        if not _is_stopword(name) and len(name) > 2:
            context = _extract_context(text, match.start(), match.end())
            candidates[name] = context

    # Extract any URLs that might be company websites
    urls: dict[str, str] = {}
    skip_domains = {
        "twitter.com", "x.com", "t.co", "youtube.com", "youtu.be",
        "facebook.com", "instagram.com", "linkedin.com", "reddit.com",
        "github.com", "bit.ly", "tinyurl.com", "medium.com",
        "techcrunch.com", "bloomberg.com", "reuters.com",
    }
    for match in URL_PATTERN.finditer(text):
        domain = match.group(1).lower()
        if domain not in skip_domains:
            company_from_domain = domain.split(".")[0]
            urls[company_from_domain] = match.group(0)

    # Build final mentions, deduplicated
    mentions: list[ParsedMention] = []
    seen_names: set[str] = set()

    for name, context in candidates.items():
        normalized = name.lower().strip()
        if normalized in seen_names:
            continue
        seen_names.add(normalized)

        company_url = urls.get(normalized)
        mentions.append(
            ParsedMention(
                company_name=name,
                context=context,
                signal_type=signal_type,
                company_url=company_url,
            )
        )

    if mentions:
        logger.debug(
            "Extracted %d mentions from tweet %s: %s",
            len(mentions),
            tweet.tweet_id,
            [m.company_name for m in mentions],
        )

    return mentions


def _detect_signal_type(text: str) -> SignalType:
    """Detect the signal type from tweet text."""
    for signal_type, pattern in SIGNAL_PATTERNS:
        if pattern.search(text):
            return signal_type
    return SignalType.X_MENTION


def _is_stopword(name: str) -> bool:
    """Check if a candidate company name is actually a common word."""
    words = name.lower().split()
    return all(w in STOPWORDS for w in words)


def _extract_context(text: str, start: int, end: int, window: int = 80) -> str:
    """Extract surrounding text for context."""
    ctx_start = max(0, start - window)
    ctx_end = min(len(text), end + window)
    context = text[ctx_start:ctx_end].strip()
    if ctx_start > 0:
        context = "..." + context
    if ctx_end < len(text):
        context = context + "..."
    return context
