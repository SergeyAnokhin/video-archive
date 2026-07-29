# video-archive

Video Archive is a local-first, Windows-targeted web application for browsing a video directory source (local folder, SMB share, or WebDAV share), converting videos in bulk with ffmpeg, generating preview collages stored next to the videos, and tagging videos through external AI providers. A Vite + React + TypeScript frontend and a FastAPI + SQLite backend run together from the repository root; UI in English/Russian with eight theme presets (Strict, Playful, Casino, Neon Night, Toxic Arcade, Cyber Violet, Vivid Glam, Mono Ice).

## Capabilities

What the application does today. Implementation details and file locations are in [docs/code-map.md](docs/code-map.md); how the pieces fit together in [docs/architecture.md](docs/architecture.md).

- **Sources** — several saved sources at once (`local` folders, `smb` shares, `webdav` shares), switchable from Settings without losing each one's data. Switching away backs the outgoing source up onto its own disk and auto-restores on the way back; app-wide settings are shared and never touched by a switch. All file access goes through the uniform [`backend/app/sources/`](backend/app/sources/) layer, so every feature behaves identically across all three protocols.
  - An `smb` source can opt into Windows-only **direct access** to read files straight off their UNC path instead of downloading each one, falling back automatically. Conversion's write side has its own separate opt-in switch. Media-info lookups for `.mp4`/`.mov`/`.m4v` also get a protocol-independent header-only fast path.
  - A `webdav` source talks plain HTTP via `httpx` (no third-party WebDAV library) and can skip TLS verification for a self-signed certificate — see [`docs/webdav-setup.md`](docs/webdav-setup.md).
- **Library UI** — collapsible directory tree, card grid with animated GIF thumbnails, scoped search (`tag:`/`file:`/`path:`) with autocomplete, and a per-file info panel holding every per-file action (preview, tag, convert, tune, similar, move, delete).
  - Prev/next navigation (buttons and arrow keys) in the player, image viewer, and info panel walks the current folder's sorted listing, or the search results' order while a search is active.
  - Folders can be created, deleted (if empty), and starred; favorites and recently-viewed history both surface as one-click "move this video here" targets. Each folder also shows its own top-5 tags, computed recursively on request.
- **Standalone images** — a photo in a video folder is a first-class library item: it appears in the grid and search, opens in a full-screen viewer, and supports tagging (including AI), move, delete, and "similar". Conversion and preview generation stay video-only.
- **Background jobs** — a two-lane worker (one CPU-bound, one network-bound for AI tagging) runs `rescan`, `convert`, `preview`, `tag`, `backup`, `restore`, `cleanup`, `optimize_db`.
  - Live per-item progress, cooperative cancellation, and pause/resume; a repeated Cancel force-terminates an unresponsive job. A job left running by a backend restart is marked failed and flagged distinctly from a real error, so it shows up as restartable.
  - An SSE-streamed event log (Jobs modal + Log Viewer) with per-stage progress, the exact ffmpeg command line for a convert job, and per-file original vs. resulting resolution and size. 24-hour retention for finished jobs.
  - A configurable number of files — or, for a single file, its own independent per-item work — runs concurrently (Settings → Performance).
- **Conversion** — saved ffmpeg profiles (codec, container, max dimension, CRF, drop-audio, `preset`, optional Intel QSV hardware encoding with automatic software fallback) with a safe-replace pipeline: encode to a temp file, validate with ffprobe, and replace the original only on success and only if it shrinks the source by at least a configurable minimum percentage.
  - Resizing only ever shrinks a source that exceeds the target — never upscales. mp4 output always gets `-movflags +faststart`.
  - Test mode preserves the original as `<name>.original.<ext>`; per-file tuning sweeps parameter ranges into `<name>.variant-<params>.mp4` outputs and can promote a variant's parameters into a saved profile. Both artifact kinds are excluded from bulk jobs.
  - A directory can also **generate a standalone PowerShell script** reproducing the same command and safe-replace guarantee, to run on any machine with filesystem access to that directory — no backend involved.
- **Previews** — two distinct artifacts, configured on separate Settings tabs.
  - The **collage**: a JPEG grid written next to its video (`<name>.jpg`), shown only in the info panel's static view. Its layout is edited in a construction-set editor with presets and a live preview.
  - The **animated preview**: a GIF per file plus `folder-preview.gif` per folder, shown on grid hover, written into the source's own `.video-archive/previews/` so it travels with the source. Source mode (still frames or short clips), segment duration, and an optional crossfade are configurable.
  - Frames are ranked by local face/person detection (ONNX models downloaded on first use; degrades to blur-score ranking offline), extracted using Intel QSV/VAAPI hardware *decode* when available, and by default seek to the nearest keyframe for speed (switchable to exact timestamps).
- **AI tagging** — a user-defined tag vocabulary and a priority-ordered list of provider entries (OpenRouter, Gemini, FAL, Mistral; any number, several per type allowed) with automatic fallback when an entry fails. Each assigned tag's score and the model that produced it are shown on cards and in the info panel.
  - **Tag Lab**: tagging a single file opens a synchronous one-shot dialog (no job queue, no batch API) for comparing provider entries — the images and prompt render immediately, then the model's raw reply, its full raw JSON, usage, and suggested tags are reviewable before applying. The raw response stays visible even when parsing it fails, so a bad response is self-diagnosable.
  - Tag Lab surfaces two per-model signals, both keyed by provider type + model name: an editable **$/1M-token price** (refreshable live from OpenRouter's public API, manual for the others) and a **rating** (per-tag like/dislike plus an applied-unchanged/with-edits/never KPI).
  - Tags live in three pools: the **AI vocabulary** (the only pool ever sent to a provider), **user-defined** tags (a short subjective list attached through a dedicated picker), and plain **ad-hoc** tags typed onto a file. All three are searchable and appear in suggestions, but only a pool's own Settings "add" flow populates it — a tag never silently joins the AI vocabulary. Manually assigned tags record 100% confidence, provider `manual`.
  - Every tag has its own background color, rendered identically everywhere, with a deterministic fallback for tags nobody has recolored.
  - What the model sees is configurable in Settings → Tagging (frame count, collage vs. separate images, resolution, request timeout), with a "preview what the model sees" button. Optional provider-side batch tagging for Gemini/Mistral is persisted the moment a batch is accepted, so it survives a restart.
  - API keys and SMB/WebDAV credentials live only in the git-ignored `backend/secrets.env`, never in the database or API responses.
- **Backend health & load indicator** — a pulsing status dot (green responding / amber slow / red unreachable, both timeouts configurable) plus a compact CPU/memory/SMB-network gauge with four click-cycled display modes. Settings → Performance adds a history chart of the same signals over a selectable 30 min/4h/12h/24h range.
- **Playback** — embedded HTML5 player over a Range-capable backend streaming proxy, or a copyable direct local/UNC path plus a raw-stream link; switchable per session.
- **Similar files** — perceptual-hash signatures computed as a best-effort side effect of preview generation (videos) or of tagging/a lazy check (images), surfaced through a per-file "Similar" action. A video and an image are never compared against each other.
- **Backup & maintenance** — manual backup/restore of library metadata as zip packages in the source's `.video-archive/backups/` with configurable retention (the same mechanism runs automatically on a source switch), plus stale-record cleanup and SQLite `VACUUM`/`ANALYZE`.
  - Settings → Backup also has an **application-settings export/import**: a JSON bundle of every app-wide setting not tied to one source. Provider entries (they carry plaintext API keys) and sources are deliberately excluded.

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
- Backend: `http://127.0.0.1:8010` (health at `/api/health`, app info at `/api/app/info`)

Both dev servers listen on `0.0.0.0`, not just loopback, so the app is also reachable from another device on the same network (e.g. a phone) or connected to it via the phone's own hotspot — open Settings → Network for the address(es) to use and setup instructions for both cases. There is no authentication, so this reachability is scoped to trusted local/private networks only.

Frontend and backend also remain independently runnable from their own directories (`npm run dev` inside `frontend/` or `backend/`).

## Kubernetes Deployment

The same repository also deploys onto the home k3s cluster through a GitOps loop: a push to `main` builds backend/frontend images into GHCR and ArgoCD rolls them out (namespace `video-archive`, `https://video-archive.192.168.1.97.nip.io`). The backend can be switched between the general-purpose node and the powerful `role=compute` node via one Helm value. The local dev loop above is unaffected. The frontend is also installable as a PWA on Android from that HTTPS address — see [docs/deployment.md#installing-as-a-pwa-on-android](docs/deployment.md#installing-as-a-pwa-on-android). See [docs/deployment.md](docs/deployment.md).

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
- [`docs/webdav-setup.md`](docs/webdav-setup.md) — configuring a `webdav` source, including Synology DSM's WebDAV Server.

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
- If a dev session already has this connected as a saved source (common across sessions, since source config persists in the SQLite db), you can safely add another saved source pointing at a scratch subfolder and switch to it (Settings → Saved sources) — switching backs up and restores each source's own files/tags automatically, so nothing is lost. Only in-progress job history isn't preserved across a switch, so let any running jobs finish first if that matters.
- Since this directory is git-ignored and persists locally across sessions, it can accumulate folders beyond the `Foscam`/`ReolinkFront` samples shown above (e.g. real personal footage copied in for a specific manual test). Check the folder/file names in the currently connected source before browsing into it for verification — don't assume it only contains the documented camera samples.
