# video-archive

Video Archive is a local-first, Windows-targeted web application for browsing a video directory source (local folder or SMB share), converting videos in bulk with ffmpeg, generating preview collages stored next to the videos, and tagging videos through external AI providers. A Vite + React + TypeScript frontend and a FastAPI + SQLite backend run together from the repository root; UI in English/Russian with eight theme presets (Strict, Playful, Casino, Neon Night, Toxic Arcade, Cyber Violet, Vivid Glam, Mono Ice).

## Capabilities

What the application does today (implementation details and file locations are in [docs/code-map.md](docs/code-map.md)):

- **Sources** — several saved sources (`local` folders or `smb` shares) at once, switchable from Settings → Source (configure/connect) and Settings → Saved sources (list, switch, forget) without losing each one's own data.
  - Switching away from a source backs it up automatically onto its own disk before wiping the local working copy; switching back auto-restores from that backup if one exists.
  - App-wide settings (tagging, preview, playback, etc.) are shared across every source and are never touched by a switch.
  - All file access (scan, convert, preview, tag, playback, backup) goes through the uniform [`backend/app/sources/`](backend/app/sources/) layer, so every feature behaves identically for both protocols.
- **Library UI** — directory tree, card grid, search, and a per-file info panel.
  - Collapsible directory tree (closed by default) showing only the active source's own folders (no source-name row at the top), with a name filter and expand-all/collapse-all buttons.
  - Card grid with animated GIF thumbnails; tag/name search with prefix autocomplete in the top bar.
  - Per-file info panel: media info via on-demand ffprobe plus all per-file actions (generate preview, tag, convert, tune, similar, move, delete).
  - A "Recent folders" button next to the breadcrumb quick-jumps (via clickable path crumbs, not just the deepest folder) to any of the last 10 distinct folders where a video was played or a file was moved to.
  - Prev/next navigation (on-screen buttons and Left/Right arrow keys) in the player, the image viewer, and the info panel walks the current folder's own sorted listing — or the search results' on-screen order while a search is active.
  - Clicking the info panel's still collage/thumbnail opens it in a fullscreen lightbox (the picture itself, not playback) with its own red delete button next to Close; a separate video-only "play" button in the info panel jumps into the same fullscreen player used from the grid, which also has its own red delete button.
  - Each folder in the tree and grid also shows its own top-5 most-used tags (user request), computed dynamically and recursively across every file in that folder's subtree — no caching, opt into it via `include_top_tags` on `GET /api/tree`/`GET /api/directories/children`.
  - Folders can be created, deleted (if empty), and starred as favorites — favorited folders and a recently-viewed-from-folder History both surface as one-click "move this video here" buttons (drilling into subfolders via a small popover when a favorite has any) in the player/info panel.
- **Standalone images** — a photo sitting in a video folder (anything not a video's own `<name>.jpg` preview collage) is a first-class library item too: it appears in the grid and search alongside videos, opens in a full-screen image viewer on click, and supports tagging (including AI auto-tagging — the image itself, not sampled frames, sized the same as a video frame), move, delete, and "similar" (compared only against other images). Conversion and preview/collage generation stay video-only.
- **Background jobs** — a two-lane worker (one CPU-bound lane, one network-bound lane for AI tagging) runs `rescan`, `convert`, `preview`, `tag`, `backup`, `restore`, `cleanup`, `optimize_db`.
  - Live per-item progress, cooperative cancellation and pause/resume; repeating a Cancel that hasn't been honored yet force-terminates an unresponsive job instead of waiting on it forever.
  - An SSE-streamed event log (Jobs modal + Log Viewer, with a "copy all" button and a per-stage progress breakdown — probing, frame extraction, encoding, rendering — for `convert`/`preview` items, also mirrored to the backend console); 24-hour retention for finished jobs.
  - Within a `convert`/`preview` job, a configurable number of files (or, for a single file, that file's own independent per-item work — variant encodes, preview frame extractions) run concurrently instead of one at a time (Settings → Performance).
- **Conversion** — saved ffmpeg profiles (codec, container, max dimension, CRF, drop-audio) with a safe-replace pipeline.
  - Safe replace: encode to a temp file, validate with ffprobe, replace the original only on success and only if it shrinks the source by at least a configurable minimum percentage (Settings → Conversion profiles, default 20% — most consequential for an unattended directory-scope batch job; otherwise the attempt is logged as a warning — console and job log — and skipped, keeping the original untouched; a tuning-sweep variant, see below, is exempt since it never replaces the source).
  - Resizing (`max_dimension`) only ever shrinks a source that already exceeds it — never upscales. mp4 output always gets `-movflags +faststart` so the embedded streaming player can start playback without waiting on the whole file.
  - Test mode preserves the original as `<name>.original.<ext>`; per-file tuning sweeps parameter ranges into `<name>.variant-<params>.mp4` outputs (defaulting to a sensible CRF/resolution range out of the box) and can promote a variant's parameters into a saved profile. `.original.`/`.variant-` artifacts are excluded from bulk jobs.
- **Previews** — two distinct kinds, configured on separate Settings tabs.
  - The **collage**: a JPEG grid written next to its video on the source (`<name>.jpg`) and shown only in the per-file info panel's static view, never as a grid/list thumbnail. Its grid layout is edited in a construction-set editor with presets and a live preview.
  - The **animated preview**: a GIF (per file, plus `folder-preview.gif` recursively per folder) shown on grid hover thumbnails. Its source mode is configurable — still frames or short video-clip bursts per segment — with adjustable segment duration and an optional crossfade transition.
  - The GIF is written into the source's own technical folder (`.video-archive/previews/`, [`backend/app/media.py`](backend/app/media.py)), the same place as the JPEG collage and metadata backups — it travels with the source instead of living on the backend. Settings → Saved sources shows the active source's GIF size/file count with a one-click clear ([`backend/app/preview_assets.py`](backend/app/preview_assets.py); only ever available for the active source, since computing/clearing needs a live connection).
  - Frames are ranked by local face/person detection (ONNX models downloaded on first use; degrades to blur-score ranking offline).
- **AI tagging** — a user-defined tag vocabulary and a priority-ordered list of provider entries (OpenRouter, Gemini, FAL, Mistral; any number, including several per type) with automatic fallback when an entry fails; each assigned tag's score and the provider/model that produced it are shown on library cards and in the file info panel.
  - Standalone images are tagged the same way — the image itself is sent to the vision model, sized like a single video frame — so a directory-scope tag job covers both kinds together.
  - **Tag Lab**: tagging a single file from the info panel's "Tags" button opens a synchronous one-shot dialog (no job queue, no batch API) for comparing provider entries — pick one, run it (the images sent and the prompt render immediately, before the model responds), then review the model's raw reply text plus its full raw JSON response (token usage and other technical fields included) and the suggested tags before applying or cancelling; directory-scope tagging is unaffected.
  - The raw reply/JSON stays visible (collapsed by default) even when interpreting the response fails, whenever the provider actually returned something (user request — self-diagnose a parse failure like "Unexpected Gemini response shape" from what the model actually said), and the run/prepare calls are wrapped in a client-side timeout so the dialog can't wait on "waiting for the model's response…" forever. Re-running against the same file reuses that file's last-sampled images instead of re-sampling them, as long as the tagging settings/vocabulary haven't changed since.
  - Tag Lab also surfaces two independent per-model signals (aggregated by provider type + model name, shared across every provider entry pointing at the same model) to help pick a good one, both shown compactly next to the model picker:
    - an editable, sourced **$/1M-token price** (`backend/app/model_pricing.py`) — refreshable live from OpenRouter's public pricing API for OpenRouter models, manually entered/corrected for Gemini/Mistral (no machine-readable pricing API), shown and editable both in Tag Lab and in a Settings → AI providers pricing table;
    - a **rating** (`backend/app/tag_lab_feedback.py`): like/dislike on each suggested tag right in the result list (independent of Apply), plus a separate apply-behavior KPI (applied unchanged / applied with edits / never applied) across every run.
  - Tags live in three pools (user request): the **AI vocabulary** above (Settings-managed, the only pool ever sent to a vision provider), **user-defined tags** (their own separate Settings section — a short, purely subjective list a vision model could never determine, e.g. personal ratings or moods — attached to a file through a dedicated picker button on the playback/image-viewer screen and in the info panel, pick-existing or create-new), and plain **ad-hoc** tags (typed directly onto a file from the info panel's or playback screen's free-text add field — join neither managed pool, never sent to the AI).
  - Every pool is fully searchable and shows up in "type a tag" suggestions alike; only Settings' own "add" flow for a given pool actually populates it, so a tag never silently joins the AI vocabulary or the user-defined list just because it was used somewhere. Encode-parameter tags on a tuning-sweep variant (e.g. "640px", "H265" — see Conversion above) are the same kind of plain ad-hoc tag: ordinary and removable on that one file, but excluded from Settings' AI-vocabulary list and every AI-tagging prompt. Manually assigned tags (any pool) are recorded at 100% confidence, provider `manual`.
  - Every tag has its own background color (user request), shown identically everywhere it's rendered — pick a free color for it (a small swatch next to its name in Settings) and its label text automatically stays black or white for readability against whatever shade it ends up; a tag nobody has recolored yet gets a stable, deterministic color instead of looking uncolored.
  - What gets sent to the vision model is configurable in Settings → Tagging: how many interior frames are sampled per video, whether they're combined into one collage or sent as separate images, one shared per-frame pixel resolution (the collage's total size scales with its grid, so switching modes never needs a resolution recompute), and Tag Lab's direct-call request timeout (default 30s) — a "preview what the model sees" button renders the current settings against the most-recently-viewed video so the real output is visible before saving.
  - Optional provider-side batch tagging for Gemini/Mistral is persisted the moment a batch is accepted (before polling starts) so it survives a service restart — polled every 30s, resumable, and viewable/forgettable from a Jobs → Batch jobs modal. Settings → AI providers also shows a usage-statistics table (calls, tokens, estimated cost per model).
  - API keys and SMB credentials live only in the git-ignored `backend/secrets.env`, never in the database or API responses.
- **Playback** — embedded HTML5 player over a Range-capable backend streaming proxy, or a copyable direct local/UNC path plus a clickable raw-stream link (opens the bare backend stream response in a new tab, no app UI); switchable per session.
- **Similar files** — perceptual-hash signatures computed as a best-effort side effect of preview generation for videos (or of tagging, or a lazy on-demand check, for standalone images), surfaced through a per-file "Similar" action; a video and an image are never compared against each other.
- **Backup & maintenance** — manual backup/restore of the library metadata as zip packages in the source's `.video-archive/backups/` with configurable retention (the same mechanism also runs automatically in the background when switching between saved sources, see Sources above); stale-record cleanup and SQLite `VACUUM`/`ANALYZE` actions.
  - Settings → Backup also has an **application-settings export/import**: a downloadable JSON bundle of every app-wide setting not tied to one source — tags (both pools), conversion profiles, preview layouts, and the conversion/preview/playback/tagging/backup/interface/performance settings singletons. Provider entries (their own export, since it carries plaintext API keys) and sources/saved sources are deliberately excluded.

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

Both dev servers listen on `0.0.0.0`, not just loopback, so the app is also reachable from another device on the same network (e.g. a phone) or connected to it via the phone's own hotspot — open Settings → Network for the address(es) to use and setup instructions for both cases. There is no authentication, so this reachability is scoped to trusted local/private networks only.

Frontend and backend also remain independently runnable from their own directories (`npm run dev` inside `frontend/` or `backend/`).

## Kubernetes Deployment

The same repository also deploys onto the home k3s cluster through a GitOps loop: a push to `main` builds backend/frontend images into GHCR and ArgoCD rolls them out (namespace `video-archive`, `https://video-archive.192.168.1.97.nip.io`). The backend can be switched between the general-purpose node and the powerful `role=compute` node via one Helm value. The local dev loop above is unaffected. See [docs/deployment.md](docs/deployment.md).

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
- If a dev session already has this connected as a saved source (common across sessions, since source config persists in the SQLite db), you can safely add another saved source pointing at a scratch subfolder and switch to it (Settings → Saved sources) — switching backs up and restores each source's own files/tags automatically, so nothing is lost. Only in-progress job history isn't preserved across a switch, so let any running jobs finish first if that matters.
- Since this directory is git-ignored and persists locally across sessions, it can accumulate folders beyond the `Foscam`/`ReolinkFront` samples shown above (e.g. real personal footage copied in for a specific manual test). Check the folder/file names in the currently connected source before browsing into it for verification — don't assume it only contains the documented camera samples.
