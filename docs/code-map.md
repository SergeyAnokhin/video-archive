# Code Map

This repository currently contains the first real source setup and browsing flow for Video Archive: a root npm orchestrator, a Vite-based React UI with source settings and library browsing, and a stdlib Python backend with local config loading, SQLite schema initialization, source configuration storage, an async job queue foundation, persistent job items/events, and persisted tree/file metadata. Use this map to find the startup flow and the smallest files to extend first.

| Path | Role |
| --- | --- |
| [`package.json`](../package.json) | Root developer entrypoint that starts frontend and backend together with `npm run dev`. |
| [`frontend/package.json`](../frontend/package.json) | Frontend scripts and React/Vite dependencies. |
| [`frontend/vite.config.js`](../frontend/vite.config.js) | Local dev server config and `/api` proxy to the backend. |
| [`frontend/src/App.jsx`](../frontend/src/App.jsx) | Main frontend flow for source setup, source test/save/reconnect, directory actions, tree browsing, file listing, and the jobs modal with detail/items/live log updates. |
| [`frontend/src/api.js`](../frontend/src/api.js) | Frontend API helper for the live backend calls used by source setup, tree/file loading, job creation, job detail loading, and job control actions. |
| [`frontend/src/mockData.js`](../frontend/src/mockData.js) | Small placeholder data that still backs static settings navigation labels and any remaining shell-only UI copy. |
| [`frontend/src/styles.css`](../frontend/src/styles.css) | Dark-theme layout and component styling for the current application shell and modal surfaces. |
| [`backend/package.json`](../backend/package.json) | Backend-local `npm run dev` wrapper for the Python server on Windows terminals. |
| [`backend/app/main.py`](../backend/app/main.py) | Stdlib HTTP entrypoint and request routing for source, tree, file, job, and log/event endpoints, including the SSE stream. |
| [`backend/app/config.py`](../backend/app/config.py) | Local config loading, including optional `backend/.env.local` overrides. |
| [`backend/app/db.py`](../backend/app/db.py) | SQLite connection helpers and idempotent schema initialization/migrations. |
| [`backend/app/job_service.py`](../backend/app/job_service.py) | Persistent job queue foundation: queued/running terminal transitions, background worker, job items, events, cancellation, restart, and placeholder non-scan job execution. |
| [`backend/app/source_service.py`](../backend/app/source_service.py) | Source payload validation, active-source persistence, password preservation on update, reconnect, and connection testing. |
| [`backend/app/library_service.py`](../backend/app/library_service.py) | Source-root scanning, persisted directory/file metadata upserts, derived directory indicators, and file listing used by both browsing and queued scan jobs. |
| [`backend/app/secrets.py`](../backend/app/secrets.py) | Local secret-file storage used to keep credentials out of the main metadata database. |
| [`backend/app/time_utils.py`](../backend/app/time_utils.py) | Shared UTC timestamp helper for persisted source and job metadata. |
| [`backend/tests/`](../backend/tests/) | Backend tests for config loading, schema init, source persistence, password retention, scan/rescan, async job execution, cancel/restart, tree derivation, and file metadata resets. |
| [`backend/.env.example`](../backend/.env.example) | Example local backend override file for Windows development. |
| [`README.md`](../README.md) | Local setup, Windows terminal commands, backend local-data notes, current browse-flow scope, and test command. |
