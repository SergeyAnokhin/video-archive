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

import os
import shlex
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app import (
    conversion,
    conversion_profiles,
    conversion_settings,
    hardware_accel,
    hardware_decode,
    performance_settings,
    tags,
)
from app.jobs import service
from app.media import is_test_artifact, sibling_relative_path
from app.sources import SourceAccess, get_source_access


class ConversionError(Exception):
    """Raised when an encode or its validation fails; the source is
    guaranteed untouched whenever this is raised."""


class ConversionSkipped(Exception):
    """Raised when the encode succeeded and validated but should not replace
    the source (e.g. the output ended up larger than the source); the source
    is guaranteed untouched whenever this is raised."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_size(num_bytes: int) -> str:
    """Human-readable size (user request -- a raw byte count "is very hard
    to read" in the job log); mirrors the frontend's own `formatSize()`
    (`frontend/src/utils/format.ts`) unit-for-unit so the two stay visually
    consistent."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    units = ["KB", "MB", "GB", "TB"]
    value = num_bytes / 1024
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    return f"{value:.1f} {units[unit_index]}"


def _format_resolution(info: dict | None) -> str:
    if not info or not info.get("width") or not info.get("height"):
        return "unknown resolution"
    return f"{info['width']}x{info['height']}"


def _format_command_for_log(args: list[str]) -> str:
    """Windows and POSIX shells quote arguments differently -- using the
    wrong one means a command copied out of the job log can't actually be
    pasted into a terminal to reproduce it (user report: filenames with an
    apostrophe came out as `'s'"'"'` in the log, which is `shlex.join`'s
    POSIX quoting and isn't valid syntax in cmd.exe, forcing a hand-rewrite
    to repro locally). `subprocess.list2cmdline` is the same quoting `Popen`
    itself uses to build the real Windows command line, so it always matches
    what actually ran there."""
    if os.name == "nt":
        return subprocess.list2cmdline(args)
    return shlex.join(args)


def _effective_params(profile: dict, overrides: dict | None) -> dict:
    overrides = overrides or {}
    return {
        "video_codec": overrides.get("video_codec", profile["video_codec"]),
        "container": profile["container"],
        "crf": overrides.get("crf", profile["crf"]),
        "drop_audio": profile["drop_audio"],
        "max_dimension": overrides.get("max_dimension", profile.get("max_dimension")),
        "extra_encoder_args": profile.get("extra_encoder_args"),
        "hardware_accel": profile.get("hardware_accel", "off"),
    }


def _temp_output_path(directory: Path, stem: str, container: str) -> Path:
    return directory / f".{stem}.convert-{uuid.uuid4().hex[:8]}.{container}"


def _probe_params(probe: dict | None) -> dict:
    """Maps a `conversion.probe_media()` dict onto the `files` cache
    columns' bind params, for the `UPDATE`/`INSERT` statements below."""
    probe = probe or {}
    return {
        "width": probe.get("width"),
        "height": probe.get("height"),
        "video_codec": probe.get("video_codec_name"),
        "format_name": probe.get("format_name"),
        "bit_rate": probe.get("bit_rate"),
    }


def _encode_and_validate(
    engine, job_id: str, file_id: str, item_id: str, source_path: Path, temp_path: Path, params: dict,
    *, min_size_reduction_percent: float | None = None,
) -> dict:
    """Returns `{"duration", "source_size", "output_size", "source_probe",
    "output_probe"}`: the source's duration in seconds (from the ffprobe call
    this already performs for max-dimension resolution), so callers can
    persist it without a second probe (re-encoding does not change a video's
    duration), plus the before/after byte sizes (user request: show original
    vs. resulting size in the job log) so callers don't need a third
    `stat()` call of their own. `source_probe`/`output_probe` are the full
    `conversion.probe_media()` dicts for the source and the encoded output,
    already computed here for other purposes (max-dimension decision, the
    result log line) -- callers use them to cache technical metadata
    (resolution/codec/container/bitrate) on the `files` row(s) they write,
    at no extra probe cost.

    Logs a `job_item_progress` event (post-V1, user request) around each
    stage -- probing, the ffmpeg encode itself, and output validation -- so
    a slow conversion's time can be attributed to a specific stage instead
    of sitting silent between "started" and "completed". Also logs the exact
    ffmpeg command line (user request: let the user copy it into a terminal
    to reproduce/inspect the encode themselves).

    `min_size_reduction_percent` (user report): when set, an encode that
    validates fine but doesn't shrink the source by at least this percentage
    (0 = "just don't come out bigger") raises `ConversionSkipped` instead of
    being handed back to the caller -- production/test-mode replace pass
    `app/conversion_settings.py`'s configured threshold so a conversion that
    wasn't actually worth it never lands, while a tuning-sweep variant
    (comparison output, never replaces the source) leaves it unset."""

    def progress(message: str) -> None:
        service.log_event(engine, job_id, file_id, "info", "job_item_progress", message)

    t0 = time.monotonic()
    source_info = conversion.probe_media(source_path)
    source_size = source_path.stat().st_size
    max_dim = conversion.effective_max_dimension(source_info, params["max_dimension"])

    # Upfront availability gate (user's requested hardware_accel may not have
    # a mapping for this codec, or the cached startup probe -- app/hardware_accel.py
    # -- may have found it unusable on this host): resolved before the first
    # ffmpeg command is even built, so a doomed hw attempt never runs.
    requested_hw = params["hardware_accel"]
    effective_hw = requested_hw
    if requested_hw and requested_hw != "off":
        if not conversion.has_hw_mapping(params["video_codec"], requested_hw):
            progress(f"No {requested_hw} encoder for codec {params['video_codec']}; using software encoder.")
            effective_hw = "off"
        elif not getattr(hardware_accel.check_hardware_accel(), requested_hw, False):
            progress(f"{requested_hw} hardware encoding unavailable on this host; using software encoder.")
            effective_hw = "off"

    # Whether the first attempt will also hardware-decode the source, on top
    # of (or independent of) `effective_hw`'s encoder decision -- decode is
    # attempted automatically whenever available (`conversion.build_ffmpeg_
    # command()`'s `decode_hw=True` default), so a codec/container hw decode
    # can't handle (real archives have plenty of non-h264 sources; the probe
    # that determined `check_hardware_decode()` only verified a synthetic
    # h264 clip) is just as much a reason for the runtime retry below as an
    # encoder failure is.
    hw_decode_backend = hardware_decode.decode_backend()
    decode_backend_used = hw_decode_backend is not None

    args = conversion.build_ffmpeg_command(
        source_path,
        temp_path,
        video_codec=params["video_codec"],
        crf=params["crf"],
        drop_audio=params["drop_audio"],
        max_dimension=max_dim,
        extra_encoder_args=params["extra_encoder_args"],
        hardware_accel=effective_hw,
    )
    progress(f"Probed source in {time.monotonic() - t0:.2f}s")
    # Source resolution/size up front (user request): so the log identifies
    # what file was picked up and its starting parameters before the encode
    # even runs, not just the end result.
    progress(f"Source: {_format_resolution(source_info)}, {_format_size(source_size)}")
    progress(f"ffmpeg command: {_format_command_for_log(args)}")

    # Live within-file progress (post-V1, user request): throttled to at
    # most once a second (or a >=1% jump) so a fast-moving encode doesn't
    # hammer the job_items row with writes -- the Jobs modal polls it every
    # 1.5s anyway (`JobsContext.tsx`), so anything finer would be wasted.
    last_reported = {"pct": -1.0, "at": 0.0}

    def on_progress(pct: float) -> None:
        now = time.monotonic()
        if pct - last_reported["pct"] < 1.0 and now - last_reported["at"] < 1.0 and pct < 100.0:
            return
        last_reported["pct"] = pct
        last_reported["at"] = now
        service.update_job_item_progress(engine, item_id, pct)

    def should_stop() -> bool:
        return service.check_stop_requested(job_id) is not None

    # Once per attempt (post-V1, user request "make it visible when hardware
    # acceleration is actually used"): `effective_hw` is the ENCODER,
    # `hw_decode_backend` the (independent) decode side -- either, both, or
    # neither may be active.
    if effective_hw != "off" or decode_backend_used:
        hw_parts = []
        if effective_hw != "off":
            hw_parts.append(f"encode={effective_hw.upper()}")
        if decode_backend_used:
            hw_parts.append(f"decode={hw_decode_backend.upper()}")
        progress(f"🚀 Hardware acceleration active ({', '.join(hw_parts)})")

    t0 = time.monotonic()
    progress(f"Encoding with ffmpeg (codec={params['video_codec']}, crf={params['crf']})")
    duration = source_info.get("duration") if source_info else None
    timeout = conversion_settings.get_settings(engine)["ffmpeg_timeout_seconds"]
    # Tripped only if this attempt's hardware decode crashes ffmpeg outright
    # (vs. failing cleanly) -- flagged via a mutable cell instead of reading
    # `hardware_decode.decode_backend()` again after the fact, since
    # `mark_runtime_broken()` below would make that immediately report
    # `None` regardless of what actually crashed just now.
    crash_detected = {"value": False}

    def _guard_decode_crash(returncode: int | None) -> None:
        if decode_backend_used and conversion.is_crash_exit_code(returncode):
            crash_detected["value"] = True
            hardware_decode.mark_runtime_broken()

    ok, error = conversion.run_ffmpeg(
        args, timeout=timeout, duration=duration, on_progress=on_progress, should_stop=should_stop,
        on_exit_code=_guard_decode_crash,
    )
    # Runtime fallback: a hardware encode and/or hardware decode that fails
    # at ffmpeg-run time (as opposed to being pre-emptively ruled out above)
    # gets exactly one retry fully in software -- the original error is
    # always logged in full first, so a genuine non-hardware ffmpeg failure
    # is never hidden, only given a second, unambiguous chance to succeed or
    # fail on its own terms.
    if not ok and (effective_hw != "off" or decode_backend_used):
        reason = (
            f"{effective_hw} hardware encode failed ({error})"
            if effective_hw != "off"
            else f"hardware decode failed ({error})"
        )
        note = " Hardware decode crashed ffmpeg -- disabled for the rest of this run." if crash_detected["value"] else ""
        service.log_event(
            engine, job_id, file_id, "warning", "job_item_progress",
            f"⚠️ {reason}; retrying this file with the software encoder.{note}",
        )
        if temp_path.exists():
            temp_path.unlink()
        args = conversion.build_ffmpeg_command(
            source_path,
            temp_path,
            video_codec=params["video_codec"],
            crf=params["crf"],
            drop_audio=params["drop_audio"],
            max_dimension=max_dim,
            extra_encoder_args=params["extra_encoder_args"],
            hardware_accel="off",
            decode_hw=False,
        )
        progress(f"ffmpeg command (software fallback): {_format_command_for_log(args)}")
        ok, error = conversion.run_ffmpeg(
            args, timeout=timeout, duration=duration, on_progress=on_progress, should_stop=should_stop
        )
    if not ok:
        if temp_path.exists():
            temp_path.unlink()
        # Elapsed time included even on failure (user report: a failed
        # conversion's log gave no sense of how long it ran before dying --
        # the success-only "Encoded in Xs" line below never fires here).
        raise ConversionError(f"ffmpeg failed after {time.monotonic() - t0:.2f}s: {error}")
    progress(f"Encoded in {time.monotonic() - t0:.2f}s")

    t0 = time.monotonic()
    valid, reason = conversion.validate_converted_output(
        temp_path, video_codec=params["video_codec"], container=params["container"]
    )
    if not valid:
        # Validation failed: discard the temp output only. The source has
        # not been touched yet in either mode (Specification §8.1 rule 4).
        temp_path.unlink()
        raise ConversionError(f"Validation failed: {reason}")
    progress(f"Validated output in {time.monotonic() - t0:.2f}s")

    output_size = temp_path.stat().st_size
    output_info = conversion.probe_media(temp_path)
    # Resulting resolution/size (user request): paired with the "Source: ..."
    # line above so the log shows what was taken and what it became without
    # having to cross-reference the ffmpeg command line.
    progress(
        f"Result: {_format_resolution(output_info)}, "
        f"{_format_size(source_size)} -> {_format_size(output_size)} "
        f"({(output_size - source_size) / source_size * 100 if source_size else 0.0:+.1f}%)"
    )
    if min_size_reduction_percent is not None:
        reduction_percent = (source_size - output_size) / source_size * 100 if source_size else 0.0
        if reduction_percent < min_size_reduction_percent:
            temp_path.unlink()
            message = (
                f"Converted output only reduced size by {reduction_percent:.1f}% "
                f"(needs at least {min_size_reduction_percent}%); keeping the original. "
                f"({_format_size(output_size)} vs {_format_size(source_size)})"
            )
            service.log_event(engine, job_id, file_id, "warning", "job_item_progress", message)
            raise ConversionSkipped(message)

    return {
        "duration": duration,
        "source_size": source_size,
        "output_size": output_size,
        "source_probe": source_info,
        "output_probe": output_info,
    }


def _has_preview(access: SourceAccess, rel_path: str, stem: str) -> bool:
    return access.exists(sibling_relative_path(rel_path, f"{stem}.jpg"))


def _replace_production(
    engine, job_id: str, item_id: str, access: SourceAccess, old_path: Path, file_row, profile: dict,
    profile_id: str, *, min_size_reduction_percent: float,
) -> dict:
    directory = old_path.parent
    stem = old_path.stem
    params = _effective_params(profile, None)

    temp_path = _temp_output_path(directory, stem, params["container"])
    encode_result = _encode_and_validate(
        engine, job_id, file_row.id, item_id, old_path, temp_path, params,
        min_size_reduction_percent=min_size_reduction_percent,
    )
    duration_seconds = encode_result["duration"]

    final_name = f"{stem}.{params['container']}"
    final_rel = sibling_relative_path(file_row.relative_path, final_name)
    access.commit_new_file(temp_path, final_rel)
    if final_rel != file_row.relative_path:
        access.remote_remove(file_row.relative_path)
    service.log_event(
        engine, job_id, file_row.id, "info", "job_item_progress", f"Replaced source with {final_name}"
    )

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
                    last_conversion_profile_id = :profile_id,
                    duration_seconds = COALESCE(:duration, duration_seconds),
                    width = :width, height = :height, video_codec = :video_codec,
                    format_name = :format_name, bit_rate = :bit_rate, media_probed_at = :now,
                    last_scanned_at = :now, updated_at = :now
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
                "duration": duration_seconds,
                "id": file_row.id,
                **_probe_params(encode_result["output_probe"]),
            },
        )

    return {
        "output_ref": final_rel,
        "source_size": encode_result["source_size"],
        "output_size": encode_result["output_size"],
    }


def _replace_test_mode(
    engine, job_id: str, item_id: str, access: SourceAccess, old_path: Path, file_row, profile: dict,
    profile_id: str, *, min_size_reduction_percent: float,
) -> dict:
    directory = old_path.parent
    stem = old_path.stem
    original_ext = file_row.extension
    params = _effective_params(profile, None)

    temp_path = _temp_output_path(directory, stem, params["container"])
    encode_result = _encode_and_validate(
        engine, job_id, file_row.id, item_id, old_path, temp_path, params,
        min_size_reduction_percent=min_size_reduction_percent,
    )
    duration_seconds = encode_result["duration"]

    # Original is always renamed, even without a name collision, so preserved
    # originals stay uniformly recognizable (Specification §8.2). Renaming
    # happens directly on the source: the original's bytes never changed, so
    # there is nothing to re-upload for an SMB source.
    original_marked_rel = sibling_relative_path(file_row.relative_path, f"{stem}.original.{original_ext}")
    access.remote_rename(file_row.relative_path, original_marked_rel)
    new_output_name = f"{stem}.{params['container']}"
    new_output_rel = sibling_relative_path(file_row.relative_path, new_output_name)
    access.commit_new_file(temp_path, new_output_rel)
    service.log_event(
        engine, job_id, file_row.id, "info", "job_item_progress",
        f"Kept original as {stem}.original.{original_ext}, wrote {new_output_name}",
    )

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
                    has_preview_asset = :has_preview,
                    duration_seconds = COALESCE(:duration, duration_seconds),
                    width = :width, height = :height, video_codec = :video_codec,
                    format_name = :format_name, bit_rate = :bit_rate, media_probed_at = :now,
                    last_scanned_at = :now, updated_at = :now
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
                "duration": duration_seconds,
                "now": now,
                "id": file_row.id,
                # Only renamed, bytes unchanged -- the source probe already
                # taken for this same encode is still accurate for it.
                **_probe_params(encode_result["source_probe"]),
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO files
                    (id, source_id, directory_id, relative_path, file_name, extension,
                     size_bytes, modified_at, discovered_at, last_scanned_at,
                     is_video_supported, converted_at, last_conversion_profile_id,
                     has_preview_asset, duration_seconds,
                     width, height, video_codec, format_name, bit_rate, media_probed_at,
                     created_at, updated_at)
                VALUES
                    (:id, :sid, :dir_id, :rel, :file_name, :ext,
                     :size, :modified_at, :now, :now,
                     1, :now, :profile_id,
                     :has_preview, :duration,
                     :width, :height, :video_codec, :format_name, :bit_rate, :now,
                     :now, :now)
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
                "duration": duration_seconds,
                "has_preview": has_preview,
                "now": now,
                "profile_id": profile_id,
                **_probe_params(encode_result["output_probe"]),
            },
        )

    return {
        "output_ref": new_output_rel,
        "source_size": encode_result["source_size"],
        "output_size": encode_result["output_size"],
    }


def _create_variant(
    engine, job_id: str, item_id: str, access: SourceAccess, old_path: Path, file_row, profile: dict,
    overrides: dict,
) -> dict:
    directory = old_path.parent
    stem = old_path.stem
    params = _effective_params(profile, overrides)
    suffix = conversion.encode_variant_suffix(profile, overrides)

    temp_path = _temp_output_path(directory, stem, params["container"])
    encode_result = _encode_and_validate(engine, job_id, file_row.id, item_id, old_path, temp_path, params)
    duration_seconds = encode_result["duration"]

    variant_name = f"{stem}.variant-{suffix}.{params['container']}"
    variant_rel = sibling_relative_path(file_row.relative_path, variant_name)
    access.commit_new_file(temp_path, variant_rel)

    stat = access.stat_rel(variant_rel)
    now = _now()
    has_preview = _has_preview(access, file_row.relative_path, stem)

    with engine.begin() as conn:
        # A variant with this exact suffix may already have a `files` row --
        # e.g. re-running a tuning sweep with a combination (dimension+crf)
        # that an earlier sweep already produced for this source file.
        # `commit_new_file()` above already overwrote the file on disk
        # unconditionally, so the DB side must follow the same
        # overwrite-in-place semantics (UPDATE) instead of blindly INSERTing
        # a second row for the same `(source_id, relative_path)`, which
        # violates that pair's UNIQUE constraint.
        existing = conn.execute(
            text("SELECT id FROM files WHERE source_id = :sid AND relative_path = :rel"),
            {"sid": file_row.source_id, "rel": variant_rel},
        ).fetchone()
        variant_id = existing.id if existing is not None else str(uuid.uuid4())
        if existing is not None:
            conn.execute(
                text(
                    """
                    UPDATE files
                    SET size_bytes = :size, modified_at = :modified_at, last_scanned_at = :now,
                        is_video_supported = 1, has_preview_asset = :has_preview,
                        duration_seconds = :duration,
                        width = :width, height = :height, video_codec = :video_codec,
                        format_name = :format_name, bit_rate = :bit_rate, media_probed_at = :now,
                        updated_at = :now
                    WHERE id = :id
                    """
                ),
                {
                    "id": existing.id,
                    "size": stat.size,
                    "modified_at": stat.modified_at,
                    "duration": duration_seconds,
                    "has_preview": has_preview,
                    "now": now,
                    **_probe_params(encode_result["output_probe"]),
                },
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO files
                        (id, source_id, directory_id, relative_path, file_name, extension,
                         size_bytes, modified_at, discovered_at, last_scanned_at,
                         is_video_supported, has_preview_asset, duration_seconds,
                         width, height, video_codec, format_name, bit_rate, media_probed_at,
                         created_at, updated_at)
                    VALUES
                        (:id, :sid, :dir_id, :rel, :file_name, :ext,
                         :size, :modified_at, :now, :now,
                         1, :has_preview, :duration,
                         :width, :height, :video_codec, :format_name, :bit_rate, :now,
                         :now, :now)
                    """
                ),
                {
                    "id": variant_id,
                    "sid": file_row.source_id,
                    "dir_id": file_row.directory_id,
                    "rel": variant_rel,
                    "file_name": variant_name,
                    "ext": params["container"],
                    "size": stat.size,
                    "modified_at": stat.modified_at,
                    "duration": duration_seconds,
                    "has_preview": has_preview,
                    "now": now,
                    **_probe_params(encode_result["output_probe"]),
                },
            )

    # Every tuning-produced file carries its effective encode parameters as
    # ordinary removable tags (user request): codec and CRF always, the
    # dimension cap when the encode had one -- so the settings behind a
    # variant are visible at a glance in the library/info panel.
    tag_names = [params["video_codec"].upper()]
    if params["max_dimension"]:
        tag_names.append(f"{params['max_dimension']}px")
    tag_names.append(f"CRF {params['crf']}")
    try:
        tags.assign_tuning_parameter_tags(engine, variant_id, tag_names)
    except Exception as exc:  # noqa: BLE001 - parameter tags are best-effort metadata; the encode itself succeeded
        service.log_event(
            engine, job_id, file_row.id, "warning", "job_item_progress",
            f"Variant {variant_name} produced, but tagging its parameters failed: {exc}",
        )

    return {"output_ref": variant_rel, "suffix": suffix}


def _convert_one_file(
    engine, job_id: str, item_id: str, access: SourceAccess, file_row, profile: dict, mode: str, profile_id: str,
    *, min_size_reduction_percent: float,
) -> dict:
    if not access.exists(file_row.relative_path):
        raise ConversionError("Source file no longer exists on the source.")

    with access.local_copy(file_row.relative_path) as old_path:
        if mode == "test":
            return _replace_test_mode(
                engine, job_id, item_id, access, old_path, file_row, profile, profile_id,
                min_size_reduction_percent=min_size_reduction_percent,
            )
        return _replace_production(
            engine, job_id, item_id, access, old_path, file_row, profile, profile_id,
            min_size_reduction_percent=min_size_reduction_percent,
        )


def run_convert_job(engine, job: dict) -> tuple[str, str]:
    # Known limitation, not addressed by this pass: `worker_count` below can
    # run several ffmpeg processes concurrently, but a single Intel iGPU only
    # supports a handful of simultaneous QSV/VAAPI encode sessions -- a
    # profile with hardware_accel set and a high parallel_workers count may
    # see some concurrent files' hardware encodes fail and fall back to
    # software (see the runtime retry in _encode_and_validate) rather than
    # all running in hardware at once.
    params = job["parameters"] or {}
    profile = conversion_profiles.get_profile(engine, params.get("profile_id", ""))
    if profile is None:
        raise RuntimeError("Conversion profile not found.")

    mode = params.get("mode", "production")
    worker_count = max(1, performance_settings.get_settings(engine)["parallel_workers"])
    min_size_reduction_percent = conversion_settings.get_settings(engine)["min_size_reduction_percent"]

    with engine.connect() as conn:
        source_row = conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()
    if source_row is None:
        raise RuntimeError("No active source is configured.")
    access = get_source_access(source_row)

    if job["scope_type"] == "file":
        return _run_file_scope(engine, job, access, params, profile, mode, worker_count, min_size_reduction_percent)
    return _run_directory_scope(engine, job, access, params, profile, mode, worker_count, min_size_reduction_percent)


def _process_convert_file(
    engine, job_id: str, access: SourceAccess, row, profile: dict, mode: str, profile_id: str,
    min_size_reduction_percent: float,
) -> tuple[str, int | None, int | None]:
    """One directory-scope file, run from inside a batch's thread pool.
    Returns `(status, source_size, output_size)` -- status is
    "completed"/"skipped"/"failed"; failures and skips go through the normal
    job-item/event mechanism (thread-safe, see `app/jobs/service.py`) rather
    than being raised, so one file's outcome can't abort a whole in-flight
    batch. `item_key` (user request) lets the Jobs modal show this file's
    path instead of a raw file id for the currently-running item."""
    item_id = service.create_job_item(
        engine, job_id, file_id=row.id, item_key=row.relative_path, step_name="convert_file"
    )
    service.start_job_item(engine, item_id)
    service.log_event(engine, job_id, row.id, "info", "job_item_started", f"Converting {row.relative_path}")
    try:
        outcome = _convert_one_file(
            engine, job_id, item_id, access, row, profile, mode, profile_id,
            min_size_reduction_percent=min_size_reduction_percent,
        )
        service.complete_job_item(engine, item_id, output_ref=outcome["output_ref"], message="Converted.")
        service.log_event(engine, job_id, row.id, "info", "job_item_completed", f"Converted {row.relative_path}")
        return "completed", outcome.get("source_size"), outcome.get("output_size")
    except ConversionSkipped as exc:
        service.skip_job_item(engine, item_id, message=str(exc))
        service.log_event(
            engine, job_id, row.id, "info", "job_item_skipped", f"Skipped {row.relative_path}: {exc}"
        )
        return "skipped", None, None
    except Exception as exc:  # noqa: BLE001 - one file's failure must not abort the job
        service.fail_job_item(engine, item_id, message=str(exc))
        service.log_event(
            engine, job_id, row.id, "error", "job_item_failed", f"Failed to convert {row.relative_path}: {exc}"
        )
        return "failed", None, None


def _run_directory_scope(
    engine, job: dict, access: SourceAccess, params: dict, profile: dict, mode: str, worker_count: int,
    min_size_reduction_percent: float,
) -> tuple[str, str]:
    relative_path = params.get("path", "") or ""
    skip_processed = params.get("skip_processed", True)
    profile_id = profile["id"]

    service.log_event(
        engine, job["id"], None, "info", "job_item_progress",
        f"Directory: {relative_path or '(whole source)'}",
    )

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

    skipped = 0
    total_source_bytes = 0
    total_output_bytes = 0
    total = len(candidates)
    service.set_job_total_items(engine, job["id"], total)

    # Independent files are converted `worker_count` at a time, submitting
    # the next file as soon as a slot frees up rather than waiting for a
    # whole batch to finish first (post-V1, user request -- see
    # `service.run_sliding_window()`'s docstring for why). `next_item()`
    # also performs the skip-processed check inline: it runs on the calling
    # thread, so a skipped file never consumes a worker slot.
    candidates_iter = iter(candidates)

    def next_item():
        nonlocal skipped
        for row in candidates_iter:
            if skip_processed and row.converted_at:
                item_id = service.create_job_item(
                    engine, job["id"], file_id=row.id, item_key=row.relative_path, step_name="convert_file"
                )
                service.skip_job_item(engine, item_id, "Already converted; skipped.")
                service.log_event(
                    engine, job["id"], row.id, "debug", "job_item_skipped",
                    f"Skipped {row.relative_path} (already converted).",
                )
                skipped += 1
                continue
            return row
        return None

    results, stop = service.run_sliding_window(
        job["id"],
        worker_count,
        next_item,
        lambda row: _process_convert_file(
            engine, job["id"], access, row, profile, mode, profile_id, min_size_reduction_percent
        ),
    )

    processed = 0
    failed = 0
    for status, source_size, output_size in results:
        if status == "completed":
            processed += 1
            if source_size is not None and output_size is not None:
                total_source_bytes += source_size
                total_output_bytes += output_size
        elif status == "skipped":
            skipped += 1
        else:
            failed += 1

    if stop:
        verb = "Cancelled" if stop == "cancel" else "Paused"
        status = "cancelled" if stop == "cancel" else "paused"
        message = f"{verb} after {processed} of {total} file(s)."
        service.log_event(engine, job["id"], None, "info", f"job_{stop}_honored", message)
        return status, message

    summary = f"Converted {processed} of {total} file(s)"
    if skipped:
        summary += f", {skipped} skipped"
    if failed:
        summary += f", {failed} failed"
    summary += "."
    if total_source_bytes:
        pct = (total_output_bytes - total_source_bytes) / total_source_bytes * 100
        summary += f" Total size: {_format_size(total_source_bytes)} -> {_format_size(total_output_bytes)} ({pct:+.1f}%)."

    status = "failed" if failed and processed == 0 and total > 0 else "completed"
    return status, summary


def _run_file_scope(
    engine, job: dict, access: SourceAccess, params: dict, profile: dict, mode: str, worker_count: int,
    min_size_reduction_percent: float,
) -> tuple[str, str]:
    file_id = params.get("file_id")
    variants = params.get("variants")
    profile_id = profile["id"]

    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM files WHERE id = :id"), {"id": file_id}).fetchone()
    if row is None:
        raise RuntimeError("File not found.")

    service.log_event(engine, job["id"], None, "info", "job_item_progress", f"File: {row.relative_path}")

    if variants:
        return _run_variant_sweep(engine, job, access, row, profile, variants, worker_count)

    skip_processed = params.get("skip_processed", True)
    item_id = service.create_job_item(
        engine, job["id"], file_id=row.id, item_key=row.relative_path, step_name="convert_file"
    )

    if skip_processed and row.converted_at:
        service.skip_job_item(engine, item_id, "Already converted; skipped.")
        service.log_event(engine, job["id"], row.id, "info", "job_item_skipped", "Already converted; skipped.")
        return "completed", "File already converted; skipped."

    service.start_job_item(engine, item_id)
    service.log_event(engine, job["id"], row.id, "info", "job_item_started", f"Converting {row.relative_path}")
    try:
        outcome = _convert_one_file(
            engine, job["id"], item_id, access, row, profile, mode, profile_id,
            min_size_reduction_percent=min_size_reduction_percent,
        )
        service.complete_job_item(engine, item_id, output_ref=outcome["output_ref"], message="Converted.")
        service.log_event(engine, job["id"], row.id, "info", "job_item_completed", f"Converted {row.relative_path}")
        return "completed", "File converted."
    except ConversionSkipped as exc:
        service.skip_job_item(engine, item_id, message=str(exc))
        service.log_event(engine, job["id"], row.id, "info", "job_item_skipped", f"Skipped: {exc}")
        return "completed", str(exc)
    except Exception as exc:  # noqa: BLE001 - failure is reported through the job, not raised further
        service.fail_job_item(engine, item_id, message=str(exc))
        service.log_event(
            engine, job["id"], row.id, "error", "job_item_failed", f"Failed to convert {row.relative_path}: {exc}"
        )
        return "failed", str(exc)


def _process_variant(engine, job_id: str, access: SourceAccess, old_path: Path, row, profile: dict, overrides: dict) -> bool:
    """One variant, run from inside a batch's thread pool -- every variant
    is an independent encode of the same already-local-copied source file
    (see `_run_variant_sweep`), the clearest "one file, many threads" case
    in this codebase (post-V1, user request)."""
    suffix = conversion.encode_variant_suffix(profile, overrides)
    item_id = service.create_job_item(engine, job_id, file_id=row.id, item_key=suffix, step_name="convert_variant")
    service.start_job_item(engine, item_id)
    service.log_event(engine, job_id, row.id, "info", "job_item_started", f"Encoding variant {suffix}")
    try:
        outcome = _create_variant(engine, job_id, item_id, access, old_path, row, profile, overrides)
        service.complete_job_item(engine, item_id, output_ref=outcome["output_ref"], message="Variant produced.")
        service.log_event(engine, job_id, row.id, "info", "job_item_completed", f"Variant {suffix} produced.")
        return True
    except Exception as exc:  # noqa: BLE001 - one variant's failure must not abort the sweep
        service.fail_job_item(engine, item_id, message=str(exc))
        service.log_event(engine, job_id, row.id, "error", "job_item_failed", f"Variant {suffix} failed: {exc}")
        return False


def _run_variant_sweep(
    engine, job: dict, access: SourceAccess, row, profile: dict, variants: list[dict], worker_count: int
) -> tuple[str, str]:
    if not access.exists(row.relative_path):
        raise RuntimeError("Source file no longer exists on the source.")

    processed = 0
    failed = 0
    total = len(variants)
    service.set_job_total_items(engine, job["id"], total)

    with access.local_copy(row.relative_path) as old_path:
        index = 0
        while index < total:
            stop = service.check_stop_requested(job["id"])
            if stop:
                verb = "Cancelled" if stop == "cancel" else "Paused"
                status = "cancelled" if stop == "cancel" else "paused"
                message = f"{verb} after {processed} of {total} variant(s)."
                service.log_event(engine, job["id"], None, "info", f"job_{stop}_honored", message)
                return status, message

            chunk = variants[index : index + worker_count]
            with ThreadPoolExecutor(max_workers=len(chunk)) as executor:
                results = list(
                    executor.map(
                        lambda overrides: _process_variant(engine, job["id"], access, old_path, row, profile, overrides),
                        chunk,
                    )
                )
            for ok in results:
                if ok:
                    processed += 1
                else:
                    failed += 1
            index += worker_count

    summary = f"Produced {processed} of {total} variant(s)"
    if failed:
        summary += f", {failed} failed"
    summary += "."

    status = "failed" if failed and processed == 0 else "completed"
    return status, summary
