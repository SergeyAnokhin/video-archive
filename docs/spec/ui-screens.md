# Video Archive UI Screens

## Overview

This document defines the main screens, modals, and interaction surfaces for Video Archive. The UI is dark by default and should remain visually light, clear, and minimally cluttered.

## Global UX Rules

- Dark theme by default; eight presets (see [Design System](./design-system.md))
- Prioritize browsing and quick actions over advanced tuning controls
- Move rare or advanced controls into settings, modals, or secondary panels
- Show incomplete indicators, but hide success-only indicators; running/failed activity is surfaced through the jobs UI, not per-file badges
- Small, icon-only buttons for global/secondary actions grouped in the top bar: menu (directory tree), Jobs, preview-style toggle (eye), theme cycle, Settings
- A compact activity indicator appears in the top bar whenever a job is queued or running: hover shows what the job is doing, click opens the jobs modal
- The scoped search box sits in the top bar center (`tag:` / `file:` / `path:` prefixes with Russian aliases, or all groups at once)
- Two UI languages (English, Russian), switchable from Settings without a reload
- Layout must remain usable on mobile-sized viewports (see [Section 14](#14-responsive-behavior))

## 1. Main Library Screen

Purpose: browse folders and files, inspect recursive status, launch common actions.

Main regions:

- collapsible directory-tree pane (closed by default at every width; overlay drawer on mobile) with a name filter, expand/collapse-all, per-folder status dots and top-tag dots
- current folder contents as a card grid
- toolbar: breadcrumb, "Recent folders" quick-jump menu (folders where a video was played or a file was moved — not plain browsing — rendered as clickable path crumbs), create-folder, sort-cycle (name / size / tags), rescan, and convert/preview/tag folder actions (overflow menu on narrow widths)

Folder cards: animated `folder-preview.gif` thumbnail, status dots, aggregate size/tag counts, dynamic top-tags row (colored badges), favorite star, delete (empty folders only).

File cards: animated GIF thumbnail (JPEG fallback) for videos — click to play; the image itself for standalone images — click to view; duration badge; status dots (conversion/preview video-only); variant/original markers with swept-parameter captions; up to 4 colored AI-tag badges; an "i" overlay button opening the file info panel — deliberately the only other direct action on a card.

Live behavior: while a job runs, a file's card refreshes as soon as that file's job item completes (not only at job end), with no loading flash.

## 2. Search Results

- An unscoped query shows up to three capped groups (tags / files / folders), each with a "search only in this group" shortcut.
- A scoped query shows one flat infinite-scroll grid.
- Sorting matches the library view; prev/next navigation in playback/viewer/info panel follows the on-screen result order while a search is active.

## 3. File Info Panel

Near-fullscreen per-file panel (evolved from the V1 "video details modal"):

- left: the static JPEG collage (or the image itself); right: details — status pills, tuning-parameter chips, editable AI-tags section (colored badges, per-tag remove, free-text add with a colored suggestion row: recently-added-manually first, then popular), "detected by" model line, a user-defined-tag picker button, and an ffprobe-backed media-info grid
- the collage/details split is a draggable divider (pointer + arrow keys), persisted; hidden on mobile where the layout stacks
- one plain button per action: preview / convert / tune (videos only), tag (opens Tag Lab), similar, move, delete
- optional prev/next navigation (buttons + arrow keys)
- favorite-folder quick-move buttons and a recent-folders History popover

## 4. Playback Overlay and Image Viewer

Playback (videos):

- full-viewport HTML5 player against the backend stream, or — in `direct_link` mode — a copyable local/UNC path plus a raw-stream link
- mode-switch and close float over the video; Escape/backdrop closes
- prev/next chevrons + arrow keys (capture-phase, so the player's own shortcuts don't swallow them)
- bottom quick-actions: open-info (jumps into the file info panel), quick tag-add (floating, suggestion badges with a confirmation pulse), user-defined-tag picker — opening one closes the other

Image viewer (standalone images): same overlay pattern, navigation, and quick-actions, with an `<img>` instead of playback controls.

## 5. Tag Lab Modal

The single-file AI-tagging workbench ([Specification §12.4](./specification.md#124-tag-lab)):

- provider-entry picker showing per-model quality stats (like ratio, apply KPI) and the selected model's $/1M price before running
- on run: the images being sent and the prompt render immediately; the model's raw reply text and the full raw provider JSON are inspectable in collapsed sections (also on failures); token/cost usage line with an inline-editable price
- suggested tags seed an editable list (colored badges): remove any, add via free text + suggestions; model-sourced tags carry like/dislike buttons
- Apply writes the final list; Cancel discards — nothing is written until Apply
- both calls run under a client-side timeout ceiling so the modal can never wait forever

## 6. Jobs Modal

- status-grouped **cards** in a responsive grid (evolved from the V1 list)
- running/paused cards: progress bar, current item, elapsed time, rolling-window ETA; failed-item count highlighted on any card
- per-card actions: cancel (second cancel force-finishes), pause/resume (pausable types only), restart, remove, view-log (opens the log viewer pre-filtered to the job)
- clear-all-finished button; finished jobs disappear automatically after 24 hours
- header button opens the **batch submissions** modal: still-polling provider-side batch-tagging submissions with a per-row "forget locally" action

## 7. Log Viewer

- streaming updates (SSE) plus backfill, capped buffer
- filters by job, file, and level, with a clear-filters action; clickable per-file `#N` badges toggle the file filter
- elapsed `MM:SS` timestamps; copy-all button
- complements backend console/file logs rather than replacing them

## 8. Settings Modal

One tabbed modal (icon sidebar on desktop, icon strip + full-screen sheet on mobile). Tabs:

| Tab | Contents |
| --- | --- |
| Source | Connection form (local/SMB, test-connection, reconnect, restore offer) + saved-sources list (activate, preview-cache stats/clear, forget) |
| Conversion profiles | Profile CRUD, duplicate, mark default |
| Preview | Collage sub-tab (aspect ratio, construction-set grid editor, preset gallery, save/load slots) + Animated sub-tab (frame count, GIF size/colors, frame/clip mode, transition) |
| Playback | `stream` / `direct_link` selector |
| Tagging | AI vocabulary chip editor, user-defined tags section, sampling/collage/resolution/top-N/timeout fields, "preview what the model sees" |
| Providers | Priority-ordered entry list (reorder, inline edit, advanced per-row panel), model pricing table + OpenRouter refresh, usage table, export/import |
| Backup | Backup list/create/restore/delete, retention, maintenance triggers (rescan, cleanup, optimize) |
| Performance | `parallel_workers` |
| Network | LAN address list with copy buttons and setup instructions |
| Interface | Language, 8-theme picker, two preview-stylization profile editors with live samples, search limits |

The preview layout editor works as a construction set: paint cells with small/enlarged tile brushes, fill/clear all, built-in preset gallery, quick save/load slots, live black-canvas preview at the configured aspect ratio (tile geometry validated by the backend).

## 9. Variant Comparison ("Tuning") Flow

Initiated from a file, not the folder toolbar. A test-mode conversion producing several outputs for one video:

- pick a sweep axis: maximum dimension (preset checkboxes), CRF (min/max/step range), or codec
- outputs appear next to the original as `<name>.variant-<params>.mp4`, each auto-tagged with its swept parameters and borrowing the original's preview in listings
- per-result "save as profile" promotes a winner into a conversion profile

## 10. Move and Folder Dialogs

- **Move dialog**: lazily-expanding folder tree from the source root, "Move here".
- **Quick-move controls** (playback/info panel): one button per favorite folder (drilling into subfolders via a compact popover) plus a recent-folders History popover.
- **Create folder dialog**: name input with collision/invalid-name feedback.

## 11. Directory Action Dialogs

- Convert: profile picker, production/test radio, skip-processed toggle.
- Preview and Tag: skip-processed toggle only.
- All directory actions apply recursively.

## 12. Backend Status Panel

Shown in the empty state while no source is connected: health and app info (version, DB, ffmpeg availability).

## 13. Top-Bar Summary

Left to right: menu toggle, title, scoped search box, activity indicator (when a job is active), Jobs, preview-style eye toggle, theme cycle, Settings.

## 14. Responsive Behavior

- on narrow viewports the directory tree becomes an overlay drawer; the card grid reflows down to a single column
- toolbar folder actions collapse into an overflow menu; the search box stays reachable
- modals (jobs, settings, info panel) become full-screen sheets on mobile widths
- touch targets stay at least 40×40 logical pixels

See [Design System](./design-system.md) for breakpoints and detailed visual rules.
