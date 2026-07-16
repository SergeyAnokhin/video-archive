# Video Archive Backup Format

## Overview

This document defines the expected contents and behavior of manual backups for Video Archive.

## Backup Location

- Backups are stored **on the source disk itself**, in the technical folder at the source root: `.video-archive/backups/`.
- Each backup is one self-contained package (a zip archive) named by its creation timestamp and id.
- The technical folder is excluded from scanning and all processing workflows.
- Because backups live with the archive, they survive a local metadata wipe (for example a source switch) and travel with the archive if it is moved.
- Backups are created two ways: manually from Settings, and **automatically on every source switch** — the outgoing source is backed up onto its own disk, and the incoming source's newest backup is auto-restored (scoped data only), so each source's metadata follows it across switches (see [Specification Section 5.2](./specification.md#52-source-switching)).

## Backup Scope

Backups primarily protect local metadata and local application configuration. They do not copy the video files themselves.

## Included Data

A backup should include:

- source-scoped metadata: directories, files, and assigned file tags
- conversion profiles
- preview layout presets (non-built-in)
- the full tag catalog (all pools)
- provider entries
- settings singletons (preview, tagging, playback, backup)
- the secrets file, only when the user explicitly opted in at backup time (`include_secrets`)

## Excluded Data

A backup should not attempt to duplicate:

- the video library itself
- preview collages (they already live next to the videos on the source)
- the local GIF preview cache (regenerable)
- job history (`jobs`/`job_items`/`app_events` are short-lived, 24 h retention)
- arbitrary temporary conversion files or other regenerable transient caches

## Backup Metadata

Each backup package should include:

- backup id
- created timestamp
- application version
- schema version
- source summary

## Restore Rules

- Restore should replace or merge local metadata according to the chosen restore mode.
- Restore must validate schema compatibility before applying.
- Restore should fail safely if the package is invalid or incompatible.
- When a source is connected and its technical folder contains backups, the UI proactively offers to restore one (see [Specification Section 5.2](./specification.md#52-source-switching)).

## Retention

- Backup retention count is configurable.
- Default retention count is `5`.
- When the count is exceeded, the oldest backups are removed after a successful new backup.

## Suggested Package Shape

Suggested package contents:

- metadata database dump or file copy
- settings export payload
- manifest file

Suggested manifest example:

```json
{
  "backup_id": "uuid",
  "created_at": "2026-07-06T12:00:00Z",
  "app_version": "0.1.0",
  "schema_version": 1,
  "includes_secrets": true
}
```

## Implementation Notes

The implementation (`backend/app/backup.py`) resolves the choices left open above as follows:

- **Package shape**: a single zip containing `manifest.json`, `data.json` (JSON dump of the included tables' rows), and an optional raw `secrets.env` copy when `include_secrets` was requested at backup time.
- **Captured tables**: source-scoped `directories`/`files` (plus their `file_tags`), global multi-row `conversion_profiles`/`tag_catalog`/`provider_entries`/`preview_layout_presets` (non-built-in), and the `preview_settings`/`tagging_settings`/`playback_settings`/`backup_settings` singletons. Job history is not included (24 h retention, [Job Model](./job-model.md#retention)).
- **Restore mode**: source-scoped tables are fully replaced and remapped to the *currently* active source id (a restore normally follows a source switch, which assigns a new source row for the same physical disk); global settings tables are upserted by id rather than wiped, so a restore never deletes a global entity (e.g. a conversion profile) the backup simply didn't know about.
- **`include_global=False`**: the flag source switching uses — restores only the source's own scoped data and leaves every global settings table (and the secrets file) untouched, so switching sources never changes app-wide settings. A failed auto-restore falls back to a fresh scan.
- **Backup id**: the id used by `GET /api/backups`, `POST /api/backups/restore`, and `DELETE /api/backups/{backup_id}` is the package filename without its `.zip` extension (`<timestamp>_<short-uuid>`), not the full `manifest.backup_id` UUID.
