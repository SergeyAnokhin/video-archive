# Code Map

Living map of the implementation files in this repository, split by area. **Whenever code files are added, moved, or removed, update the part covering them:**

| Part | Covers |
| --- | --- |
| [`code-map-frontend.md`](code-map-frontend.md) | `frontend/` — Vite + React + TypeScript app |
| [`code-map-backend.md`](code-map-backend.md) | `backend/app/` — domain modules, jobs, sources, providers; plus backend notes, known gaps, and conventions |
| [`code-map-routers.md`](code-map-routers.md) | `backend/app/routers/` — the HTTP API surface |
| [`code-map-tests.md`](code-map-tests.md) | `backend/tests/` — pytest suites and shared fixtures |

The full V1 scope plus numerous post-V1 additions are implemented; what the application does today is described in the root [`README.md`](../README.md), and how it hangs together in [`architecture.md`](architecture.md). These maps are navigational only — *what lives where and when to go there*. Rationale, feature history, and "who asked for this" live in git history, not here; keep entries to one or two sentences when updating them.

## Root

| Path | Role |
| --- | --- |
| [`package.json`](../package.json) | Root developer entrypoint; `npm run dev` starts `frontend` and `backend` together via `concurrently`. `predev` runs the stale-dev-server check below. |
| [`scripts/check-stale-dev-servers.ps1`](../scripts/check-stale-dev-servers.ps1) | Warning-only check for an orphaned dev server already holding port `5173`/`8000` before `npm run dev` starts fresh ones — an orphan keeps answering with outdated code while the new server fails to bind (see [development.md](development.md)). Also runnable via `npm run check-dev-servers`. |
| [`README.md`](../README.md) | Project overview, capabilities, and startup commands. |
| [`.github/workflows/build.yml`](../.github/workflows/build.yml), [`deploy/`](../deploy/) | CI image build and k3s deployment (Helm chart, ArgoCD app, Dockerfiles) — file-by-file map lives in [deployment.md](deployment.md). |
| [`docs/`](./) | Living project documentation ([index](./README.md)); frozen V1 specification archived in [`docs/spec/`](./spec/README.md) — reference only, do not read by default. |
