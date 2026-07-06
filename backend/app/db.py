"""SQLite initialization and schema versioning.

Schema changes are expressed as an ordered list of migrations. Each migration
is applied at most once; the applied version is tracked in `schema_meta`, a
single-row table. Later stages append new entries to `MIGRATIONS` instead of
editing already-applied ones.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Engine, MetaData, Table, Column, Integer, String, event, text, create_engine

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
    # Stage 2: source configuration, directory tree, and file records
    # (Data Model §1-3). Later stages append columns/tables for jobs,
    # conversion profiles, tags, etc. instead of editing these.
    2: [
        """
        CREATE TABLE sources (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            protocol TEXT NOT NULL,
            host TEXT,
            port INTEGER,
            root_path TEXT NOT NULL,
            username_ref TEXT,
            secret_ref TEXT,
            is_active INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_connected_at TEXT,
            last_scan_at TEXT
        )
        """,
        """
        CREATE TABLE directories (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES sources(id),
            relative_path TEXT NOT NULL,
            name TEXT NOT NULL,
            parent_relative_path TEXT,
            has_folder_preview INTEGER NOT NULL DEFAULT 0,
            folder_preview_generated_at TEXT,
            last_scanned_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (source_id, relative_path)
        )
        """,
        "CREATE INDEX idx_directories_source_parent ON directories (source_id, parent_relative_path)",
        """
        CREATE TABLE files (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES sources(id),
            directory_id TEXT NOT NULL REFERENCES directories(id),
            relative_path TEXT NOT NULL,
            file_name TEXT NOT NULL,
            extension TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            modified_at TEXT,
            discovered_at TEXT NOT NULL,
            last_scanned_at TEXT NOT NULL,
            is_video_supported INTEGER NOT NULL,
            converted_at TEXT,
            last_conversion_profile_id TEXT,
            has_preview_asset INTEGER NOT NULL DEFAULT 0,
            preview_generated_at TEXT,
            tagged_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (source_id, relative_path)
        )
        """,
        "CREATE INDEX idx_files_directory ON files (directory_id)",
        "CREATE INDEX idx_files_source ON files (source_id)",
    ],
    # Stage 3: job queue, per-item progress, and the log/event stream
    # (Data Model §6-7, §11; Job Model). A single background worker thread
    # now shares this database with request-handling threads, hence the
    # check_same_thread/WAL setup below in get_engine().
    3: [
        """
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            job_type TEXT NOT NULL,
            scope_type TEXT NOT NULL,
            scope_ref TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            parameters TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            summary_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX idx_jobs_status ON jobs (status)",
        "CREATE INDEX idx_jobs_created_at ON jobs (created_at)",
        """
        CREATE TABLE job_items (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id),
            file_id TEXT REFERENCES files(id),
            item_key TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            step_name TEXT,
            message TEXT,
            started_at TEXT,
            finished_at TEXT,
            output_ref TEXT
        )
        """,
        "CREATE INDEX idx_job_items_job ON job_items (job_id)",
        """
        CREATE TABLE app_events (
            id TEXT PRIMARY KEY,
            job_id TEXT REFERENCES jobs(id),
            file_id TEXT REFERENCES files(id),
            level TEXT NOT NULL,
            event_type TEXT NOT NULL,
            message TEXT NOT NULL,
            payload TEXT,
            created_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX idx_app_events_job ON app_events (job_id)",
        "CREATE INDEX idx_app_events_created_at ON app_events (created_at)",
    ],
    # Stage 4: conversion profiles (Data Model §4, Specification §7). The
    # `convert` job type and its safe-replace/test-mode/variant logic reuse
    # the jobs/job_items infrastructure from migration 3 unchanged.
    4: [
        """
        CREATE TABLE conversion_profiles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            is_default INTEGER NOT NULL DEFAULT 0,
            video_codec TEXT NOT NULL DEFAULT 'h265',
            container TEXT NOT NULL DEFAULT 'mp4',
            max_dimension INTEGER,
            crf INTEGER NOT NULL DEFAULT 26,
            drop_audio INTEGER NOT NULL DEFAULT 1,
            extra_encoder_args TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    ],
}

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

    return SCHEMA_VERSION


def get_schema_version() -> int | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT version FROM schema_meta WHERE id = 1")).fetchone()
        return row[0] if row else None
