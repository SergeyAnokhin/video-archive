# Video Archive Technical Specification

## 1. Overview

Video Archive is a web application for working with remote video directories. The system consists of a React frontend and a Python backend. The application connects to one remote source directory at a time, shows its folder structure, runs video conversion jobs, generates preview collages, and optionally assigns tags to videos through external AI providers.

The product is centered on three independent processing workflows:

- video conversion
- preview generation
- AI tagging

These workflows must remain separate job types and must not be implicitly coupled.

## 2. Product Goals

- Connect to a remote directory using protocol-specific credentials.
- Show the directory tree and navigate nested folders.
- Convert videos in bulk using saved conversion profiles.
- Replace original files after successful conversion.
- Support a safe test mode that preserves the original source file.
- Generate preview collages for videos and folders.
- Assign tags to videos from a predefined tag vocabulary.
- Cache processing metadata locally to avoid repeated expensive work.

## 3. Out of Scope for V1

- Multi-user collaboration
- Full media-library features such as ratings or watch history
- Advanced streaming-specific subsystems
- Free-form AI scene search across all video content
- Mobile-specific UI

## 4. System Scope

### 4.1 Frontend

- React web application
- Directory tree and file browser
- Job management screens
- Settings screens
- Preview settings page with live preview
- Log viewer
- Video details modal

### 4.2 Backend

- Python API
- Remote source access layer
- Scan and metadata layer
- Job queue
- Local processing workers
- Local database
- External AI provider integration

### 4.3 Execution Model

- Local jobs run on the same machine as the backend.
- External LLM and vision-model requests are sent to configured providers.
- Conversion, preview, and tagging are separate job types.

### 4.4 Local Development and Startup

- The first implementation target is local development on Windows.
- The project should be runnable from a terminal.
- The repository root should provide an `npm`-based entrypoint that starts frontend and backend together.
- Frontend and backend should also remain independently runnable from their own directories.
- The root-level startup flow should be the default developer entrypoint for local work.

## 5. Remote Source Model

- The application supports exactly one connected source at a time.
- The source is a protocol-backed remote directory connection, not a generic local mount abstraction.
- Supported protocols:
  - SMB
  - FTP
  - SFTP
  - WebDAV
- A source configuration includes:
  - protocol
  - host
  - remote path
  - authentication details
  - optional protocol-specific parameters such as port
- The backend must support reconnect and refresh behavior for the active source.

## 6. Core Workflows

### 6.1 Scan

- The backend scans the connected directory tree.
- Scan discovers files and folders and refreshes metadata.
- Scan is lightweight and does not require a dedicated persistent UI status indicator.
- Scan must detect:
  - newly appeared files
  - removed files
  - changed file metadata relevant to processing

### 6.2 Conversion

- User selects a folder or files and chooses a conversion profile.
- Folder-level actions always apply to the selected folder and all nested subfolders.
- Backend converts all supported video files in the selected scope.
- In production mode, the original file is replaced only after successful validation of the converted output.
- In test mode, converted output is written separately and the original file is preserved.

### 6.3 Preview Generation

- Preview generation is a separate on-demand workflow.
- It must not run automatically after conversion.
- It can be run for:
  - one video
  - multiple videos
  - a folder
- Folder-level preview generation always applies to the selected folder and all nested subfolders.

### 6.4 Tagging

- Tagging is a separate on-demand workflow.
- It must not be required for conversion or preview completion.
- Tags are selected from a predefined allowed list.
- Folder-level tagging always applies to the selected folder and all nested subfolders.

### 6.5 Rescan

- Rescan can be run for the connected source and for a selected folder subtree.
- Folder-level rescan always applies to the selected folder and all nested subfolders.

## 7. Conversion Profiles

A conversion profile is a saved set of video conversion parameters.

Each profile may define:

- target codec
- maximum output dimension
- quality or encoder tuning parameters
- audio removal behavior

Profile rules:

- Default codec for V1: `H.265`
- Default output container for V1: `MP4`
- Resizing is applied only when the source video exceeds the configured maximum dimension.
- Maximum dimension means the largest side of the output must not exceed the configured limit.
- Audio may be dropped entirely in V1.
- The application must support multiple saved profiles.
- The application must support test generation across multiple profile variants.

Test generation use cases:

- compare several resolutions
- compare several quality settings
- compare several codec or encoder variants

## 8. Safe File Replacement

The system must use a safe replacement workflow for converted files.

Required sequence:

1. Write converted output to a temporary file.
2. Run a fast validation pass on that temporary file.
3. Replace the source only if validation succeeds.
4. Keep the original file untouched if validation fails.

Validation requirements:

- output file exists
- output file size is non-zero
- output file is recognized as a valid media file
- output exposes expected video metadata
- output matches the expected container and codec combination

Validation must be lightweight and should avoid full decode playback unless later evidence shows it is necessary.

Temporary output may be created:

- locally
- near the remote source

The implementation may choose either strategy based on protocol constraints and safety.

## 9. Preview Generation

### 9.1 General Rules

- Preview generation builds a collage from sampled video frames.
- Preview generation supports video previews and folder previews.
- Folder previews can use representative frames from multiple videos.
- Preview visibility must be globally toggleable in the main UI.

### 9.2 Large and Small Tiles

- Preview layouts may contain enlarged key tiles and smaller supporting tiles.
- If a layout includes highlighted large tiles:
  - the first two large tiles should prefer face-detected frames
  - remaining large tiles should prefer human figure or pose detections
- If identity diversity is enabled, the system should try to use two different faces for the first two large tiles.
- If identity diversity is disabled, unavailable, or too expensive for the current environment, it is acceptable to use two face-detected frames from different timeline regions.
- If a layout has three or more large tiles, only the first two are face-prioritized; the remaining large tiles are figure-prioritized.

### 9.3 Detection Rules

- Face detection must run locally using Python libraries.
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

## 10. Preview Settings Page

The application must provide a dedicated preview settings page.

The page must support:

- configuring sampled frame count
- configuring how many large key tiles are used
- configuring tile layout presets
- configuring timeline flow strategy
- enabling or disabling identity diversity attempts
- previewing the resulting layout live before running a full preview job
- identity diversity attempts should be enabled by default

Preview settings concepts:

- layout preset
- row-by-row timeline flow
- column-by-column timeline flow
- shuffled time order
- large-tile count
- small-tile arrangement

The page should support:

- saving preset layouts
- loading preset layouts
- quick fill and clear actions for layout editing

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

- conversion
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
- running tuning jobs for that specific video

### 11.5 Video Playback Mode

- Video opening behavior should be configurable in settings.
- The system should support at least two playback strategies:
  - embedded playback in a modal or in-app viewer
  - external opening through a direct file path or link when the environment supports it
- Playback mode may behave differently across devices and environments, so the user must be able to switch strategies.
- External opening may use protocol-appropriate links or paths when supported by the active source and client environment.

### 11.6 Job Management UI

- The application should provide a dedicated tasks or jobs modal.
- The jobs UI should show queued, running, completed, and failed jobs.
- The jobs UI should allow:
  - stopping jobs
  - restarting jobs when appropriate
  - removing jobs from the list when appropriate
- Some jobs may also be created directly from the jobs UI, but the primary job creation flow should remain attached to folders and videos.

### 11.7 Log Viewer

- The application should provide a dedicated log viewer.
- Logs should remain available in backend console output as usual.
- The UI log viewer should display job-related activity in near real time.
- The log viewer should help the user understand what files are being processed and what each task is doing.

### 11.8 Tuning Workflow

- Tuning is an advanced workflow and should not dominate the main interface.
- Tuning is initiated from a specific video rather than from a bulk folder operation.
- Tuning jobs must generate separate output files and must never replace the source video.
- Tuning should support parameter sweeps across:
  - output dimension
  - quality settings
  - codec choices
- Example sweep behavior:
  - generate outputs for 1000, 900, 800 pixel maximum dimension using a fixed step
  - generate outputs across several quality values
  - generate outputs across several codec variants
- The user should be able to review tuning results and turn a successful tuning result into a saved conversion profile later.

## 12. Tagging

### 12.1 Tag Model

- Tags are chosen from a closed allowed vocabulary configured in settings.
- The model must not generate arbitrary free-form tags as the primary tagging result.
- The result for a video should include:
  - selected tags
  - confidence scores for selected tags

### 12.2 Tagging Input

- Tagging uses sampled frames from a video.
- The number of sampled frames is configurable in settings.
- Default sampled-frame count for tagging: `9`
- For cost control, multiple representative frames may be combined into a single image before classification.

### 12.3 Tagging Execution

- Tagging is a separate job type.
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

Each supported video file should track at least:

- discovered by scan
- converted at least once
- preview generated

File workflow states:

- `conversion_state`: `not_started | in_progress | done | failed`
- `preview_state`: `not_started | in_progress | done | failed`

### 14.2 Directory-Level State

- Directory status is derived from file states.
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

- UI indicators are shown only for incomplete, in-progress, or failed states.
- Fully successful states do not need visible indicators.
- The main directory view should use separate visual indicators for:
  - conversion
  - preview
- Indicator meaning must be explained on hover.

## 15. Metadata Storage

### 15.1 Local Database

- The application stores processing metadata in a local database on disk.
- The database is used for:
  - file-level metadata
  - cached intermediate analysis
  - job history
  - derived progress queries

### 15.2 Core File Metadata

Recommended core fields:

| Field | Purpose |
| --- | --- |
| `path` | Full current file path within the connected source |
| `relative_path` | Stable path relative to source root |
| `file_name` | Display name |
| `extension` | File type and eligibility |
| `size_bytes` | Change detection and UI display |
| `modified_at` | Change detection during rescan |
| `discovered_at` | First discovery time |
| `last_scanned_at` | Most recent scan time |
| `is_video_supported` | Whether file participates in workflows |
| `conversion_state` | Conversion state |
| `preview_state` | Preview state |
| `last_conversion_profile_id` | Last used conversion profile |
| `last_converted_at` | Last successful conversion time |
| `preview_generated_at` | Last successful preview time |
| `preview_asset_path` | Stored preview image path for the current file-level preview |
| `tags` | Final assigned tags |

### 15.3 Cached Analysis Metadata

Recommended reusable analysis fields:

| Field | Purpose |
| --- | --- |
| `keyframe_timestamps` | Reuse selected preview timestamps |
| `large_tile_timestamps` | Reuse selected highlighted frames |
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
- tagging settings
- AI provider settings
- backup and restore settings
- maintenance settings

## 18. AI Provider Settings

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

API key rule:

- API keys must not be stored in the main application database.
- Secret storage should use a safer local mechanism than normal database rows when possible.

## 19. Backup and Restore

- The local database must support manual backup creation.
- The local database must support restore from backup.
- Backup retention count must be configurable.
- Default backup retention count: `5`
- Settings must include a dedicated backup section.

## 20. Recommended Architecture

```text
React UI
  -> Python API
    -> remote protocol access layer
    -> scan and metadata layer
    -> local job queue
    -> video conversion workers
    -> preview generation workers
    -> tagging job workers
    -> local metadata database
    -> external AI provider adapters
```

## 21. Companion Specifications

Implementation details are split into the following companion documents:

- [Data Model](./data-model.md)
- [API Specification](./api-spec.md)
- [Job Model](./job-model.md)
- [Settings Specification](./settings-spec.md)
- [UI Screens](./ui-screens.md)
- [Backup Format](./backup-format.md)
