"""Simple CLI entry-point for running the HN monitor."""

from __future__ import annotations

import asyncio
import logging
import sys

from src.db.session import get_session_factory, init_db
from src.hn.client import HNClient
from src.hn.monitor import HNMonitor


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("company_sourcing")

    fetch_limit = 60
    db_url = None

    # Simple arg handling
    for arg in sys.argv[1:]:
        if arg.startswith("--db="):
            db_url = arg.split("=", 1)[1]
        elif arg.startswith("--limit="):
            fetch_limit = int(arg.split("=", 1)[1])

    logger.info("Starting HN monitor (limit=%d)", fetch_limit)

    # Initialize DB and create a session
    init_db(db_url)
    SessionFactory = get_session_factory(db_url)
    session = SessionFactory()

    client = HNClient()

    async def _run() -> None:
        try:
            monitor = HNMonitor(client=client, session=session)
            result = await monitor.run(fetch_limit=fetch_limit)
            print(f"\nDone! Fetched {result.stories_fetched} stories.")
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
