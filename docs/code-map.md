# Code Map

Living map of the implementation files in this repository, split by area. **Whenever code files are added, moved, or removed, update the part covering them:**

| Part | Covers |
| --- | --- |
| [`code-map-frontend.md`](code-map-frontend.md) | `frontend/` — Vite + React + TypeScript app |
| [`code-map-backend.md`](code-map-backend.md) | `backend/app/` — domain modules, jobs, sources, providers; plus backend notes, known gaps, and conventions |
| [`code-map-routers.md`](code-map-routers.md) | `backend/app/routers/` — the HTTP API surface |
| [`code-map-tests.md`](code-map-tests.md) | `backend/tests/` — pytest suites and shared fixtures |

What the application does today is described in the root [`README.md`](../README.md), and how it hangs together in [`architecture.md`](architecture.md). These maps are navigational only — *what lives where and when to go there*.

## Writing rules

These documents exist to be read by an LLM at the start of a task, so their size is a per-session cost. They have been compacted three times after regrowing; keep them from regrowing again:

1. **No provenance.** The fact stays, "who asked for it" and when goes. No `user request`, no `user report`, no dates, no `post-V1`, no "this used to…". That belongs to git history.
2. **One or two sentences per row** (aim for under 250 characters). A row answers "what lives here, and when do I open it" — not how it works. Depth belongs in the code itself.
3. **One fact, one home.** [`README.md`](../README.md) says *what the app does*; [`architecture.md`](architecture.md) states a rule and points at the file; these maps say *where it lives*; [`development.md`](development.md) says *how to run and test*. Anything written out in full in two places is a bug — link instead.
4. **Situational gotchas go to [`verification-notes.md`](verification-notes.md)**, not into a file everyone reads to orient.

## Root

| Path | Role |
| --- | --- |
| [`package.json`](../package.json) | Root developer entrypoint; `npm run dev` starts `frontend` and `backend` together via `concurrently`. `predev` runs the stale-dev-server check below. |
| [`scripts/check-stale-dev-servers.ps1`](../scripts/check-stale-dev-servers.ps1) | Warning-only check for an orphaned dev server already holding port `5173`/`8010` before `npm run dev` starts fresh ones — an orphan keeps answering with outdated code while the new server fails to bind (see [development.md](development.md)). Also runnable via `npm run check-dev-servers`. |
| [`README.md`](../README.md) | Project overview, capabilities, and startup commands. |
| [`.github/workflows/build.yml`](../.github/workflows/build.yml), [`deploy/`](../deploy/) | CI image build and k3s deployment (Helm chart, ArgoCD app, Dockerfiles) — file-by-file map lives in [deployment.md](deployment.md). |
| [`docs/`](./) | Living project documentation ([index](./README.md)); frozen V1 specification archived in [`docs/spec/`](./spec/README.md) — reference only, do not read by default. |
