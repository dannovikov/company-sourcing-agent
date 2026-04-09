"""CLI entry point for the company dashboard.

Usage:
    python -m src.dashboard.cli [--host HOST] [--port PORT]
"""

from __future__ import annotations

import argparse

import uvicorn

from src.db.session import init_db


def main():
    parser = argparse.ArgumentParser(description="Company Sourcing Dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    # Ensure tables exist
    init_db()

    print(f"Starting dashboard at http://{args.host}:{args.port}")
    uvicorn.run(
        "src.dashboard.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
