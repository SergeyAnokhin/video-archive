# video-archive

Video Archive is a local-first, Windows-targeted web application for browsing a video directory source (local folder or SMB share), converting videos in bulk with ffmpeg, generating preview collages stored next to the videos, and tagging videos through external AI providers.

## Current Status

**Specification stage.** The repository currently contains the complete specification set and the root orchestration file only. An earlier implementation prototype was intentionally removed; the implementation will be recreated from scratch following [docs/roadmap.md](docs/roadmap.md).

There is no runnable frontend or backend yet — `npm.cmd run dev` will work again after Roadmap Stage 1 recreates `frontend/` and `backend/`.

## Planned Local Run

The repository root stays the single developer entrypoint: one command starts frontend and backend together.

### Prerequisites

- Node.js 20+
- Python 3.11+
- ffmpeg on `PATH` (`winget install ffmpeg`)

### Startup (after Stage 1)

```powershell
npm.cmd install
npm.cmd run dev
```

- Frontend: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8000`

Frontend and backend will also remain independently runnable from their own directories.

## Project Structure

- [`package.json`](package.json) — root developer entrypoint that will start frontend and backend together.
- [`docs/`](docs/) — the product and architecture specifications that drive the implementation.
- `frontend/`, `backend/` — to be recreated in Roadmap Stage 1.

## Documentation

Core specification set:

- [`docs/specification.md`](docs/specification.md) — main technical specification
- [`docs/tech-stack.md`](docs/tech-stack.md) — fixed technology choices
- [`docs/roadmap.md`](docs/roadmap.md) — implementation stages and completion criteria
- [`docs/data-model.md`](docs/data-model.md)
- [`docs/api-spec.md`](docs/api-spec.md)
- [`docs/job-model.md`](docs/job-model.md)
- [`docs/settings-spec.md`](docs/settings-spec.md)
- [`docs/ui-screens.md`](docs/ui-screens.md)
- [`docs/design-system.md`](docs/design-system.md)
- [`docs/backup-format.md`](docs/backup-format.md)
- [`docs/code-map.md`](docs/code-map.md) — living map of implementation files
