# video-archive

Video Archive is a local-first, Windows-targeted web application for browsing a video directory source (local folder or SMB share), converting videos in bulk with ffmpeg, generating preview collages stored next to the videos, and tagging videos through external AI providers.

## Current Status

**Roadmap Stages 1-7 ("Skeleton", "Local Source, Scan, Browsing", "Job Infrastructure", "Conversion", "Preview Generation", "Tagging and Search", "SMB Source and Playback") are implemented.** `frontend/` and `backend/` run together from the repository root: a Vite + React + TypeScript shell with a dark Strict theme, a responsive top bar, and EN/RU i18n, talking to a FastAPI backend with a schema-versioned SQLite database. On top of that:

- Stage 2 adds configuring a `local` source (a folder next to the backend, or any absolute path) from Settings, with test-connection and a destructive-replace warning; a synchronous filesystem scan on connect that discovers folders/files, detects supported video extensions, and recognizes preview assets (`<name>.jpg`, `folder-preview.jpg`) without listing them as separate files; and a directory tree and folder/file card grid in the main library screen, with conversion/preview indicators shown only for incomplete folders and files.
- Stage 3 adds a job queue (`jobs`/`job_items` tables) driven by a single sequential background worker with a `queued → running → completed|failed|cancelled` state machine; a `rescan` job (triggered from a folder's toolbar) that refreshes one directory subtree file-by-file with live per-file progress and cooperative cancellation; a structured event log (`app_events`) streamed to the frontend over SSE; a top-bar activity indicator, a Jobs modal (cancel/restart/remove/clear-finished), and a Log Viewer (job/file/level filters); and 24-hour automatic retention for finished jobs.
- Stage 4 adds saved conversion profiles (CRUD in Settings: codec, container, max dimension, CRF, drop-audio, default profile); a `convert` job that runs ffmpeg with a safe replace workflow (temp output → lightweight ffprobe validation → replace the source only on success, otherwise the original is left untouched); a per-job test-mode toggle that preserves the original as `<name>.original.<ext>` instead of deleting it, plus a skip-processed toggle for bulk runs; folder-level convert dialogs (recursive, excluding `.original.`/`.variant-` artifacts) and a file-level convert/variant-comparison modal that sweeps max-dimension/CRF/codec combinations into `<name>.variant-<params>.mp4` outputs and can promote a variant's parameters into a new saved profile.
- Stage 5 adds a `preview` job that samples interior video frames, ranks them with local, best-effort face/person detection (YuNet/YOLOv8n/SFace via OpenCV and ONNX Runtime, gracefully degrading to blur-score ranking if a model is missing) and composites them into a black-background grid collage with enlarged tiles and a file-name caption, written next to the source as `<name>.jpg`; folder-level jobs also refresh `folder-preview.jpg` recursively for every directory in the subtree; a Preview Settings section (grid dimensions, collage aspect ratio, a construction-set tile editor with a built-in + custom preset gallery and quick save/load slots, timeline flow, identity diversity) with a live layout preview; and real preview thumbnails rendered in the library grid, toggleable via the existing top-bar preview-visibility button.
- Stage 6 adds a user-defined tag vocabulary (add/rename/deactivate/delete in Settings) and AI provider settings for OpenRouter, Google Gemini, FAL, and Mistral (enabled flag, vision/text model, API key written to the git-ignored `backend/secrets.env` — never stored in the database or echoed back over the API); a `tag` job that samples interior frames, composites them into one collage (or sends them individually, per setting), sends the image(s) plus the vocabulary to the configured provider, and stores the top-N scored tags per video (replacing any previous tag set); and a compact tag-search box in the library toolbar with prefix autocomplete against the vocabulary that switches the view to a flat, filtered file list.
- Stage 7 adds an `smb` source protocol alongside `local` (host/port/share-path form in Settings, with a Reconnect action), with SMB credentials written to the same git-ignored secrets file as AI provider keys; every file access — scan, conversion, preview generation, tagging, playback — now goes through a uniform `app/sources/` layer (`backend/app/sources/`) instead of raw filesystem paths, so the whole pipeline works the same way against both protocols; and two video playback strategies reachable from a "Play" action on any file card — an embedded player backed by a Range-capable backend streaming proxy, and a direct local/UNC path shown with a copy button for opening externally — switchable per-session regardless of the configured default playback mode.

See [docs/roadmap.md](docs/roadmap.md) for what comes next (backup/restore, maintenance actions, destructive source-switch warnings).

## Local Run

The repository root is the single developer entrypoint: one command starts frontend and backend together.

### Prerequisites

- Node.js 20+
- Python 3.11+
- ffmpeg on `PATH` (`winget install ffmpeg`)
- Internet access on first preview generation (or first `pytest` run touching preview code): face-detection model files (~39 MB total) are downloaded once into `backend/models/` (git-ignored) and cached from then on. Preview generation still works offline, with reduced frame-selection quality (blur-score ranking only) — see [Tech Stack](docs/tech-stack.md#local-detection-models).

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
- [`docs/`](docs/) — the product and architecture specifications that drive the implementation.
- [`frontend/`](frontend/) — Vite + React + TypeScript app.
- [`backend/`](backend/) — FastAPI app, SQLite database (git-ignored), schema versioning.

See [docs/code-map.md](docs/code-map.md) for the full file-by-file map.

## Local Test Data

`test-data/VideoArchive/` holds real camera-recording samples for manually exercising the `local` source (scanning, browsing, conversion, etc. from [Stage 2](docs/roadmap.md#stage-2--local-source-scan-browsing) onward). It mirrors what a real source root looks like:

```text
test-data/VideoArchive/
  Foscam/2026/05/06/alarm_20260506_144929.mp4
  ReolinkFront/2026/03/04/ReolinkFront_00_20260304000003.mp4
```

- Top-level folders are camera names; nested folders are date-partitioned (`YYYY/MM/DD`).
- This directory is git-ignored (`/test-data/` in [`.gitignore`](.gitignore)) — it stays local, is not committed, and is not part of the application source.
- To use it as a source, point a `local` source's root path at `test-data/VideoArchive` (or a subfolder of it).
- If a dev session already has this connected as the active source (common across sessions, since source config persists in the SQLite db), prefer dropping extra scratch files into a throwaway subfolder and rescanning that subfolder, rather than replacing the source — replacing wipes all accumulated `directories`/`files`/job metadata for a fresh scan ([Specification §5.2](docs/specification.md#52-source-switching)). Delete the scratch subfolder and rescan again afterward to restore the previous state.

## Documentation

Core specification set:

- [`docs/specification.md`](docs/specification.md) — main technical specification
- [`docs/tech-stack.md`](docs/tech-stack.md) — fixed technology choices
- [`docs/roadmap.md`](docs/roadmap.md) — implementation stages and completion criteria
- [`docs/data-model.md`](docs/data-model.md)
- [`docs/api-spec.md`](docs/api-spec.md)
- [`docs/job-model.md`](docs/job-model.md)
- [`docs/settings-spec.md`](docs/settings-spec.md)
- [`docs/ui-screens.md`](docs/ui-screens.md)
- [`docs/design-system.md`](docs/design-system.md)
- [`docs/backup-format.md`](docs/backup-format.md)
- [`docs/code-map.md`](docs/code-map.md) — living map of implementation files
