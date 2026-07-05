# Video Archive Roadmap

Implementation stages for Video Archive. Each stage produces something runnable and verifiable before the next stage starts. Details live in the linked specifications; this file only fixes the order and the completion criteria.

The previous prototype was intentionally removed; Stage 1 recreates the skeleton from scratch.

## Stage 1 — Skeleton

Scope:

- Root `package.json` orchestration (`npm run dev` starts both halves) per [Tech Stack](./tech-stack.md).
- `frontend/`: Vite + React + TypeScript shell with dark Strict theme base, top bar, i18n scaffold (EN/RU from day one).
- `backend/`: FastAPI app with `GET /api/health` and `GET /api/app/info` (including ffmpeg availability), SQLite initialization with schema versioning.

Done when: `npm.cmd run dev` from the root starts both servers; the frontend shows backend status; both languages switch live.

## Stage 2 — Local Source, Scan, Browsing

Scope:

- Source configuration for `local` protocol ([Specification §5](./specification.md#5-source-model), [Settings §1](./settings-spec.md#1-source-connection-settings)).
- Scan workflow with the supported-extension list and preview-asset detection ([Specification §6.1](./specification.md#61-scan), [Tech Stack](./tech-stack.md#supported-video-extensions)).
- Directory tree, folder contents, file cards ([UI Screens §1](./ui-screens.md#1-main-library-screen)); derived directory indicators ([Specification §14](./specification.md#14-file-and-directory-state-model)).
- Browsing endpoints ([API §3](./api-spec.md#3-directory-and-file-browsing)).

Done when: a `library` folder next to the backend is scanned and browsable, indicators reflect missing conversions/previews.

## Stage 3 — Job Infrastructure

Scope:

- Jobs and job items tables, single sequential worker, job state machine ([Job Model](./job-model.md)).
- Jobs modal, top-bar activity indicator with hover/click behavior ([UI Screens §3](./ui-screens.md#3-jobs-modal)).
- Log events + SSE stream + log viewer ([API §12](./api-spec.md#12-logs-and-events), [UI Screens §4](./ui-screens.md#4-log-viewer)).
- 24-hour retention and clear-all for finished jobs.

Done when: a dummy long-running job (e.g. rescan) is visible live in the indicator, modal, and log viewer, and can be cancelled.

## Stage 4 — Conversion

Scope:

- Conversion profiles CRUD ([Specification §7](./specification.md#7-conversion-profiles), [UI Screens §6](./ui-screens.md#6-conversion-profiles-screen)).
- ffmpeg conversion worker with safe replacement ([Specification §8.1](./specification.md#81-production-mode)).
- Test mode and skip-processed toggle ([Specification §8.2](./specification.md#82-test-mode), [§6.2](./specification.md#62-conversion)).
- Variant comparison for a single file ([Specification §8.3](./specification.md#83-variant-comparison)), promotion of a variant into a profile.

Done when: a folder converts recursively in production and test modes; failed validation never destroys an original; variants produce comparable outputs.

## Stage 5 — Preview Generation

Scope:

- Frame sampling, local face/figure detection models ([Specification §9.3–9.4](./specification.md#93-detection-rules), [Tech Stack](./tech-stack.md#local-detection-models)).
- Grid collage rendering with enlarged tiles; storage next to videos; folder previews ([Specification §9.2, §9.5](./specification.md#92-collage-grid-layout)).
- Preview settings page with live preview and layout presets ([Specification §10](./specification.md#10-preview-settings-page), [UI Screens §5](./ui-screens.md#5-preview-settings-screen)).

Done when: previews appear as `<name>.jpg` next to videos and `folder-preview.jpg` in folders, visible in the library grid.

## Stage 6 — Tagging and Search

Scope:

- Tag vocabulary management in settings ([Settings §5](./settings-spec.md#5-tagging-settings)).
- Provider configuration + secrets file ([Specification §18](./specification.md#18-ai-provider-settings-and-secrets)).
- Tagging job: 9-frame collage → provider → top-N tags with scores ([Specification §12](./specification.md#12-tagging)).
- Compact tag search with prefix autocomplete ([Specification §11.8](./specification.md#118-search), [API §10](./api-spec.md#10-tagging-and-tags)).

Done when: a video gets scored tags from a real provider; searching by tag filters the library.

## Stage 7 — SMB Source and Playback

Scope:

- SMB source adapter, reconnect behavior ([Specification §5](./specification.md#5-source-model)).
- Credentials in secrets file.
- Playback modes: backend streaming proxy with Range support, and direct link/path ([Specification §11.5](./specification.md#115-video-playback-mode), [API §11](./api-spec.md#11-playback)).

Done when: an SMB share browses, converts, and plays through both playback strategies.

## Stage 8 — Backup, Restore, Maintenance, Source Switching

Scope:

- Backup creation/restore into `.video-archive/backups/` on the source ([Backup Format](./backup-format.md)).
- Retention handling; backup discovery + restore offer when connecting a source ([Specification §5.2](./specification.md#52-source-switching)).
- Maintenance actions: full rescan, stale cleanup, DB optimize ([Specification §16](./specification.md#16-rescan-and-cleanup)).
- Destructive source-switch warning flow.

Done when: switching sources warns and wipes; a backup made before the wipe restores the library on reconnect.

## Stage 9 — Polish and Optional Features

Scope:

- Playful theme preset and decorative animations ([Design System §2.2](./design-system.md#22-playful)).
- Responsive/mobile refinement pass ([Design System §5](./design-system.md#5-responsive-breakpoints)).
- Optional: similar video detection ([Specification §13](./specification.md#13-similar-video-detection)).
- Optional: WebDAV source; provider batch tagging modes.

Done when: V1 scope from [Specification](./specification.md) is fully covered.

## Cross-Stage Rules

- EN/RU string parity is maintained in every stage, not retrofitted at the end.
- [Code Map](./code-map.md) is updated whenever files are added or moved.
- Docs are updated in the same change as behavior they describe.
