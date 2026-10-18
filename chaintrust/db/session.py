"""
chaintrust/db/session.py
Engine and session factory, plus `init_db` which creates all tables.

Usage
-----
    from chaintrust.db.session import get_session, init_db

    init_db()                      # creates tables if they don't exist
    with get_session() as session:
        session.add(some_object)
        session.commit()
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from chaintrust.config import get_config
from chaintrust.db.models import Base

logger = logging.getLogger(__name__)

# Module-level singletons (initialised lazily on first call to get_engine())
_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_engine() -> Engine:
    """Return (and lazily create) the SQLAlchemy engine from config."""
    global _engine
    if _engine is None:
        cfg = get_config()
        db_url: str = cfg["database"]["url"]
        echo: bool  = cfg["database"].get("echo", False)

        logger.info("Creating database engine: %s", db_url)
        _engine = create_engine(
            db_url,
            echo=echo,
            # SQLite-specific: enable WAL mode and foreign-key enforcement
            connect_args={"check_same_thread": False} if "sqlite" in db_url else {},
        )

        # Enable SQLite foreign-key pragma on every connection
        if "sqlite" in db_url:
            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, _connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()

    return _engine


def get_session_factory() -> sessionmaker:
    """Return (and lazily create) the session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,   # allow access to attributes after commit
        )
    return _SessionLocal


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Context manager that yields a SQLAlchemy Session.

    Commits on clean exit; rolls back and re-raises on any exception.

    Example
    -------
        with get_session() as s:
            s.add(agent)
    """
    factory = get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """
    Create all tables defined in `Base.metadata` if they do not yet exist.

    Safe to call multiple times (idempotent).  Uses `checkfirst=True` so it
    never drops or truncates existing data.
    """
    engine = get_engine()
    logger.info("Initialising database schema …")
    Base.metadata.create_all(engine, checkfirst=True)
    logger.info("Database ready.")
