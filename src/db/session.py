import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models import Base

# Default to SQLite in project root; override with DATABASE_URL env var
# for Postgres or other backends.
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "sourcing.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")


def get_engine(url: str | None = None):
    """Create a SQLAlchemy engine.

    Args:
        url: Database URL. Defaults to DATABASE_URL env var or local SQLite.
    """
    db_url = url or DATABASE_URL

    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(db_url, connect_args=connect_args, echo=False)


def get_session_factory(url: str | None = None):
    """Create a session factory bound to an engine."""
    engine = get_engine(url)
    return sessionmaker(bind=engine)


def init_db(url: str | None = None):
    """Create all tables. Useful for quick setup and testing.

    For production migrations, use Alembic instead.
    """
    engine = get_engine(url)

    # Ensure the data directory exists for SQLite
    db_url = url or DATABASE_URL
    if db_url.startswith("sqlite"):
        db_path = db_url.replace("sqlite:///", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    Base.metadata.create_all(engine)
    return engine
