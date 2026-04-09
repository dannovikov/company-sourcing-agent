"""Extract company names and classify signals from Google News articles.

Works on article *titles* and publisher metadata — no full-text fetch needed.
Uses the same heuristic approach as the HN extractor to stay fast and free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.google.client import NewsArticle
from src.models.signal import SignalType


@dataclass
class GoogleExtractionResult:
    """A company signal extracted from a Google News article."""

    company_name: str
    signal_type: SignalType
    description: str


# ---------------------------------------------------------------------------
# Regex patterns for title-based extraction
# ---------------------------------------------------------------------------

# Funding: "Acme raises $10M Series A", "Acme secures $5M seed"
FUNDING_RE = re.compile(
    r"(.+?)\s+(?:raises?|raised|secures?|secured|closes?|closed|gets?|lands?|nabs?)"
    r"\s+\$[\d.]+\s*[BMKbmk]?\s*(?:in\s+)?(?:seed|series\s+[a-z]|funding|round|investment|"
    r"venture|pre-seed|extension)?",
    re.IGNORECASE,
)

# Alternate funding: "Series A: Acme ..."  or "$10M for Acme"
FUNDING_ALT_RE = re.compile(
    r"(?:series\s+[a-z]|seed|pre-seed|funding)\s*(?:round)?[:\-]\s*(.+?)(?:\s+raises?|\s+gets?|\s*$)",
    re.IGNORECASE,
)

FUNDING_AMOUNT_RE = re.compile(
    r"\$[\d.]+\s*[BMKbmk]?\s+(?:for|to|backs?|into)\s+(.+?)(?:\s*[-,;|]|\s+to\s+|\s*$)",
    re.IGNORECASE,
)

# Product launch: "Acme launches ...", "Introducing Acme"
LAUNCH_RE = re.compile(
    r"(.+?)\s+(?:launch(?:es|ed)?|unveil(?:s|ed)?|releas(?:es|ed|ing)|introduces?|debuts?|rolls?\s+out)",
    re.IGNORECASE,
)

INTRODUCING_RE = re.compile(
    r"(?:introducing|meet|announcing)\s+(.+?)(?:\s*[-:,;|]|\s+a\s+|\s+the\s+|\s*$)",
    re.IGNORECASE,
)

# Stealth: "Acme emerges from stealth", "Acme comes out of stealth"
STEALTH_RE = re.compile(
    r"(.+?)\s+(?:emerges?|comes?\s+out|exits?|steps?\s+out)\s+(?:from|of)\s+stealth",
    re.IGNORECASE,
)

# Partnership: "Acme partners with …", "Acme and Beta announce partnership"
PARTNERSHIP_RE = re.compile(
    r"(.+?)\s+(?:partners?\s+with|announces?\s+partnership|teams?\s+up\s+with|collaborates?\s+with)",
    re.IGNORECASE,
)

# Hiring: "Acme is hiring", "Acme expands team"
HIRING_RE = re.compile(
    r"(.+?)\s+(?:is\s+hiring|hires?|expands?\s+team|adds?\s+\d+\s+(?:employees|engineers))",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Common publisher prefixes/suffixes that leak into titles
_TITLE_NOISE = re.compile(
    r"\s*[-–—|]\s*(?:TechCrunch|Bloomberg|Reuters|Forbes|The Verge|VentureBeat|"
    r"Axios|Business Insider|CNBC|Yahoo Finance|PR Newswire|GlobeNewswire|"
    r"Business Wire|Crunchbase News|The Information|Pitchbook).*$",
    re.IGNORECASE,
)

# Words that almost certainly aren't company names
STOP_WORDS = frozenset(
    {
        "how", "why", "what", "when", "where", "who", "which",
        "the", "a", "an", "is", "are", "was", "were",
        "i", "we", "my", "our", "this", "that", "these", "those",
        "new", "top", "best", "report", "study", "analysis", "opinion",
        "exclusive", "breaking", "update",
    }
)


def _clean_company_name(raw: str) -> str:
    """Best-effort cleanup of a raw company name string."""
    # Strip publisher suffixes
    name = _TITLE_NOISE.sub("", raw)
    # Remove content in parentheses (funding details, etc.)
    name = re.sub(r"\s*\([^)]*\)", "", name)
    # Remove markdown/HTML artefacts
    name = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", name)
    name = re.sub(r"<[^>]+>", "", name)
    # Take text before common separators
    name = re.split(r"\s*[-–—:,;|]\s*", name, maxsplit=1)[0]
    name = name.strip().strip(".,;:!?\"'")

    # If still too long, truncate
    if len(name) > 80:
        parts = name.split()[:5]
        name = " ".join(parts)

    return name


def _looks_like_company(name: str) -> bool:
    """Quick heuristic to reject obvious non-company names."""
    if not name or len(name) < 2:
        return False
    first_word = name.split()[0].lower()
    if first_word in STOP_WORDS:
        return False
    # Reject very long "sentence" names
    if len(name.split()) > 6:
        return False
    return True


def _try_patterns(title: str) -> GoogleExtractionResult | None:
    """Run all regex patterns against a title; return first match or None."""
    # --- Stealth reveals (high value, check first) ---
    m = STEALTH_RE.search(title)
    if m:
        name = _clean_company_name(m.group(1))
        if _looks_like_company(name):
            return GoogleExtractionResult(
                company_name=name,
                signal_type=SignalType.PRODUCT_LAUNCH,
                description=title,
            )

    # --- Funding announcements ---
    m = FUNDING_RE.search(title)
    if m:
        name = _clean_company_name(m.group(1))
        if _looks_like_company(name):
            return GoogleExtractionResult(
                company_name=name,
                signal_type=SignalType.FUNDING,
                description=title,
            )

    m = FUNDING_ALT_RE.search(title)
    if m:
        name = _clean_company_name(m.group(1))
        if _looks_like_company(name):
            return GoogleExtractionResult(
                company_name=name,
                signal_type=SignalType.FUNDING,
                description=title,
            )

    m = FUNDING_AMOUNT_RE.search(title)
    if m:
        name = _clean_company_name(m.group(1))
        if _looks_like_company(name):
            return GoogleExtractionResult(
                company_name=name,
                signal_type=SignalType.FUNDING,
                description=title,
            )

    # --- Product launches ---
    m = LAUNCH_RE.search(title)
    if m:
        name = _clean_company_name(m.group(1))
        if _looks_like_company(name):
            return GoogleExtractionResult(
                company_name=name,
                signal_type=SignalType.PRODUCT_LAUNCH,
                description=title,
            )

    m = INTRODUCING_RE.search(title)
    if m:
        name = _clean_company_name(m.group(1))
        if _looks_like_company(name):
            return GoogleExtractionResult(
                company_name=name,
                signal_type=SignalType.PRODUCT_LAUNCH,
                description=title,
            )

    # --- Partnership ---
    m = PARTNERSHIP_RE.search(title)
    if m:
        name = _clean_company_name(m.group(1))
        if _looks_like_company(name):
            return GoogleExtractionResult(
                company_name=name,
                signal_type=SignalType.PARTNERSHIP,
                description=title,
            )

    # --- Hiring ---
    m = HIRING_RE.search(title)
    if m:
        name = _clean_company_name(m.group(1))
        if _looks_like_company(name):
            return GoogleExtractionResult(
                company_name=name,
                signal_type=SignalType.HIRING_SURGE,
                description=title,
            )

    return None


def extract_from_article(article: NewsArticle) -> GoogleExtractionResult | None:
    """Try to extract a company signal from a Google News article.

    Returns None if no actionable signal is detected.
    """
    title = article.title.strip()
    if not title:
        return None

    # Strip publisher suffix that Google News sometimes appends
    title = _TITLE_NOISE.sub("", title).strip()

    return _try_patterns(title)
