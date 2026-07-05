# Video Archive Job Model

## Overview

This document defines the job system for Video Archive. The backend executes local processing jobs and provider-backed AI jobs through one queue model with multiple job types.

## Job Principles

- Every long-running operation is represented as a job.
- Conversion, preview, tagging, tuning, scan, cleanup, backup, and restore are separate job types.
- Folder jobs are recursive by default.
- Job execution happens on the backend machine.
- External provider requests are wrapped inside local jobs.

## Job Types

| Job Type | Scope | Notes |
| --- | --- | --- |
| `scan` | source | Initial or full source scan |
| `rescan` | source or directory | Refresh existing metadata |
| `convert` | directory or file | Production or test mode |
| `preview` | directory or file | On-demand only |
| `tag` | directory or file | Uses external AI providers |
| `tune` | file | Generates separate outputs only |
| `cleanup` | maintenance | Remove stale records |
| `optimize_db` | maintenance | Compact or optimize DB |
| `backup` | maintenance | Manual backup creation |
| `restore` | maintenance | Restore from backup |

## Job State Machine

Allowed states:

- `queued`
- `running`
- `completed`
- `failed`
- `cancelled`

Optional item states:

- `skipped`

State rules:

- Jobs start in `queued`.
- Running jobs may transition to `completed`, `failed`, or `cancelled`.
- Restarting creates a new job rather than mutating an old completed job into queued.

## Job Scopes

### Source scope

- full scan
- reconnect-driven scan
- whole-library maintenance

### Directory scope

- recursive convert
- recursive preview
- recursive tag
- recursive rescan

### File scope

- single-file convert
- single-file preview
- single-file tag
- single-file tuning

## Job Parameters

Each job stores a parameter snapshot.

Examples:

- conversion profile id and effective profile values
- preview preset id and effective layout values
- tagging provider/model choice
- playback-independent processing flags
- recursion mode

## Conversion Jobs

### Production mode

- temp output file
- fast validation
- source replacement on success

### Test mode

- temp or separate output
- source preserved
- output renamed using test pattern

### Tuning mode

- always separate outputs
- never replaces source
- supports parameter sweeps

## Preview Jobs

- on-demand only
- may generate file previews and folder previews
- use local face and body analysis
- use preview settings snapshot at launch time

## Tagging Jobs

- on-demand only
- use allowed vocabulary from settings
- may batch provider submissions
- store tags plus confidence scores

## Concurrency Model

- Queue is central and serialized at the scheduler level.
- Worker concurrency is configurable.
- Parallel execution may happen across files when allowed by settings and available resources.
- A single heavy conversion item may also use internal encoder parallelism.

## Cancellation Rules

- Cancellation is best-effort.
- Jobs should stop accepting new items after cancellation request.
- In-flight file operations should exit safely.
- Production conversion must never replace a source file after cancellation unless validation and swap already completed.

## Retry and Restart

- Failed jobs may be restarted from UI where supported.
- Restart typically creates a new job with copied parameters.
- Partial item completion should remain visible through job items and logs.

## Logs and Events

- Every job emits structured events.
- The UI log viewer consumes those events in near real time.
- Job item progress should be visible without reading raw logs.

Current foundation note:

- `scan` and `rescan` perform real metadata refresh work.
- `convert`, `preview`, `tag`, and `tune` already use the same persisted queue, item, and event model, but their heavy processing steps are still placeholder-only in the current implementation.

## Retention

- Completed and failed jobs remain visible until removed by policy or explicit user cleanup.
- Removal from the UI should not silently discard critical audit history if that history is still required elsewhere.
