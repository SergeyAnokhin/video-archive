# Video Archive Roadmap

Implementation stages for Video Archive. Each stage produces something runnable and verifiable before the next stage starts. Details live in the linked specifications; this file only fixes the order and the completion criteria.

**All V1 stages below are complete.** Development continued past V1; the user-facing improvements shipped since are summarized in [Post-V1 Improvements](#post-v1-improvements) at the end of this file and are folded into the other specification documents.

The previous prototype was intentionally removed; Stage 1 recreates the skeleton from scratch.

## Stage 1 — Skeleton

Scope:

- Root `package.json` orchestration (`npm run dev` starts both halves) per [Tech Stack](./tech-stack.md).
- `frontend/`: Vite + React + TypeScript shell with dark Strict theme base, top bar, i18n scaffold (EN/RU from day one).
- Mobile-first responsive foundations established from this stage, not deferred: breakpoints and layout primitives per [Design System §5](./design-system.md#5-responsive-breakpoints), portrait orientation as the primary small-screen case.
- `backend/`: FastAPI app with `GET /api/health` and `GET /api/app/info` (including ffmpeg availability), SQLite initialization with schema versioning.

Done when: `npm.cmd run dev` from the root starts both servers; the frontend shows backend status; both languages switch live; the shell layout is already responsive down to mobile/portrait widths.

## Stage 2 — Local Source, Scan, Browsing

Scope:

- Source configuration for `local` protocol ([Specification §5](./specification.md#5-source-model), [Settings §1](./settings-spec.md#1-source-settings)).
- Scan workflow with the supported-extension list and preview-asset detection ([Specification §6.1](./specification.md#61-scan), [Tech Stack](./tech-stack.md#supported-video-extensions)).
- Directory tree, folder contents, file cards ([UI Screens §1](./ui-screens.md#1-main-library-screen)); derived directory indicators ([Specification §14](./specification.md#14-file-and-directory-state-model)).
- Browsing endpoints ([API §3](./api-spec.md#3-directory-and-file-browsing)).

Done when: a `library` folder next to the backend is scanned and browsable, indicators reflect missing conversions/previews.

Manual testing can point the `local` source at [`test-data/VideoArchive/`](../../README.md#local-test-data), a local-only sample of real camera-recording folders (git-ignored, not part of the app).

## Stage 3 — Job Infrastructure

Scope:

- Jobs and job items tables, single sequential worker, job state machine ([Job Model](./job-model.md)).
- Jobs modal, top-bar activity indicator with hover/click behavior ([UI Screens §6](./ui-screens.md#6-jobs-modal)).
- Log events + SSE stream + log viewer ([API §14](./api-spec.md#14-logs-and-events), [UI Screens §7](./ui-screens.md#7-log-viewer)).
- 24-hour retention and clear-all for finished jobs.

Done when: a dummy long-running job (e.g. rescan) is visible live in the indicator, modal, and log viewer, and can be cancelled.

## Stage 4 — Conversion

Scope:

- Conversion profiles CRUD ([Specification §7](./specification.md#7-conversion-profiles), [UI Screens §8](./ui-screens.md#8-settings-modal)).
- ffmpeg conversion worker with safe replacement ([Specification §8.1](./specification.md#81-production-mode)).
- Test mode and skip-processed toggle ([Specification §8.2](./specification.md#82-test-mode), [§6.2](./specification.md#62-conversion)).
- Variant comparison for a single file ([Specification §8.3](./specification.md#83-variant-comparison)), promotion of a variant into a profile.

Done when: a folder converts recursively in production and test modes; failed validation never destroys an original; variants produce comparable outputs.

## Stage 5 — Preview Generation

Scope:

- Frame sampling, local face/figure detection models ([Specification §9.3–9.4](./specification.md#93-detection-rules), [Tech Stack](./tech-stack.md#local-detection-models)).
- Grid collage rendering with enlarged tiles; storage next to videos; folder previews ([Specification §9.2, §9.5](./specification.md#92-collage-grid-layout)).
- Preview settings page with live preview and layout presets ([Specification §10](./specification.md#10-preview-settings-page), [UI Screens §8](./ui-screens.md#8-settings-modal)).

Done when: previews appear as `<name>.jpg` next to videos and `folder-preview.jpg` in folders, visible in the library grid.

## Stage 6 — Tagging and Search

Scope:

- Tag vocabulary management in settings ([Settings §5](./settings-spec.md#5-tagging-settings)).
- Provider configuration + secrets file ([Specification §18](./specification.md#18-ai-provider-settings-and-secrets)).
- Tagging job: 9-frame collage → provider → top-N tags with scores ([Specification §12](./specification.md#12-tagging)).
- Compact tag search with prefix autocomplete ([Specification §11.8](./specification.md#118-search), [API §10](./api-spec.md#10-tags)).

Done when: a video gets scored tags from a real provider; searching by tag filters the library.

## Stage 7 — SMB Source and Playback

Scope:

- SMB source adapter, reconnect behavior ([Specification §5](./specification.md#5-source-model)).
- Credentials in secrets file.
- Playback modes: backend streaming proxy with Range support, and direct link/path ([Specification §11.5](./specification.md#115-video-playback-mode), [API §13](./api-spec.md#13-playback)).

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

- Playful theme preset and decorative animations ([Design System §2.2](./design-system.md#22-expressive-presets)).
- Responsive/mobile refinement pass ([Design System §5](./design-system.md#5-responsive-breakpoints)) — polish only; mobile-first foundations already exist from Stage 1.
- Optional: similar video detection ([Specification §13](./specification.md#13-similar-file-detection)).
- Optional: WebDAV source; provider batch tagging modes.

Done when: V1 scope from [Specification](./specification.md) is fully covered.

## Cross-Stage Rules

- EN/RU string parity is maintained in every stage, not retrofitted at the end.
- [Code Map](../code-map.md) is updated whenever files are added or moved.
- Docs are updated in the same change as behavior they describe.

## Post-V1 Improvements

Shipped after V1 completion, in rough thematic groups (details live in the other spec documents, updated in place):

- **Sources**: any number of *saved* sources with one active at a time; switching backs the outgoing source up onto its own disk and auto-restores the incoming source's backup, so switching is no longer a destructive wipe ([Specification §5](./specification.md#5-source-model)). Per-source local preview cache with stats and clear action.
- **Jobs**: two-lane worker (one CPU-bound job plus one network-bound tagging job concurrently), pause/resume, force-cancel, parallel per-item processing bounded by a performance setting, progress bars with ETA, card-based Jobs modal ([Job Model](./job-model.md)).
- **Previews**: animated GIF previews for grid/list thumbnails and folder cards, cached locally per source (never written to the source); the JPEG collage remains next to the video and is shown in the file info panel; clip-based animated mode with transitions; two client-side preview stylization profiles ([Specification §9](./specification.md#9-preview-generation)).
- **Tagging**: priority-ordered provider *entries* with automatic fallback; Tag Lab — a synchronous single-file tagging workbench with raw-response inspection, usage/cost reporting, per-model pricing and quality ratings; three tag pools (AI vocabulary / user-defined / ad-hoc); per-tag colors; persistent provider-side batch tagging that survives restarts ([Specification §12](./specification.md#12-tagging)).
- **Library**: standalone images as first-class items; scoped search (`tag:` / `file:` / `path:`); sorting; folder favorites, create/delete; file move/delete; recent-folder navigation history; live per-file updates while jobs run ([UI Screens](./ui-screens.md)).
- **Interface**: eight theme presets; LAN network access with a Settings page listing reachable URLs; request logging and a rotating backend log file; expanded log viewer ([Design System](./design-system.md), [Settings §9–10](./settings-spec.md)).
- **Quality**: backend pytest suites and frontend vitest suites (including EN/RU key-parity enforcement and component tests).
