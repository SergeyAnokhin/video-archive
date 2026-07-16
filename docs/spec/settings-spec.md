# Video Archive Settings Specification

## Overview

This document defines the settings structure for Video Archive. Settings are divided into user-editable groups stored in the local database (mostly single-row "singleton" tables) and secrets stored in a local `.env`-style file (see [Tech Stack](./tech-stack.md)). All settings changes apply immediately, without a page reload.

## Settings Areas

Matching the tabs of the settings modal:

- source (connection form + saved sources)
- conversion profiles
- preview (collage + animated preview)
- playback
- tagging (AI vocabulary, user-defined tags, sampling, resolution, timeout)
- AI providers (entries, pricing, usage, ratings)
- backup and maintenance
- performance
- network access
- interface

## 1. Source Settings

Connection form fields:

- source name
- protocol (`local | smb`; `webdav` reserved)
- host / port / remote path / username / password (SMB only; remote path is `share[/subpath]`)
- local path (local source only), absolute or relative to the backend working directory

Saved-sources list (post-V1): every source ever connected stays saved; per row —

- active badge
- local preview-cache size and file count, with a clear-cache action (for the active source, clearing also resets has-preview facts so the next preview run regenerates)
- switch-to action (activate)
- forget action (disabled for the active source; removes the saved row, its credentials, and its preview cache — never touches the source's disk)

Rules:

- Only one active source at a time.
- Username and password are written to the secrets file **per source**; the database keeps only key references.
- A `local` source does not require authentication and is not subject to reconnect/network-refresh behavior.
- Switching sources is non-destructive: the outgoing source is backed up onto its own disk and the incoming source's backup is auto-restored (see [Specification Section 5.2](./specification.md#52-source-switching)). The UI still confirms the switch.

## 2. Conversion Profile Settings

Each saved profile should expose:

- name
- codec (default `h265`)
- container (default `mp4`)
- maximum dimension (empty = never resize)
- CRF quality value (default `26`; lower = better quality/larger file; practical range 22–32)
- drop audio toggle (default **on** — audio is not needed in this archive)
- advanced encoder parameters

The settings UI should allow: create, edit, duplicate, delete, mark recommended default profile.

Job-level defaults (shown in conversion dialogs, not stored per profile):

- skip already-converted files: default **on**
- test mode (preserve originals): default **off**

## 3. Preview Settings

Two sub-tabs.

**Collage** (the static JPEG written next to the video):

- grid dimensions (rows × columns)
- collage aspect ratio: `standard` (4:3), `phone-portrait` (9:19.5), `phone-landscape` (19.5:9, **default**), `ultra-wide` (21:9), or custom — independent of grid dimensions
- enlarged tile count, sizes (2×2 or 3×3 spans), and placement (grid must stay fully covered) via the construction-set editor
- layout preset (built-in gallery + user presets + quick save/load slots)
- timeline flow mode (`row | column | shuffle`)
- identity diversity toggle (default **on**)
- live preview; fill/clear layout actions

**Animated preview** (the GIF thumbnails, stored in the local cache):

- folder-preview frame count (default `4`)
- GIF max width (default `640` px) and color count (default `64`)
- source mode: `frame` (stills) or `clip` (short segments, with segment duration)
- transition: `cut` or `crossfade`

Collage appearance is fixed (not settings): black background, thin gaps between tiles, file-name caption inside the collage (see [Specification Section 9.2.1](./specification.md#921-collage-appearance)).

## 4. Playback Settings

- playback mode (`stream | direct_link`)
- `stream`: embedded modal playback (backend streaming proxy with Range support)
- `direct_link`: copyable direct file path / UNC link plus a raw-stream browser link

Both strategies must remain available and switchable at any time (also from within the playback overlay itself).

## 5. Tagging Settings

- **AI vocabulary management**: add, rename, activate/deactivate, delete, and recolor tags (chip editor). This pool is the closed set the AI scores against; the model does not invent tags.
- **User-defined tags** (own section): the purely subjective pool, never AI-scored; same chip editor, feeding the per-file user-defined-tag picker.
- sampled frame count (default `9`)
- whether to combine sampled frames into one collage image for classification (default **on**, 3×3)
- image resolution — pixel size of a single frame sent to the provider (collage cell side / per-frame longest side), shared by both modes
- top tag count to store per file (default `10`)
- request timeout in seconds for Tag Lab's direct provider calls (default `30`)
- a "preview what the model sees" action rendering the current (possibly unsaved) sampling settings against a recently viewed video into the real output images

Behavior notes:

- Results are relevance scores 0–100 per tag, shown as percentages; only the top-N are stored.
- Tags from every pool feed search autocomplete and per-file add-tag suggestions; only the AI vocabulary is ever sent to a provider.

## 6. AI Provider Settings

Provider configuration is a priority-ordered list of **entries** — any number per provider type (`openrouter`, `gemini`, `fal`, `mistral`). Each entry:

- enabled flag
- API key (stored in the secrets file; UI shows only presence + masked suffix)
- vision model, with a model-catalog lookup where available (`fal` has no catalog API; a curated list of compatible vision endpoints is offered instead)
- optional text model
- batch preference (Gemini/Mistral only)
- per-model price override fields (inline, same data as the pricing table)

List-level controls: reorder (priority = fallback order for background tagging), add, edit inline, delete.

Additional sections on the same tab:

- **Model pricing table**: editable $/1M-token input/output prices keyed by `(provider_type, model_name)`, with a "refresh from OpenRouter" action for OpenRouter models (other providers are manual-only).
- **Usage table**: per-(provider, model) request/token/cost summary from the usage log.
- **Export / import**: JSON export of all entries **including plaintext API keys** (behind an explicit confirmation), and import of the same shape (unknown provider types are skipped and counted, not fatal).

## 7. Backup and Maintenance Settings

Backup controls:

- create backup (with an include-secrets checkbox), into the active source's `.video-archive/backups/`
- list / restore / delete backups
- retention count (default `5`)

Maintenance actions:

- full rescan
- stale record cleanup
- local database optimize/compact

## 8. Performance Settings

- `parallel_workers` (default `4`, clamped 1–16) — the per-job bound on parallel file processing for conversion and preview jobs, read once at job launch.

## 9. Network Access

Read-only helper page (post-V1): lists `http://<lan-ip>:<port>` for every detected local IPv4 address, with copy buttons, a manual refresh, and static instructions for LAN/hotspot/firewall setup. Backed by a backend network-info endpoint; frontend and backend bind to `0.0.0.0` so other devices on the network can connect.

## 10. Interface Settings

- UI language (`en | ru`)
- theme preset — one of eight (`strict` default; see [Design System](./design-system.md#2-theme-presets))
- two **preview stylization profiles** (A/B): per-profile saturation, blur, brightness, contrast, sepia, hue-rotate sliders with live sample thumbnails and per-field reset; the top-bar eye button switches the active profile
- search limits: per-group caps (tags / files / folders) for unscoped search suggestions and results

Default expectations:

- default UI language matches the browser/OS locale when recognized, falling back to English
- default theme preset is `strict`

Rules:

- Interface settings changes apply immediately, without a page reload.
- Interface settings are persisted the same way as other settings groups (and mirrored to `localStorage` for a flash-free first paint).

## Export and Import

Provider configuration export/import is explicit and key-inclusive (see [Section 6](#6-ai-provider-settings)). Library metadata and settings travel via backups instead ([Backup Format](./backup-format.md)); import validation covers structure, profile definitions, preview payloads, provider entries, and the tag catalog.
