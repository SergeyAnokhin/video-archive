# Backend image: FastAPI + ffmpeg. Built by CI (.github/workflows/build.yml)
# with the `backend/` directory as the build context; pushed to
# ghcr.io/sergeyanokhin/video-archive/backend. See docs/deployment.md.
FROM python:3.12-slim

# ffmpeg/ffprobe are hard runtime dependencies (conversion, previews, media
# info); libglib2.0-0 is the one shared lib opencv-python-headless still
# needs that python-slim lacks.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# All mutable state (SQLite DB, secrets.env, preview cache, models, logs) goes
# under VIDEO_ARCHIVE_STATE_DIR, injected by the k8s Deployment as /data/state
# on the persistent volume (see app/config.py and the Helm chart).
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
