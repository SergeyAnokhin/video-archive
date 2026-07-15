"""Tests for `app/tag_lab_feedback.py` (user request -- two independent
per-model signals: like/dislike tag-accuracy rating, and an
applied-unchanged/edited/never-applied KPI).
"""

from __future__ import annotations

import uuid

from app import tag_lab_feedback


def _run(engine, provider_type="openrouter", model_name="xiaomi/mimo-v2.5", suggested=None):
    run_id = str(uuid.uuid4())
    suggested = suggested if suggested is not None else [
        {"tag_id": "t1", "display_name": "cat", "score": 90},
        {"tag_id": "t2", "display_name": "dog", "score": 60},
    ]
    tag_lab_feedback.record_run(engine, run_id, provider_type, model_name, "file-1", suggested)
    return run_id


def test_get_model_stats_empty_when_no_runs(engine):
    stats = tag_lab_feedback.get_model_stats(engine, "openrouter", "xiaomi/mimo-v2.5")
    assert stats["likes"] == 0
    assert stats["dislikes"] == 0
    assert stats["runs_total"] == 0
    assert stats["applied_count"] == 0
    assert stats["not_applied_count"] == 0
    assert stats["applied_unchanged_count"] == 0
    assert stats["applied_changed_count"] == 0


def test_set_tag_vote_like_and_dislike_counted(engine):
    run_id = _run(engine)
    tag_lab_feedback.set_tag_vote(engine, run_id, "t1", "cat", 1)
    tag_lab_feedback.set_tag_vote(engine, run_id, "t2", "dog", -1)

    stats = tag_lab_feedback.get_model_stats(engine, "openrouter", "xiaomi/mimo-v2.5")
    assert stats["likes"] == 1
    assert stats["dislikes"] == 1


def test_set_tag_vote_can_be_changed_and_cleared(engine):
    run_id = _run(engine)
    tag_lab_feedback.set_tag_vote(engine, run_id, "t1", "cat", 1)
    tag_lab_feedback.set_tag_vote(engine, run_id, "t1", "cat", -1)  # flip like -> dislike
    stats = tag_lab_feedback.get_model_stats(engine, "openrouter", "xiaomi/mimo-v2.5")
    assert stats["likes"] == 0
    assert stats["dislikes"] == 1

    tag_lab_feedback.set_tag_vote(engine, run_id, "t1", "cat", None)  # clear back to neutral
    stats = tag_lab_feedback.get_model_stats(engine, "openrouter", "xiaomi/mimo-v2.5")
    assert stats["likes"] == 0
    assert stats["dislikes"] == 0


def test_record_apply_exact_match_is_unchanged(engine):
    run_id = _run(engine)
    tag_lab_feedback.record_apply(engine, run_id, ["t1", "t2"])
    stats = tag_lab_feedback.get_model_stats(engine, "openrouter", "xiaomi/mimo-v2.5")
    assert stats["runs_total"] == 1
    assert stats["applied_count"] == 1
    assert stats["not_applied_count"] == 0
    assert stats["applied_unchanged_count"] == 1
    assert stats["applied_changed_count"] == 0


def test_record_apply_added_tag_is_changed(engine):
    run_id = _run(engine)
    tag_lab_feedback.record_apply(engine, run_id, ["t1", "t2", "t3-manual"])
    stats = tag_lab_feedback.get_model_stats(engine, "openrouter", "xiaomi/mimo-v2.5")
    assert stats["applied_unchanged_count"] == 0
    assert stats["applied_changed_count"] == 1


def test_record_apply_removed_tag_is_changed(engine):
    run_id = _run(engine)
    tag_lab_feedback.record_apply(engine, run_id, ["t1"])
    stats = tag_lab_feedback.get_model_stats(engine, "openrouter", "xiaomi/mimo-v2.5")
    assert stats["applied_unchanged_count"] == 0
    assert stats["applied_changed_count"] == 1


def test_run_never_applied_counts_as_not_applied(engine):
    _run(engine)
    stats = tag_lab_feedback.get_model_stats(engine, "openrouter", "xiaomi/mimo-v2.5")
    assert stats["runs_total"] == 1
    assert stats["applied_count"] == 0
    assert stats["not_applied_count"] == 1


def test_get_all_model_stats_lists_every_run_model(engine):
    _run(engine, provider_type="openrouter", model_name="xiaomi/mimo-v2.5")
    _run(engine, provider_type="gemini", model_name="gemini-2.5-flash")

    all_stats = tag_lab_feedback.get_all_model_stats(engine)
    keys = {(row["provider_type"], row["model_name"]) for row in all_stats}
    assert keys == {("openrouter", "xiaomi/mimo-v2.5"), ("gemini", "gemini-2.5-flash")}


def test_stats_aggregate_across_multiple_runs_of_same_model(engine):
    run_a = _run(engine)
    run_b = _run(engine)
    tag_lab_feedback.set_tag_vote(engine, run_a, "t1", "cat", 1)
    tag_lab_feedback.set_tag_vote(engine, run_b, "t1", "cat", 1)
    tag_lab_feedback.record_apply(engine, run_a, ["t1", "t2"])

    stats = tag_lab_feedback.get_model_stats(engine, "openrouter", "xiaomi/mimo-v2.5")
    assert stats["likes"] == 2
    assert stats["runs_total"] == 2
    assert stats["applied_count"] == 1
    assert stats["not_applied_count"] == 1
