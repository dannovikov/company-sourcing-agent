"""Extract company mentions and classify signals from HN posts.

Strategy:
  1. Pattern-match on well-known HN title formats (Show HN, Launch HN, etc.)
  2. Look for funding/launch keywords in title and body text
  3. Extract company name from the title using heuristics
  4. Classify the signal type
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.hn.client import HNItem
from src.models.signal import SignalType


@dataclass
class ExtractionResult:
    """Result of extracting a company signal from an HN item."""

    company_name: str
    signal_type: SignalType
    description: str


# Patterns ordered by specificity
SHOW_HN_RE = re.compile(r"^Show HN:\s*(.+)", re.IGNORECASE)
LAUNCH_HN_RE = re.compile(r"^Launch HN:\s*(.+)", re.IGNORECASE)

# Funding patterns: "Company raises $X", "Company announces Series A", etc.
FUNDING_RE = re.compile(
    r"(.+?)\s+(?:raises?|raised|secures?|secured|closes?|closed|announces?|announced)"
    r"\s+(?:\$[\d.]+[BMK]?\s+)?(?:(?:seed|series\s+[a-z]|funding|round|investment))",
    re.IGNORECASE,
)

# "Company launches X", "We built X", "Introducing X"
LAUNCH_KEYWORDS_RE = re.compile(
    r"(.+?)\s+(?:launch(?:es|ed)?|releas(?:es|ed|ing)|introducing|we\s+built|just\s+shipped)",
    re.IGNORECASE,
)

# YC batch pattern: "Company (YC S24)"
YC_BATCH_RE = re.compile(r"(.+?)\s*\(YC\s+[A-Z]\d{2}\)", re.IGNORECASE)

# Common title fluff to strip when extracting company names
FLUFF_RE = re.compile(
    r"\s*[-–—:|]\s*(an?\s+|the\s+)?(open[- ]source\s+)?.*$",
    re.IGNORECASE,
)

# Words that are almost certainly not company names
STOP_WORDS = frozenset(
    {
        "how",
        "why",
        "what",
        "when",
        "where",
        "who",
        "ask",
        "tell",
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "i",
        "we",
        "my",
        "our",
    }
)


def _clean_company_name(raw: str) -> str:
    """Best-effort cleanup of a raw company name string."""
    # Remove markdown links
    name = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", raw)
    # Remove HTML tags
    name = re.sub(r"<[^>]+>", "", name)
    # Take text before common separators that introduce a description
    name = FLUFF_RE.sub("", name)
    name = name.strip().strip(".,;:!?\"'")

    # If what's left is very long, take the first segment before a dash/colon
    if len(name) > 60:
        parts = re.split(r"\s*[-–—:]\s*", name, maxsplit=1)
        name = parts[0].strip()

    return name


def _looks_like_company(name: str) -> bool:
    """Quick heuristic to filter out obvious non-company extractions."""
    if not name or len(name) < 2:
        return False
    first_word = name.split()[0].lower()
    if first_word in STOP_WORDS:
        return False
    # Reject if it's all lowercase and reads like a sentence
    if len(name.split()) > 6:
        return False
    return True


def extract_from_hn_item(item: HNItem) -> ExtractionResult | None:
    """Try to extract a company signal from an HN item.

    Returns None if no company signal is detected.
    """
    title = item.title.strip()
    if not title:
        return None

    # --- Show HN ---
    m = SHOW_HN_RE.match(title)
    if m:
        raw = m.group(1)
        name = _clean_company_name(raw)
        if _looks_like_company(name):
            return ExtractionResult(
                company_name=name,
                signal_type=SignalType.HN_MENTION,
                description=raw.strip(),
            )

    # --- Launch HN ---
    m = LAUNCH_HN_RE.match(title)
    if m:
        raw = m.group(1)
        name = _clean_company_name(raw)
        if _looks_like_company(name):
            return ExtractionResult(
                company_name=name,
                signal_type=SignalType.PRODUCT_LAUNCH,
                description=raw.strip(),
            )

    # --- YC batch mentions ---
    m = YC_BATCH_RE.match(title)
    if m:
        name = _clean_company_name(m.group(1))
        if _looks_like_company(name):
            return ExtractionResult(
                company_name=name,
                signal_type=SignalType.FUNDING,
                description=title,
            )

    # --- Funding announcements ---
    m = FUNDING_RE.match(title)
    if m:
        name = _clean_company_name(m.group(1))
        if _looks_like_company(name):
            return ExtractionResult(
                company_name=name,
                signal_type=SignalType.FUNDING,
                description=title,
            )

    # --- Product launches / "we built" ---
    m = LAUNCH_KEYWORDS_RE.match(title)
    if m:
        name = _clean_company_name(m.group(1))
        if _looks_like_company(name):
            return ExtractionResult(
                company_name=name,
                signal_type=SignalType.PRODUCT_LAUNCH,
                description=title,
            )

    return None
