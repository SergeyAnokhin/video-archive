# Code Map

Living map of the implementation files in this repository. **This file must be updated whenever code files are added, moved, or removed.**

[Roadmap Stage 1](./roadmap.md#stage-1--skeleton) is implemented: `frontend/` and `backend/` exist and run together via the root `package.json`. Later stages will add source browsing, jobs, conversion, previews, tagging, and playback on top of this skeleton.

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
| [`frontend/src/components/SettingsModal.tsx`](../frontend/src/components/SettingsModal.tsx) | Minimal Settings surface opened from the top bar's Settings button; currently holds only the Interface/Language option group. Becomes a full-screen sheet on mobile ([Design System §5](./design-system.md#5-responsive-breakpoints)). A placeholder for the fuller icon-rail Settings screen described in [Design System §1](./design-system.md#1-reference-inspiration), which grows as later stages add settings groups (source, conversion, preview, etc.). |
| [`frontend/src/components/AppLayout.tsx`](../frontend/src/components/AppLayout.tsx) | Shell layout: top bar + directory-tree pane + main content + `SettingsModal`, per [Design System §5](./design-system.md#5-responsive-breakpoints) breakpoints (drawer on mobile, collapsible panel on tablet, persistent pane on desktop). The tree pane is a placeholder until [Stage 2](./roadmap.md#stage-2--local-source-scan-browsing). |
| [`frontend/src/components/BackendStatusPanel.tsx`](../frontend/src/components/BackendStatusPanel.tsx) | Displays `/api/health` and `/api/app/info` (app version, DB schema version, ffmpeg availability). |
| [`frontend/src/context/PreviewVisibilityContext.tsx`](../frontend/src/context/PreviewVisibilityContext.tsx) | `previewsVisible` boolean + toggle, session-only (not persisted); consumed by the top bar's toggle button today and will gate preview rendering once the library grid exists ([Stage 2](./roadmap.md#stage-2--local-source-scan-browsing)/[Stage 5](./roadmap.md#stage-5--preview-generation)). |
| [`frontend/src/hooks/useBackendStatus.ts`](../frontend/src/hooks/useBackendStatus.ts) | Fetches health and app-info endpoints; exposes a loading/error/ready state. |
| [`frontend/src/i18n/index.ts`](../frontend/src/i18n/index.ts) | i18next setup; detects initial language from a persisted preference or the browser locale (falls back to English). Language is selected directly (not cycled) from `SettingsModal`. |
| [`frontend/src/i18n/locales/en.json`](../frontend/src/i18n/locales/en.json), [`ru.json`](../frontend/src/i18n/locales/ru.json) | UI string resources; kept in parity (see [Roadmap Cross-Stage Rules](./roadmap.md#cross-stage-rules)). |
| [`frontend/src/types/api.ts`](../frontend/src/types/api.ts) | TypeScript types for the health/app-info response shapes. |

## `backend/` — FastAPI

| Path | Role |
| --- | --- |
| [`backend/package.json`](../backend/package.json) | Wraps the Python startup (`pip install` + `uvicorn --reload`) so the root `npm run dev` can start it. |
| [`backend/requirements.txt`](../backend/requirements.txt) | Python dependencies: FastAPI, Uvicorn, SQLAlchemy, sse-starlette, python-dotenv. |
| [`backend/app/main.py`](../backend/app/main.py) | FastAPI app; on startup initializes the database and checks ffmpeg availability once. |
| [`backend/app/config.py`](../backend/app/config.py) | App version constant and the SQLite database path. |
| [`backend/app/db.py`](../backend/app/db.py) | SQLite initialization via SQLAlchemy; schema versioning through an ordered `MIGRATIONS` map and a single-row `schema_meta` table. Later stages append new migrations here for `sources`, `directories`, `files`, etc. ([Data Model](./data-model.md)). |
| [`backend/app/ffmpeg.py`](../backend/app/ffmpeg.py) | Locates `ffmpeg` on `PATH` and reads its version. |
| [`backend/app/routers/health.py`](../backend/app/routers/health.py) | `GET /api/health`. |
| [`backend/app/routers/app_info.py`](../backend/app/routers/app_info.py) | `GET /api/app/info`: app version, source summary (`null` until Stage 2), database status, queue status (`null` until Stage 3), ffmpeg availability. |

Not yet created (see [Tech Stack](./tech-stack.md#repository-layout-target)): `backend/secrets.env` (arrives with SMB/provider credentials), detection model files (Stage 5), the SQLite entity tables beyond `schema_meta` (introduced incrementally per stage).
