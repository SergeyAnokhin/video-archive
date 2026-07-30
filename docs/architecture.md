# Architecture

Video Archive is a local-first, Windows-targeted web application: a Vite + React + TypeScript frontend and a FastAPI + SQLite backend, started together from the repository root (`npm run dev`). The backend can hold any number of saved video *sources* (a local folder, an SMB share, or a WebDAV share), one of which is active at a time; it scans the active one into a local metadata database and runs all heavy work (conversion, preview generation, AI tagging, backup) as background jobs. This document describes the current shape of the system and the conventions that cut across it; for the file-by-file map see [`code-map.md`](code-map.md).

## Components

```text
frontend (Vite dev server :5173)
   |  /api proxy
   v
backend (FastAPI :8010)
   |-- routers/            HTTP API (thin; validation + delegation)
   |-- jobs/               background job handlers + two-lane worker (CPU + network)
   |-- sources/            uniform file-access layer (local | smb | webdav)
   |-- providers/          AI tagging provider clients (OpenRouter, Gemini, FAL, Mistral)
   |-- db.py               SQLite engine + init; migrations.py holds the schema statements
   `-- secrets.env         git-ignored; per-source SMB credentials + provider API keys
        |
        v
   source root (local path, SMB share, or WebDAV share) -- whichever is active
     <video>.mp4
     <video>.jpg                       JPEG collage, written next to the video
     .video-archive/backups/           backup packages on the source itself
     .video-archive/previews/          animated GIF previews (per-file + folder-preview.gif)
```

- **Frontend** (`frontend/src/`): a single library screen (collapsible directory tree + card grid) plus modals (Settings, Jobs, Log Viewer, playback, per-file info panel, convert/preview/tag dialogs). The top bar hosts the scoped search box (`tag:`/`file:`/`path:` prefixes) and all global icon actions; file cards expose two actions — click the thumbnail to play, click "i" for everything else. Shared state lives in React contexts (`src/context/`); jobs are polled every 1.5 s, logs stream over SSE. EN/RU i18n via i18next; eight theme presets via CSS variables on `data-theme`.
- **Backend routers** (`backend/app/routers/`): one module per API area. Routers stay thin — domain logic lives in the sibling top-level modules (`conversion.py`, `preview.py`, `tagging.py`, `backup.py`, …).
- **Job system** (`backend/app/jobs/`): `jobs`/`job_items` tables driven by a two-lane worker with a `queued → running → paused → completed|failed|cancelled` state machine, cooperative cancellation and pause/resume, live per-item progress, and a structured event log (`app_events`) streamed over SSE with 24-hour retention. One lane runs the CPU-bound job types (`rescan`/`rescan_with_media_info`, `convert`, `preview`, `cleanup`, `optimize_db`, `backup`, `restore`) one at a time since they compete for local ffmpeg/disk; the other runs network-bound `tag`. At startup `main.py`'s lifespan fails any job left `running` by a previous process (`service.reap_orphaned_jobs()`), setting a dedicated `jobs.interrupted` flag so the frontend can tell a backend restart apart from a real error like an ffmpeg failure.
- **Sources layer** (`backend/app/sources/`): every file access — scan, conversion, tagging, playback, backup — goes through this layer instead of raw filesystem paths, so the same code paths serve `local`, `smb`, and `webdav` alike. SMB uses `smbclient` (from `smbprotocol`) with retry-on-reconnect; WebDAV is a thin hand-rolled `httpx` client (`PROPFIND`/`GET`/`PUT`/`MKCOL`/`DELETE`/`MOVE`, no third-party library). Credentials are stored per source (`backend/app/secrets_store.py`), not shared.
- **Providers layer** (`backend/app/providers/`): one client per AI provider type behind a common registry; builds vision requests from sampled-frame collages plus the user's tag vocabulary and parses scored tags. Configuration is a priority-ordered list of entries (`backend/app/provider_entries.py`, any number per type) — the tag job falls back to the next entry when one errors, so a bad key doesn't stop tagging. Gemini/Mistral optionally support provider-side batch tagging with per-file fallback.

## Cross-cutting conventions

Each row states the rule and where it lives; implementation depth is in the linked file and its [code-map](code-map.md) entry.

| Convention | Where |
| --- | --- |
| All file access goes through `app/sources/`, never raw `pathlib`/UNC paths | `backend/app/sources/` |
| Secrets (per-source SMB/WebDAV credentials, provider API keys) live only in git-ignored `backend/secrets.env` — never in the DB, never echoed by the API | `backend/app/secrets_store.py` |
| `SourceAccess.direct_path()` (raw local/UNC path) is only for cheap sequential reads — streaming. Anything running ffprobe/ffmpeg as an external process, or doing repeated seeks, uses `local_copy()` instead (a no-op for `local`, a temp download for `smb`). An SMB source can opt into `direct_access_enabled` so `local_copy()` yields the UNC path directly when the OS has its own session to that host, with silent fallback | `backend/app/sources/access.py`, `sources/smb_backend.py`, `sources/windows_unc.py` |
| `smb_backend.py`'s `_smb_lock` serializes every SMB call in the process; a call stuck on a hung socket wedges all others until restart. `get_lock_status()`/`force_release_lock()` back the Settings → Source "release lock" button, which swaps in a fresh lock (the stuck thread is abandoned, not freed). The swap only helps callers arriving *after* it: threads already parked on the retired lock stay parked for the life of the process and are reported as `orphaned_waiters` | `backend/app/sources/smb_backend.py`, `frontend/src/components/SourceSection.tsx` |
| `webdav` has no `_smb_lock` equivalent and no direct-access fast path — `httpx` pools per request, so a stuck call blocks only its own caller. Its one opt-in setting is `verify_ssl` (default on), for a self-signed HTTPS certificate | `backend/app/sources/webdav_backend.py`, [`webdav-setup.md`](webdav-setup.md) |
| Conversion replaces the source file only after ffprobe validation of the temp output, and only if it shrinks the source by at least the configured minimum percentage (default 20%; otherwise skipped and logged, source untouched). Test mode preserves the original as `<name>.original.<ext>`; mp4 output always gets `-movflags +faststart` | `backend/app/conversion.py`, `jobs/convert.py`, `conversion_settings.py` |
| `.original.` / `.variant-` artifacts are excluded from directory-scope jobs | job handlers in `backend/app/jobs/` |
| "Preview" means two distinct artifacts: the JPEG collage written next to its video (`<name>.jpg`, shown only in the info panel) and the animated GIF written into `.video-archive/previews/` (grid/list hover thumbnails, plus `folder-preview.gif` per folder). Canvas aspect ratio and GIF size/quality are separate global settings | `backend/app/jobs/preview.py`, `preview.py`, `preview_render.py`, `preview_assets.py`, `media.py`, `preview_settings.py` |
| Preview frame extraction downscales to `EXTRACT_MAX_WIDTH` during ffmpeg's decode and seeks to the nearest keyframe by default (`frame_seek_mode`, switchable to exact). Other call sites (AI tagging, similarity, thumbnail picking) don't pass those and keep source resolution / exact timestamps | `backend/app/preview_frames.py`, `preview_settings.py` |
| Switching the active source backs the outgoing one up onto its own disk, wipes local scoped data, then auto-restores the incoming source's backup if any. Global settings tables are never touched. Resubmitting the same `(protocol, root_path)` is a **reconnect** — connection params update in place, no backup, no wipe, no rescan | `backend/app/source_switch.py`, `backup.py`, `routers/source.py` |
| `GET /source/status` reports live connection state (including whether SMB direct access is actually in effect) without writing to the DB, so it's safe to poll passively | `backend/app/routers/source.py` (`_check_connection_status()`) |
| `claim_next_queued_job()` selects and marks a job `running` in one atomic `UPDATE ... WHERE status = 'queued' ... RETURNING *` — a separate `SELECT`-then-write lets two lanes (or a stray second backend process) both start the same job | `backend/app/jobs/service.py` |
| The DB is schema-versioned; migrations are appended to `MIGRATIONS` (never edited once applied) and run in `init_db()` | `backend/app/migrations.py`, `db.py` |
| Settings are grouped into single-row singleton tables (never a generic key-value table) with `GET`/`PUT` endpoints applied immediately. Step-by-step: [development.md § Recipe](development.md#recipe-adding-a-global-settings-singleton) | `backend/app/*_settings.py` |
| An expensive-to-compute field on a directory-listing endpoint (status rollup, top tags) is opt-in via its own `include_*` query param, off by default | `backend/app/routers/tree.py`, `routers/directories.py`, `status.py`, `tags.py` |
| `GET /files/{id}/media-info` is a read-through cache on `files` (`media_probed_at` distinguishes never-probed from probed-with-no-video-stream). Cache miss tries a header-only `mp4_probe` fast path first, then `local_copy()` + real ffprobe. Also populated free by `convert`/`preview` jobs, invalidated by `scan.upsert_file()` on size/mtime change | `backend/app/routers/files.py`, `mp4_probe.py`, `media_probe.py`, `scan.py` |
| A literal-path route (e.g. `GET /jobs/batch-submissions`) must be declared *before* a same-method `/{id}` route in the same router, or the `{id}` route swallows the literal path as an id | `backend/app/routers/jobs.py` |
| A domain module that can fail in several user-facing ways raises one exception class carrying `code` + `message`; the router maps `code` to an HTTP status via a small dict. Every synchronous provider-call failure maps to **400**, never 502 | `backend/app/file_ops.py`, `tag_lab.py` + their routers' `_..._http_error()` helpers |
| A provider's raw reply (`raw_text`/`raw_full_response`) is attached to `ProviderError` on *every* failure branch where the provider returned something, and threads unchanged through `TagLabError` → HTTP `detail.error` → the Tag Lab modal — so a parse failure stays self-diagnosable | `backend/app/providers/base.py`, each `providers/*.py`, `tag_lab.py`, `routers/tag_lab.py` |
| A provider client's `timeout` kwarg is keyword-only and defaults to `None`, meaning "use that module's own `TIMEOUT_SECONDS`", not "no timeout". Only Tag Lab passes an explicit value; background `tag`/batch jobs keep the constant | `backend/app/providers/*.py`, `providers/registry.py` |
| Tag Lab's sampled images are cached in-process only (`_image_cache`, lost on restart). A hit requires identical tagging settings and vocabulary; any difference silently rebuilds | `backend/app/tag_lab.py` |
| Tags live in three pools: **AI vocabulary** (`is_ai_vocabulary` — the only pool sent to a provider), **user-defined** (`is_user_defined`), and plain **ad-hoc** (neither flag). `list_tags(category=...)` is scoped to one managed pool; `list_used_tags()` deliberately spans all three | `backend/app/tags.py`, `migrations.py` |
| A tag's background `color` is a pool-agnostic `tag_catalog` attribute rendered through one shared component (`TagBadge.tsx`), with a deterministic hash fallback computed identically in `tags.resolve_tag_color()` and `utils/tagColor.ts` — the API never returns a null color | `backend/app/tags.py`, `frontend/src/components/TagBadge.tsx`, `utils/tagColor.ts` |
| Per-model price and rating data is keyed by `(provider_type, model_name)`, never by `provider_entries.id` — two entries pointing at the same model share one price and one rating | `backend/app/model_pricing.py`, `tag_lab_feedback.py` |
| Standalone images are first-class library items: tag (incl. AI), view, and "similar" apply; conversion and preview generation stay video-only. `is_image_supported` is an independent flag on `files`, parallel to `is_video_supported` | `backend/app/media.py`, `tagging.py`, `similarity.py` |
| "Tuning" is a reserved term for ffmpeg encode-parameter sweeps — an unrelated feature must not reuse the word in UI copy, identifiers, or `provider_name` | `frontend/src/components/FileTuneModal.tsx`, `backend/app/tags.py` |
| Every frontend backend call goes through the central client — `api()` throws `ApiError` carrying the backend `detail`, `tryApi()` resolves `null` for polling/best-effort, `rawApi()` returns the raw `Response`. No component calls `fetch('/api/...')` inline | [`frontend/src/api/client.ts`](../frontend/src/api/client.ts) |
| UI strings exist in both `en.json` and `ru.json`, always in parity | `frontend/src/i18n/locales/` |
| Incomplete-state "lamp" dots share one visual convention: 8px circle, colored per category when incomplete (`--color-warning` conversion, `--color-accent` preview, `--color-danger` tags), `--color-success` once done | `frontend/src/components/*.css` |

## Key flows

- **Switch source**: pick an existing saved source (Settings → Saved sources) or configure a new one (Settings → Source) → outgoing source backed up onto its own disk → local `directories`/`files`/`file_tags`/job history wiped → incoming source activated and, if it has a backup of its own, auto-restored (scoped data only) → synchronous scan reconciles any drift since that backup.
- **Convert**: pick a saved conversion profile → job runs ffmpeg to a temp file → ffprobe validation → replace original only if valid and it clears the configured minimum size-reduction percentage. File-scope variant comparison sweeps parameter combinations into `<name>.variant-*.mp4` outputs in test mode (exempt from the size check — a deliberate comparison output).
- **Preview**: sample interior frames → rank with local face/person detection (ONNX models in git-ignored `backend/models/`, downloaded on first use; degrades to blur-score ranking offline) → composite a grid collage per the configured layout preset, and render the companion GIF.
- **Tag**: directory/source scope runs as a background job — sample frames → collage (or individual frames) + tag vocabulary → the first working provider entry in priority order → store top-N scored tags, replacing the previous set. Single-file tagging from the info panel instead opens **Tag Lab** (`app/tag_lab.py`, `TagLabModal.tsx`): one picked entry, no fallback, no job, synchronous — `prepare` returns images/prompt alone, `run` adds the raw response and usage, and nothing is written until the user applies the (optionally edited) tag list.
- **Playback**: embedded HTML5 player against a Range-capable backend streaming proxy, or a copyable direct local/UNC path — switchable per session.
