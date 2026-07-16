# Video Archive Job Model

## Overview

This document defines the job system for Video Archive. The backend executes local processing jobs and provider-backed AI jobs through one queue model with multiple job types.

## Job Principles

- Every long-running operation is represented as a job.
- Conversion, preview, tagging, scan, cleanup, backup, and restore are separate job types.
- Folder jobs are recursive by default.
- Job execution happens on the backend machine.
- External provider requests are wrapped inside local jobs.

## Job Types

| Job Type | Scope | Notes |
| --- | --- | --- |
| `scan` | source | Initial or full source scan |
| `rescan` | source or directory | Refresh existing metadata |
| `convert` | directory or file | `production` or `test` mode; test mode may include variants |
| `preview` | directory or file | On-demand only |
| `tag` | directory or file | Uses external AI providers |
| `cleanup` | maintenance | Remove stale records |
| `optimize_db` | maintenance | Compact or optimize DB |
| `backup` | maintenance | Manual backup creation |
| `restore` | maintenance | Restore from backup |

Variant comparison (formerly "tuning") is not a separate job type: it is a file-scoped `convert` job in test mode with a `variants` parameter list (see [Specification Section 8.3](./specification.md#83-variant-comparison)).

## Job State Machine

Allowed states:

- `queued`
- `running`
- `paused` (post-V1; job types with a per-item loop only)
- `completed`
- `failed`
- `cancelled`

Optional item states:

- `skipped` (used by the skip-processed rule)

State rules:

- Jobs start in `queued`.
- Running jobs may transition to `paused`, `completed`, `failed`, or `cancelled`; paused jobs resume to `running` or are cancelled.
- Restarting creates a new job rather than mutating an old completed job into queued.
- Jobs track `total_items` so the UI can show a progress bar and a rolling-window ETA.

## Concurrency Model

Post-V1 evolution from the original single sequential worker (user request):

- The worker runs **two lanes**: a **CPU lane** (`rescan`, `convert`, `preview`, `cleanup`, `optimize_db`, `backup`, `restore` — one at a time, since they all compete for local ffmpeg/disk) and a **network lane** (`tag` — bounded by the external provider, not the CPU). At most one CPU job and one tag job run concurrently; each lane is FIFO over its own job types.
- **Within a `convert`/`preview` job, files are processed in parallel**, bounded by the global `parallel_workers` performance setting (default 4, range 1–16), read once at job launch.
- ffmpeg's internal multithreading for a single file is also allowed (its defaults are fine).
- **Pause/resume:** pausable job types (those with a per-item loop) can be paused; the handler notices the request between items, and the freed lane picks up the next queued job of that lane. Resuming re-enters the loop where it left off.

The UI reflects activity through the top-bar indicator: visible whenever a job is queued or running, tooltip shows the current job and item, click opens the jobs modal.

### Job Items Are Not a Separate State Machine

Unlike jobs, `job_items` rows (`app/jobs/service.py`) have no enforced transition graph — `start_job_item()`/`complete_job_item()`/`fail_job_item()`/`skip_job_item()` are plain status writes, safe to call more than once for the same item (e.g. `start_job_item()` again after a first attempt is superseded). Handlers that need a multi-phase per-item flow (create item up front, attempt one strategy, fall back to another) can rely on this — see the `tag` job's batch-tagging path (`app/jobs/tag.py`) for an example: an item may be marked `running` once during batch preparation and again during the per-file fallback for the same item id.

## Skip-Processed Rule

Bulk jobs skip already-processed files by default; the toggle is per job:

| Job type | Skipped when (default on) |
| --- | --- |
| `convert` | `converted_at` is set |
| `preview` | `has_preview_asset` is true |
| `tag` | `tagged_at` is set |

Disabling the toggle forces reprocessing of every file in scope (for example to reconvert at a different resolution, quality/CRF, or bitrate budget). Skipped files appear as `skipped` job items so the run remains auditable.

Independent of the toggle, bulk jobs always exclude test-mode artifacts recognized by naming pattern: preserved originals (`*.original.*`) and variant outputs (`*.variant-*.mp4`). These are processed only by explicit single-file actions (see [Specification Sections 8.2–8.3](./specification.md#82-test-mode)).

## Job Parameters

Each job stores a parameter snapshot.

Examples:

- conversion profile id and effective profile values (codec, container, max dimension, CRF, drop audio)
- conversion mode (`production` | `test`) and `skip_processed` flag
- variant list for variant-comparison runs
- preview preset id and effective layout values
- tagging provider/model choice and vocabulary snapshot reference
- recursion scope

## Conversion Jobs

### Production mode

- temp output file
- fast validation
- source replacement on success

### Test mode

- same pipeline (temp output, validation)
- source never deleted; the original is always renamed to `<basename>.original.<ext>`, even when extensions differ (see [Specification Section 8.2](./specification.md#82-test-mode))
- with `variants`: one output per variant named `<basename>.<variant>.mp4`

## Preview Jobs

- on-demand only
- may generate file previews and folder previews
- use local face and body analysis
- use preview settings snapshot at launch time
- write the JPEG collage next to the video on the source and the animated GIF into the local per-source preview cache; folder GIFs are generated for the target directory and every descendant (see [Specification Section 9.5](./specification.md#95-preview-storage))
- directory scope is self-healing: skip-processed re-checks that the on-source collage actually exists
- best-effort side effect: store the file's similarity signature

## Tagging Jobs

- on-demand only; cover videos and standalone images
- send a frame collage (or per-frame images, or the standalone image itself) plus the user's AI vocabulary to a vision model, expect per-tag relevance scores
- resolve the provider **entry** live at execution: enabled entries are tried in priority order, with automatic fallback to the next on failure (a per-job dead-entry set avoids retrying a failed entry)
- store the top-N tags with scores (default 10), replacing the file's previous tag set
- **batch mode** (Gemini/Mistral): submit all pending files as one provider-side batch, persist the submission (`batch_submissions`) *before* polling, poll with interruptible sleeps; pause/cancel just leaves the submission pending, and a backend restart re-queues the owning job, which resumes polling from the submission's own snapshot; unresolved files fall back to the per-file chain
- single-file AI tagging is *not* a job: it runs synchronously through Tag Lab ([Specification §12.4](./specification.md#124-tag-lab))

## Cancellation Rules

- Cancellation is best-effort and cooperative: handlers check a shared stop checkpoint between items.
- Jobs should stop accepting new items after cancellation request.
- In-flight file operations should exit safely.
- A **second** cancel on a running job force-finishes it (for handlers stuck in an unbounded blocking call); the worker lane logs the abandonment and moves on rather than staying wedged behind an unresponsive handler.
- Production conversion must never replace a source file after cancellation unless validation and swap already completed.

## Retry and Restart

- Failed jobs may be restarted from UI where supported.
- Restart creates a new job with copied parameters.
- Partial item completion should remain visible through job items and logs.

## Logs and Events

- Every job emits structured events.
- The UI log viewer consumes those events in near real time.
- Job item progress should be visible without reading raw logs.

## Retention

- Finished jobs (completed, failed, cancelled) are deleted automatically **24 hours** after they finish, together with their job items and related events.
- The user can also delete jobs manually at any time: individually, or all finished jobs with a single clear-all action.
- Long-term history is the backend console/file log, not the jobs table.
