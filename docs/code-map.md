# Code Map

This repository currently contains the first real source setup, browsing flow, conversion workflow, tuning workflow, preview-generation workflow, playback workflow, and closed-vocabulary AI tagging workflow for Video Archive: a root npm orchestrator, a Vite-based React UI with source, preview, playback, tagging, and provider settings, and a stdlib Python backend with local config loading, SQLite schema initialization, source configuration storage, saved conversion profiles, preview presets/settings, playback settings, tagging/provider settings, an async job queue, real conversion workers, real tuning workers, real preview workers, real tagging workers, persistent job items/events, and persisted tree/file metadata. Use this map to find the startup flow and the smallest files to extend first.

## Common Edit Points

| Change area | Start here | Also verify |
| --- | --- | --- |
| Source settings changes | [`../frontend/src/features/source/SourceSettingsSection.jsx`](../frontend/src/features/source/SourceSettingsSection.jsx) | [`../frontend/src/features/source/sourceHelpers.js`](../frontend/src/features/source/sourceHelpers.js), [`../frontend/src/api.js`](../frontend/src/api.js), [`../backend/app/source_service.py`](../backend/app/source_service.py) |
| Source API or backend contract changes | [`../frontend/src/api.js`](../frontend/src/api.js) | [`../backend/app/main.py`](../backend/app/main.py), [`../backend/app/source_service.py`](../backend/app/source_service.py), [`../backend/app/library_service.py`](../backend/app/library_service.py) |
| Playback-related changes | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) | [`../frontend/src/components/modals/FileDetailsModal.jsx`](../frontend/src/components/modals/FileDetailsModal.jsx), [`../backend/app/playback_settings_service.py`](../backend/app/playback_settings_service.py), [`../backend/app/main.py`](../backend/app/main.py) |
| Preview or tagging settings changes | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) | [`../frontend/src/api.js`](../frontend/src/api.js), [`../backend/app/preview_service.py`](../backend/app/preview_service.py), [`../backend/app/tagging_service.py`](../backend/app/tagging_service.py) |
| Jobs modal or job-status browsing changes | [`../frontend/src/components/modals/JobsModal.jsx`](../frontend/src/components/modals/JobsModal.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx), [`../backend/app/job_service.py`](../backend/app/job_service.py) |
| File detail or tune modal changes | [`../frontend/src/components/modals/FileDetailsModal.jsx`](../frontend/src/components/modals/FileDetailsModal.jsx), [`../frontend/src/components/modals/TuneModal.jsx`](../frontend/src/components/modals/TuneModal.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx), [`../backend/app/conversion_profile_service.py`](../backend/app/conversion_profile_service.py), [`../backend/app/job_service.py`](../backend/app/job_service.py) |

See [`frontend-map.md`](frontend-map.md) for the frontend-only version of this routing map.

| Path | Role |
| --- | --- |
| [`package.json`](../package.json) | Root developer entrypoint that starts frontend and backend together with `npm run dev`. |
| [`frontend/package.json`](../frontend/package.json) | Frontend scripts and React/Vite dependencies. |
| [`frontend/vite.config.js`](../frontend/vite.config.js) | Local dev server config and `/api` proxy to the backend. |
| [`frontend/src/App.jsx`](../frontend/src/App.jsx) | Frontend shell/orchestration for bootstrap loading, library browsing, overlay state, log viewer, conversion dialog, playback modal, preview/tagging/playback/provider/profile settings sections, and cross-feature handlers. |
| [`frontend/src/api.js`](../frontend/src/api.js) | Frontend API helper for the live backend calls used by source setup, backend-local directory browsing, preview/playback/tagging/provider settings, tree/file loading, file detail + playback loading, conversion profile loading/creation, tuning job creation, job detail loading, and job control actions. |
| [`frontend/src/features/source/SourceSettingsSection.jsx`](../frontend/src/features/source/SourceSettingsSection.jsx) | Extracted source settings form, local-folder browser UI, and source action buttons. |
| [`frontend/src/features/source/sourceHelpers.js`](../frontend/src/features/source/sourceHelpers.js) | Source defaults/state shaping plus shared form, source payload, and tuning/profile helper functions still used by the shell. |
| [`frontend/src/components/modals/FileDetailsModal.jsx`](../frontend/src/components/modals/FileDetailsModal.jsx) | File detail modal with preview, metadata, tag display, and file-level action entry points. |
| [`frontend/src/components/modals/JobsModal.jsx`](../frontend/src/components/modals/JobsModal.jsx) | Jobs modal with recent-job list, per-job detail, item list, and event stream. |
| [`frontend/src/components/modals/TuneModal.jsx`](../frontend/src/components/modals/TuneModal.jsx) | Tune modal with sweep controls, tuning outputs, and "save as profile" entry point. |
| [`frontend/src/mockData.js`](../frontend/src/mockData.js) | Small placeholder data that still backs static settings navigation labels and any remaining shell-only UI copy. |
| [`frontend/src/styles.css`](../frontend/src/styles.css) | Dark-theme layout and component styling for the current application shell and modal surfaces. |
| [`backend/package.json`](../backend/package.json) | Backend-local `npm run dev` wrapper for the Python server on Windows terminals. |
| [`backend/app/main.py`](../backend/app/main.py) | Stdlib HTTP entrypoint and request routing for source, backend-local directory browsing, settings, provider config, preview presets, conversion profile creation, tree, file detail/playback/preview/tag endpoints, job, and log/event endpoints, including the SSE stream and ranged embedded playback responses. |
| [`backend/app/config.py`](../backend/app/config.py) | Local config loading, including optional `backend/.env.local` overrides. |
| [`backend/app/db.py`](../backend/app/db.py) | SQLite connection helpers and idempotent schema initialization/migrations, including preview assets, preview settings, tagging metadata, and app settings persistence. |
| [`backend/app/job_service.py`](../backend/app/job_service.py) | Persistent job queue execution: queued/running terminal transitions, background worker, conversion/profile snapshots, real conversion item handling, real tuning sweep output handling, real preview item handling, real tagging item handling, job items, events, cancellation, and restart. |
| [`backend/app/conversion_profile_service.py`](../backend/app/conversion_profile_service.py) | Saved conversion profile bootstrap and lookup, including UI-created and tuning-promoted profiles plus the default H.265/MP4 profile used by conversion jobs. |
| [`backend/app/conversion_service.py`](../backend/app/conversion_service.py) | `ffmpeg` / `ffprobe` based conversion execution with codec-aware encoder selection, temp outputs, lightweight validation, safe source replacement, and separate test outputs. |
| [`backend/app/playback_settings_service.py`](../backend/app/playback_settings_service.py) | Playback-mode persistence for embedded modal playback versus external file-link opening behavior. |
| [`backend/app/preview_service.py`](../backend/app/preview_service.py) | Preview settings and preset persistence, N+1 interior frame sampling, local face/body analysis, collage layout generation, live preview rendering, and file/directory preview asset storage. |
| [`backend/app/tagging_service.py`](../backend/app/tagging_service.py) | Closed-vocabulary tagging settings, vocabulary persistence, frame sampling + montage creation, provider request/response handling, batch preference, and file-tag persistence with confidence scores. |
| [`backend/app/provider_settings_service.py`](../backend/app/provider_settings_service.py) | Non-secret provider metadata persistence, provider validation/defaults, and runtime provider resolution backed by secret storage. |
| [`backend/app/source_service.py`](../backend/app/source_service.py) | Source payload validation, active-source persistence, password preservation on update, local-directory listing, reconnect, and connection testing for both local and remote sources. |
| [`backend/app/library_service.py`](../backend/app/library_service.py) | Source-root scanning, persisted directory/file metadata upserts, preview/tag invalidation on file changes, derived directory indicators, and file listing used by both browsing and queued scan jobs. |
| [`backend/app/secrets.py`](../backend/app/secrets.py) | Local secret-file storage used to keep source credentials and provider API keys out of the main metadata database. |
| [`backend/app/time_utils.py`](../backend/app/time_utils.py) | Shared UTC timestamp helper for persisted source and job metadata. |
| [`backend/tests/`](../backend/tests/) | Backend tests for config loading, schema init, preview/tagging settings, source persistence, scan/rescan, async job execution, preview/conversion/tagging state updates, cancel/restart, tree derivation, and file metadata resets. |
| [`backend/.env.example`](../backend/.env.example) | Example local backend override file for Windows development. |
| [`README.md`](../README.md) | Local setup, Windows terminal commands, backend local-data notes, current browse-flow scope, and test command. |
