"""Tag Lab per-model feedback (user request): two independent signals for
picking a good provider entry, both aggregated by (provider_type,
model_name) -- same key `app/model_pricing.py` and `provider_usage_log`
already use, so entries sharing a model share one score.

1. Tag-accuracy rating: like/dislike on individual tags a run suggested,
   shown live in Tag Lab's result list (not gated on Apply).
2. Apply-behavior KPI: across every run of a model, how often the
   suggestion was applied unchanged, applied with edits, or never applied
   at all -- a separate, coarser trust signal.

`tag_lab_runs` snapshots exactly what a run suggested (tag id/name/score,
score > 0 only -- mirrors what Tag Lab's UI pre-selects) so later
feedback/apply events compare against that snapshot rather than
re-deriving from `file_tags`, which may have changed again since.
`not_applied_count` is derived (runs with no matching `tag_lab_applies`
row), not stored, so an abandoned session (closed tab, no explicit event)
is still counted correctly.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import text


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_run(
    engine, run_id: str, provider_type: str, model_name: str | None, file_id: str, suggested_tags: list[dict]
) -> None:
    """`suggested_tags`: `[{tag_id, display_name, score}]`, already filtered
    to `score > 0` by the caller (`app/tag_lab.py::run_tag_lab`)."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO tag_lab_runs (id, provider_type, model_name, file_id, suggested_tags_json, created_at)
                VALUES (:id, :provider_type, :model_name, :file_id, :suggested_tags_json, :now)
                """
            ),
            {
                "id": run_id,
                "provider_type": provider_type,
                "model_name": model_name,
                "file_id": file_id,
                "suggested_tags_json": json.dumps(suggested_tags),
                "now": _now(),
            },
        )


def set_tag_vote(engine, run_id: str, tag_id: str, display_name: str, vote: int | None) -> None:
    """`vote=None` clears back to neutral (deletes the row) -- clicking an
    already-active like/dislike button again toggles it off, matching a
    tag with no vote at all rather than a third explicit "neutral" state."""
    with engine.begin() as conn:
        if vote is None:
            conn.execute(
                text("DELETE FROM tag_lab_tag_feedback WHERE run_id = :run_id AND tag_id = :tag_id"),
                {"run_id": run_id, "tag_id": tag_id},
            )
            return
        conn.execute(
            text(
                """
                INSERT INTO tag_lab_tag_feedback (run_id, tag_id, display_name, vote, created_at)
                VALUES (:run_id, :tag_id, :display_name, :vote, :now)
                ON CONFLICT(run_id, tag_id) DO UPDATE SET
                    vote = :vote, display_name = :display_name, created_at = :now
                """
            ),
            {"run_id": run_id, "tag_id": tag_id, "display_name": display_name, "vote": vote, "now": _now()},
        )


def record_apply(engine, run_id: str, applied_tag_ids: list[str]) -> None:
    """Compares `applied_tag_ids` (every tag_id Tag Lab's apply step wrote,
    model-sourced and manually-added alike) against the run's
    suggested-tag snapshot by tag_id set equality: an exact match is
    "unchanged", anything else (added, removed, or both) is "changed".
    No-op if `run_id` doesn't match a known run."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT suggested_tags_json FROM tag_lab_runs WHERE id = :run_id"), {"run_id": run_id}
        ).fetchone()
    if row is None:
        return
    suggested_ids = {tag["tag_id"] for tag in json.loads(row.suggested_tags_json)}
    unchanged = suggested_ids == set(applied_tag_ids)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO tag_lab_applies (run_id, unchanged, created_at)
                VALUES (:run_id, :unchanged, :now)
                ON CONFLICT(run_id) DO UPDATE SET unchanged = :unchanged, created_at = :now
                """
            ),
            {"run_id": run_id, "unchanged": unchanged, "now": _now()},
        )


def get_model_stats(engine, provider_type: str, model_name: str | None) -> dict:
    with engine.connect() as conn:
        vote_row = conn.execute(
            text(
                """
                SELECT
                    SUM(CASE WHEN f.vote = 1 THEN 1 ELSE 0 END) AS likes,
                    SUM(CASE WHEN f.vote = -1 THEN 1 ELSE 0 END) AS dislikes
                FROM tag_lab_tag_feedback f
                JOIN tag_lab_runs r ON r.id = f.run_id
                WHERE r.provider_type = :provider_type AND r.model_name IS :model_name
                """
            ),
            {"provider_type": provider_type, "model_name": model_name},
        ).fetchone()
        apply_row = conn.execute(
            text(
                """
                SELECT
                    COUNT(r.id) AS runs_total,
                    COUNT(a.run_id) AS applied_count,
                    SUM(CASE WHEN a.unchanged THEN 1 ELSE 0 END) AS applied_unchanged_count
                FROM tag_lab_runs r
                LEFT JOIN tag_lab_applies a ON a.run_id = r.id
                WHERE r.provider_type = :provider_type AND r.model_name IS :model_name
                """
            ),
            {"provider_type": provider_type, "model_name": model_name},
        ).fetchone()

    runs_total = apply_row.runs_total or 0
    applied_count = apply_row.applied_count or 0
    applied_unchanged_count = apply_row.applied_unchanged_count or 0
    return {
        "provider_type": provider_type,
        "model_name": model_name,
        "likes": vote_row.likes or 0,
        "dislikes": vote_row.dislikes or 0,
        "runs_total": runs_total,
        "applied_count": applied_count,
        "not_applied_count": runs_total - applied_count,
        "applied_unchanged_count": applied_unchanged_count,
        "applied_changed_count": applied_count - applied_unchanged_count,
    }


def get_all_model_stats(engine) -> list[dict]:
    """One entry per `(provider_type, model_name)` that has at least one
    run, for Tag Lab's model picker."""
    with engine.connect() as conn:
        pairs = conn.execute(text("SELECT DISTINCT provider_type, model_name FROM tag_lab_runs")).all()
    return [get_model_stats(engine, row.provider_type, row.model_name) for row in pairs]


__all__ = [
    "record_run",
    "set_tag_vote",
    "record_apply",
    "get_model_stats",
    "get_all_model_stats",
]
