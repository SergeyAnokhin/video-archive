# Video Archive UI Screens

## Overview

This document defines the main screens, modals, and interaction surfaces for Video Archive. The UI is dark by default and should remain visually light, clear, and minimally cluttered.

## Global UX Rules

- Dark theme by default
- Prioritize browsing and quick actions over advanced tuning controls
- Move rare or advanced controls into settings, modals, or secondary panels
- Show warning or incomplete indicators, but hide success-only indicators
- Design mobile-first from the start, with vertical screens treated as a first-class layout target
- Keep one responsive UI that can later carry into a mobile app shell
- Use `lucide-react` icons in buttons by default; text-only buttons should be exceptions, not the rule
- For obvious actions, prefer icon-only buttons with accessible labels rather than repeating short text everywhere
- Keep the main library visually compact and low-clutter, with stronger or more playful visual modes as a skin rather than a layout fork
- Keep panel radii and spacing restrained; avoid oversized rounded capsules that make the browse view feel older or less dense
- Keep the top bar as a compact strip rather than a hero block; status, source, locale, theme, and settings should fit into one shallow header row, and active jobs should read primarily as a small spinner/badge on the jobs icon instead of a verbose queue block
- Prefer thumbnail-first file cards over dense metadata tables on the main library screen
- In file cards, show only the file preview, the short file name, and compact state indicators; move size, modified time, full path, and deeper metadata into details flows
- File state on the main screen should read as compact lamps or icon indicators, not repeated text pills
- Settings navigation should use stable-height items so section buttons do not visually jump when labels wrap or the active state changes

## 1. Main Library Screen

Purpose:

- browse folders
- browse files
- inspect recursive status
- launch common actions

Main regions:

- one combined browser grid that shows direct child folders first and files after them
- compact top bar with centered `Video Archive` brand and inline search
- compact icon-first action strip for the current folder/source scope
- current-folder block with a task picker for subtree actions
- compact current-folder title row with inline `Up one level` and `Library root` navigation when the user is below root
- locale switch
- visual-mode switch

Directory actions:

- convert recursively
- preview recursively
- tag recursively
- rescan recursively

File actions:

- open playback from a single click on the card itself
- open details from the compact info button on the card
- convert
- preview
- tag
- tune

Indicators:

- conversion indicator
- preview indicator

Indicators appear only for incomplete, running, or failed states.

Preview storage:

- file preview images should be written next to the source video with the same basename and a `.jpg` suffix
- directory collages can remain backend-managed secondary assets

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
- tune file
- move file
- delete file

Possible content:

- compact multi-row summary tiles for size, resolution, aspect ratio, and duration
- codec block for current media facts such as video codec, codec profile, bitrate, frame rate, pixel format, and audio codec when available
- last conversion profile block so the user can compare a small output against the recorded conversion settings
- generated-file marker when the current file was produced by tuning or test conversion
- metadata summary without promoting full absolute paths into the main layout
- preview collage
- assigned tags with confidence
- recent job history

Playback handoff:

- clicking the preview collage should reopen playback immediately
- embedded playback should prioritize the video canvas and keep auxiliary controls reduced to close and compact info entrypoints

## 3. Jobs Modal

Purpose:

- monitor and control jobs

Sections:

- queued jobs
- running jobs
- completed jobs
- failed jobs

Actions:

- cancel job
- restart job where supported
- remove job from visible list where supported

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

- sampled frame count
- large tile count
- layout preset picker
- timeline flow mode
- aspect ratio preset picker
- identity diversity toggle
- fill / clear layout actions
- save preset
- load preset

Live preview:

- shows layout geometry immediately
- may show representative frames or placeholders

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
- quality parameters
- drop audio toggle
- advanced encoder args

## 7. Tagging Settings Screen

Purpose:

- define tagging vocabulary and tagging behavior

Controls:

- allowed tag list
- sampled frame count
- top tag count
- frame combination preferences
- provider/model selection shortcuts where useful

## 8. Playback Settings Screen

Purpose:

- choose how videos open from the library

Modes:

- embedded modal playback
- external opening by path or link

## 9. Source Settings Screen

Purpose:

- configure the active remote source

Fields:

- protocol
- host
- port
- root path
- username
- password
- backend-local favorite folders for quick test setup

Actions:

- test connection
- save source
- reconnect
- jump to repo-local test archive when available

## 10. Provider Settings Screen

Purpose:

- configure OpenRouter, Gemini, FAL, and Mistral integrations

Provider-list behavior:

- add a new provider entry
- reorder entries to define fallback priority
- remove entries
- give each entry a user-visible label

Per-entry controls:

- provider type
- enabled flag
- API key
- vision model
- optional text model
- batch preferences if available
- load models from the provider when supported

## 11. Backup and Maintenance Screen

Purpose:

- protect and maintain local metadata

Backup controls:

- create backup
- restore backup
- list backups
- retention count

Maintenance controls:

- full rescan
- subtree rescan entry point or redirect
- stale record cleanup
- database optimize

## 12. Tuning Flow

Tuning should be initiated from a file, not from the main folder toolbar.

The tuning UI should support:

- explicit choice of one tuning parameter per run
- min/max/step controls for max-side sweeps when size is the selected axis
- min/max/step controls for CRF sweeps when quality is the selected axis
- codec selection when codec is the selected axis
- fixed companion settings for the non-swept parameters in the same run
- comparison of generated outputs
- generated outputs appearing beside the source file in the same folder with a visible generated marker
- promotion of a successful tuning result into a reusable conversion profile
