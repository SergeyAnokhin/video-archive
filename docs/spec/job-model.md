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
- `completed`
- `failed`
- `cancelled`

Optional item states:

- `skipped` (used by the skip-processed rule)

State rules:

- Jobs start in `queued`.
- Running jobs may transition to `completed`, `failed`, or `cancelled`.
- Restarting creates a new job rather than mutating an old completed job into queued.

## Concurrency Model

Deliberately simple for V1:

- **Exactly one job runs at a time.** The queue is strictly FIFO and sequential.
- **Within a job, files are processed one at a time.** No parallel job items.
- ffmpeg's internal multithreading for a single file is allowed (its defaults are fine).
- If CPU utilization proves insufficient in practice, configurable parallelism may be introduced later — not in V1.

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
- write collages next to the videos (see [Specification Section 9.5](./specification.md#95-preview-storage))

## Tagging Jobs

- on-demand only
- send a frame collage plus the user vocabulary to a vision model, expect per-tag relevance scores
- store the top-N tags with scores (default 10)
- may batch provider submissions when available

## Cancellation Rules

- Cancellation is best-effort.
- Jobs should stop accepting new items after cancellation request.
- In-flight file operations should exit safely.
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
