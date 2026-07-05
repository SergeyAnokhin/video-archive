# Video Archive Backup Format

## Overview

This document defines the expected contents and behavior of manual backups for Video Archive.

## Backup Location

- Backups are stored **on the source disk itself**, in the technical folder at the source root: `.video-archive/backups/`.
- Each backup is one self-contained package (a folder or a zip archive) named by its creation timestamp and id.
- The technical folder is excluded from scanning and all processing workflows.
- Because backups live with the archive, they survive a local metadata wipe (for example a source switch) and travel with the archive if it is moved.

## Backup Scope

Backups primarily protect local metadata and local application configuration. They do not copy the video files themselves.

## Included Data

A backup should include:

- local metadata database content
- conversion profiles
- preview layout presets
- tag catalog (vocabulary)
- provider configuration
- provider secrets when the user explicitly requested full settings export/import behavior
- application settings snapshot
- job history if retention policy includes it

## Excluded Data

A backup should not attempt to duplicate:

- the video library itself
- preview collages (they already live next to the videos on the source)
- arbitrary temporary conversion files
- transient cache files that can be regenerated safely

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
