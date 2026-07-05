# Code Map

This repository currently contains the first backend foundation for Video Archive plus the first frontend application shell: a root npm orchestrator, a Vite-based React UI with library layout placeholders, and a stdlib Python backend with local config loading, SQLite schema initialization, source configuration storage, and narrow smoke-testable API endpoints. Use this map to find the startup flow and the smallest files to extend first.

| Path | Role |
| --- | --- |
| [`package.json`](../package.json) | Root developer entrypoint that starts frontend and backend together with `npm run dev`. |
| [`frontend/package.json`](../frontend/package.json) | Frontend scripts and React/Vite dependencies. |
| [`frontend/vite.config.js`](../frontend/vite.config.js) | Local dev server config and `/api` proxy to the backend. |
| [`frontend/src/App.jsx`](../frontend/src/App.jsx) | First library shell: top toolbar, directory tree shell, file list shell, preview toggle, jobs modal shell, log viewer shell, and settings navigation shell. |
| [`frontend/src/api.js`](../frontend/src/api.js) | Small frontend API helper for the current live backend calls: `GET /api/health`, `GET /api/app/info`, and `GET /api/source`. |
| [`frontend/src/mockData.js`](../frontend/src/mockData.js) | Shell-only placeholder directory, file, job, log, and settings-navigation data used until browse and jobs endpoints exist. |
| [`frontend/src/styles.css`](../frontend/src/styles.css) | Dark-theme layout and component styling for the current application shell and modal surfaces. |
| [`backend/package.json`](../backend/package.json) | Backend-local `npm run dev` wrapper for the Python server on Windows terminals. |
| [`backend/app/main.py`](../backend/app/main.py) | Stdlib HTTP entrypoint and request routing for the current backend endpoints. |
| [`backend/app/config.py`](../backend/app/config.py) | Local config loading, including optional `backend/.env.local` overrides. |
| [`backend/app/db.py`](../backend/app/db.py) | SQLite connection helpers and idempotent schema initialization/migrations. |
| [`backend/app/source_service.py`](../backend/app/source_service.py) | Source payload validation, active-source persistence, and simple connection testing. |
| [`backend/app/secrets.py`](../backend/app/secrets.py) | Local secret-file storage used to keep credentials out of the main metadata database. |
| [`backend/tests/`](../backend/tests/) | Minimal backend tests for config loading, schema init, and source persistence behavior. |
| [`backend/.env.example`](../backend/.env.example) | Example local backend override file for Windows development. |
| [`README.md`](../README.md) | Local setup, Windows terminal commands, backend local-data notes, and test command. |
