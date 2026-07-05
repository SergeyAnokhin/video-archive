from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from app.conversion_profile_service import ConversionProfileService
from app.conversion_service import ConversionService
from app.db import initialize_database
from app.job_service import JobService, _build_tune_variants
from app.library_service import LibraryService
from app.provider_settings_service import ProviderSettingsService
from app.secrets import SecretStore
from app.source_service import SourceService, parse_source_payload
from app.tagging_service import TaggingService


class FakeTuneConversionService(ConversionService):
    """Records every convert_file call so tests can assert on the variant parameters used."""

    def __init__(self) -> None:
        super().__init__(ffmpeg_binary="fake-ffmpeg", ffprobe_binary="fake-ffprobe")
        self.calls: list[dict] = []

    def convert_file(self, *, source_root: str, file_row: dict, profile: dict, mode: str, output_suffix: str | None = None) -> dict:
        self.calls.append({"profile": profile, "mode": mode, "output_suffix": output_suffix})
        source_path = Path(file_row["path"])
        target_path = source_path.with_name(f"{source_path.stem}.__tune__{output_suffix}.mp4")
        target_path.write_bytes(b"tuned-output")
        return {
            "path": str(target_path),
            "relative_path": target_path.relative_to(Path(source_root)).as_posix(),
            "file_name": target_path.name,
            "extension": target_path.suffix.lower(),
            "size_bytes": int(target_path.stat().st_size),
            "modified_at": "2026-07-05T12:00:00Z",
            "output_ref": str(target_path),
            "validation": {"codec_name": profile["video_codec"], "format_name": "mp4"},
        }


class TuneWorkflowTests(unittest.TestCase):
    def test_build_tune_variants_covers_all_sweep_axes(self) -> None:
        base_profile = {"video_codec": "h265", "max_dimension": 1920, "quality_value": "23"}
        sweep = {
            "dimension_values": [1000, 900, 800],
            "quality_values": ["20", "26"],
            "codec_values": ["h264"],
        }
        variants = _build_tune_variants(sweep, base_profile)
        labels = [variant["label"] for variant in variants]

        self.assertIn("dim-1000", labels)
        self.assertIn("dim-900", labels)
        self.assertIn("dim-800", labels)
        self.assertIn("quality-20", labels)
        self.assertIn("quality-26", labels)
        self.assertIn("codec-h264", labels)
        self.assertEqual(len(variants), 6)

    def test_tune_job_generates_separate_outputs_and_never_replaces_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "library"
            (source_root / "clips").mkdir(parents=True)
            source_file = source_root / "clips" / "One.mp4"
            source_file.write_bytes(b"original")

            db_path = root / "video_archive.db"
            secrets_path = root / "secrets.json"
            initialize_database(db_path)
            source_service = SourceService(db_path, SecretStore(secrets_path))
            source_service.replace_active_source(
                parse_source_payload(
                    {"name": "Archive NAS", "protocol": "smb", "host": "nas.local", "port": 445, "root_path": str(source_root)}
                )
            )
            library_service = LibraryService(db_path, source_service)
            profile_service = ConversionProfileService(db_path)
            source = source_service.get_active_source()
            assert source is not None
            library_service.scan_source(source, "")
            file_id = library_service.list_files("clips")[0]["id"]

            fake_conversion = FakeTuneConversionService()
            job_service = JobService(
                db_path,
                source_service,
                library_service,
                profile_service,
                fake_conversion,
                _StubPreviewService(),
                _StubTaggingService(),
            )
            job_service.start()
            self.addCleanup(job_service.shutdown)

            job = job_service.create_tune_file_job(
                file_id,
                {"dimension_values": [1000, 900], "quality_values": [], "codec_values": []},
            )
            completed = _wait_for_terminal_status(job_service, job["id"])
            items = job_service.list_job_items(job["id"])

            self.assertEqual(completed["status"], "completed")
            self.assertEqual(len(items), 2)
            self.assertTrue(all(item["status"] == "completed" for item in items))
            self.assertTrue(source_file.exists())
            self.assertTrue((source_root / "clips" / "One.__tune__dim-1000.mp4").exists())
            self.assertTrue((source_root / "clips" / "One.__tune__dim-900.mp4").exists())
            self.assertEqual(len(fake_conversion.calls), 2)
            self.assertTrue(all(call["mode"] == "tune" for call in fake_conversion.calls))

    def test_promote_completed_variant_creates_conversion_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "library"
            (source_root / "clips").mkdir(parents=True)
            (source_root / "clips" / "One.mp4").write_bytes(b"original")

            db_path = root / "video_archive.db"
            secrets_path = root / "secrets.json"
            initialize_database(db_path)
            source_service = SourceService(db_path, SecretStore(secrets_path))
            source_service.replace_active_source(
                parse_source_payload(
                    {"name": "Archive NAS", "protocol": "smb", "host": "nas.local", "port": 445, "root_path": str(source_root)}
                )
            )
            library_service = LibraryService(db_path, source_service)
            profile_service = ConversionProfileService(db_path)
            source = source_service.get_active_source()
            assert source is not None
            library_service.scan_source(source, "")
            file_id = library_service.list_files("clips")[0]["id"]

            job_service = JobService(
                db_path,
                source_service,
                library_service,
                profile_service,
                FakeTuneConversionService(),
                _StubPreviewService(),
                _StubTaggingService(),
            )
            job_service.start()
            self.addCleanup(job_service.shutdown)

            job = job_service.create_tune_file_job(file_id, {"dimension_values": [1000]})
            completed = _wait_for_terminal_status(job_service, job["id"])
            item = job_service.list_job_items(job["id"])[0]

            profile = profile_service.create_profile_from_variant(
                name="Promoted from tuning",
                variant_params=item["variant_params"],
            )

            self.assertEqual(completed["status"], "completed")
            self.assertEqual(profile["max_dimension"], 1000)
            self.assertEqual(profile["name"], "Promoted from tuning")
            self.assertIn(profile["id"], [p["id"] for p in profile_service.list_profiles()])


class _StubPreviewService:
    def resolve_settings_snapshot(self) -> dict:
        return {}


class _StubTaggingService:
    def resolve_settings_snapshot(self) -> dict:
        return {}


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
