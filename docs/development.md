# Development Workflow

How to run, test, and manually verify changes in this repository. Prerequisites and first-run notes (Node 20+, Python 3.11+, ffmpeg on `PATH`, one-time detection-model download) are in the root [`README.md`](../README.md#local-run).

## Run

```powershell
npm.cmd install
npm.cmd run dev     # starts frontend (:5173) and backend (:8010) together
```

Both dev servers bind `0.0.0.0` (reachable from a phone on the same network — Settings → Network), not just `127.0.0.1`. Frontend and backend also run independently (`npm run dev` inside `frontend/` or `backend/`). Health endpoint: `/api/health`; app info: `/api/app/info`.

`npm run dev` first runs [`scripts/check-stale-dev-servers.ps1`](../scripts/check-stale-dev-servers.ps1) (wired as `predev`): a non-blocking warning if ports `5173`/`8010` are already held, printing the holder's PID/start time/command line. Standalone: `npm run check-dev-servers`. An orphan holding the port is a real and recurring failure mode — see [verification-notes.md](verification-notes.md#dev-server-stale-processes-and-wedged-reloads).

Running a second frontend against an already-running backend (e.g. a concurrent AI coding session): use the `frontend-only` entry in [`.claude/launch.json`](../.claude/launch.json) — `frontend/vite.config.ts` reads `PORT` from the environment, so a second instance gets its own port and proxies to the same backend on `:8010`.

## Backend console logging

`app/request_logging.py`'s `RequestLoggingMiddleware` replaces uvicorn's default access log (`app/logging_config.py` disables `uvicorn.access` so it isn't logged twice): one line per request — emoji by method, route path template, params, status, duration. The high-frequency polling routes in `_QUIET_ROUTES` stay silent unless they error; add a route there if it becomes another poll target. Request bodies are never logged (some settings endpoints carry API keys).

All console output is mirrored to `logs/backend.log` at the repo root, rotating on size (`app/log_rotation_settings.py`; `app/logging_config.py::apply_rotation_settings()` applies a Settings change to the live handler with no restart). The directory is deliberately `logs/` and not `backend/logs/` — `uvicorn --reload` watches the whole `backend/` tree, so a log file written inside it would retrigger the reloader on every line.

Log files (including rotated backups) are downloadable/deletable via the Log Viewer's "Log files" tab (`LogViewerModal.tsx`'s `LogFilesPanel`, backed by `app/routers/log_files.py`). Deleting the active `backend.log` is refused with 409 — it's held open by the running process.

## Tests

| Suite | Command | Notes |
| --- | --- | --- |
| Backend (pytest) | `python -m pytest` from `backend/` | The main suite. Tests needing real ffmpeg/ffprobe skip automatically when unavailable. |
| Frontend unit tests (vitest) | `npm test` from `frontend/` | Mostly pure-logic tests. Default environment is plain `node` (no `vitest.config.ts`), so a `.test.ts` touching DOM APIs needs its own stub (see `utils/recentFolders.test.ts`). For a component test, opt into jsdom per-file with `// @vitest-environment jsdom` and render via `@testing-library/react` — pattern in `components/TaggingSettingsSection.test.tsx`. |
| Frontend lint | `npm run lint` from `frontend/` | |
| Frontend type check | `npx tsc -b` from `frontend/` | Bare `tsc --noEmit` checks **zero** files here (solution-style tsconfig). |

`tsc` alone is not proof a `.tsx` edit builds: it has been observed to pass on JSX that Vite's transform (oxc) rejects — e.g. multiple sibling elements inside `{condition && (...)}` without a wrapping fragment. After editing conditional JSX with more than one top-level sibling, reload the dev server / check `preview_logs`, or run `npm run build`.

Test conventions (per-suite details in [`code-map-tests.md`](code-map-tests.md)):

- Every test gets an isolated temp SQLite DB and secrets file via autouse fixtures in `backend/tests/conftest.py` — tests never touch `backend/video_archive.db` or `backend/secrets.env`.
- `make_video()` in `conftest.py` encodes a tiny real video for tests that need conversion/probing to succeed; `make_files()` creates dummy non-decodable files for scan/job tests.
- Hand-inserting a `directories` row: the **root** row's `parent_relative_path` is `NULL`, but every direct child of root uses `''`. Seeding root with `''` makes it appear as its own child. Working pattern: `test_directories_router.py`.
- SMB is tested against an in-memory `FakeSMBFS` fixture; provider clients with `httpx` monkeypatched — tests must never hit real SMB servers or AI provider APIs.
- A fake replacing `registry._CLIENTS`/`registry.score_tags_with_entry` must accept `**kwargs` — the real functions gain keyword-only params over time, and a rigid fake fails at call time, not collection time.
- Two recurring flaky-test shapes (transient hook state, strict jsdom `fetch` routers) are written up in [verification-notes.md § Flaky-test patterns](verification-notes.md#flaky-test-patterns).
- Per [`CLAUDE.md`](../CLAUDE.md): run the smallest relevant suite after every change; a task is not complete while required tests fail.

## Recipe: adding a global settings singleton

The repo has one recurring pattern for an app-wide setting (10 singletons already: preview, tagging, playback, backup, interface, performance, conversion, backend health, resource monitor, log rotation). Copy an existing small one — [`backend/app/performance_settings.py`](../backend/app/performance_settings.py) / [`backend/app/conversion_settings.py`](../backend/app/conversion_settings.py) are the shortest — and touch these spots:

1. `backend/app/<name>_settings.py` — constants (default/min/max), `get_settings()`, `update_settings()` (clamp there), `seed_default_settings()`.
2. `backend/app/migrations.py` — append a `CREATE TABLE IF NOT EXISTS <name>_settings (id INTEGER PRIMARY KEY CHECK (id = 1), ...)` migration, **and** a matching `if current_version < N <= SCHEMA_VERSION:` seed call in `db.py`'s `init_db()`.
3. `backend/app/routers/<name>_settings.py` — `GET`/`PUT /api/<name>-settings`, pydantic `Field(ge=..., le=...)` bounds imported from the module's constants; wire it into `backend/app/main.py` (import + `include_router`).
4. Frontend: interface in `frontend/src/types/api.ts`, a Settings section component (fetch on mount, `PUT` on change — see `PerformanceSettingsSection.tsx`), i18n keys in **both** `en.json` and `ru.json`.
5. Tests: copy `backend/tests/test_performance_settings.py` (defaults/round-trip, clamping, HTTP round-trip).

## Before starting a nontrivial feature

Run `git status`/`git diff HEAD` first, before exploring or planning. This repo is worked on across multiple (sometimes concurrent) sessions; an earlier session can leave substantial uncommitted progress on the very feature you're about to start. Cross-check the diff against your plan early, not after re-implementing half of it.

## Manual / visual verification

Use the git-ignored local sample archive `test-data/VideoArchive/` as the source — see [README § Local Test Data](../README.md#local-test-data) for layout and safety rules.

- **Never leave samples modified.** "Test mode" conversion is not a dry run: it renames the original to `<name>.original.<ext>` and writes a new file at the original name (`app/jobs/convert.py::_replace_test_mode()`). Revert by hand afterwards — a rescan will not undo it.
- **Check the active source before any real job.** `GET /api/source`'s `root_path` persists across sessions and may point at real content, not `test-data/`. A real convert/preview job mutates files there for real.
- **`PUT /api/source` is destructive and irreversible**, before any job runs: it wipes `files`/`directories`/`file_tags`/`file_similarity_signatures`/`jobs`/`job_items`/`app_events` for whatever was active. The UI confirms first; calling the endpoint directly does not. It also *reuses* an existing saved-sources row when `(protocol, host, port, root_path)` matches, overwriting that row's name — so repeatedly connecting to the same path lands on the same source, not a fresh one.
- **Already-processed samples prove nothing.** Library metadata and generated preview assets persist, so a preview/tag job with "skip already processed" checked reports every item `skipped`. Uncheck it, or pick untouched files.
- **Settings CRUD has no fixture** — it lives in the same live `video_archive.db` as the real config. If verification creates rows, delete them by the exact ids the API returned, never by guessed position.
- **Don't overwrite a sample file by name.** Writing a synthetic fixture over an existing `<name>.jpg` silently destroys a real generated collage, and this directory has no git history. Regenerate through the app's own job if it happens.

When verification gets stuck on the environment rather than the code — orphaned dev servers, screenshot timeouts, browser-automation blind spots, live provider calls — see [`verification-notes.md`](verification-notes.md).

## Housekeeping

- Update the matching part of the [code map](code-map.md) whenever files are added, moved, or removed, following its [writing rules](code-map.md#writing-rules).
- Keep `frontend/src/i18n/locales/en.json` and `ru.json` in parity — enforced by [`frontend/src/i18n/localeParity.test.ts`](../frontend/src/i18n/localeParity.test.ts), so `npm test` fails if a key is added to one file only.
- Do not read [`spec/`](spec/README.md) (frozen V1 specification) unless explicitly asked.
