# video-archive

Video Archive is a local-first, Windows-targeted web application for browsing a video directory source (local folder or SMB share), converting videos in bulk with ffmpeg, generating preview collages stored next to the videos, and tagging videos through external AI providers.

## Current Status

**Roadmap Stage 1 ("Skeleton") and Stage 2 ("Local Source, Scan, Browsing") are implemented.** `frontend/` and `backend/` run together from the repository root: a Vite + React + TypeScript shell with a dark Strict theme, a responsive top bar, and EN/RU i18n, talking to a FastAPI backend with a schema-versioned SQLite database. On top of that, Stage 2 adds:

- configuring a `local` source (a folder next to the backend, or any absolute path) from Settings, with test-connection and a destructive-replace warning;
- a synchronous filesystem scan on connect that discovers folders/files, detects supported video extensions, and recognizes preview assets (`<name>.jpg`, `folder-preview.jpg`) without listing them as separate files;
- a directory tree and folder/file card grid in the main library screen, with conversion/preview indicators shown only for incomplete folders and files.

See [docs/roadmap.md](docs/roadmap.md) for what comes next (jobs, conversion, previews, tagging, playback).

## Local Run

The repository root is the single developer entrypoint: one command starts frontend and backend together.

### Prerequisites

- Node.js 20+
- Python 3.11+
- ffmpeg on `PATH` (`winget install ffmpeg`)

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
