# Video Archive Backup Format

## Overview

This document defines the expected contents and behavior of manual backups for Video Archive.

## Backup Scope

Backups primarily protect local metadata and local application configuration. They do not copy the full remote video source.

## Included Data

A backup should include:

- local metadata database content
- conversion profiles
- preview layout presets
- tag catalog
- provider configuration
- provider secrets when the user explicitly requested full settings export/import behavior
- application settings snapshot
- job history if retention policy includes it

## Excluded Data

A backup should not attempt to duplicate:

- the full remote video library
- arbitrary temporary conversion files unless explicitly needed
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

## Retention

- Backup retention count is configurable.
- Default retention count is `5`.

## Suggested Package Shape

Suggested package contents:

- metadata database dump or file copy
- settings export payload
- manifest file

Suggested manifest example:

```json
{
  "backup_id": "uuid",
  "created_at": "2026-07-05T12:00:00Z",
  "app_version": "0.1.0",
  "schema_version": 1,
  "includes_secrets": true
}
```
