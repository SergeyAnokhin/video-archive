# Specification Archive

This folder holds the reference specification for the Video Archive application. It was originally written as the pre-implementation V1 specification; after V1 was completed, the application kept evolving, and on 2026-07-16 the documents were refreshed to fold in the post-V1 improvements that shipped since (multi-source support, the two-lane job worker with pause/resume, animated GIF previews, Tag Lab, tag pools and colors, standalone image support, scoped search, the expanded theme set, and more).

These documents describe intent and product behavior at the level of a specification. They are still **not the living documentation**: for the current file-by-file truth, trust the code and the living docs in [`docs/`](../README.md) (`architecture.md`, `code-map*.md`). Consult this folder when a question is about product intent, scope, or the reasoning behind a behavior — not for day-to-day navigation.

| File | Contents |
| --- | --- |
| [`specification.md`](specification.md) | Main technical specification |
| [`roadmap.md`](roadmap.md) | V1 stage-by-stage plan (all complete) plus the post-V1 improvement log |
| [`tech-stack.md`](tech-stack.md) | Fixed technology choices |
| [`data-model.md`](data-model.md) | Database schema |
| [`api-spec.md`](api-spec.md) | HTTP API surface |
| [`job-model.md`](job-model.md) | Background job model |
| [`settings-spec.md`](settings-spec.md) | Settings groups and semantics |
| [`ui-screens.md`](ui-screens.md) | Screen-by-screen UI description |
| [`design-system.md`](design-system.md) | Themes, breakpoints, localization presentation |
| [`backup-format.md`](backup-format.md) | Backup package format and source-switch flow |
