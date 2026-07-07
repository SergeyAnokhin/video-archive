# Development Workflow

How to run, test, and manually verify changes in this repository. Prerequisites and first-run notes (Node 20+, Python 3.11+, ffmpeg on `PATH`, one-time detection-model download) are in the root [`README.md`](../README.md#local-run).

## Run

```powershell
npm.cmd install
npm.cmd run dev     # starts frontend (127.0.0.1:5173) and backend (127.0.0.1:8000) together
```

Frontend and backend also run independently (`npm run dev` inside `frontend/` or `backend/`). The backend health endpoint is `/api/health`; app info is `/api/app/info`.

Running a second frontend dev session against an already-running backend (e.g. a second AI coding session doing UI verification while another one's server is still up on `:5173`): use the `frontend-only` entry in [`.claude/launch.json`](../.claude/launch.json) (`npm run dev --prefix frontend`, `autoPort: true`) — `frontend/vite.config.ts` reads `PORT` from the environment (falling back to `5173`), so a second instance gets its own port and proxies to the same backend on `:8000` instead of failing to bind.

## Tests

| Suite | Command | Notes |
| --- | --- | --- |
| Backend (pytest) | `python -m pytest` from `backend/` | The only automated suite. Tests needing real ffmpeg/ffprobe skip automatically when unavailable. |
| Frontend lint | `npm run lint` from `frontend/` | No frontend unit tests currently exist. |
| Frontend build check | `npm run build` from `frontend/` | Type-checks via `tsc` before bundling. |

Test conventions (per-suite details in [`code-map-tests.md`](code-map-tests.md)):

- Every test gets an isolated temp SQLite DB and an isolated secrets file via autouse fixtures in `backend/tests/conftest.py` — tests never touch `backend/video_archive.db` or `backend/secrets.env`.
- `make_video()` in `conftest.py` encodes a tiny real video with ffmpeg for tests that need conversion/probing to actually succeed; `make_files()` creates dummy non-decodable files for scan/job tests.
- SMB is tested against an in-memory `FakeSMBFS` fixture — no real SMB server is available.
- Provider clients are tested with `httpx` monkeypatched — tests must never hit real AI provider APIs.
- Per [`CLAUDE.md`](../CLAUDE.md): run the smallest relevant suite after every change; a task is not complete while required tests fail.

## Manual / visual verification

Use the git-ignored local sample archive `test-data/VideoArchive/` as the source — see [README § Local Test Data](../README.md#local-test-data) for layout and safety rules (never modify the samples in place; use test mode for conversion; prefer scratch subfolders over replacing the active source).

Before running any real (non-test-mode) job — convert, preview, tag — against "the active source" during verification, check `GET /api/source`'s `root_path` first. Source config persists in the SQLite db across sessions, so whatever was last connected stays active; it may point somewhere other than this repo's `test-data/VideoArchive` (e.g. a different checkout on disk), and a real preview/convert job run against it mutates files there for real, not just this repo's ignored sample folder.

## Housekeeping

- Update the matching part of the [code map](code-map.md) whenever files are added, moved, or removed.
- Keep `frontend/src/i18n/locales/en.json` and `ru.json` in parity when touching UI copy.
- Do not read [`spec/`](spec/README.md) (frozen V1 specification) unless explicitly asked.
