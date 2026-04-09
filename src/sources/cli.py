"""CLI entry point for the X/Twitter monitor.

Usage:
    python -m src.sources.cli monitor     # Run a full monitoring cycle
    python -m src.sources.cli config      # Show current configuration
"""

from __future__ import annotations

import argparse
import logging
import sys

from src.db.session import get_session_factory, init_db
from src.sources.config import MonitorConfig
from src.sources.monitor import TwitterMonitor


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="twitter-monitor",
        description="X/Twitter monitor for company sourcing signals.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    subparsers.add_parser("monitor", help="Run a Twitter/X monitoring cycle")
    subparsers.add_parser("config", help="Show current configuration")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "monitor":
        _cmd_monitor()
    elif args.command == "config":
        _cmd_config()


def _cmd_monitor() -> None:
    """Run a full monitoring cycle."""
    init_db()
    SessionFactory = get_session_factory()
    session = SessionFactory()
    config = MonitorConfig()
    monitor = TwitterMonitor(session=session, config=config)

    try:
        result = monitor.run()
        print(f"\n{'='*60}")
        print("Twitter/X Monitoring Cycle Complete")
        print(f"{'='*60}")
        print(f"  Tweets fetched:     {result.tweets_fetched}")
        print(f"  Signals created:    {result.signals_created}")
        print(f"  Companies created:  {result.companies_created}")
        print(f"  Duplicates skipped: {result.duplicates_skipped}")
        print(f"{'='*60}\n")
    finally:
        monitor.close()
        session.close()


def _cmd_config() -> None:
    """Show current configuration."""
    config = MonitorConfig()
    print(f"\n{'='*60}")
    print("Twitter/X Monitor Configuration")
    print(f"{'='*60}")
    api_status = "Configured" if config.twitter.has_api_access else "Not configured (using scraper fallback)"
    print(f"  Twitter API:     {api_status}")
    print(f"  Max results/q:   {config.max_results_per_query}")
    print(f"\n  Search keywords ({len(config.search_keywords)}):")
    for kw in config.search_keywords:
        print(f"    - {kw}")
    print(f"\n  Monitored accounts ({len(config.monitored_accounts)}):")
    for acc in config.monitored_accounts:
        print(f"    - @{acc}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
