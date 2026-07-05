# Video Archive UI Screens

## Overview

This document defines the main screens, modals, and interaction surfaces for Video Archive. The UI is dark by default and should remain visually light, clear, and minimally cluttered.

## Global UX Rules

- Dark theme by default
- Prioritize browsing and quick actions over advanced tuning controls
- Move rare or advanced controls into settings, modals, or secondary panels
- Show incomplete indicators, but hide success-only indicators; running/failed activity is surfaced through the jobs UI, not per-file badges
- Small, icon-only buttons for global/secondary actions (jobs, settings, theme, language) grouped in the top bar, in the spirit of the reference screenshots in [Design System](./design-system.md)
- A compact activity indicator appears in the top bar whenever a job is queued or running: hover shows what the job is doing, click opens the jobs modal
- A compact, non-dominant search field sits at the edge of the toolbar (tag autocomplete + file names); it must not become a central element
- Two theme presets available (Strict default, Playful optional), switchable from the top bar without changing layout or navigation
- Two UI languages available (English, Russian), switchable from the top bar without a reload
- Layout must remain usable on mobile-sized viewports (see [Section 13](#13-responsive-behavior) and [Design System](./design-system.md))

## 1. Main Library Screen

Purpose:

- browse folders
- browse files
- inspect recursive status
- launch common actions

Main regions:

- directory tree
- current folder contents
- toolbar (with compact search field)
- optional preview visibility toggle

Directory actions:

- convert recursively (dialog with profile picker, test-mode checkbox, skip-processed toggle)
- preview recursively
- tag recursively
- rescan recursively

File actions:

- open details
- open playback
- convert
- preview
- tag
- compare variants (test-mode sweep)

Indicators:

- conversion indicator
- preview indicator

Indicators appear only for incomplete states; their meaning is explained on hover.

## 2. Video Details Modal

Purpose:

- inspect one video in detail
- view preview assets if available
- launch file-specific jobs

Actions:

- open playback
- convert file
- preview file
- tag file
- compare variants

Possible content:

- metadata summary
- preview collage
- assigned tags with relevance percentages
- recent job history

## 3. Jobs Modal

Purpose:

- monitor and control jobs

Opened from the top-bar activity indicator or its icon button.

Sections:

- queued jobs
- running job (only one at a time; see [Job Model](./job-model.md#concurrency-model))
- completed jobs
- failed jobs

Actions:

- cancel job
- restart job where supported
- remove a single job from the list
- clear all finished jobs with one button

Finished jobs disappear automatically after 24 hours.

## 4. Log Viewer

Purpose:

- inspect near-real-time backend activity from the UI

Features:

- streaming updates
- filtering by job
- filtering by file
- filtering by level

The log viewer complements backend console logs rather than replacing them.

## 5. Preview Settings Screen

Purpose:

- configure preview generation behavior
- preview layouts before running full jobs

Controls:

- grid dimensions
- construction-set layout editor: paint cells with two tile brushes (small / enlarged 2×2 or 3×3), quick brush switching
- built-in preset gallery (varied large/small tile arrangements, selectable at a click)
- Fill all / Clear all actions
- quick save/load slots (for example 3) for custom layouts
- timeline flow mode
- identity diversity toggle
- folder-preview frame count
- save preset / load preset (named presets)

Live preview:

- shows layout geometry immediately on the black collage background
- may show representative frames or placeholders
- includes the file-name caption placement

## 6. Conversion Profiles Screen

Purpose:

- manage reusable conversion profiles

Actions:

- create profile
- edit profile
- duplicate profile
- delete profile
- mark default profile

Fields:

- codec
- container
- maximum dimension
- CRF quality value
- drop audio toggle (default on)
- advanced encoder args

## 7. Tagging Settings Screen

Purpose:

- manage the tag vocabulary and tagging behavior

Controls:

- tag vocabulary editor (add, rename, deactivate, delete tags)
- sampled frame count
- top tag count
- frame combination preferences
- provider/model selection shortcuts where useful

## 8. Playback Settings Screen

Purpose:

- choose how videos open from the library

Modes:

- embedded modal playback (backend stream with Range support)
- external opening by path or link

## 9. Source Settings Screen

Purpose:

- configure the active source (a local directory next to the backend, or an SMB share)

Fields:

- protocol (`local | smb`; `webdav` optional later)
- host (protocol sources only)
- port (protocol sources only)
- root path (remote base directory, or local path for `local`)
- username (protocol sources only)
- password (protocol sources only)

Actions:

- test connection (protocol sources only)
- save source
- reconnect (protocol sources only)

Flows:

- replacing the source shows a destructive-change warning: all library metadata will be wiped
- after connecting a source that contains backups in `.video-archive/backups/`, the UI offers to restore one

## 10. Provider Settings Screen

Purpose:

- configure OpenRouter, Gemini, FAL, and Mistral integrations

Per-provider controls:

- enabled flag
- API key (stored in the local secrets file)
- vision model
- optional text model
- batch preferences if available

## 11. Backup and Maintenance Screen

Purpose:

- protect and maintain local metadata

Backup controls:

- create backup (into the source's `.video-archive/backups/` folder)
- restore backup
- list backups
- retention count

Maintenance controls:

- full rescan
- subtree rescan entry point or redirect
- stale record cleanup
- database optimize

## 12. Variant Comparison Flow

Variant comparison (former "tuning") is initiated from a file, not from the main folder toolbar. It is a test-mode conversion producing several outputs for one video (see [Specification Section 8.3](./specification.md#83-variant-comparison)).

The UI should support:

- picking sweep values over maximum dimension
- picking sweep values over CRF quality
- picking codec variants
- comparing generated outputs (they appear next to the original as `<name>.<variant>.mp4`)
- promoting a successful variant into a reusable conversion profile

## 13. Responsive Behavior

Purpose:

- keep the same screen and interaction structure usable from desktop down to mobile widths

Rules:

- on narrow viewports, the directory tree collapses into a drawer or menu instead of a persistent side panel
- the card/file grid reflows to fewer columns, down to a single column on the smallest widths
- secondary global icon buttons (jobs, settings, theme, language) may collapse into an overflow menu on narrow widths; the compact search field stays reachable
- modals (jobs, video details, settings) become full-screen sheets on mobile widths instead of centered dialogs

See [Design System](./design-system.md) for breakpoints and detailed visual rules.
