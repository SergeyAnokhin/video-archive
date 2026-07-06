# Architecture

Video Archive is a local-first, Windows-targeted web application: a Vite + React + TypeScript frontend and a FastAPI + SQLite backend, started together from the repository root (`npm run dev`). The backend connects to one video *source* (a local folder or an SMB share), scans it into a local metadata database, and runs all heavy work (conversion, preview generation, AI tagging, backup) as background jobs. This document describes the current shape of the system and the conventions that cut across it; for the file-by-file map see [`code-map.md`](code-map.md).

## Components

```text
frontend (Vite dev server :5173)
   |  /api proxy
   v
backend (FastAPI :8000)
   |-- routers/            HTTP API (thin; validation + delegation)
   |-- jobs/               background job handlers + single sequential worker
   |-- sources/            uniform file-access layer (local | smb)
   |-- providers/          AI tagging provider clients (OpenRouter, Gemini, FAL, Mistral)
   |-- db.py               SQLite via SQLAlchemy Core, schema-versioned
   `-- secrets.env         git-ignored; SMB credentials + provider API keys
        |
        v
   source root (local path or SMB share)
     <video>.mp4, <name>.jpg, folder-preview.jpg
     .video-archive/backups/   backup packages on the source itself
```

- **Frontend** (`frontend/src/`): a single library screen (directory tree + card grid) plus modals (Settings, Jobs, Log Viewer, playback, convert/preview/tag dialogs). Shared state lives in React contexts (`src/context/`); jobs are polled every 1.5 s, logs stream over SSE. EN/RU i18n via i18next; Strict/Playful themes via CSS variables on `data-theme`.
- **Backend routers** (`backend/app/routers/`): one module per API area. Routers stay thin — domain logic lives in the sibling top-level modules (`conversion.py`, `preview.py`, `tagging.py`, `backup.py`, ...).
- **Job system** (`backend/app/jobs/`): `jobs`/`job_items` tables driven by a single sequential worker thread with a `queued → running → completed|failed|cancelled` state machine, cooperative cancellation, live per-item progress, structured event log (`app_events`) streamed over SSE, and 24-hour retention for finished jobs. Job types: `rescan`, `convert`, `preview`, `tag`, `backup`, `restore`, `cleanup`, `optimize_db`.
- **Sources layer** (`backend/app/sources/`): every file access — scan, conversion, preview, tagging, playback, backup — goes through this layer instead of raw filesystem paths, so the same code paths serve both `local` and `smb` protocols. SMB uses `smbclient` (from `smbprotocol`) with retry-on-reconnect.
- **Providers layer** (`backend/app/providers/`): one client per AI provider behind a common registry; builds vision requests from sampled-frame collages plus the user's tag vocabulary, parses scored tags. Gemini/Mistral optionally support provider-side batch tagging with per-file fallback.

## Cross-cutting conventions

| Convention | Where |
| --- | --- |
| All file access goes through `app/sources/`, never raw `pathlib`/UNC paths | `backend/app/sources/` |
| Secrets (SMB credentials, provider API keys) live only in git-ignored `backend/secrets.env`; never in the DB, never echoed by the API | `backend/app/secrets_store.py` |
| Conversion replaces the source file only after ffprobe validation of the temp output; test mode preserves the original as `<name>.original.<ext>` | `backend/app/conversion.py` |
| Preview collages are stored next to the video as `<name>.jpg`; folders get `folder-preview.jpg`; these are recognized as assets, not listed as files | `backend/app/preview.py`, `scan.py` |
| `.original.` / `.variant-` artifacts are excluded from directory-scope jobs | job handlers in `backend/app/jobs/` |
| The DB is schema-versioned; migrations run in `init_db()` | `backend/app/db.py` |
| UI strings exist in both `en.json` and `ru.json`, always in parity | `frontend/src/i18n/locales/` |
| Settings are grouped into singletons (preview, tagging, playback, backup, interface) with `GET`/`PUT` endpoints applied immediately | `backend/app/*_settings.py` |

## Key flows

- **Connect/replace source**: test connection → destructive-replace warning → wipe local metadata → synchronous scan → offer restore if backup packages are found in the source's `.video-archive/backups/`.
- **Convert**: pick a saved conversion profile → job runs ffmpeg to a temp file → ffprobe validation → replace original on success only. File-scope variant comparison sweeps parameter combinations into `<name>.variant-*.mp4` outputs in test mode.
- **Preview**: sample interior frames → rank with local face/person detection (ONNX models in git-ignored `backend/models/`, downloaded on first use; degrades to blur-score ranking offline) → composite a grid collage per the configured layout preset.
- **Tag**: sample frames → collage (or individual frames) + tag vocabulary → configured provider → store top-N scored tags, replacing the previous set.
- **Playback**: embedded HTML5 player against a Range-capable backend streaming proxy, or a copyable direct local/UNC path — switchable per session.
