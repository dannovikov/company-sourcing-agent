"""Google News monitor — fetches articles, extracts companies, stores signals."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from src.google.client import GoogleNewsClient, NewsArticle
from src.google.config import GoogleNewsConfig
from src.google.parser import GoogleExtractionResult, extract_from_article
from src.models.company import Company
from src.models.signal import Signal, SignalType

logger = logging.getLogger(__name__)

SOURCE_KEY = "google"


@dataclass
class MonitorResult:
    """Summary of a single Google News monitoring run."""

    articles_fetched: int = 0
    signals_found: int = 0
    new_signals_stored: int = 0
    new_companies: int = 0
    errors: list[str] = field(default_factory=list)


class GoogleNewsMonitor:
    """Orchestrates fetching, extraction, and storage for Google News."""

    def __init__(
        self,
        client: GoogleNewsClient,
        session: Session,
        config: GoogleNewsConfig | None = None,
    ) -> None:
        self.client = client
        self.session = session
        self.config = config or GoogleNewsConfig()

    async def run(self) -> MonitorResult:
        """Execute one monitoring cycle.

        Fetches articles across all configured queries, extracts company
        signals, and persists them.
        """
        result = MonitorResult()

        # Fetch articles
        try:
            articles = await self.client.fetch_all(
                self.config.all_queries,
                max_per_query=self.config.max_results_per_query,
            )
        except Exception as exc:
            msg = f"Error fetching Google News articles: {exc}"
            logger.error(msg)
            result.errors.append(msg)
            return result

        result.articles_fetched = len(articles)
        logger.info("Fetched %d unique articles from Google News", len(articles))

        # Extract and store
        for article in articles:
            try:
                extraction = extract_from_article(article)
                if extraction is None:
                    continue
                result.signals_found += 1
                self._store_extraction(article, extraction, result)
            except Exception as exc:
                msg = f"Error processing article '{article.title[:60]}': {exc}"
                logger.warning(msg)
                result.errors.append(msg)

        self.session.commit()

        logger.info(
            "Google News monitor run complete: %d articles, %d signals (%d new), %d new companies",
            result.articles_fetched,
            result.signals_found,
            result.new_signals_stored,
            result.new_companies,
        )
        return result

    def _store_extraction(
        self,
        article: NewsArticle,
        extraction: GoogleExtractionResult,
        result: MonitorResult,
    ) -> None:
        """Persist a single extraction (company + signal)."""
        # Look up existing company by name
        company = (
            self.session.query(Company)
            .filter(Company.name == extraction.company_name)
            .first()
        )

        if company is None:
            company = Company(
                name=extraction.company_name,
                description=extraction.description,
                urls=article.url,
                source=SOURCE_KEY,
            )
            self.session.add(company)
            self.session.flush()
            result.new_companies += 1
        else:
            # Update description if we have a better one
            if extraction.description and not company.description:
                company.description = extraction.description
            # Append URL if not already tracked
            if article.url and company.urls and article.url not in company.urls:
                company.urls = f"{company.urls}|{article.url}"
            elif article.url and not company.urls:
                company.urls = article.url

        # Check for duplicate signal (same source URL + company)
        existing_signal = (
            self.session.query(Signal)
            .filter(
                Signal.company_id == company.id,
                Signal.source_url == article.url,
            )
            .first()
        )
        if existing_signal is not None:
            return

        # Serialize raw article data for debugging
        raw_data = json.dumps(
            {
                "title": article.title,
                "url": article.url,
                "source": article.source,
                "published_at": (
                    article.published_at.isoformat()
                    if article.published_at
                    else None
                ),
                "query": article.query,
            }
        )

        signal = Signal(
            company_id=company.id,
            signal_type=extraction.signal_type,
            title=article.title,
            content=extraction.description,
            source_url=article.url,
            raw_data=raw_data,
        )
        self.session.add(signal)
        result.new_signals_stored += 1
