"""SQLite engine, schema versioning, and default-settings seeding.

The migration statements themselves live in `app/migrations.py`; this module
applies the pending ones and tracks the applied version in `schema_meta`, a
single-row table.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Engine, MetaData, Table, Column, Integer, String, event, text, create_engine

from app.config import DATABASE_PATH
from app.migrations import MIGRATIONS

metadata = MetaData()

schema_meta = Table(
    "schema_meta",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("version", Integer, nullable=False),
    Column("updated_at", String, nullable=False),
)

SCHEMA_VERSION = max(MIGRATIONS)

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        # Stage 3's job worker runs on its own background thread and shares
        # this engine with request-handling threads; check_same_thread=False
        # plus WAL allow that concurrent access without "database is locked"
        # errors under SQLite's default rollback-journal mode.
        _engine = create_engine(
            f"sqlite:///{DATABASE_PATH}",
            future=True,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

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

        if current_version < 5 <= SCHEMA_VERSION:
            from app.preview_layouts import seed_builtin_presets
            from app.preview_settings import seed_default_settings

            seed_builtin_presets(conn)
            seed_default_settings(conn)

        if current_version < 6 <= SCHEMA_VERSION:
            from app.tagging_settings import seed_default_settings as seed_default_tagging_settings

            seed_default_tagging_settings(conn)

        if current_version < 7 <= SCHEMA_VERSION:
            from app.playback_settings import seed_default_settings as seed_default_playback_settings

            seed_default_playback_settings(conn)

        if current_version < 8 <= SCHEMA_VERSION:
            from app.backup_settings import seed_default_settings as seed_default_backup_settings

            seed_default_backup_settings(conn)

        if current_version < 9 <= SCHEMA_VERSION:
            from app.interface_settings import seed_default_settings as seed_default_interface_settings

            seed_default_interface_settings(conn)

        if current_version < 16 <= SCHEMA_VERSION:
            from app.performance_settings import seed_default_settings as seed_default_performance_settings

            seed_default_performance_settings(conn)

        if current_version < 28 <= SCHEMA_VERSION:
            from app.model_pricing import seed_default_prices

            seed_default_prices(conn)

        if current_version < 32 <= SCHEMA_VERSION:
            from app.conversion_settings import seed_default_settings as seed_default_conversion_settings

            seed_default_conversion_settings(conn)

        if current_version < 34 <= SCHEMA_VERSION:
            from app.backend_health_settings import seed_default_settings as seed_default_backend_health_settings

            seed_default_backend_health_settings(conn)

        if current_version < 43 <= SCHEMA_VERSION:
            from app.resource_monitor_settings import seed_default_settings as seed_default_resource_monitor_settings

            seed_default_resource_monitor_settings(conn)

        if current_version < 45 <= SCHEMA_VERSION:
            from app.log_rotation_settings import seed_default_settings as seed_default_log_rotation_settings

            seed_default_log_rotation_settings(conn)

    return SCHEMA_VERSION


def get_schema_version() -> int | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT version FROM schema_meta WHERE id = 1")).fetchone()
        return row[0] if row else None
