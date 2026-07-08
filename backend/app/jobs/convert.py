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

All file access goes through `app.sources.SourceAccess` (Stage 7) instead of
raw `pathlib`: for a `local` source this is a zero-cost passthrough (same
behavior as before Stage 7); for an `smb` source, the file being converted is
downloaded once to a throwaway local temp directory, encoded there exactly as
before, and the result is uploaded back — renames/removals of files that were
never re-encoded (marking an original, deleting a superseded original) happen
directly on the remote source without re-uploading their bytes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app import conversion, conversion_profiles
from app.jobs import service
from app.media import is_test_artifact, sibling_relative_path
from app.sources import SourceAccess, get_source_access


class ConversionError(Exception):
    """Raised when an encode or its validation fails; the source is
    guaranteed untouched whenever this is raised."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _has_preview(access: SourceAccess, rel_path: str, stem: str) -> bool:
    return access.exists(sibling_relative_path(rel_path, f"{stem}.jpg"))


def _replace_production(engine, access: SourceAccess, old_path: Path, file_row, profile: dict, profile_id: str) -> dict:
    directory = old_path.parent
    stem = old_path.stem
    params = _effective_params(profile, None)

    temp_path = _temp_output_path(directory, stem, params["container"])
    _encode_and_validate(old_path, temp_path, params)

    final_name = f"{stem}.{params['container']}"
    final_rel = sibling_relative_path(file_row.relative_path, final_name)
    access.commit_new_file(temp_path, final_rel)
    if final_rel != file_row.relative_path:
        access.remote_remove(file_row.relative_path)

    final_stat = access.stat_rel(final_rel)
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
                "rel": final_rel,
                "file_name": final_name,
                "ext": params["container"],
                "size": final_stat.size,
                "modified_at": final_stat.modified_at,
                "has_preview": _has_preview(access, file_row.relative_path, stem),
                "now": now,
                "profile_id": profile_id,
                "id": file_row.id,
            },
        )

    return {"output_ref": final_rel}


def _replace_test_mode(engine, access: SourceAccess, old_path: Path, file_row, profile: dict, profile_id: str) -> dict:
    directory = old_path.parent
    stem = old_path.stem
    original_ext = file_row.extension
    params = _effective_params(profile, None)

    temp_path = _temp_output_path(directory, stem, params["container"])
    _encode_and_validate(old_path, temp_path, params)

    # Original is always renamed, even without a name collision, so preserved
    # originals stay uniformly recognizable (Specification §8.2). Renaming
    # happens directly on the source: the original's bytes never changed, so
    # there is nothing to re-upload for an SMB source.
    original_marked_rel = sibling_relative_path(file_row.relative_path, f"{stem}.original.{original_ext}")
    access.remote_rename(file_row.relative_path, original_marked_rel)
    new_output_name = f"{stem}.{params['container']}"
    new_output_rel = sibling_relative_path(file_row.relative_path, new_output_name)
    access.commit_new_file(temp_path, new_output_rel)

    now = _now()
    has_preview = _has_preview(access, file_row.relative_path, stem)
    orig_stat = access.stat_rel(original_marked_rel)
    new_stat = access.stat_rel(new_output_rel)
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
                "rel": original_marked_rel,
                "file_name": f"{stem}.original.{original_ext}",
                "ext": original_ext,
                "size": orig_stat.size,
                "modified_at": orig_stat.modified_at,
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
                "rel": new_output_rel,
                "file_name": new_output_name,
                "ext": params["container"],
                "size": new_stat.size,
                "modified_at": new_stat.modified_at,
                "has_preview": has_preview,
                "now": now,
                "profile_id": profile_id,
            },
        )

    return {"output_ref": new_output_rel}


def _create_variant(engine, access: SourceAccess, old_path: Path, file_row, profile: dict, overrides: dict) -> dict:
    directory = old_path.parent
    stem = old_path.stem
    params = _effective_params(profile, overrides)
    suffix = conversion.encode_variant_suffix(profile, overrides)

    temp_path = _temp_output_path(directory, stem, params["container"])
    _encode_and_validate(old_path, temp_path, params)

    variant_name = f"{stem}.variant-{suffix}.{params['container']}"
    variant_rel = sibling_relative_path(file_row.relative_path, variant_name)
    access.commit_new_file(temp_path, variant_rel)

    stat = access.stat_rel(variant_rel)
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
                "rel": variant_rel,
                "file_name": variant_name,
                "ext": params["container"],
                "size": stat.size,
                "modified_at": stat.modified_at,
                "has_preview": _has_preview(access, file_row.relative_path, stem),
                "now": now,
            },
        )

    return {"output_ref": variant_rel, "suffix": suffix}


def _convert_one_file(engine, access: SourceAccess, file_row, profile: dict, mode: str, profile_id: str) -> dict:
    if not access.exists(file_row.relative_path):
        raise ConversionError("Source file no longer exists on the source.")

    with access.local_copy(file_row.relative_path) as old_path:
        if mode == "test":
            return _replace_test_mode(engine, access, old_path, file_row, profile, profile_id)
        return _replace_production(engine, access, old_path, file_row, profile, profile_id)


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
    access = get_source_access(source_row)

    if job["scope_type"] == "file":
        return _run_file_scope(engine, job, access, params, profile, mode)
    return _run_directory_scope(engine, job, access, params, profile, mode)


def _run_directory_scope(engine, job: dict, access: SourceAccess, params: dict, profile: dict, mode: str) -> tuple[str, str]:
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
    service.set_job_total_items(engine, job["id"], total)

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
            outcome = _convert_one_file(engine, access, row, profile, mode, profile_id)
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


def _run_file_scope(engine, job: dict, access: SourceAccess, params: dict, profile: dict, mode: str) -> tuple[str, str]:
    file_id = params.get("file_id")
    variants = params.get("variants")
    profile_id = profile["id"]

    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM files WHERE id = :id"), {"id": file_id}).fetchone()
    if row is None:
        raise RuntimeError("File not found.")

    if variants:
        return _run_variant_sweep(engine, job, access, row, profile, variants)

    skip_processed = params.get("skip_processed", True)
    item_id = service.create_job_item(engine, job["id"], file_id=row.id, step_name="convert_file")

    if skip_processed and row.converted_at:
        service.skip_job_item(engine, item_id, "Already converted; skipped.")
        service.log_event(engine, job["id"], row.id, "info", "job_item_skipped", "Already converted; skipped.")
        return "completed", "File already converted; skipped."

    service.start_job_item(engine, item_id)
    try:
        outcome = _convert_one_file(engine, access, row, profile, mode, profile_id)
        service.complete_job_item(engine, item_id, output_ref=outcome["output_ref"], message="Converted.")
        service.log_event(engine, job["id"], row.id, "info", "job_item_completed", f"Converted {row.relative_path}")
        return "completed", "File converted."
    except Exception as exc:  # noqa: BLE001 - failure is reported through the job, not raised further
        service.fail_job_item(engine, item_id, message=str(exc))
        service.log_event(
            engine, job["id"], row.id, "error", "job_item_failed", f"Failed to convert {row.relative_path}: {exc}"
        )
        return "failed", str(exc)


def _run_variant_sweep(engine, job: dict, access: SourceAccess, row, profile: dict, variants: list[dict]) -> tuple[str, str]:
    if not access.exists(row.relative_path):
        raise RuntimeError("Source file no longer exists on the source.")

    processed = 0
    failed = 0
    total = len(variants)
    service.set_job_total_items(engine, job["id"], total)

    with access.local_copy(row.relative_path) as old_path:
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
                outcome = _create_variant(engine, access, old_path, row, profile, overrides)
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
