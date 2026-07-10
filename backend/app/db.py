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
    # Stage 5: preview layout presets and the global preview settings
    # singleton (Data Model §5, Specification §9-10). Seeding the built-in
    # preset gallery and the default settings row happens in application code
    # (`app/preview_layouts.py`/`app/preview_settings.py`, called from
    # `init_db()` below) rather than here, so timestamps stay dynamic and
    # seeding stays idempotent across restarts, matching the DDL-only style
    # of earlier migrations.
    5: [
        """
        CREATE TABLE preview_layout_presets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            grid_rows INTEGER NOT NULL,
            grid_cols INTEGER NOT NULL,
            timeline_flow TEXT NOT NULL DEFAULT 'row',
            identity_diversity_enabled INTEGER NOT NULL DEFAULT 1,
            layout_definition TEXT NOT NULL,
            is_builtin INTEGER NOT NULL DEFAULT 0,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE preview_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            aspect_ratio TEXT NOT NULL DEFAULT 'standard',
            aspect_ratio_custom_width INTEGER,
            aspect_ratio_custom_height INTEGER,
            folder_preview_frame_count INTEGER NOT NULL DEFAULT 4,
            updated_at TEXT NOT NULL
        )
        """,
    ],
    # Stage 6: tag vocabulary, assigned tags, the tagging settings singleton,
    # and per-provider (non-secret) configuration (Data Model §8-9,
    # Specification §12, §18). API keys never land in this database — they
    # live in `backend/secrets.env` (see `app/secrets_store.py`); only
    # `provider_configs` rows (enabled flag, model choices) are stored here,
    # following the same singleton-table convention as `preview_settings`.
    # Seeding the tagging settings row and the four fixed provider rows
    # happens in application code (`app/tagging_settings.py`,
    # `app/provider_configs.py`, called from `init_db()` below) for the same
    # reason as Stage 5's seeding: dynamic timestamps, idempotent restarts.
    # DDL uses IF NOT EXISTS/INDEX (unlike earlier migrations): a dev-time
    # incident showed a crash between table creation and the schema_meta
    # version bump leaves tables present but the version stuck at the prior
    # number, so a retry re-runs this migration's statements against
    # already-created tables — this must not raise.
    6: [
        """
        CREATE TABLE IF NOT EXISTS tag_catalog (
            id TEXT PRIMARY KEY,
            tag_key TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_tag_catalog_key ON tag_catalog (tag_key)",
        """
        CREATE TABLE IF NOT EXISTS file_tags (
            id TEXT PRIMARY KEY,
            file_id TEXT NOT NULL REFERENCES files(id),
            tag_id TEXT NOT NULL REFERENCES tag_catalog(id),
            score INTEGER NOT NULL,
            provider_name TEXT,
            model_name TEXT,
            assigned_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_file_tags_file ON file_tags (file_id)",
        "CREATE INDEX IF NOT EXISTS idx_file_tags_tag ON file_tags (tag_id)",
        """
        CREATE TABLE IF NOT EXISTS tagging_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            sample_frame_count INTEGER NOT NULL DEFAULT 9,
            combine_into_collage INTEGER NOT NULL DEFAULT 1,
            top_tag_count INTEGER NOT NULL DEFAULT 10,
            default_provider TEXT,
            default_vision_model TEXT,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS provider_configs (
            provider_name TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0,
            vision_model TEXT,
            text_model TEXT,
            batch_enabled INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """,
    ],
    # Stage 7: SMB source support (host/port/username_ref/secret_ref on
    # `sources` already exist since migration 2) plus the playback settings
    # singleton (Specification §11.5, Settings §4), following the same
    # singleton-table convention as `preview_settings`/`tagging_settings`.
    7: [
        """
        CREATE TABLE IF NOT EXISTS playback_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            mode TEXT NOT NULL DEFAULT 'stream',
            updated_at TEXT NOT NULL
        )
        """,
    ],
    # Stage 8: the backup-retention setting (Specification §19, Settings §7).
    # Backup packages themselves live on the source disk (`.video-archive/
    # backups/`, see `app/backup.py`), not in this database; this singleton
    # only holds how many of them to keep. Same convention as
    # preview_settings/tagging_settings/playback_settings.
    8: [
        """
        CREATE TABLE IF NOT EXISTS backup_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            retention_count INTEGER NOT NULL DEFAULT 5,
            updated_at TEXT NOT NULL
        )
        """,
    ],
    # Stage 9: the interface settings singleton (Settings §9, Design System
    # §2) -- backend persistence for language + theme preset, closing the
    # pre-Stage-9 known gap where language lived only in the browser's
    # localStorage. Same singleton convention as preview/tagging/playback/
    # backup_settings.
    9: [
        """
        CREATE TABLE IF NOT EXISTS interface_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            language TEXT NOT NULL DEFAULT 'en',
            theme_preset TEXT NOT NULL DEFAULT 'strict',
            updated_at TEXT NOT NULL
        )
        """,
    ],
    # Stage 9: cached near-duplicate signatures (Data Model §10, Specification
    # §13) -- optional and secondary; a missing/failed signature never blocks
    # preview or conversion. Populated best-effort by the `preview` job
    # (Specification §13 "preferred first integration point").
    10: [
        """
        CREATE TABLE IF NOT EXISTS file_similarity_signatures (
            id TEXT PRIMARY KEY,
            file_id TEXT NOT NULL UNIQUE REFERENCES files(id),
            sample_count INTEGER NOT NULL,
            signature_type TEXT NOT NULL,
            signature_payload TEXT NOT NULL,
            generated_from_job_id TEXT REFERENCES jobs(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_file_similarity_file ON file_similarity_signatures (file_id)",
    ],
    # Post-V1: configurable animated-GIF preview size/quality (user request —
    # GIFs were previously a fixed 480px/full-256-color render, too large for
    # the small grid/list-view thumbnail slot they're actually shown in).
    # ALTER TABLE ... ADD COLUMN with a literal DEFAULT backfills existing
    # rows (just the one `preview_settings` singleton row) automatically, so
    # no extra seeding step is needed here.
    11: [
        "ALTER TABLE preview_settings ADD COLUMN gif_max_width INTEGER NOT NULL DEFAULT 640",
        "ALTER TABLE preview_settings ADD COLUMN gif_colors INTEGER NOT NULL DEFAULT 64",
    ],
    # Post-V1: provider settings become a user-managed, priority-ordered list
    # of entries (`app/provider_entries.py`) instead of four fixed rows keyed
    # by provider name -- multiple entries per provider type are allowed (e.g.
    # two Gemini keys), and the tag job now falls back through enabled
    # entries in `sort_order` instead of using one frozen provider per job.
    # `sort_order` follows the same "priority" convention as
    # `tag_catalog.sort_order`. No seed step: the table starts empty, the
    # user adds their own entries. Schema intentionally leaves room for a
    # later `ALTER TABLE ... ADD COLUMN extra_params_json` if per-model
    # parameters are ever needed -- nothing here assumes a closed field set.
    # `default_provider`/`default_vision_model` on `tagging_settings` are
    # dropped since "the active provider" is no longer a single manual
    # choice -- it's whichever enabled entry the fallback chain picks.
    12: [
        "DROP TABLE IF EXISTS provider_configs",
        """
        CREATE TABLE provider_entries (
            id TEXT PRIMARY KEY,
            provider_type TEXT NOT NULL,
            display_name TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            vision_model TEXT,
            text_model TEXT,
            batch_enabled INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_provider_entries_sort_order ON provider_entries (sort_order)",
        "ALTER TABLE tagging_settings DROP COLUMN default_provider",
        "ALTER TABLE tagging_settings DROP COLUMN default_vision_model",
    ],
    # Post-V1: `jobs.total_items` (user request) -- the bulk job runners
    # (preview/convert/tag directory scope, convert variant sweep, rescan)
    # already compute the candidate count before their per-item loop; storing
    # it lets the Jobs modal show a done/total progress bar and estimate time
    # remaining while a job is running, instead of only a final summary line.
    13: [
        "ALTER TABLE jobs ADD COLUMN total_items INTEGER",
    ],
    # Post-V1: animated-preview source mode (user request) -- the animated
    # GIF preview (file-companion `.preview.gif` and `folder-preview.gif`)
    # previously always cycled through single still frames with a fixed
    # 450ms hold and a hard cut between them. This splits that setting out
    # from the (unrelated) static collage settings and adds a "clip" source
    # mode, where each position instead contributes a short burst of frames
    # sampled from a brief video segment, plus an optional crossfade
    # transition between positions. `animated_segment_seconds` replaces the
    # old fixed 450ms constant as the configurable "how long each position is
    # shown" duration (still frame hold time in "frame" mode, clip length in
    # "clip" mode) -- 0.45 keeps prior behavior as the default.
    14: [
        "ALTER TABLE preview_settings ADD COLUMN animated_source_mode TEXT NOT NULL DEFAULT 'frame'",
        "ALTER TABLE preview_settings ADD COLUMN animated_segment_seconds REAL NOT NULL DEFAULT 0.45",
        "ALTER TABLE preview_settings ADD COLUMN animated_transition TEXT NOT NULL DEFAULT 'cut'",
    ],
    # Post-V1: video duration on library cards (user request). Duration is
    # never probed during scanning (extension-only, cheap); it is instead
    # captured for free from the ffprobe call that preview generation and
    # conversion already perform, and persisted here so the grid can show it
    # without an ffprobe round-trip per card. Stays NULL until the file has
    # been previewed or converted at least once.
    15: [
        "ALTER TABLE files ADD COLUMN duration_seconds REAL",
    ],
    # Post-V1: performance settings singleton (user request) -- how many
    # files/variants the `convert` and `preview` jobs process concurrently
    # (see `app/performance_settings.py`). Same singleton convention as
    # preview/playback/backup/interface_settings.
    16: [
        """
        CREATE TABLE IF NOT EXISTS performance_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            parallel_workers INTEGER NOT NULL DEFAULT 4,
            updated_at TEXT NOT NULL
        )
        """,
    ],
    # Post-V1: animated preview saturation (user request) -- lets the user
    # desaturate library-grid GIF/thumbnail previews (0 = grayscale, 100 =
    # original colors) for a more uniform-looking grid without losing the
    # image content itself. Applied client-side as a CSS filter, so this is
    # just the persisted preference; no preview regeneration is triggered.
    # Same singleton convention as the rest of interface_settings; ALTER
    # TABLE backfills the existing row via its literal DEFAULT.
    17: [
        "ALTER TABLE interface_settings ADD COLUMN preview_saturation INTEGER NOT NULL DEFAULT 100",
    ],
    # Post-V1: two-profile preview stylization (user request, supersedes
    # migration 17's single `preview_saturation` field after the same
    # session's follow-up request) -- the "hide previews" top-bar toggle
    # (`PreviewVisibilityContext.tsx`) no longer swaps the thumbnail for a
    # folder/film icon; it now switches which of these two named style
    # profiles is applied to the (always-visible) preview image via CSS
    # `filter`. Profile A defaults to a no-op (matches original colors);
    # profile B defaults to heavily blurred + desaturated, standing in for
    # the old "hidden" state, but every field is user-editable in Settings.
    18: [
        "ALTER TABLE interface_settings DROP COLUMN preview_saturation",
        "ALTER TABLE interface_settings ADD COLUMN profile_a_saturation INTEGER NOT NULL DEFAULT 100",
        "ALTER TABLE interface_settings ADD COLUMN profile_a_blur INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE interface_settings ADD COLUMN profile_a_brightness INTEGER NOT NULL DEFAULT 100",
        "ALTER TABLE interface_settings ADD COLUMN profile_a_contrast INTEGER NOT NULL DEFAULT 100",
        "ALTER TABLE interface_settings ADD COLUMN profile_a_sepia INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE interface_settings ADD COLUMN profile_a_hue_rotate INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE interface_settings ADD COLUMN profile_b_saturation INTEGER NOT NULL DEFAULT 20",
        "ALTER TABLE interface_settings ADD COLUMN profile_b_blur INTEGER NOT NULL DEFAULT 16",
        "ALTER TABLE interface_settings ADD COLUMN profile_b_brightness INTEGER NOT NULL DEFAULT 100",
        "ALTER TABLE interface_settings ADD COLUMN profile_b_contrast INTEGER NOT NULL DEFAULT 100",
        "ALTER TABLE interface_settings ADD COLUMN profile_b_sepia INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE interface_settings ADD COLUMN profile_b_hue_rotate INTEGER NOT NULL DEFAULT 0",
    ],
    # Post-V1: multiple saved sources (user request) -- `sources` already
    # supported many rows, but only the destructive `PUT /source` handler
    # ever wrote to it, which always left exactly one row. Now that sources
    # can be listed/switched/forgotten independently, nothing else enforces
    # "at most one active row" -- this partial unique index is a cheap
    # belt-and-suspenders guard so a bug in the switch flow can't silently
    # leave two active rows (which `GET /source`'s `LIMIT 1` would then pick
    # between nondeterministically).
    19: [
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_sources_single_active ON sources(is_active) WHERE is_active = 1",
    ],
    # Favorite folders (user request): a short list of directories the user
    # pins for quick "move this video here" access. Mirrors the
    # has_folder_preview/folder_preview_generated_at pair already on this
    # table (migration 2).
    20: [
        "ALTER TABLE directories ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE directories ADD COLUMN favorited_at TEXT",
    ],
    # Durable provider-side tagging batches.  The provider has already
    # accepted the request at this point, so its identity and the immutable
    # tag vocabulary must survive an application restart while we poll it.
    21: [
        """
        CREATE TABLE external_batch_runs (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id),
            provider_entry_id TEXT NOT NULL REFERENCES provider_entries(id),
            provider_name TEXT NOT NULL,
            model_name TEXT,
            external_id TEXT NOT NULL,
            tag_ids_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'submitted',
            item_count INTEGER NOT NULL,
            submitted_at TEXT NOT NULL,
            last_polled_at TEXT,
            completed_at TEXT,
            error_message TEXT
        )
        """,
        "CREATE INDEX idx_external_batch_runs_status ON external_batch_runs(status, submitted_at)",
        """
        CREATE TABLE external_batch_items (
            id TEXT PRIMARY KEY,
            batch_run_id TEXT NOT NULL REFERENCES external_batch_runs(id),
            file_id TEXT NOT NULL REFERENCES files(id),
            job_item_id TEXT NOT NULL REFERENCES job_items(id),
            UNIQUE(batch_run_id, file_id)
        )
        """,
        """
        CREATE TABLE tag_runs (
            id TEXT PRIMARY KEY,
            file_id TEXT NOT NULL REFERENCES files(id),
            provider_name TEXT NOT NULL,
            model_name TEXT,
            execution_mode TEXT NOT NULL,
            response_payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX idx_tag_runs_file_created ON tag_runs(file_id, created_at DESC)",
        """
        CREATE TABLE model_usage (
            provider_name TEXT NOT NULL,
            model_name TEXT NOT NULL,
            request_count INTEGER NOT NULL DEFAULT 0,
            file_count INTEGER NOT NULL DEFAULT 0,
            batch_count INTEGER NOT NULL DEFAULT 0,
            last_used_at TEXT NOT NULL,
            PRIMARY KEY(provider_name, model_name)
        )
        """,
    ],
    # Zero-confidence assignments are not tags.  Remove any rows written by
    # older workers before the central writer starts filtering new results.
    22: [
        "DELETE FROM file_tags WHERE score <= 0",
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

    return SCHEMA_VERSION


def get_schema_version() -> int | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT version FROM schema_meta WHERE id = 1")).fetchone()
        return row[0] if row else None
