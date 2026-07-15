"""Tag Lab endpoints (user request): a synchronous, single-file alternative
to `POST /jobs/tag-file` for comparing AI providers/models one at a time.
`run` calls exactly one provider entry directly (no fallback chain, no
batch API) and returns everything the review UI needs without writing
anything; `apply` is the only endpoint that actually writes `file_tags`,
once the user has reviewed/edited the suggestion.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app import tag_lab as service
from app import tag_lab_feedback
from app.db import get_engine
from app.tags import resolve_tag_color

router = APIRouter()

_TAG_LAB_ERROR_STATUS = {
    "file_not_found": 404,
    "source_file_missing": 404,
    "provider_entry_not_found": 404,
    "empty_tag_vocabulary": 400,
    "provider_not_configured": 400,
    "tag_lab_failed": 400,
}


def _tag_lab_http_error(err: service.TagLabError) -> HTTPException:
    error: dict = {"code": err.code, "message": err.message}
    if err.raw_response is not None:
        error["raw_response"] = err.raw_response
    if err.raw_full_response is not None:
        error["raw_full_response"] = err.raw_full_response
    return HTTPException(status_code=_TAG_LAB_ERROR_STATUS[err.code], detail={"error": error})


@router.post("/files/{file_id}/tag-lab/prepare")
def prepare_tag_lab(file_id: str):
    """Returns just the images + prompt a run would send (user request --
    show this immediately, before the model call that follows returns)."""
    try:
        return service.prepare_tag_lab(get_engine(), file_id)
    except service.TagLabError as err:
        raise _tag_lab_http_error(err)


class TagLabRunRequest(BaseModel):
    provider_entry_id: str


@router.post("/files/{file_id}/tag-lab/run")
def run_tag_lab(file_id: str, body: TagLabRunRequest):
    try:
        return service.run_tag_lab(get_engine(), file_id, body.provider_entry_id)
    except service.TagLabError as err:
        raise _tag_lab_http_error(err)


class TagLabApplyTag(BaseModel):
    tag_id: str | None = None
    display_name: str | None = None
    score: int = 0


class TagLabApplyRequest(BaseModel):
    provider_type: str
    model_name: str | None = None
    run_id: str | None = None
    tags: list[TagLabApplyTag]


@router.post("/files/{file_id}/tag-lab/apply")
def apply_tag_lab(file_id: str, body: TagLabApplyRequest):
    try:
        service.apply_tag_lab_result(
            get_engine(), file_id, [tag.model_dump() for tag in body.tags],
            body.provider_type, body.model_name, body.run_id,
        )
    except service.TagLabError as err:
        raise _tag_lab_http_error(err)

    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT tc.id AS tag_id, tc.display_name, tc.color, ft.score, ft.provider_name, ft.model_name,
                       ft.assigned_at
                FROM file_tags ft
                JOIN tag_catalog tc ON tc.id = ft.tag_id
                WHERE ft.file_id = :file_id AND ft.score > 0
                ORDER BY ft.score DESC
                """
            ),
            {"file_id": file_id},
        ).all()

    return {
        "tags": [
            {
                "tag_id": row.tag_id,
                "display_name": row.display_name,
                "color": resolve_tag_color(row.tag_id, row.color),
                "score": row.score,
                "provider_name": row.provider_name,
                "model_name": row.model_name,
                "assigned_at": row.assigned_at,
            }
            for row in rows
        ]
    }


class TagLabFeedbackRequest(BaseModel):
    tag_id: str
    display_name: str
    vote: int | None = None


@router.post("/tag-lab/runs/{run_id}/feedback")
def set_tag_lab_feedback(run_id: str, body: TagLabFeedbackRequest):
    """Like/dislike on one tag from a Tag Lab run's result list (user
    request -- rate the model's raw suggestion, independent of what ends
    up applied). `vote`: 1 (like), -1 (dislike), or omitted/null to clear
    back to neutral."""
    tag_lab_feedback.set_tag_vote(get_engine(), run_id, body.tag_id, body.display_name, body.vote)
    return {"ok": True}
