# Video Archive Technical Specification

## 1. Overview

Video Archive is a web application for working with a video directory source. The system consists of a React + TypeScript frontend and a Python (FastAPI) backend. The application keeps any number of *saved* sources (local directories or SMB shares), exactly one of which is active at a time; it shows the active source's folder structure, runs video conversion jobs, generates preview collages and animated previews, and assigns tags to videos and standalone images through external AI providers.

The product is centered on three independent processing workflows:

- video conversion
- preview generation
- AI tagging

These workflows must remain separate job types and must not be implicitly coupled.

The concrete technology choices (frameworks, libraries, external tools) are fixed in [Tech Stack](./tech-stack.md). The implementation order is fixed in [Roadmap](./roadmap.md).

## 2. Product Goals

- Connect to a source directory (local directory or SMB share); keep multiple saved sources and switch between them without losing their metadata.
- Show the directory tree and navigate nested folders.
- Convert videos in bulk using saved conversion profiles.
- Replace original files after successful conversion.
- Support a safe test mode that preserves the original source file.
- Generate preview collages stored next to the video files themselves, plus lightweight animated previews for browsing.
- Assign tags to videos and standalone images from a user-defined tag vocabulary, with relevance scores; support fast manual tagging as well.
- Treat standalone images as first-class library items (viewing, tagging, similarity) while keeping conversion and preview generation video-only.
- Cache processing metadata locally to avoid repeated expensive work.
- Be reachable from other devices on the local network (phone, tablet) as well as from the development machine.

## 3. Out of Scope

- Multi-user collaboration and authentication
- Advanced streaming-specific subsystems
- Free-form AI scene search across all video content
- Native mobile applications (dedicated iOS/Android app)
- FTP and SFTP source protocols
- WebDAV source protocol (optional, may be added after SMB works)

Responsive behavior of the web UI on mobile-sized viewports is in scope; see [Section 11.11](#1111-responsive-and-mobile-support). Lightweight media-library conveniences originally deferred from V1 have since been added where they earn their keep (folder favorites, recently-played history for navigation, per-model quality ratings for tagging).

## 4. System Scope

### 4.1 Frontend

- React + TypeScript web application (Vite)
- Directory tree and file browser (videos and standalone images)
- Job management screens and a top-bar activity indicator
- Settings screens
- Preview settings page with live preview
- Log viewer
- Per-file info panel, playback overlay, and image viewer
- Tag Lab — a synchronous single-file AI-tagging workbench
- Compact scoped search field (`tag:` / `file:` / `path:`)

### 4.2 Backend

- Python FastAPI service
- Source access layer (local filesystem and SMB)
- Scan and metadata layer
- Job queue (two-lane worker: one CPU-bound job plus one network-bound tagging job at a time)
- Local processing workers
- Local SQLite database
- Local per-source preview cache (animated GIF assets)
- External AI provider integration

### 4.3 Execution Model

- Local jobs run on the same machine as the backend.
- External LLM and vision-model requests are sent to configured providers.
- Conversion, preview, and tagging are separate job types.
- The worker has two lanes: a CPU lane (scan, conversion, preview, maintenance, backup/restore — one at a time, since they compete for local ffmpeg/disk) and a network lane (tagging — bounded by the provider, not the CPU). At most one CPU job and one tagging job run concurrently.
- Within a CPU job, files may be processed in parallel up to the configurable `parallel_workers` performance setting (default 4). ffmpeg's own internal multithreading for a single file is also allowed.

### 4.4 Local Development and Startup

- The first implementation target is local development on Windows.
- The project should be runnable from a terminal.
- The repository root provides an `npm`-based entrypoint that starts frontend and backend together.
- Frontend and backend should also remain independently runnable from their own directories.
- The root-level startup flow should be the default developer entrypoint for local work.

## 5. Source Model

- The application keeps any number of **saved sources**; exactly one is **active** at a time.
- All library metadata (directories, files, tags, job history) always describes the active source only.
- Supported source types:
  - Local (a directory on the backend's own filesystem, for example a `library` folder placed next to the backend; primary mode for development)
  - SMB (primary remote protocol)
  - WebDAV (optional, only after SMB is complete)
- A remote source configuration includes:
  - protocol
  - host
  - remote path
  - authentication details (stored in the local secrets file, see [Section 18](#18-ai-provider-settings-and-secrets))
  - optional protocol-specific parameters such as port
- A local source configuration includes:
  - source name
  - local path, given as an absolute path or as a path relative to the backend working directory
- Local sources do not require authentication and are not subject to reconnect/network-refresh behavior; a rescan is sufficient to detect changes.
- The backend must support reconnect and refresh behavior for the active remote source.

### 5.1 Path Model

- The source root is stored once, in the source configuration.
- All file and directory records store paths **relative to the source root**.
- If the archive is moved (the source root changes), only the source configuration is updated; all file records remain valid.
- Absolute paths are always computed at runtime as `source_root + relative_path` and are never persisted per file.

### 5.2 Source Switching

Switching the active source is no longer a destructive wipe (post-V1 improvement). The activation flow, shared by "connect a new source" and "activate a saved source":

1. The outgoing source is backed up onto **its own** disk (`.video-archive/backups/`), so its metadata can come back when it is activated again.
2. Local source-scoped metadata (directories, files, file tags, job history) is wiped; global settings tables (profiles, tag catalog, provider entries, layout presets) are never touched by a switch.
3. The incoming source is activated. If its technical folder contains a backup of its own, the newest one is restored automatically (scoped data only).
4. A synchronous scan reconciles any drift on disk since that backup.

The UI still confirms the switch, and the Settings source form additionally offers restoring a detected backup explicitly when connecting a brand-new source. Saved sources can also be *forgotten* (removing the saved row, credentials, and the local preview cache — never touching the source's disk).

### 5.3 Technical Folder

- The application maintains a technical folder at the source root: `.video-archive/`.
- It holds backups (`.video-archive/backups/`) and may hold other maintenance artifacts later.
- The technical folder and its contents are excluded from scanning and all processing workflows.

## 6. Core Workflows

### 6.1 Scan

- The backend scans the connected directory tree.
- Scan discovers files and folders and refreshes metadata.
- Scan is lightweight and does not require a dedicated persistent UI status indicator.
- Scan must detect:
  - newly appeared files
  - removed files
  - changed file metadata relevant to processing
  - presence of preview assets (see [Section 9.5](#95-preview-storage))
- Scan classifies each file independently as a supported video and/or a supported standalone image (disjoint extension sets); a JPEG whose base name matches a video in the same folder is that video's preview asset, never an independent library item.
- A moved or renamed file is treated as a removed file plus a new file. Preserving history across moves is intentionally out of scope for V1.

### 6.2 Conversion

- User selects a folder or files and chooses a conversion profile.
- Folder-level actions always apply to the selected folder and all nested subfolders.
- Backend converts all supported video files in the selected scope.
- In production mode, the original file is replaced only after successful validation of the converted output.
- In test mode, the converted output is produced the same way, but the original file is preserved (see [Section 8.2](#82-test-mode)).
- **Skip-processed rule:** by default, files already marked as converted are skipped. The user can disable this per job to force reconversion of everything in scope (for example, to reconvert at a different resolution or quality).

### 6.3 Preview Generation

- Preview generation is a separate on-demand workflow.
- It must not run automatically after conversion.
- It can be run for:
  - one video
  - multiple videos
  - a folder
- Folder-level preview generation always applies to the selected folder and all nested subfolders.
- By default, files that already have a preview asset are skipped; the user can disable this per job to regenerate.

### 6.4 Tagging

- Tagging is a separate on-demand workflow.
- It must not be required for conversion or preview completion.
- Tags are matched against the user-defined AI vocabulary (see [Section 12](#12-tagging)).
- Folder-level tagging always applies to the selected folder and all nested subfolders, and covers both videos and standalone images.
- By default, files that already have tags are skipped; the user can disable this per job to re-tag.
- Single-file AI tagging goes through **Tag Lab** instead of a background job: a synchronous, review-first flow against one user-picked provider entry (see [Section 12.4](#124-tag-lab)).

### 6.5 Rescan

- Rescan can be run for the connected source and for a selected folder subtree.
- Folder-level rescan always applies to the selected folder and all nested subfolders.

## 7. Conversion Profiles

A conversion profile is a saved set of video conversion parameters.

Each profile may define:

- target codec
- maximum output dimension
- quality (CRF) value
- audio removal behavior

Profile rules:

- Default codec for V1: `H.265` (libx265)
- Default output container for V1: `MP4`
- Resizing is applied only when the source video exceeds the configured maximum dimension.
- Maximum dimension means the largest side of the output must not exceed the configured limit.
- Audio is dropped by default (`drop_audio = true`). Audio is not needed for this archive; keeping it is an explicit opt-out per profile.
- The application must support multiple saved profiles.
- The application must support test generation across multiple profile variants (see [Section 8.3](#83-variant-comparison)).

### 7.1 Quality Model (CRF)

Quality is controlled through CRF (Constant Rate Factor), the standard quality knob for x265:

- Lower CRF = better quality and larger file; higher CRF = smaller file and lower quality.
- Practical x265 range for this project: **CRF 22 (high quality) to 32 (aggressive compression)**; default: **CRF 26**.
- CRF is preferred over fixed bitrate because it keeps perceived quality constant regardless of content complexity.
- The variant-comparison workflow ([Section 8.3](#83-variant-comparison)) exists precisely to let the user find the highest CRF (smallest files) that still looks acceptable to them.

## 8. Safe File Replacement and Test Mode

### 8.1 Production Mode

The system must use a safe replacement workflow for converted files.

Required sequence:

1. Write converted output to a temporary file.
2. Run a fast validation pass on that temporary file.
3. Replace the source only if validation succeeds.
4. Keep the original file untouched if validation fails.

Validation requirements:

- output file exists
- output file size is non-zero
- output file is recognized as a valid media file (ffprobe)
- output exposes expected video metadata
- output matches the expected container and codec combination

Validation must be lightweight and should avoid full decode playback unless later evidence shows it is necessary.

Temporary output may be created:

- locally
- near the remote source

The implementation may choose either strategy based on protocol constraints and safety.

### 8.2 Test Mode

Test mode is a per-job checkbox available for both folder-level and file-level conversion. It runs the exact same pipeline (temp output, validation) with one difference: **the original file is never deleted.**

Rules:

- The converted output takes the standard converted name (`<basename>.mp4`).
- The original is **always** renamed to `<basename>.original.<ext>` — even when the extensions differ and there is no name collision. This keeps preserved originals uniformly recognizable.
- Preserved originals are visible in the browser like any file, but files whose name contains the `.original.` marker are **excluded from bulk workflows** (folder-level convert/preview/tag) so a later bulk run does not reconvert the very originals kept for comparison. They can still be processed individually on explicit user action, and the user deletes them manually when satisfied.
- Test mode exists so the user can trust a first run on real data: if something goes wrong, nothing has been lost.

### 8.3 Variant Comparison

Variant comparison (formerly "tuning") is a file-level test-mode conversion that produces several outputs for one source video so the user can compare quality against file size.

- Initiated from a specific video, not from a bulk folder operation.
- Always test mode semantics: the source video is never replaced or deleted.
- Each variant output is named `<basename>.variant-<params>.mp4`, where `<params>` encodes the parameters (for example `movie.variant-d1000-crf28.mp4`); the explicit `variant-` marker lets the scanner recognize these files reliably. Like `.original.` files, variant outputs are excluded from bulk workflows and are meant for manual review and cleanup.
- Supported sweep axes:
  - maximum output dimension (for example 1000, 900, 800)
  - CRF values (for example 24, 26, 28, 30)
  - codec choices
- The user reviews the results in the file browser and can promote a winning parameter set into a saved conversion profile.

## 9. Preview Generation

### 9.1 General Rules

- Preview generation produces two assets per video (post-V1 evolution):
  - a **JPEG collage** from sampled frames, stored next to the video and shown in the per-file info panel (static view);
  - an **animated GIF** used as the grid/list thumbnail, stored in a local per-source cache — never written to the source.
- Folder previews are animated GIFs only (`folder-preview.gif`), cycling frames sampled from different videos and subfolders of the subtree for visual variety (default frame budget: 4).
- A small, always-visible icon button in the top bar (grouped with the jobs/theme/settings buttons) instantly switches between two client-side preview **stylization profiles** (see [Section 9.6](#96-animated-previews-and-stylization)). Switching is purely client-side: no backend call, nothing deleted or regenerated, no page reload.

### 9.2 Collage Grid Layout

- A video preview collage is a fully filled rectangular grid of frame tiles (rows × columns).
- Some tiles are enlarged: an enlarged tile spans 2×2 or 3×3 grid cells and replaces the small tiles it covers.
- The grid must always remain completely filled — enlarged tiles and small tiles together cover every cell exactly once.
- The number of sampled frames is therefore derived from the layout: total cells minus cells absorbed by enlarged tiles.
- Grid dimensions, the number of enlarged tiles, their sizes (2× or 3×), and their placement are configurable (see [Section 10](#10-preview-settings-page)).
- The application ships with a built-in gallery of layout presets mixing large and small tiles in varied arrangements (large tiles at a corner, along an edge, centered, and so on), modeled on the reference screenshot shared for this project; the user picks a preset or edits a custom layout.
- The overall collage canvas aspect ratio is configurable independently of grid dimensions: presets include `standard` (4:3), `phone-portrait` (9:19.5), `phone-landscape` (19.5:9 — the **default**, chosen because it fills a mobile card's width without letterboxing), `ultra-wide` (21:9), and a custom ratio option (see [Section 10](#10-preview-settings-page)).

### 9.2.1 Collage Appearance

- The collage background is **black**.
- Tiles occupy almost the entire collage area: gaps between tiles and outer margins are thin (a few pixels), just enough to separate frames visually.
- The collage includes a caption with the **name of the source file** it was generated from, rendered on the black background (a slim caption bar above or below the tile grid).
- A folder preview follows the same rules and uses the folder name as its caption.

Enlarged tile content priority:

- the first two enlarged tiles should prefer face-detected frames
- remaining enlarged tiles should prefer human figure or pose detections
- If identity diversity is enabled, the system should try to use two different faces for the first two enlarged tiles.
- If identity diversity is disabled, unavailable, or too expensive for the current environment, it is acceptable to use two face-detected frames from different timeline regions.

### 9.3 Detection Rules

- Face detection must run locally using Python libraries (see [Tech Stack](./tech-stack.md) for the chosen models; they must stay lightweight enough for a modest CPU and limited RAM).
- Body or pose detection must also run locally when needed.
- Preferred frames should maximize:
  - face visibility
  - face size within frame
  - human figure size within frame
  - detection confidence
  - low blur

### 9.4 Sampling Rules

- Frame selection should prefer even coverage across the interior of the video.
- The beginning and end of the video should be avoided by default.
- For `N` sampled frames, the default strategy is:
  - divide the timeline into `N + 1` segments
  - choose frames from the interior points rather than the outermost edges
- This evenly spaced interior strategy should be reused across preview generation, tagging, and related analysis unless a workflow defines a better specialized rule.

### 9.5 Preview Storage

Static collages live on the source; animated previews live in a local cache:

- **JPEG collage:** stored in the same folder as the video, with the same base name: `movie.mp4` → `movie.jpg`. Because it lives next to the video, it moves together with the archive and needs no separate asset database.
- **Animated GIF (file and folder):** stored in a local per-source cache next to the backend (`backend/preview_cache/<source_id>/`, flattened collision-free names) and **never written to the source** — GIFs are bulkier, lower-fidelity browsing aids, not archive artifacts. The cache can be inspected (size/count per saved source) and cleared from Settings; clearing the active source's cache resets the has-preview facts so the next preview run regenerates.
- Scan detects on-source collages and records preview presence per file; a JPEG whose base name matches a video in the same folder is treated as that video's preview asset, not as an independent library item.
- Collage output defaults: JPEG quality 85, width 2048 px.

### 9.6 Animated Previews and Stylization

Animated previews (post-V1, user-requested) have their own settings, separate from collage layout:

- **Source mode:** `frame` (one still per sampled position) or `clip` (a short real-video segment per position, `animated_segment_seconds` long).
- **Transition:** `cut` or `crossfade` between positions.
- **Size/quality:** `gif_max_width` (default 640 px) and `gif_colors` (default 64) — deliberately lower-fidelity than the JPEG collage, since GIFs are only ever shown as small grid/list thumbnails and must load fast.
- **Stylization profiles:** two client-side profiles (A/B) of CSS-filter adjustments (saturation, blur, brightness, contrast, sepia, hue-rotate) applied to all preview thumbnails at render time; the top-bar eye button switches the active profile instantly. Profiles are edited in interface settings with live sample thumbnails and per-field reset.

## 10. Preview Settings Page

The application must provide a dedicated preview settings page.

The page has two sub-tabs: **Collage** (grid layout) and **Animated preview** (GIF behavior, see [Section 9.6](#96-animated-previews-and-stylization)).

The Collage tab must support:

- configuring the grid dimensions
- configuring the overall collage aspect ratio (standard, phone-portrait, phone-landscape, ultra-wide, or custom — see [Section 9.2](#92-collage-grid-layout))
- configuring how many enlarged tiles are used and their size (2×2 or 3×3)
- choosing from the built-in gallery of layout presets
- configuring timeline flow strategy
- enabling or disabling identity diversity attempts (enabled by default)
- previewing the resulting layout live before running a full preview job

The Animated preview tab must support:

- configuring the folder-preview frame count (default: 4)
- configuring GIF width and color count
- choosing the animated source mode (`frame` / `clip`), segment duration, and transition (`cut` / `crossfade`)

Layout editing works as a "construction set", modeled on the reference screenshot:

- a grid editor where the user paints tiles onto cells
- two tile brushes — small tile and enlarged tile — with a quick way to switch between them
- **Fill all** and **Clear all** actions
- a gallery of selectable built-in presets (varied large/small tile arrangements)
- a few quick save/load slots (for example 3) for the user's own custom layouts, in addition to named presets

Preview settings concepts:

- layout preset
- row-by-row timeline flow
- column-by-column timeline flow
- shuffled time order
- enlarged-tile count and placement
- small-tile arrangement

## 11. User Interface and Interaction Model

### 11.1 Visual Direction

- The default UI theme should be dark.
- The UI should feel light, clear, and not overloaded despite using a dark palette.
- Primary browsing screens should minimize visual clutter.
- Less common and more advanced controls should be moved into settings, modals, or secondary panels.

### 11.2 Main Navigation Priorities

The primary day-to-day workflows are:

- browsing the video library
- viewing directory contents
- launching conversion, preview, tagging, or rescan actions
- opening individual videos

The main screens should prioritize those actions and avoid exposing infrequent tuning controls by default.

### 11.3 Directory-Level Actions

For any selected folder, the UI should allow starting:

- conversion (with test-mode checkbox and skip-processed toggle)
- preview generation
- tagging
- rescan

All folder actions apply to the selected folder and all nested subfolders.

### 11.4 File-Level Actions

For any selected video, the UI should allow:

- opening the file info panel (details, media info, tags)
- viewing preview assets if available
- opening video playback according to configured playback mode
- running conversion for that specific video
- running preview generation for that specific video
- running AI tagging for that specific video (through Tag Lab, [Section 12.4](#124-tag-lab))
- running variant comparison ("tuning") for that specific video
- adding/removing tags manually, including during playback (quick tag-add)
- finding similar files
- moving the file to another folder (with favorite-folder and recent-folder shortcuts)
- deleting the file (together with its sibling preview assets)

For a standalone image, the same actions apply except conversion, preview generation, and variant comparison (video-only); playback is replaced by a full-screen image viewer.

To keep cards uncluttered, file cards expose only two direct actions — click the thumbnail to play/view, click the "i" overlay button for everything else (via the info panel).

### 11.5 Video Playback Mode

- Video opening behavior should be configurable in settings.
- The system must support at least two playback strategies, because target devices are not yet known:
  - **Stream:** embedded playback in a modal/in-app viewer, backed by a backend streaming proxy with HTTP Range support.
  - **Direct link:** external opening through a direct file path or protocol link (for example a UNC/`smb://` path) when the environment supports it.
- Playback mode may behave differently across devices and environments, so the user must be able to switch strategies at any time.

### 11.6 Job Management UI

- The top bar shows a compact activity indicator whenever a job is queued or running:
  - hovering it shows which job is running and what it is doing
  - clicking it opens the jobs modal
- The application should provide a dedicated tasks or jobs modal.
- The jobs UI should show queued, running, completed, and failed jobs.
- The jobs UI should allow:
  - stopping jobs (a second cancel force-finishes a stuck job)
  - pausing and resuming jobs with a per-item loop (pausing frees the lane for the next queued job)
  - restarting jobs when appropriate
  - removing individual jobs from the list
  - clearing all finished jobs with a single button
  - opening the log viewer pre-filtered to one job
- Running jobs show a progress bar (item counts), the current item, elapsed time, and a rolling-window ETA estimate.
- Pending provider-side batch-tagging submissions are visible in a dedicated modal reachable from the jobs UI, with a "forget locally" action.
- Finished jobs are also removed automatically after 24 hours (see [Job Model](./job-model.md)).
- Some jobs may also be created directly from the jobs UI, but the primary job creation flow should remain attached to folders and videos.

### 11.7 Log Viewer

- The application should provide a dedicated log viewer.
- Logs should remain available in backend console output as usual (every HTTP request is logged by middleware, except quiet polling routes; a rotating file log is kept as well).
- The UI log viewer should display job-related activity in near real time (SSE stream plus backfill), with filters by job, file, and level, a clear-filters action, elapsed timestamps, and clickable per-file badges that toggle the file filter.
- The log viewer should help the user understand what files are being processed and what each task is doing.

### 11.8 Search

- The UI provides a compact search field in the top bar; it must not complicate the main browsing layout.
- Search is **scoped** (post-V1 improvement): `tag:` / `file:` / `path:` prefixes (with Russian aliases) restrict a query to tags, file names, or folder names; an unprefixed query searches all three groups at once.
- Typing suggests matches per group — tags from every tag pool (usage-ordered, with their colors), files and folders via debounced server queries — each group capped by a configurable search limit.
- An unscoped search renders up to three capped result groups, each with a "search only in this group" shortcut; a scoped search renders one flat infinite-scroll grid.
- Prev/next navigation in playback, the image viewer, and the info panel follows the on-screen search-result order while a search is active, not the underlying folder order.

### 11.9 Localization

- The application must support English and Russian UI languages.
- Language must be switchable at runtime from a small, unobtrusive control (for example, a compact language toggle in the top bar) without requiring an app restart or page reload.
- All user-facing strings, including settings labels, job statuses, and error messages, must exist in both languages.
- Any new UI copy added to the product must be added in both languages at the same time; partial-language features are not acceptable.
- The selected language is a persisted user preference.

### 11.10 Visual Style and Theming

- The visual language should stay compact and uncluttered: a slim top bar, small icon-only buttons for secondary/global actions (jobs, settings, theme, language), pill-shaped filters, and a card grid for browsing.
- Every button must carry an icon from the shared icon set, except rare cases where no icon fits; and wherever an icon alone makes the action self-evident (delete, save, run, etc.), the label should be dropped in favor of an icon-only button — this should be the common case, not the exception. See [Design System §4.2](./design-system.md#42-icon-only-buttons-for-self-evident-actions) for the full rule.
- This direction is inspired by reference screenshots of another application shared for this project; the reference is a density and restraint style guide, not a template to copy pixel-for-pixel. See [Design System](./design-system.md) for the detailed breakdown.
- The application ships **eight theme presets** (post-V1 expansion from the original two): **Strict** (default, the minimal low-key dark style described above), **Playful**, **Casino**, **Neon Night**, **Toxic Arcade**, **Cyber Violet**, **Vivid Glam**, and **Mono Ice** — all built on the same layout and information structure, differing only in CSS variable sets.
- Theme preset is a persisted user preference: a top-bar icon button cycles presets; the interface settings tab offers a full picker with accent swatches.
- Switching theme preset must not change navigation structure, screen layout, or available actions — only color, iconography, and decorative treatment (scrollbars follow the theme too).
- Expressive presets may use small, purely decorative animations (hover lift, soft glow/pulse). Animations must stay lightweight, must not block or slow down interaction, must respect `prefers-reduced-motion`, and must not be added to Strict by default.

### 11.11 Responsive and Mobile Support

- The web UI must be usable on mobile-sized viewports, not only desktop.
- Primary workflows (browsing the library, opening a video, inspecting details, launching folder/file actions) must remain reachable and usable on a small screen through responsive layout, not a separate mobile codebase.
- The same screen and interaction structure should apply across desktop and mobile widths, so the interface can later be reused as the basis for a dedicated mobile application without a redesign.
- Native mobile applications remain out of scope (see [Section 3](#3-out-of-scope)); this requirement covers responsiveness of the existing web UI only.
- The frontend must be built mobile-first from the start of implementation ([Roadmap Stage 1](./roadmap.md#stage-1--skeleton)), not retrofitted in a later polish stage; portrait orientation is the primary small-screen case to design against, since most phone usage is vertical.
- The app is reachable from other devices on the local network (frontend and backend bind to `0.0.0.0`); Settings → Network lists the detected `http://<lan-ip>:<port>` addresses with copy buttons and connection instructions.
- See [Design System](./design-system.md) for breakpoints and detailed responsive rules.

### 11.12 Library Conveniences

Post-V1 quality-of-life behaviors that shape the main screen:

- **Sorting:** a toolbar button cycles the card sort order (name / size / tag count); the same order drives prev/next navigation.
- **Live updates:** while a job runs, the library refreshes a file's card as soon as that file's job item completes — not only when the whole job finishes — without a loading-state flash.
- **Folder management:** folders can be created, deleted (empty ones only, deliberately non-recursive), and marked as favorites. Favorites appear as one-click "move here" targets in playback and the info panel.
- **Recent-folder history:** the app records folders where a video was played or a file was moved (never plain browsing) and offers them as quick-jump targets — a "Recent folders" toolbar menu with clickable path crumbs, and a History popover in the quick-move controls.
- **Directory tree:** collapsible pane (closed by default), name filter that prunes to matching branches, expand/collapse-all, per-folder status dots and top-tag dots (the five most-used tags in the subtree, with tooltips).
- **Recently-played memory:** the last played videos feed defaults elsewhere (for example, the tagging settings preview picks the most recently viewed video as its sample).

## 12. Tagging

### 12.1 Tag Model

Tags live in **three pools** (post-V1, user request), tracked by two independent flags on the tag catalog:

- **AI vocabulary** (`is_ai_vocabulary`): the closed set the AI scores against — the *only* pool ever sent to a vision provider. Managed in the tagging settings' vocabulary editor.
- **User-defined** (`is_user_defined`): purely subjective tags, never AI-scored. Managed in their own settings section and assigned through a dedicated per-file picker.
- **Ad-hoc** (neither flag): tags typed directly onto a file via a free-text add field, or variant-sweep parameter tags. Manually typing a tag onto a file must **not** silently add it to either managed pool.

Rules:

- Tags may be arbitrary words or phrases; keys are normalized (lowercased) for deduplication.
- The AI's job is to evaluate **how well each vocabulary tag matches a given file**, not to invent new tags.
- The AI result for a file includes matched tags with a relevance score per tag (0–100, presented as a percentage); only the top-N best-matching tags are stored (default N = 10, configurable). Manually assigned tags carry score 100 and a `manual` provenance.
- Every tag has a **color**: an explicitly picked one, or a deterministic hash-based fallback computed identically on the backend and frontend — so a tag renders with one stable color everywhere it appears (settings, cards, info panel, Tag Lab), always with contrast-checked text.

### 12.2 Tagging Input

- For a video, tagging uses sampled frames (same interior sampling strategy as previews). The number of sampled frames is configurable in settings; default: `9`.
- For cost control, the sampled frames are combined into a single collage image (for example 3×3) before classification; this is the default behavior. Per-frame submission is the alternative.
- A configurable `image_resolution` caps the pixel size of each frame (collage cell side or per-frame longest side), so the collage's total size scales with the grid.
- A standalone image is sent as a single JPEG at `image_resolution` — no frame sampling involved.
- The tagging settings page offers a "preview what the model sees" action that renders the current (possibly unsaved) settings against a recently viewed video into the real output images.

### 12.3 Tagging Execution

- Directory/source-scope tagging is a background job on the network lane ([Section 4.3](#43-execution-model)).
- Provider configuration is a user-managed, **priority-ordered list of provider entries** (any number per provider type, see [Section 18](#18-ai-provider-settings-and-secrets)). The job tries enabled entries in priority order and falls back to the next on failure, so one bad key or outage doesn't stop tagging; entries that fail are skipped for the rest of the job.
- The classification request sends the image(s) plus the full active AI vocabulary to a vision-capable model and asks it to score each tag's relevance.
- Tagging should optimize for low cost rather than dense scene understanding.
- **Batch tagging** (Gemini/Mistral): when a batch-capable entry is enabled, the job submits all pending files in one provider-side batch request, **persists the submission before polling**, and polls until resolution. Pause/cancel/restart-safe: a restart resumes the pending submission from its own snapshot; anything unresolved falls back to the per-file chain. Pending submissions are visible (and locally forgettable) in the UI.
- Every provider call is recorded in a usage log (tokens, estimated or provider-reported cost) summarized in Settings.

### 12.4 Tag Lab

Single-file AI tagging is a synchronous, review-first workbench (post-V1, user request) instead of a background job:

- The user picks **one** provider entry (no fallback chain, no batch); the model picker shows per-model quality stats and the selected model's price per 1M tokens before running.
- The images to be sent and the prompt render immediately (a separate prepare step), before the model responds; sampled images are cached in-process so re-running against the same file with unchanged settings is cheap.
- The run returns the raw model reply text and the full raw provider JSON (collapsed, inspectable — including on failures where the provider returned *something*), token/cost usage, and every vocabulary tag ranked by score.
- Nothing is written until the user applies the (optionally edited) tag list. Suggested tags can be removed, and more can be added via the shared suggestion flow.
- Feedback loop: per-tag like/dislike votes plus an automatic apply-behavior KPI (applied unchanged / applied with edits / never applied) aggregate into per-model quality stats, keyed by `(provider_type, model_name)`.
- Direct provider calls have a configurable request timeout (default 30 s), with a matching client-side ceiling so the UI can never wait forever.

### 12.5 Model Pricing

Per-model price data (post-V1, user request) is keyed by `(provider_type, model_name)` — never by provider entry — so two entries pointing at the same model share one price:

- Prices ($/1M input and output tokens) are editable in Settings, both in a dedicated table and inline where a model is configured or run.
- OpenRouter prices can be refreshed from its public catalog API; other providers are manual-only (seeded defaults where known).
- When a provider reports its own billed cost per call (OpenRouter, and FAL's gateway route), that value is logged as-is instead of the rate-table estimate.

## 13. Similar File Detection

- Similarity detection is optional and secondary; it must not block conversion or preview completion.
- The goal is approximate near-duplicate detection, not perfect identity (exact binary hashing is not sufficient because videos may be re-encoded).
- Implemented approach: 64-bit perceptual hash (aHash) signatures — over 8 interior frames for a video, over the whole image for a standalone image — compared by Hamming distance. Matches are same-kind only (a video signature never matches an image one).
- Video signatures are generated best-effort as a side effect of the preview job; image signatures as a side effect of the tag job (plus a lazy on-demand fallback when "similar" is requested for an unsigned image).
- Similarity data is stored locally for reuse; the UI exposes a "similar files" list from the info panel, where an empty result is a normal outcome.

## 14. File and Directory State Model

### 14.1 File-Level State

Files do **not** carry workflow status enums (no `in_progress`, no `failed` per file). Transient execution state and errors live in jobs, job items, and logs only.

Each supported file tracks simple facts:

- discovered by scan (always true for existing rows)
- supported as a video and/or as a standalone image (`is_video_supported` / `is_image_supported` — independent flags, not one enum)
- converted at least once (`converted_at` timestamp, null if never; video-only)
- has a preview asset (`has_preview_asset`, detected by scan or set by the preview job; video-only)
- has tags (`tagged_at` timestamp, null if never tagged)
- playback duration (`duration_seconds`, shown as a card badge; video-only)

### 14.2 Directory-Level State

- Directory status is derived from file facts.
- Directory status must not be stored as an independent persisted aggregate flag.
- Directory status includes:
  - files in the current folder
  - files in all nested subfolders
- Only supported video files participate in conversion and preview progress calculations.

Derived rules:

- A directory conversion indicator is complete only when all supported video files in that subtree have been converted at least once.
- A directory preview indicator is complete only when all supported video files in that subtree have preview assets.
- If new files appear after rescan, derived directory status must fall back to an incomplete state.

### 14.3 UI Indicators

- UI indicators are shown only for incomplete states (and for the currently running job via the jobs UI).
- Fully complete states do not need visible indicators.
- The main directory view should use separate visual indicators for:
  - conversion
  - preview
- Indicator meaning must be explained on hover.

## 15. Metadata Storage

### 15.1 Local Database

- The application stores processing metadata in a local SQLite database on disk.
- The database is used for:
  - file-level metadata
  - cached intermediate analysis
  - job history
  - derived progress queries

### 15.2 Core File Metadata

See [Data Model](./data-model.md) for the authoritative schema. Core facts per file: relative path, name, extension, size, modification time, discovery/scan timestamps, supported-video flag, `converted_at` + last profile, `has_preview_asset` + `preview_generated_at`, `tagged_at`. Assigned tags live in a separate table with per-tag scores.

### 15.3 Cached Analysis Metadata

Recommended reusable analysis fields:

| Field | Purpose |
| --- | --- |
| `keyframe_timestamps` | Reuse selected preview timestamps |
| `large_tile_timestamps` | Reuse selected enlarged frames |
| `face_detection_summary` | Cache face-detection results |
| `body_detection_summary` | Cache body or pose results |
| `preview_layout_version` | Invalidate stale preview choices after algorithm changes |
| `tagging_model_info` | Remember provider and model used for tags |
| `tagging_updated_at` | Timestamp for current tag result |

### 15.4 Directory-Level Metadata

- The database may store recent directory-level job history for UI and audit use.
- The database should not rely on persisted "fully processed directory" flags.

## 16. Rescan and Cleanup

The application must support maintenance actions from settings.

Required actions:

- full rescan of connected source
- stale-record cleanup for files that no longer exist
- local database compact or optimize operation

These actions should live in settings or maintenance screens, not in the main browsing view.

## 17. Settings

The application must provide a dedicated settings area.

Settings areas include:

- source settings (connection form plus the saved-sources list)
- conversion profile settings
- preview settings (collage layout and animated preview)
- playback settings
- tagging settings (AI vocabulary, user-defined tags, sampling, resolution, timeout)
- AI provider settings (provider entries, model pricing, usage, ratings)
- backup and restore settings
- performance settings (parallel workers)
- network access (read-only LAN address list)
- maintenance settings
- interface settings (language, theme, preview stylization profiles, search limits)

See [Settings Specification](./settings-spec.md) for details.

## 18. AI Provider Settings and Secrets

Supported provider types:

- OpenRouter
- Google Gemini
- FAL
- Mistral

Provider configuration is a user-managed, **priority-ordered list of entries** (post-V1 evolution from one fixed choice per provider): any number of entries per type, each with its own API key, vision model, optional text model, enabled flag, and — for batch-capable types (Gemini, Mistral) — a batch preference. The list order is the fallback priority for background tagging jobs ([Section 12.3](#123-tagging-execution)).

Provider settings must support:

- adding, editing, reordering, enabling/disabling, and deleting entries
- API key entry (never echoed back — only presence and a masked suffix)
- model selection for vision workloads, with live model-catalog lookup where the provider offers one (OpenRouter, Gemini, Mistral; FAL has no catalog API and uses a curated list instead)
- optional model selection for text workloads
- per-model price overrides and the pricing table ([Section 12.5](#125-model-pricing))
- a per-(provider, model) usage summary table
- export and import of provider configuration, **including plaintext API keys**, by explicit user action behind a confirmation

Secret storage rule:

- API keys and source credentials must not be stored in the main application database.
- Secrets live in a local `.env`-style file next to the backend (see [Tech Stack](./tech-stack.md)); the file is git-ignored, human-readable, and easy to copy or back up by hand. SMB credentials are stored per saved source.

## 19. Backup and Restore

- Backups are stored on the source disk itself, in the technical folder `.video-archive/backups/` at the source root.
- The local database must support manual backup creation and restore from backup.
- Source switching creates and restores backups automatically (see [Section 5.2](#52-source-switching)), so metadata follows each source across switches.
- Backup retention count must be configurable; default: `5`.
- Settings must include a dedicated backup section.
- When a new source is connected and existing backups are detected in its technical folder, the UI offers to restore one (see [Section 5.2](#52-source-switching)).
- See [Backup Format](./backup-format.md) for package contents.

## 20. Recommended Architecture

```text
React + TypeScript UI (Vite)
  -> FastAPI backend
    -> source access layer (local FS, SMB) -- all file access goes through it
    -> scan and metadata layer
    -> job queue (two-lane worker: CPU lane + network/tagging lane)
    -> video conversion worker (ffmpeg, parallel items)
    -> preview generation worker (ffmpeg + local detection models)
       -> JPEG collage written next to the video on the source
       -> animated GIFs written to the local per-source preview cache
    -> tagging job worker (priority-ordered provider entries, batch orchestration)
    -> Tag Lab (synchronous single-file tagging, no job queue)
    -> local SQLite metadata database
    -> secrets file (.env)
```

## 21. Companion Specifications

Implementation details are split into the following companion documents:

- [Tech Stack](./tech-stack.md)
- [Roadmap](./roadmap.md)
- [Data Model](./data-model.md)
- [API Specification](./api-spec.md)
- [Job Model](./job-model.md)
- [Settings Specification](./settings-spec.md)
- [UI Screens](./ui-screens.md)
- [Design System](./design-system.md)
- [Backup Format](./backup-format.md)
