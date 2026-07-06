from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path


SCHEMA_VERSION = 5


MIGRATIONS: list[tuple[int, list[str]]] = [
    (
        1,
        [
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                protocol TEXT NOT NULL CHECK (protocol IN ('smb', 'ftp', 'sftp', 'webdav')),
                host TEXT NOT NULL,
                port INTEGER NULL,
                root_path TEXT NOT NULL,
                username_ref TEXT NULL,
                secret_ref TEXT NULL,
                is_active INTEGER NOT NULL CHECK (is_active IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_connected_at TEXT NULL,
                last_scan_at TEXT NULL
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_sources_one_active
            ON sources(is_active)
            WHERE is_active = 1
            """,
            """
            CREATE TABLE IF NOT EXISTS directories (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                name TEXT NOT NULL,
                parent_relative_path TEXT NULL,
                last_scanned_at TEXT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE,
                UNIQUE (source_id, relative_path)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS conversion_profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                is_default INTEGER NOT NULL CHECK (is_default IN (0, 1)),
                video_codec TEXT NOT NULL,
                container TEXT NOT NULL,
                max_dimension INTEGER NULL,
                quality_mode TEXT NULL,
                quality_value TEXT NULL,
                drop_audio INTEGER NOT NULL CHECK (drop_audio IN (0, 1)),
                extra_encoder_args TEXT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS preview_layout_presets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                timeline_flow TEXT NOT NULL CHECK (timeline_flow IN ('row', 'column', 'shuffle')),
                sample_count INTEGER NOT NULL,
                large_tile_count INTEGER NOT NULL,
                identity_diversity_enabled INTEGER NOT NULL CHECK (identity_diversity_enabled IN (0, 1)),
                layout_definition TEXT NOT NULL,
                is_default INTEGER NOT NULL CHECK (is_default IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                directory_id TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                extension TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                modified_at TEXT NULL,
                discovered_at TEXT NOT NULL,
                last_scanned_at TEXT NOT NULL,
                is_video_supported INTEGER NOT NULL CHECK (is_video_supported IN (0, 1)),
                conversion_state TEXT NOT NULL CHECK (conversion_state IN ('not_started', 'in_progress', 'done', 'failed')),
                preview_state TEXT NOT NULL CHECK (preview_state IN ('not_started', 'in_progress', 'done', 'failed')),
                last_conversion_profile_id TEXT NULL,
                last_converted_at TEXT NULL,
                preview_generated_at TEXT NULL,
                has_preview_assets INTEGER NOT NULL CHECK (has_preview_assets IN (0, 1)),
                last_error_code TEXT NULL,
                last_error_message TEXT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE,
                FOREIGN KEY (directory_id) REFERENCES directories(id) ON DELETE CASCADE,
                FOREIGN KEY (last_conversion_profile_id) REFERENCES conversion_profiles(id) ON DELETE SET NULL,
                UNIQUE (source_id, relative_path)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                job_type TEXT NOT NULL CHECK (job_type IN ('scan', 'convert', 'preview', 'tag', 'tune', 'rescan', 'cleanup', 'optimize_db', 'backup', 'restore')),
                scope_type TEXT NOT NULL CHECK (scope_type IN ('source', 'directory', 'file', 'maintenance')),
                scope_ref TEXT NULL,
                status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
                requested_by TEXT NULL,
                parameters TEXT NOT NULL,
                started_at TEXT NULL,
                finished_at TEXT NULL,
                summary_message TEXT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS job_items (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                file_id TEXT NULL,
                item_key TEXT NULL,
                status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled', 'skipped')),
                step_name TEXT NULL,
                message TEXT NULL,
                started_at TEXT NULL,
                finished_at TEXT NULL,
                output_ref TEXT NULL,
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE SET NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_job_items_job_id
            ON job_items(job_id)
            """,
            """
            CREATE TABLE IF NOT EXISTS tag_catalog (
                id TEXT PRIMARY KEY,
                tag_key TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                is_active INTEGER NOT NULL CHECK (is_active IN (0, 1)),
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS file_tags (
                id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL,
                tag_id TEXT NOT NULL,
                confidence REAL NOT NULL,
                provider_name TEXT NULL,
                model_name TEXT NULL,
                assigned_at TEXT NOT NULL,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tag_catalog(id) ON DELETE CASCADE,
                UNIQUE (file_id, tag_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS file_similarity_signatures (
                id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL,
                sample_count INTEGER NOT NULL,
                signature_type TEXT NOT NULL CHECK (signature_type IN ('perceptual_hash', 'embedding', 'mixed')),
                signature_payload TEXT NOT NULL,
                generated_from_job_id TEXT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                FOREIGN KEY (generated_from_job_id) REFERENCES jobs(id) ON DELETE SET NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS app_events (
                id TEXT PRIMARY KEY,
                job_id TEXT NULL,
                file_id TEXT NULL,
                level TEXT NOT NULL CHECK (level IN ('debug', 'info', 'warning', 'error')),
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                payload TEXT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE SET NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_app_events_job_id_created_at
            ON app_events(job_id, created_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_app_events_created_at
            ON app_events(created_at)
            """,
        ],
    ),
    (
        2,
        [
            """
            ALTER TABLE jobs ADD COLUMN cancel_requested_at TEXT NULL
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_job_items_job_id
            ON job_items(job_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_app_events_job_id_created_at
            ON app_events(job_id, created_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_app_events_created_at
            ON app_events(created_at)
            """,
        ],
    ),
    (
        3,
        [
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_conversion_profiles_one_default
            ON conversion_profiles(is_default)
            WHERE is_default = 1
            """,
            """
            INSERT OR IGNORE INTO conversion_profiles (
                id, name, is_default, video_codec, container, max_dimension,
                quality_mode, quality_value, drop_audio, extra_encoder_args,
                created_at, updated_at
            ) VALUES (
                'default-h265-mp4', 'Default H.265 MP4', 1, 'h265', 'mp4', NULL,
                NULL, NULL, 1, NULL, datetime('now'), datetime('now')
            )
            """,
        ],
    ),
    (
        4,
        [
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                section TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS preview_assets (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                asset_kind TEXT NOT NULL CHECK (asset_kind IN ('file', 'directory')),
                file_id TEXT NULL,
                directory_relative_path TEXT NOT NULL,
                image_path TEXT NOT NULL,
                metadata TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_preview_assets_file_unique
            ON preview_assets(file_id)
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_preview_assets_directory_unique
            ON preview_assets(source_id, asset_kind, directory_relative_path)
            WHERE asset_kind = 'directory'
            """,
            """
            ALTER TABLE files ADD COLUMN keyframe_timestamps TEXT NULL
            """,
            """
            ALTER TABLE files ADD COLUMN large_tile_timestamps TEXT NULL
            """,
            """
            ALTER TABLE files ADD COLUMN face_detection_summary TEXT NULL
            """,
            """
            ALTER TABLE files ADD COLUMN body_detection_summary TEXT NULL
            """,
            """
            ALTER TABLE files ADD COLUMN preview_layout_version INTEGER NOT NULL DEFAULT 1
            """,
            """
            ALTER TABLE files ADD COLUMN preview_asset_path TEXT NULL
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_preview_layout_presets_one_default
            ON preview_layout_presets(is_default)
            WHERE is_default = 1
            """,
            """
            INSERT OR IGNORE INTO preview_layout_presets (
                id, name, timeline_flow, sample_count, large_tile_count,
                identity_diversity_enabled, layout_definition, is_default,
                created_at, updated_at
            ) VALUES (
                'default-preview-grid', 'Balanced Grid', 'row', 9, 2,
                1, '{"kind":"auto-grid","version":1,"aspect_ratio_preset":"video"}', 1,
                datetime('now'), datetime('now')
            )
            """,
            """
            INSERT OR IGNORE INTO app_settings (section, payload, created_at, updated_at)
            VALUES (
                'preview',
                '{"sample_count":9,"large_tile_count":2,"timeline_flow":"row","identity_diversity_enabled":true,"aspect_ratio_preset":"video","layout_preset_id":"default-preview-grid"}',
                datetime('now'),
                datetime('now')
            )
            """,
        ],
    ),
    (
        5,
        [
            """
            ALTER TABLE files ADD COLUMN tagging_updated_at TEXT NULL
            """,
            """
            ALTER TABLE files ADD COLUMN tagging_model_info TEXT NULL
            """,
            """
            INSERT OR IGNORE INTO app_settings (section, payload, created_at, updated_at)
            VALUES (
                'tagging',
                '{"provider":"openrouter","sample_count":9,"combine_frames":true,"prefer_batch":true}',
                datetime('now'),
                datetime('now')
            )
            """,
        ],
    ),
]


def connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connection(database_path: Path):
    conn = connect(database_path)
    try:
        yield conn
    finally:
        conn.close()


def initialize_database(database_path: Path) -> None:
    with connection(database_path) as conn:
        _apply_migrations(conn)


def get_schema_version(database_path: Path) -> int:
    with connection(database_path) as conn:
        cursor = conn.execute("SELECT MAX(version) AS version FROM schema_migrations")
        row = cursor.fetchone()
        return int(row["version"] or 0)


def _apply_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    current_version = _current_version(conn)

    for version, statements in MIGRATIONS:
        if version <= current_version:
            continue

        with conn:
            for statement in statements:
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))",
                (version,),
            )


def _current_version(conn: sqlite3.Connection) -> int:
    cursor = conn.execute("SELECT MAX(version) AS version FROM schema_migrations")
    row = cursor.fetchone()
    return int(row["version"] or 0)
