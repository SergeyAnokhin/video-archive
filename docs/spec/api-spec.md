# Video Archive API Specification

## Overview

This document defines the backend API surface for Video Archive: a React frontend against a local FastAPI backend. All endpoints use JSON unless noted otherwise. Exact request/response shapes live in the code (routers are thin; see [`code-map-routers.md`](../code-map-routers.md)); this document fixes the surface and the semantics.

## Conventions

- Base path: `/api`
- The backend binds to `0.0.0.0` (post-V1 — LAN access from phones/tablets is supported); authentication is out of scope
- Timestamps use ISO 8601 UTC
- Long-running operations return a job record
- Folder actions are recursive by default
- Directory paths are passed as query or body parameters (`path`), never as URL path segments, to avoid slash-encoding issues
- Settings groups are singletons with `GET`/`PUT` endpoint pairs; a `PUT` is a full replace and applies immediately
- A literal-path route (e.g. `GET /jobs/batch-submissions`) must be declared before a same-method `/{id}`-style route in the same router, or the `{id}` route swallows the literal path

## 1. Health and App Info

- `GET /api/health` — liveness (`{"status": "ok"}`).
- `GET /api/app/info` — app version, active source summary, DB status, queue status, ffmpeg availability.
- `GET /api/app/network-info` — `{lan_addresses, frontend_port, backend_port}` for the Settings → Network page.

## 2. Source Management

### Active source

- `GET /api/source` — the currently active source.
- `PUT /api/source` — connect (upserts a saved source matching `(protocol, host, port, root_path)`, then runs the switch flow: back up outgoing, wipe scoped data, activate, auto-restore incoming's backup, scan). Response includes `detected_backups` and `auto_restored`. The connect scan is synchronous.
- `POST /api/source/test-connection` — test a configuration without saving it.
- `POST /api/source/reconnect` — reconnect the active source (no-op for `local`).

Request body (SMB): `name`, `protocol: "smb"`, `host`, `port`, `root_path` (`share[/subpath]`), `username`, `password`. Credentials go to the secrets file per source id. Request body (local): `name`, `protocol: "local"`, `root_path` (absolute or backend-relative). `webdav` → `400 unsupported_protocol`.

### Saved sources (post-V1)

- `GET /api/sources` — every saved source, each with local preview-cache stats.
- `POST /api/sources/{id}/activate` — switch to a saved source (no-op if already active).
- `DELETE /api/sources/{id}` — forget a saved source (`400 active_source` for the active one); removes the row, credentials, and preview cache — never touches the source's disk.
- `DELETE /api/sources/{id}/preview-cache` — clear the cached GIFs; for the active source also resets has-preview facts so the next preview run regenerates.

## 3. Directory and File Browsing

- `GET /api/tree` — recursive tree (`path`, `depth`, `include_status`, `include_top_tags`). Expensive per-node fields are opt-in booleans, off by default.
- `GET /api/directories/children` — one directory's subfolders and files (`path`, `include_status`, `include_top_tags`). Files carry `duration_seconds`, `variant_tags`, `ai_tags`, `is_variant`/`is_original`; a variant borrows its original sibling's `has_preview_asset`. `include_top_tags` adds each subfolder's dynamic top-5 most-used tags.
- `GET /api/directories/search?q=` — folder-name substring search, paginated (backs the `path:` search scope).
- `GET /api/files` — file list (`directory`, `recursive`, `video_only`, `search`, `tags`, `tag_search`, `limit`, `offset`).
- `GET /api/files/{file_id}` — full file metadata.
- `GET /api/files/{file_id}/media-info` — on-demand ffprobe details (`null` fields when unprobeable); works for standalone images too.
- `GET /api/files/{file_id}/similar` — approximate near-duplicate matches (perceptual-hash distance, same-kind only). Empty when no signature exists yet or nothing is close.

## 4. Directory Operations (post-V1)

- `POST /api/directories` — create a folder (`{parent_path, name}`; `invalid_name` / `destination_collision` errors).
- `DELETE /api/directories?path=` — delete an **empty** folder only (`400 directory_not_empty`; deliberately non-recursive).
- `PUT /api/directories/favorite` — toggle a folder's favorite flag.
- `GET /api/directories/favorites` — list favorite folders.

## 5. File Operations (post-V1)

- `POST /api/files/{file_id}/move` — move a file (with its sibling preview assets and DB rows) to another folder.
- `DELETE /api/files/{file_id}` — delete a file together with its sibling preview assets.

Both map domain error codes to HTTP statuses via one exception type per module.

## 6. Conversion Profiles

- `GET/POST /api/conversion-profiles`, `PUT/DELETE /api/conversion-profiles/{profile_id}`.

## 7. Preview Layouts and Settings

- `GET/POST /api/preview-layouts`, `PUT/DELETE /api/preview-layouts/{preset_id}` (`409 preset_protected` for built-ins).
- `POST /api/preview-layouts/preview` — stateless live-preview: validates enlarged-tile placements against the grid and returns the full tile list and derived `frame_count` (`400 invalid_layout` on out-of-bounds/overlap/bad span). The backend stays the single source of truth for grid geometry.
- `GET/PUT /api/preview-settings` — singleton: aspect ratio (`standard | phone-portrait | phone-landscape | ultra-wide | custom` + custom W/H), folder-preview frame count, `gif_max_width`, `gif_colors`, `animated_source_mode` (`frame | clip`), `animated_segment_seconds`, `animated_transition` (`cut | crossfade`).

## 8. Jobs

- `GET /api/jobs` (`status`, `job_type`, `limit`, `offset`), `GET /api/jobs/{job_id}`, `GET /api/jobs/{job_id}/items`.
- `POST /api/jobs/{job_id}/cancel` — best-effort; a second cancel on a running job force-finishes it.
- `POST /api/jobs/{job_id}/pause` / `POST /api/jobs/{job_id}/resume` — per-item-loop job types only (`409 job_not_pausable` / `job_not_resumable`).
- `POST /api/jobs/{job_id}/restart` — creates a new job with copied parameters.
- `DELETE /api/jobs/{job_id}`; `DELETE /api/jobs` — clear all finished (also auto-removed after 24 h).

### Job triggers

- `POST /api/jobs/rescan-directory` — recursive rescan (`{path}`; the source root covers the whole source).
- `POST /api/jobs/convert-directory` — `{path, profile_id, mode: "production"|"test", skip_processed}`.
- `POST /api/jobs/convert-file` — `{file_id, profile_id, mode, skip_processed, variants?}`; `variants` (list of parameter overrides) requires `mode: "test"` and produces `<basename>.variant-<params>.mp4` outputs — the variant-comparison ("tuning") flow.
- `POST /api/jobs/preview-directory` / `POST /api/jobs/preview-file`.
- `POST /api/jobs/tag-directory` / `POST /api/jobs/tag-file` — `400 no_provider_configured` / `empty_tag_vocabulary`; the actual provider entry is resolved live by the worker in priority order.
- `POST /api/jobs/cleanup-stale-records`, `POST /api/jobs/optimize-database`.

### Batch submissions (post-V1)

- `GET /api/jobs/batch-submissions` — still-pending provider-side batch-tagging submissions.
- `DELETE /api/jobs/batch-submissions/{id}` — forget locally (no provider-side cancel; the owning job falls back per-file).

## 9. Preview Assets

- `GET /api/files/{file_id}/preview` — preview metadata (existence, generation time).
- `GET /api/files/{file_id}/preview.jpg` — the JPEG collage, read from the source itself.
- `GET /api/files/{file_id}/preview.gif` — the animated preview, served from the local per-source cache.
- `GET /api/directories/preview.gif?path=` — the folder GIF, from the local cache.

A variant file's preview endpoints redirect onto its original sibling's assets.

## 10. Tags

- `GET /api/tags` — one managed pool at a time (`category: "ai" | "user"`, default `"ai"`; `query` prefix filter, `active_only`, `limit`).
- `GET /api/tags/used` — tags actually assigned to files, from **every** pool, usage-ordered (`query`, `limit`); feeds every per-file add-tag suggestion list.
- `POST /api/tags` (`409` on duplicate key; `is_ai_vocabulary` / `is_user_defined` select the pool; optional `color` hex), `PUT/DELETE /api/tags/{tag_id}`.
- Every tag response includes `color` — the stored value or a deterministic hash-based fallback, never null.

### Per-file tags

- `GET /api/files/{file_id}/tags` — assigned tags with relevance scores (0–100).
- `POST /api/files/{file_id}/tags` / `DELETE /api/files/{file_id}/tags/{tag_id}` — manual assign/remove (by `tag_id` or `display_name`; score 100, provenance `manual`, ad-hoc pool — never silently joins a managed pool).
- `POST /api/files/{file_id}/tags/user-defined` — assign from (or create into) the user-defined pool.

## 11. Tagging Settings and Tag Lab

- `GET/PUT /api/tagging-settings` — singleton: `sample_frame_count`, `combine_into_collage`, `top_tag_count`, `image_resolution`, `request_timeout_seconds`.
- `POST /api/tagging-settings/preview` — stateless "what the model sees": builds real tagging images for a file id with arbitrary (possibly unsaved) parameters, returned as base64 data URLs.

### Tag Lab (post-V1)

- `POST /api/files/{file_id}/tag-lab/prepare` — images + prompt only, no provider call (renders before the model responds).
- `POST /api/files/{file_id}/tag-lab/run` — `{provider_entry_id}` → `run_id`, images/prompt (cached between runs for an unchanged file), raw reply text, full raw provider JSON, token/cost usage, and every vocabulary tag ranked by score. Writes nothing. Synchronous provider failures map to `400`, with the raw response attached whenever the provider returned something.
- `POST /api/files/{file_id}/tag-lab/apply` — `{provider_type, model_name, run_id?, tags}` → writes the file's tags, records the apply-behavior KPI.
- `POST /api/tag-lab/runs/{run_id}/feedback` — `{tag_id, display_name, vote: 1 | -1 | null}` per suggested tag.

## 12. Provider Settings (post-V1 shape)

- `GET/POST /api/settings/provider-entries`, `PUT/DELETE /api/settings/provider-entries/{id}` — API keys are never echoed (only `has_api_key` / `key_suffix`).
- `POST /api/settings/provider-entries/reorder` — set fallback priority.
- `POST /api/settings/provider-entries/models` (draft key) / `POST /api/settings/provider-entries/{id}/models` (stored key) — model-catalog lookup.
- `GET /api/settings/provider-entries/export` — JSON download **including plaintext keys** (deliberate; UI confirms first). `POST /api/settings/provider-entries/import` — reads the export back (unknown provider types skipped and counted).
- `GET /api/settings/provider-usage` — per-(provider, model) usage summary.
- `GET/PUT /api/settings/model-pricing`; `POST /api/settings/model-pricing/refresh-openrouter` (`400 pricing_refresh_failed` on network error).
- `GET /api/settings/model-ratings` — per-model like/dislike + apply-KPI stats.

## 13. Playback

- `GET /api/files/{file_id}/playback` — preferred playback target per settings (mode, stream URL, direct path).
- `GET /api/files/{file_id}/stream` — Range-aware streaming for embedded playback; also serves a standalone image's own bytes for the image viewer and thumbnails.

## 14. Logs and Events

- `GET /api/logs` (`job_id`, `file_id`, `level`, `limit`).
- `GET /api/logs/stream` — SSE, near real time.

## 15. Settings Singletons

- `GET/PUT /api/playback-settings` — `mode: "stream" | "direct_link"`.
- `GET/PUT /api/backup-settings` — `retention_count`.
- `GET/PUT /api/performance-settings` — `parallel_workers` (1–16).
- `GET/PUT /api/interface-settings` — `language`, `theme_preset` (8 presets), two preview stylization profiles (six filter fields each), and per-group search limits.

## 16. Backups

Backup and restore run as jobs (`backup` / `restore` job types). Packages live in `.video-archive/backups/` at the source root (see [Backup Format](./backup-format.md)).

- `GET /api/backups`, `POST /api/backups` (optional `include_secrets`), `POST /api/backups/restore`, `DELETE /api/backups/{backup_id}` (synchronous).

Source switching invokes backup/restore internally, not through these endpoints.

## Error Model

Errors carry a structured code + message:

```json
{
  "error": {
    "code": "source_connection_failed",
    "message": "Unable to reach remote source"
  }
}
```

Known gap: FastAPI's default handler nests this under `{"detail": {...}}`. Domain modules raise one exception class carrying `code`/`message`; the router maps codes to HTTP statuses. Synchronous provider-call failures always map to `400`.

## Notes

- Endpoints returning directory status compute recursive progress from files; expensive per-node fields are opt-in query booleans.
- Job creation endpoints snapshot relevant profile or settings data into job parameters.
- The frontend assumes long-running work is asynchronous and job-backed; Tag Lab is the deliberate synchronous exception.
