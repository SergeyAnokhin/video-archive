from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import batch_submissions
from app.config import APP_VERSION
from app.db import get_engine, init_db
from app.ffmpeg import check_ffmpeg
from app.jobs.worker import JobWorker
from app.logging_config import configure_logging
from app.request_logging import RequestLoggingMiddleware
from app.routers import (
    app_info,
    backup_settings,
    backups,
    conversion_profiles,
    directories,
    files,
    health,
    interface_settings,
    jobs,
    logs,
    performance_settings,
    playback,
    playback_settings,
    preview_layouts,
    preview_settings,
    providers,
    source,
    sources,
    tagging_settings,
    tags,
    tree,
)

# Background-job errors (failed preview/convert/tag items, whole-job
# crashes) are otherwise only recorded in the DB-backed event log -- this
# makes them show up in the terminal running the backend too, and (via the
# rotating file handler) in `backend/logs/backend.log` for after-the-fact
# analysis. Root-level so it also covers loggers elsewhere in `app.*` should
# any start using them.
configure_logging()

_worker = JobWorker()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.app_version = APP_VERSION
    app.state.ffmpeg_status = check_ffmpeg()
    # A `tag` job stuck `running` with an unresolved batch submission was
    # mid-poll when this process last stopped -- nothing else will ever pick
    # it back up (post-V1, user request "the batch task should survive a
    # service restart"), so put it back on the queue before the worker
    # starts; `app/jobs/tag.py::run_tag_job()` detects the pending
    # submission and resumes polling it instead of re-scanning the directory.
    batch_submissions.requeue_stalled_jobs(get_engine())
    _worker.start()
    yield
    _worker.stop()


app = FastAPI(title="Video Archive API", version=APP_VERSION, lifespan=lifespan)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(health.router, prefix="/api")
app.include_router(app_info.router, prefix="/api")
app.include_router(source.router, prefix="/api")
app.include_router(sources.router, prefix="/api")
app.include_router(tree.router, prefix="/api")
app.include_router(directories.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(interface_settings.router, prefix="/api")
app.include_router(conversion_profiles.router, prefix="/api")
app.include_router(preview_layouts.router, prefix="/api")
app.include_router(preview_settings.router, prefix="/api")
app.include_router(tags.router, prefix="/api")
app.include_router(tagging_settings.router, prefix="/api")
app.include_router(providers.router, prefix="/api")
app.include_router(playback.router, prefix="/api")
app.include_router(playback_settings.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(backups.router, prefix="/api")
app.include_router(backup_settings.router, prefix="/api")
app.include_router(performance_settings.router, prefix="/api")
