"""SQLite initialization and schema versioning.

Schema changes are expressed as an ordered list of migrations. Each migration
is applied at most once; the applied version is tracked in `schema_meta`, a
single-row table. Later stages append new entries to `MIGRATIONS` instead of
editing already-applied ones.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Engine, MetaData, Table, Column, Integer, String, text, create_engine

from app.config import DATABASE_PATH

metadata = MetaData()

schema_meta = Table(
    "schema_meta",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("version", Integer, nullable=False),
    Column("updated_at", String, nullable=False),
)

# Migration 1 only establishes the schema_meta baseline; no entity tables
# exist yet (those are introduced by their owning roadmap stage).
MIGRATIONS: dict[int, list[str]] = {
    1: [],
}

SCHEMA_VERSION = max(MIGRATIONS)

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(f"sqlite:///{DATABASE_PATH}", future=True)
    return _engine


def init_db() -> int:
    """Create the database file if needed and apply pending migrations.

    Returns the schema version the database is at after this call.
    """
    engine = get_engine()
    with engine.begin() as conn:
        metadata.create_all(conn, tables=[schema_meta])

        row = conn.execute(text("SELECT version FROM schema_meta WHERE id = 1")).fetchone()
        current_version = row[0] if row else 0

        for version in range(current_version + 1, SCHEMA_VERSION + 1):
            for statement in MIGRATIONS[version]:
                conn.execute(text(statement))

        if current_version != SCHEMA_VERSION:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                text(
                    """
                    INSERT INTO schema_meta (id, version, updated_at)
                    VALUES (1, :version, :updated_at)
                    ON CONFLICT(id) DO UPDATE SET version = :version, updated_at = :updated_at
                    """
                ),
                {"version": SCHEMA_VERSION, "updated_at": now},
            )

    return SCHEMA_VERSION


def get_schema_version() -> int | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT version FROM schema_meta WHERE id = 1")).fetchone()
        return row[0] if row else None
