"""SQLAlchemy engine and session helpers."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import DATA_DIR, get_settings
from backend.models import Base

_engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def _sqlite_engine(url: str) -> Engine:
    """Create a SQLite engine that allows FastAPI's thread pool to share it."""

    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


def init_engine(url: str | None = None) -> Engine:
    """Create tables and the global session factory."""

    global _engine, SessionLocal
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "voices").mkdir(parents=True, exist_ok=True)
    if _engine is not None and url is None:
        return _engine
    if _engine is not None:
        _engine.dispose()
    db_url = url or get_settings().database_url
    _engine = _sqlite_engine(db_url) if db_url.startswith("sqlite") else create_engine(db_url)
    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(_engine)
    _migrate(_engine)
    return _engine


def _migrate(engine: Engine) -> None:
    """Add columns that create_all will not attach to an existing SQLite file."""

    if not str(engine.url).startswith("sqlite"):
        return
    inspector = inspect(engine)
    statements: list[str] = []
    if "outputs" in inspector.get_table_names():
        cols = {column["name"] for column in inspector.get_columns("outputs")}
        if "hidden" not in cols:
            statements.append("ALTER TABLE outputs ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0")
        if "voice_path" not in cols:
            statements.append("ALTER TABLE outputs ADD COLUMN voice_path VARCHAR(255) DEFAULT ''")
        if "prev_hash" not in cols:
            statements.append("ALTER TABLE outputs ADD COLUMN prev_hash VARCHAR(64)")
        if "hash" not in cols:
            statements.append("ALTER TABLE outputs ADD COLUMN hash VARCHAR(64)")
    if "users" in inspector.get_table_names():
        user_cols = {column["name"] for column in inspector.get_columns("users")}
        if "alias" not in user_cols:
            statements.append("ALTER TABLE users ADD COLUMN alias VARCHAR(24)")
        statements.append("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_alias ON users(alias)")
    if "memory_state" in inspector.get_table_names():
        mem_cols = {column["name"] for column in inspector.get_columns("memory_state")}
        if "focus" not in mem_cols:
            statements.append("ALTER TABLE memory_state ADD COLUMN focus INTEGER NOT NULL DEFAULT 5")
        if "restlessness" not in mem_cols:
            statements.append("ALTER TABLE memory_state ADD COLUMN restlessness INTEGER NOT NULL DEFAULT 4")
        if "unresolved_thought" not in mem_cols:
            statements.append("ALTER TABLE memory_state ADD COLUMN unresolved_thought TEXT NOT NULL DEFAULT ''")
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def get_session() -> Generator[Session, None, None]:
    """Yield a request-scoped session. Commits on success."""

    if SessionLocal is None:
        init_engine()
    assert SessionLocal is not None
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    """Drop the process engine. Used by tests to isolate databases."""

    global _engine, SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    SessionLocal = None


def session_factory() -> sessionmaker[Session]:
    """Return the bound sessionmaker, initialising the engine if needed."""

    if SessionLocal is None:
        init_engine()
    assert SessionLocal is not None
    return SessionLocal
