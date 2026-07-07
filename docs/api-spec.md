# Video Archive API Specification

## Overview

This document defines the backend API surface for Video Archive. The API is intended for a React frontend and a local Python backend. All endpoints below are conceptual v1 endpoints and use JSON unless noted otherwise.

## Conventions

- Base path: `/api`
- Authentication strategy is out of scope for this version
- Timestamps use ISO 8601 UTC
- Long-running operations return a job record
- Folder actions are recursive by default

## 1. Health and App Info

### `GET /api/health`

Returns backend liveness information.

Response:

```json
{
  "status": "ok"
}
```

### `GET /api/app/info`

Returns runtime information needed by the frontend.

Response fields:

- app version
- active source summary
- database status
- queue status

## 2. Source Management

### `GET /api/source`

Returns the currently configured source.

### `GET /api/local-directories`

Lists backend-local directories for the source settings folder picker.

Query parameters:

- `path` optional absolute path to browse, or omitted to return Windows drive roots

Current implementation also returns `favorites` when available, including the repo-local `test-data/VideoArchive` folder and backend-adjacent directories that are useful for local testing.

### `PUT /api/source`

Creates or replaces the active source configuration.

Request body:

```json
{
  "name": "Test Library",
  "protocol": "local",
  "root_path": "C:\\Videos\\Test Library"
}
```

Notes:

- `protocol` currently supports `local`, `smb`, `ftp`, `sftp`, and `webdav`.
- local sources skip TCP probing and only validate backend access to `root_path`.
- the persisted backend row keeps local sources compatible with the existing `sources` table by storing the local sentinel host and mapping the result back to `protocol: "local"` in API responses.
- Secrets may be routed into secret storage rather than the main database.
- Only one active source is supported.

### `POST /api/source/test-connection`

Tests a source configuration without permanently saving it.

### `POST /api/source/reconnect`

Reconnects to the active source.

## 3. Directory and File Browsing

### `GET /api/tree`

Returns the directory tree for the active source.

Query parameters:

- `path` optional relative path root
- `depth` optional integer
- `include_status` optional boolean

### `GET /api/directories`

Returns directory rows and derived recursive status indicators.

Query parameters:

- `path`
- `include_children`
- `include_counts`

### `GET /api/directories/{relative_path}`

Returns one directory summary.

### `GET /api/directories/{relative_path}/children`

Returns immediate child folders and files.

### `GET /api/files`

Returns file list.

Query parameters:

- `directory`
- `recursive`
- `video_only`
- `limit`
- `offset`

### `GET /api/files/{file_id}`

Returns full file metadata and cached processing details.

Current implementation also enriches the payload with:

- `media_info` when `ffprobe` is available on the backend machine and the file can be probed
  - includes video codec, codec profile, audio codec, width, height, display aspect ratio, frame rate, pixel format, duration, and bitrate when available
- `last_conversion_profile_id`
- `last_conversion_profile` for the saved profile that last converted the file, when one is recorded and still exists
- `generated_kind`, `generated_from_job_id`, and `generated_from_file_id` for generated tuning or test-conversion outputs

### `POST /api/files/{file_id}/move`

Moves one file into another folder under the active source root.

Request body:

```json
{
  "destination_directory": "family/archive"
}
```

### `DELETE /api/files/{file_id}`

Deletes one file from disk and removes its metadata row.

## 4. Conversion Profiles

### `GET /api/conversion-profiles`

Returns saved conversion profiles.

### `POST /api/conversion-profiles`

Creates a conversion profile.

### `PUT /api/conversion-profiles/{profile_id}`

Updates a conversion profile.

### `DELETE /api/conversion-profiles/{profile_id}`

Deletes a conversion profile if not protected.

## 5. Preview Layout Presets

### `GET /api/preview-layouts`

Returns saved preview layout presets.

### `POST /api/preview-layouts`

Creates a preview layout preset.

### `PUT /api/preview-layouts/{preset_id}`

Updates a preview layout preset.

### `DELETE /api/preview-layouts/{preset_id}`

Deletes a preview layout preset.

### `POST /api/preview-layouts/preview`

Generates a lightweight live preview payload for the preview settings page.

Request body includes:

- selected layout preset
- sample frame count
- timeline flow
- large tile count
- aspect ratio preset
- identity diversity setting

Response:

- tile geometry
- tile labels or frame placeholders
- optional representative images

## 6. Jobs

### `GET /api/jobs`

Returns jobs.

Query parameters:

- `status`
- `job_type`
- `limit`
- `offset`

### `GET /api/jobs/{job_id}`

Returns a job summary.

Current foundation response also includes:

- `cancel_requested_at`
- `item_counts` with queued, running, completed, failed, cancelled, skipped, and total counts

### `GET /api/jobs/{job_id}/items`

Returns item-level progress for a job.

### `POST /api/jobs/{job_id}/cancel`

Requests cancellation.

### `POST /api/jobs/{job_id}/restart`

Creates a restart or rerun job when supported.

### `DELETE /api/jobs/{job_id}`

Removes a completed or failed job from the UI list if allowed by retention policy.

## 7. Scan and Maintenance Jobs

### `POST /api/jobs/scan-source`

Starts a full source scan.

### `POST /api/jobs/rescan-directory`

Starts a recursive rescan for one directory subtree.

Request body:

```json
{
  "relative_path": "family/2024"
}
```

### `POST /api/jobs/cleanup-stale-records`

Starts stale-record cleanup.

### `POST /api/jobs/optimize-database`

Starts database optimization.

## 8. Conversion Jobs

### `POST /api/jobs/convert-directory`

Starts recursive conversion for a directory subtree.

Request body:

```json
{
  "relative_path": "family/2024",
  "profile_id": "uuid",
  "mode": "production"
}
```

### `POST /api/jobs/convert-file`

Starts conversion for one file.

Request body:

```json
{
  "file_id": "uuid",
  "profile_id": "default-h265-mp4",
  "mode": "test"
}
```

### `POST /api/jobs/tune-file`

Starts a tuning sweep for one file.

Request body:

```json
{
  "file_id": "uuid",
  "sweep": {
    "dimensions": [800, 900, 1000],
    "quality_values": ["20", "24", "28"],
    "codecs": ["h265"]
  }
}
```

Rules:

- tuning must never replace the source
- tuning generates separate outputs
- tuning output filenames should encode the tested codec, max side, and CRF

## 9. Preview Jobs

### `POST /api/jobs/preview-directory`

Starts recursive preview generation for a directory subtree.

### `POST /api/jobs/preview-file`

Starts preview generation for one file.

### `GET /api/files/{file_id}/preview`

Returns preview asset metadata for a file.

### `GET /api/files/{file_id}/preview-image`

Streams the stored preview image for a file. File previews are stored beside the source video with the same basename and a `.jpg` suffix.

### `GET /api/directories/{relative_path}/preview`

Returns preview asset metadata for a directory.

## 10. Tagging Jobs

### `POST /api/jobs/tag-directory`

Starts recursive tagging for a directory subtree.

### `POST /api/jobs/tag-file`

Starts tagging for one file.

### `GET /api/files/{file_id}/tags`

Returns tags and confidence scores for a file.

Current implementation returns:

- file identity fields
- stored tags ordered by confidence
- `tagging_updated_at`
- `tagging_model_info` with provider and model

## 11. Playback

### `GET /api/files/{file_id}/playback`

Returns the preferred playback target according to current playback settings.

Response may include:

- embedded stream URL
- external path
- external link
- playback mode

## 12. Logs and Events

### `GET /api/logs`

Returns recent event log entries.

Query parameters:

- `job_id`
- `file_id`
- `level`
- `limit`

### `GET /api/logs/stream`

Streams log events in near real time.

Recommended transport:

- Server-Sent Events for v1

Current foundation behavior:

- implemented as `text/event-stream`
- supports filtering by `job_id`
- streams persisted `app_events` rows for UI-tail updates

## 13. Settings

### `GET /api/settings`

Returns non-secret settings payload for the frontend.

Current implementation returns:

- `preview`
- `tagging`

### `PUT /api/settings`

Updates non-secret settings payload.

### `GET /api/settings/providers`

Returns provider configuration summary.

Current implementation returns an ordered array of provider entries, including:

- `id`
- `label`
- `enabled`
- `provider`
- `vision_model`
- optional `text_model`
- `prefer_batch`
- `order_index`
- `api_key_configured`

### `PUT /api/settings/providers`

Updates provider settings, including explicit secret changes.

### `POST /api/settings/providers/models`

Loads models for one provider type using either:

- an explicit `api_key`, or
- a saved provider entry referenced by `provider_id`

### `GET /api/settings/export`

Exports settings package including provider configuration when explicitly requested.

### `POST /api/settings/import`

Imports a settings package.

## 14. Backups

### `GET /api/backups`

Returns available backups.

### `POST /api/backups`

Creates a manual backup.

### `POST /api/backups/restore`

Restores a selected backup.

### `DELETE /api/backups/{backup_id}`

Deletes a backup if manual deletion is allowed.

## Error Model

Recommended response structure:

```json
{
  "error": {
    "code": "source_connection_failed",
    "message": "Unable to reach remote source"
  }
}
```

Current implementation notes:

- unhandled backend exceptions return `500` with `error.code = "internal_server_error"` and the exception type/message in `error.message`
- the backend also prints the full Python stack trace, request method, and request path to the terminal where `python -m app.main` is running

## Notes

- Endpoints returning directory status should compute recursive progress from files.
- Job creation endpoints should snapshot relevant profile or settings data into job parameters.
- The frontend should assume long-running work is asynchronous and job-backed.
- In the current implementation, `convert`, `preview`, and `tag` endpoints run real backend work backed by saved settings snapshots. `tune` still creates real queued jobs, items, and events but remains placeholder-only.
