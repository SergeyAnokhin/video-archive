# video-archive

Video Archive is a local-first, Windows-targeted web application for browsing a video directory source (local folder or SMB share), converting videos in bulk with ffmpeg, generating preview collages stored next to the videos, and tagging videos through external AI providers.

## Current Status

**All V1 scope from [docs/spec/specification.md](docs/spec/specification.md) is implemented (Roadmap Stages 1-9), with the exception of the WebDAV source protocol, which the specification itself lists as out of scope for V1 (§3).** `frontend/` and `backend/` run together from the repository root: a Vite + React + TypeScript shell with a dark Strict theme, a responsive top bar, and EN/RU i18n, talking to a FastAPI backend with a schema-versioned SQLite database. On top of that:

- Stage 2 adds configuring a `local` source (a folder next to the backend, or any absolute path) from Settings, with test-connection and a destructive-replace warning; a synchronous filesystem scan on connect that discovers folders/files, detects supported video extensions, and recognizes preview assets (`<name>.jpg`, `folder-preview.jpg`) without listing them as separate files; and a directory tree and folder/file card grid in the main library screen, with conversion/preview indicators shown only for incomplete folders and files.
- Stage 3 adds a job queue (`jobs`/`job_items` tables) driven by a single sequential background worker with a `queued → running → completed|failed|cancelled` state machine; a `rescan` job (triggered from a folder's toolbar) that refreshes one directory subtree file-by-file with live per-file progress and cooperative cancellation; a structured event log (`app_events`) streamed to the frontend over SSE; a top-bar activity indicator, a Jobs modal (cancel/restart/remove/clear-finished), and a Log Viewer (job/file/level filters); and 24-hour automatic retention for finished jobs.
- Stage 4 adds saved conversion profiles (CRUD in Settings: codec, container, max dimension, CRF, drop-audio, default profile); a `convert` job that runs ffmpeg with a safe replace workflow (temp output → lightweight ffprobe validation → replace the source only on success, otherwise the original is left untouched); a per-job test-mode toggle that preserves the original as `<name>.original.<ext>` instead of deleting it, plus a skip-processed toggle for bulk runs; folder-level convert dialogs (recursive, excluding `.original.`/`.variant-` artifacts) and a file-level convert/variant-comparison modal that sweeps max-dimension/CRF/codec combinations into `<name>.variant-<params>.mp4` outputs and can promote a variant's parameters into a new saved profile.
- Stage 5 adds a `preview` job that samples interior video frames, ranks them with local, best-effort face/person detection (YuNet/YOLOv8n/SFace via OpenCV and ONNX Runtime, gracefully degrading to blur-score ranking if a model is missing) and composites them into a black-background grid collage with enlarged tiles and a file-name caption, written next to the source as `<name>.jpg`; folder-level jobs also refresh `folder-preview.jpg` recursively for every directory in the subtree; a Preview Settings section (grid dimensions, collage aspect ratio, a construction-set tile editor with a built-in + custom preset gallery and quick save/load slots, timeline flow, identity diversity) with a live layout preview; and real preview thumbnails rendered in the library grid, toggleable via the existing top-bar preview-visibility button.
- Stage 6 adds a user-defined tag vocabulary (add/rename/deactivate/delete in Settings) and AI provider settings for OpenRouter, Google Gemini, FAL, and Mistral (enabled flag, vision/text model, API key written to the git-ignored `backend/secrets.env` — never stored in the database or echoed back over the API); a `tag` job that samples interior frames, composites them into one collage (or sends them individually, per setting), sends the image(s) plus the vocabulary to the configured provider, and stores the top-N scored tags per video (replacing any previous tag set); and a compact tag-search box in the library toolbar with prefix autocomplete against the vocabulary that switches the view to a flat, filtered file list.
- Stage 7 adds an `smb` source protocol alongside `local` (host/port/share-path form in Settings, with a Reconnect action), with SMB credentials written to the same git-ignored secrets file as AI provider keys; every file access — scan, conversion, preview generation, tagging, playback — now goes through a uniform `app/sources/` layer (`backend/app/sources/`) instead of raw filesystem paths, so the whole pipeline works the same way against both protocols; and two video playback strategies reachable from a "Play" action on any file card — an embedded player backed by a Range-capable backend streaming proxy, and a direct local/UNC path shown with a copy button for opening externally — switchable per-session regardless of the configured default playback mode.
- Stage 8 adds manual backup/restore: a `backup` job zips the local library metadata (directories/files/tags, conversion profiles, preview/tagging/provider/playback settings) plus an optional secrets-file copy into `.video-archive/backups/` on the source itself, with a configurable retention count trimming the oldest packages; a `restore` job replaces the current library metadata from a chosen package; connecting a source now surfaces any backups already sitting in its technical folder so the UI can offer a restore right away; replacing the active source now correctly warns and wipes the *full* local-metadata set (files, directories, tags, job history — previously only files/directories were cleared); and a Backup & Maintenance settings section adds `cleanup` (stale-record removal) and `optimize_db` (SQLite `VACUUM`/`ANALYZE`) maintenance actions alongside a full-rescan shortcut.
- Stage 9 adds a Playful theme preset alongside Strict (a top-bar icon toggle, warmer/more saturated colors, small decorative hover/glow animations that respect `prefers-reduced-motion`), with both the theme choice and the UI language now persisted server-side through a new interface-settings singleton instead of language living only in browser `localStorage`; a responsive/mobile refinement pass (an overflow menu for secondary folder actions in the library toolbar below 640px, restored 40×40 touch targets on the directory tree and breadcrumbs at mobile widths, and a fix for file-card action buttons that used to overlap the file name/size text); optional similar-video detection that computes a perceptual-hash signature from each video's sampled preview frames as a best-effort side effect of preview generation, surfaced through a per-file "Similar videos" action; and optional provider-side batch tagging for Gemini/Mistral (a directory-scope tagging job submits every pending file in one batch request when enabled, falling back per-file for anything the batch pass couldn't resolve). WebDAV, the other "optional" Stage 9 item, was intentionally not built — the specification lists it as out of scope for V1.

Post-V1: the library UI was reworked for simplicity per direct user feedback — the search box moved into the top bar (was in the per-folder toolbar), the directory tree is now collapsed by default at every screen width (was a persistent pane on desktop) and only opens via the top-bar menu toggle, file cards were cut down to two actions (click the thumbnail to play, click an "i" overlay button for a consolidated info panel with generate-preview/tag/convert/similar-videos actions, replacing five always-visible per-card icons), the playback view is now a minimal full-viewport overlay instead of a titled dialog, the library grid now only ever shows folders/videos (non-video files are filtered server-side), and a job-completion listener refetches the current folder so a newly generated thumbnail/status appears without a manual reload. A third theme preset, Casino (neon-on-near-black, alongside Strict/Playful), was added to the existing theme toggle.

See [docs/spec/roadmap.md](docs/spec/roadmap.md) for the full stage-by-stage implementation history.

## Local Run

The repository root is the single developer entrypoint: one command starts frontend and backend together.

### Prerequisites

- Node.js 20+
- Python 3.11+
- ffmpeg on `PATH` (`winget install ffmpeg`)
- Internet access on first preview generation (or first `pytest` run touching preview code): face-detection model files (~39 MB total) are downloaded once into `backend/models/` (git-ignored) and cached from then on. Preview generation still works offline, with reduced frame-selection quality (blur-score ranking only) — see [Tech Stack](docs/spec/tech-stack.md#local-detection-models).

### Startup

```powershell
npm.cmd install
npm.cmd run dev
```

- Frontend: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8000` (health at `/api/health`, app info at `/api/app/info`)

Frontend and backend also remain independently runnable from their own directories (`npm run dev` inside `frontend/` or `backend/`).

## Project Structure

- [`package.json`](package.json) — root developer entrypoint that starts frontend and backend together.
- [`docs/`](docs/) — living project documentation; the frozen V1 specification is archived in [`docs/spec/`](docs/spec/).
- [`frontend/`](frontend/) — Vite + React + TypeScript app.
- [`backend/`](backend/) — FastAPI app, SQLite database (git-ignored), schema versioning.

See [docs/code-map.md](docs/code-map.md) for the full file-by-file map.

## Local Test Data

`test-data/VideoArchive/` holds real camera-recording samples for manually exercising the `local` source (scanning, browsing, conversion, etc. from [Stage 2](docs/spec/roadmap.md#stage-2--local-source-scan-browsing) onward). It mirrors what a real source root looks like:

```text
test-data/VideoArchive/
  Foscam/2026/05/06/alarm_20260506_144929.mp4
  ReolinkFront/2026/03/04/ReolinkFront_00_20260304000003.mp4
```

- Top-level folders are camera names; nested folders are date-partitioned (`YYYY/MM/DD`).
- This directory is git-ignored (`/test-data/` in [`.gitignore`](.gitignore)) — it stays local, is not committed, and is not part of the application source.
- To use it as a source, point a `local` source's root path at `test-data/VideoArchive` (or a subfolder of it).
- If a dev session already has this connected as the active source (common across sessions, since source config persists in the SQLite db), prefer dropping extra scratch files into a throwaway subfolder and rescanning that subfolder, rather than replacing the source — replacing wipes all accumulated `directories`/`files`/job metadata for a fresh scan ([Specification §5.2](docs/spec/specification.md#52-source-switching)). Delete the scratch subfolder and rescan again afterward to restore the previous state.

## Documentation

Living docs — read and update these during development (see [`docs/README.md`](docs/README.md) for the full index):

- [`docs/code-map.md`](docs/code-map.md) — living map of implementation files
- [`docs/architecture.md`](docs/architecture.md) — current high-level architecture and cross-cutting conventions
- [`docs/development.md`](docs/development.md) — developer workflow: run, test, verify

Frozen V1 specification — [`docs/spec/`](docs/spec/): the complete pre-implementation spec set (specification, roadmap, data model, API, UI screens, design system, tech stack, job model, settings, backup format). V1 is fully implemented, so this set is archived for reference. **Do not read it by default** — consult it only when explicitly asked or when a question is specifically about original V1 spec intent.
