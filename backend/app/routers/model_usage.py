"""Read-only AI model usage statistics for Settings."""

from fastapi import APIRouter

from app.db import get_engine
from app.model_usage import list_usage
from app.external_batches import list_active

router = APIRouter()


@router.get("/settings/model-usage")
def get_model_usage():
    return {"usage": list_usage(get_engine())}


@router.get("/external-batches")
def get_external_batches():
    return {"batches": list_active(get_engine())}
