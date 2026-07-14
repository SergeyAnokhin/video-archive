# Architecture

Video Archive is a local-first, Windows-targeted web application: a Vite + React + TypeScript frontend and a FastAPI + SQLite backend, started together from the repository root (`npm run dev`). The backend can hold any number of saved video *sources* (a local folder or an SMB share), one of which is active at a time; it scans the active one into a local metadata database and runs all heavy work (conversion, preview generation, AI tagging, backup) as background jobs. This document describes the current shape of the system and the conventions that cut across it; for the file-by-file map see [`code-map.md`](code-map.md).

## Components

```text
frontend (Vite dev server :5173)
   |  /api proxy
   v
backend (FastAPI :8000)
   |-- routers/            HTTP API (thin; validation + delegation)
   |-- jobs/               background job handlers + two-lane worker (CPU + network)
   |-- sources/            uniform file-access layer (local | smb)
   |-- providers/          AI tagging provider clients (OpenRouter, Gemini, FAL, Mistral)
   |-- db.py               SQLite via SQLAlchemy Core, schema-versioned; `sources` table holds every saved source
   |-- preview_cache/      local GIF cache, one folder per source id -- GIFs never written to the source
   `-- secrets.env         git-ignored; per-source SMB credentials + provider API keys
        |
        v
   source root (local path or SMB share) -- whichever saved source is currently active
     <video>.mp4
     <video>.jpg                 JPEG collage, written next to the video
     .video-archive/backups/    backup packages on the source itself (survive switching away)
```

- **Frontend** (`frontend/src/`): a single library screen (collapsible directory tree, closed by default, + card grid) plus modals (Settings, Jobs, Log Viewer, playback, per-file info panel, convert/preview/tag dialogs). The top bar hosts the scoped search box (`tag:`/`file:`/`path:` prefixes, or all three at once — see [`code-map-frontend.md`](code-map-frontend.md)'s `LibrarySearchBox.tsx`/`SearchResults.tsx` entries) and all global icon actions; file cards expose only two actions — click the thumbnail to play, click the "i" overlay button for every other per-file operation. Shared state lives in React contexts (`src/context/`); jobs are polled every 1.5 s, logs stream over SSE. EN/RU i18n via i18next; eight theme presets (Strict, Playful, Casino, Neon Night, Toxic Arcade, Cyber Violet, Vivid Glam, Mono Ice) via CSS variables on `data-theme`.
- **Backend routers** (`backend/app/routers/`): one module per API area. Routers stay thin — domain logic lives in the sibling top-level modules (`conversion.py`, `preview.py`, `tagging.py`, `backup.py`, ...).
- **Job system** (`backend/app/jobs/`): `jobs`/`job_items` tables driven by a two-lane worker (post-V1, user request — was a single sequential worker thread) with a `queued → running → paused → completed|failed|cancelled` state machine, cooperative cancellation *and* pause/resume, live per-item progress, structured event log (`app_events`) streamed over SSE, and 24-hour retention for finished jobs. One lane runs CPU-bound job types (`rescan`, `convert`, `preview`, `cleanup`, `optimize_db`, `backup`, `restore` — one at a time, since they all compete for local ffmpeg/disk), the other runs `tag` (network-bound, calls an external AI provider API) — so at most one CPU job and one tag job run at the same time. Pausing a running job (job types with a per-item loop only) frees its lane for the next queued job of that lane once the handler notices the request between items.
- **Sources layer** (`backend/app/sources/`): every file access — scan, conversion, tagging, playback, backup — goes through this layer instead of raw filesystem paths, so the same code paths serve both `local` and `smb` protocols regardless of which saved source is active (preview generation reads a video the same way and writes the JPEG collage back next to it; only the companion GIF goes to the local cache instead, see `preview_cache.py`). SMB uses `smbclient` (from `smbprotocol`) with retry-on-reconnect; credentials are stored per source (`backend/app/secrets_store.py`), not shared across sources.
- **Providers layer** (`backend/app/providers/`): one client per AI provider type behind a common registry; builds vision requests from sampled-frame collages plus the user's tag vocabulary, parses scored tags. Provider configuration is a user-managed, priority-ordered list of entries (`backend/app/provider_entries.py`, any number per type) rather than a single fixed choice — the tag job tries enabled entries in priority order and falls back to the next one if an entry errors out, so one bad key or outage doesn't stop tagging. Gemini/Mistral optionally support provider-side batch tagging (scoped to the single highest-priority batch-capable entry) with per-file fallback.

## Cross-cutting conventions

| Convention | Where |
| --- | --- |
| All file access goes through `app/sources/`, never raw `pathlib`/UNC paths | `backend/app/sources/` |
| Secrets (SMB credentials — one key pair per saved source, provider API keys) live only in git-ignored `backend/secrets.env`; never in the DB, never echoed by the API | `backend/app/secrets_store.py` |
| Conversion replaces the source file only after ffprobe validation of the temp output; test mode preserves the original as `<name>.original.<ext>` | `backend/app/conversion.py` |
| The JPEG collage is written next to its video on the source (`<name>.jpg`) and only shown in the per-file info panel (static view), never as a grid/list-view thumbnail; its companion animated GIF (user request, for grid/list-view hover previews) is cached locally per source instead, never written back to the source; folders get an animated GIF only, `folder-preview.gif`, cycling frames sampled from different videos/subfolders (`preview.diverse_video_frame_plan()`) | `backend/app/jobs/preview.py`, `backend/app/preview_cache.py`, `backend/app/preview.py`, `scan.py` |
| Switching the active source backs the outgoing one up onto its own disk before wiping local `directories`/`files`/`file_tags`/job history, then auto-restores the incoming source's own backup if one exists (scoped data only — global settings tables are never touched by a switch) | `backend/app/source_switch.py`, `backend/app/backup.py` |
| The collage/GIF canvas aspect ratio (width/height) is a global setting resolved once per preview job: `standard` (4:3), `phone-portrait` (9:19.5), `phone-landscape` (19.5:9, **default**, user request — fills a mobile card's width without letterboxing), `ultra-wide` (21:9), or `custom` | `backend/app/preview_settings.py` |
| GIF preview size/quality is a separate global setting (`gif_max_width`/`gif_colors`, defaults 640px/64 colors, user request) from the JPEG collage's own fixed `CANVAS_WIDTH` — GIFs are only ever shown small (grid/list-view hover thumbnails), so they stay deliberately lower-fidelity to load fast | `backend/app/preview_settings.py`, `backend/app/preview.py` |
| `.original.` / `.variant-` artifacts are excluded from directory-scope jobs | job handlers in `backend/app/jobs/` |
| The DB is schema-versioned; migrations run in `init_db()` | `backend/app/db.py` |
| UI strings exist in both `en.json` and `ru.json`, always in parity | `frontend/src/i18n/locales/` |
| Incomplete-state "lamp" dots share one visual convention: 8px circle, colored per category when incomplete (`--color-warning` conversion, `--color-accent` preview, `--color-danger` tags), `--color-success` once done | `directory-tree__dot`/`library-card__dot`/`file-info-panel__dot` in `frontend/src/components/*.css` |
| Settings are grouped into singletons (preview, tagging, playback, backup, interface) with `GET`/`PUT` endpoints applied immediately | `backend/app/*_settings.py` |
| A literal-path route (e.g. `GET /jobs/batch-submissions`) must be declared *before* a same-method `/{id}`-style route in the same router, or FastAPI/Starlette matches the `{id}` route first and swallows the literal path as an id value | `backend/app/routers/jobs.py` (`batch-submissions` routes sit above `GET /jobs/{job_id}`) |
| Standalone images are first-class library items (post-V1, user request): tag (incl. AI auto-tagging), view full-screen, and "similar" all apply, but conversion and preview/collage generation stay video-only. `is_image_supported` is an independent flag on `files`, parallel to `is_video_supported`, not a single enum — listing/status/tag-scope queries widen to `(is_video_supported = 1 OR is_image_supported = 1)`, conversion/preview/tune scoping stays `is_video_supported = 1` only | `backend/app/media.py`, `backend/app/db.py` (migration 25), `backend/app/tagging.py`'s `build_tagging_images_for_file()`, `backend/app/similarity.py`'s `compute_image_signature()` |
| `SourceAccess.direct_path()` (a raw local/UNC path) is only for cheap reads that don't seek/re-read — ffprobe, streaming. Anything that does repeated seeks or heavier processing (frame extraction, ffmpeg encode) uses `local_copy()` instead, which is a no-op passthrough for `local` but downloads to a temp file for `smb` (unreliable/slow over repeated UNC seeks) | `backend/app/sources/access.py`; compare `routers/files.py`'s media-info endpoint (`direct_path`) vs `jobs/tag.py`/`jobs/convert.py` (`local_copy`) |
| A domain module that can fail in more than one user-facing way raises one exception class carrying a `code` + `message`; the router catches it once and maps `code` to an HTTP status via a small dict. Every synchronous provider-call failure (bad/missing key, HTTP error, unparseable response) maps to **400**, never 502/other, regardless of which layer actually raised it | `backend/app/file_ops.py` (`FileOperationError`) / `backend/app/tag_lab.py` (`TagLabError`) + their routers' `_..._http_error()` helpers; `backend/app/routers/providers.py`'s `_list_models_error()` for the provider-call convention |
| "Tuning" is a reserved term for FFmpeg encode-parameter sweeps (`FileTuneModal.tsx`, `tags.assign_tuning_parameter_tags()`, `provider_name='tuning'`) — an unrelated feature must not reuse the word (in UI copy, identifiers, or `provider_name`), since it already has a specific, documented meaning. Similarly "preview" already means two distinct things (the static JPEG collage vs. the animated GIF, row above) | `frontend/src/components/FileTuneModal.tsx`, `backend/app/tags.py` |

## Key flows

- **Switch source**: pick an existing saved source (Settings → Saved sources) or configure a new one (Settings → Source) → outgoing source backed up onto its own disk → local `directories`/`files`/`file_tags`/job history wiped → incoming source activated and, if it has a backup of its own, auto-restored (scoped data only) → synchronous scan reconciles any drift since that backup.
- **Convert**: pick a saved conversion profile → job runs ffmpeg to a temp file → ffprobe validation → replace original on success only. File-scope variant comparison sweeps parameter combinations into `<name>.variant-*.mp4` outputs in test mode.
- **Preview**: sample interior frames → rank with local face/person detection (ONNX models in git-ignored `backend/models/`, downloaded on first use; degrades to blur-score ranking offline) → composite a grid collage per the configured layout preset.
- **Tag**: directory/source scope still runs as a background job — sample frames → collage (or individual frames) + tag vocabulary → the first working provider entry in priority order (automatic fallback to the next one on failure) → store top-N scored tags, replacing the previous set. Single-file tagging from the info panel instead opens **Tag Lab** (`app/tag_lab.py`, `TagLabModal.tsx`): one user-picked provider entry, no fallback, no job — the images/prompt/raw response/usage are returned synchronously for review, and nothing is written until the user applies the (optionally edited) tag list.
- **Playback**: embedded HTML5 player against a Range-capable backend streaming proxy, or a copyable direct local/UNC path — switchable per session.
