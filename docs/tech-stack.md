# Video Archive Tech Stack

This document fixes the concrete technology choices for Video Archive so that implementation does not have to guess. If a choice changes, update this file in the same change.

## Frontend

| Area | Choice | Notes |
| --- | --- | --- |
| Framework | React 18+ with TypeScript | Functional components and hooks |
| Build tool | Vite | Dev server on `127.0.0.1:5173`, `/api` proxied to the backend |
| Localization | i18next (`react-i18next`) | English and Russian resource files, parity required |
| Styling | Plain CSS with CSS variables | Theme presets (Strict/Playful) switch variable sets; no heavy UI framework |
| Iconography | Lucide (`lucide-react`) | Thin-stroke outline icon set, imported as React components; avoids emoji (inconsistent/low-fidelity rendering across OSes, e.g. flag emoji on Windows) and reads more consistent with the app's muted Strict theme than filled/Material-style icon sets |
| Server state | Lightweight fetch hooks or TanStack Query | Keep simple; add TanStack Query only when polling/caching demands it |

## Backend

| Area | Choice | Notes |
| --- | --- | --- |
| Language | Python 3.11+ | |
| Framework | FastAPI + Uvicorn | Bound to `127.0.0.1:8000` only; no external exposure |
| Database | SQLite (single file next to the backend) | Accessed via SQLAlchemy 2.x; schema version tracked in a small `schema_meta` table |
| Log streaming | Server-Sent Events (`sse-starlette`) | For the UI log viewer |
| Secrets | `.env`-style file `backend/secrets.env`, loaded with `python-dotenv` | Git-ignored; holds provider API keys and source credentials; human-readable and easy to copy |
| SMB access | `smbprotocol` | Local sources use the plain filesystem |

## Media Processing

| Area | Choice | Notes |
| --- | --- | --- |
| Conversion / probing / frame extraction | ffmpeg + ffprobe | Required external dependency, must be on `PATH` (Windows: `winget install ffmpeg`); backend verifies availability at startup and reports it in `/api/app/info` |
| Video codec default | libx265 (H.265), MP4 container | CRF quality model, default CRF 26, practical range 22–32 |
| Audio | Dropped by default (`-an`) | Opt-out per conversion profile |

## Local Detection Models

Chosen for good quality on a modest CPU with limited RAM — all run via OpenCV / ONNX Runtime, no GPU required:

| Task | Model | Notes |
| --- | --- | --- |
| Face detection | YuNet (OpenCV model zoo) | Tiny, fast, good accuracy; ships as a small ONNX file |
| Face embeddings (identity diversity) | SFace (OpenCV model zoo) | Optional; used only to pick two *different* faces for the first two enlarged tiles; skip gracefully if too slow |
| Person / figure detection | YOLOv8n (ONNX, via `onnxruntime`) | Nano variant (~6 MB); person class only |
| Blur scoring | Laplacian variance (OpenCV) | Cheap sharpness heuristic for frame ranking |

Model files are downloaded once and stored next to the backend; the backend must work (with reduced frame-selection quality) if a model file is missing.

## Supported Video Extensions

Files with these extensions (case-insensitive) are treated as supported videos:

```text
mp4, m4v, mov, mkv, webm, avi, wmv, flv, mpg, mpeg,
m2v, ts, m2ts, mts, vob, 3gp, 3g2, ogv, asf, divx, rmvb
```

Anything else is listed in the browser as a plain file and excluded from video workflows. A JPEG whose base name matches a video in the same folder is treated as that video's preview asset (see [Specification Section 9.5](./specification.md#95-preview-storage)).

## AI Providers (Tagging)

| Provider | Use |
| --- | --- |
| OpenRouter | Gateway to many vision models |
| Google Gemini | Vision scoring; batch API support |
| FAL | Vision workloads |
| Mistral | Vision scoring; batch API support |

Tagging sends one collage image plus the user's tag vocabulary and expects per-tag relevance scores (0–100) in a structured JSON response.

## Repository Layout (target)

```text
/               root package.json — starts frontend + backend together
/frontend       Vite + React + TypeScript app
/backend        FastAPI app (app/), secrets.env, SQLite db file, model files
/docs           specifications (this folder)
```

The root `package.json` uses `concurrently` to run `npm run dev --prefix frontend` and `npm run dev --prefix backend`; the backend-local `package.json` wraps the Python startup so both halves start from one command on Windows.
