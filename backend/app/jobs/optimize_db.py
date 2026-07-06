"""`optimize_db` job execution (Specification §16 "database compact or
optimize"). Runs SQLite's `VACUUM` (reclaims free space and defragments the
file) and `ANALYZE` (refreshes the query planner's statistics) against the
metadata database. Both are whole-database operations with no per-file
notion, so this job never creates job items — a single fast maintenance
action rather than a bulk file workflow, and one that must never alter
semantic metadata (Data Model "Indexing and Cleanup Behavior")."""

from __future__ import annotations

from sqlalchemy import text


def run_optimize_db_job(engine, job: dict) -> tuple[str, str]:
    # VACUUM can't run inside a transaction; AUTOCOMMIT disables the
    # connection's implicit BEGIN for this one connection only.
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text("VACUUM"))
        conn.execute(text("ANALYZE"))
    return "completed", "Database optimized (VACUUM + ANALYZE)."
