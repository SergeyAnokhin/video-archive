# video-archive

Video Archive is a local-first, Windows-targeted web application for browsing a video directory source (local folder or SMB share), converting videos in bulk with ffmpeg, generating preview collages stored next to the videos, and tagging videos through external AI providers. A Vite + React + TypeScript frontend and a FastAPI + SQLite backend run together from the repository root; UI in English/Russian with eight theme presets (Strict, Playful, Casino, Neon Night, Toxic Arcade, Cyber Violet, Vivid Glam, Mono Ice).

## Capabilities

What the application does today (implementation details and file locations are in [docs/code-map.md](docs/code-map.md)):

- **Source** — one active source at a time: a `local` folder or an `smb` share. Configure, test-connection, connect, and reconnect from Settings; replacing the source wipes the scanned metadata after an explicit warning. All file access (scan, convert, preview, tag, playback, backup) goes through the uniform [`backend/app/sources/`](backend/app/sources/) layer, so every feature behaves identically for both protocols.
- **Library UI** — collapsible directory tree (closed by default), card grid with animated GIF thumbnails, tag/name search with prefix autocomplete in the top bar, and a per-file info panel: media info via on-demand ffprobe plus all per-file actions (generate preview, tag, convert, tune, similar videos, move, delete).
- **Background jobs** — a two-lane worker (one CPU-bound lane, one network-bound lane for AI tagging) runs `rescan`, `convert`, `preview`, `tag`, `backup`, `restore`, `cleanup`, `optimize_db` with live per-item progress, cooperative cancellation and pause/resume (repeating a Cancel that hasn't been honored yet force-terminates an unresponsive job instead of waiting on it forever), an SSE-streamed event log (Jobs modal + Log Viewer, with a "copy all" button and a per-stage progress breakdown — probing, frame extraction, encoding, rendering — for `convert`/`preview` items, also mirrored to the backend console), and 24-hour retention for finished jobs. Within a `convert`/`preview` job, a configurable number of files (or, for a single file, that file's own independent per-item work — variant encodes, preview frame extractions) run concurrently instead of one at a time (Settings → Performance).
- **Conversion** — saved ffmpeg profiles (codec, container, max dimension, CRF, drop-audio); safe replace: encode to a temp file, validate with ffprobe, replace the original only on success. Test mode preserves the original as `<name>.original.<ext>`; per-file tuning sweeps parameter ranges into `<name>.variant-<params>.mp4` outputs (defaulting to a sensible CRF/resolution range out of the box) and can promote a variant's parameters into a saved profile. `.original.`/`.variant-` artifacts are excluded from bulk jobs.
- **Previews** — two distinct kinds, configured on separate Settings tabs: the **collage**, a JPEG grid next to the video (`<name>.jpg`), and the **animated preview**, a GIF (in the source's `.video-archive/previews/` per file, `folder-preview.gif` recursively per folder) shown on grid hover thumbnails. The animated preview's source mode is configurable — still frames or short video-clip bursts per segment — with adjustable segment duration and an optional crossfade transition. Frames are ranked by local face/person detection (ONNX models downloaded on first use; degrades to blur-score ranking offline). Collage grid layout is edited in a construction-set editor with presets and a live preview.
- **AI tagging** — a user-defined tag vocabulary and a priority-ordered list of provider entries (OpenRouter, Gemini, FAL, Mistral; any number, including several per type) with automatic fallback when an entry fails; optional provider-side batch tagging for Gemini/Mistral. API keys and SMB credentials live only in the git-ignored `backend/secrets.env`, never in the database or API responses.
- **Playback** — embedded HTML5 player over a Range-capable backend streaming proxy, or a copyable direct local/UNC path; switchable per session.
- **Similar videos** — perceptual-hash signatures computed as a best-effort side effect of preview generation, surfaced through a per-file "Similar videos" action.
- **Backup & maintenance** — manual backup/restore of the library metadata as zip packages in the source's `.video-archive/backups/` with configurable retention; stale-record cleanup and SQLite `VACUUM`/`ANALYZE` actions.

## Local Run

The repository root is the single developer entrypoint: one command starts frontend and backend together.

### Prerequisites

- Node.js 20+
- Python 3.11+
- ffmpeg on `PATH` (`winget install ffmpeg`)
- Internet access on first preview generation (or first `pytest` run touching preview code): face-detection model files (~39 MB total) are downloaded once into `backend/models/` (git-ignored) and cached from then on. Preview generation still works offline, with reduced frame-selection quality (blur-score ranking only).

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
- [`frontend/`](frontend/) — Vite + React + TypeScript app.
- [`backend/`](backend/) — FastAPI app, SQLite database (git-ignored), schema versioning.
- [`docs/`](docs/) — living project documentation.

## Documentation

Read these before changing code — they are maintained to make navigation fast (see [`docs/README.md`](docs/README.md) for the index):

- [`docs/code-map.md`](docs/code-map.md) — file-by-file map of the implementation (split into frontend / backend / routers / tests parts). **Start here to find where anything lives.**
- [`docs/architecture.md`](docs/architecture.md) — high-level architecture, key flows, and the cross-cutting conventions table.
- [`docs/development.md`](docs/development.md) — how to run, test, and manually verify changes, including known environment pitfalls.

`docs/spec/` is a frozen pre-implementation specification archive kept for reference only — **do not read it by default**; trust the code and the living docs above.

## Local Test Data

`test-data/VideoArchive/` holds real camera-recording samples for manually exercising the `local` source (scanning, browsing, conversion, etc.). It mirrors what a real source root looks like:

```text
test-data/VideoArchive/
  Foscam/2026/05/06/alarm_20260506_144929.mp4
  ReolinkFront/2026/03/04/ReolinkFront_00_20260304000003.mp4
```

- Top-level folders are camera names; nested folders are date-partitioned (`YYYY/MM/DD`).
- This directory is git-ignored (`/test-data/` in [`.gitignore`](.gitignore)) — it stays local, is not committed, and is not part of the application source.
- To use it as a source, point a `local` source's root path at `test-data/VideoArchive` (or a subfolder of it).
- If a dev session already has this connected as the active source (common across sessions, since source config persists in the SQLite db), prefer dropping extra scratch files into a throwaway subfolder and rescanning that subfolder, rather than replacing the source — replacing wipes all accumulated `directories`/`files`/job metadata for a fresh scan. Delete the scratch subfolder and rescan again afterward to restore the previous state.
