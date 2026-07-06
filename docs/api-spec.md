# Video Archive API Specification

## Overview

This document defines the backend API surface for Video Archive. The API is intended for a React frontend and a local FastAPI backend. All endpoints below are conceptual v1 endpoints and use JSON unless noted otherwise.

## Conventions

- Base path: `/api`
- The backend binds to `127.0.0.1` only; authentication is out of scope for this version
- Timestamps use ISO 8601 UTC
- Long-running operations return a job record
- Folder actions are recursive by default
- Directory paths are passed as query or body parameters (`path`), never as URL path segments, to avoid slash-encoding issues

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
- queue status (current job, if any)
- ffmpeg availability

## 2. Source Management

### `GET /api/source`

Returns the currently configured source.

### `PUT /api/source`

Creates or replaces the active source configuration. Replacing an existing source is destructive: the frontend must show a confirmation warning first, and the backend wipes all library metadata (see [Specification Section 5.2](./specification.md#52-source-switching)).

Request body (remote protocol source):

```json
{
  "name": "Archive NAS",
  "protocol": "smb",
  "host": "nas.local",
  "port": 445,
  "root_path": "/videos",
  "username": "user",
  "password": "secret"
}
```

Request body (local source, a directory next to the backend):

```json
{
  "name": "Local Library",
  "protocol": "local",
  "root_path": "./library"
}
```

Response includes `detected_backups`: backups found in the new source's `.video-archive/backups/` folder, so the UI can immediately offer a restore.

Notes:

- Credentials are written to the secrets file; only key references are stored in the database.
- Only one active source is supported.
- For `protocol: "local"`, `root_path` may be absolute or relative to the backend working directory; `host`, `port`, `username`, and `password` are not used.

### `POST /api/source/test-connection`

Tests a source configuration without permanently saving it.

### `POST /api/source/reconnect`

Reconnects to the active source (remote protocols only).

## 3. Directory and File Browsing

### `GET /api/tree`

Returns the directory tree for the active source.

Query parameters:

- `path` optional relative path root
- `depth` optional integer
- `include_status` optional boolean

### `GET /api/directories/children`

Returns immediate child folders and files for one directory.

Query parameters:

- `path` relative directory path (empty = source root)
- `include_status` optional boolean (derived recursive conversion/preview indicators)

### `GET /api/files`

Returns file list.

Query parameters:

- `directory` relative directory path
- `recursive`
- `video_only`
- `search` optional text; matches file names
- `tags` optional comma-separated tag keys; matches assigned tags
- `limit`
- `offset`

### `GET /api/files/{file_id}`

Returns full file metadata and cached processing details.

### `GET /api/files/{file_id}/similar`

Returns approximate near-duplicate matches for one file (Specification §13, optional/secondary feature), ranked by perceptual-hash distance. Empty when the file has no stored signature yet (signatures are generated best-effort as a side effect of the `preview` job) or nothing else in the source is close enough.

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

Generates a lightweight live preview payload for the preview settings page: validates the enlarged-tile placements against the grid and returns the full tile list (small tiles auto-filled), so the frontend construction-set editor and the backend collage renderer share one source of truth for grid geometry.

Request body includes:

- grid size (`grid_rows`, `grid_cols`)
- enlarged tile placements (`{row, col, span}` list, `layout_definition`)
- timeline flow
- identity diversity setting

Response:

- `grid_rows`, `grid_cols`
- `tiles`: full tile list (`{row, col, span, type}`, `type` is `small` or `enlarged`)
- `frame_count`: number of frames the layout requires (Specification §9.2)

Returns `400 invalid_layout` if an enlarged tile is out of bounds, has an invalid span (must be 2 or 3), or overlaps another.

### `GET /api/preview-settings`

Returns the global preview settings singleton: `aspect_ratio` (`standard | phone-portrait | ultra-wide | custom`), `aspect_ratio_custom_width`/`aspect_ratio_custom_height` (used only when `aspect_ratio` is `custom`), and `folder_preview_frame_count` (default 4). These two settings are deliberately not part of a layout preset (Data Model §5).

### `PUT /api/preview-settings`

Updates the global preview settings singleton. Applies immediately, like other settings groups.

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

### `GET /api/jobs/{job_id}/items`

Returns item-level progress for a job.

### `POST /api/jobs/{job_id}/cancel`

Requests cancellation.

### `POST /api/jobs/{job_id}/restart`

Creates a restart or rerun job when supported.

### `DELETE /api/jobs/{job_id}`

Removes one job from the list.

### `DELETE /api/jobs`

Removes all finished (completed, failed, cancelled) jobs at once. Finished jobs are also auto-removed after 24 hours (see [Job Model](./job-model.md#retention)).

## 7. Scan and Maintenance Jobs

### `POST /api/jobs/scan-source`

Starts a full source scan.

### `POST /api/jobs/rescan-directory`

Starts a recursive rescan for one directory subtree.

Request body:

```json
{
  "path": "family/2024"
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
  "path": "family/2024",
  "profile_id": "uuid",
  "mode": "production",
  "skip_processed": true
}
```

- `mode`: `production` | `test` (test preserves originals, see [Specification Section 8.2](./specification.md#82-test-mode))
- `skip_processed`: default `true`; skip files already converted

### `POST /api/jobs/convert-file`

Starts conversion for one file.

Request body:

```json
{
  "file_id": "uuid",
  "profile_id": "uuid",
  "mode": "test",
  "skip_processed": false,
  "variants": [
    { "max_dimension": 1000, "crf": 26 },
    { "max_dimension": 1000, "crf": 28 },
    { "max_dimension": 800, "crf": 28 }
  ]
}
```

- `variants` is optional and allowed only with `mode: "test"`; each variant produces a separate output named `<basename>.variant-<params>.mp4`. This is the variant-comparison (former "tuning") flow.

## 9. Preview Jobs

### `POST /api/jobs/preview-directory`

Starts recursive preview generation for a directory subtree (file collages plus folder previews).

Request body:

```json
{
  "path": "family/2024",
  "skip_processed": true
}
```

### `POST /api/jobs/preview-file`

Starts preview generation for one file.

### `GET /api/files/{file_id}/preview`

Returns preview asset metadata for a file (existence, path, generation time).

### `GET /api/files/{file_id}/preview.jpg`

Serves the preview collage image itself (read through the source access layer).

### `GET /api/directories/preview.jpg`

Serves a folder preview image. Query parameter: `path`.

## 10. Tagging and Tags

### `GET /api/tags`

Returns the tag vocabulary.

Query parameters:

- `query` optional prefix filter for autocomplete (matches from the first letters)
- `active_only` optional boolean
- `limit`

### `POST /api/tags`

Adds a tag to the vocabulary.

### `PUT /api/tags/{tag_id}`

Updates a tag (rename, activate/deactivate).

### `DELETE /api/tags/{tag_id}`

Removes a tag from the vocabulary; assigned `file_tags` referencing it are removed as well.

### `POST /api/jobs/tag-directory`

Starts recursive tagging for a directory subtree.

Request body:

```json
{
  "path": "family/2024",
  "skip_processed": true
}
```

### `POST /api/jobs/tag-file`

Starts tagging for one file.

### `GET /api/files/{file_id}/tags`

Returns assigned tags with relevance scores (0–100) for a file.

## 11. Playback

### `GET /api/files/{file_id}/playback`

Returns the preferred playback target according to current playback settings.

Response may include:

- embedded stream URL (backend streaming endpoint)
- external path or protocol link (for example a UNC path)
- playback mode

### `GET /api/files/{file_id}/stream`

Streams the video file with HTTP Range support for embedded browser playback (used when playback mode is `stream`).

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

## 13. Settings

### `GET /api/settings`

Returns non-secret settings payload for the frontend.

### `PUT /api/settings`

Updates non-secret settings payload.

### `GET /api/settings/providers`

Returns provider configuration summary (keys masked).

### `PUT /api/settings/providers`

Updates provider settings; API keys are written to the secrets file.

### `GET /api/settings/export`

Exports settings package including provider configuration and API keys when explicitly requested.

### `POST /api/settings/import`

Imports a settings package.

### `GET /api/interface-settings`

Returns the interface settings singleton: `language` (`en | ru`) and `theme_preset` (`strict | playful`).

### `PUT /api/interface-settings`

Updates the interface settings singleton. Applied immediately on the frontend, without a page reload (Settings Specification §9).

## 14. Backups

Backup and restore run as jobs (`backup` / `restore` job types) and return a job record. Packages live in `.video-archive/backups/` at the source root (see [Backup Format](./backup-format.md)).

### `GET /api/backups`

Returns available backups found in the active source's technical folder.

### `POST /api/backups`

Creates a manual backup. Returns the created `backup` job.

### `POST /api/backups/restore`

Restores a selected backup. Returns the created `restore` job.

### `DELETE /api/backups/{backup_id}`

Deletes a backup package.

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

## Notes

- Endpoints returning directory status should compute recursive progress from files.
- Job creation endpoints should snapshot relevant profile or settings data into job parameters.
- The frontend should assume long-running work is asynchronous and job-backed.
