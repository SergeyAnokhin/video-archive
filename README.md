# video-archive

Video Archive is a local-first Windows-targeted application for browsing one remote video source at a time and later adding recursive conversion, preview generation, tagging, settings, and maintenance workflows. The current repository state now includes real conversion and preview foundations: a React frontend, a Python backend, and a root npm developer entrypoint that starts both together.

## Current Bootstrap Status

Implemented today:

- root `npm.cmd run dev` orchestration
- frontend shell with backend connectivity check
- backend `GET /api/health`
- backend `GET /api/app/info`
- backend source configuration endpoints:
  - `GET /api/source`
  - `PUT /api/source`
  - `POST /api/source/test-connection`
  - `GET /api/local-directories`
- backend source reconnect endpoint:
  - `POST /api/source/reconnect`
- backend source scan and browse endpoints:
  - `GET /api/tree`
  - `GET /api/files`
  - `GET /api/files/{file_id}`
  - `GET /api/files/{file_id}/playback`
  - `GET /api/files/{file_id}/content`
  - `GET /api/conversion-profiles`
  - `GET /api/jobs`
  - `GET /api/jobs/{job_id}`
  - `GET /api/jobs/{job_id}/items`
  - `GET /api/logs`
  - `GET /api/logs/stream`
  - `POST /api/jobs/scan-source`
  - `POST /api/jobs/rescan-directory`
  - `POST /api/jobs/convert-directory`
  - `POST /api/jobs/preview-directory`
  - `POST /api/jobs/tag-directory`
  - `POST /api/jobs/convert-file`
  - `POST /api/jobs/preview-file`
  - `POST /api/jobs/tag-file`
  - `POST /api/jobs/tune-file`
  - `POST /api/conversion-profiles`
  - `POST /api/jobs/{job_id}/cancel`
  - `POST /api/jobs/{job_id}/restart`
- backend local SQLite schema initialization on startup
- backend local secret file storage outside the main metadata database
- persisted directory and file metadata from scan results
- backend async job queue foundation with persistent job items and structured app events
- saved conversion profile bootstrap with a default `H.265` / `MP4` profile
- saved conversion profiles can now also be created from the UI and from successful tuning results
- real conversion jobs for file and recursive directory scopes with temp output, lightweight validation, production replacement, and separate test outputs
- real tuning jobs for a single file with dimension, quality, and codec sweeps that always write separate outputs and can be promoted into saved conversion profiles
- real preview jobs for file and recursive directory scopes with local frame sampling, local face/body prioritization, persisted preview assets, and directory collage generation
- real closed-vocabulary tagging jobs for file and recursive directory scopes with configurable sampled-frame count, stored confidence scores, provider-backed inference, and provider-side batch preference
- preview settings persistence with saved presets, live layout preview, selectable aspect ratios including Samsung S24 portrait and ultrawide presets, and a dedicated preview section in the settings UI
- playback settings persistence with embedded modal playback and external file-link opening when supported by the local environment
- tagging settings persistence with allowed vocabulary editing, provider selection, batch preference, and separate provider configuration with API keys stored outside the main database
- frontend source settings flow with backend-local folder browsing, repo test-archive shortcuts, test, save, reconnect, scan, rescan, preview display, tag display, tagging/provider settings, playback settings, conversion profile creation, a video details modal, a dedicated log viewer, a tuning workflow modal, and a jobs modal with detail, items, and live event updates
- frontend RU/EN chrome copy switching, icon-first action buttons via `lucide-react`, and three visual presentation modes from strict to playful/casino-leaning while keeping the same responsive layout

Not implemented yet:

- protocol-native remote enumeration beyond backend-accessible source paths
- backup and maintenance settings workflows

## Local Run

### Prerequisites

- Node.js 20+
- Python 3.11+

### Install dependencies

From the repository root in Windows Terminal or PowerShell:

```powershell
npm.cmd install
npm.cmd install --prefix frontend
```

### Start frontend and backend together

```powershell
npm.cmd run dev
```

- Frontend: `http://127.0.0.1:18673`
- Backend: `http://127.0.0.1:18637`

### Start frontend only

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

### Start backend only

```powershell
cd backend
npm.cmd run dev
```

The backend-local npm wrapper runs:

```powershell
python -m app.main
```

On startup the backend now also prints the resolved database and secrets paths. Unexpected request-time exceptions are written to the same terminal with a Python stack trace, request method, and request path.

### Backend local data and config

On first startup, the backend creates local development state under `backend/.local/`:

- `video_archive.db` for metadata
- `secrets.json` for source credentials stored outside the main metadata database

For the current browsing flow, `root_path` must point to a directory that is directly accessible from the backend machine, such as a local path or a reachable UNC share. The source settings screen now supports a `Local folder` mode with a backend-driven directory browser for test libraries on the same machine.

### Recommended local test archive

For UI checks, preview tuning, and browse-flow validation, use the repository-local test archive at [`test-data/VideoArchive`](test-data/VideoArchive). The source settings screen now exposes backend-local shortcuts for:

- the repository test archive
- the `backend/` folder
- the current backend local-data folder

The intent is visual and workflow verification only. Test runs should preserve the sample files rather than mutate them in place unless you explicitly choose a production conversion mode against another library.

Optional local overrides can be placed in `backend/.env.local`. Start from [`backend/.env.example`](backend/.env.example) and set values such as:

- `VIDEO_ARCHIVE_HOST`
- `VIDEO_ARCHIVE_PORT`
- `VIDEO_ARCHIVE_DATA_DIR`
- `VIDEO_ARCHIVE_DB_PATH`
- `VIDEO_ARCHIVE_SECRETS_PATH`

The default local ports are intentionally non-standard to avoid collisions with other local projects:

- frontend: `127.0.0.1:18673`
- backend: `127.0.0.1:18637`

If you still need a different backend port, set `VIDEO_ARCHIVE_PORT` before starting `npm.cmd run dev`. The frontend Vite proxy follows the same `VIDEO_ARCHIVE_PORT` value instead of hardcoding the backend target.

### Run backend tests

```powershell
npm.cmd run test --prefix backend
```

The backend test package now includes `backend/tests/__init__.py`, and the backend npm script uses unittest discovery with `-t .` so local `app` imports resolve consistently from the repo instead of accidentally colliding with unrelated global `tests` packages.

### Conversion runtime dependency

Real conversion jobs now call `ffmpeg` and `ffprobe` from the backend machine. Those binaries must be available on `PATH` for production or test conversion runs to succeed.

### Preview runtime dependencies

Real preview jobs use local Python imaging and detection libraries on the backend machine:

- `opencv-python`
- `numpy`
- `Pillow`

Preview generation does not require cloud AI providers. Face prioritization uses OpenCV's local Haar cascade, and figure prioritization uses OpenCV's local HOG person detector.

### Tagging runtime dependencies

Real tagging jobs reuse the local video frame sampler and then call one configured vision provider:

- OpenRouter
- Google Gemini
- FAL
- Mistral

The backend stores provider API keys in `backend/.local/secrets.json`, keeps provider metadata in the main settings payload, and saves only allowed closed-vocabulary tags plus confidence scores in SQLite.

## Project Structure

- [`frontend/`](frontend/) contains the Vite + React application.
- [`backend/`](backend/) contains the Python HTTP backend, local schema initialization, and backend tests.
- [`docs/code-map.md`](docs/code-map.md) routes "where should I read first for this task?" across frontend and backend.
- [`docs/frontend-map.md`](docs/frontend-map.md) points to the smallest frontend edit paths for common UI work.
- [`docs/frontend-flows.md`](docs/frontend-flows.md) routes modal, jobs, settings, playback, and log-viewer flows.
- [`docs/dev-entrypoints.md`](docs/dev-entrypoints.md) lists the canonical read-first files and verification commands for localization, theme, preview layout, and local source/test-archive work.
- [`docs/`](docs/) contains the product and architecture specifications that guide the next implementation stages.

## Documentation

Core specification set:

- [`docs/specification.md`](docs/specification.md)
- [`docs/data-model.md`](docs/data-model.md)
- [`docs/api-spec.md`](docs/api-spec.md)
- [`docs/job-model.md`](docs/job-model.md)
- [`docs/settings-spec.md`](docs/settings-spec.md)
- [`docs/ui-screens.md`](docs/ui-screens.md)
- [`docs/backup-format.md`](docs/backup-format.md)
- [`docs/code-map.md`](docs/code-map.md)
- [`docs/frontend-map.md`](docs/frontend-map.md)
- [`docs/frontend-flows.md`](docs/frontend-flows.md)
- [`docs/dev-entrypoints.md`](docs/dev-entrypoints.md)
