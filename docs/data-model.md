# Video Archive Data Model

## Overview

This document defines the persistent data model for Video Archive. It focuses on local metadata storage, job history, cached analysis data, settings references, and backup-safe entities. Secrets are out of scope for the database entirely and live in the local secrets file (see [Tech Stack](./tech-stack.md)).

## Design Rules

- The database is SQLite, local to the backend machine.
- The database stores metadata and cached analysis, not large binary video payloads.
- Preview collages are **not** stored in the database; they live as JPEG files next to the videos on the source (see [Specification Section 9.5](./specification.md#95-preview-storage)).
- Files store paths **relative to the source root** only; absolute paths are computed at runtime.
- Files do not carry transient workflow states (`in_progress`, `failed`); execution state lives in jobs, job items, and events.
- Directory status is derived from file records and must not rely on persisted "fully processed" flags.
- Folder actions always apply recursively to nested subfolders.
- Conversion, preview, tagging, and rescan remain separate job types.

## Entity List

- `sources`
- `directories`
- `files`
- `conversion_profiles`
- `preview_layout_presets`
- `preview_settings`
- `jobs`
- `job_items`
- `file_tags`
- `tag_catalog`
- `file_similarity_signatures`
- `app_events`

## 1. sources

Represents the currently configured source connection, either a remote protocol source or a local directory next to the backend.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `name` | string | User-visible label |
| `protocol` | enum | `local`, `smb` (`webdav` reserved as optional) |
| `host` | string nullable | Remote host; unused for `local` |
| `port` | integer nullable | Optional explicit port; unused for `local` |
| `root_path` | string | For `local`: absolute/backend-relative local path. For `smb`: the share name plus an optional nested subpath, as one posix-style string (e.g. `videos` or `videos/archive`) — there is no separate "share" field; the first path segment is always the share name (see `app/sources/smb_backend.py`'s `_split_share()`). |
| `username_ref` | string nullable | Key name in the secrets file; unused for `local` |
| `secret_ref` | string nullable | Key name in the secrets file; unused for `local` |
| `is_active` | boolean | Only one active source at a time |
| `created_at` | datetime | Audit |
| `updated_at` | datetime | Audit |
| `last_connected_at` | datetime nullable | Last successful connection; unused for `local` |
| `last_scan_at` | datetime nullable | Last completed scan |

Rules:

- Only one row should have `is_active = true`.
- Credentials must not be stored in this table; `username_ref`/`secret_ref` name entries in the secrets file.
- Replacing the active source wipes `directories`, `files`, `file_tags`, `file_similarity_signatures`, `jobs`, `job_items`, and `app_events` after an explicit user confirmation (see [Specification Section 5.2](./specification.md#52-source-switching)).

## 2. directories

Represents a discovered directory inside the active source.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `source_id` | UUID | FK -> `sources.id` |
| `relative_path` | string | Unique within source |
| `name` | string | Directory name |
| `parent_relative_path` | string nullable | Root has null |
| `has_folder_preview` | boolean | `folder-preview.jpg` exists in this directory |
| `folder_preview_generated_at` | datetime nullable | Last successful folder preview generation |
| `last_scanned_at` | datetime nullable | Latest scan touching this subtree |
| `created_at` | datetime | Audit |
| `updated_at` | datetime | Audit |

Rules:

- Directory workflow status (conversion/preview completeness) is computed from files under the subtree.
- `has_folder_preview` is a fact about an artifact on disk (maintained by scan and preview jobs), not an aggregate status flag.
- The technical folder `.video-archive/` is never recorded here.

## 3. files

Represents a discovered file within the source.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `source_id` | UUID | FK -> `sources.id` |
| `directory_id` | UUID | FK -> `directories.id` |
| `relative_path` | string | Unique within source; relative to source root |
| `file_name` | string | Display name |
| `extension` | string | Lowercase file extension |
| `size_bytes` | bigint | Latest known size |
| `modified_at` | datetime nullable | Source-reported modification time |
| `discovered_at` | datetime | First discovery time |
| `last_scanned_at` | datetime | Last scan touching this file |
| `is_video_supported` | boolean | Extension is in the supported list ([Tech Stack](./tech-stack.md#supported-video-extensions)) |
| `converted_at` | datetime nullable | Last successful conversion; null = never converted |
| `last_conversion_profile_id` | UUID nullable | FK -> `conversion_profiles.id` |
| `has_preview_asset` | boolean | Matching `<basename>.jpg` exists next to the file |
| `preview_generated_at` | datetime nullable | Last successful preview generation by this app |
| `tagged_at` | datetime nullable | Last successful tagging; null = never tagged |
| `created_at` | datetime | Audit |
| `updated_at` | datetime | Audit |

Rules:

- There are no per-file `in_progress`/`failed` states; a file either has a fact recorded (converted, has preview, tagged) or it does not. Errors are visible through jobs and logs.
- A JPEG whose base name matches a video in the same directory is that video's preview asset and is not stored as an independent row.
- A moved or renamed file is treated as removed + new; history does not follow moves in V1.
- If a source file disappears, the row may remain until cleanup/rescan removes it.

## 4. conversion_profiles

Saved conversion presets.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `name` | string | User-visible profile name |
| `is_default` | boolean | Recommended default profile |
| `video_codec` | string | Default `h265` for V1 |
| `container` | string | Default `mp4` for V1 |
| `max_dimension` | integer nullable | Largest allowed side; null = never resize |
| `crf` | integer | Quality (x265 CRF); default `26`, practical range 22–32 |
| `drop_audio` | boolean | Default `true` |
| `extra_encoder_args` | json nullable | Reserved for advanced tuning |
| `created_at` | datetime | Audit |
| `updated_at` | datetime | Audit |

Rules:

- Profiles are reusable for bulk conversion.
- Variant-comparison results may be promoted into saved profiles.

## 5. preview_layout_presets

Saved preview layout definitions (see [Specification Section 9.2](./specification.md#92-collage-grid-layout)).

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `name` | string | Preset name |
| `grid_rows` | integer | Grid height in cells |
| `grid_cols` | integer | Grid width in cells |
| `timeline_flow` | enum | `row`, `column`, `shuffle` |
| `identity_diversity_enabled` | boolean | Default true |
| `layout_definition` | json | Enlarged tile placements: list of `{row, col, span}` with span 2 or 3; must keep the grid fully covered |
| `is_builtin` | boolean | Ships with the app (the preset gallery); built-in presets are not editable or deletable |
| `is_default` | boolean | Preferred preset |
| `created_at` | datetime | Audit |
| `updated_at` | datetime | Audit |

Notes:

- The sampled frame count is derived: `grid_rows × grid_cols` minus cells absorbed by enlarged tiles.
- The folder-preview frame count is a global preview setting, not part of layout presets (see `preview_settings` below).
- Collage appearance (black background, thin gaps, file-name caption) is a rendering rule, not preset data (see [Specification Section 9.2.1](./specification.md#921-collage-appearance)).
- Built-in presets (`is_builtin = 1`) are seeded once, idempotently, from application code (`app/preview_layouts.py`'s `seed_builtin_presets()`, called from `init_db()`) rather than from migration SQL, so their timestamps stay dynamic.

## 5a. preview_settings

Singleton row (`id` is always `1`) holding the two preview settings that are explicitly *not* part of a layout preset: the overall collage aspect ratio (independent of grid dimensions, [Specification §9.2](./specification.md#92-collage-grid-layout)) and the folder-preview frame count.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | integer | Always `1` (singleton) |
| `aspect_ratio` | enum | `standard`, `phone-portrait`, `ultra-wide`, `custom` |
| `aspect_ratio_custom_width` | integer nullable | Used only when `aspect_ratio = custom` |
| `aspect_ratio_custom_height` | integer nullable | Used only when `aspect_ratio = custom` |
| `folder_preview_frame_count` | integer | Default `4` |
| `updated_at` | datetime | Audit |

Seeded once (default row) from `app/preview_settings.py`'s `seed_default_settings()`, called from `init_db()` alongside the built-in preset seeding above.

## 6. jobs

Top-level task records.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `job_type` | enum | `scan`, `rescan`, `convert`, `preview`, `tag`, `cleanup`, `optimize_db`, `backup`, `restore` |
| `scope_type` | enum | `source`, `directory`, `file`, `maintenance` |
| `scope_ref` | string nullable | Relative path or file id depending on scope |
| `status` | enum | `queued`, `running`, `completed`, `failed`, `cancelled` |
| `parameters` | json | Job-specific config snapshot (profile values, mode, `skip_processed`, variants, layout, provider/model) |
| `started_at` | datetime nullable | Execution start |
| `finished_at` | datetime nullable | Execution finish |
| `summary_message` | text nullable | Human-readable outcome |
| `created_at` | datetime | Audit |
| `updated_at` | datetime | Audit |

Rules:

- Variant comparison is a `convert` job with `parameters.mode = "test"` and a `parameters.variants` list; there is no separate job type.
- Jobs are append-only except for status transitions and retention cleanup.
- Finished jobs (completed/failed/cancelled) are deleted automatically 24 hours after `finished_at`, and can be deleted manually at any time (individually or all finished at once).

## 7. job_items

Per-file or per-subtask execution rows under a parent job.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `job_id` | UUID | FK -> `jobs.id` |
| `file_id` | UUID nullable | FK -> `files.id` |
| `item_key` | string nullable | Fallback key if file missing |
| `status` | enum | `queued`, `running`, `completed`, `failed`, `cancelled`, `skipped` |
| `step_name` | string nullable | Optional substep |
| `message` | text nullable | Status message (including error summaries) |
| `started_at` | datetime nullable | Execution start |
| `finished_at` | datetime nullable | Execution finish |
| `output_ref` | string nullable | Relative path of produced output (converted file, preview jpg, variant file) |

Notes:

- `skipped` is used when the skip-processed rule bypasses an already-processed file.
- Job items are removed together with their parent job by retention cleanup.

## 8. tag_catalog

User-defined tag vocabulary (managed in settings; used for tagging prompts and search autocomplete).

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `tag_key` | string | Stable normalized key (lowercased) |
| `display_name` | string | UI label as entered by the user |
| `is_active` | boolean | Included in tagging prompts |
| `sort_order` | integer | Optional UI ordering |
| `created_at` | datetime | Audit |
| `updated_at` | datetime | Audit |

## 9. file_tags

Assigned tags for a specific file.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `file_id` | UUID | FK -> `files.id` |
| `tag_id` | UUID | FK -> `tag_catalog.id` |
| `score` | integer | Relevance score 0–100, shown as a percentage |
| `provider_name` | string nullable | Tagging provider |
| `model_name` | string nullable | Tagging model |
| `assigned_at` | datetime | Timestamp |

Rules:

- Only the top-N best-scoring tags are stored per file (default N = 10, configurable).
- Re-tagging replaces the file's previous tag set.

## 10. file_similarity_signatures

Cached near-duplicate signatures (optional feature).

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `file_id` | UUID | FK -> `files.id` |
| `sample_count` | integer | Fixed frame count used |
| `signature_type` | enum | `perceptual_hash`, `embedding`, `mixed` |
| `signature_payload` | json or blob | Compact signature data |
| `generated_from_job_id` | UUID nullable | FK -> `jobs.id` |
| `created_at` | datetime | Audit |
| `updated_at` | datetime | Audit |

## 11. app_events

Lightweight log/event stream for UI log viewing.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `job_id` | UUID nullable | FK -> `jobs.id` |
| `file_id` | UUID nullable | FK -> `files.id` |
| `level` | enum | `debug`, `info`, `warning`, `error` |
| `event_type` | string | Structured event name |
| `message` | text | Human-readable event |
| `payload` | json nullable | Structured details |
| `created_at` | datetime | Event timestamp |

Retention: events older than 24 hours are pruned together with job retention cleanup. Backend console/file logs remain the long-term record.

## Derived Status Queries

Directory indicators should be derived using subtree queries over `files`:

- conversion incomplete if any supported file in subtree has `converted_at IS NULL`
- preview incomplete if any supported file in subtree has `has_preview_asset = false`
- complete states are hidden in UI; only incomplete states are shown (running/failed activity is visible through the jobs UI, not through file flags)

## Indexing and Cleanup Behavior

- Rescan updates `last_scanned_at` for touched rows.
- Missing files can be marked stale during scan and removed during cleanup.
- Database optimization actions must not alter semantic metadata.

## Notes

- Store timestamps in UTC.
- Prefer JSON columns only for flexible or versioned structures; stable fields should remain explicit columns.
- No secrets anywhere in this schema; only key names referencing the secrets file.
