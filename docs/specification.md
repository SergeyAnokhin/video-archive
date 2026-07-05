# Video Archive Technical Specification

## 1. Overview

Video Archive is a web application for working with a video directory source. The system consists of a React + TypeScript frontend and a Python (FastAPI) backend. The application connects to one source directory at a time, shows its folder structure, runs video conversion jobs, generates preview collages, and assigns tags to videos through external AI providers.

The product is centered on three independent processing workflows:

- video conversion
- preview generation
- AI tagging

These workflows must remain separate job types and must not be implicitly coupled.

The concrete technology choices (frameworks, libraries, external tools) are fixed in [Tech Stack](./tech-stack.md). The implementation order is fixed in [Roadmap](./roadmap.md).

## 2. Product Goals

- Connect to a source directory (local directory or SMB share).
- Show the directory tree and navigate nested folders.
- Convert videos in bulk using saved conversion profiles.
- Replace original files after successful conversion.
- Support a safe test mode that preserves the original source file.
- Generate preview collages stored next to the video files themselves.
- Assign tags to videos from a user-defined tag vocabulary, with relevance scores.
- Cache processing metadata locally to avoid repeated expensive work.

## 3. Out of Scope for V1

- Multi-user collaboration
- Full media-library features such as ratings or watch history
- Advanced streaming-specific subsystems
- Free-form AI scene search across all video content
- Native mobile applications (dedicated iOS/Android app)
- FTP and SFTP source protocols
- WebDAV source protocol (optional, may be added after SMB works)

Responsive behavior of the web UI on mobile-sized viewports is in scope for V1; see [Section 11.11](#1111-responsive-and-mobile-support).

## 4. System Scope

### 4.1 Frontend

- React + TypeScript web application (Vite)
- Directory tree and file browser
- Job management screens and a top-bar activity indicator
- Settings screens
- Preview settings page with live preview
- Log viewer
- Video details modal
- Compact tag-based search field

### 4.2 Backend

- Python FastAPI service
- Source access layer (local filesystem and SMB)
- Scan and metadata layer
- Job queue (single worker, strictly sequential)
- Local processing workers
- Local SQLite database
- External AI provider integration

### 4.3 Execution Model

- Local jobs run on the same machine as the backend.
- External LLM and vision-model requests are sent to configured providers.
- Conversion, preview, and tagging are separate job types.
- Exactly one job runs at a time; within a job, files are processed one at a time. ffmpeg's own internal multithreading for a single file is allowed. Higher-level parallelism may be added later only if CPU utilization proves insufficient.

### 4.4 Local Development and Startup

- The first implementation target is local development on Windows.
- The project should be runnable from a terminal.
- The repository root provides an `npm`-based entrypoint that starts frontend and backend together.
- Frontend and backend should also remain independently runnable from their own directories.
- The root-level startup flow should be the default developer entrypoint for local work.

## 5. Source Model

- The application supports exactly one connected source at a time.
- Supported source types for V1:
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

- Changing the active source is a destructive operation: the UI must warn the user that all local metadata (files, directories, tags, job history) will be deleted, because the library starts over.
- Backups stored on the old source's disk remain there untouched.
- After connecting to a new source, the backend checks the source's technical folder (see [Section 19](#19-backup-and-restore)) for existing backups. If backups are found, the UI proactively offers to restore one.

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
- Tags are matched against the user-defined vocabulary (see [Section 12](#12-tagging)).
- Folder-level tagging always applies to the selected folder and all nested subfolders.
- By default, files that already have tags are skipped; the user can disable this per job to re-tag.

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

- Preview generation builds a collage from sampled video frames.
- Preview generation supports video previews and folder previews.
- Folder previews use representative frames from videos in the folder subtree (default: 4 frames).
- Preview visibility must be globally toggleable in the main UI.

### 9.2 Collage Grid Layout

- A video preview collage is a fully filled rectangular grid of frame tiles (rows × columns).
- Some tiles are enlarged: an enlarged tile spans 2×2 or 3×3 grid cells and replaces the small tiles it covers.
- The grid must always remain completely filled — enlarged tiles and small tiles together cover every cell exactly once.
- The number of sampled frames is therefore derived from the layout: total cells minus cells absorbed by enlarged tiles.
- Grid dimensions, the number of enlarged tiles, their sizes (2× or 3×), and their placement are configurable (see [Section 10](#10-preview-settings-page)).
- The application ships with a built-in gallery of layout presets mixing large and small tiles in varied arrangements (large tiles at a corner, along an edge, centered, and so on), modeled on the reference screenshot shared for this project; the user picks a preset or edits a custom layout.

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

Preview collages are stored on the source itself, next to the content they describe:

- **Video preview:** a JPEG in the same folder as the video, with the same base name: `movie.mp4` → `movie.jpg`.
- **Folder preview:** a JPEG placed inside the folder itself with the fixed name `folder-preview.jpg`.
- Scan detects these files and records preview presence per file/folder; a JPEG whose base name matches a video in the same folder is treated as that video's preview asset, not as an independent library item.
- Collage output defaults: JPEG quality 85, width 2048 px (both configurable later if needed).
- Because assets live next to the videos, they move together with the archive and need no separate asset database.

## 10. Preview Settings Page

The application must provide a dedicated preview settings page.

The page must support:

- configuring the grid dimensions
- configuring how many enlarged tiles are used and their size (2×2 or 3×3)
- choosing from the built-in gallery of layout presets
- configuring timeline flow strategy
- enabling or disabling identity diversity attempts (enabled by default)
- configuring the folder-preview frame count (default: 4)
- previewing the resulting layout live before running a full preview job

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

### 11.4 Video-Level Actions

For any selected video, the UI should allow:

- opening video details
- viewing preview assets if available
- opening video playback according to configured playback mode
- running conversion for that specific video
- running preview generation for that specific video
- running tagging for that specific video
- running variant comparison for that specific video

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
  - stopping jobs
  - restarting jobs when appropriate
  - removing individual jobs from the list
  - clearing all finished jobs with a single button
- Finished jobs are also removed automatically after 24 hours (see [Job Model](./job-model.md)).
- Some jobs may also be created directly from the jobs UI, but the primary job creation flow should remain attached to folders and videos.

### 11.7 Log Viewer

- The application should provide a dedicated log viewer.
- Logs should remain available in backend console output as usual.
- The UI log viewer should display job-related activity in near real time.
- The log viewer should help the user understand what files are being processed and what each task is doing.

### 11.8 Search

- The UI provides a compact, non-dominant search field (for example at the edge of the toolbar); it must not occupy a central or large area.
- Search is primarily tag-driven: typing suggests existing tags from the vocabulary by prefix (autocomplete).
- Search may also match file names.
- Search is a convenience feature, not a core workflow, and must not complicate the main browsing layout.

### 11.9 Localization

- The application must support English and Russian UI languages.
- Language must be switchable at runtime from a small, unobtrusive control (for example, a compact language toggle in the top bar) without requiring an app restart or page reload.
- All user-facing strings, including settings labels, job statuses, and error messages, must exist in both languages.
- Any new UI copy added to the product must be added in both languages at the same time; partial-language features are not acceptable.
- The selected language is a persisted user preference.

### 11.10 Visual Style and Theming

- The visual language should stay compact and uncluttered: a slim top bar, small icon-only buttons for secondary/global actions (jobs, settings, theme, language), pill-shaped filters, and a card grid for browsing.
- This direction is inspired by reference screenshots of another application shared for this project; the reference is a density and restraint style guide, not a template to copy pixel-for-pixel. See [Design System](./design-system.md) for the detailed breakdown.
- The application must support at least two theme presets:
  - **Strict** (default): the minimal, low-key dark style described above and in Section 11.1.
  - **Playful**: a more energetic, casino/entertainment-inspired visual variant (brighter accent colors, more expressive iconography) built on the same layout and information structure as Strict.
- Theme preset is a persisted user preference, switchable from a small, unobtrusive control consistent with the rest of the global toolbar.
- Switching theme preset must not change navigation structure, screen layout, or available actions — only color, iconography, and decorative treatment.
- The Playful preset may use small, purely decorative animations (for example, subtle hover or transition effects). Animations must stay lightweight, must not block or slow down interaction, and must not be added to the Strict preset by default.

### 11.11 Responsive and Mobile Support

- The web UI must be usable on mobile-sized viewports, not only desktop.
- Primary workflows (browsing the library, opening a video, inspecting details, launching folder/file actions) must remain reachable and usable on a small screen through responsive layout, not a separate mobile codebase.
- The same screen and interaction structure should apply across desktop and mobile widths, so the interface can later be reused as the basis for a dedicated mobile application without a redesign.
- Native mobile applications remain out of scope for V1 (see [Section 3](#3-out-of-scope-for-v1)); this requirement covers responsiveness of the existing web UI only.
- See [Design System](./design-system.md) for breakpoints and detailed responsive rules.

## 12. Tagging

### 12.1 Tag Model

- The tag vocabulary is fully user-defined: the user adds and removes tags in settings. Tags may be arbitrary words or phrases.
- The AI's job is to evaluate **how well each vocabulary tag matches a given video**, not to invent new tags. The model must not generate free-form tags as the primary tagging result.
- The result for a video should include:
  - matched tags with a relevance score per tag (0–100, presented as a percentage)
  - only the top-N best-matching tags are stored (default N = 10, configurable)

### 12.2 Tagging Input

- Tagging uses sampled frames from a video (same interior sampling strategy as previews).
- The number of sampled frames is configurable in settings; default: `9`.
- For cost control, the sampled frames are combined into a single collage image (for example 3×3) before classification; this is the default behavior.

### 12.3 Tagging Execution

- Tagging is a separate job type.
- The classification request sends the collage image plus the full active vocabulary to a vision-capable model and asks it to score each tag's relevance to the frames.
- Tagging should optimize for low cost rather than dense scene understanding.
- The system should support provider-side batch submission when available.
- Batch tagging should combine many videos into one provider batch request when that materially reduces cost.
- Gemini-style and Mistral-style batch flows should be supported when available.

## 13. Similar Video Detection

- Similarity detection is optional and secondary.
- It must not block conversion or preview completion.
- The goal is approximate near-duplicate detection, not perfect identity.
- Exact binary hashing is not sufficient because videos may be re-encoded.
- A practical first approach is to compute a signature from a fixed number of representative frames.
- That signature may be based on:
  - perceptual hashes
  - embeddings
- Similarity data should be stored locally for reuse.
- The preferred first integration point is preview generation, because that workflow already samples representative frames.

## 14. File and Directory State Model

### 14.1 File-Level State

Files do **not** carry workflow status enums (no `in_progress`, no `failed` per file). Transient execution state and errors live in jobs, job items, and logs only.

Each supported video file tracks simple facts:

- discovered by scan (always true for existing rows)
- converted at least once (`converted_at` timestamp, null if never)
- has a preview asset (`has_preview_asset`, detected by scan or set by the preview job)
- has tags (`tagged_at` timestamp, null if never tagged)

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

- source connection settings
- conversion profile settings
- preview settings
- playback settings
- tagging settings (including vocabulary management)
- AI provider settings
- backup and restore settings
- maintenance settings
- interface settings (language, theme)

## 18. AI Provider Settings and Secrets

Supported provider targets for V1 configuration:

- OpenRouter
- Google Gemini
- FAL
- Mistral

Provider settings must support:

- API key entry
- model selection for vision workloads
- optional model selection for text workloads
- export and import of provider configuration, including API keys, by explicit user action

Secret storage rule:

- API keys and source credentials must not be stored in the main application database.
- Secrets live in a local `.env`-style file next to the backend (see [Tech Stack](./tech-stack.md)); the file is git-ignored, human-readable, and easy to copy or back up by hand.

## 19. Backup and Restore

- Backups are stored on the source disk itself, in the technical folder `.video-archive/backups/` at the source root.
- The local database must support manual backup creation and restore from backup.
- Backup retention count must be configurable; default: `5`.
- Settings must include a dedicated backup section.
- When a new source is connected and existing backups are detected in its technical folder, the UI offers to restore one (see [Section 5.2](#52-source-switching)).
- See [Backup Format](./backup-format.md) for package contents.

## 20. Recommended Architecture

```text
React + TypeScript UI (Vite)
  -> FastAPI backend
    -> source access layer (local FS, SMB)
    -> scan and metadata layer
    -> job queue (single sequential worker)
    -> video conversion worker (ffmpeg)
    -> preview generation worker (ffmpeg + local detection models)
    -> tagging job worker (external AI providers)
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
