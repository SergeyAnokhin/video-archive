# Code Map

Living map of the implementation files in this repository. **This file must be updated whenever code files are added, moved, or removed.**

[Roadmap Stage 1](./roadmap.md#stage-1--skeleton) and [Stage 2](./roadmap.md#stage-2--local-source-scan-browsing) are implemented: `frontend/` and `backend/` run together via the root `package.json`, and the backend can connect a `local` source, scan it, and serve directory/file browsing endpoints that the frontend renders as a directory tree and library grid. Later stages will add jobs, conversion, previews, tagging, and playback on top of this.

## Root

| Path | Role |
| --- | --- |
| [`package.json`](../package.json) | Root developer entrypoint; `npm run dev` uses `concurrently` to start `frontend` and `backend` together. |
| [`README.md`](../README.md) | Project overview, current status, and startup commands. |
| [`docs/`](./) | Specification set driving the implementation. |

## `frontend/` — Vite + React + TypeScript

| Path | Role |
| --- | --- |
| [`frontend/package.json`](../frontend/package.json) | Frontend scripts (`dev`, `build`, `lint`, `preview`) and dependencies (React, i18next, react-i18next, `lucide-react`). |
| [`frontend/vite.config.ts`](../frontend/vite.config.ts) | Dev server on `127.0.0.1:5173`; proxies `/api` to the backend on `127.0.0.1:8000`. |
| [`frontend/index.html`](../frontend/index.html) | HTML shell; `data-theme="strict"` selects the active theme variable set. |
| [`frontend/src/main.tsx`](../frontend/src/main.tsx) | Entry point; wires up global styles and i18n before rendering `App`. |
| [`frontend/src/App.tsx`](../frontend/src/App.tsx) | Root component: `PreviewVisibilityProvider` wrapping `AppLayout` wrapping the (currently placeholder) main content. |
| [`frontend/src/styles/theme.css`](../frontend/src/styles/theme.css) | CSS variables for the Strict theme (`[data-theme="strict"]`); Playful (Stage 9) will add its own variable set. |
| [`frontend/src/styles/global.css`](../frontend/src/styles/global.css) | Reset and base typography/touch-target rules. |
| [`frontend/src/components/TopBar.tsx`](../frontend/src/components/TopBar.tsx) | Slim top bar: mobile/tablet menu toggle, app title, preview-visibility toggle (eye icon, always visible), Settings button. Language selection is not in the top bar — see `SettingsModal.tsx` — per [Design System §4](./design-system.md#4-localization-presentation). |
| [`frontend/src/components/SettingsModal.tsx`](../frontend/src/components/SettingsModal.tsx) | Settings surface opened from the top bar's Settings button; holds a Source group (name/path form, test-connection, connect/replace with a destructive-replace confirmation step per [Specification §5.2](./specification.md#52-source-switching)) and the Interface/Language group. Becomes a full-screen sheet on mobile ([Design System §5](./design-system.md#5-responsive-breakpoints)). A placeholder for the fuller icon-rail Settings screen described in [Design System §1](./design-system.md#1-reference-inspiration), which grows as later stages add settings groups (conversion, preview, etc.). |
| [`frontend/src/components/AppLayout.tsx`](../frontend/src/components/AppLayout.tsx) | Shell layout: top bar + directory-tree pane (`DirectoryTree`, or a "configure a source" placeholder) + main content (`LibraryView`, or an empty state with `BackendStatusPanel`) + `SettingsModal`, per [Design System §5](./design-system.md#5-responsive-breakpoints) breakpoints. Owns the selected-folder path shared between the tree and the library grid. |
| [`frontend/src/components/DirectoryTree.tsx`](../frontend/src/components/DirectoryTree.tsx) (+ `.css`) | Fetches `GET /api/tree?include_status=true` and renders the recursive, expandable folder tree with conversion/preview indicator dots ([UI Screens §1](./ui-screens.md#1-main-library-screen), [Specification §14](./specification.md#14-file-and-directory-state-model)). Refetches whenever the active source changes. |
| [`frontend/src/components/LibraryView.tsx`](../frontend/src/components/LibraryView.tsx) (+ `.css`) | Fetches `GET /api/directories/children` for the selected path; renders a breadcrumb, subfolder cards, and file cards with size and incomplete-state indicator dots. |
| [`frontend/src/components/BackendStatusPanel.tsx`](../frontend/src/components/BackendStatusPanel.tsx) | Displays `/api/health` and `/api/app/info` (app version, DB schema version, ffmpeg availability); shown in `AppLayout`'s empty state while no source is connected. |
| [`frontend/src/context/PreviewVisibilityContext.tsx`](../frontend/src/context/PreviewVisibilityContext.tsx) | `previewsVisible` boolean + toggle, session-only (not persisted); consumed by the top bar's toggle button today and will gate actual thumbnail rendering once preview assets can be served ([Stage 5](./roadmap.md#stage-5--preview-generation)). |
| [`frontend/src/context/SourceContext.tsx`](../frontend/src/context/SourceContext.tsx) | Fetches and holds the active source (`GET /api/source`); exposes `refresh()` and `setSource()` (used right after connecting/replacing a source) to the whole app. |
| [`frontend/src/hooks/useBackendStatus.ts`](../frontend/src/hooks/useBackendStatus.ts) | Fetches health and app-info endpoints; exposes a loading/error/ready state. |
| [`frontend/src/i18n/index.ts`](../frontend/src/i18n/index.ts) | i18next setup; detects initial language from a persisted preference or the browser locale (falls back to English). Language is selected directly (not cycled) from `SettingsModal`. |
| [`frontend/src/i18n/locales/en.json`](../frontend/src/i18n/locales/en.json), [`ru.json`](../frontend/src/i18n/locales/ru.json) | UI string resources; kept in parity (see [Roadmap Cross-Stage Rules](./roadmap.md#cross-stage-rules)). |
| [`frontend/src/types/api.ts`](../frontend/src/types/api.ts) | TypeScript types for health/app-info, source config, directory tree, directory-children, and file-entry response shapes. |

## `backend/` — FastAPI

| Path | Role |
| --- | --- |
| [`backend/package.json`](../backend/package.json) | Wraps the Python startup (`pip install` + `uvicorn --reload`) so the root `npm run dev` can start it. |
| [`backend/requirements.txt`](../backend/requirements.txt) | Python dependencies: FastAPI, Uvicorn, SQLAlchemy, sse-starlette, python-dotenv. |
| [`backend/app/main.py`](../backend/app/main.py) | FastAPI app; on startup initializes the database and checks ffmpeg availability once. Wires up the `health`, `app_info`, `source`, `tree`, `directories`, and `files` routers. |
| [`backend/app/config.py`](../backend/app/config.py) | App version constant and the SQLite database path. |
| [`backend/app/db.py`](../backend/app/db.py) | SQLite initialization via SQLAlchemy; schema versioning through an ordered `MIGRATIONS` map and a single-row `schema_meta` table. Migration 2 creates `sources`, `directories`, and `files` ([Data Model §1-3](./data-model.md)). Later stages append further migrations (jobs, conversion profiles, tags, etc.) instead of editing these. |
| [`backend/app/ffmpeg.py`](../backend/app/ffmpeg.py) | Locates `ffmpeg` on `PATH` and reads its version. |
| [`backend/app/media.py`](../backend/app/media.py) | Supported video extension list, the `.video-archive` technical folder name, and the fixed `folder-preview.jpg` name ([Tech Stack](./tech-stack.md#supported-video-extensions), [Specification §5.3](./specification.md#53-technical-folder), [§9.5](./specification.md#95-preview-storage)). |
| [`backend/app/scan.py`](../backend/app/scan.py) | `scan_source()`: walks a local source root, upserts `directories`/`files`, detects video preview assets (`<name>.jpg`) and folder previews (`folder-preview.jpg`) so they aren't listed as independent files, and removes stale rows for files/folders that disappeared ([Specification §6.1](./specification.md#61-scan)). Runs synchronously today; Stage 3 will move this behind the job queue. |
| [`backend/app/status.py`](../backend/app/status.py) | `compute_directory_status()`: derives per-subtree conversion/preview completeness and counts from `files` rows, never persisted ([Specification §14](./specification.md#14-file-and-directory-state-model)). |
| [`backend/app/source_access.py`](../backend/app/source_access.py) | `get_active_source_or_404()` helper shared by the browsing routers. |
| [`backend/app/routers/health.py`](../backend/app/routers/health.py) | `GET /api/health`. |
| [`backend/app/routers/app_info.py`](../backend/app/routers/app_info.py) | `GET /api/app/info`: app version, active source summary (`null` if none configured), database status, queue status (`null` until Stage 3), ffmpeg availability. |
| [`backend/app/routers/source.py`](../backend/app/routers/source.py) | `GET /api/source`, `PUT /api/source` (accepts `protocol: "local"` only for now; replacing wipes `directories`/`files` and runs a synchronous scan), `POST /api/source/test-connection` ([Specification §5](./specification.md#5-source-model), [Settings §1](./settings-spec.md#1-source-connection-settings)). SMB/WebDAV are rejected with a 400 until [Stage 7](./roadmap.md#stage-7--smb-source-and-playback). |
| [`backend/app/routers/tree.py`](../backend/app/routers/tree.py) | `GET /api/tree`: recursive directory tree from a given `path`, with optional `depth` limit and `include_status` indicators. |
| [`backend/app/routers/directories.py`](../backend/app/routers/directories.py) | `GET /api/directories/children`: immediate subfolders + files for one directory, with optional `include_status`. |
| [`backend/app/routers/files.py`](../backend/app/routers/files.py) | `GET /api/files` (filters: `directory`, `recursive`, `video_only`, `search`, `limit`/`offset`; tag filtering arrives with tagging in [Stage 6](./roadmap.md#stage-6--tagging-and-search)) and `GET /api/files/{file_id}`. |

Not yet created (see [Tech Stack](./tech-stack.md#repository-layout-target)): `backend/secrets.env` (arrives with SMB/provider credentials), detection model files (Stage 5), the remaining SQLite entity tables (`conversion_profiles`, `preview_layout_presets`, `jobs`, `job_items`, `tag_catalog`, `file_tags`, `file_similarity_signatures`, `app_events` — introduced incrementally per stage).
