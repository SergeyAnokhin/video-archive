# Video Archive Data Model

## Overview

This document defines the persistent data model for Video Archive. It focuses on local metadata storage, job history, cached analysis data, settings references, and backup-safe entities. Secrets are out of scope for the main database and are defined separately in [Settings Specification](./settings-spec.md).

## Design Rules

- The database is local to the backend machine.
- The database stores metadata and cached analysis, not large binary video payloads.
- Directory status is derived from file records and must not rely on persisted "fully processed" flags.
- Folder actions always apply recursively to nested subfolders.
- Conversion, preview, tagging, and rescan remain separate job types.

## Entity List

- `sources`
- `directories`
- `files`
- `conversion_profiles`
- `preview_layout_presets`
- `jobs`
- `job_items`
- `file_tags`
- `tag_catalog`
- `file_similarity_signatures`
- `app_events`

## 1. sources

Represents the currently configured remote source connection.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `name` | string | User-visible label |
| `protocol` | enum | `smb`, `ftp`, `sftp`, `webdav` |
| `host` | string | Remote host |
| `port` | integer nullable | Optional explicit port |
| `root_path` | string | Remote base directory |
| `username_ref` | string nullable | Reference to credential storage |
| `secret_ref` | string nullable | Reference to secret storage |
| `is_active` | boolean | Only one active source at a time |
| `created_at` | datetime | Audit |
| `updated_at` | datetime | Audit |
| `last_connected_at` | datetime nullable | Last successful connection |
| `last_scan_at` | datetime nullable | Last completed scan |

Rules:

- Only one row should have `is_active = true`.
- Credentials must not be stored directly in this table.

## 2. directories

Represents a discovered directory inside the active source.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `source_id` | UUID | FK -> `sources.id` |
| `relative_path` | string | Unique within source |
| `name` | string | Directory name |
| `parent_relative_path` | string nullable | Root has null |
| `last_scanned_at` | datetime nullable | Latest scan touching this subtree |
| `created_at` | datetime | Audit |
| `updated_at` | datetime | Audit |

Rules:

- Directory status is computed from files under the subtree.
- Directory rows are structural, not status aggregates.

## 3. files

Represents a discovered file within the source.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `source_id` | UUID | FK -> `sources.id` |
| `directory_id` | UUID | FK -> `directories.id` |
| `relative_path` | string | Unique within source |
| `path` | string | Full current source path |
| `file_name` | string | Display name |
| `extension` | string | Lowercase file extension |
| `size_bytes` | bigint | Latest known size |
| `modified_at` | datetime nullable | Source-reported modification time |
| `discovered_at` | datetime | First discovery time |
| `last_scanned_at` | datetime | Last scan touching this file |
| `is_video_supported` | boolean | Eligible for video workflows |
| `conversion_state` | enum | `not_started`, `in_progress`, `done`, `failed` |
| `preview_state` | enum | `not_started`, `in_progress`, `done`, `failed` |
| `last_conversion_profile_id` | UUID nullable | FK -> `conversion_profiles.id` |
| `last_converted_at` | datetime nullable | Last successful conversion |
| `preview_generated_at` | datetime nullable | Last successful preview generation |
| `tagging_updated_at` | datetime nullable | Last successful closed-vocabulary tagging run |
| `tagging_model_info` | json nullable | Provider, model, and tagging snapshot metadata |
| `has_preview_assets` | boolean | Denormalized convenience flag |
| `last_error_code` | string nullable | Latest operational error code |
| `last_error_message` | text nullable | Latest operational error summary |
| `created_at` | datetime | Audit |
| `updated_at` | datetime | Audit |

Rules:

- `conversion_state` and `preview_state` are independent.
- `has_preview_assets` should agree with preview artifacts and `preview_generated_at`.
- `tagging_updated_at` and `tagging_model_info` should be cleared when the source file changes and old tags are invalidated.
- If a source file disappears, the row may remain until cleanup/rescan removes or tombstones it.

## 4. conversion_profiles

Saved conversion presets.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `name` | string | User-visible profile name |
| `is_default` | boolean | Recommended default profile |
| `video_codec` | string | Default `h265` for V1 |
| `container` | string | Default `mp4` for V1 |
| `max_dimension` | integer nullable | Largest allowed side |
| `quality_mode` | string nullable | Encoder quality mode |
| `quality_value` | string nullable | Preset-specific quality value |
| `drop_audio` | boolean | V1 default may be true |
| `extra_encoder_args` | json nullable | Reserved for advanced tuning |
| `created_at` | datetime | Audit |
| `updated_at` | datetime | Audit |

Rules:

- Profiles are reusable for bulk conversion.
- Tuning results may be promoted into saved profiles later.

## 5. preview_layout_presets

Saved preview layout definitions.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `name` | string | Preset name |
| `timeline_flow` | enum | `row`, `column`, `shuffle` |
| `sample_count` | integer | Total sampled frames |
| `large_tile_count` | integer | Highlighted tiles |
| `identity_diversity_enabled` | boolean | Default true |
| `layout_definition` | json | Tile geometry and ordering |
| `is_default` | boolean | Preferred preset |
| `created_at` | datetime | Audit |
| `updated_at` | datetime | Audit |

## 6. jobs

Top-level task records.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `job_type` | enum | `scan`, `convert`, `preview`, `tag`, `tune`, `rescan`, `cleanup`, `optimize_db`, `backup`, `restore` |
| `scope_type` | enum | `source`, `directory`, `file`, `maintenance` |
| `scope_ref` | string nullable | Relative path or file id depending on scope |
| `status` | enum | `queued`, `running`, `completed`, `failed`, `cancelled` |
| `requested_by` | string nullable | Reserved for future attribution |
| `parameters` | json | Job-specific config snapshot |
| `started_at` | datetime nullable | Execution start |
| `finished_at` | datetime nullable | Execution finish |
| `summary_message` | text nullable | Human-readable outcome |
| `cancel_requested_at` | datetime nullable | Best-effort cancellation request timestamp |
| `created_at` | datetime | Audit |
| `updated_at` | datetime | Audit |

Rules:

- Jobs are append-only for audit purposes except for status transitions and cleanup.
- Parameters should snapshot relevant profile or settings references used at job creation time.

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
| `message` | text nullable | Status message |
| `started_at` | datetime nullable | Execution start |
| `finished_at` | datetime nullable | Execution finish |
| `output_ref` | string nullable | Preview, temp output, or artifact reference |

## 8. tag_catalog

Allowed vocabulary for AI tagging.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `tag_key` | string | Stable key |
| `display_name` | string | UI label |
| `is_active` | boolean | Eligible for tagging prompts |
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
| `confidence` | decimal | Numeric confidence score |
| `provider_name` | string nullable | Tagging provider |
| `model_name` | string nullable | Tagging model |
| `assigned_at` | datetime | Timestamp |

Rules:

- Confidence should be stored with each assigned tag.
- Existing tags may be replaced on rerun depending on tagging mode.

## 10. file_similarity_signatures

Cached near-duplicate signatures.

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

## Derived Status Queries

Directory indicators should be derived using subtree queries over `files`:

- conversion incomplete if any supported file in subtree has `conversion_state != done`
- preview incomplete if any supported file in subtree has `preview_state != done` or `has_preview_assets = false`
- success indicators are hidden in UI; only incomplete, running, or failed states are shown

## Indexing and Cleanup Behavior

- Rescan updates `last_scanned_at` for touched rows.
- Missing files can be marked stale during scan and removed during cleanup.
- Database optimization actions must not alter semantic metadata.

## Notes

- Store timestamps in UTC.
- Prefer JSON columns only for flexible or versioned structures; stable fields should remain explicit columns.
- Keep secret references out of the main metadata schema.
