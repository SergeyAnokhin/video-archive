# video-archive

Video Archive is a local-first Windows-targeted application for browsing one remote video source at a time and later adding recursive conversion, preview generation, tagging, settings, and maintenance workflows. The current repository state is an initial implementation skeleton: a React frontend, a Python backend, and a root npm developer entrypoint that starts both together.

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
- backend local SQLite schema initialization on startup
- backend local secret file storage outside the main metadata database

Not implemented yet:

- source connectivity and scanning
- directory tree and file browser
- job execution and logs
- settings persistence and backups
- UI localization with Russian and English support

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

- Frontend: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8000`

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

### Backend local data and config

On first startup, the backend creates local development state under `backend/.local/`:

- `video_archive.db` for metadata
- `secrets.json` for source credentials stored outside the main metadata database

Optional local overrides can be placed in `backend/.env.local`. Start from [`backend/.env.example`](backend/.env.example) and set values such as:

- `VIDEO_ARCHIVE_HOST`
- `VIDEO_ARCHIVE_PORT`
- `VIDEO_ARCHIVE_DATA_DIR`
- `VIDEO_ARCHIVE_DB_PATH`
- `VIDEO_ARCHIVE_SECRETS_PATH`

### Run backend tests

```powershell
npm.cmd run test --prefix backend
```

## Project Structure

- [`frontend/`](frontend/) contains the Vite + React application.
- [`backend/`](backend/) contains the Python HTTP backend, local schema initialization, and backend tests.
- [`docs/code-map.md`](docs/code-map.md) maps the current implementation files.
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
