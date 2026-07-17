# Documentation Index

This folder contains the living project documentation — the documents that are read and updated continuously during development. The completed V1 specification is archived separately in [`spec/`](spec/README.md) and is **not read by default** (see the note there).

## Living docs

| File | Contents | Update when |
| --- | --- | --- |
| [`code-map.md`](code-map.md) | File-by-file map of the implementation — an index over four parts: [frontend](code-map-frontend.md), [backend](code-map-backend.md), [HTTP routers](code-map-routers.md), [tests](code-map-tests.md) | Files are added, moved, or removed (update the matching part) |
| [`architecture.md`](architecture.md) | Current high-level architecture and cross-cutting conventions | A component, flow, or convention changes |
| [`development.md`](development.md) | Developer workflow: run, test, manual verification | Commands, test suites, or workflows change |
| [`deployment.md`](deployment.md) | k3s cluster deployment: CI → GHCR → ArgoCD flow, Helm chart, node placement switch, human checklist | Dockerfiles, chart, CI workflow, or cluster setup change |

Project overview and startup instructions live in the root [`README.md`](../README.md).

## Archived

- [`spec/`](spec/README.md) — reference specification set (originally the V1 spec; refreshed 2026-07-16 to include post-V1 improvements). Reference only; do not read unless explicitly asked.
