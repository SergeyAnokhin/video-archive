"""`convert` job execution (Job Model "Job Types", Specification §6.2, §8).

Handles both scopes:

- **directory** (recursive): converts every supported video under a subtree,
  honoring the skip-processed rule and always excluding test-mode artifacts
  (`.original.`/`.variant-` names).
- **file**: either a single production/test conversion, or — when
  `parameters.variants` is present — a variant-comparison sweep that never
  touches the source file at all (Specification §8.3).

Production mode replaces the source only after the converted output passes
validation (Specification §8.1); test mode (single-profile or variants) never
deletes the source (Specification §8.2-8.3).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app import conversion, conversion_profiles
from app.jobs import service
from app.media import is_test_artifact


class ConversionError(Exception):
    """Raised when an encode or its validation fails; the source is
    guaranteed untouched whenever this is raised."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel(source_root: Path, path: Path) -> str:
    return path.relative_to(source_root).as_posix()


def _effective_params(profile: dict, overrides: dict | None) -> dict:
    overrides = overrides or {}
    return {
        "video_codec": overrides.get("video_codec", profile["video_codec"]),
        "container": profile["container"],
        "crf": overrides.get("crf", profile["crf"]),
        "drop_audio": profile["drop_audio"],
        "max_dimension": overrides.get("max_dimension", profile.get("max_dimension")),
        "extra_encoder_args": profile.get("extra_encoder_args"),
    }


def _temp_output_path(directory: Path, stem: str, container: str) -> Path:
    return directory / f".{stem}.convert-{uuid.uuid4().hex[:8]}.{container}"


def _encode_and_validate(source_path: Path, temp_path: Path, params: dict) -> None:
    source_info = conversion.probe_media(source_path)
    max_dim = conversion.effective_max_dimension(source_info, params["max_dimension"])
    args = conversion.build_ffmpeg_command(
        source_path,
        temp_path,
        video_codec=params["video_codec"],
        crf=params["crf"],
        drop_audio=params["drop_audio"],
        max_dimension=max_dim,
        extra_encoder_args=params["extra_encoder_args"],
    )
    ok, error = conversion.run_ffmpeg(args)
    if not ok:
        if temp_path.exists():
            temp_path.unlink()
        raise ConversionError(f"ffmpeg failed: {error}")

    valid, reason = conversion.validate_converted_output(
        temp_path, video_codec=params["video_codec"], container=params["container"]
    )
    if not valid:
        # Validation failed: discard the temp output only. The source has
        # not been touched yet in either mode (Specification §8.1 rule 4).
        temp_path.unlink()
        raise ConversionError(f"Validation failed: {reason}")


def _has_preview(directory: Path, stem: str) -> bool:
    return (directory / f"{stem}.jpg").exists()


def _replace_production(engine, source_root: Path, file_row, profile: dict, profile_id: str) -> dict:
    old_path = source_root / file_row.relative_path
    directory = old_path.parent
    stem = old_path.stem
    params = _effective_params(profile, None)

    temp_path = _temp_output_path(directory, stem, params["container"])
    _encode_and_validate(old_path, temp_path, params)

    final_path = directory / f"{stem}.{params['container']}"
    os.replace(temp_path, final_path)
    if final_path != old_path and old_path.exists():
        old_path.unlink()

    stat = final_path.stat()
    now = _now()

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE files
                SET relative_path = :rel, file_name = :file_name, extension = :ext,
                    size_bytes = :size, modified_at = :modified_at, is_video_supported = 1,
                    has_preview_asset = :has_preview, converted_at = :now,
                    last_conversion_profile_id = :profile_id, last_scanned_at = :now, updated_at = :now
                WHERE id = :id
                """
            ),
            {
                "rel": _rel(source_root, final_path),
                "file_name": final_path.name,
                "ext": params["container"],
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "has_preview": _has_preview(directory, stem),
                "now": now,
                "profile_id": profile_id,
                "id": file_row.id,
            },
        )

    return {"output_ref": _rel(source_root, final_path)}


def _replace_test_mode(engine, source_root: Path, file_row, profile: dict, profile_id: str) -> dict:
    old_path = source_root / file_row.relative_path
    directory = old_path.parent
    stem = old_path.stem
    original_ext = file_row.extension
    params = _effective_params(profile, None)

    temp_path = _temp_output_path(directory, stem, params["container"])
    _encode_and_validate(old_path, temp_path, params)

    # Original is always renamed, even without a name collision, so preserved
    # originals stay uniformly recognizable (Specification §8.2).
    renamed_original_path = directory / f"{stem}.original.{original_ext}"
    os.replace(old_path, renamed_original_path)
    new_output_path = directory / f"{stem}.{params['container']}"
    os.replace(temp_path, new_output_path)

    now = _now()
    has_preview = _has_preview(directory, stem)
    orig_stat = renamed_original_path.stat()
    new_stat = new_output_path.stat()
    new_file_id = str(uuid.uuid4())

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE files
                SET relative_path = :rel, file_name = :file_name, extension = :ext,
                    size_bytes = :size, modified_at = :modified_at,
                    has_preview_asset = :has_preview, last_scanned_at = :now, updated_at = :now
                WHERE id = :id
                """
            ),
            {
                "rel": _rel(source_root, renamed_original_path),
                "file_name": renamed_original_path.name,
                "ext": original_ext,
                "size": orig_stat.st_size,
                "modified_at": datetime.fromtimestamp(orig_stat.st_mtime, tz=timezone.utc).isoformat(),
                "has_preview": has_preview,
                "now": now,
                "id": file_row.id,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO files
                    (id, source_id, directory_id, relative_path, file_name, extension,
                     size_bytes, modified_at, discovered_at, last_scanned_at,
                     is_video_supported, converted_at, last_conversion_profile_id,
                     has_preview_asset, created_at, updated_at)
                VALUES
                    (:id, :sid, :dir_id, :rel, :file_name, :ext,
                     :size, :modified_at, :now, :now,
                     1, :now, :profile_id,
                     :has_preview, :now, :now)
                """
            ),
            {
                "id": new_file_id,
                "sid": file_row.source_id,
                "dir_id": file_row.directory_id,
                "rel": _rel(source_root, new_output_path),
                "file_name": new_output_path.name,
                "ext": params["container"],
                "size": new_stat.st_size,
                "modified_at": datetime.fromtimestamp(new_stat.st_mtime, tz=timezone.utc).isoformat(),
                "has_preview": has_preview,
                "now": now,
                "profile_id": profile_id,
            },
        )

    return {"output_ref": _rel(source_root, new_output_path)}


def _create_variant(engine, source_root: Path, file_row, profile: dict, overrides: dict) -> dict:
    old_path = source_root / file_row.relative_path
    directory = old_path.parent
    stem = old_path.stem
    params = _effective_params(profile, overrides)
    suffix = conversion.encode_variant_suffix(profile, overrides)

    temp_path = _temp_output_path(directory, stem, params["container"])
    _encode_and_validate(old_path, temp_path, params)

    variant_path = directory / f"{stem}.variant-{suffix}.{params['container']}"
    os.replace(temp_path, variant_path)

    stat = variant_path.stat()
    now = _now()
    new_file_id = str(uuid.uuid4())

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO files
                    (id, source_id, directory_id, relative_path, file_name, extension,
                     size_bytes, modified_at, discovered_at, last_scanned_at,
                     is_video_supported, has_preview_asset, created_at, updated_at)
                VALUES
                    (:id, :sid, :dir_id, :rel, :file_name, :ext,
                     :size, :modified_at, :now, :now,
                     1, :has_preview, :now, :now)
                """
            ),
            {
                "id": new_file_id,
                "sid": file_row.source_id,
                "dir_id": file_row.directory_id,
                "rel": _rel(source_root, variant_path),
                "file_name": variant_path.name,
                "ext": params["container"],
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "has_preview": _has_preview(directory, stem),
                "now": now,
            },
        )

    return {"output_ref": _rel(source_root, variant_path), "suffix": suffix}


def _convert_one_file(engine, source_root: Path, file_row, profile: dict, mode: str, profile_id: str) -> dict:
    old_path = source_root / file_row.relative_path
    if not old_path.exists():
        raise ConversionError("Source file no longer exists on disk.")

    if mode == "test":
        return _replace_test_mode(engine, source_root, file_row, profile, profile_id)
    return _replace_production(engine, source_root, file_row, profile, profile_id)


def run_convert_job(engine, job: dict) -> tuple[str, str]:
    params = job["parameters"] or {}
    profile = conversion_profiles.get_profile(engine, params.get("profile_id", ""))
    if profile is None:
        raise RuntimeError("Conversion profile not found.")

    mode = params.get("mode", "production")

    with engine.connect() as conn:
        source_row = conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()
    if source_row is None:
        raise RuntimeError("No active source is configured.")
    source_root = Path(source_row.root_path)

    if job["scope_type"] == "file":
        return _run_file_scope(engine, job, source_root, params, profile, mode)
    return _run_directory_scope(engine, job, source_root, params, profile, mode)


def _run_directory_scope(engine, job: dict, source_root: Path, params: dict, profile: dict, mode: str) -> tuple[str, str]:
    relative_path = params.get("path", "") or ""
    skip_processed = params.get("skip_processed", True)
    profile_id = profile["id"]

    with engine.connect() as conn:
        source_id = conn.execute(
            text("SELECT id FROM sources WHERE is_active = 1 LIMIT 1")
        ).fetchone().id

        clauses = ["source_id = :sid", "is_video_supported = 1"]
        query_params: dict = {"sid": source_id}
        if relative_path:
            clauses.append("(relative_path = :rel OR relative_path LIKE :prefix)")
            query_params["rel"] = relative_path
            query_params["prefix"] = f"{relative_path}/%"

        rows = conn.execute(
            text(f"SELECT * FROM files WHERE {' AND '.join(clauses)} ORDER BY relative_path"),
            query_params,
        ).all()

    candidates = [row for row in rows if not is_test_artifact(row.file_name)]

    processed = 0
    skipped = 0
    failed = 0
    total = len(candidates)

    for row in candidates:
        if service.is_cancel_requested(job["id"]):
            message = f"Cancelled after {processed} of {total} file(s)."
            service.log_event(engine, job["id"], None, "info", "job_cancel_honored", message)
            return "cancelled", message

        item_id = service.create_job_item(engine, job["id"], file_id=row.id, step_name="convert_file")

        if skip_processed and row.converted_at:
            service.skip_job_item(engine, item_id, "Already converted; skipped.")
            service.log_event(
                engine, job["id"], row.id, "debug", "job_item_skipped",
                f"Skipped {row.relative_path} (already converted).",
            )
            skipped += 1
            continue

        service.start_job_item(engine, item_id)
        try:
            outcome = _convert_one_file(engine, source_root, row, profile, mode, profile_id)
            service.complete_job_item(engine, item_id, output_ref=outcome["output_ref"], message="Converted.")
            service.log_event(
                engine, job["id"], row.id, "info", "job_item_completed", f"Converted {row.relative_path}"
            )
            processed += 1
        except Exception as exc:  # noqa: BLE001 - one file's failure must not abort the job
            failed += 1
            service.fail_job_item(engine, item_id, message=str(exc))
            service.log_event(
                engine, job["id"], row.id, "error", "job_item_failed",
                f"Failed to convert {row.relative_path}: {exc}",
            )

    summary = f"Converted {processed} of {total} file(s)"
    if skipped:
        summary += f", {skipped} skipped"
    if failed:
        summary += f", {failed} failed"
    summary += "."

    status = "failed" if failed and processed == 0 and total > 0 else "completed"
    return status, summary


def _run_file_scope(engine, job: dict, source_root: Path, params: dict, profile: dict, mode: str) -> tuple[str, str]:
    file_id = params.get("file_id")
    variants = params.get("variants")
    profile_id = profile["id"]

    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM files WHERE id = :id"), {"id": file_id}).fetchone()
    if row is None:
        raise RuntimeError("File not found.")

    if variants:
        return _run_variant_sweep(engine, job, source_root, row, profile, variants)

    skip_processed = params.get("skip_processed", True)
    item_id = service.create_job_item(engine, job["id"], file_id=row.id, step_name="convert_file")

    if skip_processed and row.converted_at:
        service.skip_job_item(engine, item_id, "Already converted; skipped.")
        service.log_event(engine, job["id"], row.id, "info", "job_item_skipped", "Already converted; skipped.")
        return "completed", "File already converted; skipped."

    service.start_job_item(engine, item_id)
    try:
        outcome = _convert_one_file(engine, source_root, row, profile, mode, profile_id)
        service.complete_job_item(engine, item_id, output_ref=outcome["output_ref"], message="Converted.")
        service.log_event(engine, job["id"], row.id, "info", "job_item_completed", f"Converted {row.relative_path}")
        return "completed", "File converted."
    except Exception as exc:  # noqa: BLE001 - failure is reported through the job, not raised further
        service.fail_job_item(engine, item_id, message=str(exc))
        service.log_event(
            engine, job["id"], row.id, "error", "job_item_failed", f"Failed to convert {row.relative_path}: {exc}"
        )
        return "failed", str(exc)


def _run_variant_sweep(engine, job: dict, source_root: Path, row, profile: dict, variants: list[dict]) -> tuple[str, str]:
    old_path = source_root / row.relative_path
    if not old_path.exists():
        raise RuntimeError("Source file no longer exists on disk.")

    processed = 0
    failed = 0
    total = len(variants)

    for overrides in variants:
        if service.is_cancel_requested(job["id"]):
            message = f"Cancelled after {processed} of {total} variant(s)."
            service.log_event(engine, job["id"], None, "info", "job_cancel_honored", message)
            return "cancelled", message

        suffix = conversion.encode_variant_suffix(profile, overrides)
        item_id = service.create_job_item(
            engine, job["id"], file_id=row.id, item_key=suffix, step_name="convert_variant"
        )
        service.start_job_item(engine, item_id)
        try:
            outcome = _create_variant(engine, source_root, row, profile, overrides)
            service.complete_job_item(engine, item_id, output_ref=outcome["output_ref"], message="Variant produced.")
            service.log_event(
                engine, job["id"], row.id, "info", "job_item_completed", f"Variant {suffix} produced."
            )
            processed += 1
        except Exception as exc:  # noqa: BLE001 - one variant's failure must not abort the sweep
            failed += 1
            service.fail_job_item(engine, item_id, message=str(exc))
            service.log_event(
                engine, job["id"], row.id, "error", "job_item_failed", f"Variant {suffix} failed: {exc}"
            )

    summary = f"Produced {processed} of {total} variant(s)"
    if failed:
        summary += f", {failed} failed"
    summary += "."

    status = "failed" if failed and processed == 0 else "completed"
    return status, summary
