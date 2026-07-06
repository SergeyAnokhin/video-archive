from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import APP_VERSION
from app.db import init_db
from app.ffmpeg import check_ffmpeg
from app.routers import app_info, directories, files, health, source, tree


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.app_version = APP_VERSION
    app.state.ffmpeg_status = check_ffmpeg()
    yield


app = FastAPI(title="Video Archive API", version=APP_VERSION, lifespan=lifespan)

app.include_router(health.router, prefix="/api")
app.include_router(app_info.router, prefix="/api")
app.include_router(source.router, prefix="/api")
app.include_router(tree.router, prefix="/api")
app.include_router(directories.router, prefix="/api")
app.include_router(files.router, prefix="/api")
