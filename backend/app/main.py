from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import APP_VERSION
from app.db import init_db
from app.ffmpeg import check_ffmpeg
from app.jobs.worker import JobWorker
from app.routers import (
    app_info,
    conversion_profiles,
    directories,
    files,
    health,
    jobs,
    logs,
    source,
    tree,
)

_worker = JobWorker()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.app_version = APP_VERSION
    app.state.ffmpeg_status = check_ffmpeg()
    _worker.start()
    yield
    _worker.stop()


app = FastAPI(title="Video Archive API", version=APP_VERSION, lifespan=lifespan)

app.include_router(health.router, prefix="/api")
app.include_router(app_info.router, prefix="/api")
app.include_router(source.router, prefix="/api")
app.include_router(tree.router, prefix="/api")
app.include_router(directories.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(conversion_profiles.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
