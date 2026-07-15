"""Tag vocabulary endpoints (API §10): CRUD over the vocabulary plus the
prefix-filtered listing used for search autocomplete (Specification §11.8).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app import tags as service
from app.db import get_engine

router = APIRouter()


class TagRequest(BaseModel):
    display_name: str
    is_active: bool = True
    is_ai_vocabulary: bool = True
    is_user_defined: bool = False
    sort_order: int = 0


def _not_found_error(tag_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": {"code": "tag_not_found", "message": f"Tag not found: {tag_id}"}},
    )


def _duplicate_error(exc: service.DuplicateTagError) -> HTTPException:
    return HTTPException(status_code=409, detail={"error": {"code": "tag_already_exists", "message": str(exc)}})


@router.get("/tags")
def list_tags(
    query: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    limit: int | None = Query(default=None, ge=1, le=1000),
    category: str | None = Query(default=None),
):
    return {
        "tags": service.list_tags(
            get_engine(), query=query, active_only=active_only, limit=limit, category=category
        )
    }


@router.get("/tags/used")
def list_used_tags(
    query: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=1000),
):
    return {"tags": service.list_used_tags(get_engine(), query=query, limit=limit)}


@router.post("/tags")
def create_tag(body: TagRequest):
    try:
        return service.create_tag(get_engine(), body.model_dump())
    except service.DuplicateTagError as exc:
        raise _duplicate_error(exc)


@router.put("/tags/{tag_id}")
def update_tag(tag_id: str, body: TagRequest):
    try:
        tag = service.update_tag(get_engine(), tag_id, body.model_dump())
    except service.DuplicateTagError as exc:
        raise _duplicate_error(exc)
    if tag is None:
        raise _not_found_error(tag_id)
    return tag


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: str):
    deleted = service.delete_tag(get_engine(), tag_id)
    if not deleted:
        raise _not_found_error(tag_id)
    return {"deleted": True}
