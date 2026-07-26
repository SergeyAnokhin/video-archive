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
    # Post-V1: AI provider usage log (user request -- "want to see usage
    # statistics for model requests, which models were used across the whole
    # app"). One row per tagging request (sync or batch) to a provider,
    # written by `app/providers/registry.py` right after the call returns or
    # raises, so a failed call is logged too. `tokens_in`/`tokens_out` are
    # `NULL` when the provider's response doesn't expose usage metadata (FAL
    # has no fixed response schema -- see `app/providers/fal.py` -- so its
    # rows are always call-only); `estimated_cost_usd` is then derived from a
    # hand-maintained per-model rate table (`app/provider_usage.py`) and is
    # `NULL` for an unrecognized model string. `item_count` is 1 for a
    # per-file request, or the number of files bundled into a batch request.
    21: [
        """
        CREATE TABLE IF NOT EXISTS provider_usage_log (
            id TEXT PRIMARY KEY,
            provider_type TEXT NOT NULL,
            model_name TEXT,
            request_kind TEXT NOT NULL,
            success INTEGER NOT NULL,
            item_count INTEGER NOT NULL DEFAULT 1,
            tokens_in INTEGER,
            tokens_out INTEGER,
            estimated_cost_usd REAL,
            error_message TEXT,
            job_id TEXT REFERENCES jobs(id),
            created_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_provider_usage_log_created_at ON provider_usage_log (created_at)",
        "CREATE INDEX IF NOT EXISTS idx_provider_usage_log_provider_model ON provider_usage_log (provider_type, model_name)",
    ],
    # Post-V1: persisted batch-tagging submissions (user request -- "the
    # batch task should survive a service restart, polling every 30s until
    # done"). Before this, `submit_batch()` submitted to the provider and
    # then blocked polling in-process for up to 30 minutes with nothing
    # written to the database until it finished -- a restart mid-poll lost
    # all track of the provider-side job. Now the external id and everything
    # needed to resolve it later are persisted the moment the batch is
    # created, so `app/batch_submissions.py`'s startup requeue can pick a
    # stalled one back up. `tag_ids_json`/`items_json` snapshot exactly what
    # was sent (tag id order, file/job-item ids) rather than re-reading the
    # live vocabulary/candidate list, so a resume after the vocabulary or
    # skip-processed set changed still resolves the original request
    # correctly. `top_tag_count` is snapshotted the same way for the same
    # reason `tagging_settings` is a per-job-launch snapshot everywhere else.
    22: [
        """
        CREATE TABLE IF NOT EXISTS batch_submissions (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id),
            provider_entry_id TEXT NOT NULL REFERENCES provider_entries(id),
            provider_type TEXT NOT NULL,
            model_name TEXT,
            external_batch_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'polling',
            tag_ids_json TEXT NOT NULL,
            top_tag_count INTEGER NOT NULL,
            items_json TEXT NOT NULL,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolved_at TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_batch_submissions_status ON batch_submissions (status)",
        "CREATE INDEX IF NOT EXISTS idx_batch_submissions_job ON batch_submissions (job_id)",
    ],
    # Post-V1: scoped library search (user request) -- the top-bar search box
    # groups matches into three sections (tags / file names / directory
    # names), each capped at a user-configurable number of entries. Same
    # interface_settings singleton convention as the preview profiles; ALTER
    # TABLE backfills the existing row via the literal DEFAULT.
    23: [
        "ALTER TABLE interface_settings ADD COLUMN search_tag_limit INTEGER NOT NULL DEFAULT 10",
        "ALTER TABLE interface_settings ADD COLUMN search_file_limit INTEGER NOT NULL DEFAULT 10",
        "ALTER TABLE interface_settings ADD COLUMN search_dir_limit INTEGER NOT NULL DEFAULT 10",
    ],
    # Post-V1: configurable tagging image resolution (user request -- wants
    # control over what gets sent to the AI vision provider). The pixel size
    # was previously a hardcoded constant (`CELL_SIZE_PX` in `app/tagging.py`);
    # this makes it a per-image cap: the collage cell side length, or each
    # frame's longest side in per-frame mode. Default 360 matches the prior
    # hardcoded constant, so existing behavior is unchanged until edited.
    24: [
        "ALTER TABLE tagging_settings ADD COLUMN image_resolution INTEGER NOT NULL DEFAULT 360",
    ],
    # Post-V1: standalone images become first-class library items (user
    # request). Parallel to `is_video_supported` rather than replacing it --
    # conversion/preview/tune job-scoping queries stay video-only unchanged;
    # listing/status/tag-scope queries widen to
    # `(is_video_supported = 1 OR is_image_supported = 1)` instead.
    25: [
        "ALTER TABLE files ADD COLUMN is_image_supported INTEGER NOT NULL DEFAULT 0",
    ],
    # Post-V1 (user request -- Tag Lab surfaced that tuning-parameter tags
    # like "640px"/"H265" were leaking into the AI-tagging vocabulary and the
    # Settings tag list): `tag_catalog` rows auto-created as a side effect of
    # `tags.assign_tuning_parameter_tags()` no longer count as vocabulary --
    # excluded from `list_tags()`/`list_used_tags()` (Settings management,
    # autocomplete, and the vocabulary sent to every AI-tagging prompt), but
    # still fully usable as ordinary `file_tags` rows. Backfills existing
    # databases: a tag whose *only* file_tags rows are `provider_name =
    # 'tuning'` is flipped to non-vocabulary; a tag used for anything else
    # (including alongside tuning) is left alone, since it's a real tag that
    # happens to share a name with a swept parameter.
    26: [
        "ALTER TABLE tag_catalog ADD COLUMN is_ai_vocabulary INTEGER NOT NULL DEFAULT 1",
        """
        UPDATE tag_catalog
        SET is_ai_vocabulary = 0
        WHERE id IN (SELECT DISTINCT tag_id FROM file_tags WHERE provider_name = 'tuning')
          AND id NOT IN (
              SELECT DISTINCT tag_id FROM file_tags
              WHERE provider_name IS NULL OR provider_name != 'tuning'
          )
        """,
    ],
    # Post-V1 (user request): a third tag pool alongside the AI vocabulary
    # (`is_ai_vocabulary`, migration 26) and ordinary ad-hoc tags typed
    # directly onto a file -- a short, centrally-managed list of purely
    # subjective tags that a vision model could never determine, attached to
    # a file through their own dedicated picker (not the free-text add
    # field) in the info panel and the playback screen. New rows default to
    # 0; nothing existing needs backfilling into this pool.
    27: [
        "ALTER TABLE tag_catalog ADD COLUMN is_user_defined INTEGER NOT NULL DEFAULT 0",
    ],
    # Post-V1 (user request -- editable, sourced per-model $/1M-token pricing
    # for Tag Lab's cost estimate). Replaces the hand-maintained Python dict
    # `provider_usage._COST_PER_MILLION_TOKENS_USD` with a DB-backed table
    # keyed the same way `provider_usage_log` already is
    # (`provider_type`, `model_name`) -- shared across every provider entry
    # that points at the same model, editable from Settings, and refreshable
    # from OpenRouter's public pricing API for that provider type. `source`
    # distinguishes a manually-entered/curated price (`'manual'`) from one
    # fetched live (`'openrouter_api'`). See `app/model_pricing.py`.
    28: [
        """
        CREATE TABLE IF NOT EXISTS model_pricing (
            provider_type TEXT NOT NULL,
            model_name TEXT NOT NULL,
            input_per_million REAL,
            output_per_million REAL,
            source TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (provider_type, model_name)
        )
        """,
    ],
    # Post-V1 (user request -- per-model rating: like/dislike on each
    # suggested tag right in Tag Lab's result list, plus a separate KPI on
    # how often a run's suggestion was applied unchanged/edited/never
    # applied). `tag_lab_runs` snapshots what a run suggested so later
    # feedback/apply events can be compared against it without re-deriving
    # from `file_tags` (which may have since changed again). `not_applied` is
    # deliberately not a stored column -- it's `tag_lab_runs` rows with no
    # matching `tag_lab_applies` row, so an abandoned session (closed tab,
    # no explicit event) is still counted correctly. See
    # `app/tag_lab_feedback.py`.
    29: [
        """
        CREATE TABLE IF NOT EXISTS tag_lab_runs (
            id TEXT PRIMARY KEY,
            provider_type TEXT NOT NULL,
            model_name TEXT,
            file_id TEXT NOT NULL,
            suggested_tags_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_tag_lab_runs_provider_model ON tag_lab_runs (provider_type, model_name)",
        """
        CREATE TABLE IF NOT EXISTS tag_lab_tag_feedback (
            run_id TEXT NOT NULL REFERENCES tag_lab_runs(id),
            tag_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            vote INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (run_id, tag_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS tag_lab_applies (
            run_id TEXT PRIMARY KEY REFERENCES tag_lab_runs(id),
            unchanged INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
    ],
    # Post-V1 (user request -- Tag Lab calls a provider directly and
    # synchronously, unlike the background `tag` job, so a hung request
    # blocks the UI with no cancel button): a configurable per-request
    # timeout for that direct call, alongside tagging's other non-vocabulary
    # settings. Default 30s.
    30: [
        "ALTER TABLE tagging_settings ADD COLUMN request_timeout_seconds INTEGER NOT NULL DEFAULT 30",
    ],
    # User request -- a per-tag background color, shown identically for that
    # tag everywhere it's rendered (library cards, file info panel, Tag Lab,
    # tag pickers). Nullable: a tag with no explicit color falls back to the
    # same deterministic hash-based color the UI already computed client-side
    # before this column existed (`app/tags.py::_fallback_color`), so nothing
    # changes visually for existing tags until a user actually picks one.
    31: [
        "ALTER TABLE tag_catalog ADD COLUMN color TEXT",
    ],
    # Post-V1: minimum size-reduction threshold for production/test-mode
    # conversion replace (user report) -- a converted output must shrink the
    # source by at least this percentage to actually replace it, otherwise
    # the attempt is logged and skipped, keeping the original untouched (see
    # `app/conversion_settings.py`, `app/jobs/convert.py`). A tuning-sweep
    # variant is exempt (deliberate comparison output, never replaces the
    # source). Same singleton convention as performance/playback/backup/
    # interface_settings.
    32: [
        """
        CREATE TABLE IF NOT EXISTS conversion_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            min_size_reduction_percent INTEGER NOT NULL DEFAULT 20,
            updated_at TEXT NOT NULL
        )
        """,
    ],
    # Post-V1: live within-file encode progress (user request -- "some files
    # take a very long time to convert, I want to see something is actually
    # happening"). Previously the Jobs modal could only show "file N of M";
    # this lets a single running `job_items` row carry a 0-100 percentage
    # parsed from ffmpeg's own `-progress` output (`app/conversion.py`,
    # `app/jobs/convert.py`), polled by the same REST refresh the Jobs modal
    # already uses (`frontend/src/context/JobsContext.tsx`) -- no new
    # transport needed. NULL until a file's encode actually starts reporting.
    33: [
        "ALTER TABLE job_items ADD COLUMN progress_pct REAL",
    ],
    # Post-V1: backend-health-indicator timeout settings (chat request
    # 2026-07-19 follow-up, user-configurable) -- how long the top-bar status
    # dot waits for `/api/health` before turning amber ("slow"), and how much
    # longer it then waits on retry before giving up and turning red
    # ("offline"). Same singleton convention as performance_settings.
    34: [
        """
        CREATE TABLE IF NOT EXISTS backend_health_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            slow_timeout_seconds INTEGER NOT NULL DEFAULT 5,
            offline_timeout_seconds INTEGER NOT NULL DEFAULT 10,
            updated_at TEXT NOT NULL
        )
        """,
    ],
    # User report: a large/slow encode hit the previously-hardcoded 3600s
    # (1h) limit in `app/conversion.py::run_ffmpeg` and was killed outright
    # ("ffmpeg timed out after 3600s"). Made configurable, same singleton
    # convention as `min_size_reduction_percent` in the same table
    # (`app/conversion_settings.py`). Existing rows default to the previous
    # hardcoded value so behavior is unchanged until a user raises it.
    35: [
        "ALTER TABLE conversion_settings ADD COLUMN ffmpeg_timeout_seconds INTEGER NOT NULL DEFAULT 3600",
    ],
    # Optional Intel hardware-accelerated encoding (QSV on Windows, VAAPI
    # groundwork for the k3s/Linux deployment) -- per-profile, not a global
    # singleton, since different saved profiles may reasonably want different
    # encode backends on the same host (see app/hardware_accel.py). Existing
    # rows default to 'off' so behavior is unchanged until a user opts in.
    36: [
        "ALTER TABLE conversion_profiles ADD COLUMN hardware_accel TEXT NOT NULL DEFAULT 'off'",
    ],
    # Post-V1 (user request): cache the rest of the technical-data panel's
    # ffprobe fields (resolution/codec/container/bitrate), not just
    # `duration_seconds` (migration 15) -- same "captured for free" pattern,
    # extended to preview generation and conversion, plus a read-through
    # cache in the media-info endpoint itself for files neither has touched
    # yet. `media_probed_at` is the cache sentinel: NULL means "never
    # probed"; non-NULL with width/height still NULL means "probed
    # successfully, file has no video stream" (e.g. audio-only) -- without
    # this distinction such a file would look like a permanent cache miss.
    37: [
        "ALTER TABLE files ADD COLUMN width INTEGER",
        "ALTER TABLE files ADD COLUMN height INTEGER",
        "ALTER TABLE files ADD COLUMN video_codec TEXT",
        "ALTER TABLE files ADD COLUMN format_name TEXT",
        "ALTER TABLE files ADD COLUMN bit_rate INTEGER",
        "ALTER TABLE files ADD COLUMN media_probed_at TEXT",
    ],
    # `reap_orphaned_jobs()` marks a job `failed` when the backend restarted
    # while it was still `running` (chat request: surface this distinctly
    # from an ordinary failure like an ffmpeg error, instead of leaving the
    # frontend to string-match `summary_message`). Existing rows default to
    # 0/false, matching their real history.
    38: [
        "ALTER TABLE jobs ADD COLUMN interrupted INTEGER NOT NULL DEFAULT 0",
    ],
    # Opt-in, Windows-only fast path for an SMB source: read files straight
    # off a `\\host\share\...` UNC path (when the OS already has -- or can
    # establish -- its own authenticated SMB session to that host) instead of
    # `local_copy()`'s default full-file download to a temp dir. Off by
    # default; existing rows default to 0/false, matching today's behavior.
    39: [
        "ALTER TABLE sources ADD COLUMN direct_access_enabled INTEGER NOT NULL DEFAULT 0",
    ],
    # Global counterpart to migration 39's per-source read-side setting: opt-in
    # write-side fast path for conversion against a direct-access SMB source
    # (commit/rename/remove via a raw UNC filesystem call instead of
    # smbclient upload). Off by default -- conversion's write side keeps
    # today's copy-based behavior until explicitly enabled and tested.
    40: [
        "ALTER TABLE conversion_settings ADD COLUMN direct_write_enabled INTEGER NOT NULL DEFAULT 0",
    ],
    # Per-profile ffmpeg encoder speed/quality trade-off (`-preset`, user
    # request) -- lets a profile favor faster encodes or better compression
    # independently of `crf`. Existing rows default to 'medium', ffmpeg's own
    # default, so behavior is unchanged until a user opts into a different
    # value.
    41: [
        "ALTER TABLE conversion_profiles ADD COLUMN preset TEXT NOT NULL DEFAULT 'medium'",
    ],
    # Opt-in "skip TLS certificate verification" for a `webdav` source
    # (Synology DSM's WebDAV Server ships with a self-signed HTTPS cert by
    # default). Off by default -- verification stays strict until the user
    # explicitly opts out; meaningless for `local`/`smb` rows.
    42: [
        "ALTER TABLE sources ADD COLUMN verify_ssl INTEGER NOT NULL DEFAULT 1",
    ],
    # Post-V1: resource-usage monitoring singleton (chat request -- diagnose
    # backend OOM restarts on Kubernetes by sampling CPU/memory at a
    # user-configurable interval into their own rotating log file, see
    # `app/resource_monitor.py` / `app/resource_monitor_settings.py`). Same
    # singleton convention as performance_settings.
    43: [
        """
        CREATE TABLE IF NOT EXISTS resource_monitor_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            enabled INTEGER NOT NULL DEFAULT 1,
            interval_seconds INTEGER NOT NULL DEFAULT 30,
            updated_at TEXT NOT NULL
        )
        """,
    ],
    # Post-V1 (chat request 2026-07-25 -- slow preview generation on
    # underpowered hardware): `frame_seek_mode` toggles ffmpeg frame
    # extraction between "keyframe" (adds `-noaccurate_seek`, ~10x faster,
    # frame lands on the nearest keyframe instead of the exact timestamp)
    # and "accurate" (prior behavior). Defaults to "keyframe" for new/
    # existing installs since the near-duplicate similarity match
    # (`app/similarity.py`) already tolerates a few seconds of drift between
    # sampled frames; switchable back per-install if that ever isn't true.
    44: [
        "ALTER TABLE preview_settings ADD COLUMN frame_seek_mode TEXT NOT NULL DEFAULT 'keyframe'",
    ],
    # Configurable log rotation (chat request): `backend.log` used to rotate
    # on a hardcoded 5-minute timer with one backup -- this lets the user
    # set a size threshold and how many backups to keep instead, see
    # `app/log_rotation_settings.py` / `app/logging_config.py`.
    45: [
        """
        CREATE TABLE IF NOT EXISTS log_rotation_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            max_bytes INTEGER NOT NULL DEFAULT 5242880,
            backup_count INTEGER NOT NULL DEFAULT 5,
            updated_at TEXT NOT NULL
        )
        """,
    ],
    # Post-V1 (chat request 2026-07-25 -- Settings -> Performance CPU/memory/
    # network history chart): resource_monitor's samples were log-only
    # (`app/resource_monitor.py`); this stores them so a time range can be
    # queried back out for the chart. Retention is capped at 24h by
    # `app/resource_monitor_history.py`'s own pruning on every write -- no
    # seed data needed, unlike the settings singletons above.
    46: [
        """
        CREATE TABLE IF NOT EXISTS resource_monitor_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            cpu_percent REAL NOT NULL,
            memory_percent REAL NOT NULL,
            network_bytes_per_sec REAL NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_resource_monitor_samples_timestamp ON resource_monitor_samples (timestamp)",
    ],
    # Post-V1 (chat request 2026-07-26): the job ETA estimate's sliding
    # rate-measurement window (`app/performance_settings.py`,
    # `frontend/src/utils/eta.ts`) was a hardcoded 5 minutes; this makes it a
    # user setting alongside `parallel_workers` in the same singleton.
    47: [
        "ALTER TABLE performance_settings ADD COLUMN eta_window_minutes INTEGER NOT NULL DEFAULT 5",
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
