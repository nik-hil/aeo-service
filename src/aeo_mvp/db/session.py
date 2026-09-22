"""SQLAlchemy engine and session factory."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from aeo_mvp.config import get_settings
from aeo_mvp.db.models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine(database_url: str | None = None) -> Engine:
    global _engine, _SessionLocal
    url = database_url or get_settings().database_url
    if _engine is None or (database_url and str(_engine.url) != url):
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, future=True, connect_args=connect_args)
        if url.startswith("sqlite"):

            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    get_engine(database_url)
    assert _SessionLocal is not None
    return _SessionLocal


def _sqlite_add_column_if_missing(engine: Engine, table: str, column: str, coltype: str) -> None:
    """Best-effort ALTER TABLE ADD COLUMN for SQLite schema drift."""
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
        existing = {r[1] for r in rows}
        if column in existing:
            return
        conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        conn.commit()


def migrate_schema(database_url: str | None = None) -> None:
    """Add nullable/default columns introduced after initial create_all (SQLite-friendly)."""
    engine = get_engine(database_url)
    for table, column, coltype in (
        ("experiment_configs", "experiment_kind", "VARCHAR(64) DEFAULT 'llm_mention'"),
        ("experiment_configs", "retrieval_enabled", "INTEGER DEFAULT 0"),
        ("experiment_configs", "discovered_queries_json", "TEXT"),
        ("visibility_observations", "model_id", "VARCHAR(128)"),
        ("visibility_observations", "retrieval_enabled", "INTEGER DEFAULT 0"),
        ("visibility_observations", "experiment_kind", "VARCHAR(64) DEFAULT 'llm_mention'"),
        ("visibility_observations", "search_queries_json", "TEXT"),
        ("visibility_observations", "source_urls_json", "TEXT"),
        ("visibility_observations", "target_domain_appeared", "INTEGER"),
        ("visibility_observations", "target_domain_cited", "INTEGER"),
        ("recommendations", "details_json", "TEXT"),
        ("pages", "source_url", "TEXT"),
        ("pages", "content_representation", "VARCHAR(32)"),
        ("pages", "primary_status_code", "INTEGER"),
        ("pages", "primary_fetch_status", "VARCHAR(32)"),
        ("pages", "alternate_fetch_status", "VARCHAR(32)"),
        ("pages", "source_markdown", "TEXT"),
    ):
        try:
            _sqlite_add_column_if_missing(engine, table, column, coltype)
        except Exception:  # noqa: BLE001
            # Table may not exist yet; create_all handles that.
            pass
    _sqlite_ensure_vis_obs_unique_index(engine)


def _sqlite_ensure_vis_obs_unique_index(engine: Engine) -> None:
    """Idempotent unique index for observation reclaim safety (P1-11)."""
    if not str(engine.url).startswith("sqlite"):
        return
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_vis_obs_cfg_prompt_run "
                "ON visibility_observations (experiment_config_id, prompt_id, run_index)"
            )
            conn.commit()
    except Exception:  # noqa: BLE001
        pass


def init_db(database_url: str | None = None) -> None:
    engine = get_engine(database_url)
    Base.metadata.create_all(bind=engine)
    migrate_schema(database_url)


@contextmanager
def get_session(database_url: str | None = None) -> Generator[Session, None, None]:
    factory = get_session_factory(database_url)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    """Test helper: drop cached engine/session factory."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
