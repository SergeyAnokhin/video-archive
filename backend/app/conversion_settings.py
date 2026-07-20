"""Global conversion settings singleton (user report): the minimum
size-reduction percentage a converted output must achieve to replace the
source. A production/test-mode replace whose output doesn't shrink the
source by at least this much is skipped instead -- the original is kept
untouched -- rather than landing a conversion that wasn't actually worth it
(most consequential for a directory-scope batch job converting many files
unattended). Read once at job launch by `app/jobs/convert.py`, same
singleton convention as `performance_settings`/`playback_settings`/
`backup_settings`/`interface_settings`.

Also holds `ffmpeg_timeout_seconds` (user report: a slow encode on a large
file was killed by the previously-hardcoded 3600s limit in
`app/conversion.py::run_ffmpeg`) -- how long a single ffmpeg encode may run
before being force-killed and the job item failed. Read per-file by
`app/jobs/convert.py::_encode_and_validate` (not once at job launch like
`min_size_reduction_percent`) so a mid-job settings change takes effect on
the next file without restarting the job.

Also holds `direct_write_enabled`: the global switch for conversion's write
side to use the same UNC fast path a direct-access SMB source's *reads*
already get for free -- writing the encoded temp file straight onto the
share and committing it with a raw filesystem rename instead of a
smbclient download+upload round trip. Off by default; only takes effect for
a source that also has its own per-source `direct_access_enabled` on and a
working UNC session (`app/sources/windows_unc.py`) -- otherwise conversion's
write side is unchanged. Read once at job launch by `app/jobs/convert.py`,
same convention as `min_size_reduction_percent`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

DEFAULT_MIN_SIZE_REDUCTION_PERCENT = 20
MIN_MIN_SIZE_REDUCTION_PERCENT = 0
MAX_MIN_SIZE_REDUCTION_PERCENT = 90

DEFAULT_FFMPEG_TIMEOUT_SECONDS = 3600
MIN_FFMPEG_TIMEOUT_SECONDS = 60
MAX_FFMPEG_TIMEOUT_SECONDS = 24 * 60 * 60

DEFAULT_DIRECT_WRITE_ENABLED = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    return {
        "min_size_reduction_percent": row.min_size_reduction_percent,
        "ffmpeg_timeout_seconds": row.ffmpeg_timeout_seconds,
        "direct_write_enabled": bool(row.direct_write_enabled),
        "updated_at": row.updated_at,
    }


def get_settings(engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM conversion_settings WHERE id = 1")).fetchone()
    return _row_to_dict(row)


def update_settings(engine, data: dict) -> dict:
    # `.get(..., current[...])` rather than strict indexing (unlike the
    # otherwise-similar backend_health_settings) so a caller updating just
    # one field -- e.g. existing tests that only ever set
    # `min_size_reduction_percent` -- doesn't need to know about every field
    # this singleton happens to hold. The frontend still sends both fields
    # together (see ConversionProfilesSection.tsx) purely because a stale
    # `settings` value in React state would otherwise round-trip the old
    # number right back; this fallback is what makes that redundant rather
    # than required.
    current = get_settings(engine)
    value = max(
        MIN_MIN_SIZE_REDUCTION_PERCENT,
        min(
            MAX_MIN_SIZE_REDUCTION_PERCENT,
            data.get("min_size_reduction_percent", current["min_size_reduction_percent"]),
        ),
    )
    timeout = max(
        MIN_FFMPEG_TIMEOUT_SECONDS,
        min(MAX_FFMPEG_TIMEOUT_SECONDS, data.get("ffmpeg_timeout_seconds", current["ffmpeg_timeout_seconds"])),
    )
    direct_write_enabled = bool(data.get("direct_write_enabled", current["direct_write_enabled"]))
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE conversion_settings SET min_size_reduction_percent = :value, "
                "ffmpeg_timeout_seconds = :timeout, direct_write_enabled = :direct_write_enabled, "
                "updated_at = :now WHERE id = 1"
            ),
            {"value": value, "timeout": timeout, "direct_write_enabled": direct_write_enabled, "now": now},
        )
    return get_settings(engine)


def seed_default_settings(conn) -> None:
    """Idempotently insert the singleton settings row. Called once from
    `init_db()` right after the migration that creates the table."""
    conn.execute(
        text(
            "INSERT OR IGNORE INTO conversion_settings "
            "(id, min_size_reduction_percent, ffmpeg_timeout_seconds, direct_write_enabled, updated_at) "
            "VALUES (1, :value, :timeout, :direct_write_enabled, :now)"
        ),
        {
            "value": DEFAULT_MIN_SIZE_REDUCTION_PERCENT,
            "timeout": DEFAULT_FFMPEG_TIMEOUT_SECONDS,
            "direct_write_enabled": DEFAULT_DIRECT_WRITE_ENABLED,
            "now": _now(),
        },
    )
