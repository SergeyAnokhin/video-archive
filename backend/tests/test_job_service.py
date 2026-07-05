from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from app.conversion_profile_service import ConversionProfileService
from app.conversion_service import ConversionService
from app.db import initialize_database
from app.job_service import JobService
from app.library_service import LibraryService
from app.secrets import SecretStore
from app.source_service import SourceService, parse_source_payload


class JobServiceTests(unittest.TestCase):
    def test_scan_job_persists_items_and_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, source_service, library_service, job_service, source_root = _build_services(tmp)
            (source_root / "family" / "2024").mkdir(parents=True)
            (source_root / "family" / "2024" / "Beach Sunset.mp4").write_bytes(b"video-data")

            job_service.start()
            self.addCleanup(job_service.shutdown)

            job = job_service.create_scan_job()
            completed = _wait_for_terminal_status(job_service, job["id"])
            items = job_service.list_job_items(job["id"])
            events = job_service.list_events(job_id=job["id"], limit=50)
            files = library_service.list_files("family/2024")

            self.assertEqual(completed["status"], "completed")
            self.assertEqual(completed["item_counts"]["completed"], 1)
            self.assertEqual(len(items), 1)
            self.assertTrue(any(event["event_type"] == "job.started" for event in events))
            self.assertTrue(any(event["event_type"] == "job.completed" for event in events))
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0]["file_name"], "Beach Sunset.mp4")

    def test_cancel_queued_job_and_restart_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, source_service, library_service, job_service, source_root = _build_services(tmp)
            (source_root / "clips").mkdir(parents=True)
            (source_root / "clips" / "One.mp4").write_bytes(b"one")
            source = source_service.get_active_source()
            assert source is not None
            library_service.scan_source(source, "")

            job = job_service.create_convert_directory_job("clips")
            cancelled = job_service.cancel_job(job["id"])
            restarted = job_service.restart_job(job["id"])

            self.assertEqual(cancelled["status"], "cancelled")
            self.assertEqual(cancelled["item_counts"]["cancelled"], 1)
            self.assertEqual(restarted["status"], "queued")

            job_service.start()
            self.addCleanup(job_service.shutdown)
            completed = _wait_for_terminal_status(job_service, restarted["id"])
            items = job_service.list_job_items(restarted["id"])
            events = job_service.list_events(job_id=restarted["id"], limit=50)

            self.assertEqual(completed["status"], "completed")
            self.assertEqual(items[0]["status"], "completed")
            self.assertTrue(any(event["event_type"] == "convert.item.completed" for event in events))

    def test_convert_job_updates_file_metadata_in_production_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, source_service, library_service, job_service, source_root = _build_services(tmp)
            target_dir = source_root / "clips"
            target_dir.mkdir(parents=True)
            source_file = target_dir / "One.mkv"
            source_file.write_bytes(b"original")
            source = source_service.get_active_source()
            assert source is not None
            library_service.scan_source(source, "")

            job_service.start()
            self.addCleanup(job_service.shutdown)

            job = job_service.create_convert_directory_job("clips")
            completed = _wait_for_terminal_status(job_service, job["id"])
            files = library_service.list_files("clips")
            items = job_service.list_job_items(job["id"])

            self.assertEqual(completed["status"], "completed")
            self.assertEqual(files[0]["extension"], ".mp4")
            self.assertEqual(files[0]["conversion_state"], "done")
            self.assertTrue(files[0]["last_error_code"] is None)
            self.assertTrue((target_dir / "One.mp4").exists())
            self.assertFalse(source_file.exists())
            self.assertEqual(items[0]["status"], "completed")
            self.assertEqual(items[0]["output_ref"], str(target_dir / "One.mp4"))

    def test_convert_file_test_mode_preserves_source_and_creates_separate_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, source_service, library_service, job_service, source_root = _build_services(tmp)
            target_dir = source_root / "clips"
            target_dir.mkdir(parents=True)
            source_file = target_dir / "One.mp4"
            source_file.write_bytes(b"original")
            source = source_service.get_active_source()
            assert source is not None
            library_service.scan_source(source, "")
            file_id = library_service.list_files("clips")[0]["id"]

            job_service.start()
            self.addCleanup(job_service.shutdown)

            job = job_service.create_convert_file_job(file_id, mode="test")
            completed = _wait_for_terminal_status(job_service, job["id"])
            files = library_service.list_files("clips")

            self.assertEqual(completed["status"], "completed")
            self.assertTrue(source_file.exists())
            self.assertTrue((target_dir / "One.__test__default-h265-mp4.mp4").exists())
            self.assertEqual(files[0]["conversion_state"], "done")


def _build_services(tmp: str) -> tuple[Path, SourceService, LibraryService, JobService, Path]:
    root = Path(tmp)
    source_root = root / "library"
    source_root.mkdir(parents=True, exist_ok=True)
    db_path = root / "video_archive.db"
    secrets_path = root / "secrets.json"
    initialize_database(db_path)
    source_service = SourceService(db_path, SecretStore(secrets_path))
    payload = parse_source_payload(
        {
            "name": "Archive NAS",
            "protocol": "smb",
            "host": "nas.local",
            "port": 445,
            "root_path": str(source_root),
        }
    )
    source_service.replace_active_source(payload)
    library_service = LibraryService(db_path, source_service)
    profile_service = ConversionProfileService(db_path)
    job_service = JobService(
        db_path,
        source_service,
        library_service,
        profile_service,
        FakeConversionService(),
    )
    return root, source_service, library_service, job_service, source_root


class FakeConversionService(ConversionService):
    def __init__(self) -> None:
        super().__init__(ffmpeg_binary="fake-ffmpeg", ffprobe_binary="fake-ffprobe")

    def convert_file(self, *, source_root: str, file_row: dict, profile: dict, mode: str) -> dict:
        source_path = Path(file_row["path"])
        container = profile["container"]
        if mode == "production":
            final_path = source_path.with_suffix(f".{container}")
            final_path.write_bytes(b"converted")
            if final_path != source_path and source_path.exists():
                source_path.unlink()
        else:
            final_path = source_path.with_name(f"{source_path.stem}.__test__default-h265-mp4.{container}")
            final_path.write_bytes(b"converted-test")

        return {
            "path": str(final_path),
            "relative_path": final_path.relative_to(Path(source_root)).as_posix(),
            "file_name": final_path.name,
            "extension": final_path.suffix.lower(),
            "size_bytes": int(final_path.stat().st_size),
            "modified_at": "2026-07-05T12:00:00Z",
            "output_ref": str(final_path),
            "validation": {"codec_name": "hevc", "format_name": "mp4"},
        }


def _wait_for_terminal_status(job_service: JobService, job_id: str, timeout: float = 5) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = job_service.get_job(job_id)
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for job {job_id} to reach a terminal status.")


if __name__ == "__main__":
    unittest.main()
