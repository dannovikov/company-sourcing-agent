"""Simple CLI entry-point for running the Google News monitor."""

from __future__ import annotations

import asyncio
import logging
import sys

from src.db.session import get_session_factory, init_db
from src.google.client import GoogleNewsClient
from src.google.config import GoogleNewsConfig
from src.google.monitor import GoogleNewsMonitor


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("company_sourcing")

    db_url = None
    max_per_query = 20

    # Simple arg handling
    for arg in sys.argv[1:]:
        if arg.startswith("--db="):
            db_url = arg.split("=", 1)[1]
        elif arg.startswith("--max-per-query="):
            max_per_query = int(arg.split("=", 1)[1])

    logger.info("Starting Google News monitor (max_per_query=%d)", max_per_query)

    # Initialize DB and create a session
    init_db(db_url)
    SessionFactory = get_session_factory(db_url)
    session = SessionFactory()

    config = GoogleNewsConfig(max_results_per_query=max_per_query)
    client = GoogleNewsClient(
        language=config.language,
        country=config.country,
    )

    async def _run() -> None:
        try:
            monitor = GoogleNewsMonitor(
                client=client, session=session, config=config
            )
            result = await monitor.run()
            print(f"\nDone! Fetched {result.articles_fetched} articles.")
            print(f"Signals found: {result.signals_found}")
            print(f"New signals stored: {result.new_signals_stored}")
            print(f"New companies discovered: {result.new_companies}")
            if result.errors:
                print(f"Errors: {len(result.errors)}")
                for err in result.errors:
                    print(f"  - {err}")
        finally:
            await client.close()
            session.close()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
