# Video Archive Tech Stack

This document fixes the concrete technology choices for Video Archive so that implementation does not have to guess. If a choice changes, update this file in the same change.

## Frontend

| Area | Choice | Notes |
| --- | --- | --- |
| Framework | React 18+ with TypeScript | Functional components and hooks |
| Build tool | Vite | Dev server on port `5173`, host `0.0.0.0` (LAN access), `/api` proxied to the backend |
| Localization | i18next (`react-i18next`) | English and Russian resource files, parity enforced by an automated key-set test |
| Styling | Plain CSS with CSS variables | Theme presets (eight) switch variable sets on `data-theme`; no heavy UI framework |
| Iconography | Lucide (`lucide-react`) | Thin-stroke outline icon set, imported as React components; avoids emoji (inconsistent/low-fidelity rendering across OSes, e.g. flag emoji on Windows) and reads more consistent with the app's muted Strict theme than filled/Material-style icon sets |
| Server state | Lightweight fetch hooks + React contexts | No API-client module; components call `fetch('/api/...')` directly, shared state lives in contexts |
| Testing | Vitest (+ `@testing-library/react` with per-file jsdom for component tests) | Pure-logic utility tests plus component tests; locale-parity test |

## Backend

| Area | Choice | Notes |
| --- | --- | --- |
| Language | Python 3.11+ | |
| Framework | FastAPI + Uvicorn | Port `8000`, host `0.0.0.0` (post-V1 — LAN access from phones/tablets); no authentication, trusted-network use only |
| Database | SQLite (single file next to the backend) | Accessed via SQLAlchemy Core; ordered migrations + schema version in a small `schema_meta` table; WAL + busy timeout since worker and request threads share the pool |
| Log streaming | Server-Sent Events (`sse-starlette`) | For the UI log viewer |
| Logging | Request-logging middleware + rotating file log | One line per request (quiet polling routes excepted); console + `logs/backend.log` |
| HTTP client | `httpx` | Provider calls and test client |
| Imaging | `opencv-python-headless`, `onnxruntime`, `Pillow`, `numpy` | Previews and detection |
| Secrets | `.env`-style file `backend/secrets.env`, loaded with `python-dotenv` | Git-ignored; holds provider API keys (per entry) and SMB credentials (per saved source); human-readable and easy to copy |
| SMB access | `smbprotocol` (its bundled `smbclient` module) | Local sources use the plain filesystem; retry-on-reconnect; heavy processing downloads a local temp copy |
| Testing | pytest | HTTP-layer tests via FastAPI's `TestClient`; SMB tested against an in-memory fake |

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

Model files are downloaded once and stored next to the backend, in `backend/models/` (git-ignored, created on demand); the backend must work (with reduced frame-selection quality) if a model file is missing. In practice (`app/detection.py`):

- YuNet and SFace have stable official direct-download URLs (OpenCV Model Zoo) and are fetched automatically, lazily, on first use.
- No stable official pre-exported ONNX file exists for YOLOv8n; person detection is enabled by placing `yolov8n.onnx` manually at `backend/models/yolov8n.onnx`. Without it, preview tile selection falls back to face detection and blur-score ranking only.

## Supported Video Extensions

Files with these extensions (case-insensitive) are treated as supported videos:

```text
mp4, m4v, mov, mkv, webm, avi, wmv, flv, mpg, mpeg,
m2v, ts, m2ts, mts, vob, 3gp, 3g2, ogv, asf, divx, rmvb
```

Anything else is listed in the browser as a plain file and excluded from video workflows. A JPEG whose base name matches a video in the same folder is treated as that video's preview asset (see [Specification Section 9.5](./specification.md#95-preview-storage)).

## Supported Image Extensions

Standalone images are first-class library items (post-V1): viewable, taggable (including AI tagging), and similarity-matched, but never converted and never given preview collages. Supported extensions (case-insensitive, disjoint from the video set):

```text
jpg, jpeg, png, gif, webp, bmp, tiff, tif
```

## AI Providers (Tagging)

| Provider | Use |
| --- | --- |
| OpenRouter | Gateway to many vision models; model catalog + live pricing API; reports actual billed cost per call |
| Google Gemini | Vision scoring; model catalog; batch API support |
| FAL | Vision workloads, best-effort (no fixed response schema, no catalog API); dual routing — direct `fal-ai/...` app endpoints or FAL's OpenRouter-gateway route to general-purpose vision LLMs (the gateway also reports billed cost) |
| Mistral | Vision scoring; model catalog; batch API support |

Provider configuration is a priority-ordered list of entries (any number per type) with automatic fallback for background jobs; see [Specification Section 18](./specification.md#18-ai-provider-settings-and-secrets). Tagging sends collage or per-frame images plus the user's AI tag vocabulary and expects index-ordered per-tag relevance scores (0–100) in a structured JSON response.

## Repository Layout (target)

```text
/               root package.json — starts frontend + backend together
/frontend       Vite + React + TypeScript app
/backend        FastAPI app (app/), secrets.env, SQLite db file, model files, preview_cache/
/docs           living docs (code maps, architecture, development) + spec/ (this folder)
```

The root `package.json` uses `concurrently` to run `npm run dev --prefix frontend` and `npm run dev --prefix backend`; the backend-local `package.json` wraps the Python startup so both halves start from one command on Windows.
