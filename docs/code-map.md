# Code Map

Living map of the implementation files in this repository. **This file must be updated whenever code files are added, moved, or removed.**

The repository is currently at the specification stage: the earlier prototype was intentionally removed, and the implementation will be recreated per [Roadmap](./roadmap.md). Right now the only implementation-related file is the root orchestrator.

| Path | Role |
| --- | --- |
| [`package.json`](../package.json) | Root developer entrypoint; will start frontend and backend together with `npm run dev` once `frontend/` and `backend/` are recreated (Roadmap Stage 1). |
| [`README.md`](../README.md) | Project overview, current status, and planned startup commands. |
| [`docs/`](./) | Specification set driving the implementation. |

To be added as implementation progresses (see [Tech Stack — Repository Layout](./tech-stack.md#repository-layout-target)):

- `frontend/` — Vite + React + TypeScript app
- `backend/` — FastAPI app, SQLite database, secrets file, detection model files
