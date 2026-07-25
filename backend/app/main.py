from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import batch_submissions
from app.config import APP_VERSION
from app.db import get_engine, init_db
from app.ffmpeg import check_ffmpeg
from app.hardware_accel import check_hardware_accel
from app.hardware_decode import check_hardware_decode, log_status as log_hardware_decode_status
from app.jobs import service as jobs_service
from app.jobs.worker import JobWorker
from app.log_rotation_settings import get_settings as get_log_rotation_settings
from app.logging_config import apply_rotation_settings, configure_logging
from app.request_logging import RequestLoggingMiddleware
from app.resource_monitor import ResourceMonitor
from app.routers import (
    app_info,
    app_settings,
    backend_health_settings,
    backup_settings,
    backups,
    conversion_profiles,
    conversion_settings,
    directories,
    files,
    health,
    interface_settings,
    jobs,
    log_files,
    log_rotation_settings,
    logs,
    performance_settings,
    playback,
    playback_settings,
    preview_layouts,
    preview_settings,
    providers,
    resource_monitor_settings,
    source,
    sources,
    system_stats,
    tag_lab,
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
_resource_monitor = ResourceMonitor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # `configure_logging()` ran at import time, before the DB existed, so it
    # started the file handler from log_rotation_settings' hardcoded
    # defaults -- sync it to whatever's actually persisted now that init_db
    # has seeded/loaded the row.
    _rotation_settings = get_log_rotation_settings(get_engine())
    apply_rotation_settings(_rotation_settings["max_bytes"], _rotation_settings["backup_count"])
    app.state.app_version = APP_VERSION
    app.state.ffmpeg_status = check_ffmpeg()
    app.state.hardware_accel_status = check_hardware_accel()
    app.state.hardware_decode_status = check_hardware_decode()
    log_hardware_decode_status(app.state.hardware_decode_status)
    # A `tag` job stuck `running` with an unresolved batch submission was
    # mid-poll when this process last stopped -- nothing else will ever pick
    # it back up (post-V1, user request "the batch task should survive a
    # service restart"), so put it back on the queue before the worker
    # starts; `app/jobs/tag.py::run_tag_job()` detects the pending
    # submission and resumes polling it instead of re-scanning the directory.
    batch_submissions.requeue_stalled_jobs(get_engine())
    # Any job still `running` after the requeue above was left behind by a
    # backend process that stopped/crashed mid-job -- nothing will ever move
    # it out of `running` on its own (post-V1, user report: a job stayed
    # stuck and un-restartable after a backend restart). Reap it to `failed`
    # so the existing Restart button becomes available for it.
    jobs_service.reap_orphaned_jobs(get_engine())
    _worker.start()
    _resource_monitor.start()
    yield
    _resource_monitor.stop()
    _worker.stop()


app = FastAPI(title="Video Archive API", version=APP_VERSION, lifespan=lifespan)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(health.router, prefix="/api")
app.include_router(system_stats.router, prefix="/api")
app.include_router(backend_health_settings.router, prefix="/api")
app.include_router(app_info.router, prefix="/api")
app.include_router(source.router, prefix="/api")
app.include_router(sources.router, prefix="/api")
app.include_router(tree.router, prefix="/api")
app.include_router(directories.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(interface_settings.router, prefix="/api")
app.include_router(conversion_profiles.router, prefix="/api")
app.include_router(conversion_settings.router, prefix="/api")
app.include_router(preview_layouts.router, prefix="/api")
app.include_router(preview_settings.router, prefix="/api")
app.include_router(tags.router, prefix="/api")
app.include_router(tagging_settings.router, prefix="/api")
app.include_router(tag_lab.router, prefix="/api")
app.include_router(providers.router, prefix="/api")
app.include_router(playback.router, prefix="/api")
app.include_router(playback_settings.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(log_files.router, prefix="/api")
app.include_router(log_rotation_settings.router, prefix="/api")
app.include_router(backups.router, prefix="/api")
app.include_router(backup_settings.router, prefix="/api")
app.include_router(performance_settings.router, prefix="/api")
app.include_router(resource_monitor_settings.router, prefix="/api")
app.include_router(app_settings.router, prefix="/api")
