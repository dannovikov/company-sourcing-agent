"""HackerNews monitor — fetches stories, extracts companies, stores signals."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from src.extraction.company_extractor import extract_from_hn_item
from src.hn.client import HNClient, HNItem
from src.models.company import Company
from src.models.signal import Signal

logger = logging.getLogger(__name__)


@dataclass
class MonitorResult:
    """Summary of a single monitoring run."""

    stories_fetched: int = 0
    signals_found: int = 0
    new_signals_stored: int = 0
    new_companies: int = 0
    errors: list[str] = field(default_factory=list)


class HNMonitor:
    """Orchestrates fetching, extraction, and storage for HackerNews."""

    def __init__(self, client: HNClient, session: Session) -> None:
        self.client = client
        self.session = session

    async def run(self, fetch_limit: int = 60) -> MonitorResult:
        """Execute one monitoring cycle.

        Pulls stories from multiple HN feeds, deduplicates, extracts
        company signals, and persists them.
        """
        result = MonitorResult()

        # Gather story IDs from multiple feeds and deduplicate
        all_ids: set[int] = set()
        try:
            for fetch_fn in (
                self.client.get_top_story_ids,
                self.client.get_new_story_ids,
                self.client.get_show_hn_ids,
            ):
                ids = await fetch_fn(limit=fetch_limit)
                all_ids.update(ids)
        except Exception as exc:
            msg = f"Error fetching story IDs: {exc}"
            logger.error(msg)
            result.errors.append(msg)
            return result

        logger.info("Fetching %d unique stories from HN", len(all_ids))
        items = await self.client.get_items(sorted(all_ids))
        result.stories_fetched = len(items)

        # Extract and store
        for item in items:
            extraction = extract_from_hn_item(item)
            if extraction is None:
                continue
            result.signals_found += 1
            self._store_extraction(item, extraction, result)

        self.session.commit()

        logger.info(
            "Monitor run complete: %d stories, %d signals (%d new), %d new companies",
            result.stories_fetched,
            result.signals_found,
            result.new_signals_stored,
            result.new_companies,
        )
        return result

    def _store_extraction(
        self,
        item: HNItem,
        extraction: "ExtractionResult",
        result: MonitorResult,
    ) -> None:
        """Persist a single extraction (company + signal)."""
        from src.extraction.company_extractor import ExtractionResult

        # Extract domain from URL if available
        domain = None
        if item.url:
            try:
                parsed = urlparse(item.url)
                domain = parsed.netloc.removeprefix("www.")
            except Exception:
                pass

        # Check if company already exists (by domain first, then name)
        company = None
        if domain:
            company = (
                self.session.query(Company)
                .filter(Company.domain == domain)
                .first()
            )
        if company is None:
            company = (
                self.session.query(Company)
                .filter(Company.name == extraction.company_name)
                .first()
            )

        if company is None:
            company = Company(
                name=extraction.company_name,
                description=extraction.description,
                domain=domain,
                urls=item.url or None,
                source="hackernews",
            )
            self.session.add(company)
            self.session.flush()  # get the ID
            result.new_companies += 1
        else:
            # Update description if we have a better one
            if extraction.description and not company.description:
                company.description = extraction.description
            # Add URL if not already present
            if item.url and company.urls and item.url not in company.urls:
                company.urls = f"{company.urls}|{item.url}"
            elif item.url and not company.urls:
                company.urls = item.url

        # Check for duplicate signal (same HN item + company)
        hn_url = f"https://news.ycombinator.com/item?id={item.id}"
        existing_signal = (
            self.session.query(Signal)
            .filter(
                Signal.company_id == company.id,
                Signal.source_url == hn_url,
            )
            .first()
        )
        if existing_signal is not None:
            return

        # Serialize raw HN data for debugging
        raw_data = json.dumps(
            {
                "hn_id": item.id,
                "by": item.by,
                "score": item.score,
                "descendants": item.descendants,
                "time": item.time,
            }
        )

        signal = Signal(
            company_id=company.id,
            signal_type=extraction.signal_type,
            title=item.title,
            content=extraction.description,
            source_url=hn_url,
            raw_data=raw_data,
        )
        self.session.add(signal)
        result.new_signals_stored += 1
